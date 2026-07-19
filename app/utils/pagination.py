"""Cursor-based pagination utilities for API endpoints."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from sqlalchemy import Select

    from app.core.protocols import AsyncDatabaseSession as AsyncSession


class CursorParams(BaseModel):
    """Pagination parameters for cursor-based pagination."""

    cursor: str | None = Field(
        default=None,
        description="Opaque cursor for fetching next page",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page (max 100)",
    )


@dataclass
class CursorPage[T]:
    """A page of results with cursor-based pagination."""

    items: list[T]
    next_cursor: str | None
    has_more: bool
    total_count: int | None = None


def encode_cursor(value: int | str) -> str:
    """Encode a cursor value (typically an ID or timestamp) to opaque string."""
    return base64.urlsafe_b64encode(str(value).encode()).decode()


def decode_cursor(cursor: str) -> str:
    """Decode an opaque cursor string back to the original value."""
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except ValueError, TypeError, UnicodeDecodeError:
        return ""


def encode_datetime_cursor(dt: datetime, secondary_id: str | int) -> str:
    """Encode a composite cursor from datetime and secondary ID.

    Used for cursor-based pagination where tie-breaking is needed for
    items with identical timestamps.

    Args:
        dt: The datetime component (must be timezone-aware for precision)
        secondary_id: Secondary sort key (typically record ID)

    Returns:
        Opaque cursor string in format "timestamp_ms:id"
    """
    dt_aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    timestamp_us = int(
        (dt_aware - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(microseconds=1)
    )
    return f"{timestamp_us}:{secondary_id}"


def decode_datetime_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    """Decode a composite cursor into datetime and secondary ID.

    Args:
        cursor: Previously encoded cursor string, or None

    Returns:
        Tuple of (datetime, secondary_id) or None if cursor is invalid
    """
    if not cursor:
        return None
    try:
        timestamp_str, secondary_id = cursor.split(":", 1)
        timestamp_us = int(timestamp_str)
        # Use integer math to reconstruct datetime perfectly
        dt = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=timestamp_us)
        return dt, secondary_id
    except ValueError, TypeError, OverflowError, OSError:
        return None


async def paginate_cursor[T](
    session: AsyncSession,
    stmt: Select[Any],
    cursor_column: Any,
    params: CursorParams,
    descending: bool = True,
    include_total: bool = False,
) -> CursorPage[T]:
    """
    Execute cursor-based pagination on a SQLAlchemy select statement.

    Args:
        session: Database session
        stmt: Base select statement (without limit/offset)
        cursor_column: Column to use for cursor (typically id or created_at)
        params: Pagination parameters
        descending: If True, order descending (newest first)
        include_total: If True, run count query for total

    Returns:
        CursorPage with items, next_cursor, and has_more flag
    """
    from sqlalchemy import func, select

    total_count: int | None = None
    if include_total:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await session.execute(count_stmt)
        total_count = count_result.scalar() or 0

    # Apply cursor filter if provided
    if params.cursor:
        cursor_value = decode_cursor(params.cursor)
        if cursor_value:
            import uuid

            try:
                # Try to cast to UUID if it looks like one, needed for SQLAlchemy 2.0+
                # with sqlite/pgvector when the column is typed as UUID
                target_value = (
                    uuid.UUID(cursor_value) if len(cursor_value) >= 32 else cursor_value
                )
            except ValueError, TypeError:
                target_value = cursor_value

            if descending:
                stmt = stmt.where(cursor_column < target_value)
            else:
                stmt = stmt.where(cursor_column > target_value)

    # Apply ordering
    if descending:
        stmt = stmt.order_by(cursor_column.desc())
    else:
        stmt = stmt.order_by(cursor_column.asc())

    # Fetch one extra to check for more
    stmt = stmt.limit(params.limit + 1)

    result = await session.scalars(stmt)
    items = list(result.all())

    has_more = len(items) > params.limit
    if has_more:
        items = items[: params.limit]

    next_cursor: str | None = None
    if has_more and items:
        last_item = items[-1]
        last_cursor_value = getattr(last_item, cursor_column.key, None)
        if last_cursor_value is not None:
            next_cursor = encode_cursor(last_cursor_value)

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )


class PaginatedResponse[T](BaseModel):
    """Standard paginated response schema."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    total_count: int | None = None

    model_config = ConfigDict(from_attributes=True)
