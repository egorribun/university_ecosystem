"""Synchronous fake transport negatives; no event loop or network is needed."""

from __future__ import annotations

import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nats.js.errors import (
    APIError,
    KeyNotFoundError,
    KeyWrongLastSequenceError,
    NotFoundError,
)

from app.deps.cache import _encode_kv_key
from app.services import stats_fill_fence as module
from tests.test_stats_fill_fence_nats_barrier import KEY, TOKEN, setup


def resolve(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("fake coroutine unexpectedly suspended")


class NegativeTests(unittest.TestCase):
    def test_malformed_or_untrusted_tombstones_do_not_hold_a_lease(self):
        marker = json.loads(module._entry(module._MARKER + TOKEN, 10)[1])
        invalid = [
            b"{",
            b"[]",
            json.dumps({**marker, "stored_at": True}).encode(),
            json.dumps({**marker, "ttl_seconds": "10"}).encode(),
            json.dumps({**marker, "payload": "wrong"}).encode(),
            json.dumps({**marker, "etag": "wrong"}).encode(),
            json.dumps({**marker, "ttl_seconds": 31}).encode(),
            json.dumps({**marker, "stored_at": float("nan")}).encode(),
            json.dumps({**marker, "ttl_seconds": float("inf")}).encode(),
            json.dumps({**marker, "stored_at": time.time() + 100}).encode(),
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.assertIs(module._nats_live_tombstone(value), False)
        self.assertIs(module._nats_live_tombstone(json.dumps(marker).encode()), True)

    def test_mismatched_cached_handle_fails_closed(self):
        for field in ("_stream", "_pre"):
            with self.subTest(field=field):
                _, kv, fence = setup()
                setattr(kv, field, "wrong")
                self.assertIsNone(resolve(fence.reserve(KEY, TOKEN, 10)))
                self.assertIsNone(resolve(fence.complete(KEY, TOKEN, {"x": 1}, 120)))
                self.assertEqual(kv.publications, [])

    def test_bad_leader_subject_and_revision_are_unknown(self):
        for subject, revision in (
            ("other", 1),
            ("$KV.synthetic." + _encode_kv_key(KEY), None),
            ("$KV.synthetic." + _encode_kv_key(KEY), 0),
        ):
            with self.subTest(subject=subject, revision=revision):
                _, kv, fence = setup()
                value = SimpleNamespace(
                    subject=subject, seq=revision, data=b"", headers={}
                )
                with patch.object(kv, "get_msg", return_value=value):
                    self.assertIsNone(resolve(fence.reserve(KEY, TOKEN, 10)))
                self.assertEqual(kv.publications, [])

    def test_live_existing_value_is_not_replaced_by_reservation(self):
        cache, kv, fence = setup()
        resolve(cache.set(KEY, {"fresh": True}, ttl=120))
        self.assertIs(resolve(fence.reserve(KEY, TOKEN, 10)), False)
        self.assertEqual(resolve(cache.get(KEY)).payload, {"fresh": True})
        self.assertEqual(kv.publications, [])

    def test_ttl_create_conflict_and_unknown_not_found_are_distinct(self):
        for error, expected in (
            (KeyWrongLastSequenceError(), False),
            (KeyNotFoundError(), None),
        ):
            with self.subTest(error=type(error).__name__):
                _, kv, fence = setup(True)
                with patch.object(kv, "create", side_effect=error):
                    self.assertIs(resolve(fence.reserve(KEY, TOKEN, 10)), expected)

    def test_reserve_api_conflict_denial_and_unexpected_error(self):
        for error, expected in (
            (APIError(code=400, err_code=10071), False),
            (APIError(code=400, err_code=10164), False),
            (APIError(code=403), None),
        ):
            with self.subTest(code=error.err_code):
                _, kv, fence = setup()
                with patch.object(kv, "publish", side_effect=error):
                    self.assertIs(resolve(fence.reserve(KEY, TOKEN, 10)), expected)
        _, kv, fence = setup()
        with patch.object(
            kv, "publish", side_effect=APIError(code=400, err_code=10999)
        ):
            with self.assertRaises(APIError):
                resolve(fence.reserve(KEY, TOKEN, 10))

    def test_missing_bucket_unknown_and_unexpected_not_found_propagates(self):
        for operation in ("reserve", "complete"):
            for error, unknown in (
                (NotFoundError(code=404, err_code=10059), True),
                (NotFoundError(code=404, err_code=10999), False),
            ):
                with self.subTest(operation=operation, unknown=unknown):
                    _, kv, fence = setup()
                    with patch.object(kv, "get_msg", side_effect=error):
                        attempt = (
                            fence.reserve(KEY, TOKEN, 10)
                            if operation == "reserve"
                            else fence.complete(KEY, TOKEN, {"x": 1}, 120)
                        )
                        if unknown:
                            self.assertIsNone(resolve(attempt))
                        else:
                            with self.assertRaises(NotFoundError):
                                resolve(attempt)

    def test_missing_capability_or_removed_marker_does_not_complete(self):
        _, _, fence = setup(None)
        self.assertIsNone(resolve(fence.complete(KEY, TOKEN, {"x": 1}, 120)))
        _, kv, fence = setup()
        self.assertIs(resolve(fence.reserve(KEY, TOKEN, 10)), True)
        kv.rows.clear()
        self.assertIs(resolve(fence.complete(KEY, TOKEN, {"x": 1}, 120)), False)

    def test_complete_conflict_denial_and_unexpected_error(self):
        errors = (
            (KeyWrongLastSequenceError(), False),
            (APIError(code=400, err_code=10070), False),
            (APIError(code=403), None),
        )
        for error, expected in errors:
            with self.subTest(error=type(error).__name__, expected=expected):
                _, kv, fence = setup()
                with patch.object(kv, "publish", side_effect=error):
                    self.assertIs(
                        resolve(fence.complete(KEY, TOKEN, {"x": 1}, 120)), expected
                    )
        _, kv, fence = setup()
        with patch.object(
            kv, "publish", side_effect=APIError(code=400, err_code=10999)
        ):
            with self.assertRaises(APIError):
                resolve(fence.complete(KEY, TOKEN, {"x": 1}, 120))
