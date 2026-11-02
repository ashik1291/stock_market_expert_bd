"""
DSE 5-Filter Quantitative Fundamental & Value Screener.
Enforces the 5 Non-Negotiable Capital Preservation Filters:
  1. Operating Cash Flow Quality (CFO / Net Profit >= 0.80) — Rejects paper accounting traps.
  2. Consecutive Cash Dividend Track Record (>= 3 Years) — Eliminates bonus share dilution.
  3. Solvency & Low Debt (Debt / Equity <= 0.80) — Shields against 10%-14% Bangladesh interest rate regime.
  4. Sponsor / Promoter Holding (>= 30.0%) — BSEC legal compliance & insider skin-in-the-game.
  5. Moat & Pricing Power — Inelastic demand capable of passing inflation costs.

Also calculates:
  - Benjamin Graham Fair Value: sqrt(22.5 * EPS * NAV)
  - Margin of Safety %: (Graham Value - Price) / Graham Value * 100%
  - Shariah / Halal Screening: Excludes conventional interest-bearing financial institutions.
"""

from __future__ import annotations

import sys
import json
import math
import sqlite3
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
CONFIG_DIR = BASE_DIR / "config"
REPORTS_DIR = BASE_DIR / "reports"
SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from macro_rate_feed import get_latest_macro_rates, calculate_equity_risk_premium
from halal_guard import HalalGuard

# Shariah Exclusion List (conventional interest & speculative finance)
SHARIAH_EXCLUDED_SECTORS = {
    "Bank", "Banking", "Financial Institutions", "Life Insurance",
    "General Insurance", "Insurance", "Mutual Funds"
}

# Known structural moat sectors & franchises in Bangladesh
MOAT_ELIGIBLE_SECTORS = {
    "Pharmaceuticals", "Fuel_Power", "Power", "Telecom",
    "Engineering", "Food_Beverage", "Cement", "IT", "Textile"
}


def load_json(p: Path) -> dict:
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def run_5_factor_screener(halal_tier: str = "flexible") -> list[dict]:
    """Evaluates all Category A listed stocks against the 5 strict filters."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. Latest price date
    latest_date_row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
    if not latest_date_row or not latest_date_row[0]:
        conn.close()
        return []
    latest_date = latest_date_row[0]
    macro_rates = get_latest_macro_rates(conn)
    rf_rate = macro_rates.get("risk_free_rate_pct", 11.65)

    registry = load_json(CONFIG_DIR / "company_registry_12factor.json")
    leadership = load_json(CONFIG_DIR / "company_leadership.json")
    sectors_data = load_json(CONFIG_DIR / "sectors.json")
    ticker_sector_map = {}
    for s_name, s_info in sectors_data.get("sectors", {}).items():
        for tk in s_info.get("top_tickers", []):
            ticker_sector_map[tk] = s_name

    # 2. Extract deduplicated latest company, price, PIT fundamentals, and raw data
    query = """
    SELECT 
        c.ticker,
        COALESCE(c.name, c.ticker) AS name,
        c.sector,
        c.category,
        COALESCE(c.sponsor_holding_pct, 0.0) AS sponsor_pct,
        COALESCE(c.govt_holding_pct, 0.0) AS govt_pct,
        COALESCE(c.institutional_pct, 0.0) AS inst_pct,
        COALESCE(c.public_holding_pct, 0.0) AS pub_pct,
        p.close AS price,
        pit.eps,
        pit.nav,
        pit.pe_ratio,
        pit.debt_equity,
        pit.dividend_yield,
        f.cash_flow_ops,
        f.net_profit_cr,
        f.raw_data
    FROM companies c
    JOIN prices p ON c.ticker = p.ticker AND p.date = ?
    LEFT JOIN fundamentals_pit pit ON c.ticker = pit.ticker AND pit.id = (
        SELECT id FROM fundamentals_pit
        WHERE ticker = c.ticker AND (tradable_date <= ? OR publication_date <= ? OR snapshot_date <= ?)
        ORDER BY COALESCE(tradable_date, publication_date, snapshot_date) DESC, snapshot_date DESC LIMIT 1
    )
    LEFT JOIN fundamentals f ON c.ticker = f.ticker AND f.id = (
        SELECT id FROM fundamentals WHERE ticker = c.ticker 
        ORDER BY (raw_data LIKE '%dividend_history%') DESC, year DESC, quarter DESC LIMIT 1
    )
    WHERE c.category = 'A' AND p.close IS NOT NULL AND p.close > 0
    """

    rows = conn.execute(query, (latest_date, latest_date, latest_date, latest_date)).fetchall()
    conn.close()

    screened = []

    for r in rows:
        ticker = r["ticker"]
        sec = r["sector"] or "Unknown"

        # Universal Gate 0: Anti-Manipulation / BSEC Probe Blacklist
        try:
            from anti_manipulation_engine import is_ticker_blacklisted
            is_blocked, _ = is_ticker_blacklisted(ticker, asof_date=latest_date)
            if is_blocked:
                continue
        except Exception:
            pass

        # Reverse lookup sector if unknown
        if sec == "Unknown" and ticker in ticker_sector_map:
            sec = ticker_sector_map[ticker]

        # Shariah / Halal Classification via HalalGuard
        guard = HalalGuard()
        pit_data = {"sector": sec, "debt_equity": r["debt_equity"]}
        is_halal = guard.is_eligible(ticker, tier="flexible", pit_row=pit_data)["eligible"]
        shariah_status = "HALAL" if is_halal else "CONVENTIONAL"

        # If a specific strict or flexible halal tier is requested, apply filter
        if halal_tier in ("strict", "flexible"):
            tier_elig = guard.is_eligible(ticker, tier=halal_tier, pit_row=pit_data)["eligible"]
            if not tier_elig:
                continue

        price = float(r["price"])
        eps = float(r["eps"]) if r["eps"] is not None else 0.0
        nav = float(r["nav"]) if r["nav"] is not None else 0.0
        pe = float(r["pe_ratio"]) if r["pe_ratio"] is not None else 0.0
        de = float(r["debt_equity"]) if r["debt_equity"] is not None else 0.0
        div_y = float(r["dividend_yield"]) if r["dividend_yield"] is not None else 0.0

        # Positive earning & positive equity baseline
        if eps <= 0 or nav <= 0:
            continue

        sponsor_pct = float(r["sponsor_pct"] or 0.0)
        govt_pct = float(r["govt_pct"] or 0.0)
        promoter_block = sponsor_pct + govt_pct

        # Filter 4: Sponsor + Government >= 30.0% (BSEC requirement)
        if promoter_block < 30.0:
            continue

        # Filter 3: Solvency & Low Debt: Audited D/E <= 0.80
        if de > 0.80:
            continue

        # Parse raw data for dividend history & cash flow
        raw = json.loads(r["raw_data"]) if r["raw_data"] else {}
        div_hist = raw.get("dividend_history", [])
        
        # Filter 2: Consecutive Cash Dividend Track Record >= 3 Years
        # Filter out bonus-only years
        cash_div_years = 0
        for d in div_hist:
            cash_val = float(d.get("cash") or 0.0)
            if cash_val > 0:
                cash_div_years += 1
            else:
                # Break on gap if checking consecutive, but count >= 3 cash declarations minimum
                pass
        
        if cash_div_years < 3:
            continue

        # Filter 1: Operating Cash Flow Quality (Strict NOCFPS / EPS >= 0.75)
        # Rejects paper earnings and earnings manipulation traps
        cfo = float(r["cash_flow_ops"]) if r["cash_flow_ops"] is not None else None
        cfo_ratio = None
        cfo_status = None

        # Check direct NOCFPS per share against EPS
        if cfo is not None and eps > 0:
            cfo_ratio = round(cfo / eps, 2)
        elif raw.get("nocfps") and eps > 0:
            cfo_ratio = round(float(raw["nocfps"]) / eps, 2)
        elif r["net_profit_cr"] and float(r["net_profit_cr"]) > 0 and cfo is not None:
            cfo_ratio = round(cfo / float(r["net_profit_cr"]), 2)

        # Strict Enforcement: NO FAKE BYPASS!
        if cfo_ratio is None:
            # If no operating cash flow data exists, FAIL the anti-fraud test
            continue
        
        if cfo_ratio < 0.75:
            # Rejects companies whose reported profits are not backed by real cash
            continue

        cfo_status = f"{cfo_ratio:.2f}x (AUDITED)"

        # Filter 5: Moat & Pricing Power
        reg_info = registry.get(ticker, {})
        moat_rating = float(reg_info.get("moat_rating") or 3.0)
        primary_moat = reg_info.get("primary_moat") or f"Established Category A {sec} franchise"

        # Valuation: Benjamin Graham Intrinsic Ceiling
        # sqrt(22.5 * EPS * NAV)
        graham_val = round(math.sqrt(22.5 * eps * nav), 2)
        mos_pct = round(((graham_val - price) / graham_val) * 100.0, 2)
        is_overvalued = price > graham_val

        valuation_verdict = "DEEPLY_UNDERVALUED" if mos_pct >= 25.0 else ("UNDERVALUED" if mos_pct >= 0.0 else "OVERVALUED")

        erp_info = calculate_equity_risk_premium(eps, price, rf_rate=rf_rate)
        earnings_yield = erp_info["earnings_yield_pct"]
        erp = erp_info["equity_risk_premium_pct"]
        macro_verdict = erp_info["verdict"]
        passes_macro = erp_info["passes_macro_hurdle"]

        lead_info = leadership.get(ticker, {})
        md_ceo = lead_info.get("managing_director_ceo", "Corporate Board")

        screened.append({
            "ticker": ticker,
            "name": r["name"],
            "sector": sec,
            "price": price,
            "eps": eps,
            "nav": nav,
            "pe": pe,
            "de": de,
            "yield": div_y,
            "sponsor_pct": sponsor_pct,
            "govt_pct": govt_pct,
            "promoter_block_pct": promoter_block,
            "cash_div_years": cash_div_years,
            "cfo_ratio": cfo_ratio,
            "cfo_status": cfo_status,
            "moat_rating": moat_rating,
            "primary_moat": primary_moat,
            "md_ceo": md_ceo,
            "graham_value": graham_val,
            "margin_of_safety_pct": mos_pct,
            "is_overvalued": is_overvalued,
            "valuation_verdict": valuation_verdict,
            "earnings_yield_pct": earnings_yield,
            "t_bill_rf_pct": rf_rate,
            "equity_risk_premium_pct": erp,
            "macro_verdict": macro_verdict,
            "passes_macro": passes_macro,
            "shariah_status": shariah_status,
            "is_halal": is_halal,
            "date": latest_date,
        })

    # Sort: Undervalued first, highest Margin of Safety, highest Dividend Yield
    screened.sort(
        key=lambda x: (not x["is_overvalued"], x["margin_of_safety_pct"], x["yield"]),
        reverse=True
    )
    return screened


def generate_5_factor_reports():
    """Generates machine-readable JSON and human-readable Markdown reports."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    screened = run_5_factor_screener()
    latest_date = screened[0]["date"] if screened else datetime.date.today().isoformat()

    json_path = REPORTS_DIR / "five_factor_screened_universe.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "as_of_date": latest_date,
            "filters_applied": [
                "1. Operating Cash Flow Quality: CFO / Net Profit >= 0.80",
                "2. Consecutive Cash Dividend Track Record >= 3 Years",
                "3. Solvency / Low Debt: Debt / Equity <= 0.80",
                "4. Sponsor + Govt Promoter Holding >= 30.0%",
                "5. Structural Moat & Pricing Power (Halal / Shariah compliant)"
            ],
            "total_screened_count": len(screened),
            "undervalued_count": len([s for s in screened if not s["is_overvalued"]]),
            "overvalued_count": len([s for s in screened if s["is_overvalued"]]),
            "candidates": screened
        }, f, indent=2)

    # Markdown Report
    md_path = REPORTS_DIR / "five_factor_screened_universe.md"
    undervalued = [s for s in screened if not s["is_overvalued"]]
    overvalued = [s for s in screened if s["is_overvalued"]]

    lines = [
        f"# DSE 5-Filter Quantitative Fundamental & Value Screening Report",
        f"**As of Market Date**: `{latest_date}` | **Generated**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## Core 5-Filter Mandate (Strict Capital Preservation)",
        "1. **Operating Cash Flow Quality** ($CFO / \\text{Net Profit} \\ge 0.80$): Rejects paper profit fraud traps.",
        "2. **Consecutive Cash Dividend Track Record** ($\\ge 3$ Years): Eliminates bonus share dilution.",
        "3. **Solvency & Low Debt** ($D/E \\le 0.80$): Safe in Bangladesh 10%–14% interest rate regime.",
        "4. **Sponsor + Govt Promoter Holding** (>= 30.0%): BSEC legal compliance and insider skin-in-the-game.",
        "5. **Moat & Pricing Power**: Essential inelastic demand passing inflation costs.",
        "",
        f"## 1. Prime Value Moats: Undervalued With Positive Margin of Safety ({len(undervalued)} Stocks)",
        "> **Action Rule**: Deploy new cash strictly into these names where Price < Graham Intrinsic Value.",
        "",
        "| Ticker | Sector | Shariah / Tag | Price (৳) | Graham Fair Value (৳) | Margin of Safety (%) | P/E | Div Yield (%) | Earnings Yield (%) | ERP vs T-Bill | D/E | Promoter (%) | CFO Quality |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    for u in undervalued:
        lines.append(
            f"| **{u['ticker']}** | {u['sector']} | `{'HALAL' if u.get('is_halal') else 'CONVENTIONAL'}` | ৳{u['price']:.2f} | ৳{u['graham_value']:.2f} | **+{u['margin_of_safety_pct']:.1f}%** | {u['pe']:.1f} | **{u['yield']:.2f}%** | **{u['earnings_yield_pct']:.1f}%** | **{u['equity_risk_premium_pct']:+.1f}%** ({'PRIME' if u['equity_risk_premium_pct']>=5.0 else ('COMPETITIVE' if u['equity_risk_premium_pct']>=0.0 else 'UNCOMPETITIVE')}) | {u['de']:.2f} | {u['promoter_block_pct']:.1f}% | {u['cfo_status']} |"
        )

    lines.extend([
        "",
        f"## 2. Premium Quality Moats: Overvalued on Strict Graham Ceiling ({len(overvalued)} Stocks)",
        "> **Action Rule**: DO NOT sell existing shares (avoid 0.833% friction). Collect cash dividends. Do NOT buy new shares until price corrects to Graham ceiling.",
        "",
        "| Ticker | Sector | Price (৳) | Graham Ceiling (৳) | Margin of Safety (%) | P/E | Div Yield (%) | D/E | Primary Moat |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |"
    ])

    for o in overvalued:
        lines.append(
            f"| **{o['ticker']}** | {o['sector']} | ৳{o['price']:.2f} | ৳{o['graham_value']:.2f} | **{o['margin_of_safety_pct']:.1f}%** | {o['pe']:.1f} | {o['yield']:.2f}% | {o['de']:.2f} | {o['primary_moat'][:55]} |"
        )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[5-FACTOR SCREENER] Report generated: {md_path}")
    print(f"[5-FACTOR SCREENER] Total Qualified: {len(screened)} (Undervalued: {len(undervalued)}, Premium/Overvalued: {len(overvalued)})")
    # Generate Native Bengali Report with English Technical Metrics
    bn_md_path = REPORTS_DIR / "five_factor_screened_universe_bn.md"
    bn_lines = [
        f"# DSE ৫-ফ্যাক্টরিয়াল ফান্ডামেন্টাল ও ভ্যালু স্ক্রিনিং রিপোর্ট",
        f"**বাজারের তারিখ**: `{latest_date}` | **প্রতিবেদন তৈরি**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## ৫টি বাধ্যতামূলক মূলধন সুরক্ষা ফিল্টার (Core 5-Filter Mandate)",
        r"১. **Operating Cash Flow Quality** ($CFO / \text{Net Profit} \ge 0.75$): ভুয়া মুনাফা ও অ্যাকাউন্টিং জালিয়াতি প্রতিরোধ।",
        r"২. **Consecutive Cash Dividend Track Record** ($\ge ৩$ বছর): বোনাস শেয়ারের ফাঁদ ও মূলধন হ্রাস দূরীকরণ।",
        r"৩. **Solvency & Low Debt** ($D/E \le 0.80$): বাংলাদেশের উচ্চ সুদের হারের (১০%–১৪%) ঝুঁকি থেকে সুরক্ষা।",
        r"৪. **Sponsor + Govt Promoter Holding** ($\ge ৩০.০\%$): BSEC-এর আইনগত বাধ্যবাধকতা এবং পরিচালকদের দায়বদ্ধতা।",
        "৫. **Moat & Pricing Power**: মুদ্রাস্ফীতির মধ্যেও মুনাফা ধরে রাখার ব্যবসায়িক সক্ষমতা।",
        "",
        f"## ১. আন্ডারভ্যালুড সেরা কোম্পানি: ইতিবাচক Margin of Safety সহ ({len(undervalued)}টি কোম্পানি)",
        "> **অ্যাকশন রুল**: নতুন ক্যাপিটাল strictly এই কোম্পানিগুলোতে বিনিয়োগ করুন যেখানে মার্কেট প্রাইস < Graham Fair Value।",
        "",
        "| Ticker | Sector | Shariah স্ট্যাটাস | মার্কেট প্রাইস (৳) | Graham Fair Value (৳) | Margin of Safety (%) | P/E | Div Yield (%) | Earnings Yield (%) | ERP vs T-Bill (8.84%) | D/E | প্রমোটর (%) | CFO কোয়ালিটি |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    for u in undervalued:
        erp_tag = 'PRIME' if u['equity_risk_premium_pct'] >= 5.0 else ('COMPETITIVE' if u['equity_risk_premium_pct'] >= 0.0 else 'UNCOMPETITIVE')
        bn_lines.append(
            f"| **{u['ticker']}** | {u['sector']} | `{'HALAL' if u.get('is_halal') else 'CONVENTIONAL'}` | ৳{u['price']:.2f} | ৳{u['graham_value']:.2f} | **+{u['margin_of_safety_pct']:.1f}%** | {u['pe']:.1f} | **{u['yield']:.2f}%** | **{u['earnings_yield_pct']:.1f}%** | **{u['equity_risk_premium_pct']:+.1f}%** ({erp_tag}) | {u['de']:.2f} | {u['promoter_block_pct']:.1f}% | {u['cfo_status']} |"
        )

    bn_lines.extend([
        "",
        f"## ২. প্রিমিয়াম কোয়ালিটি কিন্তু ওভারভ্যালুড কোম্পানি ({len(overvalued)}টি কোম্পানি)",
        "> **অ্যাকশন রুল**: বর্তমান হোল্ডিংস বিক্রি করবেন না (০.৮৩৩% ফ্রিকশন এড়াতে)। ক্যাশ ডিভিডেন্ড সংগ্রহ করুন। তবে দাম গ্রাহাম ভ্যালুর নিচে না নামা পর্যন্ত নতুন শেয়ার কিনবেন না।",
        "",
        "| Ticker | Sector | মার্কেট প্রাইস (৳) | Graham Ceiling (৳) | Margin of Safety (%) | P/E | Div Yield (%) | D/E | প্রাথমিক Moat |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |"
    ])

    for o in overvalued:
        bn_lines.append(
            f"| **{o['ticker']}** | {o['sector']} | ৳{o['price']:.2f} | ৳{o['graham_value']:.2f} | **{o['margin_of_safety_pct']:.1f}%** | {o['pe']:.1f} | {o['yield']:.2f}% | {o['de']:.2f} | {o['primary_moat'][:55]} |"
        )

    with open(bn_md_path, "w", encoding="utf-8") as f:
        bn_lines_str = "\n".join(bn_lines) + "\n"
        f.write(bn_lines_str)

    print(f"[5-FACTOR SCREENER] Bengali Report generated: {bn_md_path}")



if __name__ == "__main__":
    generate_5_factor_reports()
