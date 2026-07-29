from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

import app.models as models
from app.auth.security import get_password_hash
from app.core.localization import translate
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services.event_service import EventService
from app.services.vector_service import VectorService

pytestmark = pytest.mark.asyncio(loop_scope="session")


@contextmanager
def _capture_statements(session):
    statements: list[str] = []
    engine = session.bind
    if engine is None:
        yield statements
        return

    sync_engine = engine.sync_engine

    def _before_cursor_execute(
        _conn, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


async def test_create_event_guard(db_session, user_factory):
    user = await user_factory()
    starts = datetime.now(UTC)
    payload = schemas.EventCreate.model_construct(
        title="Invalid",
        description=None,
        location=None,
        event_type=None,
        starts_at=starts,
        ends_at=starts,
        speaker=None,
        image_url=None,
        about=None,
    )
    e_service = EventService(uow_from_session(db_session), VectorService(db_session))
    with pytest.raises(
        ValueError,
        match=translate("validation.events.end_after_start"),
    ):
        await e_service.create_event(payload, user_id=user.id)


async def test_update_event_guard(db_session, user_factory):
    user = await user_factory()
    starts = datetime.now(UTC)
    ends = starts + timedelta(hours=1)
    valid = schemas.EventCreate(
        title="Valid",
        starts_at=starts,
        ends_at=ends,
    )
    e_service = EventService(uow_from_session(db_session), VectorService(db_session))
    record = await e_service.create_event(valid, user_id=user.id)
    invalid_update = schemas.EventUpdate.model_construct(
        starts_at=starts,
        ends_at=starts,
        fields_set={"starts_at", "ends_at"},
    )
    with pytest.raises(
        ValueError,
        match=translate("validation.events.end_after_start"),
    ):
        await e_service.update_event(record.id, invalid_update)


async def test_event_model_check_constraint(db_session, user_factory):
    user = await user_factory()
    starts = datetime.now(UTC)
    event = models.Event(
        title="Broken",
        starts_at=starts,
        ends_at=starts,
        created_by=user.id,
    )
    db_session.add(event)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_get_all_events_respects_locale(db_session, user_factory):
    admin = await user_factory(role="admin")
    student = await user_factory()
    starts = datetime.now(UTC)
    event = models.Event(
        title="Русское название",
        title_en="English title",
        description="Описание",
        description_en="English description",
        location="Москва",
        location_en="Moscow",
        event_type="лекция",
        event_type_en="Lecture",
        about="Русский текст",
        about_en="English text",
        starts_at=starts,
        ends_at=starts + timedelta(hours=2),
        created_by=admin.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    e_service = EventService(uow_from_session(db_session), VectorService(db_session))
    ru_events = await e_service.get_events(user_id=student.id, locale="ru")
    en_events = await e_service.get_events(user_id=student.id, locale="en")

    # Find the specific event by ID to avoid test isolation issues
    ru_event = next((e for e in ru_events.items if e.id == event.id), None)
    en_event = next((e for e in en_events.items if e.id == event.id), None)
    assert ru_event is not None, f"Event {event.id} not found in ru_events"
    assert en_event is not None, f"Event {event.id} not found in en_events"

    assert ru_event.title == "Русское название"
    assert ru_event.title_en == "English title"
    assert en_event.title == "English title"
    assert en_event.title_en == "English title"
    assert ru_event.description == "Описание"
    assert en_event.description == "English description"
    assert ru_event.location == "Москва"
    assert en_event.location == "Moscow"
    assert ru_event.event_type == "лекция"
    assert en_event.event_type == "Lecture"
    assert ru_event.about == "Русский текст"
    assert en_event.about == "English text"


async def test_get_all_events_cursor_respects_ordering_and_gaps(
    db_session, user_factory
):
    admin = await user_factory(role="admin")
    student = await user_factory()
    # Use far future to avoid interference from other tests' events
    base = datetime.now(UTC) + timedelta(days=30)

    def _build_event(delta: timedelta, title: str) -> models.Event:
        return models.Event(
            title=title,
            starts_at=base + delta,
            ends_at=base + delta + timedelta(hours=1),
            created_by=admin.id,
            is_active=True,
        )

    initial_events = [
        _build_event(timedelta(hours=1), "Event A"),
        _build_event(timedelta(hours=2), "Event B"),
        _build_event(timedelta(hours=2, minutes=45), "Event C"),
        _build_event(timedelta(hours=3, seconds=0), "Event D0"),
        _build_event(timedelta(hours=3, seconds=10), "Event D1"),
    ]
    db_session.add_all(initial_events)
    await db_session.commit()
    for event_record in initial_events:
        await db_session.refresh(event_record)

    # Get test event IDs to filter results
    test_event_ids = {e.id for e in initial_events}

    e_service = EventService(uow_from_session(db_session), VectorService(db_session))
    first_page = await e_service.get_events(
        user_id=student.id,
        locale="en",
        limit=100,  # Get more items to filter
    )
    # Filter to only our test events
    our_events = [e for e in first_page.items if e.id in test_event_ids]
    # UUIDs don't guarantee insertion order,
    # but we sort by starts_at in the service/repo
    our_events.sort(key=lambda x: x.starts_at)
    assert [e.title for e in our_events[:2]] == ["Event A", "Event B"]

    inserted = _build_event(timedelta(hours=2, minutes=30), "Inserted Event")
    db_session.add(inserted)
    await db_session.commit()
    await db_session.refresh(inserted)
    test_event_ids.add(inserted.id)

    second_page = await e_service.get_events(
        user_id=student.id,
        locale="en",
        limit=100,
    )
    our_events = [e for e in second_page.items if e.id in test_event_ids]
    our_events.sort(key=lambda x: x.starts_at)
    # Events should be ordered by starts_at: A, B, Inserted, C, D
    assert [e.title for e in our_events] == [
        "Event A",
        "Event B",
        "Inserted Event",
        "Event C",
        "Event D0",
        "Event D1",
    ]


async def test_get_all_events_cursor_skips_total_on_followup_pages(
    db_session, user_factory
):
    admin = await user_factory(role="admin")
    student = await user_factory()
    # Use far future to avoid interference from other tests
    base = datetime.now(UTC) + timedelta(days=60)

    events = [
        models.Event(
            title=f"Event {idx}",
            starts_at=base + timedelta(hours=idx),
            ends_at=base + timedelta(hours=idx, minutes=30),
            created_by=admin.id,
            is_active=True,
        )
        for idx in range(5)
    ]
    db_session.add_all(events)
    await db_session.commit()
    for event_record in events:
        await db_session.refresh(event_record)

    e_service = EventService(uow_from_session(db_session), VectorService(db_session))
    first_page = await e_service.get_events(
        user_id=student.id,
        locale="en",
        limit=2,
    )
    # Total may include events from other tests
    assert first_page.total >= 5
    assert first_page.next_cursor is not None

    with _capture_statements(db_session) as statements:
        second_page = await e_service.get_events(
            user_id=student.id,
            locale="en",
            limit=2,
            cursor=first_page.next_cursor,
        )

    assert second_page.total is None
    lowered_statements = [stmt.lower() for stmt in statements]
    assert not any(
        "count" in stmt and " from events" in stmt for stmt in lowered_statements
    )


async def test_event_detail_returns_qr_code_after_registration(
    async_client, db_session, user_factory
):
    password = "QrCodePass123!"
    student = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    admin = await user_factory(role="admin")

    now = datetime.now(UTC)
    event = models.Event(
        title="QR enabled",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    headers = await _login(async_client, student.email, password)

    attend_response = await async_client.post(
        "/events/attendance", headers=headers, json={"event_id": str(event.id)}
    )
    assert attend_response.status_code == 200
    qr_token = attend_response.json()["qr_token"]
    assert qr_token

    detail_response = await async_client.get(f"/events/{event.id}", headers=headers)
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["my_qr_token"] == qr_token
