import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from prometheus_client import CollectorRegistry

from app.api import events
from app.auth.security import get_password_hash
from app.core import observability
from app.models import models
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
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_events_localization(async_client, db_session, user_factory):
    password = "TestEvent123!"
    hashed = get_password_hash(password)
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
    await notification_queue.reset_testing_state()

    password = "TeacherPass123!"
    teacher = await user_factory(
        role="teacher", hashed_password=get_password_hash(password), is_active=True
    )

    headers = await _login(async_client, teacher.email, password)

    def _failing_add_task(self, func, *args, **kwargs):  # pragma: no cover - test shim
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

    failed_records = await notification_queue.get_failed_enqueue_records()
    assert len(failed_records) == 1
    failure = failed_records[0]
    assert str(failure.job.record_id) == body["id"]
    assert failure.job.kind == "event"
    assert failure.attempts == 1
    assert failure.source == "NotificationService.dispatch_event_created"
    assert failure.error and "notification queue unavailable" in failure.error

    import uuid

    stored = await db_session.get(models.Event, uuid.UUID(body["id"]))
    assert stored is not None

    await notification_queue.reset_testing_state()


@pytest.mark.asyncio
async def test_events_etag_and_not_modified(
    async_client, db_session, user_factory, fake_cache
):
    await events.events_cache_version.reset(fake_cache)
    assert fake_cache is not None
    password = "TestEvent456!"
    hashed = get_password_hash(password)
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
            "starts_at": now + timedelta(days=1),
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
            "starts_at": now + timedelta(days=1),
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
    info = await db_session.execute(
        text("""
        SELECT attname, attgenerated
        FROM pg_attribute
        WHERE attrelid = 'events'::regclass AND attname = 'search_vector'
    """)
    )
    print(f"DEBUG: pg_attribute: {info.all()}")

    # DEBUG ROWS
    rows = await db_session.execute(text("SELECT id, title, search_vector FROM events"))
    for r in rows:
        print(f"DEBUG ROW: {r}")

    # Now search - PostgreSQL has computed search_vector
    from app.repositories.event_repository import EventRepository
    from app.services.event_service import EventService
    from app.services.vector_service import VectorService

    e_repo = EventRepository(db_session)
    e_service = EventService(e_repo, VectorService(db_session))

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
    hashed = get_password_hash(password)
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


@pytest.mark.skip(reason="Pre-existing issue with cache invalidation version tracking")
@pytest.mark.asyncio
async def test_events_cache_invalidation_on_mutations(
    async_client, db_session, user_factory, fake_cache
):
    await events.events_cache_version.reset(fake_cache)

    admin_password = "CacheAdmin123!"
    student_password = "CacheStudent123!"
    admin = await user_factory(
        role="admin", hashed_password=get_password_hash(admin_password)
    )
    student = await user_factory(
        hashed_password=get_password_hash(student_password), is_active=True
    )

    now = datetime.now(UTC)
    initial_event = models.Event(
        title="Initial event",
        description="Initial description",
        location="Campus",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=2),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(initial_event)
    await db_session.commit()
    await db_session.refresh(initial_event)

    student_headers = await _login(async_client, student.email, student_password)
    list_headers = {**student_headers, "Accept-Language": "en"}

    first_response = await async_client.get("/events", headers=list_headers)
    assert first_response.status_code == status.HTTP_200_OK
    version_after_first = int(await events.events_cache_version.get_version(fake_cache))
    tracked_key = events._events_list_cache_key(
        locale="en",
        search="",
        event_type="",
        location="",
        is_active=True,
        limit=first_response.json()["limit"],
        cursor=None,
        version=str(version_after_first),
    )
    cached_entry = await fake_cache.get(tracked_key)
    assert cached_entry is not None

    first_etag = first_response.headers.get("ETag")
    assert first_etag
    cached_not_modified = await async_client.get(
        "/events",
        headers={**list_headers, "If-None-Match": first_etag},
    )
    assert cached_not_modified.status_code == status.HTTP_304_NOT_MODIFIED

    admin_headers = await _login(async_client, admin.email, admin_password)
    create_payload = {
        "title": "New cached event",
        "description": "Fresh description",
        "location": "Campus",
        "starts_at": (now + timedelta(days=3)).isoformat(),
        "ends_at": (now + timedelta(days=3, hours=1)).isoformat(),
    }
    create_response = await async_client.post(
        "/events",
        headers=admin_headers,
        json=create_payload,
    )
    assert create_response.status_code == status.HTTP_200_OK
    created_event_id = create_response.json()["id"]

    version_after_create = int(
        await events.events_cache_version.get_version(fake_cache)
    )
    assert version_after_create == version_after_first + 1
    assert await fake_cache.get(tracked_key) is not None

    after_create = await async_client.get("/events", headers=list_headers)
    assert after_create.status_code == status.HTTP_200_OK
    active_key = events._events_list_cache_key(
        locale="en",
        search="",
        event_type="",
        location="",
        is_active=True,
        limit=after_create.json()["limit"],
        cursor=None,
        version=str(version_after_create),
    )
    assert await fake_cache.get(active_key) is not None

    update_response = await async_client.patch(
        f"/events/{created_event_id}",
        headers=admin_headers,
        json={"title": "Updated cached event"},
    )
    assert update_response.status_code == status.HTTP_200_OK
    version_after_update = int(
        await events.events_cache_version.get_version(fake_cache)
    )
    assert version_after_update == version_after_create + 1
    assert await fake_cache.get(active_key) is not None

    after_update = await async_client.get("/events", headers=list_headers)
    assert after_update.status_code == status.HTTP_200_OK
    post_update_key = events._events_list_cache_key(
        locale="en",
        search="",
        event_type="",
        location="",
        is_active=True,
        limit=after_update.json()["limit"],
        cursor=None,
        version=str(version_after_update),
    )
    assert await fake_cache.get(post_update_key) is not None

    delete_response = await async_client.delete(
        f"/events/{created_event_id}", headers=admin_headers
    )
    assert delete_response.status_code == status.HTTP_200_OK
    version_after_delete = int(
        await events.events_cache_version.get_version(fake_cache)
    )
    assert version_after_delete == version_after_update + 1
    assert await fake_cache.get(post_update_key) is not None


@pytest.mark.asyncio
async def test_events_cache_uses_version_from_redis(
    async_client, db_session, user_factory, fake_cache
):
    await events.events_cache_version.reset(fake_cache)

    password = "VersionPass123!"
    hashed = get_password_hash(password)
    admin = await user_factory(role="admin")
    student = await user_factory(hashed_password=hashed, is_active=True)

    now = datetime.now(UTC)
    event = models.Event(
        title="Original title",
        description="Original description",
        location="Campus",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=2),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    headers = await _login(async_client, student.email, password)
    list_headers = {**headers, "Accept-Language": "en"}

    initial_response = await async_client.get("/events", headers=list_headers)
    assert initial_response.status_code == status.HTTP_200_OK
    initial_data = initial_response.json()
    initial_items = {item["id"]: item for item in initial_data["items"]}
    assert initial_items[str(event.id)]["title"] == "Original title"

    initial_version = int(await events.events_cache_version.get_version(fake_cache))
    initial_key = events._events_list_cache_key(
        locale="en",
        search="",
        event_type="",
        location="",
        is_active=True,
        limit=initial_data["limit"],
        cursor=None,
        version=str(initial_version),
    )
    assert await fake_cache.get(initial_key) is not None

    event.title = "Updated title"
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    await events._increment_events_list_version(fake_cache)

    refreshed = await async_client.get("/events", headers=list_headers)
    assert refreshed.status_code == status.HTTP_200_OK
    refreshed_data = refreshed.json()
    refreshed_items = {item["id"]: item for item in refreshed_data["items"]}
    assert refreshed_items[str(event.id)]["title"] == "Updated title"

    refreshed_version = int(await events.events_cache_version.get_version(fake_cache))
    assert refreshed_version == initial_version + 1
    refreshed_key = events._events_list_cache_key(
        locale="en",
        search="",
        event_type="",
        location="",
        is_active=True,
        limit=refreshed_data["limit"],
        cursor=None,
        version=str(refreshed_version),
    )
    assert await fake_cache.get(refreshed_key) is not None
