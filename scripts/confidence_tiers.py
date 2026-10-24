"""
Phase 3 conviction tiers. No fake probabilities until >=200 evaluated Phase-2 labels.

Until calibration sample ready: HIGH / MED / LOW from score percentile among eligible.
After 200: optional Platt logistic on (score → hit); still emit tier + calibrated_p.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LEARN_DIR = BASE_DIR / "data" / "learning"
LEDGER_PATH = LEARN_DIR / "prediction_ledger.json"
CALIB_PATH = LEARN_DIR / "platt_calibration.json"

MIN_OBS_FOR_PROB = 200


def count_evaluated_labels() -> int:
    if not LEDGER_PATH.exists():
        return 0
    try:
        ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    return sum(
        1
        for i in ledger
        if i.get("status") == "EVALUATED" and i.get("timeframe") != "historical_bootstrap"
    )


def tier_from_percentile(pct: float) -> str:
    """pct in [0,1] where 1 = best (highest score)."""
    if pct >= 0.80:
        return "HIGH"
    if pct >= 0.50:
        return "MED"
    return "LOW"


def score_to_tier(score: float, eligible_scores: list[float]) -> dict:
    """Map absolute score to tier via cross-sectional percentile."""
    elig = [s for s in eligible_scores if s is not None and s > -900]
    if not elig or score is None or score <= -900:
        return {
            "tier": "LOW",
            "percentile": None,
            "show_probability": False,
            "probability_pct": None,
            "n_eval_labels": count_evaluated_labels(),
            "note": "ineligible_or_empty",
        }

    # percentile: fraction of eligible with score <= this score
    below = sum(1 for s in elig if s <= score)
    pct = below / len(elig)
    n = count_evaluated_labels()
    tier = tier_from_percentile(pct)
    show_p = n >= MIN_OBS_FOR_PROB
    prob = None
    if show_p:
        prob = platt_predict(score)

    return {
        "tier": tier,
        "percentile": round(pct, 3),
        "show_probability": show_p,
        "probability_pct": prob,
        "n_eval_labels": n,
        "note": "calibrated" if show_p else f"tier_only_until_{MIN_OBS_FOR_PROB}_labels",
    }


def platt_fit(scores: list[float], labels: list[int]) -> dict:
    """
    Simple 1D Platt: P = 1/(1+exp(a*score+b)).
    Newton steps on logistic NLL. Needs >= MIN_OBS_FOR_PROB.
    """
    if len(scores) < MIN_OBS_FOR_PROB:
        return {"ok": False, "reason": f"need>={MIN_OBS_FOR_PROB}", "a": 0.0, "b": 0.0}

    a, b = -0.05, 0.0
    for _ in range(40):
        g_a = g_b = 0.0
        h_aa = h_ab = h_bb = 0.0
        for s, y in zip(scores, labels):
            z = a * s + b
            # stable sigmoid
            if z >= 0:
                p = 1.0 / (1.0 + math.exp(-z))
            else:
                ez = math.exp(z)
                p = ez / (1.0 + ez)
            g_a += (p - y) * s
            g_b += (p - y)
            w = p * (1.0 - p)
            h_aa += w * s * s
            h_ab += w * s
            h_bb += w
        # Damped Newton
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        da = (h_bb * g_a - h_ab * g_b) / det
        db = (-h_ab * g_a + h_aa * g_b) / det
        a -= 0.5 * da
        b -= 0.5 * db

    out = {"ok": True, "a": round(a, 6), "b": round(b, 6), "n": len(scores)}
    CALIB_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def platt_predict(score: float) -> float | None:
    if not CALIB_PATH.exists():
        return None
    try:
        cal = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
        if not cal.get("ok"):
            return None
        z = cal["a"] * score + cal["b"]
        if z >= 0:
            p = 1.0 / (1.0 + math.exp(-z))
        else:
            ez = math.exp(z)
            p = ez / (1.0 + ez)
        return round(p * 100.0, 1)
    except Exception:
        return None


def maybe_refit_platt_from_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {"ok": False, "reason": "no ledger"}
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    scores, labels = [], []
    for i in ledger:
        if i.get("status") != "EVALUATED":
            continue
        if i.get("timeframe") == "historical_bootstrap":
            continue
        if i.get("score") is None:
            continue
        scores.append(float(i["score"]))
        labels.append(1 if i.get("actual_outcome") == "CORRECT" else 0)
    return platt_fit(scores, labels)
