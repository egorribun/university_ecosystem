from __future__ import annotations

import abc
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession, Identifiable

from pydantic import BaseModel
from sqlalchemy import delete, exists, func, select

from app.core.database import Base

# TD-W9-04: Explicit UUID format validation — replaces the fragile `len >= 32`
# magic-number check that silently passed invalid strings to SQLAlchemy.
# Accepts both canonical form (8-4-4-4-12 with dashes) and 32-char hex (no dashes).
_UUID_WITH_DASHES_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


class ReadOnlyRepository[T: Base, DTOT: BaseModel](abc.ABC):
    def __init__(self, db: AsyncDatabaseSession):
        self.db = db

    def add(self, obj: Any) -> None:
        """Add an object to the current session."""
        self.db.add(obj)

    @property
    @abc.abstractmethod
    def model(self) -> type[T]: ...  # pragma: no branch

    @property
    @abc.abstractmethod
    def dto_class(self) -> type[DTOT]: ...  # pragma: no branch

    def _to_dto(self, obj: T) -> DTOT:
        """Convert an ORM row to its concrete DTO via Pydantic ``model_validate``.

        Subclasses do not need to override this — the DTO class is supplied
        through the ``dto_class`` abstract property and ``from_attributes=True``
        is expected on every DTO that backs a repository.
        """
        return self.dto_class.model_validate(obj)

    async def _get_orm(self, id: Any, *, with_for_update: bool = False) -> T | None:
        """Fetch a single ORM row by ``id`` (or None when missing).

        ``id`` is cast through ``_cast_id`` so callers may pass canonical UUIDs,
        32-char hex UUIDs, or raw integer PKs. Set ``with_for_update=True`` to
        acquire a row-level lock — use sparingly; the implicit SELECT FOR UPDATE
        on every read was removed for performance (avoids lock escalation).
        """
        target_id = self._cast_id(id)
        stmt = select(self.model).where(
            cast("type[Identifiable]", self.model).id == target_id
        )
        if with_for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get(self, id: Any, *, with_for_update: bool = False) -> DTOT | None:
        obj = await self._get_orm(id, with_for_update=with_for_update)
        return self._to_dto(obj) if obj else None

    async def get_orm_for_update(self, id: Any) -> T | None:
        """Get the ORM object with a row-level lock for safe mutation.

        TD-20-04 (audit 2026-03-24): Public interface for services that need to
        mutate the ORM object directly (e.g. profile updates, media uploads).
        Replaces direct calls to the private ``_get_orm(with_for_update=True)``
        which leaked the repository's internal API into the service layer.
        """
        return await self._get_orm(id, with_for_update=True)

    async def get_or_raise(self, id: Any, *, with_for_update: bool = False) -> DTOT:
        # LOW-W19: do not leak model name or id value into exception message —
        # both are internal details that must not reach API error responses.
        dto = await self.get(id, with_for_update=with_for_update)
        if dto is None:
            raise ValueError("Resource not found")
        return dto

    async def get_by_ids(
        self, ids: list[Any], *, with_for_update: bool = False
    ) -> Sequence[DTOT]:
        if not ids:
            return []
        target_ids = [self._cast_id(idx) for idx in ids]
        stmt = select(self.model).where(
            cast("type[Identifiable]", self.model).id.in_(target_ids)
        )
        if with_for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    # TD-14-02 (audit 2026-03-23): Defence-in-depth cap — the ORM layer must
    # not trust its callers.  An internal service call with limit=99999 returns
    # a multi-MB payload and exhausts the connection pool.  Consistent with
    # _MAX_LIMIT=200 in pagination.py and _MAX_PAGE_SIZE in user_repository.py.
    _LIST_MAX_LIMIT: int = 200

    # LOW-W19: OFFSET pagination is O(N) on the database; prefer list_after()
    # which uses keyset (cursor) pagination for O(log N) performance.
    async def list(
        self, *, skip: int = 0, limit: int = 100, order_by: Any = None
    ) -> Sequence[DTOT]:
        capped = min(limit, self._LIST_MAX_LIMIT)
        stmt = select(self.model).offset(skip).limit(capped)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await self.db.execute(stmt)
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def list_after(
        self,
        *,
        after_id: Any = None,
        limit: int = 50,
        order_column: Any = None,
        extra_filters: Sequence[Any] | None = None,
    ) -> Sequence[DTOT]:
        """Keyset pagination — O(log N) vs O(N) for OFFSET-based paging.

        PERF-W9-03: Returns up to *limit* rows ordered by *order_column* (defaults
        to ``model.id``).  When *after_id* is provided the query adds a WHERE clause
        ``order_column > <value of order_column for after_id>`` so that the result
        set starts immediately after the given row, skipping no rows in the process.

        Design notes:
        - The cursor value is resolved with a correlated scalar subquery so the
          caller only needs to pass the opaque ``after_id`` (typically the last
          ``id`` from the previous page) rather than decoding a cursor string.
        - ``extra_filters`` accepts additional SQLAlchemy column expressions so
          callers can add tenant/user filters without subclassing.
        - Requires an index on ``order_column`` (or a composite index that starts
          with ``order_column``) for the O(log N) guarantee.
        """
        col = (
            order_column
            if order_column is not None
            else cast("type[Identifiable]", self.model).id
        )
        stmt = select(self.model).order_by(col.asc()).limit(limit)
        if extra_filters:
            for f in extra_filters:
                stmt = stmt.where(f)
        if after_id is not None:
            # PERF-W10-03: Resolve cursor value in a separate scalar query
            # so the planner sees a literal parameter in the main WHERE clause
            # instead of a correlated subquery.  Correlated subqueries can
            # prevent index-only scans on composite indexes; a literal value
            # is always sargable and allows the optimizer to use the full range.
            cursor_val = await self.db.scalar(
                select(col).where(
                    cast("type[Identifiable]", self.model).id == self._cast_id(after_id)
                )
            )
            if cursor_val is None:
                # Cursor row not found: caller passed a deleted/invalid after_id.
                # Return empty rather than full first page to avoid surprising callers.
                return []
            stmt = stmt.where(col > cursor_val)
        result = await self.db.execute(stmt)
        return [self._to_dto(obj) for obj in result.scalars()]

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def exists(self, id: Any) -> bool:
        # PERF-W19-05: use EXISTS instead of COUNT(*) — short-circuits at first row
        target_id = self._cast_id(id)
        stmt = select(
            exists().where(cast("type[Identifiable]", self.model).id == target_id)
        )
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    def _cast_id(self, id_val: Any) -> uuid.UUID | Any:
        """Cast a string ID to UUID, raising ValueError on unrecognised formats.

        TD-W9-04: The previous ``len >= 32`` check silently returned invalid
        strings (e.g. a 33-char opaque token) as-is, deferring the error to
        deep inside asyncpg with a cryptic DataError.  Explicit regex validation
        raises a clean ValueError at the repository boundary instead.

        Accepts:
          - Already a ``uuid.UUID`` — returned unchanged.
          - Canonical form: ``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx``
          - Hex form (no dashes): ``xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx``
          - Any non-string — returned unchanged (e.g. integer PKs).
        """
        if isinstance(id_val, uuid.UUID):
            return id_val
        if isinstance(id_val, str):
            if _UUID_WITH_DASHES_RE.match(id_val) or _UUID_HEX_RE.match(id_val):
                return uuid.UUID(id_val)
            raise ValueError(f"Invalid UUID format: {id_val!r}")
        return id_val

    @staticmethod
    def _escape_like(value: str, escape_char: str = "\\") -> str:
        """Escape SQL LIKE wildcards to prevent pattern injection.

        CRIT-01/05 (audit 2026-03-11): Unescaped user input in LIKE patterns
        allows two attacks:
        1. DoS — ``%`` or ``_`` turns a selective query into a full-table scan.
        2. Data disclosure — crafted patterns can enumerate rows by exploiting
           `_` (single-char wildcard) to brute-force column values.

        Must be paired with ``.like(pattern, escape=escape_char)`` or
        ``.ilike(pattern, escape=escape_char)`` in the calling query.

        Example::

            safe = self._escape_like(user_input)
            stmt = stmt.where(Column.ilike(f"%{safe}%", escape="\\"))  # LOW-W19: single backslash
        """
        # Order matters: escape the escape character first
        for ch in (escape_char, "%", "_"):
            value = value.replace(ch, f"{escape_char}{ch}")
        return value


class BaseRepository[T: Base, DTOT: BaseModel, CreateT, UpdateT](
    ReadOnlyRepository[T, DTOT]
):
    async def create(self, obj_in: CreateT | dict[str, Any]) -> DTOT:
        if hasattr(obj_in, "model_dump"):
            obj_data = obj_in.model_dump()
        else:
            obj_data = obj_in

        db_obj = self.model(**obj_data)
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return self._to_dto(db_obj)

    async def update(self, id: Any, obj_in: UpdateT | dict[str, Any]) -> DTOT | None:
        # TD-02 (audit 2026-03-04): Removed the SELECT FOR UPDATE that preceded
        # every update. Acquiring a row-level lock on every mutation caused lock
        # escalation under concurrent load and added a latency-doubling round-trip
        # even for callers that did not need serialised access.
        # setattr is retained because it correctly fires ORM column descriptors,
        # TypeDecorator processors, and SQLAlchemy attribute events. Callers that
        # genuinely need a pessimistic lock should pass with_for_update=True to
        # _get_orm() themselves.
        db_obj = await self._get_orm(id)
        if db_obj is None:
            return None

        if hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = obj_in

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        await self.db.flush()
        return self._to_dto(db_obj)

    async def delete(self, id: Any) -> bool:
        target_id = self._cast_id(id)
        stmt = delete(self.model).where(self.model.id == target_id)  # type: ignore[attr-defined]
        result = await self.db.execute(stmt)
        return (result.rowcount or 0) > 0  # type: ignore[attr-defined]

    def _ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
