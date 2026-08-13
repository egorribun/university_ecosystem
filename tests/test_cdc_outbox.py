from __future__ import annotations

import asyncio
import json
import struct
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.events import UserCreated
from app.workers.cdc_outbox import (
    CDCInsertRecord,
    CdcOutboxWorker,
    KeepaliveMessage,
    PgOutputDecoder,
    format_standby_status_update,
    int_to_lsn,
    lsn_to_int,
)


@pytest.mark.asyncio
async def test_cdc_worker_fallback_delegates_to_outbox_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the logical-replication fallback path mapped in mutmut."""

    fallback_run = AsyncMock()

    class FakeOutboxWorker:
        async def run_forever(self) -> None:
            await fallback_run()

    monkeypatch.setattr("app.workers.outbox.OutboxWorker", FakeOutboxWorker)

    await CdcOutboxWorker(nats_broker=AsyncMock())._run_fallback_worker()

    fallback_run.assert_awaited_once_with()


# ── Helpers for Building Test Binary Payloads ─────────────────────────────────


def _build_relation_msg(
    rel_id: int = 10001,
    namespace: str = "public",
    rel_name: str = "stored_events",
    columns: list[tuple[str, int]] | None = None,
) -> bytes:
    if columns is None:
        columns = [
            ("id", 2950),
            ("event_type", 1043),
            ("aggregate_type", 1043),
            ("aggregate_id", 1043),
            ("payload", 114),
            ("metadata_", 114),
        ]
    buf = (
        b"R"
        + struct.pack(">I", rel_id)
        + namespace.encode()
        + b"\x00"
        + rel_name.encode()
        + b"\x00d"
        + struct.pack(">H", len(columns))
    )
    for name, oid in columns:
        buf += b"\x00" + name.encode() + b"\x00" + struct.pack(">Ii", oid, -1)
    return buf


def _build_insert_msg(rel_id: int = 10001, values: list[str] | None = None) -> bytes:
    if values is None:
        payload_str = json.dumps({"user_id": "usr-123", "email": "cdc@test.com"})
        meta_str = json.dumps({"correlation_id": "corr-456"})
        values = [
            str(uuid.uuid4()),
            "UserCreated",
            "User",
            "usr-123",
            payload_str,
            meta_str,
        ]

    buf = b"I" + struct.pack(">I", rel_id) + b"N" + struct.pack(">H", len(values))
    for val in values:
        val_bytes = val.encode()
        buf += b"t" + struct.pack(">I", len(val_bytes)) + val_bytes
    return buf


def _wrap_xlogdata(
    wal_payload: bytes, start_lsn: int = 1000, end_lsn: int = 2000
) -> bytes:
    return b"w" + struct.pack(">QQq", start_lsn, end_lsn, 0) + wal_payload


def _build_keepalive_msg(
    wal_end_lsn: int = 5000, reply_requested: bool = True
) -> bytes:
    return (
        b"k"
        + struct.pack(">QQ", wal_end_lsn, 0)
        + (b"\x01" if reply_requested else b"\x00")
    )


# ── LSN Conversion Tests ──────────────────────────────────────────────────────


def test_lsn_to_int_and_int_to_lsn() -> None:
    lsn_str = "16/B374D88"
    lsn_val = lsn_to_int(lsn_str)
    assert lsn_val == (0x16 << 32) + 0xB374D88
    back_to_str = int_to_lsn(lsn_val)
    assert back_to_str == lsn_str

    # Zero & fallback handling
    assert lsn_to_int("0/0") == 0
    assert lsn_to_int("1000") == 0x1000
    assert lsn_to_int("") == 0


def test_format_standby_status_update() -> None:
    lsn = 123456789
    payload = format_standby_status_update(lsn, reply_requested=True)
    assert len(payload) == 34
    assert payload[0:1] == b"r"

    write_lsn, flush_lsn, apply_lsn, clock, reply_req = struct.unpack_from(
        ">QQQQB", payload, 1
    )
    assert write_lsn == lsn
    assert flush_lsn == lsn
    assert apply_lsn == lsn
    assert clock > 0
    assert reply_req == 1


# ── PgOutputDecoder Unit Tests ────────────────────────────────────────────────


def test_pgoutput_decoder_keepalive() -> None:
    decoder = PgOutputDecoder()
    msg_bytes = _build_keepalive_msg(wal_end_lsn=987654, reply_requested=True)
    res = decoder.decode(msg_bytes)
    assert isinstance(res, KeepaliveMessage)
    assert res.wal_end_lsn == 987654
    assert res.reply_requested is True


def test_pgoutput_decoder_relation_and_insert() -> None:
    decoder = PgOutputDecoder()
    rel_bytes = _wrap_xlogdata(_build_relation_msg(rel_id=5001))
    res1 = decoder.decode(rel_bytes)
    assert res1 is None
    assert 5001 in decoder.relations

    schema = decoder.relations[5001]
    assert schema.relation_name == "stored_events"
    assert len(schema.columns) == 6

    event_id = str(uuid.uuid4())
    payload_str = json.dumps({"user_id": "u-777", "email": "unit@test.com"})
    meta_str = json.dumps({"correlation_id": "corr-777"})
    values = [event_id, "UserCreated", "User", "u-777", payload_str, meta_str]

    ins_bytes = _wrap_xlogdata(
        _build_insert_msg(rel_id=5001, values=values), start_lsn=4500
    )
    res2 = decoder.decode(ins_bytes)
    assert isinstance(res2, CDCInsertRecord)
    assert res2.relation_id == 5001
    assert res2.relation_name == "stored_events"
    assert res2.lsn == 4500
    assert res2.data["event_type"] == "UserCreated"
    assert res2.data["payload"]["user_id"] == "u-777"
    assert res2.data["payload"]["email"] == "unit@test.com"
    assert res2.data["metadata_"]["correlation_id"] == "corr-777"


# ── CdcOutboxWorker Unit Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cdc_outbox_worker_dispatch_insert_record_sub_50ms_latency() -> None:
    mock_broker = AsyncMock()
    mock_broker.is_connected = True
    mock_broker.publish = AsyncMock()

    worker = CdcOutboxWorker(nats_broker=mock_broker)

    event_id = str(uuid.uuid4())
    record = CDCInsertRecord(
        relation_id=10001,
        relation_name="stored_events",
        data={
            "id": event_id,
            "event_type": "UserCreated",
            "aggregate_type": "User",
            "aggregate_id": "usr-888",
            "payload": {"user_id": "usr-888", "email": "latency@test.com"},
            "metadata_": {
                "correlation_id": "corr-sub5ms",
                "user_id": str(uuid.uuid4()),
            },
        },
        lsn=10050,
    )

    t0 = time.perf_counter()
    domain_event = await worker.dispatch_insert_record(record)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Sub-50ms dispatch latency assertion
    assert elapsed_ms < 50.0, (
        f"CDC dispatch latency was {elapsed_ms:.3f}ms (must be < 50ms)"
    )
    assert domain_event is not None
    assert isinstance(domain_event, UserCreated)
    assert domain_event.email == "latency@test.com"
    assert domain_event.metadata.correlation_id == "corr-sub5ms"

    # Verify NATS publish call and headers
    mock_broker.publish.assert_called_once()
    call_kwargs = mock_broker.publish.call_args.kwargs
    assert call_kwargs["subject"] == "outbox.events.UserCreated"
    assert call_kwargs["msg_id"] == event_id
    assert call_kwargs["headers"]["Nats-Msg-Id"] == event_id


@pytest.mark.asyncio
async def test_cdc_outbox_worker_send_status_update_advances_lsn() -> None:
    worker = CdcOutboxWorker()
    assert worker._last_acknowledged_lsn == 0

    status_bytes = worker.send_status_update(543210, reply_requested=False)
    assert worker._last_acknowledged_lsn == 543210
    assert len(status_bytes) == 34
    assert status_bytes[0:1] == b"r"

    # Does not regress LSN
    worker.send_status_update(100, reply_requested=False)
    assert worker._last_acknowledged_lsn == 543210


@pytest.mark.asyncio
async def test_cdc_outbox_worker_process_wal_message_pipeline() -> None:
    mock_broker = AsyncMock()
    mock_broker.is_connected = True
    mock_broker.publish = AsyncMock()

    worker = CdcOutboxWorker(nats_broker=mock_broker)

    # 1. Feed relation metadata message
    rel_payload = _wrap_xlogdata(_build_relation_msg(rel_id=7001))
    events1 = await worker.process_wal_message(rel_payload, lsn=100)
    assert len(events1) == 0

    # 2. Feed insert tuple message
    event_id = str(uuid.uuid4())
    ins_payload = _wrap_xlogdata(
        _build_insert_msg(
            rel_id=7001,
            values=[
                event_id,
                "UserCreated",
                "User",
                "u-1",
                json.dumps({"user_id": "u-1", "email": "pipeline@test.com"}),
                json.dumps({"correlation_id": "corr-pipe"}),
            ],
        ),
        start_lsn=500,
    )
    events2 = await worker.process_wal_message(ins_payload, lsn=500)
    assert len(events2) == 1
    assert isinstance(events2[0], UserCreated)
    assert worker._last_acknowledged_lsn == 500
    mock_broker.publish.assert_called_once()


@pytest.mark.asyncio
async def test_cdc_outbox_worker_unknown_event_type_skip() -> None:
    mock_broker = AsyncMock()
    worker = CdcOutboxWorker(nats_broker=mock_broker)

    record = CDCInsertRecord(
        relation_id=10001,
        relation_name="stored_events",
        data={
            "id": str(uuid.uuid4()),
            "event_type": "UnknownNonExistentEvent",
            "payload": {},
        },
        lsn=900,
    )

    domain_event = await worker.dispatch_insert_record(record)
    assert domain_event is None
    mock_broker.publish.assert_not_called()


@pytest.mark.asyncio
async def test_cdc_outbox_worker_provision_replication_resources() -> None:
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(side_effect=[None, None, "outbox_cdc_slot"])
    mock_conn.execute = AsyncMock()

    worker = CdcOutboxWorker()
    await worker.provision_replication_resources(conn=mock_conn)

    mock_conn.execute.assert_called_once_with(
        "CREATE PUBLICATION outbox_pub FOR TABLE stored_events;"
    )
    mock_conn.fetchval.assert_called_with(
        "SELECT pg_create_logical_replication_slot($1, 'pgoutput')",
        "outbox_cdc_slot",
    )


@pytest.mark.asyncio
async def test_cdc_outbox_worker_fallback_on_provision_failure() -> None:
    mock_broker = AsyncMock()
    worker = CdcOutboxWorker(nats_broker=mock_broker)

    with patch.object(
        worker,
        "provision_replication_resources",
        side_effect=OSError("Replication unsupported"),
    ):
        with patch.object(
            worker, "_run_fallback_worker", new=AsyncMock()
        ) as mock_fallback:
            task = asyncio.create_task(worker.run_forever())
            await asyncio.sleep(0.01)
            await worker.stop()
            await task
            mock_fallback.assert_called_once()


@pytest.mark.asyncio
async def test_cdc_outbox_worker_dispatch_failure_does_not_advance_lsn() -> None:
    mock_broker = AsyncMock()
    mock_broker.is_connected = True
    worker = CdcOutboxWorker(nats_broker=mock_broker)

    # First register relation metadata for stored_events
    rel_payload = _wrap_xlogdata(
        _build_relation_msg(rel_id=10001, rel_name="stored_events")
    )
    await worker.process_wal_message(rel_payload)

    # Mock dispatch_insert_record to simulate dispatch failure (returns None)
    with patch.object(worker, "dispatch_insert_record", return_value=None):
        ins_payload = _wrap_xlogdata(
            _build_insert_msg(
                rel_id=10001,
                values=[
                    str(uuid.uuid4()),
                    "UserCreated",
                    "User",
                    "u-1",
                    json.dumps({"user_id": "u-1"}),
                    json.dumps({}),
                ],
            ),
            start_lsn=99999,
        )
        events = await worker.process_wal_message(ins_payload, lsn=99999)
        assert len(events) == 0
        # LSN must NOT advance on dispatch failure
        assert worker._last_acknowledged_lsn == 0


def test_pgoutput_decoder_malformed_binary_safety() -> None:
    decoder = PgOutputDecoder()

    # 1. Truncated XLogData header
    truncated_xlog = b"w\x00\x00\x00"
    assert decoder.decode(truncated_xlog) is None

    # 2. Truncated Keepalive header
    truncated_keepalive = b"k\x00\x00"
    assert decoder.decode(truncated_keepalive) is None

    # 3. Corrupted relation metadata payload with invalid struct bounds
    corrupted_relation = b"R\x00\x00\x00\x01public\x00stored_events\x00"
    assert decoder.decode(corrupted_relation) is None

    # 4. Truncated insert payload
    corrupted_insert = b"I\x00\x00"
    assert decoder.decode(corrupted_insert) is None


@pytest.mark.asyncio
async def test_cdc_outbox_worker_retries_on_interface_error() -> None:
    import asyncpg

    mock_broker = AsyncMock()
    mock_broker.is_connected = True
    worker = CdcOutboxWorker(nats_broker=mock_broker)

    retry_count = 0

    async def mock_connect(*args: Any, **kwargs: Any) -> Any:
        nonlocal retry_count
        retry_count += 1
        if retry_count == 1:
            raise asyncpg.InterfaceError("Connection reset by peer socket drop")
        # On second call, stop worker
        worker._is_running = False
        raise asyncpg.InterfaceError("Stopping test loop")

    with (
        patch.object(worker, "provision_replication_resources", new=AsyncMock()),
        patch("asyncpg.connect", side_effect=mock_connect),
        patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        await worker.run_forever()
        assert retry_count >= 2
        mock_sleep.assert_called_with(5)


# ── Remediation Tests for Reviewer 2 Feedback ───────────────────────────────


@pytest.mark.asyncio
async def test_cdc_outbox_worker_status_update_byte_transmission() -> None:
    """Verify status update bytes are transmitted back to Postgres via conn.put_copy_data."""
    mock_broker = AsyncMock()
    mock_broker.is_connected = True
    mock_broker.publish = AsyncMock()
    worker = CdcOutboxWorker(nats_broker=mock_broker)

    mock_conn = AsyncMock()

    # 1. Feed Keepalive message with conn
    keepalive_bytes = _build_keepalive_msg(wal_end_lsn=88888, reply_requested=True)
    await worker.process_wal_message(keepalive_bytes, conn=mock_conn)

    mock_conn.put_copy_data.assert_called_once()
    status_bytes = mock_conn.put_copy_data.call_args[0][0]
    assert isinstance(status_bytes, bytes)
    assert len(status_bytes) == 34
    assert status_bytes[0:1] == b"r"
    assert worker._last_acknowledged_lsn == 88888

    # 2. Feed insert record message with conn
    mock_conn.reset_mock()
    rel_payload = _wrap_xlogdata(_build_relation_msg(rel_id=9001))
    await worker.process_wal_message(rel_payload, lsn=90000, conn=mock_conn)

    event_id = str(uuid.uuid4())
    ins_payload = _wrap_xlogdata(
        _build_insert_msg(
            rel_id=9001,
            values=[
                event_id,
                "UserCreated",
                "User",
                "u-trans",
                json.dumps({"user_id": "u-trans", "email": "trans@test.com"}),
                json.dumps({"correlation_id": "corr-trans"}),
            ],
        ),
        start_lsn=95000,
    )
    events = await worker.process_wal_message(ins_payload, lsn=95000, conn=mock_conn)
    assert len(events) == 1
    mock_conn.put_copy_data.assert_called_once()
    status_bytes2 = mock_conn.put_copy_data.call_args[0][0]
    assert status_bytes2[0:1] == b"r"
    assert worker._last_acknowledged_lsn == 95000


def test_pgoutput_decoder_struct_error_gracefulness() -> None:
    """Verify decoder gracefully handles struct.error and binary corruption returning None."""
    decoder = PgOutputDecoder()

    # Force struct.error by patching struct.unpack_from
    with patch("struct.unpack_from", side_effect=struct.error("unpack error")):
        valid_keepalive = _build_keepalive_msg(wal_end_lsn=1000)
        assert decoder.decode(valid_keepalive) is None

    # Invalid frame bytes that cause struct / index bounds failures
    corrupted_frames = [
        b"w\x00\x00",  # Truncated XLogData
        b"k\x00\x00\x00\x00",  # Truncated Keepalive
        b"R\x00\x00\x00\x01\x00",  # Malformed relation
        b"I\x00\x00\x00\x01N\x00\x05",  # Truncated insert header (< 8 bytes offset)
        b"I\x00",  # Truncated Insert byte length < 8
    ]
    for frame in corrupted_frames:
        assert decoder.decode(frame) is None


def test_lsn_to_int_exception_safety() -> None:
    """Verify lsn_to_int gracefully handles invalid inputs catching ValueError, AttributeError, IndexError."""
    # Invalid hex format
    assert lsn_to_int("INVALID/HEX") == 0
    assert lsn_to_int("16/ZZZZZZ") == 0
    assert lsn_to_int("ZZZZ/16") == 0

    # Invalid slash split counts
    assert lsn_to_int("1/2/3") == 0
    assert lsn_to_int("1/2/3/4") == 0
    assert lsn_to_int("///") == 0

    # Partial / boundary slashes
    assert lsn_to_int("/100") == 0
    assert lsn_to_int("100/") == 0
    assert lsn_to_int("/") == 0

    # Non-string types (AttributeError / TypeError handled)
    assert lsn_to_int(None) == 0  # type: ignore[arg-type]
    assert lsn_to_int(12345) == 0  # type: ignore[arg-type]
    assert lsn_to_int(["1/2"]) == 0  # type: ignore[arg-type]
    assert lsn_to_int({"lsn": "1/2"}) == 0  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cdc_outbox_worker_unmapped_insert_record_dispatch_failure_does_not_advance_lsn() -> (
    None
):
    mock_broker = AsyncMock()
    mock_broker.is_connected = True
    worker = CdcOutboxWorker(nats_broker=mock_broker)

    # Process insert WAL message for unmapped relation (relation_name is "") without prior R msg
    with patch.object(worker, "dispatch_insert_record", return_value=None):
        ins_payload = _wrap_xlogdata(
            _build_insert_msg(
                rel_id=8888,
                values=[
                    str(uuid.uuid4()),
                    "UserCreated",
                    "User",
                    "u-unmapped",
                    json.dumps({"user_id": "u-unmapped"}),
                    json.dumps({}),
                ],
            ),
            start_lsn=88888,
        )
        events = await worker.process_wal_message(ins_payload, lsn=88888)
        assert len(events) == 0
        # LSN must NOT advance when dispatch returns None
        assert worker._last_acknowledged_lsn == 0
