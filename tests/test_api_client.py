"""Unit tests for api_client header parsing (Area 1: quota accuracy)."""

import time
import unittest

import _path  # noqa: F401  (adds src/ to sys.path)

import httpx

import api_client as ac


class PctFromUtilizationTests(unittest.TestCase):
    def test_none_and_garbage(self):
        self.assertIsNone(ac._pct_from_utilization(None))
        self.assertIsNone(ac._pct_from_utilization("abc"))
        self.assertIsNone(ac._pct_from_utilization(""))

    def test_fraction_is_primary_format(self):
        # Real unified header format: a fraction in [0, 1].
        self.assertEqual(ac._pct_from_utilization("0"), 0)
        self.assertEqual(ac._pct_from_utilization("0.5"), 50)
        self.assertEqual(ac._pct_from_utilization("0.0184"), 2)
        # The historic worry: "1" must read as 100% (full), not 1%.
        self.assertEqual(ac._pct_from_utilization("1"), 100)
        self.assertEqual(ac._pct_from_utilization("1.0"), 100)

    def test_round_half_up_keeps_small_usage_visible(self):
        # 0.005 → 0.5% → 1 (not 0), so tiny usage isn't swallowed.
        self.assertEqual(ac._pct_from_utilization("0.005"), 1)

    def test_above_one_treated_as_percent_defensively(self):
        self.assertEqual(ac._pct_from_utilization("45"), 45)
        self.assertEqual(ac._pct_from_utilization("150"), 100)  # clamp

    def test_negative_clamped_to_zero(self):
        self.assertEqual(ac._pct_from_utilization("-0.1"), 0)


class SecondsUntilResetTests(unittest.TestCase):
    def test_none_and_empty(self):
        self.assertIsNone(ac._seconds_until_reset(None))
        self.assertIsNone(ac._seconds_until_reset("   "))
        self.assertIsNone(ac._seconds_until_reset("not-a-date"))

    def test_unix_epoch_future(self):
        future = int(time.time()) + 3600
        secs = ac._seconds_until_reset(str(future))
        self.assertIsNotNone(secs)
        self.assertTrue(3500 <= secs <= 3600)

    def test_unix_epoch_past_clamped_to_zero(self):
        past = int(time.time()) - 5000
        self.assertEqual(ac._seconds_until_reset(str(past)), 0)

    def test_relative_seconds(self):
        self.assertEqual(ac._seconds_until_reset("120"), 120)
        self.assertEqual(ac._seconds_until_reset("0"), 0)

    def test_iso8601_with_z(self):
        from datetime import datetime, timezone, timedelta
        dt = datetime.now(timezone.utc) + timedelta(minutes=10)
        iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        secs = ac._seconds_until_reset(iso)
        self.assertIsNotNone(secs)
        self.assertTrue(540 <= secs <= 600)


class SnapshotFromHeadersTests(unittest.TestCase):
    def _resp(self, headers, status=200):
        return httpx.Response(status_code=status, headers=headers)

    def test_session_and_weekly_fractions(self):
        future = int(time.time()) + 7200
        headers = {
            "anthropic-ratelimit-unified-5h-utilization": "0.25",
            "anthropic-ratelimit-unified-5h-reset": str(future),
            "anthropic-ratelimit-unified-5h-status": "allowed",
            "anthropic-ratelimit-unified-7d-utilization": "0.8",
            "anthropic-ratelimit-unified-7d-reset": str(future),
            "anthropic-ratelimit-unified-7d-status": "allowed_warning",
        }
        snap = ac.snapshot_from_headers(httpx.Headers(headers), self._resp(headers))
        self.assertTrue(snap.ok)
        self.assertEqual(snap.session_pct, 25)
        self.assertEqual(snap.weekly_pct, 80)
        self.assertEqual(snap.session_status, "allowed")
        self.assertEqual(snap.weekly_status, "allowed_warning")
        self.assertIsNone(snap.opus_pct)
        self.assertTrue(snap.has_data)

    def test_opus_weekly_discovered_dynamically(self):
        headers = {
            "anthropic-ratelimit-unified-7d-utilization": "0.4",
            "anthropic-ratelimit-unified-7d_oauth_opus-utilization": "0.9",
            "anthropic-ratelimit-unified-7d_oauth_opus-status": "allowed",
        }
        snap = ac.snapshot_from_headers(httpx.Headers(headers), self._resp(headers))
        self.assertEqual(snap.weekly_pct, 40)   # plain 7d stays weekly
        self.assertEqual(snap.opus_pct, 90)     # opus captured separately
        self.assertEqual(snap.opus_status, "allowed")

    def test_429_with_headers_is_ok(self):
        headers = {
            "anthropic-ratelimit-unified-5h-utilization": "1",
            "anthropic-ratelimit-unified-5h-status": "exceeded",
        }
        snap = ac.snapshot_from_headers(httpx.Headers(headers), self._resp(headers, 429))
        self.assertTrue(snap.ok)            # headers present → still usable
        self.assertEqual(snap.session_pct, 100)
        self.assertEqual(snap.http_status, 429)

    def test_401_without_headers_is_error(self):
        resp = httpx.Response(status_code=401, json={"error": {"message": "auth"}})
        snap = ac.snapshot_from_headers(resp.headers, resp)
        self.assertFalse(snap.ok)
        self.assertIn("401", snap.error)
        self.assertFalse(snap.has_data)


if __name__ == "__main__":
    unittest.main()
