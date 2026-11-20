"""Tier 1 data-quality tests: official DSE disclosures drive PIT dates and values."""

import os
import sqlite3
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

Q1 = ("(Q1 Un-audited): Consolidated EPS was Tk. 8.77 for July-September 2026 as against Tk. 8.35 for "
      "July-September 2025. Consolidated NOCFPS was Tk. 5.49 for July-September 2026 as against Tk. 7.55 for "
      "July-September 2025. Consolidated NAV per share was Tk. 187.35 as on September 30, 2026 and Tk. 178.99 "
      "as on June 30, 2026. (cont.)")
Q3 = ("(Q3 Un-audited): EPS was Tk. (1.12) for January-March 2025 as against Tk. 0.40 for January-March 2024; "
      "EPS was Tk. (3.29) for July 2024-March 2025 as against Tk. 1.15 for July 2023-March 2024. NOCFPS was "
      "Tk. (11.90) for July 2024-March 2025 as against Tk. 17.32 for July 2023-March 2024. NAV per share was "
      "Tk. 67.10 as on March 31, 2025 and Tk. 70.05 as on June 30, 2024.")
ANNUAL = ("The Board of Directors has recommended 15% cash and 15% stock dividend for the year ended 31-Dec-2025. "
          "Record Date: 17-May-2026. The Company has also reported Consolidated EPS of Tk. 9.12, Consolidated NAV "
          "per share of Tk. 51.56 and Consolidated NOCFPS of Tk. 72.72 for the year ended 31-Dec-2025 as against "
          "Consolidated Tk. 6.18, Consolidated Tk. 44.84 and Tk. 60.91 respectively for the year ended 31-Dec-2024.")


class TestDisclosureParser(unittest.TestCase):
    def test_interim_takes_discrete_quarter_and_matching_nav(self):
        from dse_disclosures import parse_interim
        p = parse_interim(Q1, 1)
        self.assertEqual((p["period_end"], p["eps"], p["nav"], p["nocfps"]), ("2026-09-30", 8.77, 187.35, 5.49))

    def test_q3_negative_values_and_year_to_date_cash_flow(self):
        from dse_disclosures import parse_interim
        p = parse_interim(Q3, 3)
        self.assertEqual((p["period_end"], p["eps"], p["nav"], p["nocfps"]), ("2025-03-31", -1.12, 67.10, -11.90))

    def test_annual_uses_current_year_not_comparatives(self):
        from dse_disclosures import parse_annual
        p = parse_annual(ANNUAL)
        self.assertEqual((p["period_end"], p["eps"], p["nav"], p["nocfps"]), ("2025-12-31", 9.12, 51.56, 72.72))

    def test_period_is_never_taken_from_a_comparative_date(self):
        from dse_disclosures import parse_interim
        p = parse_interim("(Q2 Un-audited): EPS was Tk. (3.17) April-June 2025 as against Tk. (2.76) April-June 2024; "
                          "NAV per share was Tk. (149.50) as on December 31, 2024.", 2)
        self.assertEqual((p["period_end"], p["eps"]), ("2025-06-30", -3.17))
        p = parse_interim("(Q3 Un-audited): EPS was Tk. (9.90), NOCFPS was Tk. (0.07) and NAV per share was Tk. (145.60) "
                          "as on September 30, 2024 as against Tk. (9.66), Tk. 0.23 and Tk. (134.22) as on September 30, 2023.", 3)
        self.assertEqual((p["period_end"], p["eps"], p["nav"]), ("2024-09-30", None, -145.60))

    def test_continuation_without_figures_is_not_a_filing(self):
        from dse_disclosures import parse_filing
        f = {"text": "(Cont. News of IDLC): The primary reason behind this variance is EPS growth.",
             "summary": "IDLC: Q1 Financials (Additional Information)"}
        self.assertIsNone(parse_filing(f))


class TestOfficialFilingsDrivePit(unittest.TestCase):
    def _seed(self, conn, code, pend, kind, q, pub, eps, nav, noc):
        import dse_disclosures as dd
        dd.ensure_schema(conn)
        conn.execute("DELETE FROM disclosure_financials")
        conn.execute("""INSERT INTO disclosure_financials (code, period_end, kind, quarter, published_date, published_time,
                        eps, nav, nocfps, basis, disclosure_ids, parsed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (code, pend, kind, q, pub, "09:50", eps, nav, noc, "consolidated", '["psi-1"]', "t"))

    def test_reconcile_dates_corrects_and_is_protected_from_processor(self):
        import dse_disclosures as dd
        import processor
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            try:
                pend = "2025-06-30"
                conn.execute("""UPDATE fundamentals_pit SET publication_source='bsec_statutory_filing', publication_is_estimated=1,
                                cash_flow_ops=18.65 WHERE ticker='SQURPHARMA' AND snapshot_date=?""", (pend,))
                self._seed(conn, "SQURPHARMA", pend, "annual", 4, "2025-10-23", 27.04, 157.88, 19.52)
                first = dd.reconcile_pit(conn, apply=True)
                second = dd.reconcile_pit(conn, apply=True)
                row = conn.execute("""SELECT publication_date, tradable_date, publication_source, publication_is_estimated,
                                      cash_flow_ops FROM fundamentals_pit WHERE ticker='SQURPHARMA' AND snapshot_date=?""",
                                   (pend,)).fetchone()
                logged = conn.execute("SELECT COUNT(*) FROM pit_corrections WHERE ticker='SQURPHARMA'").fetchone()[0]
                raw = {"multi_year_financials": [{"year": int(pend[:4]), "eps": "1.0", "nav": "2.0"}]}
                processor.upsert_fundamentals(conn, {"ticker": "SQURPHARMA"}, raw, "2026-11-20")
                after = conn.execute("""SELECT publication_date, publication_source, eps FROM fundamentals_pit
                                        WHERE ticker='SQURPHARMA' AND snapshot_date=?""", (pend,)).fetchone()
            finally:
                conn.close()
        self.assertEqual(row[0], "2025-10-23")
        self.assertGreater(row[1], row[0])
        self.assertEqual((row[2], row[3], row[4]), ("dse_disclosure", 0, 19.52))
        self.assertGreater(logged, 0)
        self.assertEqual(second["changes_logged"], 0)
        self.assertEqual(after, ("2025-10-23", "dse_disclosure", 27.04))
        self.assertGreaterEqual(first["changes_logged"], 1)

    def test_missing_filed_period_is_inserted_with_observed_date(self):
        import dse_disclosures as dd
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            try:
                conn.execute("DELETE FROM fundamentals_pit WHERE ticker='SQURPHARMA' AND snapshot_date='2026-09-30'")
                self._seed(conn, "SQURPHARMA", "2026-09-30", "interim", 1, "2026-11-11", 8.77, 187.35, 5.49)
                dd.reconcile_pit(conn, apply=True)
                row = conn.execute("""SELECT publication_date, publication_source, publication_is_estimated, fiscal_year,
                                      fiscal_quarter, eps, nav FROM fundamentals_pit
                                      WHERE ticker='SQURPHARMA' AND snapshot_date='2026-09-30'""").fetchone()
            finally:
                conn.close()
        self.assertEqual(row, ("2026-11-11", "dse_disclosure", 0, 2027, 1, 8.77, 187.35))


def _ann(pub, summary, text, i):
    return {"code": "XCO", "published_date": pub, "published_time": "09:50", "summary": "XCO: " + summary,
            "type": "Dividend", "text": text, "ids": [f"psi-{i}"]}


class TestOfficialCorporateActions(unittest.TestCase):
    def test_holiday_shift_is_taken_from_the_exchange_suspension_notice(self):
        from official_corporate_actions import official_events
        anns = [_ann("2025-05-04", "Dividend Declaration", "The Board of Directors has recommended 5% Cash Dividend for the "
                     "year ended December 31, 2024. Record Date: 12.06.2025.", 1),
                _ann("2025-06-12", "Suspension for Record date", "Trading of the shares of the company will remain "
                     "suspended on record date i.e., 15.06.2025.", 2)]
        (e,) = official_events(anns)
        self.assertEqual((e["type"], e["pct"], e["record_date"]), ("cash_dividend", 5.0, "2025-06-15"))

    def test_stock_dividend_follows_bsec_consent_or_rejection(self):
        from official_corporate_actions import official_events
        decl = _ann("2025-10-27", "Dividend Declaration", "The Board of Directors has recommended 10% Cash and 5% Stock "
                    "Dividend for the year ended June 30, 2025. Record Date: 23.11.2025.", 1)
        susp1 = _ann("2025-11-20", "Spot News", "trading of the shares will remain suspended on record date i.e., 23.11.2025.", 2)
        pending = _ann("2025-11-20", "Regarding Stock Dividend", "it has not obtained approval from BSEC yet for issuance "
                       "of 5% Stock Dividend. The record date is applicable for entitlement of Cash Dividend only.", 3)
        consent = _ann("2026-01-06", "BSEC's consent for Stock Dividend and record date", "BSEC has accorded consent for the "
                       "issuance of 5% Stock Dividend for the year ended June 30, 2025. Record Date: 13.01.2026.", 4)
        susp2 = _ann("2026-01-11", "Suspension for Record Date", "Trading will remain suspended on record date i.e., 13.01.2026.", 5)
        ev = {e["type"]: e for e in official_events([decl, susp1, pending, consent, susp2])}
        self.assertEqual(ev["cash_dividend"]["record_date"], "2025-11-23")
        self.assertEqual(ev["bonus_dividend"]["record_date"], "2026-01-13")
        rejected = _ann("2026-02-23", "BSEC rejected the application", "BSEC has decided to reject the application of the "
                        "company for issuance of 5% stock dividend.", 6)
        ev = {e["type"]: e for e in official_events([decl, susp1, pending, rejected])}
        self.assertIsNone(ev["bonus_dividend"]["record_date"])

    def test_subsidiary_dividend_is_not_the_company_dividend_and_public_only_is_flagged(self):
        from official_corporate_actions import official_events
        sub = _ann("2025-04-30", "Regarding interim cash dividend declared by a subsidiary", "The Board of Directors of J. M. "
                   "Fabrics Limited, a subsidiary company of XCO declared 30% Interim Cash Dividend.", 1)
        own = _ann("2025-10-27", "Dividend Declaration", "The Board of Directors has recommended 10% cash dividend for the year "
                   "ended June 30, 2025 only for General Shareholders. Sponsors and Directors of the company who hold 9 shares "
                   "will not be entitled to the cash dividend. Record Date: 17.11.2025.", 2)
        (e,) = official_events([sub, own])
        self.assertEqual((e["pct"], e["public_only"]), (10.0, True))

    def test_duplicates_are_removed_only_for_the_closest_official_event_and_never_when_credited(self):
        import official_corporate_actions as oca
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            try:
                conn.execute("DELETE FROM corporate_actions WHERE ticker='SQURPHARMA'")
                conn.executemany("INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, "
                                 "adjustment_factor, notes) VALUES ('SQURPHARMA', ?, 'cash_dividend', 0, ?, 1, ?)",
                                 [("2025-11-15", 12.0, "120% (estimated date)"), ("2026-11-16", 13.0, "130% real")])
                before = conn.execute("SELECT COUNT(*) FROM portfolio_dividend_credits").fetchone()[0]
                oca.reconcile(conn, apply=True)
                dates = [r[0] for r in conn.execute("""SELECT record_date FROM corporate_actions
                         WHERE ticker='SQURPHARMA' AND action_type='cash_dividend' ORDER BY record_date""")]
                after = conn.execute("SELECT COUNT(*) FROM portfolio_dividend_credits").fetchone()[0]
            finally:
                conn.close()
        self.assertNotIn("2025-11-15", dates)
        self.assertIn("2025-11-16", dates)
        self.assertIn("2026-11-16", dates)
        self.assertEqual(before, after)


class TestInstrumentMaster(unittest.TestCase):
    def _db(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript("""CREATE TABLE disclosures (id TEXT, code TEXT, published_date TEXT, summary TEXT, body TEXT);
                              CREATE TABLE prices (ticker TEXT, date TEXT, close REAL);
                              CREATE TABLE trading_calendar (date TEXT, is_trading_day INTEGER);
                              CREATE TABLE companies (ticker TEXT, sector TEXT, category TEXT);""")
        return conn

    def test_category_walks_back_through_notices_with_cancellations_and_future_changes(self):
        import instrument_master as im
        conn = self._db()
        conn.executemany("INSERT INTO disclosures VALUES (?,?,?,?,?)", [
            ("1", "XCO", "2024-11-20", "XCO: other", ""),
            ("2", "XCO", "2025-02-04", "XCO: Category Change", "The Company has been placed in 'Z' category from existing 'A' "
             "category with effect from today, i.e., 04.02.2025 as per provision 1(e)."),
            ("3", "XCO", "2025-02-11", "XCO: Category Change", "The Company will be placed in 'A' category from existing 'Z' "
             "category with effect from February 12, 2025."),
            ("4", "XCO", "2026-02-03", "XCO: Category Change", "The Company will be placed in 'Z' category from existing 'A' "
             "category with effect from February 05, 2026."),
            ("5", "XCO", "2026-02-05", "XCO: Category status remains unchanged", "Refer to the earlier news..."),
            ("6", "XCO", "2026-11-19", "XCO: Category Change", "The Company will be placed in 'Z' category from existing 'A' "
             "category with effect from November 22, 2026."),
        ])
        stats = im.build_category_history(conn, {"XCO": {"category": "A", "type": "equity"}}, "2026-11-19")
        self.assertEqual(stats["chain_breaks_count"], 0)
        got = [im.category_asof(conn, "XCO", d) for d in ("2025-01-10", "2025-02-05", "2025-06-01", "2026-03-01", "2026-11-23")]
        self.assertEqual(got, ["A", "Z", "A", "A", "Z"])

    def test_universe_keeps_names_that_later_stopped_trading(self):
        import instrument_master as im
        conn = self._db()
        conn.executescript(im.SCHEMA)
        conn.executemany("INSERT INTO trading_calendar VALUES (?, 1)",
                         [("2024-10-27",), ("2024-10-28",)] + [(f"2026-11-{d:02d}",) for d in range(1, 20)])
        conn.executemany("INSERT INTO prices VALUES (?,?,1.0)", [("OLDCO", "2024-10-28"), ("NEWCO", "2026-11-19")])
        im.build_instruments(conn, {"NEWCO": {"category": "A", "board": "PUBLIC", "sector": "x", "type": "equity"}}, "2026-11-19")
        self.assertEqual(im.universe_asof(conn, "2024-10-28", lookback_sessions=1), ["OLDCO"])
        self.assertEqual(im.universe_asof(conn, "2026-11-19", lookback_sessions=1), ["NEWCO"])
        status = conn.execute("SELECT status FROM instruments WHERE ticker='OLDCO'").fetchone()[0]
        self.assertEqual(status, "inactive")


class TestBankAssetQuality(unittest.TestCase):
    def test_npl_is_sourced_point_in_time_and_never_guessed(self):
        import bank_asset_quality as baq
        conn = sqlite3.connect(":memory:")
        conn.executescript("CREATE TABLE companies (ticker TEXT, sector TEXT);" + baq.SCHEMA)
        conn.executemany("INSERT INTO companies VALUES (?,?)", [("XBANK", "Banking"), ("XPHARMA", "Pharmaceuticals")])
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO bank_asset_quality VALUES ('XBANK','2025-12-31','2025-06-01',4.0,NULL,'https://x.example/r.pdf','t')")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO bank_asset_quality VALUES ('XBANK','2025-12-31','2026-04-20',4.0,NULL,'','t')")
        conn.execute("INSERT INTO bank_asset_quality VALUES ('XBANK','2025-12-31','2026-04-20',4.0,13.5,'https://x.example/r.pdf','t')")
        self.assertIsNone(baq.asset_quality_asof(conn, "XBANK", "2026-04-19"))
        self.assertEqual(baq.asset_quality_asof(conn, "XBANK", "2026-04-20")["npl_pct"], 4.0)
        self.assertTrue(baq.is_bank(conn, "XBANK"))
        self.assertFalse(baq.is_bank(conn, "XPHARMA"))

    def test_registry_no_longer_carries_unsourced_npl(self):
        import json
        reg = json.load(open(os.path.join(ROOT, "config", "company_registry_12factor.json"), encoding="utf-8"))
        self.assertFalse(any("bank_npl_pct" in v for v in reg.values()))


class TestIndexMembership(unittest.TestCase):
    def test_membership_is_point_in_time_and_unknown_without_a_list(self):
        import index_membership as im
        conn = sqlite3.connect(":memory:")
        im.ensure_schema(conn)
        self.assertIsNone(im.member_asof(conn, "DSES", "XCO", "2026-01-01"))
        self.assertTrue(im.store_snapshot(conn, "DSES", "2025-07-01", {"XCO", "YCO"}, "https://dse.example/dses.pdf"))
        self.assertFalse(im.store_snapshot(conn, "DSES", "2025-08-01", {"XCO", "YCO"}, "https://dse.example/dses.pdf"))
        self.assertTrue(im.store_snapshot(conn, "DSES", "2026-01-01", {"YCO"}, "https://dse.example/dses2.pdf"))
        self.assertIsNone(im.member_asof(conn, "DSES", "XCO", "2025-06-30"))
        self.assertTrue(im.member_asof(conn, "DSES", "XCO", "2025-12-31"))
        self.assertFalse(im.member_asof(conn, "DSES", "XCO", "2026-01-01"))


class TestCorporateActionsStayCorrected(unittest.TestCase):
    def test_deleted_rows_are_not_resurrected_and_no_placeholder_dates_are_invented(self):
        import corporate_action_processor as cap
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            try:
                tomb = conn.execute("""SELECT ticker, record_date, action_type FROM corporate_action_corrections
                                       WHERE change LIKE 'deleted%' LIMIT 1""").fetchone()
                conn.execute("INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, "
                             "adjustment_factor, notes) VALUES (?,?,?,0,1,1,'legacy writer')", tomb)
                resurrected = conn.execute("SELECT COUNT(*) FROM corporate_actions WHERE ticker=? AND record_date=? "
                                           "AND action_type=?", tomb).fetchone()[0]
                before = set(conn.execute("SELECT * FROM corporate_actions").fetchall())
                cap.sync_corporate_actions_from_fundamentals(conn=conn)
                after = set(conn.execute("SELECT * FROM corporate_actions").fetchall())
            finally:
                conn.close()
        self.assertEqual(resurrected, 0)
        self.assertEqual(before, after)


class TestHurdleFollowsBangladeshBank(unittest.TestCase):
    def test_champion_hurdle_is_point_in_time(self):
        from unified_score import equity_hurdle_pct, score_features
        self.assertAlmostEqual(equity_hurdle_pct("2026-06-01"), 15.1, places=2)
        self.assertAlmostEqual(equity_hurdle_pct("2026-11-19"), 12.0, places=2)
        kw = dict(pe=7.5, debt_equity=0.1, dividend_yield=5.0, rsi_14=40.0, sector="Pharmaceuticals", close=100.0)
        self.assertNotIn("macro_hurdle_deficit", score_features(asof_date="2026-11-19", **kw)["gate_reasons"])
        self.assertIn("macro_hurdle_deficit", score_features(asof_date="2026-06-01", **kw)["gate_reasons"])


class TestMacroReaders(unittest.TestCase):
    def test_each_indicator_uses_its_own_latest_observation_and_never_a_later_one(self):
        import macro_rate_feed as m
        conn = sqlite3.connect(":memory:")
        m.init_macro_schema(conn)
        conn.executemany("INSERT INTO macro_indicators (date, indicator, value, unit, source, created_at) VALUES (?,?,?,?,?,?)",
                         [("2025-01-01", "t_bill_91d", 11.6, "percent", "s", "t"),
                          ("2026-10-24", "fx_reserves_usd_bn", 19.8, "bn", "s", "t"),
                          ("2026-11-16", "bcr_91d", 8.5, "percent", "s", "t")])
        r = m.get_macro_rates_for_date("2026-11-20", conn=conn)
        self.assertEqual((r["t_bill_91d_pct"], r["bcr_91d_pct"], r["risk_free_rate_pct"], r["is_stale"]), (11.6, 8.5, 8.5, False))
        self.assertEqual((r["risk_free_source"], r["equity_hurdle_rate_pct"]), ("bcr_91d observed 2026-11-16", 12.0))
        early = m.get_macro_rates_for_date("2024-06-01", conn=conn)
        self.assertEqual(early["risk_free_source"], "policy default (no observation)")
        self.assertIsNone(early["bcr_91d_pct"])


if __name__ == "__main__":
    unittest.main()
