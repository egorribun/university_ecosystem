import uuid
from dataclasses import dataclass

from app.cqrs.base import Command, CommandHandler
from app.deps.cache import BaseCache
from app.models.enums import UserRole
from app.schemas import schemas
from app.schemas.dtos import ScheduleDTO
from app.services.schedule_service import ScheduleService


@dataclass
class CreateScheduleCommand(Command):
    data: schemas.ScheduleCreate
    locale: str
    # SEC-BE-01: actor_id records ownership so update/delete can enforce it
    actor_id: uuid.UUID | None = None


class CreateScheduleHandler(CommandHandler[CreateScheduleCommand, ScheduleDTO]):
    def __init__(self, service: ScheduleService, cache: BaseCache):
        self.service = service
        self.cache = cache

    async def handle(self, command: CreateScheduleCommand) -> ScheduleDTO:
        result = await self.service.create_schedule(
            command.data, locale=command.locale, creator_id=command.actor_id
        )
        await self.cache.invalidate(f"schedule:group:{result.group_id}")
        return result


@dataclass
class UpdateScheduleCommand(Command):
    schedule_id: uuid.UUID
    data: schemas.ScheduleUpdate
    # SEC-BE-01 (audit Wave 10): actor fields for ownership enforcement.
    # actor_id=None only accepted when actor_role == "admin".
    actor_id: uuid.UUID | None = None
    actor_role: UserRole = UserRole.STUDENT


class UpdateScheduleHandler(CommandHandler[UpdateScheduleCommand, ScheduleDTO]):
    def __init__(self, service: ScheduleService, cache: BaseCache):
        self.service = service
        self.cache = cache

    async def handle(self, command: UpdateScheduleCommand) -> ScheduleDTO:
        sched = await self.service.get_by_id(command.schedule_id)
        if not sched:
            raise ValueError("Schedule not found")

        # SEC-BE-01: non-admins may only update schedules they created.
        # Schedules with creator_id=None (legacy rows) are admin-only.
        if command.actor_role != UserRole.ADMIN:
            if sched.creator_id is None or sched.creator_id != command.actor_id:
                raise PermissionError("Not the owner of this schedule")

        previous_group = sched.group_id
        updated = await self.service.update_schedule(command.schedule_id, command.data)

        await self.cache.invalidate(
            f"schedule:group:{previous_group}",
            f"schedule:group:{updated.group_id}",
        )
        return updated


@dataclass
class DeleteScheduleCommand(Command):
    schedule_id: uuid.UUID
    # RZ-W19-11: add actor fields for authorization (was missing entirely)
    actor_id: uuid.UUID | None = None
    actor_role: UserRole = UserRole.STUDENT


class DeleteScheduleHandler(CommandHandler[DeleteScheduleCommand, bool]):
    def __init__(self, service: ScheduleService, cache: BaseCache):
        self.service = service
        self.cache = cache

    async def handle(self, command: DeleteScheduleCommand) -> bool:
        sched = await self.service.get_by_id(command.schedule_id)
        if not sched:
            return False

        # RZ-W19-11: enforce ownership — non-admins can only delete their own schedules
        if command.actor_role != UserRole.ADMIN:
            if sched.creator_id is None or sched.creator_id != command.actor_id:
                raise PermissionError("Not authorized to delete this schedule")

        group_id = sched.group_id
        deleted = await self.service.delete_schedule(command.schedule_id)

        if deleted:
            await self.cache.invalidate(f"schedule:group:{group_id}")

        return deleted
