"""Regression tests for the P0 audit fixes."""

import math
import os
import sqlite3
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
DB_PATH = os.path.join(ROOT, "data", "processed", "dse.db")


def _ro_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


class TestBuffettScreenerUsesLatestPit(unittest.TestCase):
    def test_uses_latest_tradable_annual_filing(self):
        import buffett_value_screener as b
        conn = _ro_conn()
        try:
            asof = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SQURPHARMA'").fetchone()[0]
            eps, nav = conn.execute("""
                SELECT eps, nav FROM fundamentals_pit
                WHERE ticker='SQURPHARMA' AND filing_type='annual' AND eps IS NOT NULL
                  AND tradable_date <= ? AND publication_date <= ?
                ORDER BY tradable_date DESC, publication_date DESC, snapshot_date DESC LIMIT 1
            """, (asof, asof)).fetchone()
            res = b.evaluate_ticker_12factors("SQURPHARMA", conn, {}, {})
        finally:
            conn.close()
        self.assertAlmostEqual(res["details"]["f1"]["graham_ceiling"], round(math.sqrt(22.5 * eps * nav), 2), places=2)


class TestShariahExclusionIsSectorFirst(unittest.TestCase):
    def test_non_financial_tickers_with_finance_substrings_are_not_excluded(self):
        from unified_score import is_shariah_excluded_company, is_financial_company
        for sector, ticker in (("Food_Beverage", "FINEFOODS"), ("Pharmaceuticals", "ACTIVEFINE")):
            self.assertFalse(is_shariah_excluded_company(sector, ticker=ticker))
            self.assertFalse(is_financial_company(sector, ticker))

    def test_real_financials_and_unknown_sector_fallback_still_excluded(self):
        from unified_score import is_shariah_excluded_company
        self.assertTrue(is_shariah_excluded_company("Banking", ticker="EBL"))
        self.assertTrue(is_shariah_excluded_company("Mutual Funds", ticker="1JANATAMF"))
        self.assertTrue(is_shariah_excluded_company("Unknown", ticker="NEWFINCO"))
        self.assertTrue(is_shariah_excluded_company("Food_Beverage", ticker="BATBC"))
        self.assertTrue(is_shariah_excluded_company("Unknown", name="National Credit and Commerce Bank PLC."))
        self.assertFalse(is_shariah_excluded_company("Unknown", name="Bankers Choice Textiles"))

    def test_debt_gate_applies_to_non_financial_substring_tickers(self):
        from unified_score import score_features
        r = score_features(pe=5, debt_equity=2.0, dividend_yield=5, rsi_14=50,
                           sector="Food_Beverage", ticker="FINEFOODS", close=100, halal_tier="off")
        self.assertIn("debt_gate", r["gate_reasons"])


class TestMissingDebtEquityFailsClosed(unittest.TestCase):
    def test_halal_guard_blocks_missing_de(self):
        from halal_guard import HalalGuard
        g = HalalGuard(profile={"custom_exclusions": {}})
        for tier in ("flexible", "strict"):
            r = g.is_eligible("TESTX", tier=tier, pit_row={"sector": "Pharmaceuticals", "debt_equity": None},
                              dses_row={"dses": 1})
            self.assertFalse(r["eligible"], tier)
            self.assertIn("L2_debt_unverified", r["reasons"])

    def test_strict_uses_total_de_when_long_term_missing(self):
        from halal_guard import HalalGuard
        g = HalalGuard(profile={"custom_exclusions": {}})
        lt_max = g.gates_for("strict")["L2_long_term_debt_equity_max"]
        r = g.is_eligible("TESTX", tier="strict", pit_row={"sector": "Pharmaceuticals", "debt_equity": lt_max + 0.05},
                          dses_row={"dses": 1})
        self.assertFalse(r["eligible"])
        self.assertTrue(any(x.startswith("L2_lt_debt") for x in r["reasons"]))
        ok = g.is_eligible("TESTX", tier="strict", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.01},
                           dses_row={"dses": 1})
        self.assertTrue(ok["eligible"])

    def test_strict_is_defined_by_haram_activity_and_interest_not_index_membership(self):
        from halal_guard import HalalGuard
        g = HalalGuard(profile={"custom_exclusions": {}})
        clean = g.is_eligible("TESTX", tier="strict", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.01})
        bank = g.is_eligible("TESTB", tier="strict", pit_row={"sector": "Banking", "debt_equity": 0.01})
        tobacco = g.is_eligible("BATBC", tier="strict", pit_row={"sector": "Food_Beverage", "debt_equity": 0.0})
        leveraged = g.is_eligible("TESTL", tier="strict", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.9})
        self.assertTrue(clean["eligible"])
        self.assertFalse(bank["eligible"])
        self.assertFalse(tobacco["eligible"])
        self.assertFalse(leveraged["eligible"])

    def test_five_factor_never_passes_missing_de(self):
        import five_factor_fundamental_screener as f
        rows = f.run_5_factor_screener(halal_tier="off")
        self.assertTrue(rows)
        self.assertTrue(all(r["de"] is not None for r in rows))


class TestDrawdownKillUsesMarkToMarket(unittest.TestCase):
    def _conn(self, close):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
        conn.execute("INSERT INTO prices VALUES ('AAA', '2026-11-19', ?)", (close,))
        return conn

    def test_market_drop_trips_kill_even_though_cost_basis_is_flat(self):
        import portfolio_manager as pm
        p = {"cash_balance_bdt": 0.0, "holdings": [{"ticker": "AAA", "shares": 100, "cost_basis": 10000.0}],
             "mutual_funds": [], "high_water_mark_bdt": 10000.0}
        nw = pm.compute_mark_to_market_net_worth(p, self._conn(85.0))
        self.assertEqual(nw, 8500.0)
        killed, dd, _ = pm.check_portfolio_drawdown_kill(p, nw)
        self.assertTrue(killed)
        self.assertEqual(dd, 15.0)

    def test_capital_change_shifts_hwm(self):
        import portfolio_manager as pm
        state = {"total_capital_bdt": 10000.0, "cash_balance_bdt": 10000.0, "high_water_mark_bdt": 10000.0}
        orig_load, orig_save = pm.load_portfolio, pm.save_portfolio
        pm.load_portfolio = lambda user_id="default_user": state
        pm.save_portfolio = lambda p, user_id="default_user": None
        try:
            pm.set_capital(4000.0)
        finally:
            pm.load_portfolio, pm.save_portfolio = orig_load, orig_save
        self.assertEqual(state["high_water_mark_bdt"], 4000.0)
        killed, _, _ = pm.check_portfolio_drawdown_kill(state, 4000.0)
        self.assertFalse(killed)


class TestDividendEntitlementBySettlement(unittest.TestCase):
    def _conn(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE trading_calendar (date TEXT PRIMARY KEY, is_trading_day INTEGER)")
        conn.execute("CREATE TABLE companies (ticker TEXT, category TEXT)")
        conn.execute("INSERT INTO companies VALUES ('AAA', 'A')")
        import datetime as dt
        d = dt.date(2026, 10, 1)
        while d <= dt.date(2026, 12, 31):
            conn.execute("INSERT INTO trading_calendar VALUES (?, ?)", (d.isoformat(), 0 if d.weekday() in (4, 5) else 1))
            d += dt.timedelta(days=1)
        return conn

    def test_top_up_after_record_date_keeps_original_lot_entitled(self):
        from corporate_action_processor import entitled_shares
        port = {"holdings": [{"ticker": "AAA", "shares": 8, "bought_at": "2026-10-05"}],
                "history": [{"action": "BUY", "ticker": "AAA", "shares": 5, "date": "2026-10-05"},
                            {"action": "BUY", "ticker": "AAA", "shares": 3, "date": "2026-11-05"}]}
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-01", self._conn()), 5)
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-09", self._conn()), 8)

    def test_buy_on_record_date_is_not_entitled(self):
        from corporate_action_processor import entitled_shares
        port = {"holdings": [{"ticker": "AAA", "shares": 4, "bought_at": "2026-11-10"}],
                "history": [{"action": "BUY", "ticker": "AAA", "shares": 4, "date": "2026-11-10"}]}
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-10", self._conn()), 0)
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-11", self._conn()), 0)
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-12", self._conn()), 4)

    def test_sale_settling_after_record_date_stays_entitled(self):
        from corporate_action_processor import entitled_shares
        port = {"holdings": [],
                "history": [{"action": "BUY", "ticker": "AAA", "shares": 6, "date": "2026-10-05"},
                            {"action": "SELL", "ticker": "AAA", "shares": 6, "date": "2026-11-11"}]}
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-12", self._conn()), 6)
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-15", self._conn()), 0)

    def test_undated_opening_balance_is_not_entitled(self):
        from corporate_action_processor import entitled_shares
        port = {"holdings": [{"ticker": "AAA", "shares": 10}], "history": []}
        self.assertEqual(entitled_shares(port, "AAA", "2026-11-15", self._conn()), 0)


class TestShadowIcResolutionAndPromotionGate(unittest.TestCase):
    def setUp(self):
        import tempfile
        import model_registry as mr
        self.mr = mr
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.log = os.path.join(self.tmp.name, "shadow.jsonl")
        conn = sqlite3.connect(self.db)
        conn.executescript("""
            CREATE TABLE prices (ticker TEXT, date TEXT, close REAL);
            CREATE TABLE trading_calendar (date TEXT PRIMARY KEY, is_trading_day INTEGER);
            CREATE TABLE corporate_actions (ticker TEXT, record_date TEXT, action_type TEXT);
            CREATE TABLE features_daily (ticker TEXT, date TEXT, close REAL);
        """)
        conn.executemany("INSERT INTO trading_calendar VALUES (?, ?)",
                         [("2026-11-10", 1), ("2026-11-11", 0), ("2026-11-12", 1)])
        self.tickers = [f"T{i:02d}" for i in range(20)]
        for i, t in enumerate(self.tickers):
            conn.execute("INSERT INTO prices VALUES (?, '2026-11-10', 100.0)", (t,))
            conn.execute("INSERT INTO prices VALUES (?, '2026-11-11', 999.0)", (t,))
            conn.execute("INSERT INTO prices VALUES (?, '2026-11-12', ?)", (t, 100.0 + i))
        conn.execute("INSERT INTO corporate_actions VALUES ('T19', '2026-11-12', 'bonus_dividend')")
        conn.commit()
        conn.close()
        self._orig = (mr.DB_PATH, mr.SHADOW_IC_LOG, mr.load_registry)
        from pathlib import Path
        mr.DB_PATH, mr.SHADOW_IC_LOG = Path(self.db), Path(self.log)
        mr.load_registry = lambda: {"champion": {"model_id": "champ", "parameter_hash": "h", "role": "champion",
                                                 "params": {"score": "frozen_epoch2_pit_formula"}},
                                    "challengers": [{"model_id": "adaptive", "parameter_hash": "a",
                                                     "params": {"score": "bayesian_adaptive_v1"}}]}

    def tearDown(self):
        self.mr.DB_PATH, self.mr.SHADOW_IC_LOG, self.mr.load_registry = self._orig
        self.tmp.cleanup()

    def test_resolves_with_next_trading_session_and_stored_scores(self):
        import json
        entry = {"date": "2026-11-10", "forward_date": None, "scores_universe": "full",
                 "closes": {t: 100.0 for t in self.tickers},
                 "models": {"champ": {"rank_ic": None, "n": 0,
                                      "scores": {t: (float(i) if i >= 5 else None) for i, t in enumerate(self.tickers)}}}}
        with open(self.log, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        self.mr.resolve_shadow_ic(backfill=False)
        with open(self.log, encoding="utf-8") as f:
            out = json.loads(f.readline())
        self.assertEqual(out["forward_date"], "2026-11-12")
        self.assertEqual(out["models"]["champ"]["n"], 19)
        # Gated names tie at the bottom, so a perfect ordering gives Spearman just under 1.
        self.assertGreater(out["models"]["champ"]["rank_ic"], 0.98)
        self.assertEqual(out["models"]["adaptive"].get("backfill_skipped"), "adaptive_params_would_leak_future")
        self.assertIsNone(out["models"]["adaptive"]["rank_ic"])

    def test_backfilled_ic_never_counts_toward_promotion(self):
        import json
        with open(self.log, "w", encoding="utf-8") as f:
            f.write(json.dumps({"date": "2026-11-10", "backfilled": True,
                                "models": {"champ": {"rank_ic": 0.1, "backfilled": True}}}) + "\n")
            f.write(json.dumps({"date": "2026-11-12", "models": {"champ": {"rank_ic": 0.2}}}) + "\n")
        self.assertEqual(self.mr._load_shadow_ic_series("champ"), {"2026-11-12": 0.2})
        self.assertEqual(len(self.mr._load_shadow_ic_series("champ", live_only=False)), 2)


class TestPromotionGate(unittest.TestCase):
    def _run(self, n_days, approve):
        import random
        import model_registry as mr
        rng = random.Random(7)
        dates = [f"d{i:04d}" for i in range(n_days)]
        series = {"champ": {d: rng.gauss(0.0, 0.05) for d in dates},
                  "good": {d: rng.gauss(0.04, 0.05) for d in dates}}
        reg = {"champion": {"model_id": "champ", "parameter_hash": "h"},
               "challengers": [{"model_id": "good", "status": "SHADOW", "parameter_hash": "g"}],
               "trial_count": 52, "required_periods": 12, "holm_alpha": 0.05}
        saved = []
        orig = (mr.load_registry, mr.save_registry, mr._load_shadow_ic_series)
        mr.load_registry = lambda: reg
        mr.save_registry = lambda r: saved.append(r)
        mr._load_shadow_ic_series = lambda mid, live_only=True: series[mid]
        try:
            return mr.promote_challenger(approve=approve), saved
        finally:
            mr.load_registry, mr.save_registry, mr._load_shadow_ic_series = orig

    def test_floor_blocks_short_samples(self):
        res, saved = self._run(150, approve=True)
        self.assertFalse(res["ok"])
        self.assertIn("need>=200", res["decisions"][0]["reason"])
        self.assertEqual(saved, [])

    def test_gate_pass_requires_explicit_approval(self):
        res, saved = self._run(260, approve=False)
        self.assertEqual(res.get("pending_approval"), "good")
        self.assertEqual(saved, [])
        res, saved = self._run(260, approve=True)
        self.assertTrue(res["ok"])
        self.assertEqual(len(saved), 1)

    def test_norm_isf_is_exact(self):
        import model_registry as mr
        self.assertAlmostEqual(mr._norm_isf(0.05 / 52), 3.1015, places=3)
        self.assertAlmostEqual(mr._norm_isf(0.025), 1.95996, places=4)


class TestFullHorizonLabels(unittest.TestCase):
    def test_horizon_end_requires_full_window(self):
        from multi_horizon_evaluator import horizon_end_date
        sessions = [f"2026-11-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9)]
        self.assertEqual(horizon_end_date(sessions, "2026-11-02", 3), "2026-11-05")
        self.assertEqual(horizon_end_date(sessions, "2026-11-02", 5), "2026-11-09")
        self.assertIsNone(horizon_end_date(sessions, "2026-11-02", 6))
        self.assertEqual(horizon_end_date(sessions, "2026-11-06", 1), "2026-11-08")

    def test_partial_labels_are_reopened(self):
        from multi_horizon_evaluator import reopen_partial_horizon_labels
        ledger = [
            {"status": "EVALUATED", "horizon_bars": 21, "horizon_bars_used": 10, "actual_outcome": "X", "reward_score": 1},
            {"status": "EVALUATED", "horizon_bars": 21, "horizon_bars_used": 21, "actual_outcome": "Y"},
            {"status": "EVALUATED", "horizon_bars": None, "horizon_bars_used": 10, "actual_outcome": "Z"},
            {"status": "PENDING", "horizon_bars": 21},
        ]
        self.assertEqual(reopen_partial_horizon_labels(ledger, 10), 1)
        self.assertEqual(ledger[0]["status"], "PENDING")
        self.assertNotIn("actual_outcome", ledger[0])
        self.assertEqual(ledger[1]["status"], "EVALUATED")
        self.assertEqual(ledger[2]["status"], "EVALUATED")


class TestSafetyRebalanceRefills(unittest.TestCase):
    def setUp(self):
        import types
        import forward_test_ledger_v2 as fl
        self.fl = fl
        self._orig_fill = fl._fill_price
        fl._fill_price = lambda conn, t, d, px, side: {"price": 100.0, "fill_date": d, "fill_source": "TEST"}
        fake = types.ModuleType("anti_manipulation_engine")
        fake.is_ticker_blacklisted = lambda t, asof_date=None: (False, "")
        self._orig_mod = sys.modules.get("anti_manipulation_engine")
        sys.modules["anti_manipulation_engine"] = fake

    def tearDown(self):
        self.fl._fill_price = self._orig_fill
        if self._orig_mod is not None:
            sys.modules["anti_manipulation_engine"] = self._orig_mod
        else:
            sys.modules.pop("anti_manipulation_engine", None)

    def _elig(self, n):
        return [{"ticker": f"E{i:02d}", "sector": f"S{i}", "close": 100.0, "score": 100 - i} for i in range(n)]

    def _pos(self, t):
        return {"ticker": t, "sector": "X" + t, "shares": 100, "execution_price": 100.0}

    def test_safety_sells_only_ineligible_and_refills(self):
        elig = self._elig(30)
        # E25 is eligible but outside the top 30% (9 names); BAD is no longer eligible.
        positions = [self._pos("E00"), self._pos("E25"), self._pos("BAD")]
        kept, cash, trades = self.fl._rebalance(None, positions, 50000.0, elig, "2026-11-19", False, safety_only=True)
        tickers = {p["ticker"] for p in kept}
        sells = [t["ticker"] for t in trades if t["action"] == "SELL"]
        self.assertEqual(sells, ["BAD"])
        self.assertIn("E25", tickers)
        self.assertNotIn("BAD", tickers)
        self.assertGreater(len(kept), 2)

    def test_killed_strategy_safety_sells_without_refill(self):
        elig = self._elig(30)
        kept, cash, trades = self.fl._rebalance(None, [self._pos("E00"), self._pos("BAD")], 50000.0,
                                                elig, "2026-11-19", True, safety_only=True)
        self.assertEqual([p["ticker"] for p in kept], ["E00"])
        self.assertFalse(any(t["action"] == "BUY" for t in trades))

    def test_scheduled_rebalance_still_trims_outside_top_pct(self):
        elig = self._elig(30)
        kept, _, trades = self.fl._rebalance(None, [self._pos("E25")], 50000.0, elig, "2026-11-19", False)
        self.assertIn("E25", [t["ticker"] for t in trades if t["action"] == "SELL"])


class TestChampionContentHash(unittest.TestCase):
    def test_hash_changes_when_scoring_source_changes(self):
        import tempfile
        import shutil
        from pathlib import Path
        import unified_score as us
        base = us.compute_model_content_hash()
        with tempfile.TemporaryDirectory() as tmp:
            for rel in us.SCORING_SOURCE_FILES:
                dst = Path(tmp) / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(us._BASE / rel, dst)
            orig = us._BASE
            us._BASE = Path(tmp)
            try:
                self.assertEqual(us.compute_model_content_hash(), base)
                crlf = (Path(tmp) / us.SCORING_SOURCE_FILES[0]).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                (Path(tmp) / us.SCORING_SOURCE_FILES[0]).write_bytes(crlf)
                self.assertEqual(us.compute_model_content_hash(), base, "line endings must not matter")
                with open(Path(tmp) / us.SCORING_SOURCE_FILES[1], "a", encoding="utf-8") as f:
                    f.write("\nX = 1\n")
                self.assertNotEqual(us.compute_model_content_hash(), base)
            finally:
                us._BASE = orig

    def test_spec_guard_rejects_drifted_content(self):
        import json
        import tempfile
        from pathlib import Path
        import spec_guard as sg
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "reg.json"
            reg_path.write_text(json.dumps({"champion": {"model_id": "frozen_epoch2_pit_v2",
                                                         "parameter_hash": "acf502bc65914c48",
                                                         "frozen_content_hash": "0000000000000000"}}))
            orig = sg.REGISTRY_PATH
            sg.REGISTRY_PATH = reg_path
            try:
                ok, msg = sg.check_inv5_champion_registry()
            finally:
                sg.REGISTRY_PATH = orig
        self.assertFalse(ok)
        self.assertIn("changed since freeze", msg)


class TestStaleSnapshotGuard(unittest.TestCase):
    def _conn(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL, volume INTEGER)")
        conn.execute("""CREATE TABLE trading_calendar (date TEXT PRIMARY KEY, is_trading_day INTEGER,
                        session_type TEXT, notes TEXT)""")
        for i in range(60):
            conn.execute("INSERT INTO prices VALUES (?, '2026-10-19', ?, ?)", (f"T{i}", 10.0 + i, 1000 + i))
        conn.execute("INSERT INTO trading_calendar VALUES ('2026-10-22', 0, 'holiday', '')")
        conn.execute("INSERT INTO trading_calendar VALUES ('2026-10-17', 0, 'weekend', '')")
        return conn

    def test_replayed_session_is_rejected(self):
        from processor import snapshot_rejection_reason
        conn = self._conn()
        recs = [{"ticker": f"T{i}", "close": 10.0 + i, "volume": 1000 + i} for i in range(60)]
        self.assertIn("stale snapshot", snapshot_rejection_reason(conn, "2026-10-22", recs))

    def test_fresh_prints_on_closed_calendar_day_are_accepted_and_calendar_fixed(self):
        from processor import snapshot_rejection_reason
        conn = self._conn()
        recs = [{"ticker": f"T{i}", "close": 10.5 + i, "volume": 2000 + i} for i in range(60)]
        self.assertIsNone(snapshot_rejection_reason(conn, "2026-10-22", recs))
        self.assertEqual(conn.execute("SELECT is_trading_day FROM trading_calendar WHERE date='2026-10-22'").fetchone()[0], 1)

    def test_scraper_has_no_cached_snapshot_fallback(self):
        with open(os.path.join(ROOT, "scripts", "scraper.py"), encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def scrape_all_prices"):src.index("def scrape_dse_psi_disclosures")]
        self.assertNotIn("RAW_DIR", body)


class TestPitEstimatedFlagIsHonest(unittest.TestCase):
    def _conn(self):
        import datetime as dt
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE fundamentals_pit (id INTEGER PRIMARY KEY, ticker TEXT, snapshot_date TEXT,
                publication_date TEXT, tradable_date TEXT, fiscal_year INTEGER, fiscal_quarter INTEGER,
                publication_is_estimated INTEGER, publication_source TEXT);
            CREATE TABLE trading_calendar (date TEXT PRIMARY KEY, is_trading_day INTEGER);
            CREATE TABLE corporate_actions (ticker TEXT, record_date TEXT, action_type TEXT, ratio REAL,
                cash_amount REAL, notes TEXT);
        """)
        d = dt.date(2024, 1, 1)
        while d <= dt.date(2027, 12, 31):
            conn.execute("INSERT INTO trading_calendar VALUES (?, ?)", (d.isoformat(), 0 if d.weekday() in (4, 5) else 1))
            d += dt.timedelta(days=1)
        rows = [
            (1, "AAA", "2025-06-30", None, None, 2025, 4, 1, "estimated"),
            (2, "BBB", "2025-06-30", None, None, 2025, 4, 1, "estimated"),
            (3, "CCC", "2025-06-30", None, None, 2025, 4, 1, "estimated"),
            (4, "DDD", "2026-10-05", "2026-10-05", "2026-10-06", 2026, 4, 0, "live_scrape"),
            (5, "EEE", "2024-06-30", None, None, 2024, 4, 1, "estimated"),
        ]
        conn.executemany("INSERT INTO fundamentals_pit VALUES (?,?,?,?,?,?,?,?,?)", rows)
        return conn

    def test_tiers(self):
        import pit_disclosure_resolver as r
        orig = r.load_dse_psi_disclosures
        r.load_dse_psi_disclosures = lambda: [
            {"ticker": "AAA", "fiscal_year": 2025, "fiscal_quarter": 4, "date": "2025-10-20"},
            {"ticker": "AAA", "fiscal_year": 2025, "fiscal_quarter": 4, "date": "2025-10-28"},
            {"ticker": "BBB", "fiscal_year": None, "fiscal_quarter": None, "date": "2025-10-23"},
            {"ticker": "EEE", "fiscal_year": None, "fiscal_quarter": None, "date": "2026-11-15"},
        ]
        conn = self._conn()
        try:
            r.resolve_pit_disclosures(conn=conn, force_all=True)
        finally:
            r.load_dse_psi_disclosures = orig
        got = {row[0]: row[1:] for row in conn.execute(
            "SELECT ticker, publication_date, publication_source, publication_is_estimated FROM fundamentals_pit")}
        self.assertEqual(got["AAA"], ("2025-10-20", "dse_psi", 0))
        self.assertEqual(got["BBB"][1:], ("dse_psi", 1))
        self.assertEqual(got["CCC"][1:], ("bsec_statutory_filing", 1))
        self.assertGreaterEqual(got["CCC"][0], "2025-10-28")
        self.assertEqual(got["DDD"], ("2026-10-05", "live_scrape", 0))
        # A disclosure two years after period end is not this period's release.
        self.assertEqual(got["EEE"][1:], ("bsec_statutory_filing", 1))
        self.assertLess(got["EEE"][0], "2024-11-01")


class TestBonusExDateInference(unittest.TestCase):
    def _conn(self, gaps, crash_day=None):
        import datetime as dt
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, close REAL)")
        d = dt.date(2025, 9, 1)
        px = 100.0
        while d <= dt.date(2026, 3, 31):
            if d.weekday() not in (4, 5):
                ds = d.isoformat()
                mkt = 0.9 if ds == crash_day else 1.0
                for i in range(40):
                    conn.execute("INSERT INTO prices VALUES (?, ?, ?, ?)", (f"M{i}", ds, 50.0 * mkt, 50.0 * mkt))
                if ds in gaps:
                    px *= gaps[ds]
                conn.execute("INSERT INTO prices VALUES ('AAA', ?, ?, ?)", (ds, px, px))
            d += dt.timedelta(days=1)
        return conn

    def test_finds_unique_gap(self):
        from corporate_action_processor import infer_bonus_ex_date
        conn = self._conn({"2026-01-12": 1 / 1.15})
        self.assertEqual(infer_bonus_ex_date(conn, "AAA", 1 / 1.15, "2025-12-15"), "2026-01-12")

    def test_ambiguous_or_absent_or_tiny_returns_none(self):
        from corporate_action_processor import infer_bonus_ex_date
        self.assertIsNone(infer_bonus_ex_date(self._conn({}), "AAA", 1 / 1.15, "2025-12-15"))
        two = self._conn({"2025-11-10": 1 / 1.15, "2026-01-12": 1 / 1.15})
        self.assertIsNone(infer_bonus_ex_date(two, "AAA", 1 / 1.15, "2025-12-15"))
        self.assertIsNone(infer_bonus_ex_date(self._conn({"2026-01-12": 1 / 1.02}), "AAA", 1 / 1.02, "2025-12-15"))

    def test_same_day_cash_dividend_is_part_of_expected_gap(self):
        from corporate_action_processor import infer_bonus_ex_date
        # 17.5% bonus + Tk 17.5 cash on a Tk 100 stock: (100 - 17.5) / 1.175 = 70.2 -> ratio 0.702
        conn = self._conn({"2026-01-12": 0.702})
        self.assertIsNone(infer_bonus_ex_date(conn, "AAA", 1 / 1.175, "2025-12-15"))
        self.assertEqual(infer_bonus_ex_date(conn, "AAA", 1 / 1.175, "2025-12-15", cash_per_share=17.5), "2026-01-12")

    def test_broad_market_drop_day_is_rejected(self):
        import datetime as dt
        from corporate_action_processor import infer_bonus_ex_date
        conn = self._conn({"2026-01-12": 1 / 1.15})
        # Floor-removal style day: median flat but 20% of names fall 13%.
        for i in range(8):
            conn.execute("UPDATE prices SET close = close * 0.87 WHERE ticker = ? AND date >= '2026-01-12'", (f"M{i}",))
        self.assertIsNone(infer_bonus_ex_date(conn, "AAA", 1 / 1.15, "2025-12-15"))

    def test_market_crash_day_is_not_an_ex_date(self):
        from corporate_action_processor import infer_bonus_ex_date
        conn = self._conn({"2026-01-12": 0.9}, crash_day="2026-01-12")
        self.assertIsNone(infer_bonus_ex_date(conn, "AAA", 1 / 1.10, "2025-12-15"))


class TestWriteGuardsAndDataGate(unittest.TestCase):
    """Corruption must be rejected at write time, and anything that slips in must fail the data gate."""

    def test_real_db_has_all_guards(self):
        from db_guards import missing_data_guards
        conn = _ro_conn()
        try:
            self.assertEqual(missing_data_guards(conn), [])
        finally:
            conn.close()

    def test_guards_reject_each_corruption_class(self):
        sys.path.insert(0, os.path.dirname(__file__))
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            closed = conn.execute("SELECT date FROM trading_calendar WHERE is_trading_day = 0 ORDER BY date DESC LIMIT 1").fetchone()[0]
            bad = [
                ("INSERT INTO prices (ticker, date, open, high, low, close, volume, value) VALUES ('ZZ', ?, 1, 1, 1, 1, 0, 0)", (closed,)),
                ("INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes) "
                 "VALUES ('ZZ', '2026-10-05', 'MUTUAL_FUND_NAV_DISCOVERY', 0, 0, 0.6, 'plug')", ()),
                ("INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes) "
                 "VALUES ('ZZ', '2025-12-15', 'bonus_dividend', 0.1, 0, 0.909, '10% (Historical estimated)')", ()),
                ("UPDATE fundamentals_pit SET publication_is_estimated = 0 WHERE publication_source = 'bsec_statutory_filing'", ()),
            ]
            for sql, args in bad:
                with self.assertRaises(sqlite3.DatabaseError, msg=sql[:60]):
                    conn.execute(sql, args)
            conn.close()

    def test_data_gate_catches_corruption_that_bypassed_guards(self):
        import integrity_harness as ih
        sys.path.insert(0, os.path.dirname(__file__))
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            self.assertFalse([c for c in ih.run_data_checks(conn) if c["status"] == "FAIL" and c["check"] != "portfolio_ledger_consistent"])
            conn.execute("DROP TRIGGER guard_prices_insert")
            last = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
            conn.execute("UPDATE trading_calendar SET is_trading_day = 0 WHERE date = ?", (last,))
            conn.commit()
            fails = {c["check"] for c in ih.run_data_checks(conn) if c["status"] == "FAIL"}
            conn.close()
        self.assertIn("write_guards_installed", fails)
        self.assertIn("no_bars_on_closed_days", fails)

    def test_daily_runners_stop_on_data_gate(self):
        with open(os.path.join(ROOT, "scripts", "auto_daily_alpha_routine.py"), encoding="utf-8") as f:
            alpha = f.read()
        gate = alpha.index('"--data-gate"')
        self.assertLess(gate, alpha.index("forward_test_ledger_v2.py"))
        self.assertIn("sys.exit(1)", alpha[gate:gate + 600])
        with open(os.path.join(ROOT, "scripts", "run_daily_pipeline.py"), encoding="utf-8") as f:
            pipe = f.read()
        self.assertLess(pipe.index('"--data-gate"'), pipe.index("forward_test_ledger_v2.py"))

    def test_nav_parser_reads_the_value_shown_for_the_fund(self):
        import io
        import mutual_fund_tracker as mft
        page = ("<div>Invest Now NAV 12.203 <b>Shanta First Income Unit Fund</b> NAV 12.797 Shanta Fixed Income Fund "
                "NAV 10.635 Shanta Amanah Shariah Fund Get started</div> Shanta Amanah Shariah Fund 24.042 other")

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        orig = mft.urllib.request.urlopen
        mft.urllib.request.urlopen = lambda req, timeout=10: _Resp(page.encode("utf-8"))
        try:
            self.assertEqual(mft.fetch_shanta_nav_online()["nav_redemption"], 10.635)
            self.assertEqual(mft.fetch_shanta_nav_online("Shanta Fixed Income Fund")["nav_redemption"], 12.797)
            self.assertIsNone(mft.fetch_shanta_nav_online("Unknown Fund"))
        finally:
            mft.urllib.request.urlopen = orig

    def test_implausible_nav_jump_is_rejected(self):
        import mutual_fund_tracker as mft
        orig = mft.get_latest_nav_from_db
        mft.get_latest_nav_from_db = lambda name: {"nav_redemption": 10.631}
        try:
            self.assertFalse(mft.nav_is_plausible("X", 24.042))
            self.assertTrue(mft.nav_is_plausible("X", 10.635))
        finally:
            mft.get_latest_nav_from_db = orig

    def test_mutual_fund_tracker_has_no_guessed_nav(self):
        with open(os.path.join(ROOT, "scripts", "mutual_fund_tracker.py"), encoding="utf-8") as f:
            self.assertNotIn("10.631", f.read())


class TestFiscalPeriodIsNeverGuessed(unittest.TestCase):
    def test_period_comes_only_from_audited_years(self):
        from processor import _detect_fiscal_period
        self.assertIsNone(_detect_fiscal_period({"paid_up_capital": "2029.5", "dividend_history": "2030: 10%C dec"}))
        self.assertEqual(_detect_fiscal_period({"multi_year_financials": [{"year": "2024"}, {"year": 2025.0}]}), (2025, 4))

    def test_latest_ended_quarter_respects_fiscal_year_end(self):
        from processor import latest_ended_quarter
        self.assertEqual(latest_ended_quarter("2026-11-20", 6), (2027, 1))
        self.assertEqual(latest_ended_quarter("2026-11-20", 12), (2026, 3))
        self.assertEqual(latest_ended_quarter("2026-09-29", 12), (2026, 2))
        self.assertEqual(latest_ended_quarter("2026-11-20", 3), (2027, 2))

    def test_company_page_snapshot_writes_no_pit_row_and_no_future_period(self):
        import processor
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            try:
                before = conn.execute("SELECT COUNT(*) FROM fundamentals_pit WHERE ticker='DELTALIFE'").fetchone()[0]
                raw = {"ticker": "DELTALIFE", "eps": "0", "paid_up_capital": "2029", "dividend_history": "2030 dec"}
                processor.upsert_fundamentals(conn, processor.parse_fundamentals_row("DELTALIFE", raw), raw, "2026-11-20")
                after = conn.execute("SELECT COUNT(*) FROM fundamentals_pit WHERE ticker='DELTALIFE'").fetchone()[0]
                years = conn.execute("SELECT MAX(year) FROM fundamentals WHERE ticker='DELTALIFE'").fetchone()[0]
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("INSERT INTO fundamentals_pit (ticker, snapshot_date) VALUES ('ZZ', '2999-12-31')")
            finally:
                conn.close()
        self.assertEqual(before, after)
        self.assertLessEqual(years, 2026)


if __name__ == "__main__":
    unittest.main()
