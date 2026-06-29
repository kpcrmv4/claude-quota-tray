"""Unit tests for Area 4 features: auto interval, weekly summary, near-reset."""

import sqlite3
import time
import types
import unittest

import _path  # noqa: F401

import history
from api_client import UsageSnapshot


def _snap(session=None, weekly=None, opus=None,
          s_reset=None, w_reset=None, o_reset=None, ok=True):
    return UsageSnapshot(
        session_pct=session, session_reset_seconds=s_reset, session_status=None,
        weekly_pct=weekly, weekly_reset_seconds=w_reset, weekly_status=None,
        ok=ok, fetched_at=time.time(),
        opus_pct=opus, opus_reset_seconds=o_reset, opus_status=None,
    )


class AutoIntervalTests(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main
        self._snap0 = main.state.snapshot
        self._burn0 = main.state.burn

    def tearDown(self):
        self.main.state.snapshot = self._snap0
        self.main.state.burn = self._burn0

    def _set(self, snap, burn=None):
        self.main.state.snapshot = snap
        self.main.state.burn = burn or {"session": {}, "weekly": {}}

    def test_no_data_defaults(self):
        self._set(None)
        self.assertEqual(self.main._compute_auto_interval(), 60)

    def test_high_usage_polls_fast(self):
        self._set(_snap(session=95))
        self.assertEqual(self.main._compute_auto_interval(), self.main._AUTO_MIN)

    def test_imminent_reset_polls_fast(self):
        self._set(_snap(session=50, s_reset=60))
        self.assertEqual(self.main._compute_auto_interval(), self.main._AUTO_MIN)

    def test_high_burn_rate_polls_fast(self):
        self._set(_snap(session=50), {"session": {"rate": 20.0}})
        self.assertEqual(self.main._compute_auto_interval(), self.main._AUTO_MIN)

    def test_low_flat_usage_slows_down(self):
        self._set(_snap(session=10, weekly=5), {"session": {"rate": 0.0}})
        self.assertEqual(self.main._compute_auto_interval(), self.main._AUTO_MAX)


class NearResetDecisionTests(unittest.TestCase):
    """Exercise the arming logic in _check_reset_notifications via a fake icon."""

    def setUp(self):
        import main
        self.main = main
        self.sent = []
        self._notify0 = main.notifications.notify
        main.notifications.notify = lambda icon, title, body: self.sent.append((title, body))
        self.main.state.reset_notified = {"session": False, "weekly": False, "opus": False}

    def tearDown(self):
        self.main.notifications.notify = self._notify0

    def test_fires_once_then_rearms(self):
        # Heavily used session, 5 min from reset → should fire once.
        self.main._check_reset_notifications(None, _snap(session=80, s_reset=300))
        self.assertEqual(len(self.sent), 1)
        # Still within window next poll → must NOT fire again.
        self.main._check_reset_notifications(None, _snap(session=82, s_reset=240))
        self.assertEqual(len(self.sent), 1)
        # Window rolled over (reset far out) → re-arm, no new toast yet.
        self.main._check_reset_notifications(None, _snap(session=5, s_reset=18000))
        self.assertEqual(len(self.sent), 1)
        # Approaching the next reset → fires again.
        self.main._check_reset_notifications(None, _snap(session=70, s_reset=120))
        self.assertEqual(len(self.sent), 2)

    def test_low_usage_does_not_fire(self):
        self.main._check_reset_notifications(None, _snap(session=10, s_reset=120))
        self.assertEqual(self.sent, [])


class WeeklySummaryTests(unittest.TestCase):
    def setUp(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE snapshots (ts REAL, account_id TEXT, session_pct INT, "
            "weekly_pct INT, session_reset INT, weekly_reset INT, opus_pct INT)"
        )
        self._conn.commit()
        self._saved = history._conn
        history._conn = self._conn
        # Pin language so summary text is deterministic regardless of the
        # machine's saved language setting (export uses i18n.t()).
        import i18n
        self._i18n = i18n
        self._lang0 = i18n.current_language
        i18n.current_language = lambda: "en"

    def tearDown(self):
        history._conn = self._saved
        self._conn.close()
        self._i18n.current_language = self._lang0

    def _ins(self, ago_s, s, w, o=None):
        self._conn.execute(
            "INSERT INTO snapshots VALUES (?, 'acct', ?, ?, NULL, NULL, ?)",
            (time.time() - ago_s, s, w, o),
        )
        self._conn.commit()

    def test_empty(self):
        out = history.weekly_summary("acct")
        self.assertEqual(out["samples"], 0)
        self.assertIsNone(out["peak_session"])

    def test_peaks_and_threshold_hits(self):
        self._ins(3600, 30, 40)
        self._ins(1800, 85, 60, o=92)
        self._ins(60, 50, 70)
        out = history.weekly_summary("acct", threshold=80)
        self.assertEqual(out["samples"], 3)
        self.assertEqual(out["peak_session"], 85)
        self.assertEqual(out["peak_weekly"], 70)
        self.assertEqual(out["peak_opus"], 92)
        self.assertEqual(out["threshold_hits"], 1)
        self.assertIsNotNone(out["busiest_hour"])

    def test_period_window_excludes_older_than_days(self):
        self._ins(20 * 86400, 90, 90)   # 20 days ago
        self._ins(3600, 30, 40)         # within last day
        # 7-day window sees only the recent row; 30-day window sees both.
        self.assertEqual(history.period_summary(7, "acct")["samples"], 1)
        self.assertEqual(history.period_summary(30, "acct")["samples"], 2)
        self.assertEqual(history.period_summary(30, "acct")["peak_session"], 90)

    def test_export_period_writes_file(self):
        import os, tempfile
        self._ins(3600, 30, 40)
        self._ins(60, 85, 60)
        p = os.path.join(tempfile.mkdtemp(), "m.md")
        out = history.export_period_summary(p, "Acct", 30, "acct", threshold=80)
        self.assertIsNotNone(out)
        text = open(p, encoding="utf-8").read()
        self.assertIn("30 days", text)        # range reflects the period
        self.assertIn("85%", text)


if __name__ == "__main__":
    unittest.main()
