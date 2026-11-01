"""
scripts/dse_circuit_breaker.py
------------------------------
Canonical DSE Tiered Circuit Breaker and Price Movement Limit Engine.
Implements official BSEC Directive No. BSEC/CMRRCD/2001-07/148:
  - Up to ৳100:       ±10.0%
  - ৳100.01 to ৳200:  ±8.75%
  - ৳200.01 to ৳500:  ±7.50%
  - ৳500.01 to ৳1000: ±6.25%
  - ৳1001 to ৳2000:   ±5.00%
  - ৳2001 to ৳5000:   ±3.75%
  - Above ৳5000:      ±2.00%

Provides:
- get_dse_circuit_limit_pct(price)
- get_lower_circuit_floor(prev_close)
- get_upper_circuit_ceiling(prev_close)
- is_price_circuit_locked(current_price, prev_close, tolerance_pct=0.3)
"""

from __future__ import annotations


import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_dse_circuit_limit_pct(price: float) -> float:
    """
    Returns official DSE daily maximum price movement % based on BSEC tiers.
    """
    if price <= 0:
        return 10.0
    elif price <= 100.0:
        return 10.0
    elif price <= 200.0:
        return 8.75
    elif price <= 500.0:
        return 7.50
    elif price <= 1000.0:
        return 6.25
    elif price <= 2000.0:
        return 5.00
    elif price <= 5000.0:
        return 3.75
    else:
        return 2.00


def get_lower_circuit_floor(prev_close: float) -> float:
    """Computes exact lower circuit floor price on DSE."""
    if prev_close <= 0:
        return 0.0
    limit_pct = get_dse_circuit_limit_pct(prev_close)
    return round(prev_close * (1.0 - (limit_pct / 100.0)), 1)


def get_upper_circuit_ceiling(prev_close: float) -> float:
    """Computes exact upper circuit ceiling price on DSE."""
    if prev_close <= 0:
        return 0.0
    limit_pct = get_dse_circuit_limit_pct(prev_close)
    return round(prev_close * (1.0 + (limit_pct / 100.0)), 1)


def is_price_circuit_locked(
    current_price: float,
    prev_close: float,
    tolerance_pct: float = 0.4
) -> dict:
    """
    Detects whether a price is currently clamped at upper or lower circuit limit.
    tolerance_pct: buffer within which an order book is practically frozen (zero bids/asks).
    """
    if prev_close <= 0 or current_price <= 0:
        return {"locked": False, "side": "NONE", "limit_pct": 10.0}

    limit_pct = get_dse_circuit_limit_pct(prev_close)
    lower_floor = get_lower_circuit_floor(prev_close)
    upper_ceiling = get_upper_circuit_ceiling(prev_close)

    # Lower circuit check (Price within tolerance of floor)
    if current_price <= lower_floor * (1.0 + (tolerance_pct / 100.0)):
        return {
            "locked": True,
            "side": "LOWER",
            "limit_pct": limit_pct,
            "floor_price": lower_floor,
            "ceiling_price": upper_ceiling,
            "warning": f"LOWER_CIRCUIT_LOCKED (-{limit_pct}% floor: ৳{lower_floor}): Zero bids expected; sell orders queue with high slippage"
        }

    # Upper circuit check (Price within tolerance of ceiling)
    if current_price >= upper_ceiling * (1.0 - (tolerance_pct / 100.0)):
        return {
            "locked": True,
            "side": "UPPER",
            "limit_pct": limit_pct,
            "floor_price": lower_floor,
            "ceiling_price": upper_ceiling,
            "warning": f"UPPER_CIRCUIT_CLAMPED (+{limit_pct}% ceiling: ৳{upper_ceiling}): Zero asks expected; chasing triggers pump-trap risk"
        }

    return {
        "locked": False,
        "side": "NONE",
        "limit_pct": limit_pct,
        "floor_price": lower_floor,
        "ceiling_price": upper_ceiling,
        "warning": None
    }
