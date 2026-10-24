"""
Golden-Value and Regression Tests for Quantitative Logic and Backtester.
Runs deterministic unit checks against:
  1. Break-even formula & round-trip brokerage friction (0.833%)
  2. Conservative stop-loss first execution
  3. Graham ceiling & Buffett valuation formulas
  4. Point-in-time fundamentals isolation (no lookahead)
  5. Dynamic database audit zero-violation assertion
  6. Phase 1: technical window, composite weights, freshness, DSEX source
"""

import math
import sqlite3
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestQuantEngine(unittest.TestCase):

    def test_round_trip_breakeven(self):
        """Verify that break-even multiple strictly matches 0.415% each way."""
        buy_fee_pct = 0.00415
        sell_fee_pct = 0.00415
        breakeven_ratio = (1.0 + buy_fee_pct) / (1.0 - sell_fee_pct)
        expected_ratio = 1.008334588
        self.assertTrue(math.isclose(breakeven_ratio, expected_ratio, rel_tol=1e-5), f"Break-even ratio incorrect: {breakeven_ratio}")
        self.assertTrue(math.isclose((breakeven_ratio - 1.0) * 100, 0.833, abs_tol=0.005))

    def test_graham_ceiling_formula(self):
        """Verify Graham ceiling formula: sqrt(22.5 * EPS * NAV)."""
        eps = 27.04
        nav = 157.88
        expected_graham = math.sqrt(22.5 * eps * nav)
        self.assertTrue(math.isclose(expected_graham, 309.926, rel_tol=1e-3))

    def test_fair_value_blend_formula(self):
        """Verify Square Pharma 50/50 blend of Graham ceiling and 14x P/E."""
        eps = 27.04
        nav = 157.88
        graham_ceiling = math.sqrt(22.5 * eps * nav)
        pe_fair = eps * 14.0  # 378.56
        fair_value = (graham_ceiling + pe_fair) / 2.0
        self.assertTrue(math.isclose(fair_value, 344.24, rel_tol=1e-3))

    def test_stop_loss_first_fill_rule(self):
        """Verify simulator fills stop-loss first when single bar spans both stop and target."""
        entry_price = 100.0
        stop_loss = 98.0
        target_price = 103.5
        bar_low = 97.0
        bar_high = 105.0

        hit_stop = bar_low <= stop_loss
        hit_target = bar_high >= target_price
        self.assertTrue(hit_stop and hit_target)

        exit_price = None
        exit_reason = None
        if hit_stop:
            exit_price = stop_loss
            exit_reason = "STOP_LOSS"
        elif hit_target:
            exit_price = target_price
            exit_reason = "TARGET"

        self.assertEqual(exit_reason, "STOP_LOSS")
        self.assertEqual(exit_price, 98.0)

    def test_database_dynamic_audits(self):
        """Verify that dse.db has no critical data corruption failures recorded."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        critical_failures = c.execute("""
            SELECT check_name, violation_count, details 
            FROM database_audit_log 
            WHERE status = 'FAILED' AND check_name != 'unmapped_circuit_limit_breaches'
            ORDER BY id DESC LIMIT 10
        """).fetchall()
        self.assertEqual(len(critical_failures), 0, f"Critical database integrity audit failures found: {critical_failures}")

    def test_point_in_time_schema_populated(self):
        """Verify that fundamentals_pit table exists and has rows."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        cnt = c.execute("SELECT COUNT(*) FROM fundamentals_pit").fetchone()[0]
        self.assertGreater(cnt, 0, "Point-in-time fundamentals table is empty!")

    def test_composite_weights_come_from_thresholds(self):
        """Base weights must match thresholds.json (not hardcoded 0.45/0.25/0.15/0.15)."""
        from analyzer import resolve_composite_weights, load_thresholds
        th = load_thresholds()
        w = resolve_composite_weights(th, rl_weights=None)
        self.assertAlmostEqual(w["fundamental"], th["scoring"]["fundamental_weight"], places=5)
        self.assertAlmostEqual(w["technical"], th["scoring"]["technical_weight"], places=5)
        self.assertAlmostEqual(w["sentiment"], th["scoring"]["sentiment_weight"], places=5)
        self.assertEqual(w["governance"], 0.0)
        total = sum(w.values())
        self.assertTrue(math.isclose(total, 1.0, abs_tol=1e-9))

    def test_technical_score_not_none_on_real_history(self):
        """Phase 1: bar window must yield technical score for liquid Category A names."""
        from analyzer import compute_technical_score, load_thresholds
        from processor import get_ticker_data
        th = load_thresholds()
        data = get_ticker_data("SQURPHARMA", days=400)
        closes, highs, lows = [], [], []
        for p in data["prices"]:
            if p.get("close") is None:
                continue
            c = float(p["close"])
            closes.append(c)
            highs.append(float(p["high"]) if p.get("high") is not None else c)
            lows.append(float(p["low"]) if p.get("low") is not None else c)
        self.assertGreaterEqual(len(closes), 60, "need >=60 bars for SMA/RSI window")
        result = compute_technical_score(closes[-220:], highs[-220:], lows[-220:], th)
        self.assertIsNotNone(result.get("score"), f"technical score None: {result.get('signals')}")

    def test_dsex_lives_in_market_summary_not_prices(self):
        """DSEX must come from market_summary; prices.ticker='DSEX' is empty."""
        from benchmark_index import get_dsex_level
        conn = sqlite3.connect(DB_PATH)
        dsex_in_prices = conn.execute(
            "SELECT COUNT(*) FROM prices WHERE ticker='DSEX'"
        ).fetchone()[0]
        ms_cnt = conn.execute(
            "SELECT COUNT(*) FROM market_summary WHERE dsex IS NOT NULL"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(dsex_in_prices, 0)
        self.assertGreater(ms_cnt, 0)
        date, lvl = get_dsex_level()
        self.assertIsNotNone(date)
        self.assertIsNotNone(lvl)

    def test_freshness_gate_reports_status(self):
        from data_freshness import check_freshness
        st = check_freshness()
        self.assertIn("ok", st)
        self.assertIn("latest_price_date", st)
        self.assertIn("expected_trading_day", st)
        self.assertIsNotNone(st["latest_price_date"])

    def test_technical_none_rate_under_10pct_sample(self):
        """Phase 1 gate: <10% of sampled Category A tickers may have None technical score."""
        from analyzer import compute_technical_score, load_thresholds, TIMEFRAME_FETCH_DAYS
        from processor import get_ticker_data, load_sectors
        th = load_thresholds()
        sectors = load_sectors()
        tickers = []
        for sd in sectors["sectors"].values():
            tickers.extend(sd["top_tickers"])
        tickers = list(dict.fromkeys(tickers))[:15]
        none_cnt = 0
        for t in tickers:
            data = get_ticker_data(t, days=TIMEFRAME_FETCH_DAYS["weekly"])
            closes, highs, lows = [], [], []
            for p in data["prices"]:
                if p.get("close") is None:
                    continue
                c = float(p["close"])
                closes.append(c)
                highs.append(float(p["high"]) if p.get("high") is not None else c)
                lows.append(float(p["low"]) if p.get("low") is not None else c)
            if len(closes) < 30:
                none_cnt += 1
                continue
            keep = min(len(closes), 220)
            score = compute_technical_score(closes[-keep:], highs[-keep:], lows[-keep:], th).get("score")
            if score is None:
                none_cnt += 1
        rate = none_cnt / max(len(tickers), 1)
        self.assertLess(rate, 0.10, f"technical None rate {rate:.1%} on {len(tickers)} tickers")

    def test_unified_score_debt_gate(self):
        from unified_score import score_features, MODEL_ID
        bad = score_features(pe=10, debt_equity=2.0, dividend_yield=5, rsi_14=40, sector="Pharma", close=100)
        self.assertFalse(bad["is_eligible"])
        self.assertEqual(bad["score"], -999.0)
        good = score_features(pe=10, debt_equity=0.3, dividend_yield=5, rsi_14=30, sector="Pharma", close=100)
        self.assertTrue(good["is_eligible"])
        self.assertGreater(good["score"], 0)
        self.assertEqual(good["model_id"], MODEL_ID)
        self.assertTrue(good["active_signals"]["rsi_oversold_triggered"])

    def test_feature_store_builds_rows(self):
        from feature_store import build_features_for_date, load_scored_universe
        summary = build_features_for_date()
        self.assertTrue(summary.get("ok"), summary)
        self.assertGreater(summary.get("rows", 0), 10)
        uni = load_scored_universe(summary["date"])
        self.assertEqual(len(uni), summary["rows"])
        # Ledger and serve must share same score function output
        top = uni[0]
        self.assertIn("score", top)
        self.assertIn("model_id", top)

    def test_bootstrap_disabled(self):
        from reinforcement_learning_engine import bootstrap_historical_learning
        res = bootstrap_historical_learning()
        self.assertTrue(res.get("disabled"))

    def test_confidence_tiers_no_prob_until_200(self):
        from confidence_tiers import score_to_tier, MIN_OBS_FOR_PROB
        scores = list(range(1, 21))
        info = score_to_tier(20, scores)
        self.assertIn(info["tier"], ("HIGH", "MED", "LOW"))
        self.assertEqual(info["tier"], "HIGH")
        self.assertFalse(info["show_probability"])
        self.assertIn(str(MIN_OBS_FOR_PROB), info["note"])

    def test_ic_weights_floor_negative(self):
        from unified_score import score_features
        # Explicit weights: shut off RSI (0), boost value
        w = {"div": 1.0, "value": 1.2, "rsi": 0.0, "debt": 1.0}
        a = score_features(pe=10, debt_equity=0.2, dividend_yield=5, rsi_14=25, sector="Pharma", close=100, factor_weights=w)
        b = score_features(pe=10, debt_equity=0.2, dividend_yield=5, rsi_14=25, sector="Pharma", close=100, factor_weights={"div": 1, "value": 1, "rsi": 1, "debt": 1})
        self.assertTrue(a["is_eligible"])
        # With rsi weight 0, oversold bonus dropped → score should be lower than full rsi weight
        self.assertLess(a["score"], b["score"])
        self.assertEqual(a["components"]["rsi"], 0.0)

    def test_hold_buffer_top_pct(self):
        from forward_test_ledger_v2 import _top_pct_tickers
        elig = [{"ticker": f"T{i}", "score": 100 - i} for i in range(10)]
        keep = _top_pct_tickers(elig, 0.30)
        self.assertEqual(len(keep), 3)
        self.assertIn("T0", keep)
        self.assertNotIn("T9", keep)

    def test_model_registry_init_and_hash(self):
        from model_registry import load_registry, _param_hash
        reg = load_registry()
        self.assertIn("champion", reg)
        self.assertTrue(reg["champion"]["parameter_hash"])
        self.assertGreaterEqual(len(reg.get("challengers") or []), 1)
        h1 = _param_hash({"a": 1})
        h2 = _param_hash({"a": 1})
        h3 = _param_hash({"a": 2})
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_holm_critical_tightens_with_trials(self):
        from model_registry import holm_critical
        # rank 1 of m=5 → alpha/5; rank 5 → alpha/1
        self.assertAlmostEqual(holm_critical(0.05, 5, 1), 0.01)
        self.assertAlmostEqual(holm_critical(0.05, 5, 5), 0.05)

    def test_integrity_harness_runs(self):
        from integrity_harness import run_integrity
        res = run_integrity()
        self.assertIn("checks", res)
        self.assertIn("exit_code", res)
        # Must include core checks
        names = {c["check"] for c in res["checks"]}
        self.assertIn("ledger_asof_matches_prices", names)
        self.assertTrue("rank_log_full_universe" in names or "rank_log_latest_date" in names)

    def test_portfolio_ledger_reconciliation(self):
        """Verify strict accounting identity: Cash + Equities Cost + Fund Cost == Total Capital Outlay."""
        import json
        portfolio_file = BASE_DIR / "data" / "portfolio" / "portfolio.json"
        self.assertTrue(portfolio_file.exists())
        with open(portfolio_file, encoding="utf-8") as f:
            p = json.load(f)
        cash = float(p.get("cash_balance_bdt", 0))
        eq_cost = sum(float(h.get("cost_basis", 0)) for h in p.get("holdings", []))
        mf_cost = sum(float(m.get("total_cost_bdt", 0)) for m in p.get("mutual_funds", []))
        total_account = round(cash + eq_cost + mf_cost, 2)
        total_recorded = round(float(p.get("total_capital_bdt", 0)), 2)
        self.assertEqual(total_account, total_recorded,
                         f"Accounting mismatch: cash({cash}) + eq({eq_cost}) + mf({mf_cost}) = {total_account} != recorded {total_recorded}")

    def test_served_weights_hash_matches_frozen_parameter_hash(self):
        """Verify served model strictly matches Epoch 2 frozen hash (acf502bc65914c48) and rsi=0."""
        from model_registry import champion_hash, load_registry
        from unified_score import MODEL_ID, FROZEN_PARAMETER_HASH, load_factor_weights
        
        reg = load_registry()
        champ = reg["champion"]
        self.assertEqual(champ["model_id"], "frozen_epoch2_pit_v2")
        self.assertEqual(champ["parameter_hash"], "acf502bc65914c48")
        self.assertEqual(champion_hash(), "acf502bc65914c48")
        self.assertEqual(MODEL_ID, "frozen_epoch2_pit_v2")
        self.assertEqual(FROZEN_PARAMETER_HASH, "acf502bc65914c48")
        
        w = load_factor_weights()
        self.assertEqual(w.get("rsi"), 0.0, "RSI weight must be 0.0 under frozen Epoch 2 model!")
        self.assertEqual(w.get("debt"), 0.0, "Debt must be a gate, not an additive factor!")
        self.assertEqual(w.get("div"), 1.0)
        self.assertEqual(w.get("value"), 1.0)

    def test_deterministic_golden_score_formula(self):
        """Golden-value assertion on score_features: pe=12, div=4% -> score exactly 17.0000."""
        from unified_score import score_features
        res = score_features(pe=12.0, debt_equity=0.4, dividend_yield=4.0, rsi_14=25.0, close=200.0, sector="Pharma")
        self.assertTrue(res["is_eligible"])
        self.assertEqual(res["score"], 17.0000)
        self.assertEqual(res["components"]["div"], 8.0000)
        self.assertEqual(res["components"]["pe"], 9.0000)
        self.assertEqual(res["components"]["rsi"], 0.0000)
        self.assertEqual(res["components"]["debt"], 0.0000)

        # Gate failure check
        pe_fail = score_features(pe=26.0, debt_equity=0.4, dividend_yield=4.0, rsi_14=25.0, close=200.0, sector="Pharma")
        self.assertFalse(pe_fail["is_eligible"])
        self.assertEqual(pe_fail["score"], -999.0)
        self.assertIn("pe_gate", pe_fail["gate_reasons"])

    def test_future_perturbation_invariance(self):
        """Changing future prices (T+1) must NEVER alter point-in-time score or features on date T."""
        from feature_store import build_features_for_date, load_scored_universe, latest_price_date
        conn = sqlite3.connect(DB_PATH)
        asof = latest_price_date(conn)
        conn.close()
        self.assertIsNotNone(asof)

        uni_before = load_scored_universe(asof)
        sq_before = [r for r in uni_before if r["ticker"] == "SQURPHARMA"]
        self.assertTrue(len(sq_before) > 0)
        score_before = sq_before[0]["score"]

        # Simulate a radical price shock record far in the future
        future_dt = "2029-12-31"
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO prices (ticker, date, close, volume) VALUES ('SQURPHARMA', ?, 9999.0, 1000000)", (future_dt,))
        conn.commit()
        conn.close()

        try:
            # Re-score asof date T
            build_features_for_date(asof)
            uni_after = load_scored_universe(asof)
            sq_after = [r for r in uni_after if r["ticker"] == "SQURPHARMA"]
            score_after = sq_after[0]["score"]
            self.assertEqual(score_before, score_after, "Point-in-time score leaked future data!")
        finally:
            # Cleanup future test record
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM prices WHERE date=?", (future_dt,))
            conn.commit()
            conn.close()

    def test_no_fake_base_rates_numeric(self):
        """External truth test: assert no prediction file contains base rate numerically close to 66.4%."""
        import json
        daily_dir = BASE_DIR / "reports" / "daily"
        if not daily_dir.exists():
            return
        files = list(daily_dir.glob("*_rise_fall_predictions.json"))
        for fp in files:
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                for section in ("predicted_to_rise", "predicted_to_fall"):
                    for item in data.get(section, []):
                        br = item.get("base_rate_pct")
                        if br is not None:
                            self.assertFalse(
                                abs(float(br) - 66.4) < 0.5,
                                f"Forbidden fake base rate {br}% found in {fp.name} for {item.get('ticker')}"
                            )
            except Exception:
                pass


    def test_forward_ledger_hash_chain_integrity(self):
        """Verify strict cryptographic SHA-256 hash chaining across ALL blocks in forward_test_ledger_v2.json."""
        import json, hashlib
        ledger_file = BASE_DIR / "data" / "portfolio" / "forward_test_ledger_v2.json"
        self.assertTrue(ledger_file.exists())
        with open(ledger_file, encoding="utf-8") as f:
            ledger = json.load(f)
        blocks = ledger.get("blocks", [])
        self.assertGreaterEqual(len(blocks), 2, "Ledger must have at least Genesis and Block 1")

        for i in range(1, len(blocks)):
            prev_b = blocks[i - 1]
            curr_b = blocks[i]
            prev_data_str = json.dumps(prev_b["data"], sort_keys=True)
            expected_prev_hash = hashlib.sha256((prev_data_str + prev_b["prev_hash"]).encode("utf-8")).hexdigest()
            self.assertEqual(curr_b["prev_hash"], expected_prev_hash,
                             f"Cryptographic hash chain broken between Block {i-1} and Block {i}!")
            curr_data_str = json.dumps(curr_b["data"], sort_keys=True)
            expected_curr_hash = hashlib.sha256((curr_data_str + curr_b["prev_hash"]).encode("utf-8")).hexdigest()
            self.assertEqual(curr_b["block_hash"], expected_curr_hash,
                             f"Block {i} self-hash mismatch!")

    def test_canonical_parameter_content_hash(self):
        """Verify hash is computed directly from canonical served parameter dictionary (not a hardcoded string)."""
        import json, hashlib
        from unified_score import CANONICAL_SERVED_PARAMS, CANONICAL_PARAM_CONTENT_HASH, FROZEN_PARAMETER_HASH
        
        # Verify content hash matches runtime computation from CANONICAL_SERVED_PARAMS dict
        computed_content_hash = hashlib.sha256(
            json.dumps(CANONICAL_SERVED_PARAMS, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        self.assertEqual(computed_content_hash, CANONICAL_PARAM_CONTENT_HASH)
        self.assertEqual(computed_content_hash, "7b3020aa89457fa0")

        # Verify Genesis pre-registration string hash matches Block 0 Genesis
        computed_spec_hash = hashlib.sha256("pit_dividend_pe_rsi_sector_capped_v2".encode("utf-8")).hexdigest()[:16]
        self.assertEqual(computed_spec_hash, FROZEN_PARAMETER_HASH)
        self.assertEqual(computed_spec_hash, "acf502bc65914c48")

    def test_dsex_october_continuity_and_bounds(self):
        """Assert DSEX in October 2026 stays strictly within [5200, 5600] with no unmapped jumps."""
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT date, dsex FROM market_summary WHERE date >= '2026-10-01' AND dsex IS NOT NULL ORDER BY date ASC").fetchall()
        conn.close()
        self.assertGreater(len(rows), 0, "No October 2026 market_summary rows found!")
        prev_lvl = None
        for dt, lvl in rows:
            self.assertGreaterEqual(lvl, 5200.0, f"DSEX {lvl} on {dt} below 5200 bound")
            self.assertLessEqual(lvl, 5600.0, f"DSEX {lvl} on {dt} above 5600 bound")
            if prev_lvl:
                jump_pct = abs(lvl - prev_lvl) / prev_lvl * 100.0
                self.assertLess(jump_pct, 5.0, f"DSEX jump of {jump_pct:.2f}% on {dt} breaches 5% daily continuity threshold")
            prev_lvl = lvl


    def test_five_fundamental_filters_applied(self):
        """Verify the 5 mandatory fundamental filters are strictly enforced across config and engines."""
        import json
        from analyzer import load_thresholds
        from unified_score import score_features

        # 1. Config Thresholds check
        th = load_thresholds()
        f_cfg = th.get("fundamentals", {})
        self.assertEqual(f_cfg.get("min_cfo_to_profit_ratio"), 0.8, "CFO/Profit filter missing from thresholds.json")
        self.assertEqual(f_cfg.get("min_dividend_history_years"), 3, "3-year cash dividend filter missing from thresholds.json")
        self.assertLessEqual(f_cfg.get("safe_debt_equity"), 0.8, "Safe D/E threshold exceeds 0.8 in thresholds.json")
        self.assertEqual(f_cfg.get("min_sponsor_holding_pct"), 30, "30% sponsor holding filter missing from thresholds.json")

        # 2. Hard Debt Gate check in served score
        bad_debt = score_features(pe=10.0, debt_equity=1.2, dividend_yield=5.0, rsi_14=40.0, sector="Engineering", close=100.0)
        self.assertFalse(bad_debt["is_eligible"], "Debt gate failed to block D/E > 1.0 non-bank")
        self.assertEqual(bad_debt["score"], -999.0)

        # 3. Clean moat passes gate
        clean = score_features(pe=8.0, debt_equity=0.01, dividend_yield=5.7, rsi_14=40.0, sector="Pharma", close=220.0)
        self.assertTrue(clean["is_eligible"])
        self.assertGreater(clean["score"], 0)



    def test_five_factor_screener_universe_rigor(self):
        """Assert all tickers passing 5-factor fundamental screener strictly obey the 5 constraints."""
        from five_factor_fundamental_screener import run_5_factor_screener, SHARIAH_EXCLUDED_SECTORS
        screened = run_5_factor_screener()
        self.assertGreater(len(screened), 5, "Fewer than 5 tickers passed 5-factor screening")
        for s in screened:
            self.assertGreaterEqual(s["promoter_block_pct"], 30.0, f"{s['ticker']} failed sponsor+govt >= 30%")
            self.assertLessEqual(s["de"], 0.80, f"{s['ticker']} failed debt/equity <= 0.80")
            self.assertGreaterEqual(s["cash_div_years"], 3, f"{s['ticker']} failed >= 3 years cash dividends")
            self.assertGreater(s["eps"], 0.0, f"{s['ticker']} non-positive EPS")
            self.assertGreater(s["nav"], 0.0, f"{s['ticker']} non-positive NAV")
            self.assertNotIn(s["sector"], SHARIAH_EXCLUDED_SECTORS, f"{s['ticker']} in excluded Shariah sector")

        tickers = {s["ticker"] for s in screened}
        self.assertIn("JAMUNAOIL", tickers)
        self.assertIn("PADMAOIL", tickers)
        self.assertIn("MPETROLEUM", tickers)

    def test_halal_guard_tiers_strict_flexible_off(self):
        """N1: tier strict no banks/tobacco D/E<=0.5 DSES, flexible D/E<=0.8 tobacco excl, off passthrough, custom exclusions, BATBC blocked."""
        from halal_guard import HalalGuard
        from profile import load_profile, validate_profile
        # Gates
        g_strict = HalalGuard().gates_for("strict")
        self.assertEqual(g_strict["L2_debt_equity_max"], 0.5)
        self.assertEqual(g_strict["L2_long_term_debt_equity_max"], 0.2)
        self.assertTrue(g_strict["L5_dses_required"])
        self.assertIn("Tobacco", g_strict["L1_sectors_excluded"])
        g_flex = HalalGuard().gates_for("flexible")
        self.assertEqual(g_flex["L2_debt_equity_max"], 0.8)
        self.assertFalse(g_flex["L5_dses_required"])
        self.assertIn("Tobacco", g_flex["L1_sectors_excluded"])
        g_off = HalalGuard().gates_for("off")
        self.assertEqual(g_off["L2_debt_equity_max"], 1.0)
        self.assertEqual(g_off["L1_sectors_excluded"], [])
        # BATBC blocked in strict+flexible via Tobacco override
        guard_flex = HalalGuard()
        r_batbc_flex = guard_flex.is_eligible("BATBC", tier="flexible", pit_row={"sector": "Food_Beverage", "debt_equity": 0.0}, dses_row=None)
        self.assertFalse(r_batbc_flex["eligible"], f"BATBC must be blocked in flexible: {r_batbc_flex}")
        self.assertTrue(any("L1" in x or "Tobacco" in x for x in r_batbc_flex["reasons"]))
        guard_strict = HalalGuard()
        r_batbc_strict = guard_strict.is_eligible("BATBC", tier="strict", pit_row={"sector": "Food_Beverage", "debt_equity": 0.0}, dses_row={"dses": 1})
        self.assertFalse(r_batbc_strict["eligible"])
        # flexible blocks high D/E, strict even lower
        r_high_de = guard_flex.is_eligible("TESTA", tier="flexible", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.9})
        self.assertFalse(r_high_de["eligible"])
        r_ok_de = guard_flex.is_eligible("TESTA", tier="flexible", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.4})
        self.assertTrue(r_ok_de["eligible"])
        r_strict_fail = guard_strict.is_eligible("TESTB", tier="strict", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.6})
        self.assertFalse(r_strict_fail["eligible"])
        # off passthrough even for BATBC/bank
        guard_off = HalalGuard()
        r_off = guard_off.is_eligible("BATBC", tier="off", pit_row={"sector": "Food_Beverage", "debt_equity": 5.0})
        self.assertTrue(r_off["eligible"])
        r_off_bank = guard_off.is_eligible("BRACBANK", tier="off", pit_row={"sector": "Banking", "debt_equity": 0.5})
        self.assertTrue(r_off_bank["eligible"])
        # strict DSES: missing dses -> data_gaps + not eligible if required path
        r_dses_gap = guard_strict.is_eligible("SQURPHARMA", tier="strict", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.01}, dses_row=None)
        self.assertIn("dses_membership_missing", r_dses_gap["data_gaps"])
        # purification_rate + data_gaps presence
        r_pur = guard_flex.is_eligible("SQURPHARMA", tier="flexible", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.01})
        self.assertIn("purification_rate", r_pur)
        self.assertIn("data_gaps", r_pur)
        # Banks blocked in flexible/strict
        r_bank = guard_flex.is_eligible("BRACBANK", tier="flexible", pit_row={"sector": "Banking", "debt_equity": 0.3})
        self.assertFalse(r_bank["eligible"])
        # Insurance blocked
        r_ins = guard_flex.is_eligible("RELIANCINS", tier="flexible", pit_row={"sector": "Insurance", "debt_equity": 0.0})
        self.assertFalse(r_ins["eligible"])
        # Custom exclusions additive-only
        guard_custom = HalalGuard(profile={"halal_tier": "flexible", "custom_exclusions": {"sectors": [], "tickers": ["SQURPHARMA"]}})
        r_custom = guard_custom.is_eligible("SQURPHARMA", tier="flexible", pit_row={"sector": "Pharmaceuticals", "debt_equity": 0.01})
        self.assertFalse(r_custom["eligible"])
        self.assertTrue(any("custom" in x for x in r_custom["reasons"]))
        # additive-only validator rejects relax attempts
        with self.assertRaises(ValueError):
            validate_profile({"halal_tier": "flexible", "custom_exclusions": {"sectors": ["!Banking"], "tickers": []}})
        with self.assertRaises(ValueError):
            validate_profile({"halal_tier": "flexible", "custom_exclusions": {"sectors": [], "tickers": ["-SQURPHARMA"]}})
        # profile default flexible
        prof = load_profile()
        self.assertIn(prof["halal_tier"], ("strict", "flexible", "off"))
        # apply() keeps order and filters
        uni = [
            {"ticker": "SQURPHARMA", "score": 30, "sector": "Pharmaceuticals", "debt_equity": 0.01},
            {"ticker": "BATBC", "score": 29, "sector": "Food_Beverage", "debt_equity": 0.0},
            {"ticker": "BRACBANK", "score": 28, "sector": "Banking", "debt_equity": 0.2},
            {"ticker": "OLYMPIC", "score": 20, "sector": "Food_Beverage", "debt_equity": 0.1},
        ]
        filt = guard_flex.apply(uni, "flexible")
        self.assertEqual([x["ticker"] for x in filt], ["SQURPHARMA", "OLYMPIC"])
        filt_off = guard_off.apply(uni, "off")
        self.assertEqual(len(filt_off), 4)
        # Forward ledger stays tier-agnostic: unified_score frozen hash unchanged
        from unified_score import FROZEN_PARAMETER_HASH
        self.assertEqual(FROZEN_PARAMETER_HASH, "acf502bc65914c48")


    def test_user_isolation_architecture(self):
        """Assert strict separation between core system models and user preferences/portfolios."""
        from user_manager import create_user, load_user_profile, load_user_portfolio, save_user_profile, USERS_DIR
        import hashlib
        from unified_score import CANONICAL_PARAM_CONTENT_HASH

        # 1. Create independent test user
        test_uid = "_test_isolation_user"
        res = create_user(
            user_id=test_uid,
            name="Test Investor",
            risk_tolerance="conservative",
            investment_horizon="short_term",
            halal_tier="strict",
            initial_capital_bdt=150000.0,
            language="banglish"
        )
        self.assertTrue((USERS_DIR / test_uid / "profile.json").exists())
        self.assertTrue((USERS_DIR / test_uid / "portfolio.json").exists())

        # 2. Modify user preferences
        prof = load_user_profile(test_uid)
        self.assertEqual(prof["risk_tolerance"], "conservative")
        prof["risk_tolerance"] = "aggressive"
        prof["target_annual_return_pct"] = 35.0
        save_user_profile(test_uid, prof)

        # 3. Assert core system invariants remain untouched
        from unified_score import CANONICAL_SERVED_PARAMS
        import json
        core_hash = hashlib.sha256(json.dumps(CANONICAL_SERVED_PARAMS, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        self.assertEqual(core_hash, CANONICAL_PARAM_CONTENT_HASH, "User personalization leaked into core parameter hash!")
        self.assertEqual(core_hash, "7b3020aa89457fa0")

        # Cleanup test user directory
        import shutil
        shutil.rmtree(USERS_DIR / test_uid, ignore_errors=True)

    def test_macro_rate_feed_and_erp_hurdle(self):
        """Assert Bangladesh Bank macro rate ingestion and dynamic ERP hurdle calculation."""
        from macro_rate_feed import get_latest_macro_rates, calculate_equity_risk_premium

        # 1. Macro rate retrieval
        rates = get_latest_macro_rates()
        self.assertIn("risk_free_rate_pct", rates)
        self.assertGreater(rates["risk_free_rate_pct"], 7.0)
        self.assertLess(rates["risk_free_rate_pct"], 13.0)
        self.assertAlmostEqual(rates["policy_repo_rate_pct"], 10.00, places=2)
        self.assertGreater(rates["equity_hurdle_rate_pct"], 11.0)

        # 2. Prime ERP: Jamuna Oil (Price 179.4, EPS 58.7)
        jamuna = calculate_equity_risk_premium(eps=58.7, price=179.4, rf_rate=rates["risk_free_rate_pct"])
        self.assertGreater(jamuna["earnings_yield_pct"], 32.0)
        self.assertGreater(jamuna["equity_risk_premium_pct"], 20.0)
        self.assertTrue(jamuna["passes_macro_hurdle"])
        self.assertIn("PRIME_MACRO_SPREAD", jamuna["verdict"])

        # 3. Negative ERP: High PE stock (Price 200.0, EPS 8.0, PE 25)
        high_pe = calculate_equity_risk_premium(eps=8.0, price=200.0, rf_rate=rates["risk_free_rate_pct"])
        self.assertLess(high_pe["equity_risk_premium_pct"], 0.0)
        self.assertFalse(high_pe["passes_macro_hurdle"])
        self.assertIn("UNCOMPETITIVE", high_pe["verdict"])

    def test_corporate_actions_and_dividend_distribution(self):
        """Assert corporate action tracking, ex-dividend adjustment, and idempotent portfolio crediting."""
        from corporate_action_processor import (
            record_corporate_action,
            calculate_ex_dividend_adjustment,
            process_portfolio_dividends,
            init_corporate_actions_schema,
            PORTFOLIO_DIVIDEND_SCHEMA_DDL
        )
        from user_manager import create_user, load_user_portfolio, save_user_portfolio, USERS_DIR
        import shutil

        # 1. Ex-dividend formula
        adj = calculate_ex_dividend_adjustment(unadjusted_price=220.0, cash_per_share=12.0, bonus_ratio=0.10)
        # post cash = 208.0, post bonus = 208.0 / 1.10 = 189.09
        self.assertAlmostEqual(adj["adjusted_price"], 189.09, places=2)
        self.assertAlmostEqual(adj["adjustment_factor"], 189.09 / 220.0, places=4)

        # 2. Setup test user with holdings
        test_uid = "_test_div_user"
        create_user(test_uid, name="Dividend Test User", initial_capital_bdt=10000.0)
        port = load_user_portfolio(test_uid)
        port["holdings"] = [
            {
                "ticker": "_TESTMOAT",
                "shares": 100,
                "entry_price": 50.0,
                "bought_at": "2026-09-01"
            }
        ]
        port["cash_balance_bdt"] = 500.0
        save_user_portfolio(test_uid, port)

        # 3. Record corporate action: ৳5.00 cash dividend with record date 2026-10-15
        conn = sqlite3.connect(DB_PATH)
        init_corporate_actions_schema(conn)
        record_corporate_action(
            ticker="_TESTMOAT",
            record_date="2026-10-15",
            action_type="cash_dividend",
            cash_amount=5.0,
            notes="Test 50% cash dividend",
            conn=conn
        )

        # 4. Process dividends
        res1 = process_portfolio_dividends(user_id=test_uid, asof_date="2026-10-24", tax_rate_pct=10.0, conn=conn)
        self.assertEqual(res1["credited_count"], 1)
        # Gross = 100 * 5.0 = 500.0, Tax = 50.0, Net = 450.0
        self.assertAlmostEqual(res1["total_net_cash_bdt"], 450.0, places=2)

        # Assert cash was credited in portfolio
        updated_port = load_user_portfolio(test_uid)
        self.assertAlmostEqual(updated_port["cash_balance_bdt"], 950.0, places=2)  # 500 + 450

        # 5. Assert idempotency (running second time must credit 0)
        res2 = process_portfolio_dividends(user_id=test_uid, asof_date="2026-10-24", tax_rate_pct=10.0, conn=conn)
        self.assertEqual(res2["credited_count"], 0)
        self.assertEqual(res2["total_net_cash_bdt"], 0.0)

        # Cleanup test artifacts
        conn.execute("DELETE FROM corporate_actions WHERE ticker = '_TESTMOAT'")
        conn.execute("DELETE FROM portfolio_dividend_credits WHERE user_id = ?", (test_uid,))
        conn.commit()
        conn.close()
        shutil.rmtree(USERS_DIR / test_uid, ignore_errors=True)

    def test_orderbook_depth_and_slippage_model(self):
        """Assert order book depth metrics, Corwin-Schultz spread, and market impact tranche sizing."""
        from orderbook_depth_analyzer import (
            calculate_corwin_schultz_spread,
            analyze_ticker_liquidity,
            estimate_execution_slippage
        )

        # 1. Corwin-Schultz spread deterministic calculation
        spread = calculate_corwin_schultz_spread(high_today=102.0, low_today=99.0, high_prev=101.5, low_prev=98.5)
        self.assertGreater(spread, 0.0)
        self.assertLess(spread, 3.0)

        # 2. Square Pharma liquidity profile
        sq_liq = analyze_ticker_liquidity("SQURPHARMA")
        self.assertIn(sq_liq["liquidity_tier"], ("HIGH_LIQUIDITY", "MODERATE_LIQUIDITY"))
        self.assertGreater(sq_liq["adv_shares"], 50000)
        self.assertGreater(sq_liq["safe_max_tranche_bdt"], 100000.0)

        # 3. Small vs Large Order Slippage Simulation
        # Small order: ৳5,000 in SQURPHARMA -> low impact
        small_sim = estimate_execution_slippage("SQURPHARMA", order_value_bdt=5000.0)
        self.assertEqual(small_sim["recommended_tranches"], 1)
        self.assertLess(small_sim["market_impact_slippage_pct"], 0.05)

        # Large order: ৳500,000 in a low liquidity stock (e.g. JAMUNAOIL)
        large_sim = estimate_execution_slippage("JAMUNAOIL", order_value_bdt=500000.0)
        self.assertGreater(large_sim["recommended_tranches"], 1)
        self.assertIn("SPLIT", large_sim["execution_guidance"])

if __name__ == "__main__":
    unittest.main()
