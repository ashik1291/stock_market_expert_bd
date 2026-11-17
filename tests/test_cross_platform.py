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
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            inspect_stock("ACMELAB", limit=2, as_json=True)
        output = buf.getvalue()
        self.assertIn("ACMELAB", output)
        self.assertIn("Pharmaceuticals", output)

    def test_env_detector_runs_cleanly(self):
        """env_detector.py must diagnose system without error."""
        from scripts.env_detector import get_system_diagnosis
        diag = get_system_diagnosis()
        self.assertIn(diag["os"], ["Windows", "Linux", "Darwin"])
        self.assertTrue(diag["python_version"])
        self.assertTrue(diag["database_healthy"])


if __name__ == "__main__":
    unittest.main()
