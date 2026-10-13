import uuid
from collections.abc import Sequence
from datetime import date, time
from typing import Any

from app.core.localization import translate
from app.repositories.unit_of_work import UnitOfWork
from app.schemas import schemas
from app.schemas.dtos import GroupDTO, ScheduleDTO
from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


def _json_value(value: Any) -> Any:
    """Serialize temporal values: outbox payloads are hashed with plain JSON."""
    if isinstance(value, date | time):
        return value.isoformat()
    return value


def schedule_state(schedule: ScheduleDTO) -> dict[str, Any]:
    """JSON-safe snapshot of the schedule fields recorded in domain events."""
    return {
        "group_id": str(schedule.group_id),
        "subject": schedule.subject,
        "teacher": schedule.teacher,
        "room": schedule.room,
        "weekday": _json_value(schedule.weekday),
        "start_time": _json_value(schedule.start_time),
        "end_time": _json_value(schedule.end_time),
        "parity": schedule.parity,
        "lesson_type": schedule.lesson_type,
    }


class ScheduleService:
    def __init__(
        self,
        uow: UnitOfWork,
        optimizer: ScheduleOptimizerService,
    ):
        self.uow = uow
        self.repo = uow.schedules
        self.group_repo = uow.groups
        self.optimizer = optimizer

    async def create_schedule(
        self,
        data: schemas.ScheduleCreate,
        locale: str = "en",
        creator_id: uuid.UUID | None = None,
    ) -> ScheduleDTO:
        # Serialize the conflict read and write in one transaction. The
        # repository query bypasses the display cache and its 500-row cap.
        await self.repo.lock_schedule_mutations()
        all_existing = await self.repo.get_conflict_candidates(
            data.group_id, data.teacher
        )

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
            from app.core.exceptions.domain import BusinessRuleViolation

            raise BusinessRuleViolation(
                translate("errors.schedule.conflict", locale=locale)
            )

        schedule = await self.repo.create(data, creator_id=creator_id)
        payload = schedule_state(schedule)
        from app.services.audit_service import get_secure_audit_service

        await get_secure_audit_service().record_domain_event(
            self.uow.session,
            event_type="SCHEDULE_CREATED",
            aggregate_type="schedule",
            aggregate_id=schedule.id,
            payload=payload,
            actor_id=creator_id,
        )
        async with self.uow:
            await self.uow.commit()

        return schedule

    async def get_schedule(self, group_id: uuid.UUID | str) -> Sequence[ScheduleDTO]:
        return await self.repo.get_by_group(group_id)  # type: ignore[arg-type]

    async def get_by_id(self, schedule_id: uuid.UUID | str) -> ScheduleDTO | None:
        return await self.repo.get(schedule_id)

    async def update_schedule(
        self, schedule_id: uuid.UUID | str, data: schemas.ScheduleUpdate
    ) -> ScheduleDTO:
        # Acquire before loading the current row so this update uses state that
        # reflects any competing schedule mutation that committed while waiting.
        await self.repo.lock_schedule_mutations()
        sched = await self.repo.get_for_update_fresh(schedule_id)
        if not sched:
            raise ValueError(translate("errors.schedule.not_found"))

        update_values = data.model_dump(exclude_unset=True)
        group_id = update_values.get("group_id", sched.group_id)
        teacher = update_values.get("teacher", sched.teacher)
        all_existing = [
            item
            for item in await self.repo.get_conflict_candidates(group_id, teacher)
            if item.id != sched.id
        ]
        target = ScheduleItemInternal(
            id=sched.id,
            weekday=update_values.get("weekday", sched.weekday),
            start_time=update_values.get("start_time", sched.start_time),
            end_time=update_values.get("end_time", sched.end_time),
            parity=update_values.get("parity", sched.parity) or "both",
            room=update_values.get("room", sched.room),
            teacher=teacher,
        )
        existing_items = [
            ScheduleItemInternal(
                id=item.id,
                weekday=item.weekday,
                start_time=item.start_time,
                end_time=item.end_time,
                parity=item.parity,
                room=item.room,
                teacher=item.teacher,
            )
            for item in all_existing
        ]
        conflicts = await self.optimizer.detect_conflicts(target, existing_items)
        if conflicts:
            from app.core.exceptions.domain import BusinessRuleViolation

            raise BusinessRuleViolation(translate("errors.schedule.conflict"))

        # Snapshot before the update: the repository may mutate this object.
        previous_state = schedule_state(sched)

        updated = await self.repo.update(schedule_id, data)
        if updated is None:
            raise ValueError(translate("errors.schedule.not_found"))

        payload = {
            "schedule_id": str(updated.id),
            "previous_state": previous_state,
            "current_state": schedule_state(updated),
        }
        from app.services.audit_service import get_secure_audit_service

        await get_secure_audit_service().record_domain_event(
            self.uow.session,
            event_type="SCHEDULE_UPDATED",
            aggregate_type="schedule",
            aggregate_id=updated.id,
            payload=payload,
        )
        async with self.uow:
            await self.uow.commit()
        return updated

    async def delete_schedule(self, schedule_id: uuid.UUID | str) -> bool:
        sched = await self.repo.get(schedule_id)
        if not sched:
            return False

        payload = {
            "schedule_id": str(schedule_id),
            "deleted": True,
            "subject": sched.subject,
            "group_id": str(sched.group_id),
            "previous_state": schedule_state(sched),
        }
        from app.services.audit_service import get_secure_audit_service

        await get_secure_audit_service().record_domain_event(
            self.uow.session,
            event_type="SCHEDULE_DELETED",
            aggregate_type="schedule",
            aggregate_id=schedule_id,
            payload=payload,
        )

        await self.repo.delete(schedule_id)
        async with self.uow:
            await self.uow.commit()
        return True

    # Group methods
    async def list_groups(self) -> Sequence[GroupDTO]:
        return await self.group_repo.list_groups()

    async def create_group(self, data: schemas.GroupCreate) -> GroupDTO:
        group = await self.group_repo.create(data)
        async with self.uow:
            await self.uow.commit()
        return group
