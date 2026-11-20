"""Tier 2 tests: row provenance, imputed-value flags, data-quality series, dataset versions, archive cross-check."""

import os
import sqlite3
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _prices_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
                                               volume INTEGER, value REAL, UNIQUE(ticker, date));
                          CREATE TABLE corporate_actions (ticker TEXT, record_date TEXT, action_type TEXT, ratio REAL,
                                               cash_amount REAL, adjustment_factor REAL, notes TEXT);""")
    conn.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)",
                     [("A", "2026-11-18", 10, 11, 9, 10.5, 100, 1050), ("A", "2026-11-19", 0, 11, 9, 10.2, 0, 0),
                      ("B", "2026-11-19", 20, 21, 19, 20.5, 50, 1025)])
    return conn


class TestProvenance(unittest.TestCase):
    def test_writers_stamp_only_their_rows_and_flags_accumulate(self):
        import provenance as pv
        conn = _prices_db()
        pv.ensure_schema(conn)
        iid = pv.new_ingest(conn, "dse_live_snapshot", "file", raw=b"payload")
        self.assertEqual(pv.stamp_unattributed(conn, iid, "dse_live_snapshot", "2026-11-19"), 2)
        self.assertEqual(pv.stamp_unattributed(conn, iid, "dse_live_snapshot", "2026-11-19"), 0)
        arch = pv.new_ingest(conn, "dse_day_end_archive")
        pv.stamp_prices(conn, arch, "dse_day_end_archive", [("A", "2026-11-18")], verified_on="2026-11-20")
        rows = dict(((t, d), (s, v)) for t, d, s, v in conn.execute("SELECT ticker, date, source, archive_verified_on FROM prices"))
        self.assertEqual(rows[("A", "2026-11-18")], ("dse_day_end_archive", "2026-11-20"))
        self.assertEqual(rows[("B", "2026-11-19")], ("dse_live_snapshot", None))
        pv.add_flag(conn, "open_missing", "open <= 0")
        pv.add_flag(conn, "volume_imputed", "ticker = 'A' AND date = '2026-11-19'")
        pv.add_flag(conn, "open_missing", "open <= 0")
        self.assertEqual(conn.execute("SELECT quality_flags FROM prices WHERE ticker='A' AND date='2026-11-19'").fetchone()[0],
                         "open_missing,volume_imputed")
        sha = conn.execute("SELECT raw_sha256 FROM ingest_log WHERE ingest_id = ?", (iid,)).fetchone()[0]
        self.assertEqual(len(sha), 64)

    def test_corporate_action_source_is_derived_from_writer_markers(self):
        import provenance as pv
        conn = _prices_db()
        conn.executemany("INSERT INTO corporate_actions VALUES ('X', ?, 'cash_dividend', 0, 1, 1, ?)",
                         [("2026-01-01", "10% ... source dse_disclosure ids"), ("2025-01-01", "10% (Real DSE Record Date: x)"),
                          ("2024-12-15", "10% Cash Dividend (Historical estimated)")])
        pv.classify_corporate_action_sources(conn)
        self.assertEqual([r[0] for r in conn.execute("SELECT source FROM corporate_actions ORDER BY record_date DESC")],
                         ["dse_disclosure", "dse_company_page_notice", "estimated_placeholder"])


class TestDataGateProvenance(unittest.TestCase):
    def test_unattributed_price_rows_fail_the_gate(self):
        import integrity_harness as ih
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            try:
                ok = {c["check"]: c["status"] for c in ih.run_data_checks(conn)}["price_rows_attributed"]
                conn.execute("UPDATE prices SET source = NULL WHERE rowid = (SELECT MIN(rowid) FROM prices)")
                bad = {c["check"]: c["status"] for c in ih.run_data_checks(conn)}["price_rows_attributed"]
            finally:
                conn.close()
        self.assertEqual((ok, bad), ("PASS", "FAIL"))


class TestDatasetVersion(unittest.TestCase):
    def test_fingerprint_tracks_values_not_provenance(self):
        import dataset_release as dr
        import provenance as pv
        conn = _prices_db()
        pv.ensure_schema(conn)
        base = dr.dataset_fingerprint(conn)
        conn.execute("UPDATE prices SET archive_verified_on = '2026-11-20', source = 'x', quality_flags = 'y'")
        self.assertEqual(dr.dataset_fingerprint(conn), base)
        conn.execute("UPDATE prices SET close = 10.6 WHERE ticker = 'A' AND date = '2026-11-18'")
        self.assertNotEqual(dr.dataset_fingerprint(conn), base)


class TestArchiveCrosscheck(unittest.TestCase):
    def test_matches_are_verified_and_differences_recorded_without_editing_values(self):
        import archive_crosscheck as ac
        import provenance as pv
        conn = _prices_db()
        pv.ensure_schema(conn)
        conn.executescript(ac.SCHEMA)
        arch = {"A": {"open": 0, "high": 11, "low": 9, "close": 10.2, "volume": 0},
                "B": {"open": 20, "high": 21, "low": 19, "close": 20.9, "volume": 50}}
        arch.update({f"Z{i}": {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for i in range(60)})
        saved = ac.fetch_day_end_all
        ac.fetch_day_end_all = lambda d: arch
        try:
            res = ac.check_session(conn, "2026-11-19", "test")
        finally:
            ac.fetch_day_end_all = saved
        self.assertEqual((res["compared"], res["matched"], res["mismatched"]), (2, 1, 1))
        self.assertEqual(conn.execute("SELECT close FROM prices WHERE ticker='B'").fetchone()[0], 20.5)
        self.assertEqual(conn.execute("SELECT ticker FROM archive_crosscheck_diffs").fetchone()[0], "B")
        self.assertEqual(conn.execute("SELECT archive_verified_on IS NOT NULL FROM prices WHERE ticker='A' AND date='2026-11-19'")
                         .fetchone()[0], 1)


class TestDataQualitySeries(unittest.TestCase):
    def test_gate_run_records_one_row_per_session(self):
        import data_quality as dq
        import integrity_harness as ih
        from _isolation import temp_db_copy
        with temp_db_copy() as db:
            conn = sqlite3.connect(db)
            try:
                checks = ih.run_data_checks(conn)
                dq.record(conn, checks)
                dq.record(conn, checks)
                n, unattributed = conn.execute("SELECT COUNT(*), MAX(bars_unattributed) FROM data_quality_daily").fetchone()
            finally:
                conn.close()
        self.assertEqual((n, unattributed), (1, 0))


if __name__ == "__main__":
    unittest.main()
