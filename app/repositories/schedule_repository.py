import uuid

from sqlalchemy import select

from app.core.cache import schedule_cache
from app.models import models
from app.repositories.base import BaseRepository
from app.schemas import schemas


class GroupRepository(
    BaseRepository[models.Group, schemas.GroupCreate, schemas.GroupUpdate]
):
    @property
    def model(self) -> type[models.Group]:
        return models.Group

    async def list_groups(self) -> list[models.Group]:
        """List all groups with caching."""
        cache_key = "schedule:groups"
        cached = await schedule_cache.get(cache_key)
        if cached is not None:
            from typing import cast

            return cast(list[models.Group], cached)

        stmt = select(self.model).order_by(self.model.name)
        result = await self.db.execute(stmt)
        groups = list(result.scalars().all())
        await schedule_cache.set(cache_key, groups)
        return groups


class ScheduleRepository(
    BaseRepository[models.Schedule, schemas.ScheduleCreate, schemas.ScheduleUpdate]
):
    @property
    def model(self) -> type[models.Schedule]:
        return models.Schedule

    async def get_by_group(self, group_id: uuid.UUID) -> list[models.Schedule]:
        """Get schedule for a group with caching."""
        cache_key = f"schedule:group:{group_id}"
        cached = await schedule_cache.get(cache_key)
        if cached is not None:
            from typing import cast

            return cast(list[models.Schedule], cached)

        stmt = (
            select(self.model)
            .where(self.model.group_id == group_id)
            .order_by(self.model.weekday, self.model.start_time)
        )
        result = await self.db.execute(stmt)
        schedule_items = list(result.scalars().all())
        await schedule_cache.set(cache_key, schedule_items)
        return schedule_items

    async def get_by_teacher(self, teacher: str) -> list[models.Schedule]:
        stmt = (
            select(self.model)
            .where(self.model.teacher == teacher)
            .order_by(self.model.weekday, self.model.start_time)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj_in: schemas.ScheduleCreate | dict) -> models.Schedule:
        # Override to handle UTC conversion if needed,
        # though BaseRepository doesn't do it automatically for fields.
        # crud.create_schedule did _ensure_utc.

        data = obj_in.model_dump() if hasattr(obj_in, "model_dump") else obj_in.copy()

        data["start_time"] = self._ensure_utc(data["start_time"])
        data["end_time"] = self._ensure_utc(data["end_time"])

        return await super().create(data)
