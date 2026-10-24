"""
DSE Learning Engine — Phase 2 honest labels.

Label definition (pre-registered):
  horizon H = 21 trading bars after prediction date
  stock_ret = close[t+H] / close[t] - 1
  eqw_ret   = equal-weight Category A return over same window
  net_excess_pct = (stock_ret - eqw_ret) * 100 - ROUND_TRIP_COST_PCT
  For RISE calls: reward = +1 if net_excess > 0 else -1
  For FALL calls: reward = +1 if net_excess < 0 else -1
  (FALL success = underperformed universe after costs)

Epoch 1 ledger (CORRECT/±5%/bootstrap) archived as invalid — do not train on it.
"""

from __future__ import annotations

import sys
import sqlite3
import json
import math
import logging
import shutil
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LEARN_DIR = DATA_DIR / "learning"
PROC_DIR = DATA_DIR / "processed"
REPORT_DIR = BASE_DIR / "reports" / "learning"
DB_PATH = PROC_DIR / "dse.db"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from unified_score import ROUND_TRIP_COST_PCT, DEFAULT_HORIZON_BARS, MODEL_ID
from benchmark_index import equal_weight_category_a_nav

LEDGER_PATH = LEARN_DIR / "prediction_ledger.json"
ARCHIVE_PATH = LEARN_DIR / "prediction_ledger_epoch1_invalid.json"
WEIGHTS_PATH = LEARN_DIR / "model_weights.json"
META_PATH = LEARN_DIR / "phase2_meta.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rl_learning_engine")

DEFAULT_WEIGHTS = {
    "smart_money_weight": 1.0,
    "valuation_mos_weight": 1.0,
    "debt_npl_weight": 1.0,
    "rsi_momentum_weight": 1.0,
    "macd_trend_weight": 1.0,
    "governance_weight": 1.0,
    "macro_bias_weight": 1.0,
    "learning_rate": 0.02,
    "total_training_cycles": 0,
    "overall_accuracy_pct": None,
    "label_definition": f"net_excess_vs_eqw_h{DEFAULT_HORIZON_BARS}_minus_{ROUND_TRIP_COST_PCT}pct",
    "model_id": MODEL_ID,
    "updated_at": datetime.now().isoformat(),
}


def init_learning_storage():
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not WEIGHTS_PATH.exists():
        with open(WEIGHTS_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_WEIGHTS, f, indent=2)
    if not LEDGER_PATH.exists():
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def archive_epoch1_invalid(force: bool = False) -> dict:
    """
    Move leaky Epoch-1 ledger aside once. Fresh Phase-2 ledger starts empty.
    """
    init_learning_storage()
    meta = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    if meta.get("epoch1_archived") and not force:
        return {"archived": False, "reason": "already archived", "meta": meta}

    if LEDGER_PATH.exists():
        shutil.copy2(LEDGER_PATH, ARCHIVE_PATH)
        old = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        n_boot = sum(1 for i in old if i.get("timeframe") == "historical_bootstrap")
        meta = {
            "epoch1_archived": True,
            "archived_at": datetime.now().isoformat(),
            "archive_path": str(ARCHIVE_PATH.relative_to(BASE_DIR)),
            "archived_count": len(old),
            "bootstrap_count": n_boot,
            "reason": "lookahead bootstrap + CORRECT/±5% labels invalid for Phase 2",
            "phase2_label": DEFAULT_WEIGHTS["label_definition"],
            "model_id": MODEL_ID,
        }
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        # Reset weights to neutral priors (no Epoch-1 contamination)
        save_weights(dict(DEFAULT_WEIGHTS))
        log.info(f"Archived {len(old)} Epoch-1 preds ({n_boot} bootstrap) -> {ARCHIVE_PATH.name}")
        return {"archived": True, "count": len(old), "bootstrap": n_boot, "meta": meta}

    meta = {
        "epoch1_archived": True,
        "archived_at": datetime.now().isoformat(),
        "archived_count": 0,
        "reason": "no prior ledger",
        "model_id": MODEL_ID,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return {"archived": True, "count": 0, "meta": meta}


def load_weights() -> dict:
    init_learning_storage()
    with open(WEIGHTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_weights(w: dict):
    w["updated_at"] = datetime.now().isoformat()
    w["model_id"] = MODEL_ID
    w["label_definition"] = DEFAULT_WEIGHTS["label_definition"]
    with open(WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(w, f, indent=2)


def load_ledger() -> list:
    init_learning_storage()
    with open(LEDGER_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_ledger(ledger: list):
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)


def record_prediction(
    date_str: str,
    ticker: str,
    timeframe: str,
    direction: str,
    prob_pct: float,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    active_signals: dict,
    score: float | None = None,
    model_id: str | None = None,
    horizon_bars: int = DEFAULT_HORIZON_BARS,
) -> str:
    ledger = load_ledger()
    pred_id = f"{ticker}_{date_str}_{timeframe}"
    for item in ledger:
        if item.get("prediction_id") == pred_id:
            return pred_id

    record = {
        "prediction_id": pred_id,
        "date": date_str,
        "ticker": ticker,
        "timeframe": timeframe,
        "predicted_direction": direction,
        "confidence_prob_pct": prob_pct,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "active_signals": active_signals or {},
        "score": score,
        "model_id": model_id or MODEL_ID,
        "horizon_bars": horizon_bars,
        "label_definition": DEFAULT_WEIGHTS["label_definition"],
        "status": "PENDING",
        "evaluated_at": None,
        "actual_outcome": None,
        "stock_return_pct": None,
        "eqw_return_pct": None,
        "net_excess_pct": None,
        "realized_return_pct": None,
        "reward_score": 0.0,
        "mistake_analysis": None,
    }
    ledger.append(record)
    save_ledger(ledger)
    return pred_id


def _forward_close(conn: sqlite3.Connection, ticker: str, pred_date: str, horizon: int):
    rows = conn.execute(
        """
        SELECT date, close FROM prices
        WHERE ticker=? AND date>? AND close IS NOT NULL
        ORDER BY date ASC LIMIT ?
        """,
        (ticker, pred_date, horizon),
    ).fetchall()
    if len(rows) < horizon:
        return None, None, None
    return rows[-1][0], float(rows[-1][1]), len(rows)


def evaluate_pending_predictions(eval_window_days: int | None = None) -> dict:
    """
    Phase-2 evaluator: net excess vs EQW after round-trip cost. No ±5% band.
    """
    archive_epoch1_invalid()
    init_learning_storage()
    horizon = eval_window_days or DEFAULT_HORIZON_BARS
    conn = sqlite3.connect(DB_PATH)
    ledger = load_ledger()
    weights = load_weights()

    evaluated_count = 0
    correct_count = 0
    incorrect_count = 0

    for item in ledger:
        if item.get("status") != "PENDING":
            continue
        # Never evaluate leaked bootstrap rows if any slipped in
        if item.get("timeframe") == "historical_bootstrap":
            item["status"] = "INVALID_BOOTSTRAP"
            item["mistake_analysis"] = "Epoch-1 bootstrap discarded"
            continue

        ticker = item["ticker"]
        pred_date = item["date"]
        direction = item["predicted_direction"]
        entry = float(item["entry_price"] or 0)
        if entry <= 0:
            continue

        end_date, end_close, n_bars = _forward_close(conn, ticker, pred_date, horizon)
        if end_close is None:
            continue

        stock_ret_pct = ((end_close / entry) - 1.0) * 100.0
        eqw = equal_weight_category_a_nav(pred_date, end_date)
        eqw_ret = eqw.get("return_pct") if eqw.get("ok") else 0.0
        if eqw_ret is None:
            eqw_ret = 0.0

        # Directional net excess after friction
        if direction == "RISE":
            # Long: pay round-trip; win if beat EQW after cost
            net_excess = stock_ret_pct - eqw_ret - ROUND_TRIP_COST_PCT
            win = net_excess > 0
        elif direction == "FALL":
            # Bear call: win if stock underperforms EQW (no short cost model — use raw relative)
            net_excess = eqw_ret - stock_ret_pct  # positive if stock lagged universe
            win = net_excess > 0
        else:
            net_excess = stock_ret_pct - eqw_ret - ROUND_TRIP_COST_PCT
            win = abs(net_excess) < 1.0  # range: near flat excess

        outcome = "CORRECT" if win else "INCORRECT"
        reward = 1.0 if win else -1.0
        mistake = None
        if not win:
            mistake = (
                f"net_excess={net_excess:+.2f}% stock={stock_ret_pct:+.2f}% "
                f"eqw={eqw_ret:+.2f}% cost={ROUND_TRIP_COST_PCT}% H={n_bars}"
            )

        item["status"] = "EVALUATED"
        item["evaluated_at"] = datetime.now().isoformat()
        item["actual_outcome"] = outcome
        item["stock_return_pct"] = round(stock_ret_pct, 4)
        item["eqw_return_pct"] = round(eqw_ret, 4)
        item["net_excess_pct"] = round(net_excess, 4)
        item["realized_return_pct"] = round(stock_ret_pct, 4)
        item["reward_score"] = reward
        item["mistake_analysis"] = mistake
        item["eval_end_date"] = end_date
        item["horizon_bars_used"] = n_bars

        evaluated_count += 1
        if win:
            correct_count += 1
        else:
            incorrect_count += 1

    conn.close()

    # Factor weight update from real active_signals only (Phase-2 rows)
    total_evaluated = [
        i for i in ledger
        if i.get("status") == "EVALUATED" and i.get("timeframe") != "historical_bootstrap"
    ]
    if total_evaluated:
        wins = [i for i in total_evaluated if i["actual_outcome"] == "CORRECT"]
        n_total = len(total_evaluated)
        k_wins = len(wins)
        raw_win_rate = (k_wins / n_total) * 100.0
        p_hat = k_wins / n_total

        z = 1.96
        denom = 1.0 + (z ** 2) / n_total
        center = (p_hat + (z ** 2) / (2 * n_total)) / denom
        half_width = (z * math.sqrt((p_hat * (1 - p_hat) + (z ** 2) / (4 * n_total)) / n_total)) / denom
        ci_lower = round(max(0.0, (center - half_width)) * 100.0, 1)
        ci_upper = round(min(1.0, (center + half_width)) * 100.0, 1)

        excesses = [float(i.get("net_excess_pct") or 0.0) for i in total_evaluated]
        mean_excess = sum(excesses) / len(excesses)

        # Shrink factor weights toward 0.5 prior mean hit-rate (neutral 1.0x weight)
        # Prior Beta(2,2) → mean 0.5; weaker than retracted Beta(12,8)@60%
        factors_map = {
            "debt_npl_weight": "debt_clean",
            "valuation_mos_weight": "valuation_mos_positive",
            "rsi_momentum_weight": "rsi_oversold_triggered",
            "smart_money_weight": "smart_money_active",
        }
        prior_a, prior_b = 2.0, 2.0
        prior_mean = 0.5
        lr = float(weights.get("learning_rate", 0.02))

        for w_key, sig_key in factors_map.items():
            factor_preds = [
                i for i in total_evaluated
                if i.get("active_signals", {}).get(sig_key)
            ]
            n_f = len(factor_preds)
            k_f = sum(1 for i in factor_preds if i["actual_outcome"] == "CORRECT")
            if n_f >= 15:
                shrunk_p = (k_f + prior_a) / (n_f + prior_a + prior_b)
                target_w = max(0.0, min(1.40, shrunk_p / prior_mean))
                # Floor at 0: negative-IC factors can shut off
                old_w = float(weights.get(w_key, 1.0))
                weights[w_key] = round((1.0 - lr) * old_w + lr * target_w, 3)
            # else keep prior

        # Brier on reported probs (only meaningful if probs vary)
        brier_sum = 0.0
        for item in total_evaluated:
            prob = float(item.get("confidence_prob_pct", 50.0)) / 100.0
            actual = 1.0 if item.get("actual_outcome") == "CORRECT" else 0.0
            brier_sum += (prob - actual) ** 2
        brier_score = round(brier_sum / n_total, 4)

        weights["overall_accuracy_pct"] = round(raw_win_rate, 1)
        weights["accuracy_ci_95"] = f"[{ci_lower}% – {ci_upper}%]"
        weights["mean_net_excess_pct"] = round(mean_excess, 3)
        weights["net_expectancy_pct"] = round(mean_excess, 3)
        weights["total_training_cycles"] = n_total
        weights["brier_score"] = brier_score
        weights["horizon_bars"] = horizon
        weights["round_trip_cost_pct"] = ROUND_TRIP_COST_PCT

    save_ledger(ledger)
    save_weights(weights)
    generate_learning_report()
    return {
        "evaluated_in_run": evaluated_count,
        "correct": correct_count,
        "incorrect": incorrect_count,
        "lifetime_accuracy_pct": weights.get("overall_accuracy_pct"),
        "ci_95": weights.get("accuracy_ci_95"),
        "mean_net_excess_pct": weights.get("mean_net_excess_pct"),
        "label": DEFAULT_WEIGHTS["label_definition"],
    }


def bootstrap_historical_learning(sample_size: int = 50):
    """DISABLED in Phase 2 — lookahead contaminated. Kept as hard refuse."""
    log.error(
        "bootstrap_historical_learning DISABLED. "
        "Epoch-1 bootstrap used static 2026 fundamentals on 2025 dates. "
        "Use live forward predictions + evaluate_pending_predictions only."
    )
    return {"disabled": True, "reason": "lookahead_leak"}


def generate_learning_report():
    ledger = load_ledger()
    weights = load_weights()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORT_DIR / "prediction_accuracy_evaluation.md"

    evaluated = [
        i for i in ledger
        if i.get("status") == "EVALUATED" and i.get("timeframe") != "historical_bootstrap"
    ]
    wins = [i for i in evaluated if i.get("actual_outcome") == "CORRECT"]
    losses = [i for i in evaluated if i.get("actual_outcome") == "INCORRECT"]
    win_rate = round(len(wins) / len(evaluated) * 100, 1) if evaluated else 0.0

    lines = [
        "# DSE Phase-2 Learning Audit (Net Excess vs EQW)",
        f"**Audit Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Model:** `{MODEL_ID}`",
        f"**Label:** `{DEFAULT_WEIGHTS['label_definition']}`",
        "",
        "---",
        "## 1. Performance",
        f"- Evaluated closed calls: **{len(evaluated)}**",
        f"- Hit rate (net excess sign): **{win_rate}%** CI {weights.get('accuracy_ci_95', 'n/a')}",
        f"- Mean net excess: **{weights.get('mean_net_excess_pct', 'n/a')}%**",
        f"- Round-trip cost charged: **{ROUND_TRIP_COST_PCT}%**",
        f"- Horizon: **{weights.get('horizon_bars', DEFAULT_HORIZON_BARS)}** trading bars",
        f"- Brier: **{weights.get('brier_score', 'n/a')}**",
        "",
        "## 2. Factor Weights (Beta[2,2] prior @ 50%, floor 0)",
        f"| Factor | Weight |",
        f"|---|---|",
        f"| debt_npl_weight | {weights.get('debt_npl_weight', 1.0)} |",
        f"| valuation_mos_weight | {weights.get('valuation_mos_weight', 1.0)} |",
        f"| rsi_momentum_weight | {weights.get('rsi_momentum_weight', 1.0)} |",
        f"| smart_money_weight | {weights.get('smart_money_weight', 1.0)} |",
        "",
        "## 3. Recent Mistakes",
        "",
    ]
    if losses:
        for item in losses[:8]:
            lines.append(
                f"- `{item['ticker']}` {item['date']} {item['predicted_direction']}: "
                f"{item.get('mistake_analysis')}"
            )
    else:
        lines.append("> No evaluated losses yet (ledger fresh after Epoch-1 archive).")

    lines.append("")
    lines.append("## 4. Wins")
    for item in wins[:6]:
        lines.append(
            f"- `{item['ticker']}` {item['date']}: net_excess={item.get('net_excess_pct')}%"
        )

    lines.append("")
    lines.append("---")
    lines.append("Epoch-1 archive: `data/learning/prediction_ledger_epoch1_invalid.json` (do not train).")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info(f"Learning report -> {md_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        bootstrap_historical_learning()
    elif len(sys.argv) > 1 and sys.argv[1] == "archive":
        print(archive_epoch1_invalid(force=True))
    elif len(sys.argv) > 1 and sys.argv[1] == "evaluate":
        archive_epoch1_invalid()
        print(evaluate_pending_predictions())
    else:
        archive_epoch1_invalid()
        print(evaluate_pending_predictions())
        generate_learning_report()
