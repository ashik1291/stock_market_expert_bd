"""
Single served-model score used by feature store, forward ledger, and scanners.

Model id: frozen_epoch2_pit_v2
Parameter Hash: acf502bc65914c48 (SHA-256 of 'pit_dividend_pe_rsi_sector_capped_v2'[:16])
Frozen Epoch 2 Contract:
  Gates (hard): non-bank D/E > 1.0 OR pe<=0 OR pe>25 → ineligible (score=-999)
  Score (eligible): Fundamentals dominant, RSI zero-weighted (empirical audit gross decile t=+0.26, no tradable alpha).
    w_div = 1.0   -> f_div = div_yield * 2.0
    w_value = 1.0 -> f_pe = max(0, 18 - pe) * 1.5
    w_debt = 0.0  -> hard gate only (no additive score distortion)
    w_rsi = 0.0   -> zero-weighted per Epoch 2 freeze protocol
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

MODEL_ID = "frozen_epoch2_pit_v2"
CANONICAL_SPEC = "pit_dividend_pe_rsi_sector_capped_v2"
FROZEN_PARAMETER_HASH = hashlib.sha256(CANONICAL_SPEC.encode("utf-8")).hexdigest()[:16]  # "acf502bc65914c48"
ROUND_TRIP_COST_PCT = 0.833
DEFAULT_HORIZON_BARS = 21

# Frozen Epoch 2 weights: strictly locked; dynamic IC calibration moved to offline shadow mode
FROZEN_FACTOR_WEIGHTS = {
    "div": 1.0,
    "value": 1.0,
    "debt": 0.0,
    "rsi": 0.0,
}

CANONICAL_SERVED_PARAMS = {
    "epoch": "EPOCH-2-LIVE-PROSPECTIVE-2026",
    "factor_weights": FROZEN_FACTOR_WEIGHTS,
    "gates": {
        "nonbank_debt_equity_max": 1.0,
        "pe_max": 25.0,
        "pe_min": 0.001,
    },
    "model_id": MODEL_ID,
    "portfolio_rules": {
        "execution_fill": "NEXT_SESSION_OPEN_PLUS_10BPS",
        "max_sector_weight_pct": 20.0,
        # NOTE (N3 concentration): single-name cap is 10% at scoring/portfolio_rules level;
        # execution layer (forward_test_ledger_v2 INITIAL_CAPITAL/TARGET_POSITIONS) already
        # enforces ~10% per position. Expert guidance (N2/N3) recommends relaxing the cap to
        # 20–25% when weighted by margin-of-safety (MoS) — i.e., cap = min(20–25%, MoS-scaled)
        # to let deep-value names with large MoS (low pe, high cover) take larger weights
        # without over-concentration in shallow value. This is a COMMENT/NOTE ONLY — the
        # active cap remains 10% until PIT dividend/cover completeness justifies the MoS bump.
        "max_single_stock_pct": 10.0,
        "round_trip_fee_pct": ROUND_TRIP_COST_PCT,
    },
    "pre_registration_spec_string": CANONICAL_SPEC,
    "scoring_factors": {
        "balance_sheet_debt": "hard_gate_only",
        "dividend_yield": "div_yield * 2.0",
        "rsi_14": "zero_weighted",
        "value_margin_of_safety": "max(0, 18 - pe) * 1.5",
    },
}

CANONICAL_PARAM_CONTENT_HASH = hashlib.sha256(
    json.dumps(CANONICAL_SERVED_PARAMS, sort_keys=True).encode("utf-8")
).hexdigest()[:16]  # Content hash of the actual served parameter dict: "7b3020aa89457fa0"

_BASE = Path(__file__).resolve().parent.parent


_SHARIAH_EXCLUDED_SECTOR_NAMES = {
    "bank",
    "banking",
    "banks",
    "insurance",
    "life insurance",
    "general insurance",
    "financial institution",
    "financial institutions",
    "mutual fund",
    "mutual funds",
    "tobacco",
}


def is_shariah_excluded_sector(sector: str | None) -> bool:
    """Return True for conventional finance or tobacco sectors."""
    normalized = re.sub(r"[^a-z0-9]+", " ", (sector or "").lower()).strip()
    if normalized in _SHARIAH_EXCLUDED_SECTOR_NAMES:
        return True
    return "bank" in normalized or "insurance" in normalized


def load_factor_weights() -> dict:
    """Return immutable copy of frozen factor weights."""
    return dict(FROZEN_FACTOR_WEIGHTS)


def score_features(
    *,
    pe: float | None,
    debt_equity: float | None,
    dividend_yield: float | None,
    rsi_14: float | None,
    sector: str | None = None,
    close: float | None = None,
    factor_weights: dict | None = None,
    ticker: str | None = None,
    asof_date: str | None = None,
) -> dict:
    """Return score, eligibility, and component breakdown under frozen model or explicit weights."""
    sec = (sector or "Unknown")
    is_excluded_sector = is_shariah_excluded_sector(sec)
    pe_v = float(pe) if pe is not None else None
    de_v = float(debt_equity) if debt_equity is not None else None
    div_v = float(dividend_yield) if dividend_yield is not None else 0.0
    rsi_v = float(rsi_14) if rsi_14 is not None else None
    w = factor_weights or load_factor_weights()

    reasons = []
    eligible = True

    if is_excluded_sector:
        eligible = False
        reasons.append("shariah_excluded_sector")

    if close is not None and close <= 0:
        eligible = False
        reasons.append("bad_price")

    if not is_excluded_sector:
        if de_v is None:
            eligible = False
            reasons.append("missing_debt_equity")
        elif de_v > 0.80:  # Enforce SPEC.md INV-3: Max Debt/Equity <= 0.80
            eligible = False
            reasons.append("debt_gate")

    if pe_v is None:
        eligible = False
        reasons.append("missing_pe_ratio")
    elif pe_v <= 0 or pe_v > 25:
        eligible = False
        reasons.append("pe_gate")

    if ticker:
        try:
            from anti_manipulation_engine import is_ticker_blacklisted
            is_b, _ = is_ticker_blacklisted(ticker, asof_date=asof_date)
            if is_b:
                eligible = False
                reasons.append("manipulation_blacklist")
        except Exception:
            pass

    if not eligible:
        return {
            "model_id": MODEL_ID,
            "parameter_hash": FROZEN_PARAMETER_HASH,
            "score": -999.0,
            "is_eligible": False,
            "gate_reasons": reasons,
            "components": {"div": 0.0, "pe": 0.0, "rsi": 0.0, "debt": 0.0},
            "factor_weights": w,
            "active_signals": {
                "debt_clean": False,
                "valuation_mos_positive": False,
                "rsi_oversold_triggered": False,
            },
        }

    # Raw factor signals (pre-weight)
    f_div = div_v * 2.0
    f_pe = max(0.0, 18.0 - (pe_v if pe_v is not None else 18.0)) * 1.5
    f_rsi = 0.0
    if rsi_v is not None:
        if rsi_v < 35:
            f_rsi = 8.0
        elif rsi_v <= 50:
            f_rsi = 3.0
        elif rsi_v > 70:
            f_rsi = -5.0
    f_debt = 0.0
    if de_v is not None and de_v <= 0.5:
        f_debt = 5.0

    w_div = float(w.get("div", 1.0))
    w_pe = float(w.get("value", 1.0))
    w_rsi = float(w.get("rsi", 0.0))
    w_debt = float(w.get("debt", 0.0))

    c_div = w_div * f_div
    c_pe = w_pe * f_pe
    c_rsi = w_rsi * f_rsi
    c_debt = w_debt * f_debt

    score = round(c_div + c_pe + c_rsi + c_debt, 4)
    return {
        "model_id": MODEL_ID,
        "parameter_hash": FROZEN_PARAMETER_HASH,
        "score": score,
        "is_eligible": True,
        "gate_reasons": [],
        "components": {
            "div": round(c_div, 4),
            "pe": round(c_pe, 4),
            "rsi": round(c_rsi, 4),
            "debt": round(c_debt, 4),
        },
        "factor_weights": {
            "div": w_div,
            "value": w_pe,
            "rsi": w_rsi,
            "debt": w_debt,
        },
        "active_signals": {
            "debt_clean": (
                not is_excluded_sector
                and de_v is not None
                and de_v <= 0.5
            ),
            "valuation_mos_positive": pe_v is not None and pe_v <= 15.0,
            "rsi_oversold_triggered": rsi_v is not None and rsi_v < 35.0,
        },
    }
