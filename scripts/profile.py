"""
User profile loader — halal_tier + additive-only custom_exclusions.

Schema:
  {
    halal_tier: "strict" | "flexible" | "off",
    configured: bool,
    custom_exclusions: { sectors: string[], tickers: string[] }
  }

Rules:
  - load_profile() defaults to off (regular stock) if file missing/invalid.
  - validate_profile(): additive-only strictness — custom_exclusions can only
    *add* exclusions, never relax L1/L2/L5 gates. Validator rejects anything
    that tries to re-enable a blocked ticker/sector.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROFILE_PATH = BASE / "config" / "profile.json"
POLICY_PATH = BASE / "config" / "halal_policy.json"

VALID_TIERS = {"strict", "flexible", "off"}


def validate_profile(data: dict) -> dict:
    """Validate and normalize profile; additive-only custom_exclusions."""
    if not isinstance(data, dict):
        raise ValueError("profile must be object")
    tier = data.get("halal_tier", "flexible")
    if tier not in VALID_TIERS:
        raise ValueError(f"halal_tier must be one of {sorted(VALID_TIERS)}, got {tier!r}")
    ce = data.get("custom_exclusions", {})
    if not isinstance(ce, dict):
        raise ValueError("custom_exclusions must be object")
    sectors = ce.get("sectors", [])
    tickers = ce.get("tickers", [])
    if not isinstance(sectors, list) or not isinstance(tickers, list):
        raise ValueError("custom_exclusions.sectors/tickers must be lists")
    # Normalize to upper for tickers, title-case stripped for sectors
    norm_sectors = []
    for s in sectors:
        if not isinstance(s, str) or not s.strip():
            raise ValueError(f"invalid sector entry: {s!r}")
        norm_sectors.append(s.strip())
    norm_tickers = []
    for t in tickers:
        if not isinstance(t, str) or not t.strip():
            raise ValueError(f"invalid ticker entry: {t!r}")
        norm_tickers.append(t.strip().upper())
    # Additive-only: custom_exclusions cannot contain magic relax keys
    for t in norm_tickers:
        if t.startswith("!") or t.startswith("-"):
            raise ValueError(f"additive-only: custom_exclusions.tickers cannot relax: {t!r}")
    for s in norm_sectors:
        if s.startswith("!") or s.startswith("-"):
            raise ValueError(f"additive-only: custom_exclusions.sectors cannot relax: {s!r}")
    configured = bool(data.get("configured", False))
    return {
        "halal_tier": tier,
        "configured": configured,
        "custom_exclusions": {"sectors": norm_sectors, "tickers": norm_tickers},
    }


def load_profile() -> dict:
    """Load profile.json; default flexible if missing/unreadable."""
    try:
        if PROFILE_PATH.exists():
            with open(PROFILE_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            return validate_profile(raw)
    except Exception:
        pass
    return {"halal_tier": "flexible", "configured": False, "custom_exclusions": {"sectors": [], "tickers": []}}


def save_profile(profile: dict) -> None:
    validated = validate_profile(profile)
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(validated, f, indent=2, ensure_ascii=False)
    try:
        from pathlib import Path as _P
        # no cache to invalidate
        pass
    except Exception:
        pass
