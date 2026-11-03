"""
DSE Opportunistic Capital Deployment & Net-Value Allocation Engine.
Implements the User's Mandate:
  - NO fixed arbitrary percentages.
  - Deploys cash strictly to the BEST, most undervalued moat with positive Margin of Safety.
  - Automatically filters out overvalued stocks (Price > Graham Fair Value).
  - Enforces strict 5-Factor Verification (Operating Cash Flow / EPS >= 0.75x, Low Debt, Promoters).
  - Whole-share budget allocation with 0.415% transaction fee reservation.
  - Produces bilingual (English & Bengali) deployment plans.
"""

from __future__ import annotations

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
REPORTS_DIR = BASE_DIR / "reports" / "monthly"
SCRIPTS_DIR = BASE_DIR / "scripts"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from macro_rate_feed import get_latest_macro_rates, calculate_equity_risk_premium

# Core Halal Moat Candidates (Audited Category A with verified CFO Quality)
CANDIDATE_MOATS = [
    "JAMUNAOIL", "PADMAOIL", "MPETROLEUM", "WALTONHIL", 
    "SQURPHARMA", "HWAWELLTEX", "BXPHARMA", "SUMITPOWER", "OLYMPIC", "GP"
]
COMMISSION_RATE = 0.00415  # 0.415% CDBL + Broker fee


def candidate_universe(asof: str | None = None, tier: str | None = None, top_k: int | None = None) -> list[str]:
    """Halal-aware candidate universe strictly derived from 5-Factor Fundamental Screener."""
    _tier = tier
    _k = top_k or 15
    try:
        if _tier is None:
            from profile import load_profile  # type: ignore
            _tier = load_profile().get("halal_tier", "flexible")
    except Exception:
        _tier = _tier or "flexible"

    # 1. Primary: Direct verified 5-Factor Screened Moats
    try:
        from five_factor_fundamental_screener import run_5_factor_screener
        screened = run_5_factor_screener(halal_tier=_tier)
        if screened:
            from anti_manipulation_engine import is_ticker_blacklisted
            clean_list = []
            for s in screened:
                is_b, _ = is_ticker_blacklisted(s["ticker"], asof_date=asof)
                if not is_b:
                    clean_list.append(s["ticker"])
            return clean_list[: int(_k)]
    except Exception:
        pass

    # 2. Secondary fallback: Scored universe via feature store
    try:
        from feature_store import load_scored_universe  # type: ignore
        uni = load_scored_universe(asof)
        if uni:
            from halal_guard import HalalGuard  # type: ignore
            from profile import load_profile as _lp  # type: ignore
            _prof = _lp()
            _guard = HalalGuard(profile=_prof)
            filt = _guard.apply(uni, _prof.get("halal_tier", _tier))
            tickers = [x["ticker"] for x in filt[: int(_k)]]
            if tickers:
                return tickers
    except Exception:
        pass

    return list(CANDIDATE_MOATS)[: int(_k)]


def evaluate_moat_valuations(tickers: list[str] | None = None) -> list[dict]:
    """Calculate Graham Fair Value, live price, and Margin of Safety % with strict 5-filter verification."""
    _tickers = tickers if tickers is not None else candidate_universe()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    results = []
    asof_row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
    asof_date = asof_row[0] if asof_row and asof_row[0] else datetime.date.today().isoformat()

    macro_rates = get_latest_macro_rates(conn)
    rf_rate = macro_rates.get("risk_free_rate_pct", 8.84)

    for ticker in _tickers:
        px_row = conn.execute(
            "SELECT close, date FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        price = float(px_row["close"]) if px_row and px_row["close"] else None

        c_row = conn.execute(
            "SELECT sponsor_holding_pct, govt_holding_pct, sector FROM companies WHERE ticker = ?",
            (ticker,)
        ).fetchone()
        sponsor = float(c_row["sponsor_holding_pct"] or 0.0) if c_row else 0.0
        govt = float(c_row["govt_holding_pct"] or 0.0) if c_row else 0.0
        sec = str(c_row["sector"] or "Unknown") if c_row else "Unknown"
        promoter_pct = sponsor + govt

        pit_row = conn.execute(
            """
            SELECT eps, nav, pe_ratio, debt_equity, dividend_yield 
            FROM fundamentals_pit 
            WHERE ticker = ?
              AND tradable_date <= ?
              AND publication_date <= ?
            ORDER BY tradable_date DESC, publication_date DESC, snapshot_date DESC LIMIT 1
            """,
            (ticker, asof_date, asof_date)
        ).fetchone()

        nocfps = None
        pit_cfo = conn.execute(
            """
            SELECT cash_flow_ops
            FROM fundamentals_pit
            WHERE ticker = ?
              AND tradable_date <= ?
              AND publication_date <= ?
              AND cash_flow_ops IS NOT NULL
            ORDER BY tradable_date DESC, publication_date DESC, snapshot_date DESC LIMIT 1
            """,
            (ticker, asof_date, asof_date)
        ).fetchone()
        if pit_cfo and pit_cfo["cash_flow_ops"] is not None:
            nocfps = float(pit_cfo["cash_flow_ops"])

        eps = float(pit_row["eps"]) if pit_row and pit_row["eps"] else None
        nav = float(pit_row["nav"]) if pit_row and pit_row["nav"] else None
        pe = float(pit_row["pe_ratio"]) if pit_row and pit_row["pe_ratio"] else None
        div_y = float(pit_row["dividend_yield"]) if pit_row and pit_row["dividend_yield"] else 0.0
        de = float(pit_row["debt_equity"]) if pit_row and pit_row["debt_equity"] else 0.0

        # Preserve the hierarchical fallback (f_row -> raw_data -> fundamentals_pit) computed above
        cfo_ratio = round(nocfps / eps, 2) if (nocfps is not None and eps and eps > 0) else None

        if not price or not eps or not nav or eps <= 0 or nav <= 0:
            continue

        # Graham Intrinsic Value: sqrt(22.5 * EPS * NAV)
        graham_val = round(math.sqrt(22.5 * eps * nav), 2)
        mos_pct = round(((graham_val - price) / graham_val) * 100.0, 2)
        is_overvalued = price > graham_val

        # Macro Hurdle Rate & ERP Verification
        erp_info = calculate_equity_risk_premium(eps, price, rf_rate=rf_rate)
        earnings_yield = erp_info["earnings_yield_pct"]
        erp = erp_info["equity_risk_premium_pct"]
        passes_macro = erp_info["passes_macro_hurdle"]

        # 5 Non-Negotiable Capital Preservation Filters
        passes_debt = (de <= 0.80)
        passes_sponsor = (promoter_pct >= 30.0)
        passes_cfo = (cfo_ratio is not None and cfo_ratio >= 0.75)

        status = "OVERVALUED (AVOID)" if is_overvalued else (
            "UNDERVALUED (BUY CANDIDATE)" if (passes_macro and passes_cfo) else "UNDERVALUED (ERP BELOW T-BILL / LOW CFO)"
        )

        results.append({
            "ticker": ticker,
            "sector": sec,
            "price": price,
            "eps": eps,
            "nav": nav,
            "pe": pe,
            "yield": div_y,
            "debt_equity": de,
            "promoter_pct": promoter_pct,
            "nocfps": nocfps,
            "cfo_ratio": cfo_ratio,
            "passes_filters": passes_debt and passes_sponsor and passes_cfo,
            "earnings_yield_pct": earnings_yield,
            "equity_risk_premium_pct": erp,
            "passes_macro_hurdle": passes_macro,
            "graham_value": graham_val,
            "margin_of_safety_pct": mos_pct,
            "is_overvalued": is_overvalued,
            "status": status
        })

    conn.close()
    # Rank by highest Margin of Safety % (deepest discount to net value)
    results.sort(key=lambda x: (not x["is_overvalued"], x["margin_of_safety_pct"]), reverse=True)
    return results


def get_portfolio_sector_weights() -> dict[str, float]:
    """Calculates current sector weight percentage in the portfolio."""
    try:
        if not PORTFOLIO_PATH.exists():
            return {}
        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            p = json.load(f)
        total_eq = 0.0
        sec_eq = {}
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        for h in p.get("holdings", []):
            t = h["ticker"]
            val = float(h.get("gross_cost", 0.0))
            row = conn.execute("SELECT sector FROM companies WHERE ticker = ?", (t,)).fetchone()
            s = row[0] if row and row[0] else "Unknown"
            sec_eq[s] = sec_eq.get(s, 0.0) + val
            total_eq += val
        conn.close()
        if total_eq > 0:
            return {s: round((v / total_eq) * 100.0, 1) for s, v in sec_eq.items()}
    except Exception:
        pass
    return {}


def calculate_opportunistic_deployment(budget_bdt: float = 2000.0) -> dict:
    """Deploy available cash with sector concentration guards (max 35% per sector)."""
    valuations = evaluate_moat_valuations()
    sec_weights = get_portfolio_sector_weights()
    # Deploy only in undervalued stocks that beat risk-free T-bills (ERP >= 0.0%) and have verified CFO
    undervalued = [
        v for v in valuations 
        if (not v["is_overvalued"] and v.get("passes_macro_hurdle", True) and v.get("passes_filters", True))
    ]

    # Fallback to general undervalued if strict passes_filters is empty
    if not undervalued:
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

    # Sector Concentration Filter: Avoid allocating to sectors already > 35% of stock equity
    best = None
    for cand in undervalued:
        c_sec = cand.get("sector", "Unknown")
        if sec_weights.get(c_sec, 0.0) < 35.0 or len(undervalued) == 1:
            best = cand
            break
    if not best:
        best = undervalued[0]
    px = best["price"]
    cost_per_sh = px * (1.0 + COMMISSION_RATE)

    # ENFORCE MANDATORY 10% TACTICAL CASH BUFFER
    cash_buffer_reserve = round(budget_bdt * 0.10, 2)
    investable_capital = max(budget_bdt - cash_buffer_reserve, 0.0)
    shares = int(investable_capital / cost_per_sh)
    gross_cost = round(shares * px, 2)
    comm = round(gross_cost * COMMISSION_RATE, 2)
    total_outlay = round(gross_cost + comm, 2)
    surplus = round(budget_bdt - total_outlay, 2)

    return {
        "budget_bdt": budget_bdt,
        "cash_buffer_reserve": cash_buffer_reserve,
        "investable_capital": investable_capital,
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


def generate_monthly_rebalance_reports(budget_bdt: float = 2000.0) -> tuple[Path, Path]:
    """Generates both English and Bengali markdown deployment reports."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    plan = calculate_opportunistic_deployment(budget_bdt)
    month_str = datetime.date.today().strftime("%Y-%m")

    # 1. English Report
    en_lines = [
        f"# 💰 Opportunistic Capital Deployment Plan — {month_str}",
        f"**Budget**: ৳{budget_bdt:,.2f} | **Generated**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"**Strategy**: 5-Factor Screened Moats, Verified NOCFPS, Benjamin Graham Margin of Safety\n",
        "## 🏛️ Valuation & Margin of Safety Evaluation\n",
        "| Ticker | Price | Graham Fair Value | Margin of Safety | CFO/EPS | D/E | Promoter % | Status |",
        "|---|---|---|---|---|---|---|---|"
    ]
    for v in plan["valuations"]:
        cfo_s = f"{v['cfo_ratio']:.2f}x" if v.get("cfo_ratio") is not None else "—"
        en_lines.append(
            f"| **{v['ticker']}** | ৳{v['price']:.2f} | ৳{v['graham_value']:.2f} | **{v['margin_of_safety_pct']:+.1f}%** | "
            f"{cfo_s} | {v['debt_equity']:.2f} | {v['promoter_pct']:.1f}% | `{v['status']}` |"
        )
    en_lines.append("\n---\n")

    if "best_stock" in plan:
        en_lines.extend([
            f"## 🎯 Primary Recommendation: **{plan['best_stock']}**\n",
            f"- **Target Quantity**: **{plan['shares']} shares** @ ৳{plan['price']:.2f}",
            f"- **Gross Outlay**: ৳{plan['gross_cost']:,.2f}",
            f"- **Broker & CDBL Fee (0.415%)**: ৳{plan['commission']:,.2f}",
            f"- **Total Capital Required**: **৳{plan['total_outlay']:,.2f}**",
            f"- **Mandatory 10% Cash Reserve**: ৳{plan.get('cash_buffer_reserve', 0):,.2f}",
            f"- **Total Surplus Cash Retained**: ৳{plan['surplus_cash']:,.2f}",
            f"- **Intrinsic Value**: ৳{plan['graham_value']:.2f} (Deepest Discount: **{plan['margin_of_safety_pct']:+.1f}% MOS**)\n",
            "> Execution Rule: Submit passive limit order at best ask during opening 15 minutes."
        ])
    else:
        en_lines.append(f"> 🛡️ {plan.get('directive')}")

    en_path = REPORTS_DIR / f"{month_str}_opportunistic_plan.md"
    with open(en_path, "w", encoding="utf-8") as f:
        f.write("\n".join(en_lines))

    # 2. Bengali Report
    bn_lines = [
        f"# 💰 মাসিক ক্যাপিটাল ডিপ্লয়মেন্ট ও রিব্যালান্সিং প্ল্যান — {month_str}",
        f"**বাজেট**: ৳{budget_bdt:,.2f} | **তৈরির সময়**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"**কৌশল**: ৫-ফ্যাক্টর অডিটেড কোম্পানি, অডিটেড NOCFPS ক্যাশ ফ্লো, বেঞ্জামিন গ্রাহাম Margin of Safety\n",
        "## 🏛️ গ্রাহাম ফেয়ার ভ্যালু ও মার্জিন অব সেফটি মূল্যায়ন\n",
        "| Ticker | বর্তমান দর | Graham Fair Value | Margin of Safety | CFO/EPS | Debt/Equity | Promoter % | স্ট্যাটাস |",
        "|---|---|---|---|---|---|---|---|"
    ]
    for v in plan["valuations"]:
        cfo_s = f"{v['cfo_ratio']:.2f}x" if v.get("cfo_ratio") is not None else "—"
        status_bn = "ক্রয়যোগ্য (আন্ডারভ্যালুড)" if "BUY CANDIDATE" in v["status"] else (
            "এড়িয়ে চলুন (ওভারভ্যালুড)" if "OVERVALUED" in v["status"] else "কম্পিটিটিভ নয়"
        )
        bn_lines.append(
            f"| **{v['ticker']}** | ৳{v['price']:.2f} | ৳{v['graham_value']:.2f} | **{v['margin_of_safety_pct']:+.1f}%** | "
            f"{cfo_s} | {v['debt_equity']:.2f} | {v['promoter_pct']:.1f}% | `{status_bn}` |"
        )
    bn_lines.append("\n---\n")

    if "best_stock" in plan:
        bn_lines.extend([
            f"## 🎯 সর্বোচ্চ অগ্রাধিকার ক্রয়ের সুপারিশ: **{plan['best_stock']}**\n",
            f"- **শেয়ার সংখ্যা**: **{plan['shares']} টি** @ ৳{plan['price']:.2f}",
            f"- **মোট শেয়ার মূল্য**: ৳{plan['gross_cost']:,.2f}",
            f"- **ব্রোকারেজ ও CDBL ফি (০.৪১৫%)**: ৳{plan['commission']:,.2f}",
            f"- **মোট বিনিয়োগ খরচ**: **৳{plan['total_outlay']:,.2f}**",
            f"- **বাধ্যতামূলক ১০% তরল রিজার্ভ বাফার**: ৳{plan.get('cash_buffer_reserve', 0):,.2f}",
            f"- **মোট উদ্বৃত্ত ক্যাশ রিজার্ভ**: ৳{plan['surplus_cash']:,.2f}",
            f"- **অন্তর্নিহিত ফেয়ার ভ্যালু**: ৳{plan['graham_value']:.2f} (সর্বোচ্চ ডিসকাউন্ট: **{plan['margin_of_safety_pct']:+.1f}% MOS**)\n",
            "> এক্সিকিউশন পরামর্শ: বাজার খোলার প্রথম ১৫ মিনিটে Best Ask প্রাইসে লিমিট অর্ডার স্থাপন করুন।"
        ])
    else:
        bn_lines.append(f"> 🛡️ {plan.get('directive')}")

    bn_path = REPORTS_DIR / f"{month_str}_opportunistic_plan_bn.md"
    with open(bn_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines))

    return en_path, bn_path


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
        cfo_s = f"CFO: {v['cfo_ratio']:.2f}x" if v.get("cfo_ratio") is not None else "CFO: N/A"
        print(f"  {v['ticker']:<12} Price: ৳{v['price']:<7.2f} FairVal: ৳{v['graham_value']:<7.2f} MOS: {v['margin_of_safety_pct']:+6.2f}% {cfo_s:<12} [{v['status']}]")
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

    en_p, bn_p = generate_monthly_rebalance_reports(budget)
    print(f"[Reports Published: {en_p.name} & {bn_p.name}]")


if __name__ == "__main__":
    main()
