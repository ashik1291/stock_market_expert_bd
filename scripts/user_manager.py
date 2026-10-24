"""
DSE Multi-User Isolation & Preferences Management Engine.

Enforces strict separation between Core Quantitative System Assets and User-Specific Preferences:
  - Core System Files (IMMUTABLE via User Personalization):
      * scripts/unified_score.py, scripts/feature_store.py, scripts/model_registry.py
      * config/thresholds.json, config/disclosure_lag.json, config/halal_policy.json
      * data/processed/dse.db, data/portfolio/forward_test_ledger_v2.json
  - User Personalization Files (ISOLATED per user_id):
      * data/users/<user_id>/profile.json
      * data/users/<user_id>/portfolio.json
      * data/users/<user_id>/position_plan.md
      * data/users/<user_id>/trade_ledger.jsonl
"""

from __future__ import annotations

import sys
import json
import shutil
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
USERS_DIR = BASE_DIR / "data" / "users"
LEGACY_PORTFOLIO = BASE_DIR / "data" / "portfolio" / "portfolio.json"
LEGACY_PROFILE = BASE_DIR / "config" / "profile.json"

DEFAULT_USER_ID = "default_user"
VALID_RISK_PROFILES = {"conservative", "moderate", "aggressive"}
VALID_HORIZONS = {"short_term", "mid_term", "long_term", "multi_horizon"}
VALID_HALAL_TIERS = {"strict", "flexible", "off"}
VALID_LANGUAGES = {"banglish", "bengali", "english"}


def get_user_dir(user_id: str = DEFAULT_USER_ID) -> Path:
    """Returns directory path for specified user and ensures existence."""
    uid = str(user_id or DEFAULT_USER_ID).strip().lower().replace(" ", "_")
    p = USERS_DIR / uid
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_default_profile(user_id: str = DEFAULT_USER_ID) -> dict:
    """Generates standard default preferences for a new investor."""
    return {
        "user_id": user_id,
        "name": user_id.replace("_", " ").title(),
        "language": "banglish",
        "investment_horizon": "long_term",
        "risk_tolerance": "moderate",
        "halal_tier": "flexible",
        "target_annual_return_pct": 20.0,
        "max_single_stock_pct": 25.0,
        "custom_exclusions": {
            "sectors": [],
            "tickers": []
        },
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }


def get_default_portfolio(user_id: str = DEFAULT_USER_ID) -> dict:
    """Default starting portfolio state."""
    # If legacy portfolio exists and requesting default_user, initialize from legacy
    if user_id == DEFAULT_USER_ID and LEGACY_PORTFOLIO.exists():
        try:
            with open(LEGACY_PORTFOLIO, encoding="utf-8") as f:
                legacy = json.load(f)
            legacy["user_id"] = user_id
            return legacy
        except Exception:
            pass

    return {
        "user_id": user_id,
        "total_capital_bdt": 50000.0,
        "cash_balance_bdt": 50000.0,
        "mutual_funds": [],
        "holdings": [],
        "trade_history": [],
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }


def load_user_profile(user_id: str = DEFAULT_USER_ID) -> dict:
    """Loads user preferences from isolated user profile file."""
    user_dir = get_user_dir(user_id)
    profile_path = user_dir / "profile.json"

    if profile_path.exists():
        try:
            with open(profile_path, encoding="utf-8") as f:
                prof = json.load(f)
            # Fill missing keys if any
            default = get_default_profile(user_id)
            for k, v in default.items():
                if k not in prof:
                    prof[k] = v
            return prof
        except Exception:
            pass

    # If legacy profile exists for default_user, import it
    if user_id == DEFAULT_USER_ID and LEGACY_PROFILE.exists():
        try:
            with open(LEGACY_PROFILE, encoding="utf-8") as f:
                leg = json.load(f)
            prof = get_default_profile(user_id)
            prof["halal_tier"] = leg.get("halal_tier", "flexible")
            prof["custom_exclusions"] = leg.get("custom_exclusions", {"sectors": [], "tickers": []})
            save_user_profile(user_id, prof)
            return prof
        except Exception:
            pass

    # Initialize default
    prof = get_default_profile(user_id)
    save_user_profile(user_id, prof)
    return prof


def save_user_profile(user_id: str, profile: dict) -> None:
    """Saves validated preferences strictly in user's isolated directory."""
    user_dir = get_user_dir(user_id)
    profile_path = user_dir / "profile.json"

    # Validation
    tier = profile.get("halal_tier", "flexible")
    if tier not in VALID_HALAL_TIERS:
        tier = "flexible"
    profile["halal_tier"] = tier

    risk = profile.get("risk_tolerance", "moderate")
    if risk not in VALID_RISK_PROFILES:
        risk = "moderate"
    profile["risk_tolerance"] = risk

    horizon = profile.get("investment_horizon", "long_term")
    if horizon not in VALID_HORIZONS:
        horizon = "long_term"
    profile["investment_horizon"] = horizon

    lang = profile.get("language", "banglish")
    if lang not in VALID_LANGUAGES:
        lang = "banglish"
    profile["language"] = lang

    profile["updated_at"] = datetime.datetime.utcnow().isoformat()

    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def load_user_portfolio(user_id: str = DEFAULT_USER_ID) -> dict:
    """Loads user's holdings from isolated directory."""
    user_dir = get_user_dir(user_id)
    portfolio_path = user_dir / "portfolio.json"

    if portfolio_path.exists():
        try:
            with open(portfolio_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Fallback to default
    port = get_default_portfolio(user_id)
    save_user_portfolio(user_id, port)
    return port


def save_user_portfolio(user_id: str, portfolio: dict) -> None:
    """Saves user's portfolio state into user directory."""
    user_dir = get_user_dir(user_id)
    portfolio_path = user_dir / "portfolio.json"
    portfolio["user_id"] = user_id
    portfolio["updated_at"] = datetime.datetime.utcnow().isoformat()

    with open(portfolio_path, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)

    # If default user, also sync to legacy portfolio path for backward compatibility
    if user_id == DEFAULT_USER_ID:
        try:
            with open(LEGACY_PORTFOLIO, "w", encoding="utf-8") as f:
                json.dump(portfolio, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


def set_user_language(user_id: str = DEFAULT_USER_ID, language: str = "banglish") -> dict:
    """Updates language preference for the user (banglish, bengali, english)."""
    prof = load_user_profile(user_id)
    lang = language.strip().lower()
    if lang in VALID_LANGUAGES:
        prof["language"] = lang
        save_user_profile(user_id, prof)
    return prof

def list_users() -> list[str]:
    """Returns list of all active user IDs."""
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    users = [d.name for d in USERS_DIR.iterdir() if d.is_dir()]
    if DEFAULT_USER_ID not in users:
        users.insert(0, DEFAULT_USER_ID)
    return sorted(users)


def create_user(
    user_id: str,
    name: str = "",
    risk_tolerance: str = "moderate",
    investment_horizon: str = "long_term",
    halal_tier: str = "flexible",
    initial_capital_bdt: float = 50000.0,
    language: str = "banglish"
) -> dict:
    """Initializes a new isolated user workspace."""
    uid = str(user_id).strip().lower().replace(" ", "_")
    profile = get_default_profile(uid)
    profile["name"] = name or uid.replace("_", " ").title()
    profile["risk_tolerance"] = risk_tolerance if risk_tolerance in VALID_RISK_PROFILES else "moderate"
    profile["investment_horizon"] = investment_horizon if investment_horizon in VALID_HORIZONS else "long_term"
    profile["halal_tier"] = halal_tier if halal_tier in VALID_HALAL_TIERS else "flexible"
    profile["language"] = language if language in VALID_LANGUAGES else "banglish"

    save_user_profile(uid, profile)

    portfolio = {
        "user_id": uid,
        "total_capital_bdt": float(initial_capital_bdt),
        "cash_balance_bdt": float(initial_capital_bdt),
        "mutual_funds": [],
        "holdings": [],
        "trade_history": [],
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }
    save_user_portfolio(uid, portfolio)

    return {"profile": profile, "portfolio": portfolio}


if __name__ == "__main__":
    # Test initialize default_user
    u = load_user_profile(DEFAULT_USER_ID)
    p = load_user_portfolio(DEFAULT_USER_ID)
    print(f"[USER MANAGER] Verified user: '{DEFAULT_USER_ID}' | Risk: {u['risk_tolerance']} | Capital: ৳{p.get('total_capital_bdt', 0):,.2f}")
    print(f"[USER MANAGER] Active Users: {list_users()}")
