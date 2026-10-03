"""Cursor-based pagination utilities for API endpoints."""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass


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
    except (ValueError, TypeError, UnicodeDecodeError):
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
        if not secondary_id:
            return None
        timestamp_us = int(timestamp_str)
        # Use integer math to reconstruct datetime perfectly
        dt = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=timestamp_us)
        return dt, secondary_id
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def encode_ranked_datetime_cursor(
    dt: datetime, secondary_id: str, score: float | None
) -> str:
    """Encode every sort key; retain explicit null scores for semantic search."""
    if score is not None and not math.isfinite(score):
        raise ValueError("Ranked cursor score must be finite")
    score_text = "null" if score is None else repr(score)
    return f"r1:{score_text}:{encode_datetime_cursor(dt, secondary_id)}"


def decode_ranked_datetime_cursor(
    cursor: str | None,
) -> tuple[datetime, str, float | None] | None:
    if not cursor or not cursor.startswith("r1:"):
        return None
    try:
        _, score_text, datetime_cursor = cursor.split(":", 2)
        score = None if score_text == "null" else float(score_text)
        if score is not None and not math.isfinite(score):
            return None
        decoded = decode_datetime_cursor(datetime_cursor)
        if decoded is not None:
            return decoded[0], decoded[1], score
    except (ValueError, TypeError):
        pass
    return None


class PaginatedResponse[T](BaseModel):
    """Standard paginated response schema."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    total_count: int | None = None

    model_config = ConfigDict(from_attributes=True)
