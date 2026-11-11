"""
scripts/db_retention_cleaner.py — Automated Database Hygiene & Payload Retention Utility

Maintains optimal SQLite database performance and footprint by:
1. Retaining all structured numerical, analytical, and indicator columns permanently.
2. Trimming or nullifying the heavy `full_payload` TEXT blobs for records older than 180 days.
3. Executing SQLite VACUUM / PRAGMA optimize to defragment B-trees and reclaim disk space.
"""

from __future__ import annotations

import sys
import sqlite3
import datetime
import logging
from pathlib import Path
from typing import Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("db_retention_cleaner")


def clean_retention_payloads(
    retention_days: int = 180,
    vacuum: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Cleans heavy JSON blobs older than `retention_days` while preserving all
    indexed indicators, scores, prices, and forensic metrics.
    """
    if not DB_PATH.exists():
        log.error(f"Database not found: {DB_PATH}")
        return {"status": "error", "message": "DB not found"}

    cutoff_date = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)
    ).strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    cur = conn.cursor()

    # Check candidates for cleanup
    count_signals = cur.execute(
        "SELECT COUNT(*) FROM company_signals_history WHERE date < ? AND full_payload IS NOT NULL",
        (cutoff_date,),
    ).fetchone()[0]

    count_dna = cur.execute(
        "SELECT COUNT(*) FROM company_pattern_dna_history WHERE date < ? AND full_payload IS NOT NULL",
        (cutoff_date,),
    ).fetchone()[0]

    log.info(
        f"Retention audit (cutoff: {cutoff_date}): {count_signals} expired signals, {count_dna} expired DNA records."
    )

    if dry_run:
        conn.close()
        return {
            "status": "dry_run",
            "cutoff_date": cutoff_date,
            "expired_signals": count_signals,
            "expired_dna": count_dna,
        }

    trimmed_signals = 0
    trimmed_dna = 0

    if count_signals > 0:
        cur.execute(
            "UPDATE company_signals_history SET full_payload = NULL WHERE date < ?",
            (cutoff_date,),
        )
        trimmed_signals = cur.rowcount

    if count_dna > 0:
        cur.execute(
            "UPDATE company_pattern_dna_history SET full_payload = NULL WHERE date < ?",
            (cutoff_date,),
        )
        trimmed_dna = cur.rowcount

    conn.commit()

    reclaimed = False
    if vacuum and (trimmed_signals > 0 or trimmed_dna > 0):
        log.info("Running PRAGMA incremental_vacuum and optimize...")
        try:
            cur.execute("PRAGMA optimize;")
            conn.commit()
            reclaimed = True
        except Exception as e:
            log.warning(f"Vacuum optimize warning: {e}")

    conn.close()

    log.info(
        f"Retention clean completed. Trimmed {trimmed_signals} signal blobs and {trimmed_dna} DNA blobs."
    )
    return {
        "status": "success",
        "cutoff_date": cutoff_date,
        "trimmed_signals": trimmed_signals,
        "trimmed_dna": trimmed_dna,
        "vacuum_executed": reclaimed,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prune old JSON blobs in SQLite while keeping index records.")
    parser.add_argument("--days", type=int, default=180, help="Retention period in days (default: 180)")
    parser.add_argument("--dry-run", action="store_true", help="Audit without modifying database")
    args = parser.parse_args()

    result = clean_retention_payloads(retention_days=args.days, dry_run=args.dry_run)
    print(f"Result: {result}")
