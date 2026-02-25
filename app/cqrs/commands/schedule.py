import uuid
from dataclasses import dataclass

from app.cqrs.base import Command, CommandHandler
from app.deps.cache import BaseCache
from app.models import models
from app.schemas import schemas
from app.schemas.dtos import ScheduleDTO
from app.services.schedule_service import ScheduleService


@dataclass
class CreateScheduleCommand(Command):
    data: schemas.ScheduleCreate
    locale: str

class CreateScheduleHandler(CommandHandler[CreateScheduleCommand, ScheduleDTO]):
    def __init__(self, service: ScheduleService, cache: BaseCache):
        self.service = service
        self.cache = cache

    async def handle(self, command: CreateScheduleCommand) -> ScheduleDTO:
        result = await self.service.create_schedule(command.data, locale=command.locale)
        await self.cache.invalidate(f"schedule:group:{result.group_id}")
        return result

@dataclass
class UpdateScheduleCommand(Command):
    schedule_id: uuid.UUID
    data: schemas.ScheduleUpdate

class UpdateScheduleHandler(CommandHandler[UpdateScheduleCommand, ScheduleDTO]):
    def __init__(self, service: ScheduleService, cache: BaseCache):
        self.service = service
        self.cache = cache

    async def handle(self, command: UpdateScheduleCommand) -> ScheduleDTO:
        sched = await self.service.get_by_id(command.schedule_id)
        if not sched:
            raise ValueError("Schedule not found")

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

class DeleteScheduleHandler(CommandHandler[DeleteScheduleCommand, bool]):
    def __init__(self, service: ScheduleService, cache: BaseCache):
        self.service = service
        self.cache = cache

    async def handle(self, command: DeleteScheduleCommand) -> bool:
        sched = await self.service.get_by_id(command.schedule_id)
        if not sched:
            return False

        group_id = sched.group_id
        deleted = await self.service.delete_schedule(command.schedule_id)

        if deleted:
            await self.cache.invalidate(f"schedule:group:{group_id}")

        return deleted
