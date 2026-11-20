"""
scripts/multi_horizon_evaluator.py — Multi-Horizon Prediction Evaluator & Alpha Accrual

Evaluates pending predictions across H=5 (1-week swing), H=10 (2-week cycle), and H=21 (position).
Precomputes benchmark intervals so 300+ predictions evaluate in < 3 seconds without SQLite locks.
"""

from __future__ import annotations

import sys
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime

# UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LEARN_DIR = DATA_DIR / "learning"
PROC_DIR = DATA_DIR / "processed"
REPORT_DIR = BASE_DIR / "reports" / "learning"
DB_PATH = PROC_DIR / "dse.db"

SCRIPTS = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

from unified_score import ROUND_TRIP_COST_PCT
from benchmark_index import equal_weight_category_a_nav

LEDGER_PATH = LEARN_DIR / "prediction_ledger.json"
WEIGHTS_PATH = LEARN_DIR / "model_weights.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("multi_horizon_evaluator")


LABEL_FIELDS = ("evaluated_at", "actual_outcome", "stock_return_pct", "eqw_return_pct", "net_excess_pct",
                "realized_return_pct", "reward_score", "eval_end_date", "horizon_bars_used",
                "eval_horizon_target", "mistake_analysis")


def _priced_sessions(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("""
        SELECT t.date FROM trading_calendar t
        WHERE t.is_trading_day = 1 AND t.date IN (SELECT DISTINCT date FROM prices)
        ORDER BY t.date
    """)]


def horizon_end_date(sessions: list[str], pred_date: str, horizon: int) -> str | None:
    """The horizon-th priced trading session strictly after pred_date, or None if not yet reached."""
    import bisect
    i = bisect.bisect_right(sessions, pred_date) + horizon - 1
    return sessions[i] if i < len(sessions) else None


def reopen_partial_horizon_labels(ledger: list[dict], default_horizon: int) -> int:
    """Return EVALUATED items scored on fewer bars than their declared horizon to PENDING."""
    reopened = 0
    for item in ledger:
        if item.get("status") != "EVALUATED":
            continue
        if not item.get("horizon_bars"):
            continue  # no declared horizon, so a label cannot be "partial"
        h = int(item["horizon_bars"])
        used = item.get("horizon_bars_used")
        if used is None or int(used) < h:
            for k in LABEL_FIELDS:
                item.pop(k, None)
            item["status"] = "PENDING"
            item["relabel_reason"] = f"previously scored on {used} bars < declared horizon {h}"
            reopened += 1
    return reopened


def evaluate_predictions(target_horizon_bars: int = 10, min_bars_required: int | None = None) -> dict:
    """
    Evaluates pending predictions once their full declared horizon (item horizon_bars, else
    target_horizon_bars) of trading sessions has elapsed. Partial horizons are never scored;
    min_bars_required is accepted for backward compatibility and ignored.
    """
    if not LEDGER_PATH.exists():
        log.error(f"Ledger not found at {LEDGER_PATH}")
        return {"ok": False, "error": "Ledger missing"}

    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        ledger = json.load(f)

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    sessions = _priced_sessions(conn)
    session_set = set(sessions)
    reopened = reopen_partial_horizon_labels(ledger, target_horizon_bars)
    if reopened:
        log.info(f"Reopened {reopened} predictions previously scored on a partial horizon.")

    # Cache benchmark intervals (pred_date, end_date) -> eqw_return_pct
    benchmark_cache = {}

    def get_cached_eqw(start: str, end: str) -> float:
        key = (start, end)
        if key not in benchmark_cache:
            res = equal_weight_category_a_nav(start, end)
            ret = res.get("return_pct") if res.get("ok") else 0.0
            benchmark_cache[key] = ret if ret is not None else 0.0
        return benchmark_cache[key]

    evaluated_count = 0
    correct_count = 0
    cash_gain_count = 0
    total_net_excess = 0.0

    outcomes_breakdown = {}

    log.info(f"Auditing {len(ledger)} predictions in ledger (target H={target_horizon_bars}, min H={min_bars_required})...")

    for item in ledger:
        if item.get("status") != "PENDING":
            continue

        if item.get("timeframe") == "historical_bootstrap":
            item["status"] = "INVALID_BOOTSTRAP"
            continue

        ticker = item["ticker"]
        pred_date = item["date"]
        direction = item.get("predicted_direction", "RISE")
        entry = float(item.get("entry_price") or 0.0)
        if entry <= 0:
            continue

        if pred_date not in session_set:
            item["status"] = "INVALID_NON_TRADING_DAY"
            continue
        base_row = conn.execute("SELECT close FROM prices WHERE ticker = ? AND date = ?", (ticker, pred_date)).fetchone()
        if base_row and base_row[0]:
            entry = float(base_row[0])
        horizon = int(item.get("horizon_bars") or target_horizon_bars)
        end_date = horizon_end_date(sessions, pred_date, horizon)
        if end_date is None:
            continue
        # A suspended stock cannot be exited, so its last traded close stands at the horizon.
        end_row = conn.execute(
            "SELECT close FROM prices WHERE ticker = ? AND date > ? AND date <= ? AND close IS NOT NULL "
            "ORDER BY date DESC LIMIT 1",
            (ticker, pred_date, end_date),
        ).fetchone()
        if not end_row:
            continue
        n_bars = horizon
        end_close = float(end_row[0])
        # Bonus / split in the window dilutes the raw close; restore per-original-share value.
        for (fac,) in conn.execute(
            """
            SELECT adjustment_factor FROM corporate_actions
            WHERE ticker = ? AND record_date > ? AND record_date <= ?
              AND action_type IN ('bonus_dividend', 'split', 'rights_split')
              AND adjustment_factor > 0 AND adjustment_factor < 1
            """,
            (ticker, pred_date, end_date),
        ).fetchall():
            end_close /= float(fac)

        # Adjust for cash dividends received in window
        div_row = conn.execute(
            """
            SELECT SUM(cash_amount) FROM corporate_actions
            WHERE ticker = ? AND action_type = 'cash_dividend'
              AND record_date > ? AND record_date <= ?
              AND cash_amount IS NOT NULL AND cash_amount > 0
            """,
            (ticker, pred_date, end_date),
        ).fetchone()

        cash_div = float(div_row[0]) if (div_row and div_row[0] is not None) else 0.0
        effective_end_val = end_close + (cash_div * 0.90)  # 10% AIT tax net
        stock_ret_pct = ((effective_end_val / entry) - 1.0) * 100.0

        # Benchmark return
        eqw_ret = get_cached_eqw(pred_date, end_date)
        net_cash_ret = stock_ret_pct - ROUND_TRIP_COST_PCT
        net_excess = stock_ret_pct - eqw_ret - ROUND_TRIP_COST_PCT

        if direction == "RISE":
            if net_cash_ret > 0:
                outcome = "CORRECT_PROFIT"
                reward = 1.0
                win = True
                cash_gain_count += 1
            elif net_excess > 0:
                outcome = "RELATIVE_ALPHA_CASH_LOSS"
                reward = -0.5  # Penalize losing capital even if beat falling index
                win = False
            else:
                outcome = "INCORRECT_LOSS"
                reward = -1.0
                win = False
        elif direction == "FALL":
            win = (eqw_ret - stock_ret_pct) > 0
            outcome = "AVOIDANCE_SUCCESS" if win else "AVOIDANCE_FAIL"
            reward = 0.5 if win else -0.5
        else:
            win = abs(net_excess) < 1.0
            outcome = "CORRECT" if win else "INCORRECT"
            reward = 1.0 if win else -1.0

        item["status"] = "EVALUATED"
        item["evaluated_at"] = datetime.now().isoformat()
        item["actual_outcome"] = outcome
        item["stock_return_pct"] = round(stock_ret_pct, 4)
        item["eqw_return_pct"] = round(eqw_ret, 4)
        item["net_excess_pct"] = round(net_excess, 4)
        item["realized_return_pct"] = round(stock_ret_pct, 4)
        item["reward_score"] = reward
        item["eval_end_date"] = end_date
        item["horizon_bars_used"] = n_bars
        item["eval_horizon_target"] = horizon
        item.pop("relabel_reason", None)

        evaluated_count += 1
        if win:
            correct_count += 1
        total_net_excess += net_excess
        outcomes_breakdown[outcome] = outcomes_breakdown.get(outcome, 0) + 1

    conn.close()

    # Save ledger
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)

    # Compute overall statistics
    total_evaluated = sum(1 for i in ledger if i.get("status") == "EVALUATED")
    total_wins = sum(1 for i in ledger if i.get("actual_outcome") in ("CORRECT_PROFIT", "AVOIDANCE_SUCCESS", "CORRECT"))
    win_rate_pct = (total_wins / total_evaluated * 100.0) if total_evaluated > 0 else 0.0
    avg_net_excess = (total_net_excess / evaluated_count) if evaluated_count > 0 else 0.0

    # Update model weights metadata
    if WEIGHTS_PATH.exists():
        with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
            w_data = json.load(f)
        w_data["overall_accuracy_pct"] = round(win_rate_pct, 2)
        w_data["total_evaluated_count"] = total_evaluated
        w_data["updated_at"] = datetime.now().isoformat()
        with open(WEIGHTS_PATH, "w", encoding="utf-8") as f:
            json.dump(w_data, f, indent=2)

    print("\n" + "=" * 80)
    print("🎯 MULTI-HORIZON PREDICTION ACCURACY REPORT")
    print("=" * 80)
    print(f"Newly Evaluated in Run: {evaluated_count} predictions")
    print(f"Total Evaluated (All):  {total_evaluated}")
    print(f"Total Winning Calls:    {total_wins}")
    print(f"Empirical Win Rate:     {win_rate_pct:.2f}%")
    print(f"Avg Net Excess vs EQW:  {avg_net_excess:+.2f}%")
    print("-" * 80)
    print("Outcome Breakdown (Newly Evaluated):")
    for out, count in outcomes_breakdown.items():
        pct = (count / evaluated_count * 100) if evaluated_count > 0 else 0
        print(f"  * {out:<26}: {count:>3} ({pct:>5.1f}%)")
    print("=" * 80 + "\n")

    return {
        "ok": True,
        "evaluated_in_run": evaluated_count,
        "total_evaluated": total_evaluated,
        "total_wins": total_wins,
        "win_rate_pct": win_rate_pct,
        "avg_net_excess": avg_net_excess,
        "breakdown": outcomes_breakdown,
    }


if __name__ == "__main__":
    h = 10
    if len(sys.argv) > 1:
        try:
            h = int(sys.argv[1])
        except ValueError:
            pass
    evaluate_predictions(target_horizon_bars=h)
