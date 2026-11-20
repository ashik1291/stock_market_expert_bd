"""
Remove fundamentals rows for fiscal periods that had not ended when they were written, and relabel
rows whose fiscal year/quarter was guessed instead of derived from the company's fiscal year end.

  fundamentals_pit  delete snapshot_date in the future; live_scrape observations are labelled with
                    the last fiscal quarter that ended on or before the observation date
  fundamentals      interim rows are relabelled from the period stored in raw_data; rows whose
                    period end is still in the future and carry no period are deleted

Usage: python scripts/repair_fiscal_labels.py [--apply]
"""

import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from processor import (DB_PATH, _month_end, fiscal_quarter_end, fiscal_year_end_month,  # noqa: E402
                       fiscal_year_of, latest_ended_quarter)


def plan(conn: sqlite3.Connection, today: str) -> dict:
    fye = {}

    def fy_month(t):
        if t not in fye:
            fye[t] = fiscal_year_end_month(conn, t)
        return fye[t]

    pit_delete = [r[0] for r in conn.execute(
        "SELECT id FROM fundamentals_pit WHERE snapshot_date > ?", (today,))]
    pit_relabel = []
    for rid, t, snap, fy, fq in conn.execute(
            "SELECT id, ticker, snapshot_date, fiscal_year, fiscal_quarter FROM fundamentals_pit "
            "WHERE publication_source = 'live_scrape' AND snapshot_date <= ?", (today,)):
        want = latest_ended_quarter(snap, fy_month(t))
        if (fy, fq) != want:
            pit_relabel.append((rid, *want))

    f_delete, f_relabel = [], []
    for rid, t, y, q, raw in conn.execute("SELECT rowid, ticker, year, quarter, raw_data FROM fundamentals"):
        try:
            y, q = int(float(y)), int(float(q))
        except (TypeError, ValueError):
            f_delete.append(rid)
            continue
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {}
        period = str(payload.get("period") or "") if isinstance(payload, dict) else ""
        if period[:6].isdigit() and len(period) >= 6:
            end = _month_end(int(period[:4]), int(period[4:6]))
            want = (fiscal_year_of(end, fy_month(t)), q)
            if end > today:
                f_delete.append(rid)
            elif (y, q) != want:
                f_relabel.append((rid, t, *want))
        elif fiscal_quarter_end(y, q, fy_month(t)) > today:
            f_delete.append(rid)
    return {"pit_delete": pit_delete, "pit_relabel": pit_relabel,
            "fund_delete": f_delete, "fund_relabel": f_relabel}


def apply(conn: sqlite3.Connection, p: dict) -> dict:
    conn.executemany("DELETE FROM fundamentals_pit WHERE id = ?", [(i,) for i in p["pit_delete"]])
    conn.executemany("UPDATE fundamentals_pit SET fiscal_year = ?, fiscal_quarter = ? WHERE id = ?",
                     [(fy, fq, i) for i, fy, fq in p["pit_relabel"]])
    conn.executemany("DELETE FROM fundamentals WHERE rowid = ?", [(i,) for i in p["fund_delete"]])
    merged = 0
    for rid, t, y, q in p["fund_relabel"]:
        if conn.execute("SELECT 1 FROM fundamentals WHERE ticker = ? AND year = ? AND quarter = ?",
                        (t, y, q)).fetchone():
            conn.execute("DELETE FROM fundamentals WHERE rowid = ?", (rid,))
            merged += 1
        else:
            conn.execute("UPDATE fundamentals SET year = ?, quarter = ? WHERE rowid = ?", (y, q, rid))
    conn.commit()
    return {"duplicates_dropped": merged}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    p = plan(conn, today)
    print({k: len(v) for k, v in p.items()})
    if args.apply:
        print(apply(conn, p))
    conn.close()


if __name__ == "__main__":
    main()
