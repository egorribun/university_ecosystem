"""DataLoaders for efficient batch loading and N+1 prevention.

DataLoaders batch multiple individual requests into single database queries,
preventing the N+1 query problem common in GraphQL APIs.

Each DataLoader is instantiated per-request in the GraphQL context to ensure
proper cache isolation between requests.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from strawberry.dataloader import DataLoader

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def load_users_by_ids(
    keys: list[int],
    session: AsyncSession,
) -> Sequence:
    """Batch load users by their IDs."""
    from sqlalchemy import select

    from app.models import User

    result = await session.execute(select(User).where(User.id.in_(keys)))
    users = {user.id: user for user in result.scalars().all()}
    return [users.get(key) for key in keys]


async def load_news_by_ids(
    keys: list[str],
    session: AsyncSession,
) -> Sequence:
    """Batch load news articles by their IDs."""
    from sqlalchemy import select

    from app.models import News

    result = await session.execute(select(News).where(News.id.in_(keys)))
    news_map = {news.id: news for news in result.scalars().all()}
    return [news_map.get(key) for key in keys]


async def load_events_by_ids(
    keys: list[str],
    session: AsyncSession,
) -> Sequence:
    """Batch load events by their IDs."""
    from sqlalchemy import select

    from app.models import Event

    result = await session.execute(select(Event).where(Event.id.in_(keys)))
    events_map = {event.id: event for event in result.scalars().all()}
    return [events_map.get(key) for key in keys]


class DataLoaderRegistry:
    """Registry of DataLoaders for a single request context.

    Create a new instance for each GraphQL request to ensure
    cache isolation between requests.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users: DataLoader[int, object] | None = None
        self._news: DataLoader[str, object] | None = None
        self._events: DataLoader[str, object] | None = None

    @property
    def users(self) -> DataLoader[int, object]:
        if self._users is None:
            self._users = DataLoader(
                load_fn=lambda keys: load_users_by_ids(keys, self._session)
            )
        return self._users

    @property
    def news(self) -> DataLoader[str, object]:
        if self._news is None:
            self._news = DataLoader(
                load_fn=lambda keys: load_news_by_ids(keys, self._session)
            )
        return self._news

    @property
    def events(self) -> DataLoader[str, object]:
        if self._events is None:
            self._events = DataLoader(
                load_fn=lambda keys: load_events_by_ids(keys, self._session)
            )
        return self._events
