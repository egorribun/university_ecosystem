"""Closure tests for schedule service success paths."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions.domain import BusinessRuleViolation
from app.schemas.schedule import ScheduleUpdate
from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)
from app.services.schedule_service import ScheduleService


def _uow() -> MagicMock:
    uow = MagicMock()
    uow.schedules = AsyncMock()
    uow.groups = AsyncMock()
    uow.session = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    return uow


def _schedule(group_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        group_id=group_id,
        subject="Mathematics",
        teacher="Dr. Test",
        room="101",
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
        lesson_type="lecture",
    )


@pytest.mark.asyncio
async def test_create_schedule_uses_teacher_and_default_parity():
    group_id = uuid.uuid4()
    created = _schedule(group_id)
    uow = _uow()
    uow.schedules.get_by_group = AsyncMock(return_value=[])
    uow.schedules.get_by_teacher = AsyncMock(return_value=[])
    uow.schedules.create = AsyncMock(return_value=created)
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[])
    service = ScheduleService(uow, optimizer)
    data = SimpleNamespace(
        group_id=group_id,
        teacher="Dr. Test",
        weekday="Monday",
        start_time=created.start_time,
        end_time=created.end_time,
        parity=None,
    )

    with patch("app.services.audit_service.get_secure_audit_service") as factory:
        factory.return_value.record_domain_event = AsyncMock()
        result = await service.create_schedule(
            data, locale="ru", creator_id=uuid.uuid4()
        )

    assert result is created
    uow.schedules.get_by_teacher.assert_awaited_once_with("Dr. Test")
    assert optimizer.detect_conflicts.await_args.args[0].parity == "both"
    uow.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_schedule_success_records_audit_and_commits():
    schedule_id = uuid.uuid4()
    group_id = uuid.uuid4()
    current = _schedule(group_id)
    updated = _schedule(group_id)
    uow = _uow()
    uow.schedules.get = AsyncMock(return_value=current)
    uow.schedules.get_by_group = AsyncMock(return_value=[current])
    uow.schedules.get_by_teacher = AsyncMock(return_value=[current])
    uow.schedules.update = AsyncMock(return_value=updated)
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[])
    service = ScheduleService(uow, optimizer)
    data = ScheduleUpdate(subject="Updated")
    audit = AsyncMock()

    with patch("app.services.audit_service.get_secure_audit_service") as factory:
        factory.return_value.record_domain_event = audit
        result = await service.update_schedule(schedule_id, data)

    assert result is updated
    uow.schedules.update.assert_awaited_once_with(schedule_id, data)
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["event_type"] == "SCHEDULE_UPDATED"
    uow.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_schedule_checks_effective_values_and_excludes_current_item():
    schedule_id = uuid.uuid4()
    group_id = uuid.uuid4()
    current = _schedule(group_id)
    current.id = schedule_id
    updated = _schedule(group_id)
    updated.id = schedule_id
    uow = _uow()
    uow.schedules.get = AsyncMock(return_value=current)
    uow.schedules.get_by_group = AsyncMock(return_value=[current])
    uow.schedules.get_by_teacher = AsyncMock(return_value=[current])
    uow.schedules.update = AsyncMock(return_value=updated)
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[])
    service = ScheduleService(uow, optimizer)
    data = ScheduleUpdate(subject="Updated subject")
    audit = AsyncMock()

    with patch("app.services.audit_service.get_secure_audit_service") as factory:
        factory.return_value.record_domain_event = audit
        result = await service.update_schedule(schedule_id, data)

    assert result is updated
    target, existing = optimizer.detect_conflicts.await_args.args
    assert target == ScheduleItemInternal(
        id=schedule_id,
        weekday=current.weekday,
        start_time=current.start_time,
        end_time=current.end_time,
        parity=current.parity,
        room=current.room,
        teacher=current.teacher,
    )
    assert existing == []
    uow.schedules.update.assert_awaited_once_with(schedule_id, data)
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["event_type"] == "SCHEDULE_UPDATED"
    uow.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_noop_update_with_real_optimizer_excludes_current_schedule():
    schedule_id = uuid.uuid4()
    current = _schedule(uuid.uuid4())
    current.id = schedule_id
    uow = _uow()
    uow.schedules.get = AsyncMock(return_value=current)
    uow.schedules.get_by_group = AsyncMock(return_value=[current])
    uow.schedules.get_by_teacher = AsyncMock(return_value=[current])
    uow.schedules.update = AsyncMock(return_value=current)
    service = ScheduleService(uow, ScheduleOptimizerService())
    audit = AsyncMock()

    with patch("app.services.audit_service.get_secure_audit_service") as factory:
        factory.return_value.record_domain_event = audit
        result = await service.update_schedule(schedule_id, ScheduleUpdate())

    assert result is current
    uow.schedules.get_by_group.assert_awaited_once_with(current.group_id)
    uow.schedules.get_by_teacher.assert_awaited_once_with(current.teacher)
    uow.schedules.update.assert_awaited_once()
    audit.assert_awaited_once()
    uow.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_schedule_uses_changed_group_and_skips_empty_teacher_lookup():
    current = _schedule(uuid.uuid4())
    target_group_id = uuid.uuid4()
    updated = _schedule(target_group_id)
    uow = _uow()
    uow.schedules.get = AsyncMock(return_value=current)
    uow.schedules.get_by_group = AsyncMock(return_value=[])
    uow.schedules.get_by_teacher = AsyncMock(return_value=[])
    uow.schedules.update = AsyncMock(return_value=updated)
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[])
    service = ScheduleService(uow, optimizer)
    data = ScheduleUpdate(group_id=target_group_id, teacher=None, weekday="Tuesday")

    with patch("app.services.audit_service.get_secure_audit_service") as factory:
        factory.return_value.record_domain_event = AsyncMock()
        result = await service.update_schedule(current.id, data)

    assert result is updated
    uow.schedules.get_by_group.assert_awaited_once_with(target_group_id)
    uow.schedules.get_by_teacher.assert_not_awaited()
    target, existing = optimizer.detect_conflicts.await_args.args
    assert target.weekday == "Tuesday"
    assert target.teacher is None
    assert existing == []


@pytest.mark.asyncio
async def test_update_schedule_rejects_conflict_before_update_audit_or_commit():
    schedule_id = uuid.uuid4()
    group_id = uuid.uuid4()
    current = _schedule(group_id)
    current.id = schedule_id
    conflict = _schedule(group_id)
    conflict.id = uuid.uuid4()
    conflict.start_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    conflict.end_time = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    uow = _uow()
    uow.schedules.get = AsyncMock(return_value=current)
    uow.schedules.get_by_group = AsyncMock(return_value=[current, conflict])
    uow.schedules.get_by_teacher = AsyncMock(return_value=[current])
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[conflict])
    service = ScheduleService(uow, optimizer)
    data = ScheduleUpdate(
        start_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
    )
    audit = AsyncMock()

    with patch("app.services.audit_service.get_secure_audit_service") as factory:
        factory.return_value.record_domain_event = audit
        with pytest.raises(BusinessRuleViolation, match="conflict"):
            await service.update_schedule(schedule_id, data)

    target, existing = optimizer.detect_conflicts.await_args.args
    assert target.start_time == data.start_time
    assert target.end_time == data.end_time
    assert [item.id for item in existing] == [conflict.id]
    uow.schedules.update.assert_not_awaited()
    audit.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_schedule_rejects_repository_miss_after_initial_lookup():
    uow = _uow()
    current = _schedule(uuid.uuid4())
    uow.schedules.get = AsyncMock(return_value=current)
    uow.schedules.get_by_group = AsyncMock(return_value=[current])
    uow.schedules.get_by_teacher = AsyncMock(return_value=[current])
    uow.schedules.update = AsyncMock(return_value=None)
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[])
    service = ScheduleService(uow, optimizer)

    with pytest.raises(ValueError, match="not found"):
        await service.update_schedule(uuid.uuid4(), ScheduleUpdate())
