import pytest
from unittest.mock import AsyncMock, MagicMock
from dishka import make_async_container, Scope

from app.core.di.infrastructure import InfrastructureProvider
from app.core.di.auth import AuthProvider
from app.core.di.cqrs import CQRSProvider
from app.core.di.chat import ChatProvider
from app.core.di.content import ContentProvider
from app.core.di.search import SearchProvider
from app.core.di.spicedb import SpiceDBProvider
from app.core.di.users import UsersProvider

def test_providers_initialization():
    """Test that all providers can be instantiated."""
    assert InfrastructureProvider()
    assert AuthProvider()
    assert CQRSProvider()
    assert ChatProvider()
    assert ContentProvider()
    assert SearchProvider()
    assert SpiceDBProvider()
    assert UsersProvider()

@pytest.mark.asyncio
async def test_auth_provider_dependencies():
    """Test AuthProvider methods directly."""
    provider = AuthProvider()
    
    mock_db = AsyncMock()
    repo = provider.auth_repository(provider, db=mock_db)
    assert repo is not None

    mock_audit = MagicMock()
    mock_uow = MagicMock()
    service = provider.auth_service(provider, audit=mock_audit, uow=mock_uow)
    assert service is not None

@pytest.mark.asyncio
async def test_cqrs_provider_dependencies():
    """Test CQRSProvider methods directly."""
    provider = CQRSProvider()
    
    mock_db = AsyncMock()
    mock_cache = AsyncMock()
    handler = provider.get_schedule_handler(provider, db=mock_db, cache=mock_cache)
    assert handler is not None

    mock_container = AsyncMock()
    bus = provider.query_bus(provider, container=mock_container)
    assert bus is not None
