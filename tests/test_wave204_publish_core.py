"""Wave 204 SW1 — NatsTaskBroker.publish_core() unit tests.

publish_core is the CORE-NATS (fire-and-forget, no JetStream stream) publisher
that mirrors in-process ws_manager chat broadcasts onto the ws-hub ``chat.*``
core subscription so frames reach browser clients LIVE.

Three contracts under test:
  1. orjson serialisation handles the raw ``uuid.UUID`` + ``datetime`` values
     the ``new_message`` frame carries (stdlib ``json.dumps`` would TypeError).
  2. connect-if-needed: a None core connection triggers ``connect()`` first.
  3. best-effort: a raising ``_nc.publish`` (infra error) is swallowed, and a
     still-None connection after connect logs + returns without raising — the
     in-process delivery + refetch fallback must stay intact.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.nats_broker import NatsTaskBroker


def _new_message_frame() -> dict:
    """A frame shaped like the real ws envelope, with raw UUID + datetime."""
    chat_id = uuid.uuid4()
    return {
        "type": "new_message",
        "room": str(chat_id),
        # `payload` mirrors serialize_message(): raw uuid.UUID + ISO datetime.
        "payload": {
            "type": "new_message",
            "chat_id": str(chat_id),
            "message": {
                "id": uuid.uuid4(),  # raw UUID — json.dumps would crash here
                "chat_id": chat_id,  # raw UUID
                "sender_id": uuid.uuid4(),  # raw UUID
                "content": "hello",
                "created_at": datetime(2026, 5, 30, 12, 0, tzinfo=UTC),  # raw datetime
                "read_status": False,
                "read_at": None,
            },
        },
    }


@pytest.mark.asyncio
async def test_publish_core_serializes_uuid_and_datetime() -> None:
    """orjson serialises raw uuid.UUID + datetime without TypeError."""
    broker = NatsTaskBroker()
    mock_nc = MagicMock()
    mock_nc.is_connected = True
    mock_nc.publish = AsyncMock()
    broker._nc = mock_nc  # already connected

    frame = _new_message_frame()
    subject = f"chat.{frame['room']}"

    await broker.publish_core(subject, frame)

    mock_nc.publish.assert_awaited_once()
    call = mock_nc.publish.call_args
    assert call.args[0] == subject
    data = call.args[1]
    assert isinstance(data, bytes)
    # Round-trips through stdlib json: orjson produced valid JSON with the
    # UUIDs stringified + the datetime rendered ISO-8601 (no crash).
    decoded = json.loads(data)
    raw_id = frame["payload"]["message"]["id"]
    assert decoded["payload"]["message"]["id"] == str(raw_id)
    assert decoded["payload"]["message"]["created_at"].startswith("2026-05-30T12:00:00")
    # W3C trace headers are injected (matches publish()).
    assert "headers" in call.kwargs


@pytest.mark.asyncio
async def test_publish_core_skips_when_nc_is_none() -> None:
    """No connection → skip silently. publish_core must NOT trigger a connect
    from this ephemeral hot path: a connect would add a multi-second timeout to
    the message-send path during a NATS outage and would raise in test/CLI
    contexts where NATS isn't running. The frame self-heals via refetch."""
    broker = NatsTaskBroker()
    assert broker._nc is None

    with patch("app.core.nats_broker.nats.connect", new=AsyncMock()) as mock_connect:
        # No exception; crucially, NO connect attempted.
        await broker.publish_core("chat.abc", {"type": "read", "room": "abc"})

    mock_connect.assert_not_awaited()
    assert broker._nc is None


@pytest.mark.asyncio
async def test_publish_core_swallows_publish_error() -> None:
    """A raising _nc.publish (infra error) is swallowed — never propagates."""
    broker = NatsTaskBroker()
    mock_nc = MagicMock()
    mock_nc.is_connected = True
    mock_nc.publish = AsyncMock(side_effect=ConnectionError("nats down"))
    broker._nc = mock_nc

    # Must NOT raise — the caller's in-process delivery + refetch fallback
    # depend on this being best-effort.
    await broker.publish_core("chat.abc", {"type": "new_message", "room": "abc"})

    mock_nc.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_core_skips_when_not_connected() -> None:
    """A present-but-disconnected core connection → skip without publishing
    (e.g. mid NATS-outage; the broker's background reconnect restores it)."""
    broker = NatsTaskBroker()
    mock_nc = MagicMock()
    mock_nc.is_connected = False
    mock_nc.publish = AsyncMock()
    broker._nc = mock_nc

    await broker.publish_core("chat.abc", {"type": "read", "room": "abc"})

    mock_nc.publish.assert_not_awaited()
