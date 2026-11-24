from __future__ import annotations

import base64
import json
import unittest
from types import SimpleNamespace

from nats.js.api import Header
from nats.js.client import JetStreamContext
from nats.js.errors import APIError
from nats.js.kv import KV_DEL, KV_OP

STREAM = "KV_synthetic"
SUBJECT = "$KV.synthetic.stats=3agrades=3a7=3a90d"


class Connection:
    def __init__(self):
        self.calls = []
        self.error = None

    async def request(self, subject, payload, *, timeout, headers=None):
        self.calls.append((subject, payload, dict(headers or {})))
        if self.error:
            return SimpleNamespace(data=json.dumps({"error": self.error}).encode())
        if subject == f"$JS.API.STREAM.MSG.GET.{STREAM}":
            hdrs = b"NATS/1.0\r\nKV-Operation: DEL\r\n\r\n"
            message = {
                "subject": SUBJECT,
                "seq": 4,
                "time": "2026-11-24T00:00:00Z",
                "data": base64.b64encode(b"synthetic-marker").decode(),
                "hdrs": base64.b64encode(hdrs).decode(),
            }
            return SimpleNamespace(data=json.dumps({"message": message}).encode())
        return SimpleNamespace(data=json.dumps({"stream": STREAM, "seq": 7}).encode())


class PublicClientContract(unittest.IsolatedAsyncioTestCase):
    async def test_nonce_delete_and_fixed_barrier_headers_are_transmitted(self):
        nc = Connection()
        js = JetStreamContext(nc, timeout=2)
        await js.publish(
            SUBJECT,
            b"opaque-marker",
            stream=STREAM,
            headers={KV_OP: KV_DEL, Header.EXPECTED_LAST_SUBJECT_SEQUENCE: "0"},
        )
        _, payload, headers = nc.calls[-1]
        self.assertEqual(payload, b"opaque-marker")
        self.assertEqual(headers[KV_OP], KV_DEL)
        self.assertEqual(headers[Header.EXPECTED_LAST_SUBJECT_SEQUENCE], "0")
        await js.publish(
            "$KV.synthetic.stats=3a__fill_fence_barrier__",
            b"",
            stream=STREAM,
            headers={KV_OP: KV_DEL, Header.MSG_ID: "a" * 32},
        )
        _, payload, headers = nc.calls[-1]
        self.assertEqual(payload, b"")
        self.assertEqual(headers[Header.MSG_ID], "a" * 32)
        self.assertEqual(headers[KV_OP], KV_DEL)

    async def test_combined_expected_guards_are_sent_with_stream(self):
        nc = Connection()
        js = JetStreamContext(nc, timeout=2)
        ack = await js.publish(
            SUBJECT,
            b"value",
            stream=STREAM,
            headers={
                Header.EXPECTED_LAST_SUBJECT_SEQUENCE: "4",
                Header.EXPECTED_LAST_MSG_ID: "b" * 32,
            },
        )
        self.assertEqual((ack.stream, ack.seq, ack.duplicate), (STREAM, 7, None))
        subject, payload, headers = nc.calls[-1]
        self.assertEqual((subject, payload), (SUBJECT, b"value"))
        self.assertEqual(headers[Header.EXPECTED_STREAM], STREAM)
        self.assertEqual(headers[Header.EXPECTED_LAST_SUBJECT_SEQUENCE], "4")
        self.assertEqual(headers[Header.EXPECTED_LAST_MSG_ID], "b" * 32)

    async def test_authoritative_read_uses_stream_message_get(self):
        nc = Connection()
        js = JetStreamContext(nc, timeout=2)
        result = await js.get_msg(STREAM, subject=SUBJECT, direct=False)
        self.assertEqual(
            (result.subject, result.seq, result.data), (SUBJECT, 4, b"synthetic-marker")
        )
        self.assertEqual(result.headers[KV_OP], KV_DEL)
        subject, payload, _ = nc.calls[-1]
        self.assertEqual(subject, f"$JS.API.STREAM.MSG.GET.{STREAM}")
        self.assertEqual(json.loads(payload), {"last_by_subj": SUBJECT})

    async def test_last_message_id_conflict_keeps_official_error_code(self):
        nc = Connection()
        nc.error = {"code": 400, "err_code": 10070, "description": "synthetic"}
        js = JetStreamContext(nc, timeout=2)
        with self.assertRaises(APIError) as caught:
            await js.publish(SUBJECT, b"value", stream=STREAM)
        self.assertEqual(
            (caught.exception.code, caught.exception.err_code), (400, 10070)
        )
