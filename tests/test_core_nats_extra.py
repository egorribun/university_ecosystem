from unittest.mock import AsyncMock

import pytest

from app.core.nats_broker import NATSBroker


@pytest.mark.asyncio
async def test_nats_broker_connection(monkeypatch):
    mock_nc = AsyncMock()
    monkeypatch.setattr("nats.connect", AsyncMock(return_value=mock_nc))
    broker = NATSBroker()
    await broker.connect()
    assert broker.is_connected
