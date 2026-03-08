"""GraphQL Query resolvers for the University Ecosystem API.

This module defines the root Query type with resolvers for fetching
news, events, schedule, and other data.
"""

from __future__ import annotations

from typing import Any

import strawberry
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.graphql.context import GraphQLContext
from app.graphql.types import (
    EventsConnection,
    EventType,
    NewsConnection,
    NewsType,
    PageInfo,
    ScheduleEntryType,
    UserType,
)
from app.models import Event, News, User


def _user_to_type(user: User) -> UserType:
    """Convert SQLAlchemy User model to GraphQL UserType."""
    return UserType(
        id=strawberry.ID(str(user.id)),
        email=user.email,
        full_name=user.profile.full_name if getattr(user, "profile", None) else None,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _news_to_type(news: News, author: User | None = None) -> NewsType:
    """Convert SQLAlchemy News model to GraphQL NewsType."""
    return NewsType(
        id=strawberry.ID(str(news.id)),
        title=news.title,
        content=news.content,
        summary=getattr(news, "summary", None),
        image_url=getattr(news, "image_url", None),
        author=_user_to_type(author) if author else None,
        created_at=news.created_at,
        updated_at=getattr(news, "updated_at", None),
        likes_count=getattr(news, "likes_count", 0),
        comments_count=getattr(news, "comments_count", 0),
    )


def _event_to_type(event: Event, organizer: User | None = None) -> EventType:
    """Convert SQLAlchemy Event model to GraphQL EventType."""
    return EventType(
        id=strawberry.ID(str(event.id)),
        title=event.title,
        description=getattr(event, "description", None),
        location=getattr(event, "location", None),
        start_time=event.starts_at,
        end_time=getattr(event, "ends_at", None),
        is_active=getattr(event, "is_active", True),
        image_url=getattr(event, "image_url", None),
        organizer=_user_to_type(organizer) if organizer else None,
        attendees_count=getattr(event, "attendees_count", 0),
        max_attendees=getattr(event, "max_attendees", None),
        created_at=event.created_at,
    )


@strawberry.type(description="Root Query type for the University Ecosystem API")
class Query:
    @strawberry.field(description="Get paginated list of news articles")  # type: ignore[misc]
    async def news(
        self: Any,
        info: strawberry.Info[GraphQLContext],
        limit: int = 20,
        offset: int = 0,
    ) -> NewsConnection:
        session = info.context.session
        from app.models import News

        stmt = select(News).order_by(News.created_at.desc())

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch news without selectinload (DataLoaders will handle the author)
        result = await session.execute(stmt.offset(offset).limit(limit))
        news_list = result.scalars().all()

        items = [_news_to_type(n) for n in news_list]

        return NewsConnection(
            items=items,
            page_info=PageInfo(
                has_next_page=offset + limit < total,
                has_previous_page=offset > 0,
                total_count=total,
            ),
        )

    @strawberry.field(description="Get a single news article by ID")  # type: ignore[misc]
    async def news_by_id(
        self,
        info: strawberry.Info[GraphQLContext],
        id: strawberry.ID,
    ) -> NewsType | None:
        from uuid import UUID

        from app.models import News

        try:
            uid = UUID(str(id))
        except (ValueError, TypeError):
            return None

        result = await info.context.session.execute(
            select(News).where(News.id == uid).options(selectinload(News.author))
        )
        news = result.scalar_one_or_none()
        if not news:
            return None
        return _news_to_type(news, getattr(news, "author", None))

    @strawberry.field(description="Get paginated list of events")  # type: ignore[misc]
    async def events(
        self: Any,
        info: strawberry.Info[GraphQLContext],
        limit: int = 25,
        offset: int = 0,
        active_only: bool = True,
    ) -> EventsConnection:
        from app.models import Event

        session = info.context.session

        # Build query (removed selectinload to avoid Overfetching)
        query = select(Event)
        if active_only:
            query = query.where(Event.is_active == True)  # noqa: E712

        # Count without subquery materialization
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        # Fetch
        result = await session.execute(
            query.order_by(Event.starts_at.desc()).offset(offset).limit(limit)
        )
        events_list = result.scalars().all()

        items = [_event_to_type(e) for e in events_list]

        return EventsConnection(
            items=items,
            page_info=PageInfo(
                has_next_page=offset + limit < total,
                has_previous_page=offset > 0,
                total_count=total,
            ),
        )

    @strawberry.field(description="Get schedule entries for a group")  # type: ignore[misc]
    async def schedule(
        self: Any,
        info: strawberry.Info[GraphQLContext],
        group_id: strawberry.ID,
    ) -> list[ScheduleEntryType]:
        from uuid import UUID

        from app.models import Schedule

        try:
            uid = UUID(str(group_id))
        except (ValueError, TypeError):
            return []

        result = await info.context.session.execute(
            select(Schedule).where(Schedule.group_id == uid)
        )
        entries = result.scalars().all()

        return [
            ScheduleEntryType(
                id=strawberry.ID(str(e.id)),
                day_of_week=e.weekday,
                time_start=str(e.start_time),
                time_end=str(e.end_time),
                subject=e.subject,
                teacher=getattr(e, "teacher", None),
                room=getattr(e, "room", None),
                type=getattr(e, "lesson_type", None),
            )
            for e in entries
        ]

    @strawberry.field(description="Get current authenticated user")  # type: ignore[misc]
    async def me(
        self: Any,
        info: strawberry.Info[GraphQLContext],
    ) -> UserType | None:
        user = info.context.current_user
        if not user:
            return None
        return _user_to_type(user)
