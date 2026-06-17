"""Funnel unittests (move 7): cap enforcement + tier flip + usage — the £0-killer logic.
No deploy, no VM, no network — pure auth-layer logic against an isolated store."""
import os
import sys
import tempfile
import pathlib
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meok_one import auth


class TestFunnel(unittest.TestCase):
    def setUp(self):
        # isolate the user store so tests never touch real data
        self._orig = auth._STORE
        auth._STORE = pathlib.Path(tempfile.mkdtemp()) / "users.json"

    def tearDown(self):
        auth._STORE = self._orig

    def test_free_caps_at_limit(self):
        uid = auth.create_anon()["user_id"]
        cap = auth.FREE_DAILY_CAP
        allowed = sum(1 for _ in range(cap + 5) if auth.check_and_bump(uid)["allowed"])
        self.assertEqual(allowed, cap)                       # exactly FREE_DAILY_CAP allowed
        self.assertFalse(auth.check_and_bump(uid)["allowed"])  # over-cap blocked

    def test_pro_flip_unlocks(self):
        uid = auth.create_anon()["user_id"]
        for _ in range(auth.FREE_DAILY_CAP + 1):
            auth.check_and_bump(uid)
        self.assertFalse(auth.check_and_bump(uid)["allowed"])   # capped as free
        auth.set_tier(uid, "pro")                                # the webhook flip
        c = auth.check_and_bump(uid)
        self.assertTrue(c["allowed"])
        self.assertEqual(c["cap"], auth.PRO_DAILY_CAP)
        self.assertEqual(auth.get_tier(uid), "pro")

    def test_usage_today_tracks(self):
        uid = auth.create_anon()["user_id"]
        for _ in range(3):
            auth.check_and_bump(uid)
        self.assertEqual(auth.usage_today(uid), 3)

    def test_me_exposes_tier_and_cap(self):
        uid = auth.create_anon()["user_id"]
        me = auth.me(uid)
        self.assertIn(me["tier"], ("free", "pro", "enterprise"))
        self.assertEqual(me["daily_cap"], auth.FREE_DAILY_CAP)
        self.assertEqual(me["usage_today"], 0)

    def test_set_tier_unknown_user(self):
        self.assertFalse(auth.set_tier("u_nope", "pro")["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
