"""
tests/test_cross_platform.py — Cross-Platform & Multi-OS Compatibility Sentinel
Verifies scripts run cleanly across Windows, macOS, and Linux without shell or path breaks.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class TestCrossPlatformCompatibility(unittest.TestCase):

    def test_shell_scripts_have_lf_endings(self):
        """Shell scripts (.sh) MUST have LF line endings (\n), never CRLF (\r\n), or Linux/macOS will fail."""
        sh_files = list(BASE_DIR.glob("*.sh")) + list((BASE_DIR / "scripts").glob("*.sh"))
        for sh in sh_files:
            with open(sh, "rb") as f:
                content = f.read()
            self.assertNotIn(b"\r\n", content, f"File {sh.name} has CRLF line endings which breaks Unix/macOS.")
            self.assertTrue(content.startswith(b"#!/usr/bin/env bash") or content.startswith(b"#!/bin/bash") or content.startswith(b"#!/bin/sh"),
                            f"File {sh.name} missing proper POSIX shebang.")

    def test_batch_scripts_are_clean_ascii(self):
        """Windows batch files (.bat) must not contain non-ASCII characters that cmd.exe mishandles."""
        bat_files = list(BASE_DIR.glob("*.bat"))
        for bat in bat_files:
            with open(bat, "rb") as f:
                content = f.read()
            # Must decode cleanly as ASCII
            try:
                content.decode("ascii")
            except UnicodeDecodeError:
                self.fail(f"Batch file {bat.name} contains non-ASCII characters that corrupt cmd.exe execution.")

    def test_query_stock_runs_cleanly(self):
        """query_stock.py must execute and return valid data for ACMELAB without throwing exceptions."""
        from scripts.query_stock import inspect_stock
        res = inspect_stock("ACMELAB", limit=2, quiet=True)
        self.assertIn("company", res)
        self.assertEqual(res["company"]["ticker"], "ACMELAB")
        self.assertEqual(res["company"]["sector"], "Pharmaceuticals")

    def test_all_396_stocks_queryable_without_exception(self):
        """CRITICAL: Every single stock in the 396-stock DSE universe must be queryable without crash."""
        import sqlite3
        from scripts.query_stock import inspect_stock, DB_PATH

        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        tickers = [r[0] for r in conn.execute("SELECT ticker FROM companies ORDER BY ticker").fetchall()]

        self.assertGreaterEqual(len(tickers), 390, f"Expected ~396 tickers, found {len(tickers)}")
        failures = []
        for t in tickers:
            try:
                res = inspect_stock(t, limit=1, quiet=True, conn=conn)
                if "company" not in res or not res["company"]:
                    failures.append((t, "Missing company data"))
            except Exception as e:
                failures.append((t, str(e)))

        conn.close()
        self.assertEqual(len(failures), 0, f"Failed querying {len(failures)} tickers: {failures[:5]}")

    def test_env_detector_runs_cleanly(self):
        """env_detector.py must diagnose system without error."""
        from scripts.env_detector import get_system_diagnosis
        diag = get_system_diagnosis()
        self.assertIn(diag["os"], ["Windows", "Linux", "Darwin"])
        self.assertTrue(diag["python_version"])
        self.assertTrue(diag["database_healthy"])


if __name__ == "__main__":
    unittest.main()
