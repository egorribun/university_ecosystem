"""Closure test for explicitly opted-out insecure SpiceDB channel."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from app.auth.rbac import PermissionChecker
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


@pytest.mark.asyncio
async def test_spicedb_provider_opens_secure_channel_and_closes_it():
    provider = SpiceDBProvider()
    channel = AsyncMock()
    channel.close = AsyncMock()
    credentials = object()

    with (
        patch.dict(os.environ, {"SPICEDB_INSECURE": "false"}),
        patch("app.core.config.settings") as settings,
        patch(
            "grpcutil.bearer_token_credentials", return_value=credentials
        ) as make_credentials,
        patch("grpc.aio.secure_channel", return_value=channel) as secure,
    ):
        settings.spicedb_endpoint = "localhost:50051"
        settings.spicedb_preshared_key = "token"
        generator = provider.spicedb_channel()
        assert await generator.__anext__() is channel
        await generator.aclose()

    make_credentials.assert_called_once_with("token")
    secure.assert_called_once()
    channel.close.assert_awaited_once()


def test_spicedb_provider_builds_request_scoped_permission_checker():
    provider = SpiceDBProvider()
    channel = object()

    checker = provider.provide_permission_checker(channel)

    assert isinstance(checker, PermissionChecker)
