from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from sqlalchemy import delete
from sqlalchemy import event as sqlalchemy_event

import app.models as models
from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.database import get_read_db
from app.core.protocols import AsyncDatabaseSession
from app.repositories.event_repository import EventRepository
from app.services import attendance_tokens
from app.services.event_service import EventService
from app.services.vector_service import VectorService
from tests.conftest import dishka_overrides


def test_my_events_openapi_documents_locale_sort_and_overflow(app) -> None:
    paths = app.openapi()["paths"]
    page = paths["/api/v1/events/my/page"]["get"]
    params = {param["name"]: param for param in page["parameters"]}
    assert params["lang"]["in"] == "query"
    assert "newest_desc" in params["sort"]["schema"]["enum"]
    overflow = paths["/api/v1/events/my"]["get"]["responses"]["409"]
    problem = overflow["content"]["application/problem+json"]["schema"]
    assert problem["properties"]["code"]["const"] == "events_my_pagination_required"
    assert problem["properties"]["legacy_limit"]["const"] == 100
    assert "Link" in overflow["headers"]


async def _create_events(db_session, owner, count: int) -> list[models.Event]:
    now = datetime.now(UTC).replace(microsecond=0)
    secret = attendance_tokens.generate_secret()
    signature = attendance_tokens.compute_secret_hmac(secret)
    events = [
        models.Event(
            id=uuid.UUID(int=50_000 + index),
            title=f"Event {index}",
            title_en=f"English {index}",
            starts_at=now + timedelta(minutes=index // 2),
            ends_at=now + timedelta(minutes=index // 2, hours=1),
            created_by=owner.id,
            is_active=True,
        )
        for index in range(count)
    ]
    db_session.add_all(events)
    await db_session.flush()
    db_session.add_all(
        models.EventAttendance(
            event_id=event.id,
            user_id=owner.id,
            qr_secret=secret,
            qr_hmac=signature,
        )
        for event in events
    )
    await db_session.commit()
    return events


async def _login(async_client, owner, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": owner.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    assert token
    return {"Authorization": f"Bearer {token}", "Accept-Language": "en"}


@pytest.mark.asyncio
async def test_overflow_cannot_be_hidden_by_a_cached_100_row_etag(
    async_client, db_session, user_factory, fake_cache, monkeypatch
) -> None:
    password = f"{uuid.uuid4().hex}Aa1!"
    owner = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    events = await _create_events(db_session, owner, 100)
    headers = await _login(async_client, owner, password)
    first = await async_client.get("/events/my", headers=headers)
    assert first.status_code == 200
    assert len(first.json()) == 100
    old_etag = first.headers["ETag"]

    later = datetime.now(UTC) + timedelta(days=3)
    extra = models.Event(
        id=uuid.uuid4(),
        title="One more",
        starts_at=later,
        ends_at=later + timedelta(hours=1),
        created_by=owner.id,
        is_active=True,
    )
    secret = attendance_tokens.generate_secret()
    db_session.add(extra)
    await db_session.flush()
    db_session.add(
        models.EventAttendance(
            event_id=extra.id,
            user_id=owner.id,
            qr_secret=secret,
            qr_hmac=attendance_tokens.compute_secret_hmac(secret),
        )
    )
    await db_session.commit()  # No cache-version increment, like an external writer.
    issue_token = Mock(wraps=attendance_tokens.issue_token)
    monkeypatch.setattr(attendance_tokens, "issue_token", issue_token)

    overflow = await async_client.get(
        "/events/my", headers={**headers, "If-None-Match": old_etag}
    )

    assert overflow.status_code == 409
    assert overflow.headers["content-type"].startswith("application/problem+json")
    assert overflow.headers["cache-control"] == "private, no-store"
    assert overflow.json()["code"] == "events_my_pagination_required"
    assert overflow.json()["legacy_limit"] == 100
    assert overflow.json()["pagination_url"] == "/api/v1/events/my/page"
    assert "/api/v1/events/my/page" in overflow.headers["link"]
    issue_token.assert_not_called()
    assert len(events) == 100


@pytest.mark.asyncio
async def test_newest_desc_pages_preserve_global_order_across_equal_timestamps(
    db_session, user_factory
) -> None:
    owner = await user_factory()
    events = await _create_events(db_session, owner, 5)
    repo = EventRepository(db_session)
    service = EventService(
        cast(Any, SimpleNamespace(events=repo)), cast(VectorService, None)
    )
    first = await service.get_my_events_page(owner.id, limit=2, sort="newest_desc")
    second = await service.get_my_events_page(
        owner.id, limit=2, sort="newest_desc", cursor=first.next_cursor
    )
    third = await service.get_my_events_page(
        owner.id, limit=2, sort="newest_desc", cursor=second.next_cursor
    )
    ids = [item.id for page in (first, second, third) for item in page.items]
    expected = sorted(
        events, key=lambda event: (event.starts_at, event.id), reverse=True
    )
    assert ids == [event.id for event in expected]
    assert len(ids) == len(set(ids)) == 5
    assert first.has_more and second.has_more and not third.has_more
    assert third.next_cursor is None


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["my-page", "detail"])
async def test_old_etag_cannot_replay_expired_qr_from_server_payload_cache(
    async_client, db_session, user_factory, fake_cache, monkeypatch, route: str
) -> None:
    password = f"{uuid.uuid4().hex}Aa1!"
    owner = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    event = (await _create_events(db_session, owner, 1))[0]
    headers = await _login(async_client, owner, password)
    start = datetime(2026, 10, 28, 10, 0, 59, tzinfo=UTC)
    clock = [start]
    monkeypatch.setattr(settings, "attendance_token_ttl_seconds", 60)
    monkeypatch.setattr(attendance_tokens, "_now", lambda: clock[0])
    url = (
        f"/events/{event.id}?lang=en"
        if route == "detail"
        else "/events/my/page?limit=1&lang=en"
    )

    first = await async_client.get(url, headers=headers)
    assert first.status_code == 200
    old_token = (
        first.json()["my_qr_token"]
        if route == "detail"
        else first.json()["items"][0]["my_qr_token"]
    )
    old_etag = first.headers["ETag"]
    clock[0] += timedelta(seconds=121)
    second = await async_client.get(url, headers={**headers, "If-None-Match": old_etag})

    assert second.status_code == 200
    new_token = (
        second.json()["my_qr_token"]
        if route == "detail"
        else second.json()["items"][0]["my_qr_token"]
    )
    assert new_token != old_token
    attendance = await EventRepository(db_session).get_attendance(event.id, owner.id)
    assert attendance is not None
    with pytest.raises(attendance_tokens.AttendanceTokenExpired):
        attendance_tokens.verify_token(old_token, attendance, now=clock[0])
    attendance_tokens.verify_token(new_token, attendance, now=clock[0])


@pytest.mark.asyncio
async def test_detail_never_loads_unexposed_attachments_on_200_or_304(
    async_client, db_session, user_factory, monkeypatch
) -> None:
    password = f"{uuid.uuid4().hex}Aa1!"
    owner = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    event = (await _create_events(db_session, owner, 1))[0]
    headers = await _login(async_client, owner, password)
    now = datetime(2026, 10, 28, 10, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(attendance_tokens, "_now", lambda: now)
    url = f"/events/{event.id}?lang=en"

    before = await async_client.get(url, headers=headers)
    assert before.status_code == 200
    db_session.add_all(
        models.EventFile(event_id=event.id, file_url=f"/files/{index}.pdf")
        for index in range(150)
    )
    await db_session.commit()
    file_selects: list[str] = []

    def record_select(_connection, _cursor, statement, _parameters, _context, _many):
        sql = " ".join(statement.lower().split())
        if sql.startswith("select") and "event_files" in sql:
            file_selects.append(sql)

    engine = db_session.bind.sync_engine
    sqlalchemy_event.listen(engine, "before_cursor_execute", record_select)
    try:
        fresh = await async_client.get(url, headers=headers)
        conditional = await async_client.get(
            url, headers={**headers, "If-None-Match": fresh.headers["ETag"]}
        )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", record_select)

    assert fresh.status_code == 200
    assert fresh.json() == before.json()
    assert fresh.json()["files"] == []
    assert fresh.headers["ETag"] == before.headers["ETag"]
    assert conditional.status_code == 304
    attendance = await EventRepository(db_session).get_attendance(event.id, owner.id)
    assert attendance is not None
    attendance_tokens.verify_token(fresh.json()["my_qr_token"], attendance, now=now)
    assert file_selects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", ["newest", "upcoming", "popular"])
async def test_preexisting_v1_cursor_continues_the_original_order(
    db_session, user_factory, sort: str
) -> None:
    owner = await user_factory()
    events = await _create_events(db_session, owner, 5)
    cutoff = events[0].starts_at - timedelta(days=1) if sort == "upcoming" else None
    ordered = sorted(events, key=lambda event: (event.starts_at, event.id))
    if sort == "popular":
        ordered = sorted(events, key=lambda event: event.id, reverse=True)
    anchor = ordered[1]
    binding = {
        "user": str(owner.id),
        "locale": "en",
        "limit": 2,
        "category": None,
        "date_range": None,
        "date_anchor": None,
        "sort": sort,
        "upcoming_after": cutoff.isoformat() if cutoff else None,
    }
    fingerprint = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    value: str | int = 1 if sort == "popular" else anchor.starts_at.isoformat()
    payload = {
        "v": 1,
        "sort": sort,
        "filter": fingerprint,
        "key": {"value": value, "id": str(anchor.id)},
    }
    cursor = (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    service = EventService(
        cast(Any, SimpleNamespace(events=EventRepository(db_session))),
        cast(VectorService, None),
    )

    page = await service.get_my_events_page(
        owner.id,
        locale="en",
        limit=2,
        sort=sort,
        cursor=cursor,
        upcoming_after=cutoff,
    )

    assert [item.id for item in page.items] == [event.id for event in ordered[2:4]]
    assert page.has_more is True


@pytest.mark.asyncio
async def test_my_page_query_language_is_bound_to_cursor_and_content(
    async_client, db_session, user_factory
) -> None:
    password = f"{uuid.uuid4().hex}Aa1!"
    owner = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    await _create_events(db_session, owner, 3)
    headers = await _login(async_client, owner, password)

    first = await async_client.get(
        "/events/my/page", params={"lang": "ru", "limit": 1}, headers=headers
    )
    assert first.status_code == 200
    assert first.headers["content-language"] == "ru"
    assert first.json()["items"][0]["title"] == "Event 0"
    cursor = first.json()["next_cursor"]
    second = await async_client.get(
        "/events/my/page",
        params={"lang": "en", "limit": 1, "cursor": cursor},
        headers=headers,
    )
    assert second.status_code == 422


@pytest.mark.asyncio
async def test_more_than_legacy_capacity_remains_available_across_bounded_http_pages(
    async_client, db_session, user_factory
) -> None:
    password = f"{uuid.uuid4().hex}Aa1!"
    owner = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    events = await _create_events(db_session, owner, 205)
    headers = await _login(async_client, owner, password)
    selects: list[tuple[str, Any]] = []

    def record_select(_connection, _cursor, statement, _parameters, _context, _many):
        sql = " ".join(statement.lower().split())
        if sql.startswith("select") and "join event_attendance" in sql:
            selects.append((sql, _parameters))

    engine = db_session.bind.sync_engine
    sqlalchemy_event.listen(engine, "before_cursor_execute", record_select)
    try:
        cursor = None
        pages = []
        while True:
            params: dict[str, Any] = {
                "lang": "en",
                "limit": 100,
                "sort": "newest_desc",
            }
            if cursor:
                params["cursor"] = cursor
            response = await async_client.get(
                "/events/my/page", params=params, headers=headers
            )
            assert response.status_code == 200
            page = response.json()
            pages.append(page)
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
            assert cursor
            assert len(pages) < 4
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", record_select)

    actual = [item["id"] for page in pages for item in page["items"]]
    expected = sorted(
        events, key=lambda event: (event.starts_at, event.id), reverse=True
    )
    assert actual == [str(event.id) for event in expected]
    assert [len(page["items"]) for page in pages] == [100, 100, 5]
    assert len(actual) == len(set(actual)) == 205
    assert len(selects) == 3
    assert all(" limit " in f" {sql} " and 101 in params for sql, params in selects)


class _UnavailableReplica:
    async def execute(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("My-events read reached the replica")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/events/my", "/events/my/page?limit=1"])
async def test_my_routes_resolve_primary_when_replica_is_distinct(
    app, async_client, db_session, user_factory, monkeypatch, path: str
) -> None:
    password = f"{uuid.uuid4().hex}Aa1!"
    owner = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    await _create_events(db_session, owner, 1)
    headers = await _login(async_client, owner, password)

    async def unavailable_replica() -> AsyncIterator[AsyncDatabaseSession]:
        yield cast(AsyncDatabaseSession, _UnavailableReplica())

    monkeypatch.setitem(app.dependency_overrides, get_read_db, unavailable_replica)
    with dishka_overrides(app):
        response = await async_client.get(path, headers=headers)
    assert response.status_code == 200
    body = response.json()
    items = body if isinstance(body, list) else body["items"]
    assert len(items) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["my-page", "detail"])
async def test_revoke_and_reregister_are_observed_before_conditional_response(
    async_client, db_session, user_factory, fake_cache, route: str
) -> None:
    password = f"{uuid.uuid4().hex}Aa1!"
    owner = await user_factory(
        hashed_password=await get_password_hash(password), is_active=True
    )
    event = (await _create_events(db_session, owner, 1))[0]
    headers = await _login(async_client, owner, password)
    url = (
        f"/events/{event.id}?lang=en"
        if route == "detail"
        else "/events/my/page?limit=1&lang=en"
    )
    first = await async_client.get(url, headers=headers)
    assert first.status_code == 200

    await db_session.execute(
        delete(models.EventAttendance).where(
            models.EventAttendance.event_id == event.id,
            models.EventAttendance.user_id == owner.id,
        )
    )
    await db_session.commit()
    removed = await async_client.get(
        url, headers={**headers, "If-None-Match": first.headers["ETag"]}
    )
    assert removed.status_code == 200
    if route == "detail":
        assert removed.json()["is_registered"] is False
        assert removed.json()["my_qr_token"] is None
    else:
        assert removed.json()["items"] == []

    secret = attendance_tokens.generate_secret()
    db_session.add(
        models.EventAttendance(
            event_id=event.id,
            user_id=owner.id,
            qr_secret=secret,
            qr_hmac=attendance_tokens.compute_secret_hmac(secret),
        )
    )
    await db_session.commit()
    restored = await async_client.get(
        url, headers={**headers, "If-None-Match": removed.headers["ETag"]}
    )
    assert restored.status_code == 200
    item = restored.json() if route == "detail" else restored.json()["items"][0]
    assert item["is_registered"] is True
    attendance = await EventRepository(db_session).get_attendance(event.id, owner.id)
    assert attendance is not None
    attendance_tokens.verify_token(item["my_qr_token"], attendance)
