"""Unit tests for history persistence (Area 3: CSV export crash, prune)."""

import os
import sqlite3
import tempfile
import time
import types
import unittest

import _path  # noqa: F401

import history


class HistoryDbTests(unittest.TestCase):
    def setUp(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE snapshots (
                ts REAL NOT NULL,
                account_id TEXT NOT NULL,
                session_pct INTEGER,
                weekly_pct INTEGER,
                session_reset INTEGER,
                weekly_reset INTEGER,
                opus_pct INTEGER
            )
            """
        )
        self._conn.commit()
        self._saved = history._conn
        history._conn = self._conn

    def tearDown(self):
        history._conn = self._saved
        self._conn.close()

    def _snap(self, session_pct, weekly_pct, ts=None):
        return types.SimpleNamespace(
            ok=True,
            session_pct=session_pct,
            weekly_pct=weekly_pct,
            session_reset_seconds=100,
            weekly_reset_seconds=200,
            fetched_at=ts or time.time(),
        )

    def test_record_and_recent_roundtrip(self):
        history.record("acct", self._snap(10, 20))
        history.record("acct", self._snap(30, 40))
        rows = history.recent(24, "acct")
        self.assertEqual(len(rows), 2)

    def test_record_skips_empty_snapshot(self):
        history.record("acct", self._snap(None, None))
        self.assertEqual(history.recent(24, "acct"), [])

    def test_export_csv_does_not_crash(self):
        # Regression: export_csv used the csv module without importing it.
        history.record("acct", self._snap(10, 20))
        history.record("acct", self._snap(30, 40))
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            count = history.export_csv(path, hours=24, account_id="acct")
            self.assertEqual(count, 2)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("session_pct", content)   # header row
            self.assertIn("10", content)
        finally:
            os.unlink(path)

    def test_prune_removes_old_rows(self):
        old = time.time() - 10 * 86400
        history.record("acct", self._snap(10, 20, ts=old))
        history.record("acct", self._snap(30, 40))  # now
        history.prune(7)
        rows = history.recent(24 * 365, "acct")  # look back a year
        self.assertEqual(len(rows), 1)  # only the recent one survives


if __name__ == "__main__":
    unittest.main()
