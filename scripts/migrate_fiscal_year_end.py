"""
scripts/migrate_fiscal_year_end.py — Re-anchor fundamentals_pit periods to each company's real fiscal year end.

Rows were written assuming a July-June fiscal year for every company. For calendar-year (and
March) companies this put annual snapshots six months early, which made results tradable
before they were published. This migration:
  * stores companies.fiscal_year_end_month (derived from interim period ends, else sector rule),
  * moves annual snapshot_date to the true fiscal year end (dropping a row if the true period already exists),
  * relabels interim fiscal_year from the actual period end,
  * clears the dates of every moved row and flags it estimated, so pit_disclosure_resolver
    re-dates it (rows with no tradable_date are invisible to as-of reads until then).
Observed live_scrape rows are left untouched. Idempotent.

Usage:
  python scripts/migrate_fiscal_year_end.py            # dry run
  python scripts/migrate_fiscal_year_end.py --apply    # apply, then re-run the PIT resolver
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from db import get_db_connection  # noqa: E402
from processor import fiscal_year_end_month, fiscal_quarter_end, fiscal_year_of  # noqa: E402

DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def _latest_interim_payload(conn, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT raw_data FROM fundamentals WHERE ticker = ? AND raw_data LIKE '%periodEnds%' ORDER BY id DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def migrate(apply: bool) -> dict:
    conn = get_db_connection(DB_PATH)
    stats = Counter()
    fye_dist = Counter()
    try:
        tickers = [r[0] for r in conn.execute("SELECT ticker FROM companies")]
        fye = {}
        for t in tickers:
            fye[t] = fiscal_year_end_month(conn, t, _latest_interim_payload(conn, t))
            fye_dist[fye[t]] += 1

        rows = conn.execute("""
            SELECT id, ticker, snapshot_date, fiscal_year, fiscal_quarter, filing_type
            FROM fundamentals_pit
            WHERE COALESCE(publication_source, '') NOT IN ('live_scrape', 'dse_disclosure')
        """).fetchall()
        existing = {(r[1], r[2]) for r in conn.execute("SELECT id, ticker, snapshot_date FROM fundamentals_pit")}

        for pid, t, snap, fy, fq, ftype in rows:
            m = fye.get(t, 6)
            if fq == 4 and fy:
                target = fiscal_quarter_end(int(fy), 4, m)
                if target == snap:
                    continue
                if (t, target) in existing:
                    stats["annual_duplicate_dropped"] += 1
                    if apply:
                        conn.execute("DELETE FROM fundamentals_pit WHERE id = ?", (pid,))
                else:
                    stats["annual_snapshot_moved"] += 1
                    existing.discard((t, snap))
                    existing.add((t, target))
                    if apply:
                        conn.execute(
                            "UPDATE fundamentals_pit SET snapshot_date = ?, publication_date = NULL, tradable_date = NULL, "
                            "publication_is_estimated = 1 WHERE id = ?",
                            (target, pid),
                        )
            elif fq in (1, 2, 3) and snap:
                new_fy = fiscal_year_of(str(snap)[:10], m)
                if new_fy != fy:
                    stats["interim_fiscal_year_relabelled"] += 1
                    if apply:
                        conn.execute(
                            "UPDATE fundamentals_pit SET fiscal_year = ?, publication_is_estimated = 1 WHERE id = ?",
                            (new_fy, pid),
                        )
        if apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    return {"applied": apply, "fiscal_year_end_months": dict(fye_dist), **stats}


if __name__ == "__main__":
    print(json.dumps(migrate("--apply" in sys.argv), indent=2))
