"""
tests/test_institutional_expert.py — Institutional Securities Expert Test Suite
Verifies the three institutional pillars:
  1. Political Exposure & Governance/Legal Risk Sentinel
  2. Export vs Domestic Revenue & Regulatory Accreditations Disaggregator
  3. Head-to-Head Peer Moat Matrix & 3-Way DuPont ROE Decomposition
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.governance_risk_sentinel import (
    evaluate_governance_risk,
    list_high_risk_governance,
    DB_PATH
)
from scripts.revenue_segment_analyzer import (
    get_revenue_segment,
    list_top_exporters,
    KNOWN_SEGMENT_PROFILES
)
from scripts.peer_moat_comparator import (
    get_peer_metrics,
    compare_peers
)


class TestGovernanceRiskSentinel(unittest.TestCase):
    """Verifies Pillar 1: Corporate Governance, Legal Exposure, and Political Overhang."""

    def test_bxpharma_high_governance_risk(self):
        """BXPHARMA must flag sponsor detention, Beximco receivership proceedings, and high risk tier."""
        audit = evaluate_governance_risk("BXPHARMA")
        self.assertEqual(audit["ticker"], "BXPHARMA")
        self.assertIn(audit["legal_risk_tier"], ("HIGH", "CRITICAL"))
        self.assertGreaterEqual(audit["political_exposure_score"], 60)
        self.assertEqual(audit["receivership_court_petition"], 1)
        self.assertEqual(audit["sponsor_legal_issues"], 1)
        self.assertGreater(len(audit["active_flags"]), 0)

    def test_squrpharma_pristine_governance(self):
        """SQURPHARMA must reflect pristine governance, zero receivership risk, and low score."""
        audit = evaluate_governance_risk("SQURPHARMA")
        self.assertEqual(audit["ticker"], "SQURPHARMA")
        self.assertEqual(audit["legal_risk_tier"], "LOW")
        self.assertLessEqual(audit["political_exposure_score"], 20)
        self.assertEqual(audit["receivership_court_petition"], 0)
        self.assertEqual(audit["sponsor_legal_issues"], 0)

    def test_unknown_ticker_governance_fallback(self):
        """Unknown or uncurated tickers must evaluate gracefully without throwing exceptions."""
        audit = evaluate_governance_risk("XYZUNKNOWN123")
        self.assertEqual(audit["ticker"], "XYZUNKNOWN123")
        self.assertIn("legal_risk_tier", audit)
        self.assertIn("political_exposure_score", audit)
        self.assertEqual(audit["receivership_court_petition"], 0)

    def test_database_persistence_governance(self):
        """Audit results must save cleanly to the SQLite database without constraint errors."""
        evaluate_governance_risk("BXPHARMA")
        high_risk = list_high_risk_governance()
        tickers = [a["ticker"] for a in high_risk]
        self.assertIn("BXPHARMA", tickers)


class TestRevenueSegmentAnalyzer(unittest.TestCase):
    """Verifies Pillar 2: Export vs Domestic Revenue & Regulatory Accreditations."""

    def test_bxpharma_revenue_and_accreditations(self):
        """BXPHARMA must show ~10% export revenue and prestigious US FDA & UK MHRA certifications."""
        rev = get_revenue_segment("BXPHARMA")
        self.assertEqual(rev["ticker"], "BXPHARMA")
        self.assertAlmostEqual(rev["export_share_pct"], 9.95, delta=0.5)
        self.assertEqual(rev["us_fda_approved"], 1)
        self.assertEqual(rev["uk_mhra_approved"], 1)
        self.assertEqual(rev["who_gmp_approved"], 1)
        self.assertGreaterEqual(rev["export_destinations_count"], 50)

    def test_squrpharma_accreditations(self):
        """SQURPHARMA must have US FDA and UK MHRA approvals."""
        rev = get_revenue_segment("SQURPHARMA")
        self.assertEqual(rev["ticker"], "SQURPHARMA")
        self.assertEqual(rev["us_fda_approved"], 1)
        self.assertEqual(rev["uk_mhra_approved"], 1)

    def test_unknown_ticker_revenue_default(self):
        """Unknown ticker should default to 100% domestic, 0% export without throwing."""
        rev = get_revenue_segment("RANDOM_TICKER")
        self.assertEqual(rev["ticker"], "RANDOM_TICKER")
        self.assertEqual(rev["export_share_pct"], 0.0)
        self.assertEqual(rev["us_fda_approved"], 0)

    def test_top_exporters_listing(self):
        """Listing top exporters must include core pharma and export giants."""
        for ticker in KNOWN_SEGMENT_PROFILES:
            get_revenue_segment(ticker)
        top = list_top_exporters()
        tickers = [item["ticker"] for item in top]
        self.assertIn("BXPHARMA", tickers)
        self.assertIn("SQURPHARMA", tickers)


class TestPeerMoatComparator(unittest.TestCase):
    """Verifies Pillar 3: DuPont ROE Decomposition, Macro ERP, and Head-to-Head Comparison."""

    def test_bxpharma_metrics_and_dupont(self):
        """DuPont 3-Way Identity: ROE = Net Margin * Asset Turnover * Equity Multiplier."""
        metrics = get_peer_metrics("BXPHARMA")
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["ticker"], "BXPHARMA")
        dupont = metrics["dupont"]
        
        # Verify 3 factors exist and are positive
        self.assertGreater(dupont["net_margin_pct"], 0)
        self.assertGreater(dupont["asset_turnover"], 0)
        self.assertGreater(dupont["equity_multiplier"], 0)
        
        # Formula check: Margin * Turnover * Multiplier = ROE
        expected_roe = (dupont["net_margin_pct"] / 100.0) * dupont["asset_turnover"] * dupont["equity_multiplier"] * 100.0
        self.assertAlmostEqual(dupont["formula_check_roe"], round(expected_roe, 2), delta=0.1)

    def test_peer_comparison_ranking(self):
        """Comparing BXPHARMA, SQURPHARMA, RENATA must accurately penalize governance overhang and reward pristine ROE."""
        res = compare_peers(["BXPHARMA", "SQURPHARMA", "RENATA"])
        ranking = res["ranking"]
        self.assertEqual(len(ranking), 3)
        
        # SQURPHARMA must rank #1 due to ~17% ROE, zero debt, and pristine governance
        self.assertEqual(res["top_pick"], "SQURPHARMA")
        self.assertGreater(res["top_score"], 80)
        
        # BXPHARMA must carry governance penalty
        bx = next(r for r in ranking if r["ticker"] == "BXPHARMA")
        self.assertEqual(bx["metrics"]["governance_tier"], "HIGH")
        self.assertGreater(bx["metrics"]["political_score"], 50)

    def test_macro_erp_calculation(self):
        """Equity Risk Premium (ERP) must accurately compute Earnings Yield minus 91-Day T-Bill (11.60%)."""
        metrics = get_peer_metrics("BXPHARMA")
        ey = metrics["earnings_yield"]
        erp = metrics["macro_erp_vs_tbill"]
        rf = 11.60
        self.assertAlmostEqual(erp, ey - rf, delta=0.05)


if __name__ == "__main__":
    unittest.main()
