"""Safety boundaries for the deferred, unsupported CDC transport."""

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

import app.core.lifespan as lifecycle
import app.workers.cdc_outbox as cdc
from app.core.events import UserCreated


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["production", "testing"])
async def test_cdc_opt_in_fails_before_lifespan_resources(environment: str) -> None:
    app = FastAPI()
    with (
        patch.object(lifecycle, "settings") as settings,
        patch.object(lifecycle, "_reset_closed_dishka_container") as reset,
        patch.object(lifecycle, "_startup_database_and_di", new=AsyncMock()) as startup,
    ):
        settings.environment = environment
        settings.embedded_cdc_outbox_worker_enabled = True
        # Make an unsafe entry fail promptly instead of opening other resources.
        startup.side_effect = AssertionError("startup reached before CDC preflight")
        with pytest.raises(RuntimeError, match=r"CDC.*unsupported.*ADR-037"):
            async with lifecycle.lifespan(app):
                pytest.fail("unsupported CDC must not start")
        reset.assert_not_called()
        startup.assert_not_awaited()


@pytest.mark.asyncio
async def test_cdc_opt_in_fails_before_background_tasks_or_polling_selection() -> None:
    app = FastAPI()
    with (
        patch.object(lifecycle, "settings") as settings,
        patch.object(lifecycle, "setup_periodic_cleanups", new=AsyncMock()) as cleanup,
    ):
        settings.embedded_cdc_outbox_worker_enabled = True
        cleanup.side_effect = AssertionError("cleanup reached before CDC preflight")
        with pytest.raises(RuntimeError, match=r"CDC.*unsupported.*ADR-037"):
            await lifecycle._startup_background_workers(app)
        cleanup.assert_not_awaited()
        assert not hasattr(app.state, "background_tasks")


@pytest.mark.asyncio
async def test_standalone_cdc_fails_before_connecting_or_provisioning() -> None:
    broker = MagicMock(is_connected=False, connect=AsyncMock())
    worker = cdc.CdcOutboxWorker(nats_broker=broker)
    with patch.object(
        worker, "provision_replication_resources", new=AsyncMock()
    ) as provision:
        provision.side_effect = AssertionError("provisioning reached before preflight")
        with pytest.raises(RuntimeError, match=r"CDC.*unsupported.*ADR-037"):
            await worker.run_forever()
        assert worker._is_running is False
        broker.connect.assert_not_awaited()
        provision.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint", [0, 50])
@pytest.mark.parametrize("reply_requested", [False, True])
async def test_keepalive_cannot_acknowledge_failed_delivery(
    checkpoint: int, reply_requested: bool
) -> None:
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())
    worker.send_status_update(checkpoint)
    conn = AsyncMock()
    record = cdc.CDCInsertRecord(1, "stored_events", {}, 100)
    with (
        patch.object(worker._decoder, "decode", return_value=record),
        patch.object(
            worker, "dispatch_insert_record", new=AsyncMock(return_value=None)
        ),
    ):
        assert await worker.process_wal_message(b"insert", conn=conn) == []
    conn.put_copy_data.assert_not_awaited()
    keepalive = b"k" + struct.pack(">QqB", 200, 0, int(reply_requested))
    assert await worker.process_wal_message(keepalive, conn=conn) == []
    assert worker._last_acknowledged_lsn == checkpoint
    packet = conn.put_copy_data.await_args.args[0]
    assert struct.unpack_from(">QQQ", packet, 1) == (checkpoint,) * 3


@pytest.mark.asyncio
async def test_keepalive_reports_only_the_successful_delivery_checkpoint() -> None:
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())
    record = cdc.CDCInsertRecord(1, "stored_events", {}, 100)
    with (
        patch.object(worker._decoder, "decode", return_value=record),
        patch.object(
            worker, "dispatch_insert_record", new=AsyncMock(return_value=UserCreated())
        ),
    ):
        await worker.process_wal_message(b"insert")
    conn = AsyncMock()
    await worker.process_wal_message(b"k" + struct.pack(">QqB", 200, 0, 1), conn=conn)
    assert worker._last_acknowledged_lsn == 100
    assert (
        struct.unpack_from(">QQQ", conn.put_copy_data.await_args.args[0], 1)
        == (100,) * 3
    )


def test_status_packet_never_regresses_the_checkpoint() -> None:
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock())
    worker.send_status_update(100)
    packet = worker.send_status_update(50)
    assert struct.unpack_from(">QQQ", packet, 1) == (100,) * 3
