from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nats.errors import TimeoutError as NatsTimeoutError
from nats.js.api import Header
from nats.js.errors import (
    APIError,
    KeyNotFoundError,
    KeyWrongLastSequenceError,
    NotFoundError,
)
from nats.js.kv import KV_DEL, KV_OP

from app.deps.cache import NatsKVCache, _encode_kv_key
from app.services.stats_cache import get_cached_stats
from app.services.stats_fill_fence import StatsFillFence

KEY = "stats:grades:7:90d"
TOKEN = "a" * 32
BUCKET = "synthetic"
PREFIX = f"$KV.{BUCKET}."
STREAM = f"KV_{BUCKET}"


class FakeKV:
    """Models server-side sequence and global Msg-Id guards, not a real server."""

    def __init__(self, ttl_enabled=False):
        self.ttl_enabled = ttl_enabled
        self.rows = {}
        self.seq = 0
        self.last_id = ""
        self._js = self
        self._stream = STREAM
        self._pre = PREFIX
        self.created_ttl = None
        self.leader_reads = 0
        self.publications = []
        self.lost_stage = None
        self.deny_leader = False
        self.before_barrier = None
        self.before_complete = None
        self.direct_stale = None

    async def status(self):
        return SimpleNamespace(
            stream_info=SimpleNamespace(
                config=SimpleNamespace(allow_msg_ttl=self.ttl_enabled)
            )
        )

    def write(self, key, value, op=None, msgid=""):
        self.seq += 1
        self.last_id = msgid
        self.rows[key] = SimpleNamespace(value=value, revision=self.seq, op=op)
        return self.seq

    async def create(self, key, value, msg_ttl=None):
        if key in self.rows and self.rows[key].op != KV_DEL:
            raise KeyWrongLastSequenceError()
        self.created_ttl = msg_ttl
        return self.write(key, value)

    async def get(self, key):
        row = self.direct_stale or self.rows.get(key)
        if row is None:
            raise KeyNotFoundError()
        if row.op == KV_DEL:
            raise KeyNotFoundError(row, KV_DEL)
        return row

    async def put(self, key, value):
        return self.write(key, value)

    async def update(self, key, value, last=None):
        if key not in self.rows or self.rows[key].revision != last:
            raise KeyWrongLastSequenceError()
        return self.write(key, value)

    async def delete(self, key):
        return self.write(key, b"", KV_DEL)

    async def get_msg(self, stream, subject=None, direct=False):
        if stream != STREAM or not subject or not subject.startswith(PREFIX):
            raise AssertionError("invalid stream binding")
        if direct is not False:
            raise AssertionError("marker read must not use a lagging follower")
        self.leader_reads += 1
        if self.deny_leader:
            raise NatsTimeoutError()
        row = self.rows.get(subject[len(PREFIX) :])
        if row is None:
            raise NotFoundError(code=404, err_code=10037)
        return SimpleNamespace(
            subject=subject,
            data=row.value,
            seq=row.revision,
            headers={KV_OP: row.op} if row.op else {},
        )

    async def publish(self, subject, payload=b"", *, stream=None, headers=None, **_):
        if stream != STREAM or not subject.startswith(PREFIX):
            raise AssertionError("invalid stream binding")
        headers = headers or {}
        key = subject[len(PREFIX) :]
        barrier_key = _encode_kv_key("stats:__fill_fence_barrier__")
        stage = (
            "barrier"
            if key == barrier_key
            else ("reserve" if headers.get(KV_OP) == KV_DEL else "fill")
        )
        if stage == "barrier" and self.before_barrier:
            hook, self.before_barrier = self.before_barrier, None
            hook()
        if stage == "fill" and self.before_complete:
            hook, self.before_complete = self.before_complete, None
            hook()
        expected = headers.get(Header.EXPECTED_LAST_SUBJECT_SEQUENCE)
        if expected is not None and int(expected) != (
            self.rows[key].revision if key in self.rows else 0
        ):
            raise APIError(code=400, err_code=10071)
        expected_id = headers.get(Header.EXPECTED_LAST_MSG_ID)
        if expected_id and expected_id != self.last_id:
            raise APIError(code=400, err_code=10070)
        self.publications.append((stage, headers.copy()))
        seq = self.write(
            key, payload, headers.get(KV_OP), headers.get(Header.MSG_ID, "")
        )
        if self.lost_stage == stage:
            raise NatsTimeoutError()
        return SimpleNamespace(stream=STREAM, seq=seq, duplicate=False)

    def recreate_with_fresh_value(self):
        self.rows.clear()
        self.seq = 0
        self.last_id = ""
        # Same subject revision as an initial reservation.
        import json

        value = json.dumps(
            {
                "etag": "synthetic",
                "payload": {"fresh": True},
                "stored_at": 1,
                "ttl_seconds": 120,
            }
        ).encode()
        self.write(_encode_kv_key(KEY), value)

    def set_fresh_value(self):
        import json

        value = json.dumps(
            {
                "etag": "synthetic",
                "payload": {"fresh": True},
                "stored_at": 1,
                "ttl_seconds": 120,
            }
        ).encode()
        self.write(_encode_kv_key(KEY), value)


def setup(ttl_enabled=False):
    kv = FakeKV(ttl_enabled)
    cache = NatsKVCache(BUCKET, 120)
    cache._kv = kv
    return cache, kv, StatsFillFence(cache)


class BarrierTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_ttl_cold_becomes_real_warm(self):
        cache, kv, fence = setup()
        self.assertIsNone(
            await get_cached_stats(
                cache=cache, kind="grades", user_id=7, period_key="90d"
            )
        )
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        self.assertIsNone(
            await get_cached_stats(
                cache=cache, kind="grades", user_id=7, period_key="90d"
            )
        )
        self.assertIs(await fence.complete(KEY, TOKEN, {"value": 4}, 120), True)
        warm = await get_cached_stats(
            cache=cache, kind="grades", user_id=7, period_key="90d"
        )
        self.assertEqual(warm.payload, {"value": 4})
        self.assertEqual(
            [p[0] for p in kv.publications], ["reserve", "barrier", "fill"]
        )
        self.assertEqual(kv.publications[0][1][KV_OP], KV_DEL)
        barrier_id = kv.publications[1][1][Header.MSG_ID]
        self.assertEqual(len(barrier_id), 32)
        self.assertEqual(kv.publications[2][1][Header.EXPECTED_LAST_MSG_ID], barrier_id)
        self.assertGreater(
            int(kv.publications[2][1][Header.EXPECTED_LAST_SUBJECT_SEQUENCE]), 0
        )
        self.assertNotIn(Header.MSG_TTL, kv.publications[2][1])
        self.assertGreaterEqual(kv.leader_reads, 1)

    async def test_ttl_enabled_keeps_ttl_and_warms(self):
        cache, kv, fence = setup(True)
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        self.assertEqual(kv.created_ttl, 10)
        self.assertIs(await fence.complete(KEY, TOKEN, {"value": 4}, 120), True)
        self.assertEqual((await cache.get(KEY)).payload, {"value": 4})
        self.assertEqual([p[0] for p in kv.publications], ["barrier", "fill"])

    async def test_successful_delete_before_barrier_revokes(self):
        cache, _kv, fence = setup()
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        await cache.invalidate(KEY)
        self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
        self.assertIsNone(await cache.get(KEY))

    async def test_successful_delete_after_leader_read_revokes(self):
        cache, kv, fence = setup()
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        kv.before_complete = lambda: kv.write(_encode_kv_key(KEY), b"", KV_DEL)
        self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
        self.assertIsNone(await cache.get(KEY))

    async def test_legacy_set_before_and_after_leader_read_revokes(self):
        for stage in ("before_barrier", "before_complete"):
            with self.subTest(stage=stage):
                cache, kv, fence = setup()
                self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
                setattr(kv, stage, kv.set_fresh_value)
                self.assertIs(
                    await fence.complete(KEY, TOKEN, {"stale": True}, 120), False
                )
                self.assertEqual((await cache.get(KEY)).payload, {"fresh": True})

    async def test_three_cold_sections_become_warm_without_interleaving(self):
        cache, kv, fence = setup()
        keys = [
            f"stats:{kind}:7:90d" for kind in ("attendance", "grades", "participation")
        ]
        tokens = ["a" * 32, "b" * 32, "c" * 32]
        for key, token in zip(keys, tokens, strict=True):
            self.assertIsNone(await cache.get(key))
            self.assertIs(await fence.reserve(key, token, 10), True)
        for key, token in zip(keys, tokens, strict=True):
            self.assertIs(await fence.complete(key, token, {"value": 4}, 120), True)
        for key in keys:
            self.assertEqual((await cache.get(key)).payload, {"value": 4})
        stages = [stage for stage, _ in kv.publications]
        self.assertEqual(
            [stages.count(stage) for stage in ("reserve", "barrier", "fill")], [3, 3, 3]
        )

    async def test_recreation_before_barrier_preserves_new_value(self):
        cache, kv, fence = setup()
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        kv.before_barrier = kv.recreate_with_fresh_value
        self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
        self.assertEqual((await cache.get(KEY)).payload, {"fresh": True})

    async def test_recreation_after_read_rejects_reused_revision(self):
        cache, kv, fence = setup()
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        kv.before_complete = kv.recreate_with_fresh_value
        self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
        self.assertEqual((await cache.get(KEY)).payload, {"fresh": True})

    async def test_stale_follower_does_not_override_leader(self):
        _cache, kv, fence = setup()
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        stale = kv.rows[_encode_kv_key(KEY)]
        kv.recreate_with_fresh_value()
        kv.direct_stale = stale
        self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
        self.assertGreater(kv.leader_reads, 0)

    async def test_lost_ack_and_leader_permission_never_allow_fallback(self):
        for stage in ("reserve", "barrier", "fill", "leader"):
            with self.subTest(stage=stage):
                _cache, kv, fence = setup()
                if stage == "reserve":
                    kv.lost_stage = stage
                    self.assertIsNone(await fence.reserve(KEY, TOKEN, 10))
                    self.assertNotIn("fill", [p[0] for p in kv.publications])
                    continue
                self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
                kv.lost_stage = stage
                kv.deny_leader = stage == "leader"
                self.assertIsNone(await fence.complete(KEY, TOKEN, {"value": 4}, 120))
                if stage in ("barrier", "leader"):
                    self.assertNotIn("fill", [p[0] for p in kv.publications])

    async def test_no_ttl_abandoned_marker_can_be_replaced_safely(self):
        cache, kv, fence = setup()
        kv.lost_stage = "reserve"
        now = time.time()
        with patch("app.services.stats_fill_fence.time.time", return_value=now):
            self.assertIsNone(await fence.reserve(KEY, TOKEN, 10))
            kv.lost_stage = None
            other = "b" * 32
            self.assertIs(await fence.reserve(KEY, other, 10), False)
        with patch("app.services.stats_fill_fence.time.time", return_value=now + 11):
            self.assertIs(await fence.reserve(KEY, other, 10), True)
            self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
            self.assertIs(await fence.complete(KEY, other, {"fresh": True}, 120), True)
        self.assertEqual((await cache.get(KEY)).payload, {"fresh": True})

    async def test_no_ttl_logical_reservation_expires_before_completion(self):
        cache, _kv, fence = setup()
        now = time.time()
        with patch("app.services.stats_fill_fence.time.time", return_value=now):
            self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        with patch("app.services.stats_fill_fence.time.time", return_value=now + 11):
            self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
        self.assertIsNone(await cache.get(KEY))

    async def test_unrelated_write_rejects_then_explicit_retry_recovers(self):
        cache, kv, fence = setup()
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        kv.before_complete = lambda: kv.write("other", b"unrelated")
        self.assertIs(await fence.complete(KEY, TOKEN, {"value": 4}, 120), False)
        self.assertIsNone(await cache.get(KEY))
        self.assertIs(await fence.complete(KEY, TOKEN, {"value": 4}, 120), True)
        self.assertEqual((await cache.get(KEY)).payload, {"value": 4})

    async def test_ttl_enabled_recreation_after_read_rejects(self):
        cache, kv, fence = setup(True)
        self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
        kv.before_complete = kv.recreate_with_fresh_value
        self.assertIs(await fence.complete(KEY, TOKEN, {"stale": True}, 120), False)
        self.assertEqual((await cache.get(KEY)).payload, {"fresh": True})

    async def test_malformed_ack_never_permits_following_write(self):
        for bad in (
            None,
            SimpleNamespace(stream=STREAM, seq=0, duplicate=False),
            SimpleNamespace(stream="wrong", seq=1, duplicate=False),
            SimpleNamespace(stream=STREAM, seq=1),
            SimpleNamespace(stream=STREAM, seq=1, duplicate=True),
        ):
            with self.subTest(bad=bad):
                _cache, kv, fence = setup()
                self.assertIs(await fence.reserve(KEY, TOKEN, 10), True)
                original = kv.publish

                async def bad_barrier(*args, _original=original, _bad=bad, **kwargs):
                    await _original(*args, **kwargs)
                    return _bad

                with patch.object(kv, "publish", side_effect=bad_barrier):
                    self.assertIsNone(
                        await fence.complete(KEY, TOKEN, {"stale": True}, 120)
                    )
                self.assertNotIn("fill", [p[0] for p in kv.publications])

    async def test_missing_capability_and_denied_leader_never_reserve(self):
        for mode in ("missing", "denied"):
            with self.subTest(mode=mode):
                _, kv, fence = setup(None if mode == "missing" else False)
                kv.deny_leader = mode == "denied"
                self.assertIsNone(await fence.reserve(KEY, TOKEN, 10))
                self.assertEqual(kv.publications, [])

    async def test_unexpected_bad_request_is_not_silently_swallowed(self):
        _, kv, fence = setup()
        with patch.object(
            kv, "get_msg", side_effect=APIError(code=400, err_code=10999)
        ):
            with self.assertRaises(APIError):
                await fence.reserve(KEY, TOKEN, 10)


if __name__ == "__main__":
    unittest.main()
