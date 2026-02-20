from app.core.localization import translate
from app.models import models
from app.repositories.schedule_repository import GroupRepository, ScheduleRepository
from app.schemas import schemas
from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


class ScheduleService:
    def __init__(
        self,
        repo: ScheduleRepository,
        group_repo: GroupRepository,
        optimizer: ScheduleOptimizerService,
    ):
        self.repo = repo
        self.group_repo = group_repo
        self.optimizer = optimizer

    async def create_schedule(
        self, data: schemas.ScheduleCreate, locale: str = "en"
    ) -> models.Schedule:
        # Conflict check
        existing_group = await self.repo.get_by_group(data.group_id)

        existing_teacher = []
        if data.teacher:
            existing_teacher = await self.repo.get_by_teacher(data.teacher)

        all_existing = list(existing_group) + list(existing_teacher)

        target = ScheduleItemInternal(
            weekday=data.weekday,
            start_time=data.start_time,
            end_time=data.end_time,
            parity=data.parity or "both",
        )
        existing_items = [
            ScheduleItemInternal(
                id=s.id,
                weekday=s.weekday,
                start_time=s.start_time,
                end_time=s.end_time,
                parity=s.parity,
            )
            for s in all_existing
        ]

        conflicts = await self.optimizer.detect_conflicts(target, existing_items)
        if conflicts:
            # We raise directly or use helper?
            # The API helper 'raise_conflict' raises HTTPException.
            # Services should ideally raise Domain Exceptions.
            # But the existing `raise_conflict` is imported from `app.api.validation`.
            # Let's use it for now to match behavior, or raise BusinessRuleViolation.
            # BusinessRuleViolation is better for Service layer.
            # But the user asked to minimize friction.
            # Let's use BusinessRuleViolation and let API handle it?
            # Or just raise HTTPException since we are wrapping API logic.
            # I will use BusinessRuleViolation for cleaner architecture if available.
            # Let's check imports in user_service. It uses BusinessRuleViolation.
            from app.core.exceptions.domain import BusinessRuleViolation

            raise BusinessRuleViolation(
                translate("errors.schedule.conflict", locale=locale)
            )

        schedule = await self.repo.create(data)
        await self.repo.commit()
        await self.repo.refresh(schedule)

        return schedule

    async def get_schedule(self, group_id: int) -> list[models.Schedule]:
        return await self.repo.get_by_group(group_id)  # type: ignore[arg-type]

    async def get_by_id(self, schedule_id: int) -> models.Schedule | None:
        return await self.repo.get(schedule_id)

    async def update_schedule(
        self, schedule_id: int, data: schemas.ScheduleUpdate
    ) -> models.Schedule:
        sched = await self.repo.get(schedule_id)
        if not sched:
            raise ValueError(translate("errors.schedule.not_found"))

        updated = await self.repo.update(schedule_id, data)
        assert updated is not None
        await self.repo.commit()
        return updated

    async def delete_schedule(self, schedule_id: int) -> bool:
        sched = await self.repo.get(schedule_id)
        if not sched:
            return False

        await self.repo.delete(schedule_id)
        await self.repo.commit()
        return True

    # Group methods
    async def list_groups(self) -> list[models.Group]:
        return await self.group_repo.list_groups()

    async def create_group(self, data: schemas.GroupCreate) -> models.Group:
        group = await self.group_repo.create(data)
        await self.repo.commit()
        await self.repo.refresh(group)
        return group
