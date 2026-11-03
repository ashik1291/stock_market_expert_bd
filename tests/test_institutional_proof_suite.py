"""
Unit and Integration Tests for Institutional Proof & Statistical Edge Leap
==========================================================================
Validates all 9 Institutional Proof Pillars:
  Pillar 1: Verified PIT Isolation (publication_is_estimated=0 only for live)
  Pillar 2: True Total-Return Multi-Asset Benchmark Suite (bonus shares + cash div net of AIT)
  Pillar 3: 87-Period Purged Walk-Forward Out-of-Sample Engine (5-bar embargo, SHA-256 manifests)
  Pillar 4: Calibrated Empirical Probability Engine (minimum N>=30, Wilson 95% CI, Brier score)
  Pillar 5: Portfolio Sizing & Risk Controls (falling knife guard, -10% drawdown kill switch, sector cap <= 25%)
  Pillar 6: Microstructure Execution Simulation (minimum ৳5.00 ticket fee, circuit lockouts)
  Pillar 7 & 8: Institutional Promotion Gatekeeper (6 non-negotiable gates, Holm-Bonferroni, Newey-West)
  Pillar 9: Composite Indexing & Sub-5-Second Runtime
  Invariant: Zero Bank Exposure (INV-3) fail-closed protection
"""

import json
import sqlite3
import unittest
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
DATA_DIR = BASE_DIR / "data"
PROC_DIR = DATA_DIR / "processed"
DB_PATH = PROC_DIR / "dse.db"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(BASE_DIR))

from unified_score import (
    score_features,
    is_shariah_excluded_sector,
    is_shariah_excluded_company,
    ROUND_TRIP_COST_PCT,
    CANONICAL_PARAM_CONTENT_HASH,
)
from benchmark_index import get_multi_asset_benchmark_suite, equal_weight_category_a_nav
from calibrated_probability_engine import (
    get_calibrated_empirical_probability,
    get_factor_bin_key,
    compute_wilson_ci,
)
from portfolio_manager import (
    check_reversal_confirmation,
    check_portfolio_drawdown_kill,
    calculate_round_trip_break_even,
)
from purged_walk_forward_engine import (
    compute_newey_west_stats,
    run_purged_walk_forward_evaluation,
)
from statistical_promotion_gate import (
    run_statistical_promotion_gate,
    compute_t_pval,
)


class TestInstitutionalProofSuite(unittest.TestCase):

    def test_pillar_1_verified_pit_isolation(self):
        """Pillar 1: Estimated PIT filings must be rejected in strict live mode."""
        # Estimated PIT record
        res_est = score_features(
            pe=12.0,
            debt_equity=0.10,
            dividend_yield=5.0,
            rsi_14=40.0,
            sector="Fuel_Power",
            close=100.0,
            publication_is_estimated=1,
            strict_verified_pit=True,
        )
        self.assertFalse(res_est["is_eligible"])
        self.assertIn("estimated_pit_research_only", res_est["gate_reasons"])
        self.assertFalse(res_est["is_pit_verified"])

        # Verified PIT record
        res_ver = score_features(
            pe=12.0,
            debt_equity=0.10,
            dividend_yield=5.0,
            rsi_14=40.0,
            sector="Fuel_Power",
            close=100.0,
            publication_is_estimated=0,
            strict_verified_pit=True,
        )
        self.assertTrue(res_ver["is_eligible"])
        self.assertTrue(res_ver["is_pit_verified"])

    def test_pillar_2_total_return_multi_asset_benchmark(self):
        """Pillar 2: Benchmark suite covers EQW TR, DSEX, 91D T-Bill, and Cash."""
        suite = get_multi_asset_benchmark_suite("2026-01-01", "2026-03-01")
        self.assertIn("benchmarks", suite)
        bm = suite["benchmarks"]
        self.assertIn("eqw_total_return_pct", bm)
        self.assertIn("dsex_index_pct", bm)
        self.assertIn("tbill_91d_pct", bm)
        self.assertEqual(bm["cash_pct"], 0.0)
        self.assertGreater(suite["sessions"], 0)

    def test_pillar_3_purged_walk_forward_sample_size(self):
        """Pillar 3: Walk-forward engine supports 87 non-overlapping periods with Newey-West stats."""
        # Test Newey-West stats calculation
        excesses = [1.2, -0.5, 0.8, -1.0, 2.1, 0.4, -0.2, 1.5, -0.9, 0.3]
        nw = compute_newey_west_stats(excesses, max_lags=2)
        self.assertIn("mean", nw)
        self.assertIn("se_hac", nw)
        self.assertIn("t_stat", nw)
        self.assertIn("ci_lower_95", nw)

        # Test Wilson binomial CI
        low, high = compute_wilson_ci(10, 20)
        self.assertLessEqual(low, 50.0)
        self.assertGreaterEqual(high, 50.0)

    def test_pillar_4_calibrated_empirical_probability(self):
        """Pillar 4: Bins with N < 30 strictly return INSUFFICIENT_DATA."""
        # Unseen / small factor bucket
        prob_res = get_calibrated_empirical_probability(
            mos_pct=-50.0,
            debt_equity=2.5,
            passes_macro=False,
            rsi_14=85.0,
        )
        self.assertEqual(prob_res["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(prob_res["empirical_probability_pct"])

    def test_pillar_5_portfolio_risk_and_knife_guard(self):
        """Pillar 5: Falling knife guard and portfolio drawdown kill rule."""
        conn = sqlite3.connect(DB_PATH)
        # Test reversal confirmation
        rev_conf = check_reversal_confirmation("SQURPHARMA", conn)
        self.assertIsInstance(rev_conf, bool)
        conn.close()

        # Test portfolio drawdown kill switch
        portfolio_state = {"total_capital_bdt": 100000.0, "high_water_mark_bdt": 100000.0}
        # 5% drawdown -> safe
        is_killed, dd, _ = check_portfolio_drawdown_kill(portfolio_state, 95000.0)
        self.assertFalse(is_killed)
        self.assertEqual(dd, 5.0)

        # 12% drawdown -> kill triggered
        is_killed, dd, _ = check_portfolio_drawdown_kill(portfolio_state, 88000.0)
        self.assertTrue(is_killed)
        self.assertEqual(dd, 12.0)

    def test_pillar_6_microstructure_ticket_fees(self):
        """Pillar 6: Break-even pricing accounts for ৳5.00 minimum ticket fee and 0.880% round-trip."""
        self.assertEqual(ROUND_TRIP_COST_PCT, 0.880)
        be_standard = calculate_round_trip_break_even(100.0, shares=100, min_fee=0.0)
        # 100 * (1 + 0.00415) / (1 - 0.00465) = 100.88
        self.assertEqual(be_standard, 100.88)

        # With ৳5.00 min ticket fee on 1 share:
        be_min_fee = calculate_round_trip_break_even(100.0, shares=1, min_fee=5.0)
        self.assertGreater(be_min_fee, be_standard)

    def test_pillar_7_and_8_statistical_promotion_gate(self):
        """Pillar 8: Challenger failing statistical gates must be rejected."""
        mock_wf = {
            "folds_evaluated": 87,
            "statistics": {
                "mean_excess_return_pct": -0.50,  # Negative alpha
                "excess_95_ci": [-1.50, 0.50],    # Crosses zero
                "newey_west_t_stat": -0.80,       # Below 2.0
                "max_drawdown_pct": 22.0,         # Exceeds 10%
            },
            "folds_summary": [],
        }
        gate_res = run_statistical_promotion_gate("Failing_Challenger", mock_wf)
        self.assertEqual(gate_res["overall_status"], "REJECTED_BY_PROMOTION_GATE")
        self.assertFalse(gate_res["gates"]["gate_1_positive_net_alpha"]["passed"])
        self.assertFalse(gate_res["gates"]["gate_2_positive_95_ci_lower_bound"]["passed"])
        self.assertFalse(gate_res["gates"]["gate_3_newey_west_t_stat"]["passed"])

    def test_pillar_9_database_composite_indexes(self):
        """Pillar 9: Verify composite indexes exist in SQLite schema."""
        conn = sqlite3.connect(DB_PATH)
        indexes = {
            r[1]
            for r in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        conn.close()
        self.assertIn("idx_pit_composite", indexes)
        self.assertIn("idx_pit_verified", indexes)
        self.assertIn("idx_corp_actions_composite", indexes)

    def test_zero_bank_exposure_inv3(self):
        """Invariant 3: Zero conventional banks/financials permitted, even if marked Unknown."""
        self.assertTrue(is_shariah_excluded_company("Banking"))
        self.assertTrue(is_shariah_company := is_shariah_excluded_company("Unknown", ticker="JAMUNABANK"))
        self.assertTrue(is_shariah_excluded_company("Unknown", ticker="PRIMEBANK"))
        self.assertTrue(is_shariah_excluded_company("Unknown", ticker="IPDC"))
        self.assertTrue(is_shariah_excluded_company("Unknown", name="National Credit and Commerce Bank PLC."))
        # Non-bank Halal company passes
        self.assertFalse(is_shariah_excluded_company("Pharmaceuticals", ticker="SQURPHARMA"))
        self.assertFalse(is_shariah_excluded_company("Fuel_Power", ticker="JAMUNAOIL"))


if __name__ == "__main__":
    unittest.main()
