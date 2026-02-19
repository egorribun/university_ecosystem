"""
Unit of Work pattern for transactional boundaries.

Provides a single point of commit/rollback for multiple repository operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.repositories.event_repository import EventRepository
from app.repositories.news_repository import NewsRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.story_repository import StoryRepository
from app.repositories.user_repository import UserRepository

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    """
    Unit of Work for managing transactions across multiple repositories.

    Usage:
        async with UnitOfWork(session_factory) as uow:
            user = await uow.users.get(user_id)
            await uow.notifications.create(...)
            await uow.commit()
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        """
        Initialize Unit of Work.

        Args:
            session_factory: Callable that returns an AsyncSession
        """
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> UnitOfWork:
        """Enter async context and initialize repositories."""
        self._session = self._session_factory()

        # Initialize all repositories with the same session
        self.users = UserRepository(self._session)
        self.events = EventRepository(self._session)
        self.notifications = NotificationRepository(self._session)
        self.news = NewsRepository(self._session)
        self.stories = StoryRepository(self._session)
        self.sessions = SessionRepository(self._session)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
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
    def session(self) -> AsyncSession:
        """Get the underlying session (for advanced use cases)."""
        if self._session is None:
            raise RuntimeError("UnitOfWork not initialized. Use 'async with' context.")
        return self._session


def get_unit_of_work(session_factory: Callable[[], AsyncSession]) -> UnitOfWork:
    """Factory function for creating UnitOfWork instances."""
    return UnitOfWork(session_factory)


__all__ = ["UnitOfWork", "get_unit_of_work"]
