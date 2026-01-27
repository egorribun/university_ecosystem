"""GraphQL Query resolvers for the University Ecosystem API.

This module defines the root Query type with resolvers for fetching
news, events, schedule, and other data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import strawberry
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.graphql.types import (
    EventsConnection,
    EventType,
    NewsConnection,
    NewsType,
    PageInfo,
    ScheduleEntryType,
    UserType,
)

if TYPE_CHECKING:
    from app.graphql.context import GraphQLContext


def _user_to_type(user) -> UserType:
    """Convert SQLAlchemy User model to GraphQL UserType."""
    return UserType(
        id=strawberry.ID(str(user.id)),
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _news_to_type(news, author=None) -> NewsType:
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


def _event_to_type(event, organizer=None) -> EventType:
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
    @strawberry.field(description="Get paginated list of news articles")
    async def news(
        self,
        info: strawberry.Info[GraphQLContext],
        limit: int = 20,
        offset: int = 0,
    ) -> NewsConnection:
        session = info.context.session

        # Count total
        count_result = await session.execute(
            select(func.count()).select_from(
                select(1)
                .select_from(__import__("app.models", fromlist=["News"]).News)
                .subquery()
            )
        )
        total = count_result.scalar() or 0

        # Fetch news with author
        from app.models import News

        result = await session.execute(
            select(News)
            .options(selectinload(News.author))
            .order_by(News.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        news_list = result.scalars().all()

        items = [_news_to_type(n, getattr(n, "author", None)) for n in news_list]

        return NewsConnection(
            items=items,
            page_info=PageInfo(
                has_next_page=offset + limit < total,
                has_previous_page=offset > 0,
                total_count=total,
            ),
        )

    @strawberry.field(description="Get a single news article by ID")
    async def news_by_id(
        self,
        info: strawberry.Info[GraphQLContext],
        id: strawberry.ID,
    ) -> NewsType | None:
        from app.models import News

        result = await info.context.session.execute(
            select(News).where(News.id == int(id)).options(selectinload(News.author))
        )
        news = result.scalar_one_or_none()
        if not news:
            return None
        return _news_to_type(news, getattr(news, "author", None))

    @strawberry.field(description="Get paginated list of events")
    async def events(
        self,
        info: strawberry.Info[GraphQLContext],
        limit: int = 25,
        offset: int = 0,
        active_only: bool = True,
    ) -> EventsConnection:
        from app.models import Event

        session = info.context.session

        # Build query
        query = select(Event).options(selectinload(Event.organizer))
        if active_only:
            query = query.where(Event.is_active == True)  # noqa: E712

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        # Fetch
        result = await session.execute(
            query.order_by(Event.starts_at.desc()).offset(offset).limit(limit)
        )
        events_list = result.scalars().all()

        items = [_event_to_type(e, getattr(e, "organizer", None)) for e in events_list]

        return EventsConnection(
            items=items,
            page_info=PageInfo(
                has_next_page=offset + limit < total,
                has_previous_page=offset > 0,
                total_count=total,
            ),
        )

    @strawberry.field(description="Get schedule entries for a group")
    async def schedule(
        self,
        info: strawberry.Info[GraphQLContext],
        group_id: int,
    ) -> list[ScheduleEntryType]:
        from app.models import Schedule

        result = await info.context.session.execute(
            select(Schedule).where(Schedule.group_id == group_id)
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

    @strawberry.field(description="Get current authenticated user")
    async def me(
        self,
        info: strawberry.Info[GraphQLContext],
    ) -> UserType | None:
        user = info.context.current_user
        if not user:
            return None
        return _user_to_type(user)
