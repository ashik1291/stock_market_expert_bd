"""
Daily data-quality time series (one row per market session, refreshed by every data-gate run).

Lets anyone citing the dataset see how coverage, verification and provenance evolved over time.
"""

from __future__ import annotations

import datetime
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_quality_daily (
    session_date                  TEXT PRIMARY KEY,
    recorded_at                   TEXT NOT NULL,
    equities_active               INTEGER,
    bars_on_session               INTEGER,
    bars_unattributed             INTEGER,
    bars_archive_verified_pct_1y  REAL,
    pit_rows                      INTEGER,
    pit_observed_pct              REAL,
    pit_observed_pct_since_2024q3 REAL,
    corporate_actions_official_pct_since_2025 REAL,
    estimated_placeholders        INTEGER,
    crosscheck_match_rate_pct     REAL,
    t_bill_staleness_days         INTEGER,
    bcr_latest                    TEXT,
    gate_critical_fails           INTEGER,
    gate_warnings                 INTEGER,
    detail                        TEXT
);
"""


def _one(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchone()[0]
    except sqlite3.Error:
        return None


def record(conn: sqlite3.Connection, checks: list[dict]) -> dict:
    conn.executescript(SCHEMA)
    session = _one(conn, "SELECT MAX(date) FROM prices")
    year_ago = (datetime.date.fromisoformat(session) - datetime.timedelta(days=365)).isoformat()
    t_obs = _one(conn, "SELECT MAX(date) FROM macro_indicators WHERE indicator = 't_bill_91d'")
    row = {
        "session_date": session,
        "recorded_at": datetime.datetime.utcnow().isoformat(timespec="seconds"),
        "equities_active": _one(conn, "SELECT COUNT(*) FROM instruments WHERE instrument_type = 'equity' AND status = 'active'"),
        "bars_on_session": _one(conn, "SELECT COUNT(*) FROM prices WHERE date = ?", (session,)),
        "bars_unattributed": _one(conn, "SELECT COUNT(*) FROM prices WHERE source IS NULL"),
        "bars_archive_verified_pct_1y": _one(conn, """SELECT ROUND(100.0 * SUM(archive_verified_on IS NOT NULL) / COUNT(*), 2)
                                                     FROM prices WHERE date > ?""", (year_ago,)),
        "pit_rows": _one(conn, "SELECT COUNT(*) FROM fundamentals_pit"),
        "pit_observed_pct": _one(conn, "SELECT ROUND(100.0 * SUM(publication_is_estimated = 0) / COUNT(*), 2) FROM fundamentals_pit"),
        "pit_observed_pct_since_2024q3": _one(conn, """SELECT ROUND(100.0 * SUM(publication_is_estimated = 0) / COUNT(*), 2)
            FROM fundamentals_pit WHERE snapshot_date >= '2024-09-30' AND publication_source != 'live_scrape'"""),
        "corporate_actions_official_pct_since_2025": _one(conn, """SELECT ROUND(100.0 * SUM(source = 'dse_disclosure') / COUNT(*), 2)
            FROM corporate_actions WHERE record_date >= '2025-01-01'"""),
        "estimated_placeholders": _one(conn, "SELECT COUNT(*) FROM corporate_actions WHERE source = 'estimated_placeholder'"),
        "crosscheck_match_rate_pct": _one(conn, "SELECT ROUND(100.0 * SUM(matched) / SUM(compared), 3) FROM archive_crosscheck"),
        "t_bill_staleness_days": (datetime.date.fromisoformat(session) - datetime.date.fromisoformat(t_obs)).days if t_obs else None,
        "bcr_latest": _one(conn, "SELECT MAX(date) FROM macro_indicators WHERE indicator = 'bcr_91d'"),
        "gate_critical_fails": sum(1 for c in checks if c["status"] == "FAIL"),
        "gate_warnings": sum(1 for c in checks if c["status"] == "WARN"),
        "detail": json.dumps({c["check"]: c["status"] for c in checks}),
    }
    conn.execute(f"INSERT OR REPLACE INTO data_quality_daily ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                 tuple(row.values()))
    conn.commit()
    return row
