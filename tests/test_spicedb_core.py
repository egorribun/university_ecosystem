import os
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from authzed.api.v1 import (
    CheckPermissionRequest,
    CheckPermissionResponse,
    WatchRequest,
    WatchResponse,
)
from authzed.api.v1.permission_service_pb2_grpc import (
    PermissionsServiceServicer,
    PermissionsServiceStub,
    add_PermissionsServiceServicer_to_server,
)
from authzed.api.v1.watch_service_pb2_grpc import (
    WatchServiceServicer,
    WatchServiceStub,
    add_WatchServiceServicer_to_server,
)

from app.core.spicedb import (
    SpiceDBClient,
    _parse_endpoint,
    _StreamBearerTokenInterceptor,
    _UnaryBearerTokenInterceptor,
    close_global_spicedb_channel,
    get_async_spicedb_channel,
    get_spicedb_client,
)


@pytest.mark.parametrize("opt_in", [None, "false", "1", "true"])
@pytest.mark.parametrize("scheme", ["", "grpc://", "grpcs://"])
def test_endpoint_requires_tls_unless_explicitly_opted_out(monkeypatch, opt_in, scheme):
    if opt_in is None:
        monkeypatch.delenv("SPICEDB_INSECURE", raising=False)
    else:
        monkeypatch.setenv("SPICEDB_INSECURE", opt_in)

    host, port, use_ssl = _parse_endpoint(f"{scheme}spicedb:50051")

    assert (host, port) == ("spicedb", 50051)
    assert use_ssl is (scheme == "grpcs://" or opt_in != "true")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interceptor_class,method",
    [
        (_UnaryBearerTokenInterceptor, "intercept_unary_unary"),
        (_StreamBearerTokenInterceptor, "intercept_unary_stream"),
    ],
)
async def test_plaintext_auth_preserves_all_other_call_details(
    interceptor_class, method
):
    token = secrets.token_urlsafe(24)
    credentials = grpc.access_token_call_credentials(secrets.token_urlsafe(24))
    details = grpc.aio.ClientCallDetails(b"/test/method", 0.25, None, credentials, True)
    request, response = object(), object()

    async def continuation(forwarded_details, forwarded_request):
        assert forwarded_request is request
        assert forwarded_details._replace(metadata=None) == details
        assert tuple(forwarded_details.metadata) == (
            ("authorization", f"Bearer {token}"),
        )
        return response

    interceptor = interceptor_class(token)
    assert (
        await getattr(interceptor, method)(continuation, details, request) is response
    )
    assert details.metadata is None


@pytest.fixture
async def spicedb_rpc_server():
    """Require a synthetic PSK at a real gRPC transport boundary."""
    token = secrets.token_urlsafe(24)
    received = []

    async def authenticate(request, context):
        metadata = tuple(context.invocation_metadata())
        received.append((request, metadata))
        authorization = [value for key, value in metadata if key == "authorization"]
        if authorization != [f"Bearer {token}"]:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing test auth")

    class Permissions(PermissionsServiceServicer):
        async def CheckPermission(self, request, context):
            await authenticate(request, context)
            return CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )

    class Watch(WatchServiceServicer):
        async def Watch(self, request, context):
            await authenticate(request, context)
            yield WatchResponse()

    server = grpc.aio.server()
    add_PermissionsServiceServicer_to_server(Permissions(), server)
    add_WatchServiceServicer_to_server(Watch(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield SimpleNamespace(
            token=token, port=port, endpoint=f"127.0.0.1:{port}", received=received
        )
    finally:
        await server.stop(0)


@pytest.fixture(params=["global", "provider"])
async def plaintext_spicedb_channel(request, monkeypatch, spicedb_rpc_server):
    import app.core.config as config
    import app.core.spicedb as spicedb
    from app.core.di.spicedb import SpiceDBProvider

    test_settings = SimpleNamespace(
        spicedb_endpoint=spicedb_rpc_server.endpoint,
        spicedb_preshared_key=spicedb_rpc_server.token,
    )
    monkeypatch.setenv("SPICEDB_INSECURE", "true")
    monkeypatch.setattr(config, "settings", test_settings)
    monkeypatch.setattr(spicedb, "settings", test_settings)
    monkeypatch.setattr(spicedb, "_global_channel", None)
    monkeypatch.setattr(spicedb, "_global_channel_lock", None)
    generator = (
        get_async_spicedb_channel()
        if request.param == "global"
        else SpiceDBProvider().spicedb_channel()
    )
    channel = await anext(generator)
    try:
        yield channel
    finally:
        await generator.aclose()
        if request.param == "global":
            await close_global_spicedb_channel()


@pytest.mark.asyncio
@pytest.mark.parametrize("rpc", ["permission", "watch"])
@pytest.mark.parametrize("metadata_kind", ["absent", "tuple", "aio"])
async def test_plaintext_generated_rpc_authenticates_and_preserves_metadata(
    plaintext_spicedb_channel, spicedb_rpc_server, rpc, metadata_kind
):
    existing_metadata = (
        ("x-request-id", "first"),
        ("x-request-id", "second"),
        ("trace-bin", b"\x00\x01"),
        ("authorization", "Bearer obsolete-test-value"),
        ("authorization", "Bearer another-obsolete-test-value"),
    )
    metadata = {
        "absent": None,
        "tuple": existing_metadata,
        "aio": grpc.aio.Metadata(*existing_metadata),
    }[metadata_kind]
    before = tuple(metadata or ())
    if rpc == "permission":
        request = CheckPermissionRequest(permission="view")
        response = await PermissionsServiceStub(
            plaintext_spicedb_channel
        ).CheckPermission(request, metadata=metadata, timeout=2, wait_for_ready=True)
        assert (
            response.permissionship
            == CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
        )
    else:
        request = WatchRequest(optional_object_types=["document"])
        responses = [
            response
            async for response in WatchServiceStub(plaintext_spicedb_channel).Watch(
                request, metadata=metadata, timeout=2, wait_for_ready=True
            )
        ]
        assert responses == [WatchResponse()]

    assert len(spicedb_rpc_server.received) == 1
    received_request, received_metadata = spicedb_rpc_server.received[0]
    assert received_request == request
    assert [entry for entry in received_metadata if entry[0] != "user-agent"] == [
        ("authorization", f"Bearer {spicedb_rpc_server.token}")
    ] + [entry for entry in before if entry[0] != "authorization"]
    assert tuple(metadata or ()) == before


@pytest.mark.asyncio
async def test_permission_checker_uses_authenticated_plaintext_transport(
    plaintext_spicedb_channel, spicedb_rpc_server, monkeypatch
):
    from collections import OrderedDict

    from app.auth import rbac
    from app.core.circuit_breaker import CircuitBreaker

    monkeypatch.setattr(rbac, "_permission_cache", OrderedDict())
    monkeypatch.setattr(rbac, "_spicedb_breaker", CircuitBreaker("transport-test"))

    checker = rbac.PermissionChecker(plaintext_spicedb_channel)
    assert await checker.check_permission("document", "1", "view", "user-1") is True
    assert len(spicedb_rpc_server.received) == 1
    request, _metadata = spicedb_rpc_server.received[0]
    assert request.resource.object_type == "document"
    assert request.resource.object_id == "1"
    assert request.subject.object.object_id == "user-1"
    assert request.permission == "view"


@pytest.mark.asyncio
async def test_watch_once_uses_authenticated_plaintext_transport(spicedb_rpc_server):
    from app.core.spicedb_watch import _watch_once

    await _watch_once(
        spicedb_rpc_server.token, "127.0.0.1", spicedb_rpc_server.port, False
    )
    assert len(spicedb_rpc_server.received) == 1
    request, _metadata = spicedb_rpc_server.received[0]
    assert request == WatchRequest(optional_object_types=[])


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
