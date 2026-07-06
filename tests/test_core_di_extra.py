from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.di.auth import AuthProvider
from app.core.di.chat import ChatProvider
from app.core.di.content import ContentProvider
from app.core.di.cqrs import CQRSProvider
from app.core.di.infrastructure import InfrastructureProvider
from app.core.di.search import SearchProvider
from app.core.di.spicedb import SpiceDBProvider
from app.core.di.users import UserProvider


def test_providers_initialization():
    """Test that all providers can be instantiated."""
    assert InfrastructureProvider()
    assert AuthProvider()
    assert CQRSProvider()
    assert ChatProvider()
    assert ContentProvider()
    assert SearchProvider()
    assert SpiceDBProvider()
    assert UserProvider()


@pytest.mark.asyncio
async def test_auth_provider_dependencies():
    """Test AuthProvider methods directly."""
    provider = AuthProvider()

    mock_db = AsyncMock()
    repo = provider.auth_repository(db=mock_db)
    assert repo is not None

    mock_audit = MagicMock()
    mock_uow = MagicMock()
    service = provider.auth_service(audit=mock_audit, uow=mock_uow)
    assert service is not None


@pytest.mark.asyncio
async def test_cqrs_provider_dependencies():
    """Test CQRSProvider methods directly."""
    provider = CQRSProvider()

    mock_db = AsyncMock()
    mock_cache = AsyncMock()
    handler = provider.get_schedule_handler(db=mock_db, cache=mock_cache)
    assert handler is not None

    mock_container = AsyncMock()
    bus = provider.query_bus(container=mock_container)
    assert bus is not None

    mock_analytics = AsyncMock()
    mock_service = AsyncMock()

    stats_handler = provider.get_stats_handler(
        db=mock_db, cache=mock_cache, analytics_service=mock_analytics
    )
    assert stats_handler is not None

    c_bus = provider.command_bus(container=mock_container)
    assert c_bus is not None

    assert (
        provider.create_schedule_handler(service=mock_service, cache=mock_cache)
        is not None
    )
    assert (
        provider.update_schedule_handler(service=mock_service, cache=mock_cache)
        is not None
    )
    assert (
        provider.delete_schedule_handler(service=mock_service, cache=mock_cache)
        is not None
    )


@pytest.mark.asyncio
async def test_search_provider():
    """Test SearchProvider search_service generator with different setting configurations."""
    from unittest.mock import patch

    provider = SearchProvider()

    # Case 1: Elasticsearch password set
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.elasticsearch_url = "http://localhost:9200"
        mock_settings.elasticsearch_user = "elastic"
        mock_settings.elasticsearch_password = "password"  # pragma: allowlist secret

        gen = provider.search_service()
        async for svc in gen:
            assert svc is not None

    # Case 2: Elasticsearch password empty
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.elasticsearch_url = "http://localhost:9200"
        mock_settings.elasticsearch_user = "elastic"
        mock_settings.elasticsearch_password = ""

        gen = provider.search_service()
        async for svc in gen:
            assert svc is not None


@pytest.mark.asyncio
async def test_content_provider():
    """Test ContentProvider methods."""
    provider = ContentProvider()
    mock_db = AsyncMock()
    mock_uow = MagicMock()
    mock_vector = AsyncMock()

    assert provider.notification_service(db=mock_db) is not None
    assert provider.vector_service(db=mock_db) is not None
    assert provider.group_service(db=mock_db) is not None
    assert provider.event_service(uow=mock_uow, vector=mock_vector) is not None
    assert provider.story_service(uow=mock_uow) is not None
    assert provider.news_service(uow=mock_uow, vector=mock_vector) is not None
    assert provider.schedule_service(uow=mock_uow) is not None
    assert provider.user_analytics_service(db=mock_db) is not None


@pytest.mark.asyncio
async def test_chat_provider():
    """Test ChatProvider methods."""
    provider = ChatProvider()
    mock_db = AsyncMock()
    mock_cache = AsyncMock()
    mock_uow = MagicMock()
    mock_attachments = AsyncMock()
    mock_notifications = AsyncMock()

    assert provider.chat_repository(db=mock_db) is not None
    assert provider.chat_attachment_service() is not None
    assert provider.chat_ws_notification_service(db=mock_db) is not None
    assert provider.chat_query_service(uow=mock_uow) is not None
    assert (
        provider.chat_message_dispatcher(
            uow=mock_uow, attachments=mock_attachments, notifications=mock_notifications
        )
        is not None
    )
    assert (
        provider.chat_maintenance_service(uow=mock_uow, attachments=mock_attachments)
        is not None
    )
    assert (
        provider.chat_creation_service(uow=mock_uow, db=mock_db, cache=mock_cache)
        is not None
    )


@pytest.mark.asyncio
async def test_infrastructure_provider():
    """Test InfrastructureProvider methods, including generator and conditional logic."""
    from unittest.mock import patch

    provider = InfrastructureProvider()

    # Simple factory & singleton providers
    assert provider._session_factory() is not None
    assert provider.outbox_worker() is not None
    assert provider.cache() is not None
    assert provider.audit_service() is not None
    assert provider.secure_audit_service() is not None
    assert provider.suspicious_activity_detector() is not None
    assert provider.redis_session_service() is not None

    # Geolocation and session backend
    with patch(
        "app.services.geolocation.get_geolocation_service_instance",
        new_callable=AsyncMock,
    ) as mock_geo:
        mock_geo.return_value = AsyncMock()
        assert await provider.geolocation_service() is not None

    with patch(
        "app.auth.redis_session.get_session_backend", new_callable=AsyncMock
    ) as mock_backend:
        mock_backend.return_value = AsyncMock()
        assert await provider.session_backend() is not None

    # db connection generator
    mock_session_factory = MagicMock()
    mock_session = AsyncMock()
    # Mocking async context manager
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    db_gen = provider.db(session_factory=mock_session_factory)
    async for s in db_gen:
        assert s is mock_session

    # fraud detection service generator
    with (
        patch("app.core.config.settings") as mock_settings,
        patch("app.core.di.infrastructure.aioredis.from_url") as mock_from_url,
    ):
        mock_settings.cache_redis_url = "redis://localhost:6379"
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        fraud_gen = provider.fraud_detection_service()
        async for svc in fraud_gen:
            assert svc is not None
        mock_client.close.assert_called_once()

    # NATS broker generator - testing environment
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.environment = "testing"
        nats_gen = provider.nats_broker()
        async for broker in nats_gen:
            assert broker is not None

    # NATS broker generator - non-testing environment, connection success
    with (
        patch("app.core.config.settings") as mock_settings,
        patch(
            "app.core.nats_broker.broker.connect", new_callable=AsyncMock
        ) as mock_connect,
        patch(
            "app.core.nats_broker.broker.close", new_callable=AsyncMock
        ) as mock_close,
    ):
        mock_settings.environment = "production"
        nats_gen = provider.nats_broker()
        async for broker in nats_gen:
            assert broker is not None
        mock_connect.assert_called_once()
        mock_close.assert_called_once()

    # NATS broker generator - non-testing environment, connection failure (except branch)
    with (
        patch("app.core.config.settings") as mock_settings,
        patch(
            "app.core.nats_broker.broker.connect",
            side_effect=ConnectionError("NATS disconnected"),
        ) as mock_connect,
        patch(
            "app.core.nats_broker.broker.close", new_callable=AsyncMock
        ) as mock_close,
    ):
        mock_settings.environment = "production"
        nats_gen = provider.nats_broker()
        async for broker in nats_gen:
            assert broker is not None
        mock_connect.assert_called_once()
        mock_close.assert_called_once()
