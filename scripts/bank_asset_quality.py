"""
Sourced, point-in-time bank asset quality (NPL ratio, capital adequacy).

These figures are published only in banks' annual reports / Bangladesh Bank documents, not in any structured
DSE feed, so they are recorded by hand — but every row must carry the period it describes, the date it became
public and the document it came from. Screeners read the latest row public on or before their as-of date.
Nothing is ever inferred: a bank without a sourced row is "unverified", never safe and never toxic.

Usage:
  python scripts/bank_asset_quality.py add TICKER PERIOD_END PUBLISHED_DATE --npl 4.2 [--car 13.1] --source URL
  python scripts/bank_asset_quality.py list [TICKER]
"""

from __future__ import annotations

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
BANK_SECTORS = ("Bank", "Banking")

SCHEMA = """
CREATE TABLE IF NOT EXISTS bank_asset_quality (
    ticker          TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    published_date  TEXT NOT NULL,
    npl_pct         REAL,
    car_pct         REAL,
    source_url      TEXT NOT NULL,
    entered_at      TEXT NOT NULL,
    PRIMARY KEY (ticker, period_end),
    CHECK (published_date >= period_end),
    CHECK (npl_pct IS NULL OR (npl_pct >= 0 AND npl_pct <= 100)),
    CHECK (car_pct IS NULL OR car_pct >= -100),
    CHECK (length(source_url) > 8)
);
"""


def is_bank(conn: sqlite3.Connection, ticker: str) -> bool:
    row = conn.execute("SELECT sector FROM companies WHERE ticker = ?", (ticker,)).fetchone()
    return bool(row and row[0] in BANK_SECTORS)


def asset_quality_asof(conn: sqlite3.Connection, ticker: str, asof: str | None = None) -> dict | None:
    """Latest sourced row public on or before asof, or None."""
    asof = asof or datetime.date.today().isoformat()
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'bank_asset_quality'").fetchone():
        return None
    row = conn.execute("""SELECT period_end, published_date, npl_pct, car_pct, source_url FROM bank_asset_quality
                          WHERE ticker = ? AND published_date <= ? ORDER BY period_end DESC LIMIT 1""", (ticker, asof)).fetchone()
    return dict(zip(("period_end", "published_date", "npl_pct", "car_pct", "source_url"), row)) if row else None


def lookup(ticker: str, asof: str | None = None) -> tuple[bool, dict | None]:
    """(is_bank_by_sector, sourced asset quality or None) using a read-only connection."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30.0)
    try:
        return is_bank(conn, ticker), asset_quality_asof(conn, ticker, asof)
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("ticker")
    a.add_argument("period_end")
    a.add_argument("published_date")
    a.add_argument("--npl", type=float)
    a.add_argument("--car", type=float)
    a.add_argument("--source", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("ticker", nargs="?")
    args = ap.parse_args()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.executescript(SCHEMA)
    if args.cmd == "add":
        for d in (args.period_end, args.published_date):
            datetime.date.fromisoformat(d)
        if args.npl is None and args.car is None:
            sys.exit("give --npl and/or --car")
        if not is_bank(conn, args.ticker.upper()):
            sys.exit(f"{args.ticker} is not in a bank sector {BANK_SECTORS}")
        conn.execute("""INSERT OR REPLACE INTO bank_asset_quality VALUES (?,?,?,?,?,?,?)""",
                     (args.ticker.upper(), args.period_end, args.published_date, args.npl, args.car, args.source,
                      datetime.datetime.utcnow().isoformat(timespec="seconds")))
        conn.commit()
        print("recorded", args.ticker.upper(), args.period_end)
    else:
        q = "SELECT * FROM bank_asset_quality" + (" WHERE ticker = ?" if args.ticker else "") + " ORDER BY ticker, period_end"
        for r in conn.execute(q, (args.ticker.upper(),) if args.ticker else ()):
            print(r)
    conn.close()


if __name__ == "__main__":
    main()
