"""Dependency injection, health, logging, and middleware contracts."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Targets
import app.core.spicedb as spicedb_module
from app.core.di.chat import ChatProvider
from app.core.di.content import ContentProvider
from app.core.di.cqrs import CQRSProvider
from app.core.di.infrastructure import InfrastructureProvider
from app.core.di.search import SearchProvider
from app.core.di.spicedb import SpiceDBProvider
from app.core.di.users import UserProvider
from app.core.exceptions import (
    AppException,
    InvalidOperationException,
    PermissionDeniedException,
    ResourceNotFoundException,
    app_exception_handler,
)
from app.core.health import check_database_connectivity, check_spicedb_health
from app.core.logging import (
    add_otel_context,
    bind_context,
    clear_context,
    configure_logging,
    is_logger_enabled,
)
from app.core.middleware.content_size import ContentSizeLimitMiddleware


# 1. app/core/di/search.py
@pytest.mark.asyncio
async def test_search_provider_with_password():
    provider = SearchProvider()
    from app.core.config import settings

    with (
        patch("app.core.config.settings", spec=settings) as mock_settings,
        patch("app.services.search.SearchService.close", AsyncMock()) as mock_close,
    ):
        mock_settings.elasticsearch_url = "http://localhost:9200"
        mock_settings.elasticsearch_user = "elastic"
        mock_settings.elasticsearch_password = "password"  # pragma: allowlist secret

        gen = provider.search_service()
        svc = await gen.__anext__()
        assert svc is not None

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_search_provider_no_password():
    provider = SearchProvider()
    from app.core.config import settings

    with (
        patch("app.core.config.settings", spec=settings) as mock_settings,
        patch("app.services.search.SearchService.close", AsyncMock()),
    ):
        mock_settings.elasticsearch_url = "http://localhost:9200"
        mock_settings.elasticsearch_user = "elastic"
        mock_settings.elasticsearch_password = ""

        gen = provider.search_service()
        svc = await gen.__anext__()
        assert svc is not None
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()


# 2. app/core/di/cqrs.py
def test_cqrs_provider():
    provider = CQRSProvider()
    db = MagicMock()
    cache = MagicMock()
    analytics_service = MagicMock()
    container = MagicMock()
    service = MagicMock()

    assert provider.get_schedule_handler(db, cache) is not None
    assert provider.get_stats_handler(db, cache, analytics_service) is not None
    assert provider.query_bus(container) is not None
    assert provider.command_bus(container) is not None
    assert provider.create_schedule_handler(service, cache) is not None
    assert provider.update_schedule_handler(service, cache) is not None
    assert provider.delete_schedule_handler(service, cache) is not None


# 3. app/core/di/content.py
def test_content_provider():
    provider = ContentProvider()
    db = MagicMock()
    uow = MagicMock()
    vector = MagicMock()

    assert provider.notification_service(db) is not None
    with patch("app.services.vector_service.validate_url_not_internal"):
        assert provider.vector_service(db) is not None
    assert provider.group_service(db) is not None
    assert provider.event_service(uow, vector) is not None
    assert provider.story_service(uow) is not None
    assert provider.news_service(uow, vector) is not None
    assert provider.schedule_service(uow) is not None
    assert provider.user_analytics_service(db) is not None


# 4. app/core/di/chat.py
def test_chat_provider():
    provider = ChatProvider()
    db = MagicMock()
    uow = MagicMock()
    attachments = MagicMock()
    notifications = MagicMock()
    cache = MagicMock()

    assert provider.chat_repository(db) is not None
    assert provider.chat_attachment_service() is not None
    assert provider.chat_ws_notification_service(db) is not None
    assert provider.chat_query_service(uow) is not None
    assert provider.chat_message_dispatcher(uow, attachments, notifications) is not None
    assert provider.chat_maintenance_service(uow, attachments) is not None
    assert provider.chat_creation_service(uow, db, cache) is not None


# 5. app/core/di/infrastructure.py
@pytest.mark.asyncio
async def test_infrastructure_provider():
    provider = InfrastructureProvider()
    from app.core.config import settings

    # outbox_worker
    with patch("app.core.config.settings", spec=settings) as mock_settings:
        mock_settings.outbox_poll_interval_seconds = 1.0
        mock_settings.outbox_batch_size = 10
        assert provider.outbox_worker() is not None

        # audit
        assert provider.audit_service() is not None
        assert provider.secure_audit_service() is not None
        assert provider.suspicious_activity_detector() is not None
        assert provider.redis_session_service() is not None
        assert provider._session_factory() is not None

    # cache
    with patch("app.core.di.infrastructure.get_cache") as mock_get_cache:
        provider.cache()
        mock_get_cache.assert_called_once()

    # db
    session_factory = MagicMock()
    session_factory.return_value = MagicMock()
    gen_db = provider.db(session_factory)
    await gen_db.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen_db.__anext__()

    # nats_broker testing vs non-testing env, and connect exceptions
    with patch("app.core.config.settings", spec=settings) as mock_settings:
        mock_settings.environment = "production"
        from app.core.nats_broker import broker as global_broker

        with (
            patch.object(global_broker, "connect", AsyncMock()) as mock_connect,
            patch.object(global_broker, "close", AsyncMock()) as mock_close,
        ):
            gen_nats = provider.nats_broker()
            await gen_nats.__anext__()
            mock_connect.assert_called_once()
            with pytest.raises(StopAsyncIteration):
                await gen_nats.__anext__()
            mock_close.assert_called_once()

    # nats_broker connection fails with OSError
    with patch("app.core.config.settings", spec=settings) as mock_settings:
        mock_settings.environment = "production"
        from app.core.nats_broker import broker as global_broker

        with (
            patch.object(
                global_broker, "connect", AsyncMock(side_effect=OSError("NATS offline"))
            ),
            patch.object(global_broker, "close", AsyncMock()),
        ):
            gen_nats = provider.nats_broker()
            await gen_nats.__anext__()
            with pytest.raises(StopAsyncIteration):
                await gen_nats.__anext__()

    # fraud_detection_service
    with patch("app.core.config.settings", spec=settings) as mock_settings:
        mock_settings.cache_redis_url = "redis://localhost"
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        with patch("redis.asyncio.from_url", return_value=mock_client) as mock_from_url:
            gen_fraud = provider.fraud_detection_service()
            svc = await gen_fraud.__anext__()
            assert svc is not None
            mock_from_url.assert_called_once()
            with pytest.raises(StopAsyncIteration):
                await gen_fraud.__anext__()
            mock_client.close.assert_called_once()

    # session_backend
    with patch(
        "app.auth.redis_session.get_session_backend", AsyncMock()
    ) as mock_backend:
        await provider.session_backend()
        mock_backend.assert_called_once()

    # geolocation_service
    with patch(
        "app.services.geolocation.get_geolocation_service_instance", AsyncMock()
    ) as mock_geo:
        await provider.geolocation_service()
        mock_geo.assert_called_once()


# 6. app/core/di/users.py
def test_users_provider():
    provider = UserProvider()
    uow = MagicMock()
    audit = MagicMock()
    notifications = MagicMock()
    db = MagicMock()

    assert provider.user_service(uow, audit, notifications) is not None
    assert provider.user_profile_service(uow, audit, notifications) is not None
    assert provider.user_compliance_service(uow, audit) is not None
    assert provider.user_media_service(uow) is not None
    assert provider.user_repository(db) is not None
    assert provider.active_session_repository(db) is not None
    assert provider.session_service(uow) is not None

    # unit_of_work
    with patch("app.repositories.unit_of_work.get_unit_of_work") as mock_get_uow:
        mock_uow_instance = MagicMock()
        mock_get_uow.return_value = mock_uow_instance
        res_uow = provider.unit_of_work(db)
        assert res_uow == mock_uow_instance


# 7. app/core/di/spicedb.py
@pytest.mark.asyncio
async def test_spicedb_provider():
    provider = SpiceDBProvider()
    from app.core.config import settings

    # spicedb_channel with insecure_channel
    with patch("app.core.config.settings", spec=settings) as mock_settings:
        mock_settings.spicedb_endpoint = "localhost:50051"
        mock_settings.spicedb_preshared_key = "token"

        mock_channel = AsyncMock()
        mock_channel.close = AsyncMock()

        with (
            patch("grpc.aio.insecure_channel", return_value=mock_channel),
            patch("grpc.aio.secure_channel", return_value=mock_channel),
        ):
            gen = provider.spicedb_channel()
            channel = await gen.__anext__()
            assert channel == mock_channel
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
            mock_channel.close.assert_called_once()

    # provide_permission_checker
    assert provider.provide_permission_checker(MagicMock()) is not None


# 8. app/core/exceptions/__init__.py
@pytest.mark.asyncio
async def test_app_exception_handler():
    req = MagicMock()

    # 1. Custom AppException
    exc = AppException(
        "Bad request", status_code=400, code="bad_request", payload={"key": "val"}
    )
    res = await app_exception_handler(req, exc)
    assert res.status_code == 400

    # 2. Inherited Exception
    exc2 = ResourceNotFoundException("Not found")
    res2 = await app_exception_handler(req, exc2)
    assert res2.status_code == 404

    exc3 = PermissionDeniedException("Denied")
    res3 = await app_exception_handler(req, exc3)
    assert res3.status_code == 403

    exc4 = InvalidOperationException("Invalid")
    res4 = await app_exception_handler(req, exc4)
    assert res4.status_code == 400

    # 3. Non-AppException
    exc_non = ValueError("Critical issue")
    res_non = await app_exception_handler(req, exc_non)
    assert res_non.status_code == 500


# 9. app/core/health.py
@pytest.mark.asyncio
async def test_check_database_connectivity_failures():
    db = AsyncMock()

    # 1. TimeoutError
    db.execute.side_effect = TimeoutError()
    res = await check_database_connectivity(db, timeout_ms=10)
    assert res is False

    # 2. General Exception
    db.execute.side_effect = ValueError("conn failure")
    res2 = await check_database_connectivity(db, timeout_ms=10)
    assert res2 is False


@pytest.mark.asyncio
async def test_check_spicedb_health_variants():
    # 1. channel is None
    async def mock_get_channel_none():
        yield None

    with patch("app.core.spicedb.get_async_spicedb_channel", mock_get_channel_none):
        status, _ = await check_spicedb_health()
        assert status == "disabled"

    # 2. channel_ready throws TimeoutError
    mock_channel = AsyncMock()

    async def mock_get_channel_valid():
        yield mock_channel

    async def mock_ready():
        raise TimeoutError()

    mock_channel.channel_ready = mock_ready

    with patch("app.core.spicedb.get_async_spicedb_channel", mock_get_channel_valid):
        status, _ = await check_spicedb_health()
        assert status == "error"

    # 3. channel_ready throws grpc.RpcError
    import grpc

    async def mock_ready_rpc():
        raise grpc.RpcError()

    mock_channel.channel_ready = mock_ready_rpc
    with patch("app.core.spicedb.get_async_spicedb_channel", mock_get_channel_valid):
        status, _ = await check_spicedb_health()
        assert status == "error"

    # 4. general exception inside check_spicedb_health
    async def mock_get_channel_throws():
        raise ValueError("General error")
        yield None

    with patch("app.core.spicedb.get_async_spicedb_channel", mock_get_channel_throws):
        status, _ = await check_spicedb_health()
        assert status == "error"


# 10. app/core/logging.py
def test_logging_otel_context():
    # span not recording
    span = MagicMock()
    span.is_recording.return_value = False
    with patch("opentelemetry.trace.get_current_span", return_value=span):
        res = add_otel_context(None, "info", {"msg": "hello"})
        assert "trace_id" not in res

    # span recording
    span.is_recording.return_value = True
    ctx = MagicMock()
    ctx.trace_id = 12345
    ctx.span_id = 67890
    span.get_span_context.return_value = ctx
    with patch("opentelemetry.trace.get_current_span", return_value=span):
        res = add_otel_context(None, "info", {"msg": "hello"})
        assert "trace_id" in res
        assert "span_id" in res


def test_configure_logging_non_json():
    import app.core.logging as logging_module

    # Force re-configure
    logging_module._configured = False
    with (
        patch("structlog.configure"),
        patch("logging.basicConfig"),
    ):
        configure_logging(json_output=False)
        assert logging_module._configured is True


def test_is_logger_enabled():
    # 1. logger with is_enabled_for
    logger1 = MagicMock(spec=["is_enabled_for"])
    logger1.is_enabled_for.return_value = True
    assert is_logger_enabled(logger1, 10) is True

    # 2. logger with isEnabledFor
    logger2 = MagicMock(spec=["isEnabledFor"])
    logger2.isEnabledFor.return_value = False
    assert is_logger_enabled(logger2, 10) is False

    # context management
    bind_context(request_id="123")
    clear_context()


# 11. app/core/middleware/content_size.py
@pytest.mark.asyncio
async def test_content_size_middleware():
    from fastapi import FastAPI

    app = FastAPI()
    middleware = ContentSizeLimitMiddleware(app, max_bytes=100)

    # 1. Non-http scope
    scope = {"type": "lifespan"}
    receive = AsyncMock()
    send = AsyncMock()
    app_mock = AsyncMock()
    middleware.app = app_mock
    await middleware(scope, receive, send)
    app_mock.assert_called_once()

    # 2. Request with invalid content-length header
    scope2 = {
        "type": "http",
        "method": "POST",
        "path": "/api",
        "headers": [(b"content-length", b"invalid")],
        "query_string": b"",
        "server": ("127.0.0.1", 80),
    }
    send2 = AsyncMock()
    await middleware(scope2, receive, send2)
    assert send2.called

    # 3. Request exceeding limit in Content-Length
    scope3 = {
        "type": "http",
        "method": "POST",
        "path": "/api",
        "headers": [(b"content-length", b"200")],
        "query_string": b"",
        "server": ("127.0.0.1", 80),
    }
    send3 = AsyncMock()
    await middleware(scope3, receive, send3)
    assert send3.called

    # 4. Chunked stream under threshold
    scope4 = {
        "type": "http",
        "method": "POST",
        "path": "/api",
        "headers": [],
        "query_string": b"",
        "server": ("127.0.0.1", 80),
    }

    receive_chunks = AsyncMock()
    receive_chunks.side_effect = [
        {"type": "http.request", "body": b"chunk1", "more_body": True},
        {"type": "http.request", "body": b"chunk2", "more_body": False},
    ]

    middleware._max_bytes = 100
    middleware._MEM_BUFFER_THRESHOLD = 50

    send4 = AsyncMock()
    app_mock.reset_mock()
    await middleware(scope4, receive_chunks, send4)
    app_mock.assert_called_once()

    # 5. Chunked stream exceeding max bytes
    receive_large = AsyncMock()
    receive_large.side_effect = [
        {"type": "http.request", "body": b"a" * 80, "more_body": True},
        {"type": "http.request", "body": b"b" * 30, "more_body": False},
    ]
    send5 = AsyncMock()
    await middleware(scope4, receive_large, send5)
    assert send5.called

    # 6. Chunked stream spilling to tempfile
    middleware._max_bytes = 100
    middleware._MEM_BUFFER_THRESHOLD = 10
    receive_spill = AsyncMock()
    receive_spill.side_effect = [
        {"type": "http.request", "body": b"a" * 15, "more_body": True},
        {"type": "http.request", "body": b"b" * 10, "more_body": False},
    ]
    send6 = AsyncMock()
    app_mock.reset_mock()
    await middleware(scope4, receive_spill, send6)
    app_mock.assert_called_once()

    # 7. Content-length under threshold fast path
    scope7 = {
        "type": "http",
        "method": "POST",
        "path": "/api",
        "headers": [(b"content-length", b"8")],
        "query_string": b"",
        "server": ("127.0.0.1", 80),
    }
    receive_fast = AsyncMock()
    receive_fast.side_effect = [
        {"type": "http.request", "body": b"fastbody", "more_body": False}
    ]
    middleware._MEM_BUFFER_THRESHOLD = 10
    send7 = AsyncMock()
    app_mock.reset_mock()
    await middleware(scope7, receive_fast, send7)
    app_mock.assert_called_once()


# 12. app/core/spicedb.py
@pytest.mark.asyncio
async def test_spicedb_module_core():
    # Reset global state for isolation
    spicedb_module._global_channel = None

    # Mock synchronous authzed Client/InsecureClient
    with (
        patch("app.core.spicedb.Client", MagicMock()),
        patch("app.core.spicedb.InsecureClient", MagicMock()),
    ):
        # 1. SpiceDBClient sync without token warning
        with patch("app.core.spicedb.settings") as mock_settings:
            mock_settings.spicedb_endpoint = "localhost:50051"
            mock_settings.spicedb_preshared_key = ""
            mock_settings.spicedb_insecure = True

            client = spicedb_module.SpiceDBClient()
            assert client.get_client() is not None

            assert spicedb_module.get_spicedb_client() is not None

        # 2. SpiceDBClient sync with SSL
        with patch("app.core.spicedb.settings") as mock_settings:
            mock_settings.spicedb_endpoint = "dns:///localhost:443"
            mock_settings.spicedb_preshared_key = "secret"
            mock_settings.spicedb_insecure = False

            with patch("grpcutil.bearer_token_credentials") as mock_creds:
                client = spicedb_module.SpiceDBClient()
                client.get_client()
                mock_creds.assert_called_once()

    # 3. get_async_spicedb_channel insecure
    with patch("app.core.spicedb.settings") as mock_settings:
        mock_settings.spicedb_endpoint = "localhost:50051"
        mock_settings.spicedb_preshared_key = "secret"

        mock_channel = AsyncMock()
        mock_channel.close = AsyncMock()
        with (
            patch("grpc.aio.insecure_channel", return_value=mock_channel),
            patch("grpc.aio.secure_channel", return_value=mock_channel),
            patch("grpcutil.bearer_token_credentials", return_value=None),
        ):
            gen = spicedb_module.get_async_spicedb_channel()
            chan = await gen.__anext__()
            assert chan == mock_channel
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

            # Close it
            await spicedb_module.close_global_spicedb_channel()
            mock_channel.close.assert_called_once()
            assert spicedb_module._global_channel is None

            # Clear singleton lru_cache to avoid contaminating other tests
            spicedb_module.get_spicedb_client.cache_clear()
