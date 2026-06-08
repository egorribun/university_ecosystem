"""Unit tests for the CQRS schedule command handlers (app/cqrs/commands/schedule.py).

Hermetic — no DB/Redis/NATS. The handlers' `service` + `cache` collaborators are
pure ``AsyncMock`` doubles, mirroring the patch-at-module-level / assert-call-args
structure of tests/test_nats_broker.py. Covers the ownership-enforcement branches
(SEC-BE-01 / RZ-W19-11) that were previously uncovered — only the Command
*dataclasses* were exercised before, never the Handler.handle() bodies.
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
async def test_create_invokes_service_and_invalidates_cache():
    group_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    result = _sched(group_id, actor_id)

    service = AsyncMock()
    service.create_schedule.return_value = result
    cache = AsyncMock()

    handler = CreateScheduleHandler(service, cache)
    data = MagicMock()
    command = CreateScheduleCommand(data=data, locale="ru", actor_id=actor_id)

    returned = await handler.handle(command)

    assert returned is result
    service.create_schedule.assert_awaited_once_with(
        data, locale="ru", creator_id=actor_id
    )
    cache.invalidate.assert_awaited_once_with(f"schedule:group:{group_id}")


# --------------------------------------------------------------------------- #
# UpdateScheduleHandler
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_update_raises_value_error_when_not_found():
    service = AsyncMock()
    service.get_by_id.return_value = None
    cache = AsyncMock()

    handler = UpdateScheduleHandler(service, cache)
    command = UpdateScheduleCommand(schedule_id=uuid.uuid4(), data=MagicMock())

    with pytest.raises(ValueError, match="Schedule not found"):
        await handler.handle(command)

    service.update_schedule.assert_not_called()
    cache.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_update_non_admin_legacy_row_creator_none_is_forbidden():
    """Non-admin updating a legacy schedule (creator_id=None) → PermissionError."""
    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=None)
    cache = AsyncMock()

    handler = UpdateScheduleHandler(service, cache)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.STUDENT,
    )

    with pytest.raises(PermissionError, match="Not the owner"):
        await handler.handle(command)
    service.update_schedule.assert_not_called()


@pytest.mark.asyncio
async def test_update_non_admin_other_owner_is_forbidden():
    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=uuid.uuid4())
    cache = AsyncMock()

    handler = UpdateScheduleHandler(service, cache)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=uuid.uuid4(),  # different from creator_id
        actor_role=UserRole.STUDENT,
    )

    with pytest.raises(PermissionError):
        await handler.handle(command)


@pytest.mark.asyncio
async def test_update_owner_succeeds_and_invalidates_both_groups():
    actor_id = uuid.uuid4()
    old_group = uuid.uuid4()
    new_group = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(old_group, creator_id=actor_id)
    service.update_schedule.return_value = _sched(new_group, creator_id=actor_id)
    cache = AsyncMock()

    handler = UpdateScheduleHandler(service, cache)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=actor_id,
        actor_role=UserRole.STUDENT,
    )

    updated = await handler.handle(command)

    assert updated.group_id == new_group
    cache.invalidate.assert_awaited_once_with(
        f"schedule:group:{old_group}", f"schedule:group:{new_group}"
    )


@pytest.mark.asyncio
async def test_update_admin_bypasses_ownership_check():
    """Admin may update a legacy (creator_id=None) schedule they don't own."""
    old_group = uuid.uuid4()
    new_group = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(old_group, creator_id=None)
    service.update_schedule.return_value = _sched(new_group, creator_id=None)
    cache = AsyncMock()

    handler = UpdateScheduleHandler(service, cache)
    command = UpdateScheduleCommand(
        schedule_id=uuid.uuid4(),
        data=MagicMock(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.ADMIN,
    )

    updated = await handler.handle(command)
    assert updated.group_id == new_group
    cache.invalidate.assert_awaited_once()


# --------------------------------------------------------------------------- #
# DeleteScheduleHandler
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_returns_false_when_not_found():
    service = AsyncMock()
    service.get_by_id.return_value = None
    cache = AsyncMock()

    handler = DeleteScheduleHandler(service, cache)
    command = DeleteScheduleCommand(schedule_id=uuid.uuid4())

    assert await handler.handle(command) is False
    service.delete_schedule.assert_not_called()
    cache.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_delete_non_admin_non_owner_is_forbidden():
    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=uuid.uuid4())
    cache = AsyncMock()

    handler = DeleteScheduleHandler(service, cache)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.STUDENT,
    )

    with pytest.raises(PermissionError, match="Not authorized"):
        await handler.handle(command)
    service.delete_schedule.assert_not_called()


@pytest.mark.asyncio
async def test_delete_owner_success_invalidates_cache():
    actor_id = uuid.uuid4()
    group_id = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(group_id, creator_id=actor_id)
    service.delete_schedule.return_value = True
    cache = AsyncMock()

    handler = DeleteScheduleHandler(service, cache)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(), actor_id=actor_id, actor_role=UserRole.STUDENT
    )

    assert await handler.handle(command) is True
    cache.invalidate.assert_awaited_once_with(f"schedule:group:{group_id}")


@pytest.mark.asyncio
async def test_delete_service_returns_false_skips_cache_invalidation():
    """When the service reports nothing deleted, no cache invalidation fires."""
    actor_id = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(uuid.uuid4(), creator_id=actor_id)
    service.delete_schedule.return_value = False
    cache = AsyncMock()

    handler = DeleteScheduleHandler(service, cache)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(), actor_id=actor_id, actor_role=UserRole.STUDENT
    )

    assert await handler.handle(command) is False
    cache.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_delete_admin_bypasses_ownership_and_invalidates():
    group_id = uuid.uuid4()

    service = AsyncMock()
    service.get_by_id.return_value = _sched(group_id, creator_id=None)
    service.delete_schedule.return_value = True
    cache = AsyncMock()

    handler = DeleteScheduleHandler(service, cache)
    command = DeleteScheduleCommand(
        schedule_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        actor_role=UserRole.ADMIN,
    )

    assert await handler.handle(command) is True
    cache.invalidate.assert_awaited_once_with(f"schedule:group:{group_id}")
