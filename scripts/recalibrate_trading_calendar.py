"""
scripts/recalibrate_trading_calendar.py
---------------------------------------
Backfills and validates a dense, continuous trading calendar for DSE from 2012 to 2027.
Ensures every calendar date is present:
  - is_trading_day = 1 for confirmed historical trading sessions
  - is_trading_day = 0 for weekends (Friday & Saturday) and public/bank holidays
"""

import sqlite3
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def recalibrate_trading_calendar():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cur = conn.cursor()

    # 1. Fetch all distinct trading dates from prices
    cur.execute("SELECT DISTINCT date FROM prices WHERE close > 0")
    prices_trading_dates = {r[0] for r in cur.fetchall()}

    # 2. Determine bounds
    start_date = datetime.date.fromisoformat("2012-10-01")
    end_date = datetime.date.fromisoformat("2027-12-31")
    total_days = (end_date - start_date).days + 1

    print(f"[CALENDAR] Recalibrating continuous DSE calendar: {start_date} to {end_date} ({total_days} total days)...")

    # 3. Read existing calendar dates
    cur.execute("SELECT date, is_trading_day FROM trading_calendar")
    existing_calendar = {r[0]: r[1] for r in cur.fetchall()}

    inserted_non_trading = 0
    updated_trading = 0

    for i in range(total_days):
        d = start_date + datetime.timedelta(days=i)
        d_str = d.isoformat()
        wd = d.weekday()  # Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6

        is_trading = 1 if d_str in prices_trading_dates else 0

        # For future dates past prices (e.g. late 2026/2027), preserve existing or use weekend rule
        if d_str not in prices_trading_dates and d_str > "2026-11-01":
            if d_str in existing_calendar:
                is_trading = existing_calendar[d_str]
            else:
                is_trading = 0 if wd in (4, 5) else 1

        if is_trading == 0:
            if wd in (4, 5):
                stype = "closed"
                notes = "Weekend (DSE Closed)"
            else:
                stype = "holiday"
                notes = "Public / Bank / Eid Holiday"
        else:
            stype = "regular"
            notes = "Active Trading Session"

        if d_str not in existing_calendar:
            cur.execute("""
                INSERT INTO trading_calendar (date, is_trading_day, session_type, total_volume, total_trades, notes)
                VALUES (?, ?, ?, 0, 0, ?)
            """, (d_str, is_trading, stype, notes))
            if is_trading == 0:
                inserted_non_trading += 1
            else:
                updated_trading += 1
        else:
            # Reconcile if marked trading but was not in prices and was a weekend
            if existing_calendar[d_str] == 1 and d_str not in prices_trading_dates and wd in (4, 5) and d_str <= "2026-11-01":
                cur.execute("""
                    UPDATE trading_calendar SET is_trading_day = 0, session_type = 'closed', notes = 'Weekend (DSE Closed)'
                    WHERE date = ?
                """, (d_str,))
                inserted_non_trading += 1

    conn.commit()

    # Audit final state
    cur.execute("SELECT COUNT(*) FROM trading_calendar")
    total_recs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM trading_calendar WHERE is_trading_day = 1")
    trading_recs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM trading_calendar WHERE is_trading_day = 0")
    non_trading_recs = cur.fetchone()[0]

    conn.close()

    print(f"[CALENDAR] Recalibration complete! Inserted {inserted_non_trading} non-trading dates.")
    print(f"[CALENDAR] Final Database Counts -> Total: {total_recs} | Trading Days: {trading_recs} | Non-Trading: {non_trading_recs}")
    return {
        "total_records": total_recs,
        "trading_days": trading_recs,
        "non_trading_days": non_trading_recs,
        "inserted_non_trading": inserted_non_trading
    }


if __name__ == "__main__":
    recalibrate_trading_calendar()
