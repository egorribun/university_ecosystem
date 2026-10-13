"""Prove schedule conflict checks serialize and read uncached PostgreSQL state."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models as models
from app.core.cache import schedule_cache
from app.core.exceptions.domain import BusinessRuleViolation
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.unit_of_work import uow_from_session
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from app.services.schedule_optimizer import ScheduleOptimizerService
from app.services.schedule_service import ScheduleService
from scripts import seed_demo_data

_RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN_INTEGRATION_TESTS,
        reason="Set RUN_INTEGRATION_TESTS=1 for PostgreSQL concurrency coverage",
    ),
]


def _install_local_schedule_cache(monkeypatch) -> tuple[dict[str, Any], list[str]]:
    cache: dict[str, Any] = {}
    reads: list[str] = []

    async def get(key: str) -> Any:
        reads.append(key)
        return cache.get(key)

    async def set_value(key: str, value: Any) -> None:
        cache[key] = value

    async def delete(key: str) -> None:
        cache.pop(key, None)

    monkeypatch.setattr(schedule_cache, "get", get)
    monkeypatch.setattr(schedule_cache, "set", set_value)
    monkeypatch.setattr(schedule_cache, "delete", delete)
    return cache, reads


async def _wait_for_advisory_wait(observer: AsyncSession, pid: int) -> None:
    for _ in range(250):
        waiting = await observer.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks "
                "WHERE locktype = 'advisory' AND NOT granted AND pid = :pid)"
            ),
            {"pid": pid},
        )
        if waiting:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"PostgreSQL backend {pid} never waited for the schedule lock")


class _RendezvousOptimizer:
    """Let the pre-fix check-then-write requests reach conflict detection together."""

    def __init__(self) -> None:
        self._optimizer = ScheduleOptimizerService()
        self._both_checks_started = asyncio.Event()
        self.first_check_started = asyncio.Event()
        self._call_count = 0
        self._count_lock = asyncio.Lock()

    async def detect_conflicts(self, target, existing):
        async with self._count_lock:
            self._call_count += 1
            if self._call_count == 1:
                self.first_check_started.set()
            if self._call_count == 2:
                self._both_checks_started.set()

        # Under the transaction lock only the first writer can reach this point.
        # The finite timeout lets it commit so the second writer can verify the
        # newly committed schedule instead of deadlocking the regression itself.
        try:
            await asyncio.wait_for(self._both_checks_started.wait(), timeout=1.5)
        except TimeoutError:
            pass
        return await self._optimizer.detect_conflicts(target, existing)


def _schedule_row(
    group_id: UUID,
    *,
    weekday: str,
    start_time: datetime,
    teacher: str | None = None,
) -> models.Schedule:
    return models.Schedule(
        group_id=group_id,
        subject="Concurrent schedule regression",
        teacher=teacher,
        weekday=weekday,
        start_time=start_time,
        end_time=start_time + timedelta(hours=1),
        parity="both",
    )


async def _run_create(
    session_factory: async_sessionmaker[AsyncSession],
    optimizer: _RendezvousOptimizer,
    group_id: UUID,
    teacher: str,
) -> str:
    async with session_factory() as session:
        service = ScheduleService(uow_from_session(session), optimizer)
        start = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
        try:
            await service.create_schedule(
                ScheduleCreate(
                    group_id=group_id,
                    subject="Concurrent lecture",
                    teacher=teacher,
                    weekday="monday",
                    start_time=start,
                    end_time=start + timedelta(hours=1),
                    parity="both",
                )
            )
        except BusinessRuleViolation:
            return "conflict"
        return "created"


async def _run_update(
    session_factory: async_sessionmaker[AsyncSession],
    optimizer: _RendezvousOptimizer,
    schedule_id: UUID,
    data: ScheduleUpdate | None = None,
    prefetched_event: asyncio.Event | None = None,
) -> str:
    async with session_factory() as session:
        service = ScheduleService(uow_from_session(session), optimizer)
        # Match UpdateScheduleHandler's ownership pre-read. The mutation must
        # refresh this identity-mapped DTO after waiting for the transaction lock.
        await service.get_by_id(schedule_id)
        if prefetched_event is not None:
            prefetched_event.set()
        start = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
        try:
            await service.update_schedule(
                schedule_id,
                data
                or ScheduleUpdate(
                    weekday="wednesday",
                    start_time=start,
                    end_time=start + timedelta(hours=1),
                ),
            )
        except BusinessRuleViolation:
            return "conflict"
        return "updated"


@pytest.mark.asyncio
async def test_concurrent_creates_recheck_teacher_conflict_after_transaction_lock(
    db_session, monkeypatch
):
    assert db_session.bind.dialect.name == "postgresql"
    _install_local_schedule_cache(monkeypatch)
    groups = [
        models.Group(name=f"aud228-create-{uuid4().hex}"),
        models.Group(name=f"aud228-create-{uuid4().hex}"),
    ]
    db_session.add_all(groups)
    await db_session.flush()
    group_ids = [group.id for group in groups]
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    optimizer = _RendezvousOptimizer()
    teacher = f"AUD228-{uuid4().hex}"
    try:
        with patch("app.services.audit_service.get_secure_audit_service") as factory:
            audit = AsyncMock()
            factory.return_value.record_domain_event = audit
            outcomes = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        _run_create(session_factory, optimizer, group_id, teacher)
                        for group_id in group_ids
                    )
                ),
                timeout=10,
            )

        assert sorted(outcomes) == ["conflict", "created"]
        async with session_factory() as reader:
            stored = list(
                (
                    await reader.scalars(
                        select(models.Schedule).where(
                            models.Schedule.teacher == teacher
                        )
                    )
                ).all()
            )
        assert len(stored) == 1
        assert stored[0].group_id in set(group_ids)
    finally:
        await db_session.rollback()
        await db_session.execute(
            delete(models.Group).where(models.Group.id.in_(group_ids))
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_concurrent_updates_recheck_group_conflict_after_commit(
    db_session, monkeypatch
):
    assert db_session.bind.dialect.name == "postgresql"
    _install_local_schedule_cache(monkeypatch)
    group = models.Group(name=f"aud228-update-{uuid4().hex}")
    db_session.add(group)
    await db_session.flush()
    monday = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    tuesday = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    rows = [
        _schedule_row(group.id, weekday="monday", start_time=monday),
        _schedule_row(group.id, weekday="tuesday", start_time=tuesday),
    ]
    db_session.add_all(rows)
    await db_session.flush()
    group_id = group.id
    schedule_ids = [row.id for row in rows]
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    optimizer = _RendezvousOptimizer()
    try:
        with patch("app.services.audit_service.get_secure_audit_service") as factory:
            factory.return_value.record_domain_event = AsyncMock()
            outcomes = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        _run_update(session_factory, optimizer, schedule_id)
                        for schedule_id in schedule_ids
                    )
                ),
                timeout=10,
            )

        assert sorted(outcomes) == ["conflict", "updated"]
        async with session_factory() as reader:
            stored = list(
                (
                    await reader.scalars(
                        select(models.Schedule).where(
                            models.Schedule.id.in_(schedule_ids)
                        )
                    )
                ).all()
            )
        assert len(stored) == 2
        assert sum(row.weekday == "wednesday" for row in stored) == 1
        assert all(row.group_id == group_id for row in stored)
    finally:
        await db_session.rollback()
        await db_session.execute(
            delete(models.Group).where(models.Group.id == group_id)
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_update_refreshes_prefetched_row_after_waiting_for_lock(
    db_session, monkeypatch
):
    assert db_session.bind.dialect.name == "postgresql"
    _install_local_schedule_cache(monkeypatch)
    groups = [
        models.Group(name=f"aud228-refresh-{uuid4().hex}"),
        models.Group(name=f"aud228-refresh-{uuid4().hex}"),
    ]
    db_session.add_all(groups)
    await db_session.flush()
    first_group_id, second_group_id = (group.id for group in groups)
    start = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    conflict_start = start + timedelta(hours=1)
    teacher = f"AUD228-refresh-{uuid4().hex}"
    moving = _schedule_row(first_group_id, weekday="monday", start_time=start)
    teacher_conflict = _schedule_row(
        second_group_id,
        weekday="monday",
        start_time=conflict_start,
        teacher=teacher,
    )
    db_session.add_all([moving, teacher_conflict])
    await db_session.flush()
    moving_id = moving.id
    conflict_id = teacher_conflict.id
    group_ids = [first_group_id, second_group_id]
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    optimizer = _RendezvousOptimizer()
    move_time = ScheduleUpdate(
        start_time=conflict_start,
        end_time=conflict_start + timedelta(hours=1),
    )
    assign_teacher = ScheduleUpdate(teacher=teacher)
    try:
        with patch("app.services.audit_service.get_secure_audit_service") as factory:
            factory.return_value.record_domain_event = AsyncMock()
            first = asyncio.create_task(
                _run_update(session_factory, optimizer, moving_id, move_time)
            )
            await asyncio.wait_for(optimizer.first_check_started.wait(), timeout=5)
            second_prefetched = asyncio.Event()
            second = asyncio.create_task(
                _run_update(
                    session_factory,
                    optimizer,
                    moving_id,
                    assign_teacher,
                    second_prefetched,
                )
            )
            await asyncio.wait_for(second_prefetched.wait(), timeout=1)
            outcomes = await asyncio.wait_for(asyncio.gather(first, second), timeout=10)

        assert sorted(outcomes) == ["conflict", "updated"]
        async with session_factory() as reader:
            stored = list(
                (
                    await reader.scalars(
                        select(models.Schedule).where(
                            models.Schedule.id.in_([moving_id, conflict_id])
                        )
                    )
                ).all()
            )
        updated = next(row for row in stored if row.id == moving_id)
        assert updated.start_time == conflict_start
        assert updated.teacher is None
    finally:
        await db_session.rollback()
        await db_session.execute(
            delete(models.Group).where(models.Group.id.in_(group_ids))
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_conflict_ignores_stale_capped_group_cache(
    db_session, monkeypatch
):
    assert db_session.bind.dialect.name == "postgresql"
    _cached, cache_reads = _install_local_schedule_cache(monkeypatch)
    group = models.Group(name=f"aud228-cache-{uuid4().hex}")
    db_session.add(group)
    await db_session.flush()
    group_id = group.id
    monday = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    tuesday = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    db_session.add_all(
        _schedule_row(group_id, weekday="monday", start_time=monday) for _ in range(500)
    )
    await db_session.commit()

    display_rows = await ScheduleRepository(db_session).get_by_group(group_id)
    assert len(display_rows) == 500
    assert cache_reads == []

    # Preserve the capped snapshot a different worker could still hold, then
    # commit a conflicting row beyond its display cap. Reads and write
    # validation must bypass that now-stale process-local view.
    _cached[f"schedule:group:{group_id}"] = [
        row.model_dump(mode="json") for row in display_rows
    ]
    db_session.add(_schedule_row(group_id, weekday="tuesday", start_time=tuesday))
    await db_session.commit()
    service = ScheduleService(uow_from_session(db_session), ScheduleOptimizerService())
    try:
        with patch("app.services.audit_service.get_secure_audit_service") as factory:
            factory.return_value.record_domain_event = AsyncMock()
            with pytest.raises(BusinessRuleViolation):
                await service.create_schedule(
                    ScheduleCreate(
                        group_id=group_id,
                        subject="Must not be inserted",
                        weekday="tuesday",
                        start_time=tuesday,
                        end_time=tuesday + timedelta(hours=1),
                        parity="both",
                    )
                )
        assert cache_reads == []
    finally:
        await db_session.rollback()
        await db_session.execute(
            delete(models.Group).where(models.Group.id == group_id)
        )
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(("finish", "expected_count"), [("commit", 1), ("rollback", 0)])
async def test_schedule_lock_waiter_observes_commit_or_rollback(
    db_session, finish: str, expected_count: int
):
    assert db_session.bind.dialect.name == "postgresql"
    group = models.Group(name=f"aud228-boundary-{uuid4().hex}")
    db_session.add(group)
    await db_session.flush()
    group_id = group.id
    teacher = f"AUD228-boundary-{uuid4().hex}"
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    holder = session_factory()
    waiter_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    waiter_task: asyncio.Task[int] | None = None

    async def wait_for_candidate() -> int:
        async with session_factory() as waiter:
            pid = int(await waiter.scalar(text("SELECT pg_backend_pid()")))
            waiter_pid.set_result(pid)
            repository = ScheduleRepository(waiter)
            await repository.lock_schedule_mutations()
            return len(await repository.get_conflict_candidates(group_id, teacher))

    try:
        await ScheduleRepository(holder).lock_schedule_mutations()
        holder.add(
            _schedule_row(
                group_id,
                weekday="monday",
                start_time=datetime(2026, 10, 12, 9, 0, tzinfo=UTC),
                teacher=teacher,
            )
        )
        await holder.flush()
        waiter_task = asyncio.create_task(wait_for_candidate())
        pid = await asyncio.wait_for(waiter_pid, timeout=5)
        await _wait_for_advisory_wait(db_session, pid)

        if finish == "commit":
            await holder.commit()
        else:
            await holder.rollback()

        assert await asyncio.wait_for(waiter_task, timeout=5) == expected_count
    finally:
        await holder.rollback()
        await holder.close()
        if waiter_task is not None and not waiter_task.done():
            waiter_task.cancel()
            await asyncio.gather(waiter_task, return_exceptions=True)
        await db_session.rollback()
        await db_session.execute(
            delete(models.Group).where(models.Group.id == group_id)
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_seed_writer_holds_shared_lock_and_api_rechecks_after_seed_commit(
    db_session, monkeypatch
):
    assert db_session.bind.dialect.name == "postgresql"
    _install_local_schedule_cache(monkeypatch)
    seed_group = await seed_demo_data.seed_group(db_session)
    seed_user = await seed_demo_data.seed_user(db_session, seed_group)
    api_group = models.Group(name=f"aud228-seed-api-{uuid4().hex}")
    db_session.add(api_group)
    await db_session.commit()
    seed_group_id = seed_group.id
    seed_user_id = seed_user.id
    api_group_id = api_group.id
    first = seed_demo_data.SCHEDULE_DATA[0]
    weekday, pair_number, _subject, teacher, _room, _lesson_type, _parity = first
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE[weekday], pair_number)

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    seed_checked = asyncio.Event()
    release_seed = asyncio.Event()
    seed_session: dict[str, AsyncSession] = {}
    original_candidates = ScheduleRepository.get_conflict_candidates

    async def pause_seed_after_candidate_read(repository, group_id, teachers):
        candidates = await original_candidates(repository, group_id, teachers)
        if repository.db is seed_session.get("session"):
            seed_checked.set()
            await release_seed.wait()
        return candidates

    monkeypatch.setattr(
        ScheduleRepository,
        "get_conflict_candidates",
        pause_seed_after_candidate_read,
    )
    api_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def run_seed() -> str:
        async with session_factory() as session:
            seed_session["session"] = session
            group = await session.get(models.Group, seed_group_id)
            user = await session.get(seed_demo_data.User, seed_user_id)
            assert group is not None and user is not None
            await seed_demo_data.seed_schedule(session, group, user)
            await session.commit()
            return "seeded"

    async def run_api() -> str:
        async with session_factory() as session:
            api_pid.set_result(
                int(await session.scalar(text("SELECT pg_backend_pid()")))
            )
            service = ScheduleService(
                uow_from_session(session), ScheduleOptimizerService()
            )
            data = ScheduleCreate(
                group_id=api_group_id,
                subject="Concurrent API lesson",
                teacher=teacher,
                weekday=weekday,
                start_time=start,
                end_time=end,
                parity="both",
            )
            try:
                await service.create_schedule(data)
            except BusinessRuleViolation:
                return "conflict"
            return "created"

    seed_task: asyncio.Task[str] | None = None
    api_task: asyncio.Task[str] | None = None
    try:
        seed_task = asyncio.create_task(run_seed())
        await asyncio.wait_for(seed_checked.wait(), timeout=5)
        api_task = asyncio.create_task(run_api())
        pid = await asyncio.wait_for(api_pid, timeout=5)
        await _wait_for_advisory_wait(db_session, pid)
        release_seed.set()

        assert await asyncio.wait_for(seed_task, timeout=10) == "seeded"
        assert await asyncio.wait_for(api_task, timeout=10) == "conflict"
        assert await db_session.scalar(
            select(func.count())
            .select_from(models.Schedule)
            .where(models.Schedule.group_id == seed_group_id)
        ) == len(seed_demo_data.SCHEDULE_DATA)
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(models.Schedule)
                .where(
                    models.Schedule.group_id == api_group_id,
                    models.Schedule.teacher == teacher,
                    models.Schedule.weekday == weekday,
                    models.Schedule.start_time == start,
                )
            )
            == 0
        )
    finally:
        release_seed.set()
        for task in (seed_task, api_task):
            if task is not None and not task.done():
                task.cancel()
        pending = [task for task in (seed_task, api_task) if task is not None]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await db_session.rollback()
        await db_session.execute(
            delete(models.Group).where(
                models.Group.id.in_([seed_group_id, api_group_id])
            )
        )
        await db_session.commit()
