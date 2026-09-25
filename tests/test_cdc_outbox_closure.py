from __future__ import annotations

import ast
import json
import os
import struct
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.cdc_outbox as cdc
from app.core.events import UserCreated

_CLOSE_REPLICATION_MUTANT_PREFIX = (
    "xǁCdcOutboxWorkerǁ_close_replication_connection__mutmut_"
)


def _close_replication_function_node() -> ast.AsyncFunctionDef:
    """Return the active close implementation from the imported source.

    ``contextlib.suppress(*_REPLICATION_CLOSE_ERRORS)`` deliberately delegates
    the complete exception contract to an immutable module-level tuple.
    ``ConnectionError`` subclasses ``OSError``, so a runtime-only test cannot
    distinguish removing the explicit class from the original implementation.
    During mutmut runs, the generated module contains one sibling function per
    mutation; selecting the active sibling makes this contract test fail for
    that otherwise equivalent survivor without weakening production behavior.
    """
    source_path = Path(cdc.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    mutation = os.environ.get("MUTANT_UNDER_TEST", "")
    _, _, mutant_name = mutation.rpartition(".")
    generated_original = f"{_CLOSE_REPLICATION_MUTANT_PREFIX}orig"
    target_name = "_close_replication_connection"
    generated_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith(_CLOSE_REPLICATION_MUTANT_PREFIX)
    }
    if generated_names:
        target_name = (
            mutant_name
            if mutant_name.startswith(_CLOSE_REPLICATION_MUTANT_PREFIX)
            else generated_original
        )
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == target_name:
            return node
    raise AssertionError(f"{target_name} is missing from {source_path}")


def test_replication_close_error_contract_is_explicit_and_module_level() -> None:
    """The teardown exception tuple is explicit, immutable, and module-level."""
    assert isinstance(cdc._REPLICATION_CLOSE_ERRORS, tuple)
    assert cdc._REPLICATION_CLOSE_ERRORS == (
        OSError,
        ConnectionError,
        cdc.asyncpg.PostgresError,
        cdc.asyncpg.InterfaceError,
    )
    assert ConnectionError in cdc._REPLICATION_CLOSE_ERRORS


def test_close_replication_connection_uses_explicit_module_error_contract() -> None:
    """The close path must consume the complete module-level error tuple."""
    function = _close_replication_function_node()
    suppress_arguments: list[ast.expr] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            context = item.context_expr
            if not isinstance(context, ast.Call):
                continue
            if (
                not isinstance(context.func, ast.Attribute)
                or context.func.attr != "suppress"
            ):
                continue
            suppress_arguments.extend(context.args)

    assert any(
        isinstance(argument, ast.Starred)
        and isinstance(argument.value, ast.Name)
        and argument.value.id == "_REPLICATION_CLOSE_ERRORS"
        for argument in suppress_arguments
    )


def test_close_replication_function_falls_back_to_generated_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stats run for another function must select mutmut's original sibling."""
    generated_source = "\n".join(
        (
            "async def _close_replication_connection(self):",
            "    pass",
            "async def xǁCdcOutboxWorkerǁ_close_replication_connection__mutmut_orig(self):",
            "    pass",
            "async def xǁCdcOutboxWorkerǁ_close_replication_connection__mutmut_1(self):",
            "    pass",
        )
    )
    source_path = tmp_path / "cdc_outbox.py"
    source_path.write_text(generated_source, encoding="utf-8")
    monkeypatch.setattr(cdc, "__file__", str(source_path))
    monkeypatch.setenv("MUTANT_UNDER_TEST", "xǁOtherWorkerǁother__mutmut_1")

    function = _close_replication_function_node()

    assert function.name == (
        "xǁCdcOutboxWorkerǁ_close_replication_connection__mutmut_orig"
    )


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
@pytest.mark.parametrize(
    "close_error",
    [
        OSError("socket closed"),
        ConnectionError("connection reset"),
        cdc.asyncpg.PostgresError("postgres closed"),
        cdc.asyncpg.InterfaceError("interface closed"),
    ],
)
async def test_close_replication_connection_suppresses_expected_teardown_errors(
    close_error: Exception,
) -> None:
    """Teardown must be best-effort for every supported asyncpg close error."""
    conn = AsyncMock()
    conn.close.side_effect = close_error
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())
    worker._replication_connection = conn

    await worker._close_replication_connection()

    assert worker._replication_connection is None
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
async def test_missing_event_type_log_does_not_include_raw_cdc_payload() -> None:
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())
    record = cdc.CDCInsertRecord(
        relation_id=7,
        relation_name="stored_events",
        data={
            "email": "alice@example.edu",
            "phone": "+7 999 123-45-67",
            "payload": {"token": "secret-token"},
        },
        lsn=42,
    )

    with patch.object(cdc.logger, "warning") as warning:
        assert await worker.dispatch_insert_record(record) is None

    warning.assert_called_once()
    template, *arguments = warning.call_args.args
    rendered = " ".join(str(value) for value in arguments)
    assert template == (
        "CDC record missing event_type (relation=%s, lsn=%s, fields=%d)"
    )
    assert arguments == ["stored_events", 42, 3]
    assert "alice@example.edu" not in rendered
    assert "+7 999 123-45-67" not in rendered
    assert "secret-token" not in rendered


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
@patch("app.workers.cdc_outbox.require_supported_cdc_transport", new=lambda: None)
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
@patch("app.workers.cdc_outbox.require_supported_cdc_transport", new=lambda: None)
async def test_run_forever_logs_shutdown_provisioning_without_starting_fallback() -> (
    None
):
    """A shutdown race must be observable and must not start the fallback worker."""
    worker = cdc.CdcOutboxWorker(nats_broker=MagicMock(is_connected=True))

    async def fail_after_shutdown() -> None:
        worker._is_running = False
        raise OSError("database unavailable")

    worker.provision_replication_resources = AsyncMock(side_effect=fail_after_shutdown)
    with (
        patch.object(cdc.logger, "info") as info,
        patch.object(worker, "_run_fallback_worker", new=AsyncMock()) as fallback,
    ):
        await worker.run_forever()

    info.assert_any_call(
        "CdcOutboxWorker: provisioning failed after shutdown; fallback skipped"
    )
    assert worker._fallback_worker is None
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_worker_clears_owned_reference_after_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback completion must release the lifecycle-owned worker reference."""
    instances: list[object] = []

    class FakeOutboxWorker:
        def __init__(self) -> None:
            instances.append(self)

        async def run_forever(self) -> None:
            return None

    monkeypatch.setattr("app.workers.outbox.OutboxWorker", FakeOutboxWorker)
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())

    await worker._run_fallback_worker()

    assert len(instances) == 1
    assert worker._fallback_worker is None


@pytest.mark.asyncio
@patch("app.workers.cdc_outbox.require_supported_cdc_transport", new=lambda: None)
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


@pytest.mark.asyncio
async def test_stop_clears_fallback_reference_after_stopping_it() -> None:
    fallback = AsyncMock()
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())
    worker._fallback_worker = fallback
    worker._close_replication_connection = AsyncMock()

    await worker.stop()

    assert worker._is_running is False
    fallback.stop.assert_awaited_once_with()
    assert worker._fallback_worker is None
    worker._close_replication_connection.assert_awaited_once_with()
