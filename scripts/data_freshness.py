"""
Data freshness gate — fail-closed when prices lag expected trading calendar.

Exit codes:
  0 = fresh enough (latest price within 1 trading day of expected last session)
  1 = stale (pipeline should abort)
  2 = DB / calendar unavailable
"""

from __future__ import annotations

import datetime
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

# Max trading sessions prices may lag the expected last session before abort
MAX_STALE_TRADING_DAYS = 1


def _connect():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def latest_price_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(date) AS d FROM prices").fetchone()
    return row["d"] if row and row["d"] else None


def expected_last_trading_day(conn: sqlite3.Connection, asof: datetime.date | None = None) -> str | None:
    """Most recent calendar date <= asof marked as trading day."""
    asof = asof or datetime.date.today()
    row = conn.execute(
        """
        SELECT date FROM trading_calendar
        WHERE date <= ? AND is_trading_day = 1
        ORDER BY date DESC LIMIT 1
        """,
        (asof.isoformat(),),
    ).fetchone()
    if row and row["date"]:
        return row["date"]

    # Fallback: weekend-aware DSE schedule (Sun–Thu) when calendar empty
    d = asof
    for _ in range(14):
        if d.weekday() in (6, 0, 1, 2, 3):  # Sun–Thu
            return d.isoformat()
        d -= datetime.timedelta(days=1)
    return None


def trading_days_between(conn: sqlite3.Connection, start: str, end: str) -> int:
    """Count trading days strictly after start up to and including end."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM trading_calendar
        WHERE date > ? AND date <= ? AND is_trading_day = 1
        """,
        (start, end),
    ).fetchone()
    if row and row["n"] is not None and row["n"] > 0:
        return int(row["n"])

    # Fallback calendar walk
    d0 = datetime.date.fromisoformat(start[:10])
    d1 = datetime.date.fromisoformat(end[:10])
    n = 0
    cur = d0 + datetime.timedelta(days=1)
    while cur <= d1:
        if cur.weekday() in (6, 0, 1, 2, 3):
            n += 1
        cur += datetime.timedelta(days=1)
    return n


def check_freshness(asof: datetime.date | None = None) -> dict:
    """
    Returns status dict:
      ok, latest_price_date, expected_trading_day, stale_trading_days, reason
    """
    conn = _connect()
    if conn is None:
        return {
            "ok": False,
            "latest_price_date": None,
            "expected_trading_day": None,
            "stale_trading_days": None,
            "reason": "dse.db missing",
            "exit_code": 2,
        }

    try:
        latest = latest_price_date(conn)
        expected = expected_last_trading_day(conn, asof)
        if not latest:
            return {
                "ok": False,
                "latest_price_date": None,
                "expected_trading_day": expected,
                "stale_trading_days": None,
                "reason": "no prices in DB",
                "exit_code": 2,
            }
        if not expected:
            return {
                "ok": False,
                "latest_price_date": latest,
                "expected_trading_day": None,
                "stale_trading_days": None,
                "reason": "trading calendar empty / no expected session",
                "exit_code": 2,
            }

        if latest >= expected:
            stale = 0
        else:
            stale = trading_days_between(conn, latest, expected)

        ok = stale <= MAX_STALE_TRADING_DAYS
        reason = (
            f"fresh (latest={latest}, expected={expected}, lag={stale} sessions)"
            if ok
            else f"STALE prices: latest={latest}, expected={expected}, lag={stale} sessions > {MAX_STALE_TRADING_DAYS}"
        )
        return {
            "ok": ok,
            "latest_price_date": latest,
            "expected_trading_day": expected,
            "stale_trading_days": stale,
            "reason": reason,
            "exit_code": 0 if ok else 1,
        }
    finally:
        conn.close()


def assert_fresh_or_exit(label: str = "pipeline") -> dict:
    status = check_freshness()
    print(f"[FRESHNESS/{label}] {status['reason']}", flush=True)
    if not status["ok"]:
        print(f"[FRESHNESS/{label}] ABORT — refresh prices before analysis.", flush=True)
        sys.exit(status["exit_code"])
    return status


if __name__ == "__main__":
    st = check_freshness()
    print(st["reason"])
    sys.exit(st["exit_code"])
