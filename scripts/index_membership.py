"""
Point-in-time index membership.

  DSEX, DS30  captured from the official DSE API (/api/live/index-constituents) on every run; a new snapshot is
              stored only when membership changes, dated with the session it was observed in.
  DSES        DSE does not serve Shariah-index constituents through any API or news feed, so the official list is
              imported by hand with its effective date and the document it came from.

member_asof() answers True/False only when a snapshot of that index effective on or before the date exists;
otherwise None (unknown) — membership is never assumed.

Usage:
  python scripts/index_membership.py capture
  python scripts/index_membership.py import DSES 2026-07-01 --source URL --tickers A B C   (or --file list.txt)
"""

from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path

import requests
import urllib3

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
API = "https://www.dse.com.bd/api/live/index-constituents"
SNAPSHOT_API = "https://www.dse.com.bd/api/live/snapshot"
AUTO_INDICES = ("DSEX", "DS30")
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research client)"}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA = """
CREATE TABLE IF NOT EXISTS index_membership (
    index_code     TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    ticker         TEXT NOT NULL,
    source_url     TEXT NOT NULL,
    captured_at    TEXT NOT NULL,
    PRIMARY KEY (index_code, effective_date, ticker)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _latest_snapshot(conn: sqlite3.Connection, index_code: str, asof: str | None = None) -> tuple[str | None, set]:
    q = "SELECT MAX(effective_date) FROM index_membership WHERE index_code = ?" + (" AND effective_date <= ?" if asof else "")
    eff = conn.execute(q, (index_code, asof) if asof else (index_code,)).fetchone()[0]
    if not eff:
        return None, set()
    return eff, {r[0] for r in conn.execute(
        "SELECT ticker FROM index_membership WHERE index_code = ? AND effective_date = ?", (index_code, eff))}


def member_asof(conn: sqlite3.Connection, index_code: str, ticker: str, asof: str) -> bool | None:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'index_membership'").fetchone():
        return None
    eff, members = _latest_snapshot(conn, index_code, asof)
    return None if eff is None else ticker.upper() in members


def store_snapshot(conn: sqlite3.Connection, index_code: str, effective_date: str, tickers: set, source_url: str) -> bool:
    """Store a snapshot only if membership differs from the latest one on or before effective_date."""
    ensure_schema(conn)
    _, prev = _latest_snapshot(conn, index_code, effective_date)
    if prev == tickers:
        return False
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    conn.executemany("INSERT OR REPLACE INTO index_membership VALUES (?,?,?,?,?)",
                     [(index_code, effective_date, t, source_url, now) for t in sorted(tickers)])
    conn.commit()
    return True


def capture(conn: sqlite3.Connection) -> dict:
    sess = requests.get(SNAPSHOT_API, headers=HEADERS, timeout=60, verify=False).json()["prices"].get("session")  # nosec B501
    session = sess.get("sessionDate") if isinstance(sess, dict) else None
    if not session:
        raise ValueError("DSE live feed returned no sessionDate; refusing to date index snapshots")
    out = {"session": session}
    for code in AUTO_INDICES:
        rows = requests.get(API, params={"code": code}, headers=HEADERS, timeout=60, verify=False).json().get("rows", [])  # nosec B501
        tickers = {r["code"].strip().upper() for r in rows if r.get("code")}
        if not tickers:
            out[code] = "empty response; nothing stored"
            continue
        changed = store_snapshot(conn, code, session, tickers, f"{API}?code={code}")
        out[code] = {"members": len(tickers), "new_snapshot": changed}
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("capture")
    imp = sub.add_parser("import")
    imp.add_argument("index_code")
    imp.add_argument("effective_date")
    imp.add_argument("--source", required=True)
    imp.add_argument("--tickers", nargs="*")
    imp.add_argument("--file")
    args = ap.parse_args()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    ensure_schema(conn)
    if args.cmd == "capture":
        print(json.dumps(capture(conn)))
    else:
        datetime.date.fromisoformat(args.effective_date)
        tickers = set(t.upper() for t in (args.tickers or []))
        if args.file:
            tickers |= {ln.strip().upper() for ln in open(args.file, encoding="utf-8") if ln.strip()}
        known = {r[0] for r in conn.execute("SELECT ticker FROM companies")}
        unknown = sorted(tickers - known)
        if not tickers or unknown or len(args.source) < 9:
            sys.exit(f"refused: empty list, bad source, or unknown tickers {unknown}")
        print("stored" if store_snapshot(conn, args.index_code.upper(), args.effective_date, tickers, args.source)
              else "unchanged")
    conn.close()


if __name__ == "__main__":
    main()
