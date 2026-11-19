"""Unit tests for the CQRS schedule command handlers (app/cqrs/commands/schedule.py).

Hermetic — no DB/Redis/NATS. The handlers' service collaborators are
``AsyncMock`` doubles. These tests cover service delegation and the
ownership-enforcement branches (SEC-BE-01 / RZ-W19-11).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cqrs.commands.schedule import (
    CreateScheduleCommand,
    CreateScheduleHandler,
    DeleteScheduleCommand,
    DeleteScheduleHandler,
    UpdateScheduleCommand,
    UpdateScheduleHandler,
)
from app.models.enums import UserRole


def _sched(group_id: uuid.UUID, creator_id: uuid.UUID | None):
    sched = MagicMock()
    sched.group_id = group_id
    sched.creator_id = creator_id
    return sched


# --------------------------------------------------------------------------- #
# CreateScheduleHandler
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_invokes_service_with_actor_and_locale():
    group_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    result = _sched(group_id, actor_id)

    service = AsyncMock()
    service.create_schedule.return_value = result
    handler = CreateScheduleHandler(service)
    data = MagicMock()
    command = CreateScheduleCommand(data=data, locale="ru", actor_id=actor_id)

    returned = await handler.handle(command)

    assert returned is result
    service.create_schedule.assert_awaited_once_with(
        data, locale="ru", creator_id=actor_id
    )


# --------------------------------------------------------------------------- #
# UpdateScheduleHandler
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_update_raises_value_error_when_not_found():
    service = AsyncMock()
    service.get_by_id.return_value = None
    handler = UpdateScheduleHandler(service)
    command = UpdateScheduleCommand(schedule_id=uuid.uuid4(), data=MagicMock())

    with pytest.raises(ValueError, match="Schedule not found"):
        await handler.handle(command)

    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.update_schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_non_admin_legacy_row_creator_none_is_forbidden():
    """Non-admin updating a legacy schedule (creator_id=None) → PermissionError."""
    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=None)
    handler = UpdateScheduleHandler(service)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.STUDENT,
    )

    with pytest.raises(PermissionError, match="Not the owner"):
        await handler.handle(command)
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.update_schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_non_admin_other_owner_is_forbidden():
    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=uuid.uuid4())
    handler = UpdateScheduleHandler(service)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=uuid.uuid4(),  # different from creator_id
        actor_role=UserRole.STUDENT,
    )

    with pytest.raises(PermissionError):
        await handler.handle(command)
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.update_schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_owner_delegates_group_change_to_service():
    actor_id = uuid.uuid4()
    old_group = uuid.uuid4()
    new_group = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(old_group, creator_id=actor_id)
    result = _sched(new_group, creator_id=actor_id)
    service.update_schedule.return_value = result

    handler = UpdateScheduleHandler(service)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=actor_id,
        actor_role=UserRole.STUDENT,
    )

    updated = await handler.handle(command)

    assert updated is result
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.update_schedule.assert_awaited_once_with(command.schedule_id, command.data)


@pytest.mark.asyncio
async def test_update_admin_bypasses_ownership_check():
    """Admin may update a legacy (creator_id=None) schedule they don't own."""
    old_group = uuid.uuid4()
    new_group = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(old_group, creator_id=None)
    service.update_schedule.return_value = _sched(new_group, creator_id=None)
    handler = UpdateScheduleHandler(service)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.ADMIN,
    )

    updated = await handler.handle(command)
    assert updated.group_id == new_group
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.update_schedule.assert_awaited_once_with(command.schedule_id, command.data)


# --------------------------------------------------------------------------- #
# DeleteScheduleHandler
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_returns_false_when_not_found():
    service = AsyncMock()
    service.get_by_id.return_value = None
    handler = DeleteScheduleHandler(service)
    command = DeleteScheduleCommand(schedule_id=uuid.uuid4())

    assert await handler.handle(command) is False
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.delete_schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_non_admin_non_owner_is_forbidden():
    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=uuid.uuid4())
    handler = DeleteScheduleHandler(service)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.STUDENT,
    )

    with pytest.raises(PermissionError, match="Not authorized"):
        await handler.handle(command)
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.delete_schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_owner_delegates_to_service():
    actor_id = uuid.uuid4()
    group_id = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(group_id, creator_id=actor_id)
    service.delete_schedule.return_value = True
    handler = DeleteScheduleHandler(service)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(), actor_id=actor_id, actor_role=UserRole.STUDENT
    )

    assert await handler.handle(command) is True
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.delete_schedule.assert_awaited_once_with(command.schedule_id)


@pytest.mark.asyncio
async def test_delete_propagates_false_from_service():
    actor_id = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=actor_id)
    service.delete_schedule.return_value = False
    handler = DeleteScheduleHandler(service)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(), actor_id=actor_id, actor_role=UserRole.STUDENT
    )

    assert await handler.handle(command) is False
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.delete_schedule.assert_awaited_once_with(command.schedule_id)


@pytest.mark.asyncio
async def test_delete_admin_bypasses_ownership_check():
    group_id = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(group_id, creator_id=None)
    service.delete_schedule.return_value = True
    handler = DeleteScheduleHandler(service)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.ADMIN,
    )

    assert await handler.handle(command) is True
    service.get_by_id.assert_awaited_once_with(command.schedule_id)
    service.delete_schedule.assert_awaited_once_with(command.schedule_id)
