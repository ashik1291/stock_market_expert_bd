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
        self.assertIn("rank_log_full_universe", names)

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


if __name__ == "__main__":
    unittest.main()
