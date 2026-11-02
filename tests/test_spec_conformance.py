"""
tests/test_spec_conformance.py
------------------------------
Unit test suite verifying that the codebase conforms strictly to SPEC.md
and passes all 8 Non-Negotiable System Invariants via scripts/spec_guard.py.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from spec_guard import (
    check_inv1_pit_isolation,
    check_inv2_macro_hurdle,
    check_inv3_shariah_zero_bank,
    check_inv4_microstructure_realism,
    check_inv5_champion_registry,
    check_inv6_cryptographic_ledger,
    check_inv7_sqlite_wal,
    check_inv8_portable_bootstrap,
    run_spec_guard,
)


class TestSpecConformance(unittest.TestCase):
    """Verifies that all 8 non-negotiable invariants in SPEC.md are enforced."""

    def test_inv1_point_in_time_isolation(self):
        ok, msg = check_inv1_pit_isolation()
        self.assertTrue(ok, f"INV-1 Failed: {msg}")

    def test_inv2_central_bank_macro_hurdle(self):
        ok, msg = check_inv2_macro_hurdle()
        self.assertTrue(ok, f"INV-2 Failed: {msg}")

    def test_inv3_shariah_and_zero_bank_shield(self):
        ok, msg = check_inv3_shariah_zero_bank()
        self.assertTrue(ok, f"INV-3 Failed: {msg}")

    def test_inv4_frontier_microstructure_realism(self):
        ok, msg = check_inv4_microstructure_realism()
        self.assertTrue(ok, f"INV-4 Failed: {msg}")

    def test_inv5_frozen_champion_registry(self):
        ok, msg = check_inv5_champion_registry()
        self.assertTrue(ok, f"INV-5 Failed: {msg}")

    def test_inv6_cryptographic_forward_test_ledger(self):
        ok, msg = check_inv6_cryptographic_ledger()
        self.assertTrue(ok, f"INV-6 Failed: {msg}")

    def test_inv7_universal_sqlite_wal(self):
        ok, msg = check_inv7_sqlite_wal()
        self.assertTrue(ok, f"INV-7 Failed: {msg}")

    def test_inv8_zero_broken_portable_bootstrap(self):
        ok, msg = check_inv8_portable_bootstrap()
        self.assertTrue(ok, f"INV-8 Failed: {msg}")

    def test_full_spec_guard_runner(self):
        passed = run_spec_guard()
        self.assertTrue(passed, "run_spec_guard() failed one or more invariants")

    def test_planner_skill_exists(self):
        skill_path = os.path.join(ROOT, ".agents", "skills", "dse-planner", "SKILL.md")
        self.assertTrue(os.path.exists(skill_path), "dse-planner skill is missing")

    def test_user_proxy_simulation_generates_valid_plan(self):
        from user_proxy_simulation import evaluate_user_investment_plan
        res = evaluate_user_investment_plan(capital_bdt=50000.0, top_n=3)
        self.assertIn("top_picks", res)
        self.assertGreaterEqual(len(res["top_picks"]), 1)
        first = res["top_picks"][0]
        self.assertIn("profit_probability", first)
        self.assertGreaterEqual(first["profit_probability"], 50.0)
        self.assertIn("limit_entry", first)
        self.assertIn("break_even", first)
        self.assertIn("tp1", first)
        self.assertIn("stop_loss", first)


if __name__ == "__main__":
    unittest.main()
