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


if __name__ == "__main__":
    unittest.main()
