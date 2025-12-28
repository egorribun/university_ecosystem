"""
Base repository pattern implementation.

Provides abstract repository for standardized data access operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)
CreateSchemaT = TypeVar("CreateSchemaT")
UpdateSchemaT = TypeVar("UpdateSchemaT")


class BaseRepository(ABC, Generic[ModelT, CreateSchemaT, UpdateSchemaT]):
    """Abstract base repository for CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    @abstractmethod
    def model(self) -> type[ModelT]:
        """Return the SQLAlchemy model class."""
        ...

    async def get(self, id: int) -> ModelT | None:
        """Get a single record by ID."""
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalars().first()

    async def get_or_raise(self, id: int) -> ModelT:
        """Get a record by ID or raise ValueError."""
        record = await self.get(id)
        if record is None:
            raise ValueError(f"{self.model.__name__} with id {id} not found")
        return record

    async def get_by_ids(self, ids: Sequence[int]) -> list[ModelT]:
        """Get multiple records by IDs."""
        if not ids:
            return []
        result = await self.db.execute(select(self.model).where(self.model.id.in_(ids)))
        return list(result.scalars().all())

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: Any | None = None,
    ) -> list[ModelT]:
        """List records with pagination."""
        stmt = select(self.model)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count total records."""
        result = await self.db.execute(select(func.count(self.model.id)))
        return result.scalar() or 0

    async def create(self, data: CreateSchemaT) -> ModelT:
        """Create a new record."""
        if hasattr(data, "model_dump"):
            obj_data = data.model_dump()  # type: ignore
        else:
            obj_data = dict(data)  # type: ignore
        instance = self.model(**obj_data)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def update(self, id: int, data: UpdateSchemaT) -> ModelT | None:
        """Update a record by ID."""
        record = await self.get(id)
        if record is None:
            return None

        if hasattr(data, "model_dump"):
            update_data = data.model_dump(exclude_unset=True)  # type: ignore
        else:
            update_data = dict(data)  # type: ignore

        for field, value in update_data.items():
            setattr(record, field, value)

        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def delete(self, id: int) -> bool:
        """Delete a record by ID."""
        result = await self.db.execute(delete(self.model).where(self.model.id == id))
        return (result.rowcount or 0) > 0

    async def exists(self, id: int) -> bool:
        """Check if a record exists."""
        result = await self.db.execute(
            select(func.count(self.model.id)).where(self.model.id == id)
        )
        return (result.scalar() or 0) > 0


class ReadOnlyRepository(ABC, Generic[ModelT]):
    """Read-only repository for query operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    @abstractmethod
    def model(self) -> type[ModelT]: ...

    async def get(self, id: int) -> ModelT | None:
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalars().first()

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[ModelT]:
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


__all__ = [
    "BaseRepository",
    "ReadOnlyRepository",
    "ModelT",
    "CreateSchemaT",
    "UpdateSchemaT",
]
