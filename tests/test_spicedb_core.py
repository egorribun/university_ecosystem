import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.spicedb import (
    SpiceDBClient,
    close_global_spicedb_channel,
    get_async_spicedb_channel,
    get_spicedb_client,
)


def test_spicedb_client_init_existing():
    """Verify SpiceDBClient returns early if client is already initialized."""
    client_wrapper = SpiceDBClient()
    mock_client = MagicMock()
    client_wrapper.client = mock_client

    assert client_wrapper._init_client() is mock_client


def test_spicedb_client_init_missing_token():
    """Verify warning is logged if spicedb_preshared_key token is missing."""
    with patch("app.core.spicedb.settings") as mock_settings:
        mock_settings.spicedb_preshared_key = ""
        mock_settings.spicedb_endpoint = "localhost:50051"

        with (
            patch("app.core.spicedb.logger") as mock_logger,
            patch("app.core.spicedb.InsecureClient"),
            patch.dict(os.environ, {"SPICEDB_INSECURE": "true"}),
        ):
            client_wrapper = SpiceDBClient()
            client_wrapper._init_client()

            mock_logger.warning.assert_any_call(
                "SPICEDB_PRESHARED_KEY is not set. SpiceDB integration will fail."
            )


def test_spicedb_client_init_secure_token_and_get_client():
    with (
        patch("app.core.spicedb.settings") as mock_settings,
        patch("app.core.spicedb.Client") as client_class,
        patch("grpcutil.bearer_token_credentials") as credentials,
        patch.dict(os.environ, {"SPICEDB_INSECURE": "false"}),
    ):
        mock_settings.spicedb_preshared_key = "secure-token"
        mock_settings.spicedb_endpoint = "grpcs://spicedb.internal:443"
        credentials.return_value = MagicMock(name="credentials")
        client = MagicMock(name="client")
        client_class.return_value = client

        wrapper = SpiceDBClient()

        assert wrapper.get_client() is client
        client_class.assert_called_once()
        credentials.assert_called_once_with("secure-token")


def test_get_spicedb_client_singleton():
    """Verify get_spicedb_client returns the same client on subsequent calls."""
    with patch("app.core.spicedb.SpiceDBClient") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        # First call gets client
        get_spicedb_client()
        # Second call should use lru_cache
        get_spicedb_client()

        mock_class.assert_called_once()
        mock_instance.get_client.assert_called_once()


@pytest.mark.asyncio
async def test_get_async_spicedb_channel_secure():
    """Test get_async_spicedb_channel creates a secure channel when ssl is enabled."""
    # Reset global channel before test
    import app.core.spicedb as spicedb_mod

    spicedb_mod._global_channel = None

    mock_channel = MagicMock()

    # We enforce use_ssl = True by not setting SPICEDB_INSECURE
    with (
        patch("app.core.spicedb.settings") as mock_settings,
        patch(
            "grpc.aio.secure_channel", return_value=mock_channel
        ) as mock_secure_channel,
        patch("grpcutil.bearer_token_credentials") as mock_creds,
        patch.dict(os.environ, {"SPICEDB_INSECURE": "false"}),
    ):
        mock_settings.spicedb_endpoint = "grpcs://localhost:443"
        mock_settings.spicedb_preshared_key = "test-token"

        # Retrieve channel
        channels = []
        async for channel in get_async_spicedb_channel():
            channels.append(channel)

        assert len(channels) == 1
        assert channels[0] is mock_channel

        # Verify secure channel creation
        mock_creds.assert_called_once_with("test-token")
        mock_secure_channel.assert_called_once()

        # Second call should yield from global singleton directly without recreating
        channels2 = []
        async for channel in get_async_spicedb_channel():
            channels2.append(channel)
        assert channels2[0] is mock_channel
        mock_secure_channel.assert_called_once()  # Still called once

        # Close global channel
        mock_close = AsyncMock()
        mock_channel.close = mock_close
        await close_global_spicedb_channel()
        mock_close.assert_awaited_once()
        assert spicedb_mod._global_channel is None


@pytest.mark.asyncio
async def test_get_async_spicedb_channel_insecure():
    """Test get_async_spicedb_channel creates an insecure channel when use_ssl is False."""
    import app.core.spicedb as spicedb_mod

    spicedb_mod._global_channel = None

    mock_channel = MagicMock()

    with (
        patch("app.core.spicedb.settings") as mock_settings,
        patch(
            "grpc.aio.insecure_channel", return_value=mock_channel
        ) as mock_insecure_channel,
        patch.dict(os.environ, {"SPICEDB_INSECURE": "true"}),
    ):
        mock_settings.spicedb_endpoint = "grpc://localhost:50051"
        mock_settings.spicedb_preshared_key = "test-token"

        channels = []
        async for channel in get_async_spicedb_channel():
            channels.append(channel)

        assert len(channels) == 1
        assert channels[0] is mock_channel
        mock_insecure_channel.assert_called_once()

        # Clean up
        mock_close = AsyncMock()
        mock_channel.close = mock_close
        await close_global_spicedb_channel()
