from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.cache import schedule_cache
from app.models import models
from app.repositories.base import BaseRepository
from app.schemas import schemas
from app.schemas.dtos import GroupDTO, ScheduleDTO

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession


class GroupRepository(
    BaseRepository[models.Group, GroupDTO, schemas.GroupCreate, schemas.GroupUpdate]
):
    @property
    def model(self) -> type[models.Group]:
        return models.Group

    @property
    def dto_class(self) -> type[GroupDTO]:
        return GroupDTO

    # Safety cap: no university has more than this many groups.
    # Prevents runaway queries if data grows unexpectedly.
    _MAX_GROUPS: int = 1000

    async def list_groups(self) -> Sequence[GroupDTO]:
        """List all groups with caching."""
        cache_key = "schedule:groups"
        cached = await schedule_cache.get(cache_key)
        if cached is not None:
            from typing import cast

            return cast(list[GroupDTO], cached)

        stmt = select(self.model).order_by(self.model.name).limit(self._MAX_GROUPS)
        result = await self.db.execute(stmt)
        groups = list(result.scalars().all())
        dtos = [self._to_dto(g) for g in groups]
        await schedule_cache.set(cache_key, dtos)
        return dtos


class ScheduleRepository(
    BaseRepository[
        models.Schedule, ScheduleDTO, schemas.ScheduleCreate, schemas.ScheduleUpdate
    ]
):
    @property
    def model(self) -> type[models.Schedule]:
        return models.Schedule

    @property
    def dto_class(self) -> type[ScheduleDTO]:
        return ScheduleDTO

    # Safety cap: a group cannot realistically have more schedule items than this.
    _MAX_ITEMS_PER_GROUP: int = 500

    async def get_by_group(self, group_id: uuid.UUID) -> Sequence[ScheduleDTO]:
        """Get schedule for a group with caching."""
        cache_key = f"schedule:group:{group_id}"
        cached = await schedule_cache.get(cache_key)
        if cached is not None:
            from typing import cast

            return cast(list[ScheduleDTO], cached)

        stmt = (
            select(self.model)
            .where(self.model.group_id == group_id)
            .order_by(self.model.weekday, self.model.start_time)
            .limit(self._MAX_ITEMS_PER_GROUP)
        )
        result = await self.db.execute(stmt)
        schedule_items = list(result.scalars().all())
        dtos = [self._to_dto(s) for s in schedule_items]
        await schedule_cache.set(cache_key, dtos)
        return dtos

    async def get_by_teacher(self, teacher: str) -> Sequence[ScheduleDTO]:
        stmt = (
            select(self.model)
            .where(self.model.teacher == teacher)
            .order_by(self.model.weekday, self.model.start_time)
        )
        result = await self.db.execute(stmt)
        return [self._to_dto(s) for s in result.scalars().all()]

    async def create(
        self, obj_in: schemas.ScheduleCreate | dict[str, Any]
    ) -> ScheduleDTO:
        # Override to handle UTC conversion if needed
        data = obj_in.model_dump() if hasattr(obj_in, "model_dump") else obj_in.copy()
        data["start_time"] = self._ensure_utc(data["start_time"])
        data["end_time"] = self._ensure_utc(data["end_time"])

        return await super().create(data)


def get_group_repository(db: AsyncDatabaseSession) -> GroupRepository:
    return GroupRepository(db)


def get_schedule_repository(db: AsyncDatabaseSession) -> ScheduleRepository:
    return ScheduleRepository(db)
