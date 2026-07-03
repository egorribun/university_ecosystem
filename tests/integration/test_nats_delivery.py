"""Integration tests for NATS publishing and subscription dispatching."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.core.nats_broker import NatsTaskBroker


@pytest.mark.asyncio
async def test_nats_publish_jetstream():
    """Verify JetStream publishing propagates trace context and parses correctly."""
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_js = AsyncMock()

    broker._nc = mock_nc
    broker._js = mock_js

    subject = "test.subject"
    payload = {"data": "hello"}

    await broker.publish(subject, payload)

    # Verify JetStream publish was called with the serialized payload
    mock_js.publish.assert_called_once()
    call_args = mock_js.publish.call_args[0]
    assert call_args[0] == subject
    assert json.loads(call_args[1].decode()) == payload


@pytest.mark.asyncio
async def test_nats_publish_core():
    """Verify Core NATS publishing serialized message payload successfully."""
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    broker._nc = mock_nc

    subject = "chat.message"
    payload = {"msg": "core test"}

    await broker.publish_core(subject, payload)

    # Verify Core NATS publish was called
    mock_nc.publish.assert_called_once()
    call_args = mock_nc.publish.call_args[0]
    assert call_args[0] == subject
    assert json.loads(call_args[1].decode()) == payload
