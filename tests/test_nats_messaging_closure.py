from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.nats_messaging as nats_module
from app.services.nats_messaging import NatsService


@pytest.mark.asyncio
async def test_nats_not_connected_guards():
    service = NatsService()
    await service.close()
    with pytest.raises(RuntimeError, match="Not connected"):
        await service.ensure_stream("stream", [])
    with pytest.raises(RuntimeError, match="Not connected"):
        await service.publish("subject", b"data")
    with pytest.raises(RuntimeError, match="Not connected"):
        await service.publish_jetstream("subject", b"data")
    with pytest.raises(RuntimeError, match="Not connected"):
        await service.subscribe("subject", AsyncMock())
    with pytest.raises(RuntimeError, match="Not connected"):
        await service.subscribe_jetstream("stream", "subject", AsyncMock())


@pytest.mark.asyncio
async def test_nats_stream_setup_logs_connection_error():
    service = NatsService()
    service._js = AsyncMock()
    service._js.add_stream.side_effect = ConnectionError("offline")
    await service.ensure_stream("stream", ["subject"], max_age=1)


@pytest.mark.asyncio
async def test_nats_jetstream_publish_accepts_bytes():
    service = NatsService()
    service._js = AsyncMock()
    ack = MagicMock(seq=7)
    service._js.publish.return_value = ack
    await service.publish_jetstream("subject", b"raw")
    service._js.publish.assert_awaited_once()
    args, kwargs = service._js.publish.call_args
    assert args == ("subject", b"raw")
    assert "Nats-Msg-Id" in kwargs["headers"]


def test_nats_singleton_double_check_handles_race_inside_lock():
    original_service = nats_module._nats_service
    original_lock = nats_module._nats_service_lock
    raced_service = NatsService(name="raced")

    class RaceLock:
        def __enter__(self):
            nats_module._nats_service = raced_service
            return self

        def __exit__(self, *_args):
            return False

    try:
        nats_module._nats_service = None
        nats_module._nats_service_lock = RaceLock()
        assert nats_module.get_nats_service() is raced_service
    finally:
        nats_module._nats_service = original_service
        nats_module._nats_service_lock = original_lock
