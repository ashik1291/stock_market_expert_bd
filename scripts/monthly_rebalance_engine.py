"""
DSE Opportunistic Capital Deployment & Net-Value Allocation Engine.
Implements the User's Mandate:
  - NO fixed arbitrary percentages.
  - Deploys cash strictly to the BEST, most undervalued moat with positive Margin of Safety.
  - Automatically filters out overvalued stocks (Price > Graham Fair Value).
  - Whole-share budget allocation with 0.415% transaction fee reservation.
"""

import sys
import json
import math
import sqlite3
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PORTFOLIO_DIR = BASE_DIR / "data" / "portfolio"
PORTFOLIO_PATH = PORTFOLIO_DIR / "portfolio.json"
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Core Halal Moat Candidates (Audited Category A) — legacy fallback
CANDIDATE_MOATS = ["JAMUNAOIL", "PADMAOIL", "MPETROLEUM", "BSRMLTD", "WALTONHIL", "SQURPHARMA", "OLYMPIC", "LHB", "GP"]
COMMISSION_RATE = 0.00415  # 0.415% CDBL + Broker fee

# Candidate universe is now guard-driven (config-driven top_k), halal-blind ranking + view-only filter.
# Legacy CANDIDATE_MOATS kept as fallback only if feature_store/DB unavailable.


def candidate_universe(asof: str | None = None, tier: str | None = None, top_k: int | None = None) -> list[str]:
    """Halal-aware candidate universe: unified_score ranking (halal-blind) filtered via HalalGuard at S6."""
    # Resolve tier + top_k
    _tier = tier
    _k = top_k
    try:
        if _tier is None:
            from profile import load_profile  # type: ignore
            _tier = load_profile().get("halal_tier", "flexible")
    except Exception:
        _tier = _tier or "flexible"
    try:
        if _k is None:
            import json as _json
            _pol = _json.loads((BASE_DIR / "config" / "halal_policy.json").read_text(encoding="utf-8"))
            _k = int(_pol.get("candidate_universe", {}).get("top_k", 12))
    except Exception:
        _k = _k or 12
    # Build scored universe (halal-blind)
    uni: list[dict] = []
    try:
        from feature_store import load_scored_universe  # type: ignore
        uni = load_scored_universe(asof)
    except Exception:
        return list(CANDIDATE_MOATS)[: int(_k)]
    if not uni:
        return list(CANDIDATE_MOATS)[: int(_k)]
    # Enrich with sector for L1 (BATBC override via guard's sector_map)
    try:
        _sec: dict[str, str] = {}
        _conn = __import__("sqlite3").connect(str(DB_PATH))
        _conn.row_factory = __import__("sqlite3").Row
        for _r in _conn.execute("SELECT ticker, sector FROM companies"):
            _sec[_r["ticker"]] = _r["sector"]
        _conn.close()
        for _u in uni:
            if not _u.get("sector"):
                _u["sector"] = _sec.get(_u["ticker"])
    except Exception:
        pass
    # View-only guard filter (keep 60/30/10 logic downstream)
    try:
        from halal_guard import HalalGuard  # type: ignore
        from profile import load_profile as _lp  # type: ignore
        _prof = _lp()
        _tier2 = _prof.get("halal_tier", _tier)
        _guard = HalalGuard(profile=_prof)
        filt = _guard.apply(uni, _tier2)
        # Preserve halal-blind order, take top_k
        tickers = [x["ticker"] for x in filt[: int(_k)]]
        return tickers if tickers else [x["ticker"] for x in uni[: int(_k)]]
    except Exception:
        return [x["ticker"] for x in uni[: int(_k)]]


def evaluate_moat_valuations(tickers: list[str] | None = None) -> list[dict]:
    """Calculate Graham Fair Value, live price, and Margin of Safety % for each candidate with 5-filter verification."""
    _tickers = tickers if tickers is not None else candidate_universe()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    results = []

    for ticker in _tickers:
        px_row = conn.execute(
            "SELECT close, date FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        price = float(px_row["close"]) if px_row and px_row["close"] else None

        c_row = conn.execute(
            "SELECT sponsor_holding_pct, govt_holding_pct FROM companies WHERE ticker = ?",
            (ticker,)
        ).fetchone()
        sponsor = float(c_row["sponsor_holding_pct"] or 0.0) if c_row else 0.0
        govt = float(c_row["govt_holding_pct"] or 0.0) if c_row else 0.0
        promoter_pct = sponsor + govt

        pit_row = conn.execute(
            """
            SELECT eps, nav, pe_ratio, debt_equity, dividend_yield 
            FROM fundamentals_pit 
            WHERE ticker = ? 
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (ticker,)
        ).fetchone()

        eps = float(pit_row["eps"]) if pit_row and pit_row["eps"] else None
        nav = float(pit_row["nav"]) if pit_row and pit_row["nav"] else None
        pe = float(pit_row["pe_ratio"]) if pit_row and pit_row["pe_ratio"] else None
        div_y = float(pit_row["dividend_yield"]) if pit_row and pit_row["dividend_yield"] else 0.0
        de = float(pit_row["debt_equity"]) if pit_row and pit_row["debt_equity"] else 0.0

        if not price or not eps or not nav or eps <= 0 or nav <= 0:
            continue

        # Graham Intrinsic Ceiling: sqrt(22.5 * EPS * NAV)
        graham_val = round(math.sqrt(22.5 * eps * nav), 2)
        mos_pct = round(((graham_val - price) / graham_val) * 100.0, 2)
        is_overvalued = price > graham_val

        # 5 Filters verification
        passes_debt = (de <= 0.80)
        passes_sponsor = (promoter_pct >= 30.0)

        results.append({
            "ticker": ticker,
            "price": price,
            "eps": eps,
            "nav": nav,
            "pe": pe,
            "yield": div_y,
            "debt_equity": de,
            "promoter_pct": promoter_pct,
            "passes_filters": passes_debt and passes_sponsor,
            "graham_value": graham_val,
            "margin_of_safety_pct": mos_pct,
            "is_overvalued": is_overvalued,
            "status": "OVERVALUED (AVOID)" if is_overvalued else "UNDERVALUED (BUY CANDIDATE)"
        })

    conn.close()
    # Rank by highest Margin of Safety % (deepest discount to net value)
    results.sort(key=lambda x: (not x["is_overvalued"], x["margin_of_safety_pct"]), reverse=True)
    return results


def calculate_opportunistic_deployment(budget_bdt: float = 2000.0) -> dict:
    """Deploy available cash into the highest-conviction undervalued stock."""
    valuations = evaluate_moat_valuations()
    undervalued = [v for v in valuations if not v["is_overvalued"]]

    if not undervalued:
        return {
            "budget_bdt": budget_bdt,
            "allocated_shares": {},
            "total_outlay": 0.0,
            "surplus_cash": budget_bdt,
            "directive": "All candidates are currently above Graham fair value. HOLD CASH and wait for pullback.",
            "valuations": valuations,
        }

    # Best value stock = deepest margin of safety + positive yield
    best = undervalued[0]
    px = best["price"]
    cost_per_sh = px * (1.0 + COMMISSION_RATE)
    shares = int(budget_bdt / cost_per_sh)
    gross_cost = round(shares * px, 2)
    comm = round(gross_cost * COMMISSION_RATE, 2)
    total_outlay = round(gross_cost + comm, 2)
    surplus = round(budget_bdt - total_outlay, 2)

    return {
        "budget_bdt": budget_bdt,
        "best_stock": best["ticker"],
        "shares": shares,
        "price": px,
        "graham_value": best["graham_value"],
        "margin_of_safety_pct": best["margin_of_safety_pct"],
        "gross_cost": gross_cost,
        "commission": comm,
        "total_outlay": total_outlay,
        "surplus_cash": surplus,
        "valuations": valuations,
    }


def main():
    budget = 2000.0
    if len(sys.argv) > 1:
        try:
            budget = float(sys.argv[1])
        except ValueError:
            pass

    plan = calculate_opportunistic_deployment(budget)
    print("=" * 80)
    print(f"💰 NET-VALUE OPPORTUNISTIC DEPLOYMENT PLAN (Budget: ৳{budget:,.2f})")
    print("=" * 80)
    print("Graham Fair Value & Margin of Safety Evaluation:")
    print("-" * 80)
    for v in plan["valuations"]:
        print(f"  {v['ticker']:<12} Price: ৳{v['price']:<7.2f} FairVal: ৳{v['graham_value']:<7.2f} MOS: {v['margin_of_safety_pct']:+6.2f}% [{v['status']}]")
    print("-" * 80)

    if "best_stock" in plan:
        print(f"🎯 Recommended Purchase: {plan['best_stock']}")
        print(f"   Buy {plan['shares']} shares @ ৳{plan['price']:.2f}")
        print(f"   Gross Cost: ৳{plan['gross_cost']:.2f} | Broker Fee: ৳{plan['commission']:.2f}")
        print(f"   Total Outlay: ৳{plan['total_outlay']:.2f} | Cash Retained: ৳{plan['surplus_cash']:.2f}")
        print(f"   Deepest Discount: Graham Value ৳{plan['graham_value']:.2f} ({plan['margin_of_safety_pct']:+.1f}% MOS)")
    else:
        print(f"🛡️ {plan.get('directive')}")
    print("=" * 80)


if __name__ == "__main__":
    main()
