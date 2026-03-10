from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.repositories.active_session_repository import ActiveSessionRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.event_repository import EventRepository
from app.repositories.news_repository import NewsRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.schedule_repository import GroupRepository, ScheduleRepository
from app.repositories.story_repository import StoryRepository
from app.repositories.user_repository import UserRepository

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.core.protocols import AsyncDatabaseSession


class UnitOfWork:
    """
    Unit of Work for managing transactions across multiple repositories.

    Usage:
        async with UnitOfWork(session_factory) as uow:
            user = await uow.users.get(user_id)
            await uow.notifications.create(...)
            await uow.commit()
    """

    def __init__(self, session_factory: Callable[[], AsyncDatabaseSession]) -> None:
        """
        Initialize Unit of Work.

        Args:
            session_factory: Callable that returns an AsyncDatabaseSession
        """
        self._session_factory = session_factory
        self._session: AsyncDatabaseSession | None = None

    async def __aenter__(self) -> UnitOfWork:
        """Enter async context and initialize repositories."""
        self._session = self._session_factory()

        # Initialize all repositories with the same session
        self.users = UserRepository(self._session)
        self.auth = AuthRepository(self._session)
        self.chats = ChatRepository(self._session)
        self.events = EventRepository(self._session)
        self.notifications = NotificationRepository(self._session)
        self.news = NewsRepository(self._session)
        self.stories = StoryRepository(self._session)
        self.sessions = ActiveSessionRepository(self._session)
        self.schedules = ScheduleRepository(self._session)
        self.groups = GroupRepository(self._session)

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context, rollback if exception occurred."""
        if exc_type is not None:
            await self.rollback()
        await self._close()

    async def commit(self) -> None:
        """Commit the current transaction."""
        if self._session:
            await self._session.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._session:
            await self._session.rollback()

    async def flush(self) -> None:
        """Flush pending changes without committing."""
        if self._session:
            await self._session.flush()

    async def _close(self) -> None:
        """Close the session."""
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> AsyncDatabaseSession:
        """Get the underlying session (for advanced use cases)."""
        if self._session is None:
            raise RuntimeError("UnitOfWork not initialized. Use 'async with' context.")
        return self._session


def get_unit_of_work(session_factory: Callable[[], AsyncDatabaseSession]) -> UnitOfWork:
    """Factory function for creating UnitOfWork instances."""
    return UnitOfWork(session_factory)


def uow_from_session(session: AsyncDatabaseSession) -> UnitOfWork:
    """Create an eagerly-initialized UnitOfWork from an existing open session.

    Use this when you already have a session (e.g. from FastAPI Depends() or a
    test fixture) and need to pass a UnitOfWork to services that access
    ``uow.users``, ``uow.events``, etc. in their ``__init__``.
    """
    uow = UnitOfWork(lambda: session)
    uow._session = session
    uow.users = UserRepository(session)
    uow.auth = AuthRepository(session)
    uow.chats = ChatRepository(session)
    uow.events = EventRepository(session)
    uow.notifications = NotificationRepository(session)
    uow.news = NewsRepository(session)
    uow.stories = StoryRepository(session)
    uow.sessions = ActiveSessionRepository(session)
    uow.schedules = ScheduleRepository(session)
    uow.groups = GroupRepository(session)
    return uow


__all__ = ["UnitOfWork", "get_unit_of_work", "uow_from_session"]
