"""
Phase 4 weekly drift report:
  - Factor IC (from factor_ic_weights + shadow log)
  - Portfolio turnover proxy (ledger last_trades)
  - Hit rate by conviction tier (prediction ledger)
  - Calibration curve stub (platt / bins when labels exist)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LEARN_DIR = BASE_DIR / "data" / "learning"
PORT_DIR = BASE_DIR / "data" / "portfolio"
REPORT_DIR = BASE_DIR / "reports" / "drift"
IC_WEIGHTS = LEARN_DIR / "factor_ic_weights.json"
SHADOW_IC = PORT_DIR / "shadow_model_ic.jsonl"
LEDGER = PORT_DIR / "forward_test_ledger_v2.json"
PRED_LEDGER = LEARN_DIR / "prediction_ledger.json"
REGISTRY = LEARN_DIR / "model_registry.json"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))


def _load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def build_weekly_drift_report() -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    ic = _load_json(IC_WEIGHTS, {})
    reg = _load_json(REGISTRY, {})
    led = _load_json(LEDGER, {})
    preds = _load_json(PRED_LEDGER, []) or []

    # Shadow IC series by model
    shadow_series = defaultdict(list)
    if SHADOW_IC.exists():
        for line in SHADOW_IC.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            for mid, m in (o.get("models") or {}).items():
                if m.get("rank_ic") is not None:
                    shadow_series[mid].append({"date": o.get("date"), "ic": m["rank_ic"]})

    # Turnover from recent ledger trades
    trades = []
    blocks = led.get("blocks") or []
    for b in blocks[-10:]:
        for t in (b.get("data") or {}).get("last_trades") or []:
            if t.get("action") in ("BUY", "SELL"):
                trades.append(t)
    sells = sum(1 for t in trades if t.get("action") == "SELL")
    buys = sum(1 for t in trades if t.get("action") == "BUY")
    latest = (blocks[-1].get("data") if blocks else {}) or {}
    n_pos = len(latest.get("positions") or [])
    turnover_proxy = round((sells + buys) / max(n_pos, 1), 3)

    # Hit rate by tier (if predictions carry conviction_tier — else by score tercile)
    evaluated = [
        p for p in preds
        if p.get("status") == "EVALUATED" and p.get("timeframe") != "historical_bootstrap"
    ]
    tier_stats = {}
    if evaluated:
        # Approximate tiers from score percentile among evaluated
        scores = sorted([float(p["score"]) for p in evaluated if p.get("score") is not None])
        def tier_of(sc):
            if sc is None or not scores:
                return "UNK"
            # percentile
            below = sum(1 for s in scores if s <= sc)
            pct = below / len(scores)
            if pct >= 0.80:
                return "HIGH"
            if pct >= 0.50:
                return "MED"
            return "LOW"

        buckets = defaultdict(lambda: {"n": 0, "wins": 0})
        for p in evaluated:
            t = tier_of(p.get("score"))
            buckets[t]["n"] += 1
            if p.get("actual_outcome") in ("CORRECT", "CORRECT_PROFIT"):
                buckets[t]["wins"] += 1
        for t, b in buckets.items():
            tier_stats[t] = {
                "n": b["n"],
                "hit_rate_pct": round(100.0 * b["wins"] / b["n"], 1) if b["n"] else None,
            }

    # Calibration bins
    calib_bins = {"50-65": {"n": 0, "wins": 0}, "65-80": {"n": 0, "wins": 0}, "80-100": {"n": 0, "wins": 0}}
    for p in evaluated:
        prob = float(p.get("confidence_prob_pct") or 50)
        win = 1 if p.get("actual_outcome") in ("CORRECT", "CORRECT_PROFIT") else 0
        if prob < 65:
            k = "50-65"
        elif prob < 80:
            k = "65-80"
        else:
            k = "80-100"
        calib_bins[k]["n"] += 1
        calib_bins[k]["wins"] += win
    for k, b in calib_bins.items():
        b["observed_hit_pct"] = round(100.0 * b["wins"] / b["n"], 1) if b["n"] else None

    report = {
        "generated_at": datetime.now().isoformat(),
        "week_of": today,
        "champion": (reg.get("champion") or {}).get("model_id"),
        "champion_hash": (reg.get("champion") or {}).get("parameter_hash"),
        "challengers": [c.get("model_id") for c in (reg.get("challengers") or [])],
        "trial_count": reg.get("trial_count"),
        "factor_ic_weights": (ic.get("weights") or {}),
        "factor_ic_stats": (ic.get("stats") or {}),
        "shadow_ic_tail": {
            mid: series[-5:] for mid, series in shadow_series.items()
        },
        "turnover": {
            "recent_buys": buys,
            "recent_sells": sells,
            "positions": n_pos,
            "turnover_proxy": turnover_proxy,
            "note": "proxy = (buys+sells)/n_pos over last ~10 blocks",
        },
        "hit_rate_by_tier": tier_stats,
        "calibration_bins": calib_bins,
        "portfolio": {
            "nav": latest.get("portfolio_nav"),
            "excess_vs_eqw_pct": latest.get("excess_vs_eqw_pct"),
            "max_drawdown_pct": latest.get("max_drawdown_pct"),
            "strategy_status": latest.get("strategy_status"),
            "asof": latest.get("asof_price_date"),
        },
        "evaluated_labels": len(evaluated),
    }

    json_path = REPORT_DIR / f"{today}_drift.json"
    md_path = REPORT_DIR / f"{today}_drift.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"# Weekly Drift Report — {today}",
        f"**Champion**: `{report['champion']}` (`{report['champion_hash']}`)",
        f"**Challengers**: {', '.join(f'`{c}`' for c in report['challengers']) or 'none'}",
        f"**Trial count (Holm m)**: {report['trial_count']}",
        "",
        "## Factor IC Weights",
        "| Factor | Weight | EMA IC | t_NW |",
        "|---|---|---|---|",
    ]
    stats = report["factor_ic_stats"]
    for k, w in (report["factor_ic_weights"] or {}).items():
        s = stats.get(k) or {}
        lines.append(f"| {k} | {w} | {s.get('ema_ic')} | {s.get('t_nw')} |")

    lines += [
        "",
        "## Shadow Rank IC (last 5)",
    ]
    for mid, series in report["shadow_ic_tail"].items():
        lines.append(f"- `{mid}`: " + ", ".join(f"{x['date']}={x['ic']:+.3f}" for x in series))

    lines += [
        "",
        "## Turnover Proxy",
        f"- Buys={buys} Sells={sells} Positions={n_pos} -> proxy={turnover_proxy}",
        "",
        "## Hit Rate by Tier",
        "| Tier | N | Hit % |",
        "|---|---|---|",
    ]
    for t, b in sorted(tier_stats.items()):
        lines.append(f"| {t} | {b['n']} | {b['hit_rate_pct']} |")

    lines += [
        "",
        "## Calibration Bins (reported prob)",
        "| Bin | N | Observed Hit % |",
        "|---|---|---|",
    ]
    for k, b in calib_bins.items():
        lines.append(f"| {k} | {b['n']} | {b['observed_hit_pct']} |")

    lines += [
        "",
        "## Portfolio",
        f"- NAV={latest.get('portfolio_nav')} excess={latest.get('excess_vs_eqw_pct')}% "
        f"dd={latest.get('max_drawdown_pct')}% status={latest.get('strategy_status')}",
        f"- Evaluated Phase-2 labels: {len(evaluated)}",
        "",
        "> Promote challenger only via `python scripts/model_registry.py promote` after Holm gate.",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[DRIFT] wrote {md_path}")
    # ASCII-safe console summary
    print(f"[DRIFT] champion={report.get('champion')} turnover_proxy={turnover_proxy} labels={len(evaluated)}")
    return report


if __name__ == "__main__":
    build_weekly_drift_report()
