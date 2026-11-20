"""
Row-level provenance for research-grade data.

  ingest_log           one row per ingest run: source, URL/file, SHA-256 of the raw payload, time, row count
  prices               source (origin of the current values), ingest_id, archive_verified_on (the date the bar was
                       found identical to DSE's official day-end archive), quality_flags (comma list, e.g.
                       volume_imputed, open_missing)
  corporate_actions    source, derived deterministically from the provenance markers every writer puts in notes

Price sources: dse_live_snapshot, dse_day_end_archive, raw_snapshot_rebuild, historical_archive_csv,
legacy_pre_provenance (rows that predate this tracking; their origin was not recorded).

Usage: python scripts/provenance.py backfill [--imputed-from data/processed/dse.pre_audit_fix.bak]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
PROVENANCE_START = "2026-11-20"

INGEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_log (
    ingest_id    TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    source_ref   TEXT,
    raw_sha256   TEXT,
    started_at   TEXT NOT NULL,
    rows         INTEGER,
    note         TEXT
);
"""
COLUMNS = {
    "prices": [("source", "TEXT"), ("ingest_id", "TEXT"), ("archive_verified_on", "TEXT"), ("quality_flags", "TEXT")],
    "corporate_actions": [("source", "TEXT")],
}
CA_SOURCE_SQL = """
UPDATE corporate_actions SET source = CASE
    WHEN notes LIKE '%dse_disclosure%' THEN 'dse_disclosure'
    WHEN notes LIKE '%verified against official DSE dividend history%' THEN 'dse_notice_verified_by_dividend_history'
    WHEN notes LIKE '%Real DSE Record Date%' THEN 'dse_company_page_notice'
    WHEN notes LIKE '%Official DSE PSI%' THEN 'dse_psi_live'
    WHEN notes LIKE '%inferred from price gap%' THEN 'price_gap_inference'
    WHEN lower(notes) LIKE '%estimated%' THEN 'estimated_placeholder'
    ELSE 'legacy_pre_provenance' END
WHERE source IS NULL OR source != CASE
    WHEN notes LIKE '%dse_disclosure%' THEN 'dse_disclosure'
    WHEN notes LIKE '%verified against official DSE dividend history%' THEN 'dse_notice_verified_by_dividend_history'
    WHEN notes LIKE '%Real DSE Record Date%' THEN 'dse_company_page_notice'
    WHEN notes LIKE '%Official DSE PSI%' THEN 'dse_psi_live'
    WHEN notes LIKE '%inferred from price gap%' THEN 'price_gap_inference'
    WHEN lower(notes) LIKE '%estimated%' THEN 'estimated_placeholder'
    ELSE 'legacy_pre_provenance' END
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(INGEST_SCHEMA)
    for table, cols in COLUMNS.items():
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            continue
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    conn.commit()


def sha256_of(payload) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, Path):
        return hashlib.sha256(payload.read_bytes()).hexdigest() if payload.exists() else None
    if not isinstance(payload, (bytes, bytearray)):
        payload = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def new_ingest(conn: sqlite3.Connection, source: str, source_ref: str | None = None, raw=None, note: str | None = None) -> str:
    ensure_schema(conn)
    iid = f"{source[:12]}-{uuid.uuid4().hex[:12]}"
    conn.execute("INSERT INTO ingest_log VALUES (?,?,?,?,?,NULL,?)",
                 (iid, source, source_ref, sha256_of(raw), datetime.datetime.utcnow().isoformat(timespec="seconds"), note))
    return iid


def stamp_prices(conn: sqlite3.Connection, ingest_id: str, source: str, keys: list[tuple[str, str]],
                 verified_on: str | None = None) -> int:
    """Record origin (and archive verification) for the given (ticker, date) bars."""
    ensure_schema(conn)
    conn.executemany("UPDATE prices SET source = ?, ingest_id = ? WHERE ticker = ? AND date = ?",
                     [(source, ingest_id, t, d) for t, d in keys])
    if verified_on:
        conn.executemany("UPDATE prices SET archive_verified_on = ? WHERE ticker = ? AND date = ?",
                         [(verified_on, t, d) for t, d in keys])
    conn.execute("UPDATE ingest_log SET rows = COALESCE(rows, 0) + ? WHERE ingest_id = ?", (len(keys), ingest_id))
    return len(keys)


def stamp_unattributed(conn: sqlite3.Connection, ingest_id: str, source: str, date: str | None = None) -> int:
    """Attribute bars that have no source yet (optionally only one session) to this ingest."""
    ensure_schema(conn)
    q = "UPDATE prices SET source = ?, ingest_id = ? WHERE source IS NULL" + (" AND date = ?" if date else "")
    n = conn.execute(q, (source, ingest_id, date) if date else (source, ingest_id)).rowcount
    conn.execute("UPDATE ingest_log SET rows = COALESCE(rows, 0) + ? WHERE ingest_id = ?", (n, ingest_id))
    return n


def mark_archive_verified(conn: sqlite3.Connection, keys: list[tuple[str, str]], verified_on: str) -> int:
    ensure_schema(conn)
    conn.executemany("UPDATE prices SET archive_verified_on = ? WHERE ticker = ? AND date = ?",
                     [(verified_on, t, d) for t, d in keys])
    return len(keys)


def add_flag(conn: sqlite3.Connection, flag: str, where_sql: str, params: tuple = ()) -> int:
    cur = conn.execute(f"""UPDATE prices SET quality_flags = CASE
                               WHEN quality_flags IS NULL OR quality_flags = '' THEN ?
                               WHEN (',' || quality_flags || ',') LIKE ? THEN quality_flags
                               ELSE quality_flags || ',' || ? END
                           WHERE {where_sql}""", (flag, f"%,{flag},%", flag, *params))
    return cur.rowcount


def classify_corporate_action_sources(conn: sqlite3.Connection) -> int:
    ensure_schema(conn)
    return conn.execute(CA_SOURCE_SQL).rowcount


def backfill(conn: sqlite3.Connection, imputed_from: Path | None) -> dict:
    ensure_schema(conn)
    out = {}
    iid = new_ingest(conn, "legacy_pre_provenance", note="rows that existed before provenance tracking began")
    out["legacy_prices"] = conn.execute("UPDATE prices SET source = 'legacy_pre_provenance', ingest_id = ? WHERE source IS NULL",
                                        (iid,)).rowcount
    conn.execute("UPDATE ingest_log SET rows = ? WHERE ingest_id = ?", (out["legacy_prices"], iid))
    out["open_missing"] = add_flag(conn, "open_missing", "open IS NULL OR open <= 0")
    if imputed_from and imputed_from.exists():
        bak = sqlite3.connect(f"file:{imputed_from}?mode=ro", uri=True)
        keys = bak.execute("SELECT ticker, date FROM prices WHERE volume IS NULL").fetchall()
        bak.close()
        n = 0
        for t, d in keys:
            n += add_flag(conn, "volume_imputed", "ticker = ? AND date = ? AND COALESCE(volume, 0) = 0", (t, d))
        out["volume_imputed"] = n
    out["corporate_action_sources"] = classify_corporate_action_sources(conn)
    conn.commit()
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--imputed-from", default=str(BASE_DIR / "data" / "processed" / "dse.pre_audit_fix.bak"))
    args = ap.parse_args()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    print(json.dumps(backfill(conn, Path(args.imputed_from))))
    conn.close()


if __name__ == "__main__":
    main()
