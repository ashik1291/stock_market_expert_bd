"""
scripts/query_stock.py — Universal Cross-Platform Stock Inspector
Runs identically on Windows (PowerShell/CMD), macOS, and Linux.
Provides clean terminal inspection of any DSE ticker or the entire 396-stock market.

Usage:
  python scripts/query_stock.py ACMELAB
  python scripts/query_stock.py GP --limit 10
  python scripts/query_stock.py --all
  python scripts/query_stock.py --sector Pharmaceuticals
  python scripts/query_stock.py --search SQUARE
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path

# Enforce UTF-8 output across Windows, Mac, and Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def get_db():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}. Run 'python main.py ready' to restore.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def list_market_universe(sector: str = None, search: str = None, as_json: bool = False):
    """Lists stocks from the 396 universe with filtering options."""
    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT c.ticker, c.name, c.sector, c.category, c.market_cap_cr,
               f.close, f.pe_ratio, f.dividend_yield, f.rsi_14
        FROM companies c
        LEFT JOIN (
            SELECT ticker, close, pe_ratio, dividend_yield, rsi_14
            FROM features_daily
            WHERE (ticker, date) IN (SELECT ticker, MAX(date) FROM features_daily GROUP BY ticker)
        ) f ON c.ticker = f.ticker
        WHERE 1=1
    """
    params = []
    if sector:
        query += " AND LOWER(c.sector) LIKE LOWER(?)"
        params.append(f"%{sector}%")
    if search:
        query += " AND (LOWER(c.ticker) LIKE LOWER(?) OR LOWER(c.name) LIKE LOWER(?))"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY c.sector, c.ticker"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if as_json:
        print(json.dumps(rows, indent=2, default=str))
        return rows

    title_filter = f" (Sector: {sector})" if sector else (f" (Search: '{search}')" if search else " (All Stocks)")
    print("=" * 85)
    print(f"🏛️ DSE MARKET UNIVERSE DIRECTORY{title_filter} — {len(rows)} Companies Found")
    print("=" * 85)
    print(f"{'Ticker':<12} {'Sector':<20} {'Cat':<5} {'Close (৳)':<11} {'P/E':<8} {'Div%':<8} {'RSI':<7} {'Company Name'}")
    print("-" * 85)

    for r in rows:
        close_str = f"{r['close']:.2f}" if r.get("close") is not None else "N/A"
        pe_str = f"{r['pe_ratio']:.1f}" if r.get("pe_ratio") is not None else "-"
        div_str = f"{r['dividend_yield']:.1f}%" if r.get("dividend_yield") is not None else "-"
        rsi_str = f"{r['rsi_14']:.1f}" if r.get("rsi_14") is not None else "-"
        name_str = (r.get("name") or "")[:28]
        print(f"{r['ticker']:<12} {r.get('sector', 'N/A')[:19]:<20} {r.get('category', '-'):<5} {close_str:<11} {pe_str:<8} {div_str:<8} {rsi_str:<7} {name_str}")

    print("=" * 85)
    print(f"Total: {len(rows)} stocks listed. Run 'python main.py stock <TICKER>' for full profile.")
    return rows


def inspect_stock(ticker: str, limit: int = 5, as_json: bool = False, quiet: bool = False, conn: sqlite3.Connection = None):
    ticker = ticker.strip().upper()
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    cur = conn.cursor()

    # 1. Company Profile
    cur.execute(
        """
        SELECT ticker, name, sector, category, market_cap_cr,
               sponsor_holding_pct, govt_holding_pct, institutional_pct,
               public_holding_pct, free_float_pct, updated_at
        FROM companies
        WHERE ticker = ?
        """,
        (ticker,)
    )
    company = cur.fetchone()

    if not company:
        cur.execute("SELECT ticker FROM companies WHERE ticker LIKE ? LIMIT 5", (f"%{ticker}%",))
        suggestions = [r["ticker"] for r in cur.fetchall()]
        if close_conn:
            conn.close()
        res = {"error": f"Ticker '{ticker}' not found", "suggestions": suggestions}
        if not quiet:
            if as_json:
                print(json.dumps(res))
            else:
                print(f"❌ Ticker '{ticker}' not found in 396-stock DSE universe.")
                if suggestions:
                    print(f"💡 Did you mean: {', '.join(suggestions)}?")
        return res

    company_data = dict(company)

    # 2. Latest Prices (uses B-tree index on ticker and date)
    cur.execute(
        """
        SELECT date, open, high, low, close, volume, value, change, change_pct
        FROM prices
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (ticker, limit)
    )
    prices = [dict(r) for r in cur.fetchall()]

    # 3. Latest Fundamentals
    cur.execute(
        """
        SELECT year, quarter, eps, nav, pe_ratio, debt_equity, dividend_yield, roe, net_profit_cr
        FROM fundamentals
        WHERE ticker = ?
        ORDER BY year DESC, quarter DESC
        LIMIT 1
        """,
        (ticker,)
    )
    fund_row = cur.fetchone()
    fundamentals = dict(fund_row) if fund_row else {}

    # 4. Daily Feature Store & Quantitative Intelligence
    cur.execute(
        """
        SELECT date, close, volume, pe_ratio, debt_equity, dividend_yield, eps, nav, rsi_14, sma_20, sma_50, score, is_eligible
        FROM features_daily
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 1
        """,
        (ticker,)
    )
    feat_row = cur.fetchone()
    features = dict(feat_row) if feat_row else {}

    # 5. Point-in-Time Fundamentals
    cur.execute(
        """
        SELECT tradable_date, publication_date, fiscal_year, fiscal_quarter, eps, nav, pe_ratio, filing_type
        FROM fundamentals_pit
        WHERE ticker = ?
        ORDER BY tradable_date DESC
        LIMIT 2
        """,
        (ticker,)
    )
    pit_data = [dict(r) for r in cur.fetchall()]

    # 6. Corporate Actions & Dividends
    cur.execute(
        """
        SELECT record_date, action_type, ratio, cash_amount, notes
        FROM corporate_actions
        WHERE ticker = ?
        ORDER BY record_date DESC
        LIMIT 5
        """,
        (ticker,)
    )
    actions = [dict(r) for r in cur.fetchall()]

    # 7. Official Announcements & News
    cur.execute(
        """
        SELECT date, headline, source, sentiment_score
        FROM news
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 5
        """,
        (ticker,)
    )
    news = [dict(r) for r in cur.fetchall()]

    if close_conn:
        conn.close()

    result = {
        "company": company_data,
        "prices": prices,
        "fundamentals": fundamentals,
        "features": features,
        "fundamentals_pit": pit_data,
        "corporate_actions": actions,
        "news": news,
    }

    if quiet:
        return result

    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return result

    # Visual Cross-Platform Terminal Output
    print("=" * 80)
    print(f"📊 DSE STOCK INSPECTOR: {company_data['ticker']} — {company_data['name']}")
    print("=" * 80)
    print(f"Sector: {company_data.get('sector', 'N/A')}  |  Category: {company_data.get('category', 'N/A')}  |  Market Cap: ৳{company_data.get('market_cap_cr', 0):,.2f} Cr")
    print(f"Ownership: Sponsor {company_data.get('sponsor_holding_pct', 0)}% | Govt {company_data.get('govt_holding_pct', 0)}% | Inst {company_data.get('institutional_pct', 0)}% | Public {company_data.get('public_holding_pct', 0)}%")
    print("-" * 80)

    pe_val = features.get("pe_ratio") if features.get("pe_ratio") is not None else fundamentals.get("pe_ratio")
    eps_val = features.get("eps") if features.get("eps") is not None else fundamentals.get("eps")
    nav_val = features.get("nav") if features.get("nav") is not None else fundamentals.get("nav")
    div_val = features.get("dividend_yield") if features.get("dividend_yield") is not None else fundamentals.get("dividend_yield")
    debt_val = features.get("debt_equity") if features.get("debt_equity") is not None else fundamentals.get("debt_equity")

    print("Valuation & Quantitative Factor Intelligence:")
    print(f"  * P/E Ratio: {f'{pe_val:.2f}' if isinstance(pe_val, float) else pe_val}  |  EPS: ৳{f'{eps_val:.2f}' if isinstance(eps_val, float) else eps_val}  |  NAV: ৳{f'{nav_val:.2f}' if isinstance(nav_val, float) else nav_val}")
    print(f"  * Dividend Yield: {f'{div_val:.2f}%' if isinstance(div_val, float) else div_val}  |  Debt/Equity: {f'{debt_val:.3f}' if isinstance(debt_val, float) else debt_val}")
    if features.get("rsi_14") is not None:
        rsi = features.get("rsi_14", 0.0)
        sma20 = features.get("sma_20", 0.0)
        sma50 = features.get("sma_50", 0.0)
        print(f"  * Technical Momentum: RSI(14)={rsi:.1f} | SMA(20)=৳{sma20:.2f} | SMA(50)=৳{sma50:.2f}")
    print("-" * 80)

    # Latest Prices Table
    print(f"Recent Price Sessions (Latest {len(prices)} trading days):")
    print(f"{'Date':<12} {'Close (৳)':<11} {'Open (৳)':<11} {'High (৳)':<11} {'Low (৳)':<11} {'Change %':<10} {'Volume':<12}")
    print("-" * 80)
    for p in prices:
        chg = p.get('change_pct') or 0.0
        sign = "+" if chg > 0 else ""
        print(f"{p['date']:<12} {p.get('close', 0.0):<11.2f} {p.get('open', 0.0):<11.2f} {p.get('high', 0.0):<11.2f} {p.get('low', 0.0):<11.2f} {sign}{chg:<9.2f}% {p.get('volume', 0):<12,}")
    print("-" * 80)

    # Corporate Actions
    if actions:
        print(f"Corporate Actions & Dividends ({len(actions)} found):")
        for a in actions:
            cash = f"Cash: ৳{a['cash_amount']}" if a.get('cash_amount') else ""
            notes = f"({a['notes']})" if a.get('notes') else ""
            print(f"  * [Record: {a['record_date']}] {a['action_type'].upper()} {cash} {notes}")
        print("-" * 80)

    # News
    if news:
        print(f"Disclosures & News ({len(news)} items):")
        for n in news:
            print(f"  * [{n['date']}] {n['headline']}")
        print("-" * 80)
    else:
        print("Disclosures & News: No headline matches in current news window.")
        print("-" * 80)

    return result


def main():
    parser = argparse.ArgumentParser(description="Cross-Platform DSE Stock Inspector & Universe Directory")
    parser.add_argument("ticker", nargs="?", default=None, help="Stock ticker symbol (e.g. ACMELAB, GP, SQURPHARMA, BATBC)")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent price sessions to show (default: 5)")
    parser.add_argument("--all", action="store_true", help="List all 396 stocks in the market universe")
    parser.add_argument("--sector", type=str, default=None, help="Filter market by sector name (e.g. Pharmaceuticals, Banking, Food & Allied)")
    parser.add_argument("--search", type=str, default=None, help="Search universe by ticker or company name")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    if args.all or args.sector or args.search or (args.ticker and args.ticker.lower() in ("all", "--all")):
        list_market_universe(sector=args.sector, search=args.search, as_json=args.json)
    else:
        target = args.ticker or "ACMELAB"
        inspect_stock(target, limit=args.limit, as_json=args.json)


if __name__ == "__main__":
    main()
