"""
Independent cross-check of stored price bars against DSE's official day-end archive (audit only — never edits values).

For each checked session: every stored bar is compared with the archive bar (open/high/low/close/volume via
repair_price_history.bar_differs). Matching bars get archive_verified_on; differences are recorded per bar in
archive_crosscheck_diffs; per-session totals go to archive_crosscheck. The published match rate is the share of
compared bars that are identical.

Usage:
  python scripts/archive_crosscheck.py --since 2024-01-01
  python scripts/archive_crosscheck.py --sample 120 --before 2024-01-01 --seed 7
  python scripts/archive_crosscheck.py --report
"""

from __future__ import annotations

import argparse
import datetime
import json
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provenance import ensure_schema, mark_archive_verified  # noqa: E402
from repair_price_history import bar_differs, fetch_day_end_all  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "dse.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS archive_crosscheck (
    session_date       TEXT PRIMARY KEY,
    checked_on         TEXT NOT NULL,
    archive_bars       INTEGER NOT NULL,
    compared           INTEGER NOT NULL,
    matched            INTEGER NOT NULL,
    mismatched         INTEGER NOT NULL,
    missing_in_db      INTEGER NOT NULL,
    missing_in_archive INTEGER NOT NULL,
    selection          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS archive_crosscheck_diffs (
    session_date  TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    reason        TEXT NOT NULL,
    stored        TEXT,
    archive       TEXT,
    PRIMARY KEY (session_date, ticker)
);
"""


def check_session(conn: sqlite3.Connection, d: str, selection: str) -> dict | None:
    src = fetch_day_end_all(d)
    if len(src) < 50:
        return None
    known = {r[0] for r in conn.execute("SELECT ticker FROM instruments")} if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'instruments'").fetchone() else set(db_tickers(conn))
    db = {r[0]: r[1:] for r in conn.execute("SELECT ticker, open, high, low, close, volume FROM prices WHERE date = ?", (d,))}
    compared = [t for t in db if t in src]
    diffs = {t: bar_differs(db[t], src[t]) for t in compared}
    matched = [t for t, why in diffs.items() if not why]
    today = datetime.date.today().isoformat()
    with conn:
        conn.execute("DELETE FROM archive_crosscheck_diffs WHERE session_date = ?", (d,))
        conn.executemany("INSERT INTO archive_crosscheck_diffs VALUES (?,?,?,?,?)",
                         [(d, t, why, json.dumps(db[t]),
                           json.dumps([src[t][k] for k in ("open", "high", "low", "close", "volume")]))
                          for t, why in diffs.items() if why])
        mark_archive_verified(conn, [(t, d) for t in matched], today)
        row = (d, today, len(src), len(compared), len(matched), len(compared) - len(matched),
               len([t for t in src if t not in db and t in known]), len([t for t in db if t not in src]), selection)
        conn.execute("INSERT OR REPLACE INTO archive_crosscheck VALUES (?,?,?,?,?,?,?,?,?)", row)
    return dict(zip(("date", "checked_on", "archive_bars", "compared", "matched", "mismatched", "missing_in_db",
                     "missing_in_archive"), row[:8]))


def db_tickers(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT ticker FROM prices")]


def report(conn: sqlite3.Connection) -> dict:
    out = {}
    for sel, n, comp, match, miss_db in conn.execute("""
            SELECT selection, COUNT(*), SUM(compared), SUM(matched), SUM(missing_in_db) FROM archive_crosscheck GROUP BY selection"""):
        out[sel] = {"sessions": n, "bars_compared": comp, "match_rate_pct": round(100.0 * match / comp, 3) if comp else None,
                    "archive_bars_missing_in_db": miss_db}
    out["by_reason"] = dict(conn.execute("SELECT reason, COUNT(*) FROM archive_crosscheck_diffs GROUP BY reason"))
    out["verified_bars_total"] = conn.execute("SELECT COUNT(*) FROM prices WHERE archive_verified_on IS NOT NULL").fetchone()[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--before", default="2024-01-01")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    ensure_schema(conn)
    conn.executescript(SCHEMA)
    sessions = []
    if args.since:
        sessions = [(r[0], f"all_since_{args.since}") for r in conn.execute(
            "SELECT DISTINCT date FROM prices WHERE date >= ? ORDER BY date", (args.since,))]
    elif args.sample:
        pool = [r[0] for r in conn.execute("SELECT DISTINCT date FROM prices WHERE date < ? ORDER BY date", (args.before,))]
        sessions = [(d, f"random_sample_before_{args.before}_seed{args.seed}")
                    for d in sorted(random.Random(args.seed).sample(pool, min(args.sample, len(pool))))]
    done = {r[0] for r in conn.execute("SELECT session_date FROM archive_crosscheck")}
    for i, (d, sel) in enumerate(sessions, 1):
        if d in done:
            continue
        res = check_session(conn, d, sel)
        if i % 25 == 0 or res is None:
            print(f"  {i}/{len(sessions)} {d} -> {res}", flush=True)
    print(json.dumps(report(conn), indent=1))
    conn.close()


if __name__ == "__main__":
    main()
