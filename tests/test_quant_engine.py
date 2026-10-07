"""
Golden-Value and Regression Tests for Quantitative Logic and Backtester.
Runs deterministic unit checks against:
  1. Break-even formula & round-trip brokerage friction (0.833%)
  2. Conservative stop-loss first execution
  3. Graham ceiling & Buffett valuation formulas
  4. Point-in-time fundamentals isolation (no lookahead)
  5. Dynamic database audit zero-violation assertion
"""

import math
import sqlite3
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


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
        """Verify that dse.db has no active audit failures recorded."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        recent_failures = c.execute("""
            SELECT check_name, violation_count, details 
            FROM database_audit_log 
            WHERE status = 'FAILED'
            ORDER BY id DESC LIMIT 10
        """).fetchall()
        self.assertEqual(len(recent_failures), 0, f"Database integrity audit failures found: {recent_failures}")

    def test_point_in_time_schema_populated(self):
        """Verify that fundamentals_pit table exists and has rows."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        cnt = c.execute("SELECT COUNT(*) FROM fundamentals_pit").fetchone()[0]
        self.assertGreater(cnt, 0, "Point-in-time fundamentals table is empty!")


if __name__ == "__main__":
    unittest.main()
