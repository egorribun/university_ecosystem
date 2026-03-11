"""Cursor-based (keyset) pagination primitives.

Usage::

    # In a repository method:
    from app.repositories.pagination import Page, CursorParams, apply_cursor

    async def list_users(self, params: CursorParams) -> Page[User]:
        stmt = select(User).order_by(User.id)
        stmt = apply_cursor(stmt, User.id, params)
        rows = (await self._session.scalars(stmt)).all()
        return Page.from_rows(rows, params.limit)

    # In a router:
    @router.get("/users", response_model=Page[UserResponse])
    async def list_users(params: CursorParams = Depends()):
        ...

Design notes:
- Keyset pagination scales to arbitrarily deep pages in O(log N) time because
  the database uses the primary-key index directly rather than scanning skipped rows.
- The cursor is an opaque base64url-encoded string so the implementation detail
  (which column is used) is hidden from the API consumer.
- ``Page.next_cursor`` is None when there are no more rows, allowing clients to
  detect the last page without a separate COUNT query.
"""
from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, Select

if TYPE_CHECKING:
    from collections.abc import Sequence

T = TypeVar("T")

# Maximum rows a single page may contain — protects against accidental large scans.
_MAX_LIMIT: int = 200
_DEFAULT_LIMIT: int = 20


# ---------------------------------------------------------------------------
# Cursor encoding helpers
# ---------------------------------------------------------------------------


def encode_cursor(value: uuid.UUID | int | str) -> str:
    """Encode a sort-key value as an opaque URL-safe base64 cursor string."""
    raw = str(value).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor_as_uuid(cursor: str) -> uuid.UUID:
    """Decode a cursor string back to a UUID, raising ValueError on bad input."""
    padding = 4 - len(cursor) % 4
    raw = base64.urlsafe_b64decode(cursor + "=" * (padding % 4))
    return uuid.UUID(raw.decode())


def decode_cursor_as_int(cursor: str) -> int:
    """Decode a cursor string back to an integer, raising ValueError on bad input."""
    padding = 4 - len(cursor) % 4
    raw = base64.urlsafe_b64decode(cursor + "=" * (padding % 4))
    return int(raw.decode())


# ---------------------------------------------------------------------------
# CursorParams — FastAPI Depends()-compatible query parameter model
# ---------------------------------------------------------------------------


@dataclass
class CursorParams:
    """Query parameters for cursor-based pagination.

    Use as a FastAPI dependency::

        @router.get("/items")
        async def list_items(params: CursorParams = Depends()):
            ...
    """

    limit: int = Query(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=_MAX_LIMIT,
        description="Maximum number of items to return (1–200).",
    )
    after: str | None = Query(
        default=None,
        description=(
            "Opaque cursor returned by the previous page's ``next_cursor`` field. "
            "Omit to start from the beginning."
        ),
    )

    @property
    def after_uuid(self) -> uuid.UUID | None:
        """Decode ``after`` as a UUID cursor, or None if not provided."""
        if self.after is None:
            return None
        return decode_cursor_as_uuid(self.after)

    @property
    def after_int(self) -> int | None:
        """Decode ``after`` as an integer cursor, or None if not provided."""
        if self.after is None:
            return None
        return decode_cursor_as_int(self.after)


# ---------------------------------------------------------------------------
# SQLAlchemy helpers
# ---------------------------------------------------------------------------


def apply_cursor(
    stmt: Select,
    column: Column,
    params: CursorParams,
) -> Select:
    """Apply keyset pagination clauses to *stmt*.

    Assumes *stmt* already has an ``ORDER BY column`` clause (ascending).
    Fetches ``params.limit + 1`` rows so the caller can detect whether a next
    page exists (see ``Page.from_rows``).
    """
    if params.after is not None:
        try:
            # Try UUID first, fall back to integer for non-UUID primary keys.
            try:
                cursor_val = decode_cursor_as_uuid(params.after)
            except (ValueError, AttributeError):
                cursor_val = decode_cursor_as_int(params.after)  # type: ignore[assignment]
            stmt = stmt.where(column > cursor_val)
        except (ValueError, AttributeError):
            pass  # Malformed cursor — treat as first page to avoid 500 errors.
    return stmt.limit(params.limit + 1)


# ---------------------------------------------------------------------------
# Page[T] — generic paginated response envelope
# ---------------------------------------------------------------------------


class Page(BaseModel, Generic[T]):
    """A single page of results with a cursor for the next page.

    ``items`` contains at most ``limit`` elements.
    ``next_cursor`` is ``None`` when this is the last page.
    ``has_more`` mirrors ``next_cursor is not None`` for convenience.
    """

    items: list[T]
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Pass this value as ``after`` to retrieve the next page. "
            "``null`` means there are no more results."
        ),
    )
    has_more: bool = Field(
        default=False,
        description="True when more results are available beyond this page.",
    )

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_rows(
        cls,
        rows: Sequence[T],
        limit: int,
        *,
        cursor_fn: None = None,  # kept for API compat — cursor comes from last row's id
    ) -> Page[T]:
        """Build a ``Page`` from a raw row sequence.

        Pass ``limit + 1`` rows (as returned by :func:`apply_cursor`) so the method
        can detect whether a next page exists without a COUNT query.

        The ``next_cursor`` is derived from the last visible row's ``id`` attribute.
        If your sort key is not ``id``, encode it yourself and set ``page.next_cursor``
        directly.
        """
        has_more = len(rows) > limit
        visible = list(rows[:limit])
        next_cursor: str | None = None
        if has_more and visible:
            last = visible[-1]
            row_id = getattr(last, "id", None)
            if row_id is not None:
                next_cursor = encode_cursor(row_id)
        return cls(items=visible, next_cursor=next_cursor, has_more=has_more)

    @classmethod
    def empty(cls) -> Page[T]:
        """Return an empty page (no results, no next cursor)."""
        return cls(items=[], next_cursor=None, has_more=False)


__all__ = [
    "CursorParams",
    "Page",
    "apply_cursor",
    "decode_cursor_as_int",
    "decode_cursor_as_uuid",
    "encode_cursor",
]
