"""Registration rechecks current event state after its first unlocked read."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.auth.security import get_password_hash
from app.core.database import async_session
from app.models import Event, EventAttendance
from app.repositories.event_repository import EventRepository
from app.repositories.unit_of_work import uow_from_session
from app.schemas.events import EventAttendanceCreate
from app.services.event_service import EventService
from app.services.vector_service import VectorService
from tests.test_event_attendance_api import _login


@pytest.mark.parametrize("closure", ["hidden", "ended"])
async def test_registration_rechecks_cached_event_after_concurrent_closure(
    db_session, user_factory, closure
):
    user = await user_factory()
    now = datetime.now(UTC)
    event = Event(
        title="Synthetic stale registration probe",
        starts_at=now - timedelta(hours=2),
        ends_at=now + timedelta(hours=2),
        created_by=user.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    event_id, user_id = event.id, user.id
    # This is the first db.get performed by the HTTP attendance handler.
    cached = await db_session.get(Event, event_id)
    assert cached is event and cached.is_active

    changes = (
        {"is_active": False}
        if closure == "hidden"
        else {"ends_at": now - timedelta(hours=1)}
    )
    async with async_session() as organizer:
        await organizer.execute(
            update(Event).where(Event.id == event_id).values(**changes)
        )
        await organizer.commit()

    service = EventService(uow_from_session(db_session), cast(VectorService, None))
    with pytest.raises(ValueError, match="registration_closed"):
        await service.register_attendance(
            EventAttendanceCreate(event_id=event_id), user_id
        )
    async with async_session() as observer:
        current = await observer.get(Event, event_id)
        assert current is not None
        if closure == "hidden":
            assert current.is_active is False
        else:
            end = current.ends_at.replace(tzinfo=UTC)
            assert end < datetime.now(UTC)
        count = await observer.scalar(
            select(func.count())
            .select_from(EventAttendance)
            .where(
                EventAttendance.event_id == event_id,
                EventAttendance.user_id == user_id,
            )
        )
        assert count == 0


@pytest.mark.parametrize("closure", ["hidden", "ended"])
async def test_fresh_session_rejects_the_same_closed_event(
    db_session, user_factory, closure
):
    user = await user_factory()
    now = datetime.now(UTC)
    event = Event(
        title="Synthetic fresh registration control",
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1)
        if closure == "ended"
        else now + timedelta(hours=1),
        created_by=user.id,
        is_active=closure != "hidden",
    )
    db_session.add(event)
    await db_session.commit()
    event_id, user_id = event.id, user.id
    async with async_session() as fresh:
        service = EventService(uow_from_session(fresh), cast(VectorService, None))
        with pytest.raises(ValueError, match="registration_closed"):
            await service.register_attendance(
                EventAttendanceCreate(event_id=event_id), user_id
            )


@pytest.mark.parametrize("closure", ["hidden", "ended"])
async def test_http_rejects_registration_after_concurrent_closure(
    async_client, db_session, user_factory, monkeypatch, closure
):
    password = f"{secrets.token_urlsafe(24)}aA1!"
    student = await user_factory(hashed_password=await get_password_hash(password))
    now = datetime.now(UTC)
    event = Event(
        title="Synthetic HTTP interleaving proof",
        starts_at=now - timedelta(hours=2),
        ends_at=now + timedelta(hours=2),
        created_by=student.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    event_id, student_id = event.id, student.id
    headers = await _login(async_client, student.email, password)
    original_lock = EventRepository.get_for_registration
    seen = []

    async def close_before_lock(repo, requested_id):
        # The endpoint has already read and checked this exact row.
        cached = next(
            row
            for row in repo.db.identity_map.values()
            if isinstance(row, Event) and row.id == event_id
        )
        assert cached.is_active
        changes = (
            {"is_active": False}
            if closure == "hidden"
            else {"ends_at": now - timedelta(hours=1)}
        )
        async with async_session() as organizer:
            await organizer.execute(
                update(Event).where(Event.id == event_id).values(**changes)
            )
            await organizer.commit()
        locked = await original_lock(repo, requested_id)
        assert locked is cached
        seen.append(locked.id)
        return locked

    monkeypatch.setattr(EventRepository, "get_for_registration", close_before_lock)
    response = await async_client.post(
        "/events/attendance", headers=headers, json={"event_id": str(event_id)}
    )
    assert response.status_code == 409, response.text
    assert seen == [event_id]
    async with async_session() as observer:
        current = await observer.get(Event, event_id)
        assert current is not None
        if closure == "hidden":
            assert not current.is_active
        else:
            assert current.ends_at.replace(tzinfo=UTC) < datetime.now(UTC)
        assert (
            await observer.scalar(
                select(func.count())
                .select_from(EventAttendance)
                .where(
                    EventAttendance.event_id == event_id,
                    EventAttendance.user_id == student_id,
                )
            )
            == 0
        )


@pytest.mark.parametrize("commit", [False, True])
async def test_registration_lock_keeps_pending_edits_and_transaction_ownership(
    db_session, user_factory, commit
):
    user = await user_factory()
    now = datetime.now(UTC)
    event = Event(
        title="Original title",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    event_id = event.id
    event.title = "Pending title"
    event.is_active = False
    assert db_session.autoflush

    locked = await EventRepository(db_session).get_for_registration(event_id)
    assert locked is event
    assert locked.title == "Pending title"
    assert locked.is_active is False
    # The existing query autoflushes, but locking must not commit the edit.
    async with async_session() as observer:
        saved = await observer.get(Event, event_id)
        assert saved is not None
        assert saved.title == "Original title"
        assert saved.is_active is True
    if commit:
        await db_session.commit()
    else:
        await db_session.rollback()
    async with async_session() as observer:
        saved = await observer.get(Event, event_id)
        assert saved is not None
        assert saved.title == ("Pending title" if commit else "Original title")
        assert saved.is_active is not commit


async def test_registration_lock_does_not_erase_invalid_pending_changes(
    db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    event = Event(
        title="Invalid pending edit",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add(event)
    await db_session.commit()
    event_id = event.id
    event.ends_at = now - timedelta(hours=1)
    # Autoflush retains the existing constraint failure instead of refreshing
    # away the invalid edit and making the operation appear successful.
    with pytest.raises(IntegrityError):
        await EventRepository(db_session).get_for_registration(event_id)
    await db_session.rollback()
    async with async_session() as observer:
        saved = await observer.get(Event, event_id)
        assert saved is not None
        assert saved.ends_at.replace(tzinfo=UTC) == now + timedelta(hours=1)


async def test_only_registration_lookup_has_refresh_and_the_same_row_lock(db_session):
    statements = []

    def collect(execute_state):
        if execute_state.is_select:
            statements.append(execute_state.statement)

    sqlalchemy_event.listen(db_session.sync_session, "do_orm_execute", collect)
    try:
        repository = EventRepository(db_session)
        missing_id = uuid4()
        assert await repository.get(missing_id) is None
        assert await repository.get_for_registration(missing_id) is None
    finally:
        sqlalchemy_event.remove(db_session.sync_session, "do_orm_execute", collect)

    assert len(statements) == 2
    ordinary, locked = statements
    assert "FOR UPDATE" not in str(ordinary.compile(dialect=postgresql.dialect()))
    locked_sql = str(locked.compile(dialect=postgresql.dialect()))
    assert locked_sql.endswith(" FOR UPDATE")
    assert "NOWAIT" not in locked_sql
    assert "SKIP LOCKED" not in locked_sql
    assert "FOR SHARE" not in locked_sql
    assert locked.compile().params == {"id_1": missing_id}
    assert not ordinary.get_execution_options().get("populate_existing", False)
    assert locked.get_execution_options()["populate_existing"] is True
    assert "autoflush" not in locked.get_execution_options()
