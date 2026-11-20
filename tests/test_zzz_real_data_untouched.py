"""Runs last under unittest discover: the suite must leave real data exactly as it found it."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import tests  # noqa: E402
from _isolation import real_data_fingerprint  # noqa: E402


class TestRealDataUntouched(unittest.TestCase):
    def test_suite_did_not_mutate_real_data(self):
        start = tests.REAL_DATA_FINGERPRINT_AT_START
        now = real_data_fingerprint()
        changed = sorted(k for k in start if start[k] != now.get(k))
        self.assertEqual(changed, [], f"tests mutated real data: {changed}")


if __name__ == "__main__":
    unittest.main()
