"""
Versioned, citable dataset releases.

dataset_fingerprint() hashes the research content of the database (values only — provenance/audit columns such as
source, ingest_id, archive_verified_on and timestamps are excluded, so re-verifying a bar does not change the version).
A release exports each research table to gzipped CSV under data/releases/<version>/ with a manifest holding row counts,
per-file SHA-256, table schemas, the fingerprint and the git commit, plus a copy of docs/DATA_CARD.md.

Usage:
  python scripts/dataset_release.py fingerprint
  python scripts/dataset_release.py release
"""

from __future__ import annotations

import argparse
import csv
import datetime
import gzip
import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
RELEASE_DIR = BASE_DIR / "data" / "releases"

TABLES = {
    "prices": "ticker, date",
    "trading_calendar": "date",
    "corporate_actions": "ticker, record_date, action_type",
    "fundamentals_pit": "ticker, snapshot_date",
    "disclosure_financials": "code, period_end, kind, published_date",
    "instruments": "ticker",
    "category_history": "ticker, valid_from",
    "index_membership": "index_code, effective_date, ticker",
    "company_dividend_history": "code, fiscal_year",
    "macro_indicators": "indicator, date",
    "bank_asset_quality": "ticker, period_end",
    "companies": "ticker",
}
AUDIT_TABLES = ("pit_corrections", "corporate_action_corrections", "archive_crosscheck", "data_quality_daily", "ingest_log")
NON_CONTENT = {"id", "source", "ingest_id", "archive_verified_on", "created_at", "updated_at", "fetched_at", "parsed_at",
               "captured_at", "entered_at", "recorded_at", "source_hash", "quality_flags", "status_evidence"}


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _content_cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[1] not in NON_CONTENT]


def dataset_fingerprint(conn: sqlite3.Connection) -> str:
    h = hashlib.sha256()
    have = _tables(conn)
    for t, order in TABLES.items():
        if t not in have:
            continue
        h.update(t.encode())
        for row in conn.execute(f"SELECT {', '.join(_content_cols(conn, t))} FROM {t} ORDER BY {order}"):
            h.update(repr(row).encode())
    return h.hexdigest()[:16]


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(BASE_DIR), capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def release(conn: sqlite3.Connection) -> dict:
    fp = dataset_fingerprint(conn)
    session = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    version = f"dse-{session}-{fp}"
    out = RELEASE_DIR / version
    if (out / "manifest.json").exists():
        return json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    have = _tables(conn)
    files = {}
    for t in [*TABLES, *AUDIT_TABLES]:
        if t not in have:
            continue
        order = TABLES.get(t, "rowid")
        cur = conn.execute(f"SELECT * FROM {t} ORDER BY {order}")
        cols = [d[0] for d in cur.description]
        path = out / f"{t}.csv.gz"
        n = 0
        with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in cur:
                w.writerow(row)
                n += 1
        files[t] = {"file": path.name, "rows": n, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "schema": conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (t,)).fetchone()[0],
                    "role": "research" if t in TABLES else "audit"}
    card = BASE_DIR / "docs" / "DATA_CARD.md"
    if card.exists():
        shutil.copyfile(card, out / "DATA_CARD.md")
    manifest = {"version": version, "dataset_fingerprint": fp, "latest_session": session,
                "created_at": datetime.datetime.utcnow().isoformat(timespec="seconds"), "git_commit": _git_commit(),
                "license_note": "Derived from public DSE and Bangladesh Bank publications; academic and research use.",
                "files": files}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("fingerprint", "release"))
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30.0)
    if args.cmd == "fingerprint":
        print(dataset_fingerprint(conn))
    else:
        m = release(conn)
        print(json.dumps({"version": m["version"], "tables": {k: v["rows"] for k, v in m["files"].items()}}, indent=1))
    conn.close()


if __name__ == "__main__":
    main()
