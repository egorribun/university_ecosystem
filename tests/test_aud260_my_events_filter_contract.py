from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.auth.security import get_password_hash
from app.core.config import settings
from app.models import Event
from app.repositories.event_repository import EventRepository
from app.services.event_service import (
    EventService,
    InvalidMyEventsCursor,
    _my_events_date_bounds,
)
from app.services.vector_service import VectorService

_POSTGRESQL = os.environ.get("DATABASE_URL", "").startswith("postgresql")
requires_postgresql = pytest.mark.skipif(
    not _POSTGRESQL, reason="Category regex parity requires PostgreSQL"
)


def _service(db_session: AsyncSession) -> EventService:
    unit_of_work = cast(Any, SimpleNamespace(events=EventRepository(db_session)))
    return EventService(unit_of_work, cast(VectorService, None))


@pytest.fixture(autouse=True)
def _use_fixture_attendance_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.event_service.attendance_tokens.issue_token",
        lambda attendance: f"fixture-token-{attendance.user_id}",
    )


def _event(
    owner_id: uuid.UUID,
    event_number: int,
    *,
    starts_at: datetime,
    created_at: datetime,
    event_type: str | None = None,
    event_type_en: str | None = None,
) -> Event:
    return Event(
        id=uuid.UUID(int=event_number),
        title=f"Fixture event {event_number}",
        title_en=f"Fixture event {event_number}",
        event_type=event_type,
        event_type_en=event_type_en,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        created_by=owner_id,
        created_at=created_at,
        is_active=True,
    )


def _attendance(event: Event, user_id: uuid.UUID) -> models.EventAttendance:
    return models.EventAttendance(
        event_id=event.id,
        user_id=user_id,
        qr_secret=f"fixture-qr-{event.id}",
        qr_hmac=f"fixture-hmac-{event.id}",
    )


async def _login(async_client: Any, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    assert token
    return {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "en",
        "X-Query-Budget": "15",
    }


@requires_postgresql
@pytest.mark.asyncio
async def test_my_category_filter_matches_serialized_fallback_and_first_match(
    db_session: AsyncSession, user_factory: Any
) -> None:
    owner = await user_factory()
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)
    mixed = _event(
        owner.id,
        1001,
        starts_at=now + timedelta(days=1),
        created_at=now,
        event_type="lecture workshop",
        event_type_en="workshop",
    )
    empty_primary_falls_back = _event(
        owner.id,
        1002,
        starts_at=now + timedelta(days=2),
        created_at=now,
        event_type="",
        event_type_en="workshop",
    )
    both_empty = _event(
        owner.id,
        1003,
        starts_at=now + timedelta(days=3),
        created_at=now,
        event_type="",
        event_type_en="",
    )
    both_null = _event(
        owner.id,
        1004,
        starts_at=now + timedelta(days=4),
        created_at=now,
        event_type=None,
        event_type_en=None,
    )
    events = [mixed, empty_primary_falls_back, both_empty, both_null]
    db_session.add_all(events)
    await db_session.flush()
    db_session.add_all([_attendance(item, owner.id) for item in events])
    await db_session.flush()

    service = _service(db_session)
    lecture = await service.get_my_events_page(
        owner.id, locale="ru", limit=10, category="lecture"
    )
    workshop = await service.get_my_events_page(
        owner.id, locale="ru", limit=10, category="workshop"
    )
    other = await service.get_my_events_page(
        owner.id, locale="ru", limit=10, category="other"
    )

    assert [item.id for item in lecture.items] == [mixed.id]
    assert lecture.items[0].event_type == "lecture workshop"
    assert [item.id for item in workshop.items] == [empty_primary_falls_back.id]
    assert workshop.items[0].event_type == "workshop"
    assert {item.id for item in other.items} == {both_empty.id, both_null.id}
    serialized_other_types = {item.id: item.event_type for item in other.items}
    assert serialized_other_types == {both_empty.id: "", both_null.id: None}


def test_campus_date_ranges_use_local_midnights_across_dst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "campus_timezone", "America/New_York")

    today_start, today_end = _my_events_date_bounds("today", date(2026, 3, 8))
    week_start, week_end = _my_events_date_bounds("week", date(2026, 3, 11))
    month_start, month_end = _my_events_date_bounds("month", date(2026, 3, 11))

    assert today_start is not None and today_end is not None
    assert today_start == datetime(2026, 3, 8, 5, tzinfo=UTC)
    assert today_end == datetime(2026, 3, 9, 4, tzinfo=UTC)
    assert today_end - today_start == timedelta(hours=23)
    assert week_start == datetime(2026, 3, 9, 4, tzinfo=UTC)
    assert week_end == datetime(2026, 3, 16, 4, tzinfo=UTC)
    assert month_start == datetime(2026, 3, 1, 5, tzinfo=UTC)
    assert month_end == datetime(2026, 4, 1, 4, tzinfo=UTC)


@pytest.mark.asyncio
async def test_my_date_filter_includes_local_start_and_excludes_next_midnight(
    db_session: AsyncSession,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "campus_timezone", "America/New_York")
    owner = await user_factory()
    start = datetime(2026, 3, 8, 5, tzinfo=UTC)
    end = datetime(2026, 3, 9, 4, tzinfo=UTC)
    boundary_events = [
        _event(
            owner.id,
            1101,
            starts_at=start - timedelta(microseconds=1),
            created_at=start,
        ),
        _event(owner.id, 1102, starts_at=start, created_at=start),
        _event(
            owner.id,
            1103,
            starts_at=end - timedelta(microseconds=1),
            created_at=start,
        ),
        _event(owner.id, 1104, starts_at=end, created_at=start),
    ]
    db_session.add_all(boundary_events)
    await db_session.flush()
    db_session.add_all([_attendance(item, owner.id) for item in boundary_events])
    await db_session.flush()

    result = await _service(db_session).get_my_events_page(
        owner.id,
        locale="en",
        limit=10,
        date_range="today",
        date_anchor=date(2026, 3, 8),
    )

    assert [item.id for item in result.items] == [
        boundary_events[1].id,
        boundary_events[2].id,
    ]


@pytest.mark.parametrize(
    ("sort", "expected_order"),
    [
        ("newest", [1201, 1202, 1203, 1204, 1205]),
        ("popular", [1205, 1204, 1203, 1202, 1201]),
        ("upcoming", [1201, 1202, 1203, 1204, 1205]),
    ],
)
@pytest.mark.asyncio
async def test_my_sort_cursor_keeps_global_order_across_equal_key_pages(
    db_session: AsyncSession,
    user_factory: Any,
    sort: str,
    expected_order: list[int],
) -> None:
    owner = await user_factory()
    starts_at = datetime(2026, 10, 20, 12, tzinfo=UTC)
    created_at = datetime(2026, 10, 18, 12, tzinfo=UTC)
    events = [
        _event(
            owner.id,
            event_number,
            starts_at=starts_at,
            created_at=created_at,
        )
        for event_number in range(1201, 1206)
    ]
    db_session.add_all(events)
    await db_session.flush()
    db_session.add_all([_attendance(item, owner.id) for item in events])
    await db_session.flush()

    service = _service(db_session)
    params: dict[str, Any] = {"sort": sort, "limit": 2, "locale": "en"}
    if sort == "upcoming":
        params["upcoming_after"] = starts_at - timedelta(minutes=1)

    first = await service.get_my_events_page(owner.id, **params)
    assert first.has_more
    second = await service.get_my_events_page(
        owner.id, cursor=first.next_cursor, **params
    )
    assert second.has_more
    third = await service.get_my_events_page(
        owner.id, cursor=second.next_cursor, **params
    )

    actual_order = [
        item.id.int for page in (first, second, third) for item in page.items
    ]
    assert actual_order == expected_order
    assert len(actual_order) == len(set(actual_order))
    assert third.has_more is False
    assert third.next_cursor is None


@pytest.mark.asyncio
async def test_my_upcoming_cutoff_is_strict(
    db_session: AsyncSession, user_factory: Any
) -> None:
    owner = await user_factory()
    cutoff = datetime(2026, 10, 20, 12, tzinfo=UTC)
    starts = [
        cutoff - timedelta(microseconds=1),
        cutoff,
        cutoff + timedelta(microseconds=1),
    ]
    events = [
        _event(
            owner.id,
            1301 + index,
            starts_at=starts_at,
            created_at=cutoff,
        )
        for index, starts_at in enumerate(starts)
    ]
    db_session.add_all(events)
    await db_session.flush()
    db_session.add_all([_attendance(item, owner.id) for item in events])
    await db_session.flush()

    result = await _service(db_session).get_my_events_page(
        owner.id,
        locale="en",
        limit=10,
        sort="upcoming",
        upcoming_after=cutoff,
    )

    assert [item.id for item in result.items] == [events[2].id]


@pytest.mark.asyncio
async def test_my_cursor_is_bound_to_account_and_every_filter(
    db_session: AsyncSession, user_factory: Any
) -> None:
    owner = await user_factory()
    other_user = await user_factory()
    cutoff = datetime(2026, 10, 20, 12, tzinfo=UTC)
    events = [
        _event(
            owner.id,
            1401 + index,
            starts_at=cutoff + timedelta(hours=index + 1),
            created_at=cutoff,
            event_type="lecture",
            event_type_en="lecture",
        )
        for index in range(3)
    ]
    db_session.add_all(events)
    await db_session.flush()
    db_session.add_all([_attendance(item, owner.id) for item in events])
    await db_session.flush()

    service = _service(db_session)
    first = await service.get_my_events_page(
        owner.id,
        locale="en",
        limit=1,
        sort="upcoming",
        upcoming_after=cutoff,
    )
    assert first.next_cursor
    cursor = first.next_cursor
    equivalent_cutoff = cutoff.astimezone(timezone(timedelta(hours=-4)))
    equivalent_page = await service.get_my_events_page(
        owner.id,
        locale="en",
        limit=1,
        sort="upcoming",
        upcoming_after=equivalent_cutoff,
        cursor=cursor,
    )
    assert [item.id for item in equivalent_page.items] == [events[1].id]

    changed_contexts = [
        {"user_id": other_user.id},
        {"locale": "ru"},
        {"limit": 2},
        {"category": "lecture"},
        {"date_range": "today", "date_anchor": date(2026, 10, 20)},
        {"sort": "popular", "upcoming_after": None},
        {"upcoming_after": cutoff + timedelta(seconds=1)},
        {"cursor": "not-a-canonical-cursor"},
    ]
    for changed in changed_contexts:
        user_id = changed.pop("user_id", owner.id)
        params: dict[str, Any] = {
            "locale": "en",
            "limit": 1,
            "sort": "upcoming",
            "upcoming_after": cutoff,
            "cursor": cursor,
        }
        params.update(changed)
        with pytest.raises(InvalidMyEventsCursor):
            await service.get_my_events_page(user_id, **params)


@pytest.mark.asyncio
async def test_anonymous_my_events_request_never_queries_event_rows(
    async_client: Any, db_session: AsyncSession
) -> None:
    statements: list[str] = []

    def record_statement(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(" ".join(statement.lower().split()))

    engine = db_session.bind.sync_engine
    sqlalchemy_event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = await async_client.get("/events/my/page?limit=100")
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 401
    assert not any(
        " from events " in f" {statement} "
        or " join events " in f" {statement} "
        or "event_attendance" in statement
        for statement in statements
    )


@pytest.mark.asyncio
async def test_my_events_rejects_invalid_filter_combinations(
    async_client: Any, user_factory: Any
) -> None:
    password = secrets.token_urlsafe(24)
    password_hash = await get_password_hash(password)
    owner = await user_factory(hashed_password=password_hash, is_active=True)
    headers = await _login(async_client, owner.email, password)

    invalid_queries = [
        {"limit": "101"},
        {"category": "unknown"},
        {"date_range": "today"},
        {"sort": "upcoming"},
        {"sort": "newest", "upcoming_after": "2026-10-20T12:00:00Z"},
        {"sort": "upcoming", "upcoming_after": "2026-10-20T12:00:00"},
    ]
    for params in invalid_queries:
        response = await async_client.get(
            "/events/my/page", params=params, headers=headers
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_my_events_etag_matches_the_exact_cursor_page(
    async_client: Any, db_session: AsyncSession, user_factory: Any
) -> None:
    password = secrets.token_urlsafe(24)
    password_hash = await get_password_hash(password)
    owner = await user_factory(hashed_password=password_hash, is_active=True)
    starts_at = datetime(2026, 10, 20, 12, tzinfo=UTC)
    events = [
        _event(
            owner.id,
            1501 + index,
            starts_at=starts_at + timedelta(hours=index),
            created_at=starts_at,
        )
        for index in range(2)
    ]
    db_session.add_all(events)
    await db_session.flush()
    db_session.add_all([_attendance(item, owner.id) for item in events])
    await db_session.flush()
    # Commit before the HTTP login: its request session writes to the same
    # SQLite file, and an open flushed transaction would hold the write lock.
    await db_session.commit()
    headers = await _login(async_client, owner.email, password)

    first = await async_client.get("/events/my/page?limit=1", headers=headers)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["items"][0]["id"] == str(events[0].id)
    assert first_payload["has_more"] is True
    first_etag = first.headers["ETag"]

    page_two_params = {"limit": "1", "cursor": first_payload["next_cursor"]}
    second_with_first_etag = await async_client.get(
        "/events/my/page",
        params=page_two_params,
        headers={**headers, "If-None-Match": first_etag},
    )
    assert second_with_first_etag.status_code == 200
    second_payload = second_with_first_etag.json()
    assert second_payload["items"][0]["id"] == str(events[1].id)
    second_etag = second_with_first_etag.headers["ETag"]
    assert second_etag != first_etag

    second_not_modified = await async_client.get(
        "/events/my/page",
        params=page_two_params,
        headers={**headers, "If-None-Match": second_etag},
    )

    assert second_not_modified.status_code == 304
    assert second_not_modified.headers["ETag"] == second_etag
