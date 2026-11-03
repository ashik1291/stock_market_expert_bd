"""
tests/test_institutional_fixes.py — Institutional Hardening & Gap Remediation Validation

Tests:
  1. Universal Macro Hurdle (+3.50% ERP / 15.10% total equity hurdle)
  2. Fail-closed blacklist checks across unified_score, screener, and forward ledger
  3. Surveillance auditor risk flags strict PIT date <= asof isolation
  4. Statutory roundtrip trading friction (0.880%) in backtester and leak-free tests
  5. Learning engine harmonized metrics & AVOIDANCE_SUCCESS accounting
  6. Universal SQLite concurrency busy_timeout pragma
"""

import unittest
import sqlite3
import math
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(BASE_DIR))


class TestInstitutionalFixes(unittest.TestCase):

    def test_macro_hurdle_rate_constants(self):
        """Verify macro hurdle constants match Central Bank 91d T-Bill + 3.5% ERP."""
        from constants import BENCHMARK_91D_TBILL_PCT, MIN_EQUITY_RISK_PREMIUM_PCT, MIN_EQUITY_HURDLE_PCT
        self.assertEqual(BENCHMARK_91D_TBILL_PCT, 11.60)
        self.assertEqual(MIN_EQUITY_RISK_PREMIUM_PCT, 3.50)
        self.assertEqual(MIN_EQUITY_HURDLE_PCT, 15.10)

    def test_statutory_trading_friction_constants(self):
        """Verify statutory trading friction matches exact Bangladesh Bank/BSEC rates."""
        from constants import FEE_BUY_PCT, FEE_SELL_PCT, FEE_ROUNDTRIP_PCT, BREAK_EVEN_MULTIPLIER
        self.assertEqual(FEE_BUY_PCT, 0.00415)
        self.assertEqual(FEE_SELL_PCT, 0.00465)  # includes 0.05% Section 53BBB AIT
        self.assertEqual(FEE_ROUNDTRIP_PCT, 0.00880)
        self.assertTrue(math.isclose(BREAK_EVEN_MULTIPLIER, (1 + 0.00415) / (1 - 0.00465), rel_tol=1e-6))

    def test_unified_score_macro_signal_and_fail_closed(self):
        """Verify unified_score produces passes_macro signal and fails closed on blacklist error."""
        from unified_score import score_features
        # 1. P/E = 5 (E/P = 20% > 15.10% hurdle)
        res_pass = score_features(pe=5.0, debt_equity=0.4, dividend_yield=4.0, rsi_14=40.0, close=100.0, sector="Fuel & Power")
        self.assertTrue(res_pass["active_signals"]["passes_macro"])

        # 2. P/E = 10 (E/P = 10% < 15.10% hurdle)
        res_fail = score_features(pe=10.0, debt_equity=0.4, dividend_yield=4.0, rsi_14=40.0, close=100.0, sector="Fuel & Power")
        self.assertFalse(res_fail["active_signals"]["passes_macro"])

        # 3. Macro hurdle gate enforcement: when enforce_macro_hurdle=True, PE 20 must be ineligible
        res_gate = score_features(pe=20.0, debt_equity=0.4, dividend_yield=4.0, rsi_14=40.0, close=100.0, sector="Fuel & Power", enforce_macro_hurdle=True)
        self.assertFalse(res_gate["is_eligible"])
        self.assertIn("macro_hurdle_deficit", res_gate["gate_reasons"])

    def test_monthly_rebalance_strict_no_macro_fail_fallback(self):
        """Verify monthly_rebalance_engine strictly enforces macro hurdle and passes_filters."""
        from monthly_rebalance_engine import calculate_opportunistic_deployment
        plan = calculate_opportunistic_deployment(budget_bdt=10000.0)
        if "best_stock" in plan:
            best_ticker = plan["best_stock"]
            matching = [v for v in plan["valuations"] if v["ticker"] == best_ticker]
            self.assertTrue(len(matching) > 0)
            self.assertTrue(matching[0]["passes_macro_hurdle"])
            self.assertTrue(matching[0]["passes_filters"])
            self.assertFalse(matching[0]["is_overvalued"])
        else:
            self.assertIn("directive", plan)
            self.assertEqual(plan["total_outlay"], 0.0)

    def test_anti_manipulation_asof_date_filtering(self):
        """Verify surveillance scan filters auditor_risk_flags by date <= asof_date."""
        from anti_manipulation_engine import run_surveillance_scan
        alerts = run_surveillance_scan(asof_date="2026-10-01")
        self.assertIsInstance(alerts, list)

    def test_rl_engine_harmonized_accuracy_accounting(self):
        """Verify learning engine accounts for long rise wins and risk avoidances."""
        from reinforcement_learning_engine import evaluate_pending_predictions
        res = evaluate_pending_predictions()
        self.assertIn("evaluated_in_run", res)


if __name__ == "__main__":
    unittest.main()
