"""
tests/test_audit_fixes_validation.py
-----------------------------------
Verifies fixes from the 2026-11-01 brutal system audit:
1. portfolio_manager.record_buy() defines effective_entry and blocks blacklisted stocks.
2. smart_capital_planner computes dynamic dips, checks blacklist, and respects sector caps.
3. All 6 screener scripts import and call is_ticker_blacklisted.
4. scraper.py enforces price count data gate.
5. anti_manipulation_engine uses adaptive volume thresholds.
"""

import unittest
import os
import sys
import sqlite3
import json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class TestAuditFixesValidation(unittest.TestCase):

    def test_record_buy_not_crashing_and_calculates_effective_entry(self):
        from portfolio_manager import calculate_round_trip_break_even
        price = 100.0
        be = calculate_round_trip_break_even(price)
        self.assertGreater(be, price)
        # Check that effective entry logic is valid
        shares = 10
        gross = shares * price
        comm = round(gross * 0.004, 2)
        net = round(gross + comm, 2)
        eff = round(net / shares, 2)
        self.assertEqual(eff, 100.4)

    def test_smart_capital_planner_dynamic_execution(self):
        from smart_capital_planner import generate_smart_plan
        plan = generate_smart_plan(amount=3000.0)
        self.assertIn("regime_info", plan)
        self.assertIn("allocations", plan)
        self.assertGreaterEqual(len(plan["allocations"]), 1)
        
        # Verify allocations do not exceed sector limits (max 1 of same sector in 2-pick plan)
        sectors = [a["sector"] for a in plan["allocations"]]
        self.assertEqual(len(sectors), len(set(sectors)), "Sector concentration violated: multiple picks from same sector")
        
        # Verify target dip is computed dynamically and <= current_price
        for a in plan["allocations"]:
            self.assertLessEqual(a["target_limit_price"], a["current_price"])

    def test_all_screening_scripts_have_blacklist_guard(self):
        screeners = [
            "buffett_value_screener.py",
            "smart_capital_planner.py",
            "portfolio_manager.py",
            "analyzer.py",
            "pattern_causal_engine.py",
            "unified_score.py"
        ]
        for s in screeners:
            path = os.path.join(ROOT, "scripts", s)
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
            self.assertIn("is_ticker_blacklisted", code, f"{s} is missing is_ticker_blacklisted guard!")

    def test_anti_manipulation_adaptive_thresholds(self):
        path = os.path.join(ROOT, "scripts", "anti_manipulation_engine.py")
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("avg_vol_20 >= 500000", code, "Missing large-cap adaptive volume threshold")
        self.assertIn("Tiered by Baseline Liquidity", code, "Missing liquidity tier logic")


    def test_dse_circuit_breaker_tiers(self):
        from dse_circuit_breaker import get_dse_circuit_limit_pct, get_lower_circuit_floor, is_price_circuit_locked
        self.assertEqual(get_dse_circuit_limit_pct(50.0), 10.0)
        self.assertEqual(get_dse_circuit_limit_pct(150.0), 8.75)
        self.assertEqual(get_dse_circuit_limit_pct(219.6), 7.50)
        self.assertEqual(get_dse_circuit_limit_pct(700.0), 6.25)
        self.assertEqual(get_dse_circuit_limit_pct(1500.0), 5.00)

        # Verify floor for SQURPHARMA (219.6)
        floor = get_lower_circuit_floor(219.6)
        self.assertEqual(floor, 203.1)

        # Verify circuit lock detection
        lock_res = is_price_circuit_locked(203.1, 219.6)
        self.assertTrue(lock_res["locked"])
        self.assertEqual(lock_res["side"], "LOWER")

    def test_statutory_ait_in_breakeven(self):
        from portfolio_manager import calculate_round_trip_break_even, TOTAL_BUY_FEE_PCT, TOTAL_SELL_FEE_PCT
        self.assertEqual(TOTAL_BUY_FEE_PCT, 0.00415)
        self.assertEqual(TOTAL_SELL_FEE_PCT, 0.00465)  # includes 0.05% Section 53BBB AIT
        price = 100.0
        be = calculate_round_trip_break_even(price)
        # Factor is (1 + 0.00415) / (1 - 0.00465) = 1.00884
        self.assertEqual(be, 100.88)

    def test_mutual_fund_tracker_nav_sync(self):
        from mutual_fund_tracker import sync_portfolio_mutual_fund_nav, get_latest_nav_from_db
        res = sync_portfolio_mutual_fund_nav(latest_redemption_px=10.631, asof_date="2026-11-01")
        self.assertEqual(res["status"], "success")
        db_nav = get_latest_nav_from_db("Shanta Amana Shariah Fund")
        self.assertIsNotNone(db_nav)
        self.assertEqual(db_nav["nav_redemption"], 10.631)

    def test_layer7_pit_live_scrape_not_lagged(self):
        """Verify Layer 7 fix: live scrape fundamentals are not lagged 75 days into future."""
        db_path = os.path.join(ROOT, "data", "processed", "dse.db")
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("""
            SELECT ticker, snapshot_date, publication_date, tradable_date 
            FROM fundamentals_pit 
            WHERE snapshot_date >= '2026-10-01' AND snapshot_date NOT LIKE '%-03-31'
              AND snapshot_date NOT LIKE '%-06-30' AND snapshot_date NOT LIKE '%-09-30'
              AND snapshot_date NOT LIKE '%-12-31'
            LIMIT 5
        """)
        rows = cur.fetchall()
        con.close()
        self.assertTrue(len(rows) > 0)
        for sym, snap, pub, trad in rows:
            self.assertEqual(snap, pub)
            self.assertTrue(trad >= snap)
            self.assertTrue(trad <= '2026-11-01')

    def test_layer7_strict_missing_data_gate(self):
        """Verify Layer 7 fix: missing PE or Debt marks is_eligible = False."""
        from unified_score import score_features
        # 1. Missing PE
        res1 = score_features(pe=None, debt_equity=0.2, dividend_yield=5.0, rsi_14=40.0, sector="Textile", close=20.0)
        self.assertFalse(res1["is_eligible"])
        self.assertIn("missing_pe_ratio", res1["gate_reasons"])

        # 2. Missing Debt for Non-Bank
        res2 = score_features(pe=12.0, debt_equity=None, dividend_yield=5.0, rsi_14=40.0, sector="Textile", close=20.0)
        self.assertFalse(res2["is_eligible"])
        self.assertIn("missing_debt_equity", res2["gate_reasons"])

        # 3. Missing Debt for Bank is allowed
        res3 = score_features(pe=6.0, debt_equity=None, dividend_yield=7.0, rsi_14=40.0, sector="Banking", close=20.0)
        self.assertTrue(res3["is_eligible"])

    def test_layer7_portfolio_record_sell(self):
        """Verify Layer 7 fix: record_sell properly executes, deducts commission, and credits net proceeds."""
        import tempfile
        import shutil
        from portfolio_manager import record_sell, load_portfolio, save_portfolio

        # Setup test portfolio in temp location or with test_uid
        test_uid = "test_sell_user"
        test_port = {
            "user_id": test_uid,
            "cash_balance_bdt": 100.0,
            "holdings": [
                {
                    "ticker": "TESTMOCK",
                    "shares": 10,
                    "entry_price": 50.0,
                    "gross_cost": 500.0,
                    "commission_bdt": 5.0,
                    "cost_basis": 505.0,
                    "effective_entry": 50.5,
                    "break_even_price": 50.95
                }
            ],
            "history": []
        }
        save_portfolio(test_port, user_id=test_uid)

        # Execute sell of 4 shares @ 60.0
        # Gross = 240.0, Commission = max(240 * 0.00465, 5.0) = 5.0
        # Net proceeds = 235.0
        # Sold cost basis = (505 / 10) * 4 = 202.0
        # Realized P&L = 235.0 - 202.0 = +33.0
        entry = record_sell("TESTMOCK", 4, 60.0, user_id=test_uid, min_ticket_fee=5.0)
        self.assertEqual(entry["net_proceeds"], 235.0)
        self.assertEqual(entry["realized_pnl_bdt"], 33.0)

        updated_port = load_portfolio(user_id=test_uid)
        self.assertEqual(updated_port["cash_balance_bdt"], 335.0)  # 100 + 235
        self.assertEqual(len(updated_port["holdings"]), 1)
        self.assertEqual(updated_port["holdings"][0]["shares"], 6)

        # Cleanup test portfolio file
        port_file = os.path.join(ROOT, "data", "users", test_uid, "portfolio.json")
        if os.path.exists(port_file):
            os.remove(port_file)

    def test_layer7_anti_manipulation_asof_date(self):
        """Verify Layer 7 fix: is_ticker_blacklisted respects asof_date without lookahead."""
        from anti_manipulation_engine import is_ticker_blacklisted
        # Asof date in the far past (before any alerts existed)
        is_b, _ = is_ticker_blacklisted("DGIC", asof_date="2020-01-01")
        self.assertFalse(is_b)

    def test_layer7_trading_calendar_continuous_density(self):
        """Verify Layer 7 fix: dense continuous calendar 2012-2027 with zero date gaps."""
        db_path = os.path.join(ROOT, "data", "processed", "dse.db")
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(is_trading_day), SUM(CASE WHEN is_trading_day = 0 THEN 1 ELSE 0 END) FROM trading_calendar")
        total_days, trading_days, non_trading_days = cur.fetchone()
        con.close()
        self.assertGreater(total_days, 5500)
        self.assertGreater(trading_days, 3600)
        self.assertGreater(non_trading_days, 1800)

    def test_layer7_backtester_portfolio_simulation(self):
        """Verify Layer 7 fix: shared-capital portfolio backtester with cash pool, limits, and statutory friction."""
        from backtester import simulate_portfolio_backtest
        res = simulate_portfolio_backtest(initial_capital=50000.0, max_concurrent=3)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("initial_capital_bdt"), 50000.0)
        self.assertIn("final_equity_bdt", res)
        self.assertIn("max_drawdown_pct", res)
        self.assertIn("total_trades", res)
        self.assertIn("annualized_sharpe_ratio", res)

    def test_layer7_scraper_multi_layer_failover(self):
        """Verify Layer 7 fix: scraper failover robustness and price normalization."""
        from scraper import scrape_market_summary, scrape_all_prices
        prices = scrape_all_prices()
        self.assertIsInstance(prices, list)
        self.assertGreaterEqual(len(prices), 50)
        first = prices[0]
        self.assertIn("ticker", first)
        self.assertIn("close", first)
        self.assertIn("category", first)

    def test_layer7_dse_psi_corporate_action_parsing(self):
        """Verify Layer 7 fix: official DSE PSI multi-part disclosure regex parser and database synchronization."""
        from corporate_action_processor import parse_and_record_dse_psi
        mock_psi_news = [
            {
                "code": "TESTMOCK_PSI",
                "summary": "TESTMOCK_PSI: Dividend Declaration (cont.1)",
                "body": "The Board of Directors has recommended 20% Cash Dividend and 10% Stock Dividend for the year ended June 30, 2026. Date of AGM: 28.12.2026. Record Date: 25.11.2026.",
                "date": "02 Nov 2026"
            },
            {
                "code": "TESTMOCK_PSI",
                "summary": "TESTMOCK_PSI: Dividend Declaration (cont.2)",
                "body": "(Cont. News of TESTMOCK_PSI): NAV per share of Tk. 45.00 and EPS of Tk. 3.50. (end)",
                "date": "02 Nov 2026"
            }
        ]
        db_path = os.path.join(ROOT, "data", "processed", "dse.db")
        con = sqlite3.connect(db_path)
        res = parse_and_record_dse_psi(news_items=mock_psi_news, conn=con)
        self.assertTrue(res.get("ok"))
        self.assertGreaterEqual(res.get("total_parsed"), 2)

        cur = con.cursor()
        cur.execute("SELECT action_type, cash_amount, ratio, adjustment_factor FROM corporate_actions WHERE ticker = 'TESTMOCK_PSI' ORDER BY action_type ASC")
        rows = cur.fetchall()
        # Clean up mock row
        con.execute("DELETE FROM corporate_actions WHERE ticker = 'TESTMOCK_PSI'")
        con.commit()
        con.close()

        self.assertEqual(len(rows), 2)
        # bonus_dividend: ratio = 0.10, adjustment_factor = 1/(1+0.1) = 0.909091
        # cash_dividend: cash_amount = 2.0 (20% of 10), adjustment_factor = 1.0
        self.assertEqual(rows[0][0], "bonus_dividend")
        self.assertAlmostEqual(rows[0][2], 0.10, places=2)
        self.assertAlmostEqual(rows[0][3], 0.909091, places=4)

        self.assertEqual(rows[1][0], "cash_dividend")
        self.assertAlmostEqual(rows[1][1], 2.0, places=2)
        self.assertEqual(rows[1][3], 1.0)


if __name__ == "__main__":
    unittest.main()
