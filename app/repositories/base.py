import abc
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base


class ReadOnlyRepository[T: Base](abc.ABC):
    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    @abc.abstractmethod
    def model(self) -> type[T]: ...

    async def get(self, id: Any) -> T | None:
        target_id = self._cast_id(id)
        stmt = select(self.model).where(self.model.id == target_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_or_raise(self, id: Any) -> T:
        db_obj = await self.get(id)
        if db_obj is None:
            raise ValueError(f"{self.model.__name__} with id {id} not found")
        return db_obj

    async def get_by_ids(self, ids: list[Any]) -> Sequence[T]:
        if not ids:
            return []
        target_ids = [self._cast_id(idx) for idx in ids]
        stmt = select(self.model).where(self.model.id.in_(target_ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list(
        self, *, skip: int = 0, limit: int = 100, order_by: Any = None
    ) -> Sequence[T]:
        stmt = select(self.model).offset(skip).limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def exists(self, id: Any) -> bool:
        target_id = self._cast_id(id)
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.id == target_id)
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


class BaseRepository[T: Base, CreateT, UpdateT](ReadOnlyRepository[T]):
    async def create(self, obj_in: CreateT | dict[str, Any]) -> T:
        if hasattr(obj_in, "model_dump"):
            obj_data = obj_in.model_dump()
        else:
            obj_data = obj_in  # type: ignore

        db_obj = self.model(**obj_data)
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj

    async def update(self, id: Any, obj_in: UpdateT | dict[str, Any]) -> T | None:
        db_obj = await self.get(id)
        if db_obj is None:
            return None

        if hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = obj_in  # type: ignore

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, id: Any) -> bool:
        target_id = self._cast_id(id)
        stmt = delete(self.model).where(self.model.id == target_id)
        result = await self.db.execute(stmt)
        return (result.rowcount or 0) > 0

    def _ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
