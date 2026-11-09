"""Actual schedule service paths must resolve parents before mutation.

Mocked visibility is a unit control, not PostgreSQL RLS execution evidence.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions.domain import EntityNotFound
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from app.schemas.schedule import ScheduleUpdate
from app.services.schedule_service import ScheduleService
from tests.test_schedule_service_closure import _schedule, _uow


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "move", "unchanged"])
@pytest.mark.parametrize("scope", ["", str(uuid.UUID(int=1)), str(uuid.UUID(int=2))])
async def test_invisible_parent_rejected_before_any_mutation(operation, scope):
    uow = _uow()
    current = _schedule(uuid.uuid4())
    uow.schedules.get_for_update_fresh.return_value = current
    uow.groups.get.return_value = None
    uow.schedules.create.return_value = current
    uow.schedules.update.return_value = current
    optimizer = AsyncMock()
    optimizer.detect_conflicts.return_value = []
    service = ScheduleService(uow, optimizer)
    events = []
    uow.schedules.lock_schedule_mutations.side_effect = lambda: events.append("lock")

    async def missing(*args, **kwargs):
        events.append("parent")
        assert tenant_id_ctx.get() == scope
        assert not bypass_rls_ctx.get()
        return None

    uow.groups.get.side_effect = missing
    token = tenant_id_ctx.set(scope)
    bypass = bypass_rls_ctx.set(False)
    try:
        with patch("app.services.audit_service.get_secure_audit_service") as audit:
            with pytest.raises(EntityNotFound):
                if operation == "create":
                    await service.create_schedule(current)
                else:
                    data = (
                        ScheduleUpdate(group_id=uuid.uuid4())
                        if operation == "move"
                        else ScheduleUpdate(room="202")
                    )
                    await service.update_schedule(current.id, data)
            target = data.group_id if operation == "move" else current.group_id
            uow.groups.get.assert_awaited_once_with(target, with_for_update=True)
            assert events == ["lock", "parent"]
            uow.schedules.create.assert_not_awaited()
            uow.schedules.update.assert_not_awaited()
            uow.schedules.get_conflict_candidates.assert_not_awaited()
            optimizer.detect_conflicts.assert_not_awaited()
            uow.commit.assert_not_awaited()
            audit.assert_not_called()
        assert tenant_id_ctx.get() == scope
        assert not bypass_rls_ctx.get()
    finally:
        bypass_rls_ctx.reset(bypass)
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_sqlite_real_repositories_validate_effective_parent_without_cache():
    from sqlalchemy import select

    from app import models
    from app.core.database import async_session
    from app.models.domain_events import StoredEvent
    from app.schemas import schemas
    from tests.test_schedule_audit_payload_serialization import END, START, _service

    async with async_session() as db:
        group = models.Group(name="AUD360-PARENT")
        other = models.Group(name="AUD360-PARENT-NEXT")
        db.add_all([group, other])
        await db.commit()
        service = _service(db)
        missing = uuid.uuid4()
        data = schemas.ScheduleCreate(
            group_id=missing,
            subject="Physics",
            teacher="Dr. Curie",
            room="101",
            weekday="monday",
            start_time=START,
            end_time=END,
        )
        with patch(
            "app.repositories.schedule_repository.schedule_cache.get",
            new=AsyncMock(
                side_effect=AssertionError("Parent authorization must not read cache")
            ),
        ):
            with pytest.raises(EntityNotFound):
                await service.create_schedule(data)
            assert not (await db.execute(select(models.Schedule))).scalars().all()
            assert not (await db.execute(select(StoredEvent))).scalars().all()
            created = await service.create_schedule(
                data.model_copy(update={"group_id": group.id})
            )
            with pytest.raises(EntityNotFound):
                await service.update_schedule(
                    created.id, ScheduleUpdate(group_id=missing)
                )
            persisted = await service.repo.get_for_update_fresh(created.id)
            assert persisted.group_id == group.id
            updated = await service.update_schedule(
                created.id, ScheduleUpdate(group_id=other.id)
            )
            assert updated.group_id == other.id
            unchanged = await service.update_schedule(
                created.id, ScheduleUpdate(room="202")
            )
            assert unchanged.group_id == other.id
            assert unchanged.room == "202"


@pytest.mark.asyncio
async def test_lookup_error_propagates_without_write_or_context_change():
    uow = _uow()
    current = _schedule(uuid.uuid4())
    uow.groups.get.side_effect = RuntimeError("parent lookup unavailable")
    service = ScheduleService(uow, AsyncMock())
    before = (tenant_id_ctx.get(), bypass_rls_ctx.get())
    with pytest.raises(RuntimeError, match="parent lookup unavailable"):
        await service.create_schedule(current)
    uow.schedules.create.assert_not_awaited()
    uow.commit.assert_not_awaited()
    assert before == (tenant_id_ctx.get(), bypass_rls_ctx.get())


@pytest.mark.asyncio
async def test_existing_service_read_group_and_conflict_contracts():
    from app.core.exceptions.domain import BusinessRuleViolation

    uow = _uow()
    current = _schedule(uuid.uuid4())
    optimizer = AsyncMock()
    optimizer.detect_conflicts.return_value = [object()]
    service = ScheduleService(uow, optimizer)
    with pytest.raises(BusinessRuleViolation):
        await service.create_schedule(current)
    uow.schedules.create.assert_not_awaited()
    uow.schedules.get_for_update_fresh.return_value = None
    with pytest.raises(ValueError):
        await service.update_schedule(current.id, ScheduleUpdate())
    assert (
        await service.get_schedule(current.group_id)
        is uow.schedules.get_by_group.return_value
    )
    assert await service.get_by_id(current.id) is uow.schedules.get.return_value
    assert await service.list_groups() is uow.groups.list_groups.return_value
    assert await service.create_group(current) is uow.groups.create.return_value
    uow.commit.assert_awaited_once_with()
