import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from prometheus_client import CollectorRegistry

import app.models as models
from app.api import events
from app.auth.security import get_password_hash
from app.core import observability
from app.services import attendance_tokens, notification_queue

# Skip marker for tests that require PostgreSQL full-text search
_database_url = os.environ.get("DATABASE_URL", "")
_is_postgresql = _database_url.startswith("postgresql")
requires_postgresql = pytest.mark.skipif(
    not _is_postgresql,
    reason="Test requires PostgreSQL (uses pg_attribute or full-text search)",
)


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


@pytest.mark.asyncio
async def test_events_localization(async_client, db_session, user_factory):
    password = "TestEvent123!"
    hashed = await get_password_hash(password)
    admin = await user_factory(role="admin")
    student = await user_factory(hashed_password=hashed, is_active=True)

    now = datetime.now(UTC)
    primary = models.Event(
        title="Русское событие",
        description="Описание по-русски",
        location="Москва",
        event_type="лекция",
        about="Подробности",
        title_en="English Event",
        description_en="Description in English",
        location_en="Moscow",
        event_type_en="Lecture",
        about_en="More details",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=2),
        created_by=admin.id,
        is_active=True,
    )
    fallback = models.Event(
        title="Только русский",
        description="Без перевода",
        location="Санкт-Петербург",
        event_type="встреча",
        about="Описание только на русском",
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=3),
        created_by=admin.id,
        is_active=True,
    )

    db_session.add_all([primary, fallback])
    await db_session.commit()
    await db_session.refresh(primary)
    await db_session.refresh(fallback)

    headers = await _login(async_client, student.email, password)

    response_en = await async_client.get(
        "/events",
        headers={**headers, "Accept-Language": "en"},
    )
    assert response_en.status_code == 200
    assert response_en.headers.get("Cache-Control") == "private, max-age=180"
    assert response_en.headers.get("Content-Language") == "en"
    vary_en = response_en.headers.get("Vary", "")
    assert any(
        value.strip().lower() == "accept-language"
        for value in vary_en.split(",")
        if value.strip()
    )
    etag_en = response_en.headers.get("ETag")
    assert etag_en
    data_en = response_en.json()
    assert data_en["total"] == 2
    assert data_en["limit"] >= len(data_en["items"])
    payload_en = {item["id"]: item for item in data_en["items"]}

    assert payload_en[str(primary.id)]["title"] == "English Event"
    assert payload_en[str(primary.id)]["description"] == "Description in English"
    assert payload_en[str(primary.id)]["location"] == "Moscow"
    assert payload_en[str(primary.id)]["event_type"] == "Lecture"
    assert payload_en[str(primary.id)]["about"] == "More details"
    assert payload_en[str(primary.id)]["title_en"] == "English Event"
    assert payload_en[str(primary.id)]["description_en"] == "Description in English"

    assert payload_en[str(fallback.id)]["title"] == "Только русский"
    assert payload_en[str(fallback.id)]["description"] == "Без перевода"
    assert payload_en[str(fallback.id)]["location"] == "Санкт-Петербург"
    assert payload_en[str(fallback.id)]["event_type"] == "встреча"
    assert payload_en[str(fallback.id)]["about"] == "Описание только на русском"
    assert payload_en[str(fallback.id)]["title_en"] is None

    response_ru = await async_client.get(
        "/events",
        headers={**headers, "Accept-Language": "ru"},
    )
    assert response_ru.status_code == 200
    assert response_ru.headers.get("Cache-Control") == "private, max-age=180"
    assert response_ru.headers.get("Content-Language") == "ru"
    vary_ru = response_ru.headers.get("Vary", "")
    assert any(
        value.strip().lower() == "accept-language"
        for value in vary_ru.split(",")
        if value.strip()
    )
    assert response_ru.headers.get("ETag")
    data_ru = response_ru.json()
    assert data_ru["total"] == 2
    assert data_ru["cursor"] is None
    payload_ru = {item["id"]: item for item in data_ru["items"]}

    assert payload_ru[str(primary.id)]["title"] == "Русское событие"
    assert payload_ru[str(primary.id)]["description"] == "Описание по-русски"
    assert payload_ru[str(primary.id)]["location"] == "Москва"
    assert payload_ru[str(primary.id)]["event_type"] == "лекция"
    assert payload_ru[str(primary.id)]["about"] == "Подробности"
    assert payload_ru[str(fallback.id)]["title"] == "Только русский"
    assert payload_ru[str(fallback.id)]["description"] == "Без перевода"


@pytest.mark.asyncio
async def test_create_event_records_enqueue_failure(
    async_client, db_session, user_factory, monkeypatch
):
    registry = CollectorRegistry()
    metrics = observability.reinitialize_notification_queue_metrics(registry=registry)
    notification_queue._queue_metrics = metrics

    password = "TeacherPass123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )

    headers = await _login(async_client, teacher.email, password)

    def _failing_add_task(self, func, *args, **kwargs):
        raise RuntimeError("notification queue unavailable")

    monkeypatch.setattr(events.BackgroundTasks, "add_task", _failing_add_task)

    now = datetime.now(UTC)
    payload = {
        "title": "Queue Failure",
        "description": "Test enqueue failure handling",
        "starts_at": (now + timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=1, hours=1)).isoformat(),
    }

    response = await async_client.post("/events", headers=headers, json=payload)
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body["title"] == "Queue Failure"

    counter_value = metrics.enqueue_failures_total.labels(kind="event")._value.get()
    assert counter_value == pytest.approx(1.0)

    import uuid

    stored = await db_session.get(models.Event, uuid.UUID(body["id"]))
    assert stored is not None


@pytest.mark.asyncio
async def test_events_etag_and_not_modified(
    async_client, db_session, user_factory, fake_cache
):
    await events.events_cache_version.reset(fake_cache)
    assert fake_cache is not None
    password = "TestEvent456!"
    hashed = await get_password_hash(password)
    admin = await user_factory(role="admin")
    student = await user_factory(hashed_password=hashed, is_active=True)

    now = datetime.now(UTC)
    event = models.Event(
        title="Test event",
        description="Primary description",
        location="Campus",
        title_en="Test event EN",
        description_en="Primary description EN",
        location_en="Campus EN",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=1),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    secret = attendance_tokens.generate_secret()
    attendance = models.EventAttendance(
        event_id=event.id,
        user_id=student.id,
        qr_secret=secret,
        qr_hmac=attendance_tokens.compute_secret_hmac(secret),
    )
    db_session.add(attendance)
    await db_session.commit()

    headers = await _login(async_client, student.email, password)
    base_headers = {**headers, "Accept-Language": "en"}

    list_response = await async_client.get("/events", headers=base_headers)
    assert list_response.status_code == status.HTTP_200_OK
    list_etag = list_response.headers.get("ETag")
    assert list_etag
    assert list_response.headers.get("Cache-Control") == "private, max-age=180"

    list_not_modified = await async_client.get(
        "/events",
        headers={**base_headers, "If-None-Match": list_etag},
    )
    assert list_not_modified.status_code == status.HTTP_304_NOT_MODIFIED
    assert list_not_modified.headers.get("Content-Language") == "en"
    assert list_not_modified.headers.get("Cache-Control") == "private, max-age=180"
    vary_list = list_not_modified.headers.get("Vary", "")
    assert any(
        value.strip().lower() == "accept-language"
        for value in vary_list.split(",")
        if value.strip()
    )
    assert list_not_modified.headers.get("ETag") == list_etag

    my_response = await async_client.get("/events/my", headers=base_headers)
    assert my_response.status_code == status.HTTP_200_OK
    my_etag = my_response.headers.get("ETag")
    assert my_etag
    assert my_response.headers.get("Cache-Control") == "private, max-age=180"

    my_not_modified = await async_client.get(
        "/events/my",
        headers={**base_headers, "If-None-Match": my_etag},
    )
    assert my_not_modified.status_code == status.HTTP_304_NOT_MODIFIED
    assert my_not_modified.headers.get("Content-Language") == "en"
    assert my_not_modified.headers.get("ETag") == my_etag
    assert my_not_modified.headers.get("Cache-Control") == "private, max-age=180"


@requires_postgresql
@pytest.mark.asyncio
async def test_get_all_events_search_deterministic_order(db_session, user_factory):
    """Test FTS search returns results ordered by relevance then starts_at.

    Uses raw SQL INSERT to ensure PostgreSQL computes GENERATED ALWAYS
    search_vector column, bypassing ORM caching issues.
    """
    from sqlalchemy import text

    admin = await user_factory(role="admin")
    now = datetime.now(UTC)
    shared_phrase = "Symposium"

    import uuid

    # Insert events via raw SQL so PostgreSQL computes search_vector
    insert_sql = text("""
        INSERT INTO events (
            id, title, title_en, description, location,
            starts_at, ends_at, created_by, is_active
        ) VALUES (
            :id, :title, :title_en, :description, :location,
            :starts_at, :ends_at, :created_by, :is_active
        ) RETURNING id
    """)

    events_data = [
        {
            "id": uuid.uuid4(),
            "title": f"{shared_phrase} kickoff",
            "title_en": None,
            "description": "Agenda review",
            "location": "Main campus",
            "starts_at": now + timedelta(days=1, hours=1),
            "ends_at": now + timedelta(days=1, hours=2),
            "created_by": admin.id,
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "title": f"{shared_phrase} planning",
            "title_en": None,
            "description": "Breakout sessions",
            "location": "Main campus",
            "starts_at": now + timedelta(days=1, hours=2),
            "ends_at": now + timedelta(days=1, hours=3),
            "created_by": admin.id,
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "title": "Обсуждение",
            "title_en": f"{shared_phrase} recap",
            "description": "Post-event debrief",
            "location": "Satellite hall",
            "starts_at": now + timedelta(days=2),
            "ends_at": now + timedelta(days=2, hours=2),
            "created_by": admin.id,
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "title": "Another meetup",
            "title_en": None,
            "description": "Different topic",
            "location": "Offsite",
            "starts_at": now + timedelta(days=3),
            "ends_at": now + timedelta(days=3, hours=1),
            "created_by": admin.id,
            "is_active": True,
        },
    ]

    event_ids = []
    for data in events_data:
        result = await db_session.execute(insert_sql, data)
        event_ids.append(result.scalar_one())

    await db_session.commit()

    # DEBUG CHECK
    await db_session.execute(
        text("""
        SELECT attname, attgenerated
        FROM pg_attribute
        WHERE attrelid = 'events'::regclass AND attname = 'search_vector'
    """)
    )

    # Now search - PostgreSQL has computed search_vector
    from app.repositories.unit_of_work import uow_from_session
    from app.services.event_service import EventService
    from app.services.vector_service import VectorService

    uow = uow_from_session(db_session)
    e_service = EventService(uow, VectorService(db_session))

    result_items = await e_service.get_events(
        search=shared_phrase, limit=10, is_active=None
    )

    assert len(result_items.items) == 3
    ordered_ids = [item.id for item in result_items.items]
    # First 3 events contain "Symposium", unrelated does not
    assert ordered_ids == event_ids[:3]


@pytest.mark.asyncio
async def test_events_pagination_semantics(async_client, db_session, user_factory):
    password = "PaginationPass123!"
    hashed = await get_password_hash(password)
    admin = await user_factory(role="admin")
    student = await user_factory(hashed_password=hashed, is_active=True)

    base_start = datetime.now(UTC) + timedelta(days=1)
    events = []
    for i in range(7):
        record = models.Event(
            title=f"Event {i}",
            description=f"Description {i}",
            location="Campus",
            starts_at=base_start + timedelta(days=i, seconds=i),
            ends_at=base_start + timedelta(days=i, hours=2),
            created_by=admin.id,
            is_active=True,
        )
        events.append(record)
    db_session.add_all(events)
    await db_session.commit()

    headers = await _login(async_client, student.email, password)

    first = await async_client.get(
        "/events",
        headers=headers,
        params={"limit": 3},
    )
    assert first.status_code == status.HTTP_200_OK
    first_data = first.json()
    assert first_data["limit"] == 3
    assert first_data["cursor"] is None
    assert len(first_data["items"]) == 3
    assert first_data["has_more"] is True
    assert isinstance(first_data["next_cursor"], str)
    assert first_data["total"] == 7

    second = await async_client.get(
        "/events",
        headers=headers,
        params={"limit": 3, "cursor": first_data["next_cursor"]},
    )
    assert second.status_code == status.HTTP_200_OK
    second_data = second.json()
    assert second_data["cursor"] == first_data["next_cursor"]
    assert len(second_data["items"]) == 3
    assert second_data["has_more"] is True
    assert isinstance(second_data["next_cursor"], str)
    assert second_data["next_cursor"] is not None
    assert second_data["total"] is None

    third = await async_client.get(
        "/events",
        headers=headers,
        params={"cursor": second_data["next_cursor"]},
    )
    assert third.status_code == status.HTTP_200_OK
    third_data = third.json()
    assert third_data["cursor"] == second_data["next_cursor"]
    assert len(third_data["items"]) == 1
    # If it returns 7, it means cursor was ignored or invalid
    assert third_data["has_more"] is False
    assert third_data["next_cursor"] is None
    assert third_data["total"] is None

    default_response = await async_client.get("/events", headers=headers)
    assert default_response.status_code == status.HTTP_200_OK
    # DEFAULT_EVENTS_LIMIT was 20 in crud
    assert default_response.json()["limit"] == 20
    assert default_response.json()["total"] == 7

    capped = await async_client.get(
        "/events",
        headers=headers,
        params={"limit": 100},
    )
    assert capped.status_code == status.HTTP_200_OK
    # MAX_EVENTS_LIMIT was 100 in crud
    assert capped.json()["limit"] == 100
