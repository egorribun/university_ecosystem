from __future__ import annotations

import abc
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.core.database import Base


class ReadOnlyRepository[T: Base, DTOT: BaseModel](abc.ABC):
    def __init__(self, db: AsyncDatabaseSession):
        self.db = db

    def add(self, obj: Any) -> None:
        """Add an object to the current session."""
        self.db.add(obj)

    @property
    @abc.abstractmethod
    def model(self) -> type[T]: ...

    @property
    @abc.abstractmethod
    def dto_class(self) -> type[DTOT]: ...

    def _to_dto(self, obj: T) -> DTOT:
        """Convert ORM object to DTO."""
        return self.dto_class.model_validate(obj)

    async def _get_orm(self, id: Any, *, with_for_update: bool = False) -> T | None:
        """Internal helper to get the ORM object."""
        target_id = self._cast_id(id)
        stmt = select(self.model).where(self.model.id == target_id)  # type: ignore[attr-defined]
        if with_for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get(self, id: Any, *, with_for_update: bool = False) -> DTOT | None:
        obj = await self._get_orm(id, with_for_update=with_for_update)
        return self._to_dto(obj) if obj else None

    async def get_or_raise(self, id: Any, *, with_for_update: bool = False) -> DTOT:
        dto = await self.get(id, with_for_update=with_for_update)
        if dto is None:
            raise ValueError(f"{self.model.__name__} with id {id} not found")
        return dto

    async def get_by_ids(
        self, ids: list[Any], *, with_for_update: bool = False
    ) -> Sequence[DTOT]:
        if not ids:
            return []
        target_ids = [self._cast_id(idx) for idx in ids]
        stmt = select(self.model).where(self.model.id.in_(target_ids))  # type: ignore[attr-defined]
        if with_for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def list(
        self, *, skip: int = 0, limit: int = 100, order_by: Any = None
    ) -> Sequence[DTOT]:
        stmt = select(self.model).offset(skip).limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await self.db.execute(stmt)
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def exists(self, id: Any) -> bool:
        target_id = self._cast_id(id)
        stmt = (
            select(func.count()).where(self.model.id == target_id)  # type: ignore[attr-defined]
        )
        result = await self.db.execute(stmt)
        return (result.scalar() or 0) > 0

    def _cast_id(self, id_val: Any) -> Any:
        """Cast input ID to UUID if applicable, preventing SQLAlchemy errors."""
        if isinstance(id_val, str) and len(id_val) >= 32:
            try:
                return uuid.UUID(id_val)
            except (ValueError, TypeError):
                return id_val
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
            stmt = stmt.where(Column.ilike(f"%{safe}%", escape="\\\\"))
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
