"""Closure test for explicitly opted-out insecure SpiceDB channel."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from app.core.di.spicedb import SpiceDBProvider


@pytest.mark.asyncio
async def test_spicedb_provider_opens_insecure_channel_when_explicitly_enabled():
    provider = SpiceDBProvider()
    channel = AsyncMock()
    channel.close = AsyncMock()

    with (
        patch.dict(os.environ, {"SPICEDB_INSECURE": "true"}),
        patch("app.core.config.settings") as settings,
        patch("grpc.aio.insecure_channel", return_value=channel) as insecure,
    ):
        settings.spicedb_endpoint = "localhost:50051"
        settings.spicedb_preshared_key = "token"
        generator = provider.spicedb_channel()
        assert await generator.__anext__() is channel
        await generator.aclose()

    insecure.assert_called_once()
    channel.close.assert_awaited_once()
