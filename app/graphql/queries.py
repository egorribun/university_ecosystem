"""GraphQL Query resolvers for the University Ecosystem API.

This module defines the root Query type with resolvers for fetching
news, events, schedule, and other data.
"""

from __future__ import annotations

from typing import Any

import strawberry
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
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

logger = get_logger(__name__)


def _user_to_type(user: User, show_email: bool = False) -> UserType:
    """Convert ``User`` ORM row to ``UserType`` with PII protection.

    The caller MUST pass ``show_email=True`` only when the requesting actor
    is the user themselves or an admin; otherwise email is masked to
    ``None``. ``profile.full_name`` is read defensively (``getattr`` with a
    default) because ``user.profile`` may be unloaded — every relationship
    on User has ``lazy="noload"`` per project convention.

    Args:
        user: ORM User row. Must have ``profile`` eagerly loaded (via
            ``selectinload(User.profile)``) if a name is desired.
        show_email: When False, ``email`` is dropped from the response.

    Returns:
        ``UserType`` ready for the GraphQL serializer.
    """
    return UserType(
        id=strawberry.ID(str(user.id)),
        email=user.email if show_email else None,
        full_name=user.profile.full_name if getattr(user, "profile", None) else None,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _news_to_type(news: News, author: User | None = None) -> NewsType:
    """Convert ``News`` ORM row to ``NewsType`` with optional author embed.

    ``author`` is a separate parameter (rather than ``news.author``) because
    every News.* relationship has ``lazy="noload"`` per the project
    convention; resolvers must eager-load and pass it explicitly to avoid
    accidental N+1.

    Args:
        news: ORM News row.
        author: Optional pre-loaded ``User`` to embed via ``_user_to_type``.

    Returns:
        ``NewsType`` ready for the GraphQL serializer. The author is always
        rendered with ``show_email=False`` (PII protection by default).
    """
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
    """Convert ``Event`` ORM row to ``EventType`` with optional organizer embed.

    Same eager-loading contract as ``_news_to_type``: every Event.*
    relationship is ``lazy="noload"``, so resolvers must pre-load
    ``organizer`` explicitly. ``ends_at``/``description``/``location``/
    ``image_url``/``max_attendees`` are read defensively because some Event
    rows are imported with sparse metadata.

    Args:
        event: ORM Event row.
        organizer: Optional pre-loaded ``User`` to embed.

    Returns:
        ``EventType`` ready for the GraphQL serializer.
    """
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
    @strawberry.field(description="Get paginated list of news articles")  # type: ignore[misc, untyped-decorator]
    async def news(
        self: Any,
        info: strawberry.Info[GraphQLContext],
        limit: int = 20,
        after: str | None = strawberry.UNSET,
    ) -> NewsConnection:
        """Paginated news using keyset cursor (MOD-03, audit Wave 10).

        ``after`` is an opaque base64-encoded cursor returned in PageInfo.cursor.
        Omit it (or pass null) to get the first page.  Keyset is O(log N) vs
        OFFSET O(N) because Postgres can use the (created_at DESC, id DESC) index
        to seek directly to the starting row.
        """
        limit = min(limit, 200)
        session = info.context.session
        from sqlalchemy import and_, or_

        from app.models import News
        from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor

        # Normalise strawberry.UNSET → None
        cursor_str: str | None = None if after is strawberry.UNSET else after

        # PERF-GQL-02 (audit Wave 10): use direct COUNT(id) with a separate
        # WHERE clause instead of .select_from(subquery()).  The subquery
        # materializes the full result set in a CTE before counting — O(N) at
        # large table sizes.  func.count(News.id) uses the primary key index
        # directly and is O(log N).
        count_stmt = select(func.count(News.id))
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        # PERF-GQL-01 (audit Wave 10): add selectinload(News.author) so all
        # authors are fetched in a single IN query instead of N lazy loads.
        stmt = (
            select(News)
            .options(selectinload(News.author))
            .order_by(News.created_at.desc(), News.id.desc())
        )

        # MOD-03 (audit Wave 10): keyset filter — eliminates O(N) OFFSET scan.
        if cursor_str:
            decoded = decode_datetime_cursor(cursor_str)
            if decoded:
                last_created_at, last_id_str = decoded
                import uuid as _uuid

                try:
                    last_id = _uuid.UUID(last_id_str)
                except ValueError, AttributeError:  # RZ-28-01
                    last_id = None
                if last_id is not None:
                    stmt = stmt.where(
                        or_(
                            News.created_at < last_created_at,
                            and_(
                                News.created_at == last_created_at,
                                News.id < last_id,
                            ),
                        )
                    )

        # Fetch limit+1 to determine has_next_page without a COUNT.
        result = await session.execute(stmt.limit(limit + 1))
        news_rows = result.scalars().all()

        has_next_page = len(news_rows) > limit
        news_list = news_rows[:limit]
        items = [_news_to_type(n, getattr(n, "author", None)) for n in news_list]

        next_cursor: str | None = None
        if has_next_page and news_list:
            last = news_list[-1]
            next_cursor = encode_datetime_cursor(last.created_at, str(last.id))

        return NewsConnection(
            items=items,
            page_info=PageInfo(
                has_next_page=has_next_page,
                has_previous_page=cursor_str is not None,
                total_count=total,
                cursor=next_cursor,
            ),
        )

    @strawberry.field(description="Get a single news article by ID")  # type: ignore[misc, untyped-decorator]
    async def news_by_id(
        self,
        info: strawberry.Info[GraphQLContext],
        id: strawberry.ID,
    ) -> NewsType | None:
        from uuid import UUID

        from app.models import News

        try:
            uid = UUID(str(id))
        except ValueError, TypeError:  # RZ-28-01
            return None

        result = await info.context.session.execute(
            select(News).where(News.id == uid).options(selectinload(News.author))
        )
        news = result.scalar_one_or_none()
        if not news:
            return None
        return _news_to_type(news, getattr(news, "author", None))

    @strawberry.field(description="Get paginated list of events")  # type: ignore[misc, untyped-decorator]
    async def events(
        self: Any,
        info: strawberry.Info[GraphQLContext],
        limit: int = 25,
        after: str | None = strawberry.UNSET,
        active_only: bool = True,
    ) -> EventsConnection:
        """Paginated events using keyset cursor (MOD-03, audit Wave 10).

        ``after`` is an opaque base64-encoded cursor returned in PageInfo.cursor.
        """
        limit = min(limit, 200)
        from sqlalchemy import and_, or_

        from app.models import Event
        from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor

        session = info.context.session
        cursor_str: str | None = None if after is strawberry.UNSET else after

        # Build base filter used for both count and data queries.
        filters = []
        if active_only:
            filters.append(Event.is_active == True)  # noqa: E712

        # PERF-GQL-02 (audit Wave 10): direct COUNT(id) with the same WHERE
        # conditions avoids subquery materialization O(N) → index O(log N).
        count_query = select(func.count(Event.id))
        if filters:
            count_query = count_query.where(*filters)
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        query = select(Event).order_by(Event.starts_at.desc(), Event.id.desc())
        if filters:
            query = query.where(*filters)

        # MOD-03 (audit Wave 10): keyset filter on (starts_at, id).
        if cursor_str:
            decoded = decode_datetime_cursor(cursor_str)
            if decoded:
                last_starts_at, last_id_str = decoded
                import uuid as _uuid

                try:
                    last_id = _uuid.UUID(last_id_str)
                except ValueError, AttributeError:  # RZ-28-01
                    last_id = None
                if last_id is not None:
                    query = query.where(
                        or_(
                            Event.starts_at < last_starts_at,
                            and_(
                                Event.starts_at == last_starts_at,
                                Event.id < last_id,
                            ),
                        )
                    )

        # Fetch limit+1 to determine has_next_page.
        result = await session.execute(query.limit(limit + 1))
        events_rows = result.scalars().all()

        has_next_page = len(events_rows) > limit
        events_list = events_rows[:limit]
        items = [_event_to_type(e) for e in events_list]

        next_cursor: str | None = None
        if has_next_page and events_list:
            last_evt = events_list[-1]
            next_cursor = encode_datetime_cursor(last_evt.starts_at, str(last_evt.id))

        return EventsConnection(
            items=items,
            page_info=PageInfo(
                has_next_page=has_next_page,
                has_previous_page=cursor_str is not None,
                total_count=total,
                cursor=next_cursor,
            ),
        )

    @strawberry.field(description="Get schedule entries for a group")  # type: ignore[misc, untyped-decorator]
    async def schedule(
        self: Any,
        info: strawberry.Info[GraphQLContext],
        group_id: strawberry.ID,
    ) -> list[ScheduleEntryType]:
        from uuid import UUID

        from app.models import Schedule

        try:
            uid = UUID(str(group_id))
        except ValueError, TypeError:  # RZ-28-01
            return []

        # RZ-GQL-AUTH: Enforce ReBAC for group schedules.
        # Only members or staff with "view" permission on the group can see the schedule.
        # Fail-closed: return empty list on permission denial or service failure.
        try:
            checker = info.context.checker
            if checker is None:
                return []
            current_user = info.context.current_user
            user_id = str(current_user.id) if current_user else "anonymous"

            if not await checker.check_permission(
                resource_type="group",
                resource_id=str(uid),
                permission="view",
                user_id=user_id,
            ):
                return []
        except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth — denies access on ReBAC check failure (reviewed TD-27-04)
            # P1: Log auth degradation but don't leak schedule data.
            logger.warning("GraphQL ReBAC check failed for group %s: %s", uid, exc)
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

    @strawberry.field(description="Get current authenticated user")  # type: ignore[misc, untyped-decorator]
    async def me(
        self: Any,
        info: strawberry.Info[GraphQLContext],
    ) -> UserType | None:
        user = info.context.current_user
        if not user:
            return None
        return _user_to_type(user, show_email=True)
