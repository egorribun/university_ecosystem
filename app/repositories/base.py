from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base


class BaseRepository[T: Base]:
    def __init__(self, model: type[T], db: AsyncSession):
        self.model = model
        self.db = db

    async def get(self, id: Any) -> T | None:
        return await self.db.get(self.model, id)

    async def get_multi(self, *, skip: int = 0, limit: int = 100) -> Sequence[T]:
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, **kwargs: Any) -> T:
        db_obj = self.model(**kwargs)
        self.db.add(db_obj)
        await self.db.flush()
        return db_obj

    async def update(self, db_obj: T, **kwargs: Any) -> T:
        for field, value in kwargs.items():
            setattr(db_obj, field, value)
        self.db.add(db_obj)
        await self.db.flush()
        return db_obj

    async def delete(self, id: Any) -> bool:
        db_obj = await self.get(id)
        if db_obj:
            await self.db.delete(db_obj)
            await self.db.flush()
            return True
        return False

    def _ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
