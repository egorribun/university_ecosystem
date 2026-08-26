from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.active_session_repository import ActiveSessionRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.event_repository import EventRepository
from app.repositories.news_repository import NewsRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.schedule_repository import GroupRepository, ScheduleRepository
from app.repositories.story_repository import StoryRepository
from app.repositories.unit_of_work import UnitOfWork, get_unit_of_work, uow_from_session
from app.repositories.user_repository import UserRepository


@pytest.mark.asyncio
async def test_uow_init():
    """Test UnitOfWork initialization."""
    session_factory = MagicMock()
    uow = UnitOfWork(session_factory)
    assert uow._session_factory == session_factory
    assert uow._session is None


@pytest.mark.asyncio
async def test_uow_aenter_aexit():
    """Test async context management."""
    mock_session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock(return_value=mock_session)

    async with UnitOfWork(session_factory) as uow:
        assert uow._session == mock_session
        assert isinstance(uow.users, UserRepository)
        assert isinstance(uow.events, EventRepository)
        assert isinstance(uow.notifications, NotificationRepository)
        assert isinstance(uow.news, NewsRepository)
        assert isinstance(uow.stories, StoryRepository)
        assert isinstance(uow.sessions, ActiveSessionRepository)
        assert isinstance(uow.auth, AuthRepository)
        assert isinstance(uow.chats, ChatRepository)
        assert isinstance(uow.schedules, ScheduleRepository)
        assert isinstance(uow.groups, GroupRepository)

        # Verify all repositories use the same session
        assert uow.users.db == mock_session
        assert uow.events.db == mock_session
        assert uow.notifications.db == mock_session
        assert uow.news.db == mock_session
        assert uow.stories.db == mock_session
        assert uow.sessions.db == mock_session
        assert uow.auth.db == mock_session
        assert uow.chats.db == mock_session
        assert uow.schedules.db == mock_session
        assert uow.groups.db == mock_session

    mock_session.close.assert_awaited_once()
    assert uow._session is None


@pytest.mark.asyncio
async def test_uow_commit():
    """Test commit functionality."""
    mock_session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock(return_value=mock_session)

    async with UnitOfWork(session_factory) as uow:
        await uow.commit()
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_rollback():
    """Test manual rollback functionality."""
    mock_session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock(return_value=mock_session)

    async with UnitOfWork(session_factory) as uow:
        await uow.rollback()
        mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_flush():
    """Test flush functionality."""
    mock_session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock(return_value=mock_session)

    async with UnitOfWork(session_factory) as uow:
        await uow.flush()
        mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_rollback_on_exception():
    """Test automatic rollback on exception."""
    mock_session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock(return_value=mock_session)

    with pytest.raises(ValueError, match="Test error"):
        async with UnitOfWork(session_factory):
            raise ValueError("Test error")

    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_session_property():
    """Test session property access."""
    mock_session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock(return_value=mock_session)

    uow = UnitOfWork(session_factory)
    with pytest.raises(RuntimeError, match="UnitOfWork not initialized"):
        _ = uow.session

    async with uow:
        assert uow.session == mock_session


@pytest.mark.asyncio
async def test_get_unit_of_work():
    """Test factory function."""
    session_factory = MagicMock()
    uow = get_unit_of_work(session_factory)
    assert isinstance(uow, UnitOfWork)
    assert uow._session_factory == session_factory


@pytest.mark.asyncio
async def test_uow_no_session_ops():
    """Test operations when session is not initialized."""
    session_factory = MagicMock()
    uow = UnitOfWork(session_factory)

    # These should not raise exceptions if session is None (guarded by if self._session)
    await uow.commit()
    await uow.rollback()
    await uow.flush()
    await uow._close()


@pytest.mark.asyncio
async def test_borrowed_session_is_not_closed_on_context_exit():
    """A request-scoped session remains owned by its dependency provider."""
    mock_session = AsyncMock(spec=AsyncSession)
    uow = uow_from_session(mock_session)

    async with uow as entered:
        assert entered.session is mock_session
        assert entered.users.db is mock_session

    mock_session.close.assert_not_awaited()
    assert uow.session is mock_session
    assert uow.users.db is mock_session


@pytest.mark.asyncio
async def test_borrowed_session_rolls_back_but_is_not_closed_on_error():
    """A borrowed transaction still rolls back without stealing lifecycle ownership."""
    mock_session = AsyncMock(spec=AsyncSession)
    uow = uow_from_session(mock_session)

    with pytest.raises(ValueError, match="borrowed transaction failed"):
        async with uow:
            raise ValueError("borrowed transaction failed")

    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_not_awaited()
    assert uow.session is mock_session
