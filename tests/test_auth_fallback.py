"""Unit tests for auth discovery fallback (Area 2)."""

import unittest

import _path  # noqa: F401

import auth_discovery as ad
from token_reader import TokenError


def _provider(token):
    def _fn():
        if token is None:
            return None
        return {"token": token, "plan": None, "raw": {}, "source": f"src:{token}"}
    return _fn


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self._orig = ad._providers_for_platform

    def tearDown(self):
        ad._providers_for_platform = self._orig

    def _chain(self, *tokens):
        chain = [(f"p{i}", _provider(tok)) for i, tok in enumerate(tokens)]
        ad._providers_for_platform = lambda: chain

    def test_first_match_wins(self):
        self._chain("AAA", "BBB")
        creds = ad.read_credentials()
        self.assertEqual(creds["token"], "AAA")

    def test_skips_excluded_token(self):
        self._chain("AAA", "BBB")
        creds = ad.read_credentials(exclude_tokens={"AAA"})
        self.assertEqual(creds["token"], "BBB")

    def test_skips_missing_then_finds(self):
        self._chain(None, "BBB")
        creds = ad.read_credentials()
        self.assertEqual(creds["token"], "BBB")

    def test_all_excluded_raises_rejected(self):
        self._chain("AAA", "BBB")
        with self.assertRaises(TokenError) as ctx:
            ad.read_credentials(exclude_tokens={"AAA", "BBB"})
        self.assertIn("rejected", str(ctx.exception).lower())


class ProbeFormattingTests(unittest.TestCase):
    def test_fingerprint(self):
        fp = ad._token_fingerprint("sk-ant-abcdef0123456789")
        self.assertIn("sk-ant", fp)
        self.assertIn("len", fp)

    def test_expiry_note_expired(self):
        note = ad._expiry_note({"raw": {"expiresAt": 1000.0}})  # epoch 1970-ish
        self.assertIn("EXPIRED", note)

    def test_expiry_note_absent(self):
        self.assertEqual(ad._expiry_note({"raw": {}}), "")


if __name__ == "__main__":
    unittest.main()
