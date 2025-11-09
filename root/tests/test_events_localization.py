from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from app import crud
from app.api import events
from app.auth.security import get_password_hash
from app.models import models
from app.services import attendance_tokens


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
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

    assert payload_en[primary.id]["title"] == "English Event"
    assert payload_en[primary.id]["description"] == "Description in English"
    assert payload_en[primary.id]["location"] == "Moscow"
    assert payload_en[primary.id]["event_type"] == "Lecture"
    assert payload_en[primary.id]["about"] == "More details"
    assert payload_en[primary.id]["title_en"] == "English Event"
    assert payload_en[primary.id]["description_en"] == "Description in English"

    assert payload_en[fallback.id]["title"] == "Только русский"
    assert payload_en[fallback.id]["description"] == "Без перевода"
    assert payload_en[fallback.id]["location"] == "Санкт-Петербург"
    assert payload_en[fallback.id]["event_type"] == "встреча"
    assert payload_en[fallback.id]["about"] == "Описание только на русском"
    assert payload_en[fallback.id]["title_en"] is None

    response_ru = await async_client.get(
        "/events",
        headers={**headers, "Accept-Language": "ru"},
    )
    assert response_ru.status_code == 200
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

    assert payload_ru[primary.id]["title"] == "Русское событие"
    assert payload_ru[primary.id]["description"] == "Описание по-русски"
    assert payload_ru[primary.id]["location"] == "Москва"
    assert payload_ru[primary.id]["event_type"] == "лекция"
    assert payload_ru[primary.id]["about"] == "Подробности"
    assert payload_ru[fallback.id]["title"] == "Только русский"
    assert payload_ru[fallback.id]["description"] == "Без перевода"


@pytest.mark.anyio
async def test_events_etag_and_not_modified(
    async_client, db_session, user_factory, fake_cache
):
    await events._reset_events_list_cache_version()
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

    list_not_modified = await async_client.get(
        "/events",
        headers={**base_headers, "If-None-Match": list_etag},
    )
    assert list_not_modified.status_code == status.HTTP_304_NOT_MODIFIED
    assert list_not_modified.headers.get("Content-Language") == "en"
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

    my_not_modified = await async_client.get(
        "/events/my",
        headers={**base_headers, "If-None-Match": my_etag},
    )
    assert my_not_modified.status_code == status.HTTP_304_NOT_MODIFIED
    assert my_not_modified.headers.get("Content-Language") == "en"
    assert my_not_modified.headers.get("ETag") == my_etag


@pytest.mark.anyio
async def test_get_all_events_search_deterministic_order(db_session, user_factory):
    admin = await user_factory(role="admin")

    now = datetime.now(UTC)
    shared_phrase = "Symposium"
    first = models.Event(
        title=f"{shared_phrase} kickoff",
        description="Agenda review",
        location="Main campus",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=2),
        created_by=admin.id,
        is_active=True,
    )
    second = models.Event(
        title=f"{shared_phrase} planning",
        description="Breakout sessions",
        location="Main campus",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=3),
        created_by=admin.id,
        is_active=True,
    )
    third = models.Event(
        title="Обсуждение",
        title_en=f"{shared_phrase} recap",
        description="Post-event debrief",
        location="Satellite hall",
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=2),
        created_by=admin.id,
        is_active=True,
    )
    unrelated = models.Event(
        title="Another meetup",
        description="Different topic",
        location="Offsite",
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=1),
        created_by=admin.id,
        is_active=True,
    )

    db_session.add_all([first, second, third, unrelated])
    await db_session.commit()
    for event in (first, second, third, unrelated):
        await db_session.refresh(event)

    result = await crud.get_all_events(db_session, search=shared_phrase, limit=10)

    assert result.total == 3
    assert result.has_more is False
    ordered_ids = [item.id for item in result.items]
    assert ordered_ids == [first.id, second.id, third.id]


@pytest.mark.anyio
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
            starts_at=base_start + timedelta(days=i),
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
    assert second_data["next_cursor"] != first_data["next_cursor"]

    third = await async_client.get(
        "/events",
        headers=headers,
        params={"cursor": second_data["next_cursor"]},
    )
    assert third.status_code == status.HTTP_200_OK
    third_data = third.json()
    assert third_data["cursor"] == second_data["next_cursor"]
    assert len(third_data["items"]) == 1
    assert third_data["has_more"] is False
    assert third_data["next_cursor"] is None
    assert third_data["total"] == 7

    default_response = await async_client.get("/events", headers=headers)
    assert default_response.status_code == status.HTTP_200_OK
    assert default_response.json()["limit"] == crud.DEFAULT_EVENTS_LIMIT

    capped = await async_client.get(
        "/events",
        headers=headers,
        params={"limit": crud.MAX_EVENTS_LIMIT},
    )
    assert capped.status_code == status.HTTP_200_OK
    assert capped.json()["limit"] == crud.MAX_EVENTS_LIMIT


@pytest.mark.anyio
async def test_events_cache_invalidation_on_mutations(
    async_client, db_session, user_factory, fake_cache
):
    await events._reset_events_list_cache_version()

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
    version_after_first = await events._read_events_list_version(fake_cache)
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

    version_after_create = await events._read_events_list_version(fake_cache)
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
    version_after_update = await events._read_events_list_version(fake_cache)
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
    version_after_delete = await events._read_events_list_version(fake_cache)
    assert version_after_delete == version_after_update + 1
    assert await fake_cache.get(post_update_key) is not None


@pytest.mark.anyio
async def test_events_cache_uses_version_from_redis(
    async_client, db_session, user_factory, fake_cache
):
    await events._reset_events_list_cache_version()

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
    assert initial_items[event.id]["title"] == "Original title"

    initial_version = await events._read_events_list_version(fake_cache)
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
    assert refreshed_items[event.id]["title"] == "Updated title"

    refreshed_version = await events._read_events_list_version(fake_cache)
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
