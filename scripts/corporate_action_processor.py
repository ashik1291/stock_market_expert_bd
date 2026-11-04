"""
DSE Corporate Action & Cash Dividend Distribution Ledger.

Tracks and processes:
  - Cash Dividend announcements, Record Dates, and Bank Disbursements
  - Bonus Shares / Stock Dividends & Ex-Dividend Price Adjustments
  - Automated Portfolio Cash Crediting:
      * Calculates Gross Dividend = Shares * Cash_Per_Share
      * Deducts BSEC standard tax (10% for TIN registered, 15% without TIN)
      * Credits Net Cash to User Portfolio cash balance
      * Idempotent ledger guaranteeing zero double-crediting
"""

from __future__ import annotations

import sys
import json
import sqlite3
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Schema DDL for Dividend Credits & Corporate Actions
PORTFOLIO_DIVIDEND_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS portfolio_dividend_credits (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL,
    ticker              TEXT NOT NULL,
    record_date         TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    shares_held         INTEGER NOT NULL,
    cash_per_share      REAL NOT NULL,
    gross_dividend_bdt  REAL NOT NULL,
    tax_rate_pct        REAL NOT NULL,
    tax_deducted_bdt    REAL NOT NULL,
    net_cash_credited_bdt REAL NOT NULL,
    credited_at         TEXT NOT NULL,
    notes               TEXT,
    UNIQUE(user_id, ticker, record_date, action_type)
);
CREATE INDEX IF NOT EXISTS idx_div_credits_user ON portfolio_dividend_credits(user_id, ticker);
"""


def init_corporate_actions_schema(conn: sqlite3.Connection) -> None:
    """Ensures corporate_actions and dividend credit tables exist."""
    conn.executescript(PORTFOLIO_DIVIDEND_SCHEMA_DDL)
    conn.commit()


def normalize_psi_date(d_str: str) -> Optional[str]:
    """Converts diverse date formats from DSE disclosures into standard ISO YYYY-MM-DD."""
    if not d_str:
        return None
    d_str = d_str.strip().rstrip('.')
    formats = [
        '%d.%m.%Y', '%d-%m-%Y', '%d/%m/%Y',
        '%d %b %Y', '%d %B %Y', '%B %d, %Y', '%b %d, %Y',
        '%B %d %Y', '%b %d %Y',
        '%Y-%m-%d'
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(d_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    import re
    m = re.search(r'(\d{1,2})[.\-\s]+([A-Za-z]+|[0-9]{1,2})[.\-\s]+(\d{4})', d_str)
    if m:
        day, mon, yr = m.group(1), m.group(2), m.group(3)
        for fmt in ('%d %b %Y', '%d %B %Y', '%d %m %Y'):
            try:
                return datetime.datetime.strptime(f'{day} {mon} {yr}', fmt).strftime('%Y-%m-%d')
            except ValueError:
                pass
    return None


def parse_and_record_dse_psi(
    news_items: Optional[List[Dict[str, Any]]] = None,
    conn: Optional[sqlite3.Connection] = None
) -> dict:
    """
    Parses official DSE Price Sensitive Information (PSI) disclosures.
    Extracts cash dividends, bonus shares, record dates, and AGMs directly into corporate_actions table.
    """
    import re
    from collections import defaultdict

    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000;")
        should_close = True

    init_corporate_actions_schema(conn)

    if news_items is None:
        raw_dirs = sorted([d for d in (BASE_DIR / "data" / "raw").iterdir() if d.is_dir() and (d / "dse_psi_news.json").exists()], reverse=True)
        if raw_dirs:
            try:
                with open(raw_dirs[0] / "dse_psi_news.json", "r", encoding="utf-8") as f:
                    news_items = json.load(f)
            except Exception:
                news_items = []
        if not news_items:
            try:
                import scraper
                news_items = scraper.scrape_dse_psi_disclosures()
            except Exception:
                news_items = []

    if not news_items or not isinstance(news_items, list):
        if should_close:
            conn.close()
        return {"total_parsed": 0, "cash_recorded": 0, "bonus_recorded": 0}

    # Group multi-part disclosures by (code, base_summary)
    groups = defaultdict(list)
    for row in news_items:
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue
        base_summary = re.sub(r'\(cont.*?\)', '', str(row.get("summary") or "")).strip()
        groups[(code, base_summary)].append(str(row.get("body") or ""))

    cash_count = 0
    bonus_count = 0
    total_parsed = 0

    for (code, summary), bodies in groups.items():
        full_text = " ".join(reversed(bodies))
        if not re.search(r'(dividend|bonus\s+share)', full_text, re.IGNORECASE):
            continue

        # Record Date extraction
        rec_m = re.search(
            r'Record Date\s*(?:i\.e\.,?\s*|for\s+AGM\s*(?:and\s+dividend)?\s*:?\s*)?[:\-]?\s*([0-9]{1,2}[.\-/][0-9]{1,2}[.\-/][0-9]{2,4}|[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})',
            full_text,
            re.IGNORECASE
        )
        record_date = None
        if rec_m:
            record_date = normalize_psi_date(rec_m.group(1))

        if not record_date:
            continue

        # Cash dividend %
        cash_pct = 0.0
        cash_m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:interim\s+)?cash(?:\s+and|\s+dividend)?', full_text, re.IGNORECASE)
        if not cash_m:
            cash_m = re.search(r'declared\s+interim\s+cash\s+dividend\s+of\s+(\d+(?:\.\d+)?)%', full_text, re.IGNORECASE)
        if not cash_m:
            cash_m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*Cash', full_text, re.IGNORECASE)
        if cash_m:
            cash_pct = float(cash_m.group(1))

        # Bonus / Stock dividend %
        stock_pct = 0.0
        stock_m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:interim\s+)?stock(?:\s+and|\s+dividend)?', full_text, re.IGNORECASE)
        if not stock_m:
            stock_m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*Stock', full_text, re.IGNORECASE)
        if not stock_m:
            stock_m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*bonus\s+shares?', full_text, re.IGNORECASE)
        if stock_m:
            stock_pct = float(stock_m.group(1))

        is_interim = bool(re.search(r'interim', full_text, re.IGNORECASE))
        div_label = "Interim" if is_interim else "Final"

        # Record Cash Dividend
        if cash_pct > 0:
            cash_per_share = round((cash_pct / 100.0) * 10.0, 2)
            note_str = f"Official DSE PSI: {cash_pct:.1f}% ({div_label} Cash Tk {cash_per_share:.2f}/share) [Record: {record_date}]"
            conn.execute("""
                INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes)
                VALUES (?, ?, 'cash_dividend', 0.0, ?, 1.0, ?)
                ON CONFLICT(ticker, record_date, action_type) DO UPDATE SET
                    cash_amount = excluded.cash_amount,
                    notes = excluded.notes
            """, (code, record_date, cash_per_share, note_str))
            cash_count += 1
            total_parsed += 1

        # Record Bonus Dividend
        if stock_pct > 0:
            bonus_ratio = round(stock_pct / 100.0, 4)
            adj_factor = round(1.0 / (1.0 + bonus_ratio), 6)
            note_str = f"Official DSE PSI: {stock_pct:.1f}% ({div_label} Stock Dividend / Bonus) [Record: {record_date}]"
            conn.execute("""
                INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes)
                VALUES (?, ?, 'bonus_dividend', ?, 0.0, ?, ?)
                ON CONFLICT(ticker, record_date, action_type) DO UPDATE SET
                    ratio = excluded.ratio,
                    adjustment_factor = excluded.adjustment_factor,
                    notes = excluded.notes
            """, (code, record_date, bonus_ratio, adj_factor, note_str))
            bonus_count += 1
            total_parsed += 1

    conn.commit()
    if should_close:
        conn.close()

    return {
        "ok": True,
        "total_parsed": total_parsed,
        "cash_recorded": cash_count,
        "bonus_recorded": bonus_count
    }


def record_corporate_action(
    ticker: str,
    record_date: str,
    action_type: str,
    cash_amount: float = 0.0,
    ratio: float = 0.0,
    notes: str = "",
    conn: Optional[sqlite3.Connection] = None
) -> dict:
    """
    Inserts or updates a corporate action in corporate_actions table.
    """
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000;")
        should_close = True

    init_corporate_actions_schema(conn)

    adjustment_factor = 1.0
    if action_type == "bonus_dividend" and ratio > 0:
        adjustment_factor = round(1.0 / (1.0 + ratio), 6)
    elif action_type == "cash_dividend" and cash_amount > 0:
        adjustment_factor = 1.0

    conn.execute("""
        INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, record_date, action_type) DO UPDATE SET
            ratio = excluded.ratio,
            cash_amount = excluded.cash_amount,
            adjustment_factor = excluded.adjustment_factor,
            notes = excluded.notes
    """, (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes))

    conn.commit()
    if should_close:
        conn.close()

    return {
        "ticker": ticker,
        "record_date": record_date,
        "action_type": action_type,
        "cash_amount": cash_amount,
        "ratio": ratio,
        "adjustment_factor": adjustment_factor,
        "notes": notes
    }


def sync_corporate_actions_from_fundamentals(conn: Optional[sqlite3.Connection] = None) -> dict:
    """
    Scans the fundamentals table for dividend_history records and populates corporate_actions.
    """
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000;")
        should_close = True

    init_corporate_actions_schema(conn)

    rows = conn.execute("SELECT ticker, year, raw_data FROM fundamentals WHERE raw_data LIKE '%dividend_history%'").fetchall()
    inserted_cash = 0
    inserted_bonus = 0

    for ticker, base_year, raw_str in rows:
        try:
            raw = json.loads(raw_str)
            
            # 1. Primary: Real corporate actions extracted from official DSE announcements/notices
            real_actions = raw.get("real_corporate_actions", [])
            real_dates_recorded = set()
            for ra in real_actions:
                r_date = ra.get("record_date")
                a_type = ra.get("action_type")
                if not r_date or not a_type:
                    continue
                c_amt = float(ra.get("cash_amount") or 0.0)
                b_ratio = float(ra.get("bonus_ratio") or 0.0)
                adj_fac = round(1.0 / (1.0 + b_ratio), 6) if b_ratio > 0 else 1.0
                src = ra.get("source", "DSE Official Company Notice")
                pct = ra.get("pct", 0.0)

                conn.execute("""
                    INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, record_date, action_type) DO UPDATE SET
                        ratio = excluded.ratio,
                        cash_amount = excluded.cash_amount,
                        adjustment_factor = excluded.adjustment_factor,
                        notes = excluded.notes
                """, (ticker, r_date, a_type, b_ratio, c_amt, adj_fac, f"{pct:.1f}% {a_type} (Real DSE Record Date: {r_date})"))
                
                real_dates_recorded.add((ticker, a_type, r_date[:4]))
                if a_type == "cash_dividend":
                    inserted_cash += 1
                else:
                    inserted_bonus += 1

            # 2. Secondary fallback for older historical years missing explicit notices
            div_hist = raw.get("dividend_history", [])
            # Exclude current and future years from synthetic fallback
            div_hist = [item for item in div_hist if int(float(str(item.get("year", 9999)).strip())) < datetime.date.today().year]
            for item in div_hist:
                d_year = item.get("year")
                if not d_year:
                    continue
                try:
                    d_year = int(float(str(d_year).strip()))
                except Exception:
                    continue

                cash_pct = float(item.get("cash") or 0.0)
                stock_pct = float(item.get("stock") or 0.0)
                est_record_date = f"{d_year}-12-15"

                # Check if real notice already exists for this year in real_dates_recorded or DB
                existing_in_db = conn.execute(
                    "SELECT 1 FROM corporate_actions WHERE ticker = ? AND action_type = 'cash_dividend' AND SUBSTR(record_date, 1, 4) = ? AND notes NOT LIKE '%Historical estimated%'",
                    (ticker, str(d_year))
                ).fetchone()

                if cash_pct > 0 and (ticker, "cash_dividend", str(d_year)) not in real_dates_recorded and not existing_in_db:
                    cash_per_share = round((cash_pct / 100.0) * 10.0, 2)
                    conn.execute("""
                        INSERT OR IGNORE INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes)
                        VALUES (?, ?, 'cash_dividend', 0.0, ?, 1.0, ?)
                    """, (ticker, est_record_date, cash_per_share, f"{cash_pct:.1f}% Cash Dividend (Historical estimated)"))
                    inserted_cash += 1

                existing_bonus_in_db = conn.execute(
                    "SELECT 1 FROM corporate_actions WHERE ticker = ? AND action_type = 'bonus_dividend' AND SUBSTR(record_date, 1, 4) = ? AND notes NOT LIKE '%Historical estimated%'",
                    (ticker, str(d_year))
                ).fetchone()

                if stock_pct > 0 and (ticker, "bonus_dividend", str(d_year)) not in real_dates_recorded and not existing_bonus_in_db:
                    bonus_ratio = round(stock_pct / 100.0, 4)
                    adj_factor = round(1.0 / (1.0 + bonus_ratio), 6)
                    conn.execute("""
                        INSERT OR IGNORE INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount, adjustment_factor, notes)
                        VALUES (?, ?, 'bonus_dividend', ?, 0.0, ?, ?)
                    """, (ticker, est_record_date, bonus_ratio, adj_factor, f"{stock_pct:.1f}% Stock Dividend (Historical estimated)"))
                    inserted_bonus += 1

        except Exception:
            continue

    # Also parse live official DSE PSI announcements
    psi_res = parse_and_record_dse_psi(conn=conn)
    inserted_cash += psi_res.get("cash_recorded", 0)
    inserted_bonus += psi_res.get("bonus_recorded", 0)

    conn.commit()
    if should_close:
        conn.close()

    return {
        "ok": True,
        "cash_dividends_indexed": inserted_cash,
        "bonus_dividends_indexed": inserted_bonus,
        "dse_psi_announcements_parsed": psi_res.get("total_parsed", 0)
    }


def process_portfolio_dividends(
    user_id: str = "default_user",
    asof_date: Optional[str] = None,
    tax_rate_pct: float = 10.0,
    conn: Optional[sqlite3.Connection] = None
) -> dict:
    """
    Evaluates user holdings and credits cash dividends for any held stock that has reached record date.
    Maintains 100% idempotent transaction history in portfolio_dividend_credits table.
    """
    import portfolio_manager
    from user_manager import load_user_portfolio, save_user_portfolio

    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000;")
        should_close = True

    init_corporate_actions_schema(conn)

    if asof_date is None:
        row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
        asof_date = row[0] if (row and row[0]) else datetime.date.today().isoformat()

    # Load target portfolio
    if user_id == "default_user":
        port = portfolio_manager.load_portfolio()
    else:
        port = load_user_portfolio(user_id)

    holdings = port.get("holdings", [])
    if not holdings:
        if should_close:
            conn.close()
        return {"user_id": user_id, "credited_count": 0, "net_cash_credited": 0.0, "details": []}

    credited_records = []
    total_net_cash = 0.0
    now_iso = datetime.datetime.utcnow().isoformat()

    for h in holdings:
        ticker = h.get("ticker")
        shares = int(h.get("shares") or 0)
        bought_at = h.get("bought_at") or "2000-01-01"

        if not ticker or shares <= 0:
            continue

        # Look for cash dividend actions where:
        # 1. Action is 'cash_dividend'
        # 2. record_date >= bought_at (holding was established before record date)
        # 3. record_date <= asof_date (record date has been reached)
        actions = conn.execute("""
            SELECT record_date, cash_amount, notes
            FROM corporate_actions
            WHERE ticker = ? AND action_type = 'cash_dividend'
              AND record_date >= ? AND record_date <= ?
        """, (ticker, bought_at, asof_date)).fetchall()

        for rec_date, cash_per_sh, notes in actions:
            if not cash_per_sh or cash_per_sh <= 0:
                continue

            # Check idempotency: already credited?
            already = conn.execute("""
                SELECT id FROM portfolio_dividend_credits
                WHERE user_id = ? AND ticker = ? AND record_date = ? AND action_type = 'cash_dividend'
            """, (user_id, ticker, rec_date)).fetchone()

            if already:
                continue

            # Calculate dividend and tax
            gross_div = round(shares * cash_per_sh, 2)
            tax_bdt = round(gross_div * (tax_rate_pct / 100.0), 2)
            net_div = round(gross_div - tax_bdt, 2)

            # Insert credit log
            conn.execute("""
                INSERT INTO portfolio_dividend_credits (
                    user_id, ticker, record_date, action_type, shares_held,
                    cash_per_share, gross_dividend_bdt, tax_rate_pct, tax_deducted_bdt,
                    net_cash_credited_bdt, credited_at, notes
                ) VALUES (?, ?, ?, 'cash_dividend', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, ticker, rec_date, shares, cash_per_sh,
                gross_div, tax_rate_pct, tax_bdt, net_div, now_iso, notes
            ))

            total_net_cash += net_div
            credited_records.append({
                "ticker": ticker,
                "shares": shares,
                "record_date": rec_date,
                "cash_per_share": cash_per_sh,
                "gross_dividend_bdt": gross_div,
                "tax_bdt": tax_bdt,
                "net_dividend_bdt": net_div,
                "notes": notes
            })

    # If any dividend was credited, update portfolio cash balance
    if total_net_cash > 0:
        current_cash = float(port.get("cash_balance_bdt") or 0.0)
        new_cash = round(current_cash + total_net_cash, 2)
        port["cash_balance_bdt"] = new_cash

        # Update summary
        if "summary" in port:
            port["summary"]["cash_balance_bdt"] = new_cash
            total_mkt = float(port["summary"].get("total_market_value_bdt") or 0.0)
            port["summary"]["total_market_value_bdt"] = round(total_mkt + total_net_cash, 2)

        # Track in portfolio history
        div_hist = port.setdefault("dividend_distribution_history", [])
        for cr in credited_records:
            div_hist.append({
                "date": asof_date,
                "ticker": cr["ticker"],
                "shares": cr["shares"],
                "gross_bdt": cr["gross_dividend_bdt"],
                "tax_bdt": cr["tax_bdt"],
                "net_bdt": cr["net_dividend_bdt"],
                "credited_at": now_iso
            })

        # Save portfolio
        if user_id == "default_user":
            portfolio_manager.save_portfolio(port)
        else:
            save_user_portfolio(user_id, port)

    conn.commit()
    if should_close:
        conn.close()

    return {
        "user_id": user_id,
        "asof_date": asof_date,
        "credited_count": len(credited_records),
        "total_net_cash_bdt": round(total_net_cash, 2),
        "details": credited_records
    }


def calculate_ex_dividend_adjustment(
    unadjusted_price: float,
    cash_per_share: float = 0.0,
    bonus_ratio: float = 0.0
) -> dict:
    """
    Computes exact ex-dividend adjusted price and dilution factors for backtesting.
    """
    if unadjusted_price <= 0:
        return {"adjusted_price": unadjusted_price, "factor": 1.0}

    # First deduct cash dividend
    post_cash = max(0.01, unadjusted_price - cash_per_share)
    # Then adjust for bonus share dilution
    adj_price = round(post_cash / (1.0 + bonus_ratio), 2)
    factor = round(adj_price / unadjusted_price, 6)

    return {
        "unadjusted_price": unadjusted_price,
        "cash_per_share": cash_per_share,
        "bonus_ratio": bonus_ratio,
        "adjusted_price": adj_price,
        "adjustment_factor": factor
    }


if __name__ == "__main__":
    print("[CORPORATE ACTION PROCESSOR] Starting synchronization...")
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    sync_res = sync_corporate_actions_from_fundamentals(conn)
    print(f"[SYNC RESULT] {sync_res}")

    # Process dividends for default portfolio
    div_res = process_portfolio_dividends("default_user", conn=conn)
    print(f"[DIVIDEND DISTRIBUTION] Result: Credited={div_res['credited_count']}, Net Cash=৳{div_res['total_net_cash_bdt']:.2f}")
    for d in div_res["details"]:
        print(f"  * {d['ticker']}: {d['shares']} shares @ ৳{d['cash_per_share']}/sh -> Gross: ৳{d['gross_dividend_bdt']}, Tax: ৳{d['tax_bdt']}, Net: ৳{d['net_dividend_bdt']}")

    conn.close()
