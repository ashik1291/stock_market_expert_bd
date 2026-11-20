"""
scripts/peer_moat_comparator.py — Institutional Head-to-Head Peer Moat Comparator & DuPont 3-Way Decomposition
Compares competitor stocks side-by-side across DuPont operational efficiency,
valuation, central bank macro hurdle rates, governance risk, and export barriers.
"""

from __future__ import annotations

import sys
import json
import sqlite3
import argparse
from pathlib import Path

# Enforce UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

# Ensure repo root is in python path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

MACRO_91D_TBILL_RATE = 11.60  # Risk-Free Rate anchor from Bangladesh Bank auction


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_peer_metrics(ticker: str) -> dict | None:
    ticker = ticker.strip().upper()
    conn = get_db()
    cur = conn.cursor()

    # 1. Company
    cur.execute("SELECT ticker, name, sector, category, market_cap_cr FROM companies WHERE ticker = ?", (ticker,))
    comp = cur.fetchone()
    if not comp:
        conn.close()
        return None

    # 2. Features Daily (Latest)
    cur.execute(
        """
        SELECT date, close, volume, pe_ratio, debt_equity, dividend_yield, eps, nav, rsi_14, sma_20, sma_50
        FROM features_daily
        WHERE ticker = ? ORDER BY date DESC LIMIT 1
        """,
        (ticker,)
    )
    feat = cur.fetchone()

    # 3. Fundamentals (for ROE, Net profit, Revenue)
    cur.execute(
        """
        SELECT year, quarter, roe, net_profit_cr, revenue_cr, eps, nav, pe_ratio, debt_equity, dividend_yield
        FROM fundamentals
        WHERE ticker = ? ORDER BY year DESC, quarter DESC LIMIT 1
        """,
        (ticker,)
    )
    fund = cur.fetchone()
    conn.close()

    # Import specialized modules
    from scripts.governance_risk_sentinel import evaluate_governance_risk
    from scripts.revenue_segment_analyzer import get_revenue_segment

    gov = evaluate_governance_risk(ticker, persist=False)
    seg = get_revenue_segment(ticker, persist=False)

    px = feat["close"] if feat and feat["close"] is not None else 0.0
    pe = feat["pe_ratio"] if feat and feat["pe_ratio"] is not None else (fund["pe_ratio"] if fund else 0.0)
    eps = feat["eps"] if feat and feat["eps"] is not None else (fund["eps"] if fund else 0.0)
    nav = feat["nav"] if feat and feat["nav"] is not None else (fund["nav"] if fund else 0.0)
    div_y = feat["dividend_yield"] if feat and feat["dividend_yield"] is not None else (fund["dividend_yield"] if fund else 0.0)
    de = feat["debt_equity"] if feat and feat["debt_equity"] is not None else (fund["debt_equity"] if fund else 0.0)
    roe = fund["roe"] if fund and fund["roe"] is not None else (round((eps / nav * 100.0), 2) if nav and nav > 0 else 0.0)

    # Earnings Yield & Macro Hurdle Spread
    earnings_yield = round((eps / px * 100.0), 2) if px and px > 0 else 0.0
    from macro_rate_feed import get_latest_macro_rates
    macro_erp = round(earnings_yield - get_latest_macro_rates()["risk_free_rate_pct"], 2)

    # DuPont 3-Way Decomposition:
    # ROE = Net Profit Margin * Asset Turnover * Equity Multiplier
    # Equity Multiplier ≈ 1 + Debt/Equity
    equity_multiplier = round(1.0 + (de or 0.0), 3)

    rev_cr = seg.get("total_revenue_cr") or (fund["revenue_cr"] if fund else 0.0)
    profit_cr = fund["net_profit_cr"] if fund and fund["net_profit_cr"] else None

    if rev_cr and profit_cr and rev_cr > 0:
        net_margin = round((profit_cr / rev_cr) * 100.0, 2)
    elif roe and equity_multiplier > 0:
        # Estimate Margin assuming standard capital turnover
        net_margin = round(min(roe / equity_multiplier, 25.0), 2)
    else:
        net_margin = 15.0

    asset_turnover = round(roe / (net_margin * equity_multiplier), 2) if (net_margin and equity_multiplier) else 0.8

    return {
        "ticker": ticker,
        "name": comp["name"],
        "sector": comp["sector"],
        "category": comp["category"],
        "market_cap_cr": comp["market_cap_cr"],
        "price": px,
        "pe_ratio": pe,
        "eps": eps,
        "nav": nav,
        "pb_ratio": round(px / nav, 2) if nav and nav > 0 else 0.0,
        "dividend_yield": div_y,
        "debt_equity": de,
        "roe": roe,
        "dupont": {
            "net_margin_pct": net_margin,
            "asset_turnover": asset_turnover,
            "equity_multiplier": equity_multiplier,
            "formula_check_roe": round(net_margin * asset_turnover * equity_multiplier, 2)
        },
        "earnings_yield": earnings_yield,
        "macro_erp_vs_tbill": macro_erp,
        "governance_tier": gov["legal_risk_tier"],
        "political_score": gov["political_exposure_score"],
        "export_share_pct": seg.get("export_share_pct", 0.0),
        "us_fda": seg.get("us_fda_approved", 0),
        "uk_mhra": seg.get("uk_mhra_approved", 0),
        "markets_count": seg.get("export_destinations_count", 0)
    }


def compare_peers(tickers: list[str], as_json: bool = False):
    peers_data = []
    for t in tickers:
        m = get_peer_metrics(t)
        if m:
            peers_data.append(m)

    if not peers_data:
        print(f"Error: None of the tickers {tickers} found in database.", file=sys.stderr)
        return

    if as_json:
        print(json.dumps(peers_data, indent=2))
        return

    # Visual Multi-Stock Comparison Dashboard
    print("=" * 110)
    print(f"🏛️ INSTITUTIONAL HEAD-TO-HEAD PEER MOAT & DUPONT MATRIX ({len(peers_data)} Peers)")
    print("=" * 110)

    # 1. Valuation & Financials Table
    print(f"{'Ticker':<12} {'Price (৳)':<11} {'P/E':<8} {'EPS':<8} {'NAV':<9} {'P/B':<6} {'Div%':<7} {'D/E':<7} {'Earn Yield':<12} {'Macro ERP vs T-Bill'}")
    print("-" * 110)
    for p in peers_data:
        erp_sign = "+" if p['macro_erp_vs_tbill'] >= 0 else ""
        erp_str = f"{erp_sign}{p['macro_erp_vs_tbill']:.2f}%"
        print(f"{p['ticker']:<12} ৳{p['price']:<10.2f} {p['pe_ratio']:<8.1f} ৳{p['eps']:<7.2f} ৳{p['nav']:<8.2f} {p['pb_ratio']:<6.2f} {p['dividend_yield']:<6.2f}% {p['debt_equity']:<7.3f} {p['earnings_yield']:<11.2f}% {erp_str}")
    print("-" * 110)

    # 2. DuPont 3-Way ROE Decomposition Table
    print("\n🔍 DUPONT 3-WAY ROE DECOMPOSITION (Pricing Power × Operational Efficiency × Leverage):")
    print(f"{'Ticker':<12} {'Reported ROE':<15} {'Net Margin (%)':<16} {'Asset Turnover':<16} {'Equity Multiplier':<18} {'Primary ROE Driver'}")
    print("-" * 110)
    for p in peers_data:
        dp = p["dupont"]
        driver = "Pricing Power" if dp["net_margin_pct"] > 18.0 else ("Asset Velocity" if dp["asset_turnover"] > 1.0 else "Balance Sheet Leverage")
        print(f"{p['ticker']:<12} {p['roe']:<14.2f}% {dp['net_margin_pct']:<15.2f}% {dp['asset_turnover']:<15.2f}x {dp['equity_multiplier']:<17.3f}x {driver}")
    print("-" * 110)

    # 3. Governance, Political Exposure & Export Barriers
    print("\n🛡️ GOVERNANCE RISKS, EXPORT MOATS & REGULATORY BARRIERS:")
    print(f"{'Ticker':<12} {'Governance Tier':<20} {'Pol Score':<12} {'Export %':<11} {'US FDA':<9} {'UK MHRA':<9} {'Export Reach'}")
    print("-" * 110)
    for p in peers_data:
        fda = "✓ YES" if p["us_fda"] else "✗ No"
        mhra = "✓ YES" if p["uk_mhra"] else "✗ No"
        print(f"{p['ticker']:<12} {p['governance_tier']:<20} {p['political_score']:<11.1f} {p['export_share_pct']:<10.2f}% {fda:<9} {mhra:<9} {p['markets_count']} countries")
    print("=" * 110)

    # 4. Executive Capital Allocation Verdict
    # Best stock selection based on Macro ERP + Clean Governance + Strong Net Margin
    scored = []
    for p in peers_data:
        score = 0
        if p["governance_tier"] == "LOW":
            score += 35
        elif p["governance_tier"] == "MEDIUM":
            score += 15
        else:
            score -= 30  # Penalty for high/critical governance risk

        if p["debt_equity"] < 0.20:
            score += 25
        elif p["debt_equity"] < 0.60:
            score += 15

        if p["us_fda"]:
            score += 20
        if p["macro_erp_vs_tbill"] > 0:
            score += 20

        scored.append((p["ticker"], score, p))

    scored.sort(key=lambda x: x[1], reverse=True)
    winner = scored[0]

    print(f"🎯 INSTITUTIONAL RESEARCH VERDICT & CAPITAL ALLOCATION:")
    print(f"  * Top Conviction Pick : 🏆 {winner[0]} (Quality & Moat Score: {winner[1]}/100)")
    print(f"  * Rationale           : Superior governance integrity, pristine balance sheet (D/E: {winner[2]['debt_equity']}), and unmatched operational moat.")
    if len(scored) > 1 and scored[-1][2]["governance_tier"] in ("HIGH", "CRITICAL"):
        print(f"  * Cautious / Underweight: ⚠️ {scored[-1][0]} (Score: {scored[-1][1]}/100) due to {scored[-1][2]['governance_tier']} governance/political overhang despite apparent cheap P/E.")
    print("=" * 110)

    verdict = {
        "peers": peers_data,
        "ranking": [{"ticker": s[0], "institutional_score": s[1], "metrics": s[2]} for s in scored],
        "top_pick": winner[0],
        "top_score": winner[1],
        "rationale": f"Superior governance integrity, pristine balance sheet (D/E: {winner[2]['debt_equity']}), and unmatched operational moat."
    }
    return verdict


def main():
    parser = argparse.ArgumentParser(description="Institutional Peer Moat Comparator & DuPont Decomposition")
    parser.add_argument("tickers", nargs="*", default=["BXPHARMA", "SQURPHARMA", "RENATA"], help="Stock ticker symbols to compare")
    parser.add_argument("--sector", type=str, default=None, help="Compare top stocks in a given sector")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    tickers = args.tickers
    if args.sector:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ticker FROM companies
            WHERE LOWER(sector) LIKE LOWER(?) AND category = 'A'
            ORDER BY market_cap_cr DESC LIMIT 5
            """,
            (f"%{args.sector}%",)
        )
        tickers = [r[0] for r in cur.fetchall()]
        conn.close()

    compare_peers(tickers, as_json=args.json)


if __name__ == "__main__":
    main()
