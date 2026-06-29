"""Unit tests for burn-rate / ETA math (Area 1: no hallucinated ETAs)."""

import sqlite3
import time
import unittest

import _path  # noqa: F401

import history


class BurnRateTests(unittest.TestCase):
    def setUp(self):
        # Point the history module at a throwaway in-memory DB.
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE snapshots (
                ts REAL NOT NULL,
                account_id TEXT NOT NULL,
                session_pct INTEGER,
                weekly_pct INTEGER,
                session_reset INTEGER,
                weekly_reset INTEGER
            )
            """
        )
        self._conn.commit()
        self._saved = history._conn
        history._conn = self._conn

    def tearDown(self):
        history._conn = self._saved
        self._conn.close()

    def _insert(self, ago_seconds, session_pct=None, weekly_pct=None):
        ts = time.time() - ago_seconds
        self._conn.execute(
            "INSERT INTO snapshots VALUES (?, 'acct', ?, ?, NULL, NULL)",
            (ts, session_pct, weekly_pct),
        )
        self._conn.commit()

    def test_too_few_points(self):
        self._insert(100, session_pct=10)
        out = history.burn_rate(60, "acct")
        self.assertIsNone(out["session"]["rate"])
        self.assertIsNone(out["session"]["eta_seconds"])

    def test_steady_growth_gives_rate_and_eta(self):
        self._insert(1800, session_pct=10)
        self._insert(900, session_pct=20)
        self._insert(1, session_pct=30)
        out = history.burn_rate(60, "acct")
        self.assertIsNotNone(out["session"]["rate"])
        self.assertGreater(out["session"]["rate"], 0)
        self.assertIsNotNone(out["session"]["eta_seconds"])
        self.assertGreater(out["session"]["eta_seconds"], 0)

    def test_reset_within_window_uses_tail(self):
        # Rises to 90, window resets (drops), then climbs again.
        self._insert(3000, session_pct=80)
        self._insert(2400, session_pct=90)
        self._insert(1200, session_pct=5)
        self._insert(600, session_pct=15)
        self._insert(1, session_pct=25)
        out = history.burn_rate(60, "acct")
        # Rate must be positive (computed from the post-reset 5→25 tail),
        # not negative from the 80→25 overall drop.
        self.assertIsNotNone(out["session"]["rate"])
        self.assertGreater(out["session"]["rate"], 0)

    def test_flat_usage_no_eta(self):
        self._insert(1800, session_pct=50)
        self._insert(900, session_pct=50)
        self._insert(1, session_pct=50)
        out = history.burn_rate(60, "acct")
        self.assertEqual(out["session"]["rate"], 0.0)
        self.assertIsNone(out["session"]["eta_seconds"])

    def test_tiny_rate_suppresses_eta(self):
        # ~0.4 %/h growth over 2.5h — below the ETA trust threshold.
        self._insert(9000, session_pct=40)
        self._insert(1, session_pct=41)
        out = history.burn_rate(240, "acct")
        self.assertIsNotNone(out["session"]["rate"])
        self.assertLess(out["session"]["rate"], history._MIN_RATE_FOR_ETA)
        self.assertIsNone(out["session"]["eta_seconds"])


if __name__ == "__main__":
    unittest.main()
