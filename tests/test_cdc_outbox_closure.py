from __future__ import annotations

import json
import struct
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.cdc_outbox as cdc
from app.core.events import UserCreated


def _relation_prefix(relation_id: int = 7, columns: int = 1) -> bytes:
    return (
        b"R"
        + struct.pack(">I", relation_id)
        + b"public\x00stored_events\x00d"
        + struct.pack(">H", columns)
    )


def _insert(relation_id: int, values: list[tuple[bytes, bytes]]) -> bytes:
    payload = b"I" + struct.pack(">I", relation_id) + b"N"
    payload += struct.pack(">H", len(values))
    for kind, value in values:
        payload += kind
        if kind == b"t":
            payload += struct.pack(">I", len(value)) + value
    return payload


def test_metric_factory_handles_disabled_collectors_and_registration_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert cdc._get_or_create_metric(None, "disabled", "disabled") is None

    created = object()
    monkeypatch.setattr(cdc, "REGISTRY", None)
    assert (
        cdc._get_or_create_metric(lambda *args, **kwargs: created, "new", "doc")
        is created
    )

    existing = object()
    registry = MagicMock()
    registry._names_to_collectors = {"existing": existing}
    monkeypatch.setattr(cdc, "REGISTRY", registry)
    constructor = MagicMock()
    assert cdc._get_or_create_metric(constructor, "existing", "doc") is existing
    constructor.assert_not_called()

    def duplicate_after_registration(*args: object, **kwargs: object) -> object:
        registry._names_to_collectors["raced"] = existing
        raise ValueError("duplicate metric")

    assert (
        cdc._get_or_create_metric(duplicate_after_registration, "raced", "doc")
        is existing
    )

    registry._names_to_collectors.clear()
    with pytest.raises(ValueError, match="duplicate metric"):
        cdc._get_or_create_metric(
            MagicMock(side_effect=ValueError("duplicate metric")),
            "unregistered",
            "doc",
        )


def test_standby_status_update_clamps_pre_postgres_epoch_clock() -> None:
    with patch.object(cdc.time, "time", return_value=0):
        payload = cdc.format_standby_status_update(11)
    assert struct.unpack_from(">QQQQB", payload, 1) == (11, 11, 11, 0, 0)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"R\x00\x00\x00",
        b"R" + struct.pack(">I", 1),
        b"R" + struct.pack(">I", 1) + b"public\x00",
        b"R" + struct.pack(">I", 1) + b"p\x00r\x00",
    ],
)
def test_decoder_rejects_empty_and_truncated_relation_fields(payload: bytes) -> None:
    decoder = cdc.PgOutputDecoder()
    if payload:
        assert decoder.decode(payload) is None
    else:
        assert decoder.decode(payload) is None
        assert decoder._decode_pgoutput_payload(payload, lsn=0) is None


@pytest.mark.parametrize(
    ("suffix", "expected_columns"),
    [
        (b"", 0),
        (b"\x00unterminated", 0),
        (b"\x00name\x00\x00", 0),
    ],
)
def test_decoder_keeps_safe_partial_relation_schema(
    suffix: bytes, expected_columns: int
) -> None:
    decoder = cdc.PgOutputDecoder()
    assert decoder.decode(_relation_prefix() + suffix) is None
    assert len(decoder.relations[7].columns) == expected_columns


def test_decoder_handles_direct_unknown_and_inner_struct_errors() -> None:
    decoder = cdc.PgOutputDecoder()
    assert decoder.decode(b"Z") is None
    with patch.object(cdc.struct, "unpack_from", side_effect=TypeError("bad frame")):
        assert decoder._decode_pgoutput_payload(_relation_prefix(), lsn=0) is None


def test_decoder_covers_null_json_numeric_and_invalid_tuple_values() -> None:
    decoder = cdc.PgOutputDecoder()
    relation_id = 12
    columns = ["payload", "metadata_", "error_count", "version", "plain"]
    relation = (
        b"R"
        + struct.pack(">I", relation_id)
        + b"public\x00stored_events\x00d"
        + struct.pack(">H", len(columns))
    )
    for name in columns:
        relation += b"\x00" + name.encode() + b"\x00" + struct.pack(">Ii", 25, -1)
    assert decoder.decode(relation) is None

    record = decoder.decode(
        _insert(
            relation_id,
            [
                (b"t", b"not-json"),
                (b"n", b""),
                (b"t", b"42"),
                (b"t", b"not-an-int"),
                (b"u", b""),
            ],
        ),
        default_lsn=99,
    )
    assert isinstance(record, cdc.CDCInsertRecord)
    assert record.data == {
        "payload": "not-json",
        "metadata_": None,
        "error_count": 42,
        "version": "not-an-int",
        "plain": None,
    }

    assert decoder.decode(b"I" + struct.pack(">I", relation_id) + b"O\x00\x00") is None
    assert decoder.decode(_insert(relation_id, [(b"x", b"")])) is None

    short_length = (
        b"I" + struct.pack(">I", relation_id) + b"N\x00\x01t" + b"\x00\x00\x00"
    )
    assert decoder.decode(short_length) is None
    overlong = (
        b"I"
        + struct.pack(">I", relation_id)
        + b"N\x00\x01t"
        + struct.pack(">I", 9)
        + b"x"
    )
    assert decoder.decode(overlong) is None


@pytest.mark.asyncio
async def test_provision_resources_owns_and_closes_its_connection() -> None:
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[1, 1])
    worker = cdc.CdcOutboxWorker(dsn="postgresql+asyncpg://db/test")
    with patch.object(
        cdc.asyncpg, "connect", new=AsyncMock(return_value=conn)
    ) as connect:
        await worker.provision_replication_resources()
    connect.assert_awaited_once_with("postgresql://db/test")
    conn.execute.assert_not_awaited()
    conn.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_dispatch_handles_missing_and_serialized_payload_variants() -> None:
    broker = AsyncMock()
    worker = cdc.CdcOutboxWorker(nats_broker=broker)
    missing = cdc.CDCInsertRecord(1, "stored_events", {"payload": {}}, 1)
    assert await worker.dispatch_insert_record(missing) is None

    event_id = str(uuid.uuid4())
    user_id = uuid.uuid4()
    serialized = cdc.CDCInsertRecord(
        1,
        "stored_events",
        {
            "id": "stored-id",
            "event_type": "UserCreated",
            "payload": json.dumps(
                {"user_id": str(user_id), "email": "cdc@example.com"}
            ),
            "metadata_": json.dumps({"event_id": event_id, "user_id": str(user_id)}),
        },
        2,
    )
    event = await worker.dispatch_insert_record(serialized)
    assert isinstance(event, UserCreated)
    assert event.event_id == event_id
    assert event.metadata.user_id == user_id

    uuid_metadata = cdc.CDCInsertRecord(
        1,
        "stored_events",
        {
            "event_type": "UserCreated",
            "payload": "{invalid",
            "metadata_": {"user_id": user_id},
        },
        3,
    )
    event = await worker.dispatch_insert_record(uuid_metadata)
    assert isinstance(event, UserCreated)
    assert event.metadata.user_id == user_id

    no_metadata = cdc.CDCInsertRecord(
        1,
        "stored_events",
        {
            "event_type": "UserCreated",
            "payload": {},
            "metadata_": "{invalid",
        },
        4,
    )
    assert isinstance(await worker.dispatch_insert_record(no_metadata), UserCreated)


@pytest.mark.asyncio
async def test_dispatch_publish_failure_is_contained_and_counted() -> None:
    broker = AsyncMock()
    broker.publish.side_effect = OSError("nats unavailable")
    worker = cdc.CdcOutboxWorker(nats_broker=broker)
    record = cdc.CDCInsertRecord(
        1,
        "stored_events",
        {"event_type": "UserCreated", "payload": {}},
        1,
    )
    assert await worker.dispatch_insert_record(record) is None


@pytest.mark.asyncio
async def test_process_wal_message_covers_failure_and_lsn_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())
    worker._decoder.decode = MagicMock(side_effect=ValueError("malformed"))
    assert await worker.process_wal_message(b"bad") == []

    conn = AsyncMock()
    worker._decoder.decode = MagicMock(
        return_value=cdc.CDCInsertRecord(1, "other_table", {}, 25)
    )
    assert await worker.process_wal_message(b"record", conn=conn) == []
    conn.put_copy_data.assert_awaited_once()

    conn.reset_mock()
    worker._decoder.decode = MagicMock(
        return_value=cdc.CDCInsertRecord(1, "other_table", {}, 0)
    )
    assert await worker.process_wal_message(b"record", conn=conn) == []
    conn.put_copy_data.assert_not_awaited()

    worker._decoder.decode = MagicMock(
        return_value=cdc.CDCInsertRecord(1, "stored_events", {}, 0)
    )
    worker.dispatch_insert_record = AsyncMock(return_value=UserCreated())
    events = await worker.process_wal_message(b"record")
    assert len(events) == 1

    worker._decoder.decode = MagicMock(return_value=cdc.KeepaliveMessage(0, 0, False))
    assert await worker.process_wal_message(b"keepalive") == []

    lag_metric = MagicMock()
    monkeypatch.setattr(cdc, "CDC_WAL_REPLICATION_LAG_BYTES", None)
    monkeypatch.setattr(cdc, "OUTBOX_CDC_REPLICATION_LAG_SECONDS", lag_metric)
    server_clock = int((time.time() - 946684800 - 1) * 1_000_000)
    worker._decoder.decode = MagicMock(
        return_value=cdc.KeepaliveMessage(50, server_clock, True)
    )
    await worker.process_wal_message(b"keepalive")
    lag_metric.labels.assert_called_once_with(slot_name=worker.slot_name)


@pytest.mark.asyncio
async def test_run_forever_connects_and_processes_replication_stream() -> None:
    broker = MagicMock(is_connected=False)
    broker.connect = AsyncMock()
    worker = cdc.CdcOutboxWorker(nats_broker=broker)
    worker.provision_replication_resources = AsyncMock()
    worker.process_wal_message = AsyncMock(return_value=[])
    conn = AsyncMock()

    async def copy_out(statement: str, writer: object, timeout: object) -> None:
        assert "START_REPLICATION SLOT" in statement
        assert timeout is None
        await writer(b"wal")  # type: ignore[operator]
        worker._is_running = False

    conn._copy_out.side_effect = copy_out
    with patch.object(cdc.asyncpg, "connect", new=AsyncMock(return_value=conn)):
        await worker.run_forever()

    broker.connect.assert_awaited_once_with()
    worker.process_wal_message.assert_awaited_once_with(b"wal", conn=conn)
    conn.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_replication_writer_ignores_data_after_stop() -> None:
    broker = MagicMock(is_connected=True)
    worker = cdc.CdcOutboxWorker(nats_broker=broker)
    worker.provision_replication_resources = AsyncMock()
    worker.process_wal_message = AsyncMock(return_value=[])
    conn = AsyncMock()

    async def copy_out(statement: str, writer: object, timeout: object) -> None:
        worker._is_running = False
        await writer(b"late-wal")  # type: ignore[operator]

    conn._copy_out.side_effect = copy_out
    with patch.object(cdc.asyncpg, "connect", new=AsyncMock(return_value=conn)):
        await worker.run_forever()

    worker.process_wal_message.assert_not_awaited()
    conn.close.assert_awaited_once_with()
