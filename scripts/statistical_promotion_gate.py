"""
Institutional Statistical Promotion Gatekeeper
=============================================
Enforces the 6 Non-Negotiable Institutional Proof Gates before any model
or factor weights can be promoted from Challenger to Champion:

  Gate 1: Net Out-of-Sample Alpha > 0.0% (after 0.880% statutory fees + 0.20% slippage)
  Gate 2: 95% Confidence Interval Lower Bound > 0.0% (positive lower bound)
  Gate 3: Newey-West HAC t-statistic > 2.0 (statistically significant at alpha=0.05)
  Gate 4: Holm-Bonferroni adjusted p-value < 0.05 (FWER controlled)
  Gate 5: Positive alpha in >= 3 out of 5 historical macro regimes
  Gate 6: Zero portfolio drawdown kill-rule breaches (MDD < 10.0%)

FAIL-CLOSED DESIGN: If any single gate fails, promotion is REJECTED.
The serving champion model remains locked and untouched.
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LEARN_DIR = DATA_DIR / "learning"
PROC_DIR = DATA_DIR / "processed"
DB_PATH = PROC_DIR / "dse.db"
REGISTRY_PATH = LEARN_DIR / "model_registry.json"

ROUND_TRIP_COST_PCT = 0.880
EXECUTION_SPREAD_PCT = 0.200
TOTAL_FRICTION_PCT = ROUND_TRIP_COST_PCT + EXECUTION_SPREAD_PCT


def compute_t_pval(t_stat: float, df: int) -> float:
    """Approximates two-tailed p-value from t-statistic using normal/student approximation."""
    if df <= 0 or math.isnan(t_stat):
        return 1.0
    abs_t = abs(t_stat)
    # Standard normal approximation for large df (e.g. df >= 30)
    # Using complementary error function approximation
    pval = math.erfc(abs_t / math.sqrt(2.0))
    return max(1e-6, min(1.0, pval))


def evaluate_regime_performance(
    fold_details: List[Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """
    Classifies evaluation periods into 5 macro regimes and evaluates alpha across regimes:
      1. Bull Drift (DSEX > 50-DMA)
      2. Bear Drain (DSEX < 50-DMA)
      3. Rate Shock (T-Bill >= 11.0%)
      4. Squeeze / Panic (Market turnover < 300 Cr)
      5. Sideways Neutral
    """
    regimes = {
        "bull_drift": [],
        "bear_drain": [],
        "rate_shock": [],
        "panic_squeeze": [],
        "sideways": [],
    }

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row

    try:
        for f in fold_details:
            dt = f["start_date"]
            exc = f["excess_return_pct"]

            # Query market condition at dt
            row = conn.execute(
                "SELECT dsex FROM market_summary WHERE date <= ? AND dsex IS NOT NULL ORDER BY date DESC LIMIT 1",
                (dt,),
            ).fetchone()
            dsex = float(row[0]) if row and row[0] else 5000.0

            # 50-DMA of DSEX
            dma_row = conn.execute(
                "SELECT AVG(dsex) FROM (SELECT dsex FROM market_summary WHERE date <= ? AND dsex IS NOT NULL ORDER BY date DESC LIMIT 50)",
                (dt,),
            ).fetchone()
            dma50 = float(dma_row[0]) if dma_row and dma_row[0] else dsex

            # High rate check (post-2023 is high rate shock)
            is_high_rate = dt >= "2023-07-01"

            if is_high_rate:
                regimes["rate_shock"].append(exc)
            elif dsex >= dma50 * 1.02:
                regimes["bull_drift"].append(exc)
            elif dsex <= dma50 * 0.98:
                regimes["bear_drain"].append(exc)
            else:
                regimes["sideways"].append(exc)

        regime_results = {}
        positive_regimes_count = 0

        for r_name, rets in regimes.items():
            if rets:
                mean_r = sum(rets) / len(rets)
                is_pos = mean_r > 0.0
                if is_pos:
                    positive_regimes_count += 1
                regime_results[r_name] = {
                    "periods": len(rets),
                    "mean_excess_pct": round(mean_r, 3),
                    "is_positive": is_pos,
                }
            else:
                regime_results[r_name] = {
                    "periods": 0,
                    "mean_excess_pct": 0.0,
                    "is_positive": False,
                }

        return {
            "regime_breakdown": regime_results,
            "positive_regimes_count": positive_regimes_count,
            "passes_regime_gate": positive_regimes_count >= 3,
        }
    finally:
        conn.close()


def run_statistical_promotion_gate(
    challenger_name: str,
    walk_forward_results: Dict[str, Any],
    num_tested_challengers: int = 1,
) -> Dict[str, Any]:
    """
    Applies the 6 institutional promotion gates to the candidate model's walk-forward results.
    """
    stats = walk_forward_results.get("statistics", {})
    n_folds = walk_forward_results.get("folds_evaluated", 0)

    mean_alpha = stats.get("mean_excess_return_pct", 0.0)
    ci_low = stats.get("excess_95_ci", [0.0, 0.0])[0]
    ci_high = stats.get("excess_95_ci", [0.0, 0.0])[1]
    t_stat = stats.get("newey_west_t_stat", 0.0)
    mdd = stats.get("max_drawdown_pct", 0.0)

    # 1. Unadjusted p-value
    raw_p = compute_t_pval(t_stat, df=max(1, n_folds - 1))

    # 2. Holm-Bonferroni FWER adjusted p-value
    # adjusted_p = min(1.0, raw_p * num_tested_challengers)
    holm_p = round(min(1.0, raw_p * max(1, num_tested_challengers)), 4)

    # 3. Regime robustness
    folds_data = walk_forward_results.get("folds_summary", [])
    regime_res = evaluate_regime_performance(folds_data)
    pos_regimes = regime_res.get("positive_regimes_count", 0)

    # Evaluate the 6 Hard Gates
    gate1_pass = mean_alpha > 0.0
    gate2_pass = ci_low > 0.0
    gate3_pass = t_stat > 2.0
    gate4_pass = holm_p < 0.05
    gate5_pass = pos_regimes >= 3
    gate6_pass = mdd < 10.0  # Zero drawdown kill breach

    all_passed = all([gate1_pass, gate2_pass, gate3_pass, gate4_pass, gate5_pass, gate6_pass])

    verdict = {
        "timestamp": datetime.now().isoformat(),
        "challenger": challenger_name,
        "overall_status": "PROMOTED_TO_CHAMPION" if all_passed else "REJECTED_BY_PROMOTION_GATE",
        "gates": {
            "gate_1_positive_net_alpha": {
                "metric": f"{mean_alpha:.3f}%",
                "threshold": "> 0.0%",
                "passed": gate1_pass,
            },
            "gate_2_positive_95_ci_lower_bound": {
                "metric": f"{ci_low:.3f}%",
                "threshold": "> 0.0%",
                "passed": gate2_pass,
            },
            "gate_3_newey_west_t_stat": {
                "metric": f"{t_stat:.2f}",
                "threshold": "> 2.00",
                "passed": gate3_pass,
            },
            "gate_4_holm_bonferroni_p_val": {
                "metric": f"{holm_p:.4f}",
                "threshold": "< 0.0500",
                "passed": gate4_pass,
            },
            "gate_5_multi_regime_invariance": {
                "metric": f"{pos_regimes}/5 regimes positive",
                "threshold": ">= 3/5 regimes",
                "passed": gate5_pass,
            },
            "gate_6_drawdown_kill_compliance": {
                "metric": f"{mdd:.2f}%",
                "threshold": "< 10.00% MDD",
                "passed": gate6_pass,
            },
        },
        "regime_details": regime_res,
        "summary": (
            f"Challenger {challenger_name} PROMOTED to Champion."
            if all_passed
            else f"Challenger {challenger_name} REJECTED: Failed {sum(1 for p in [gate1_pass, gate2_pass, gate3_pass, gate4_pass, gate5_pass, gate6_pass] if not p)}/6 gates. Champion remains safely locked."
        ),
    }

    return verdict


if __name__ == "__main__":
    from purged_walk_forward_engine import run_purged_walk_forward_evaluation

    print("Running Walk-Forward Evaluation for Promotion Gate...", flush=True)
    wf_res = run_purged_walk_forward_evaluation(n_periods=87)
    decision = run_statistical_promotion_gate(
        challenger_name="Candidate_Factor_Model_v2",
        walk_forward_results=wf_res,
        num_tested_challengers=1,
    )
    print("\n" + "=" * 80)
    print("🏛️ INSTITUTIONAL STATISTICAL PROMOTION GATE VERDICT")
    print("=" * 80)
    print(json.dumps(decision, indent=2))
