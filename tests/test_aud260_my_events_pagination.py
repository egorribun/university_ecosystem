from __future__ import annotations

import base64
import json
import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.api import events as events_api
from app.core.config import settings
from app.models import Event
from app.repositories.event_repository import EventRepository
from app.services.event_service import (
    EventService,
    InvalidMyEventsCursor,
    InvalidMyEventsQuery,
    _decode_my_events_cursor,
    _my_events_cursor_binding,
)
from app.services.vector_service import VectorService
from tests.conftest import call_injected

# Attendance QR material is never asserted, so per-run random values keep the
# fixtures free of secret-shaped literals without changing what is checked.
_OWNER_QR_MATERIAL = secrets.token_urlsafe(16)
_OTHER_QR_MATERIAL = secrets.token_urlsafe(16)
_OUTSIDER_QR_MATERIAL = secrets.token_urlsafe(16)


@pytest.mark.asyncio
async def test_my_events_pages_are_bounded_unique_and_user_scoped(
    db_session: AsyncSession, user_factory
) -> None:
    owner = await user_factory()
    other_user = await user_factory()
    now = datetime.now(UTC)

    def make_event(event_id: int, title: str, created_by: uuid.UUID) -> Event:
        starts_at = now + timedelta(days=1, minutes=event_id)
        return Event(
            id=uuid.UUID(int=event_id),
            title=title,
            created_at=now + timedelta(minutes=event_id),
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            created_by=created_by,
            is_active=True,
        )

    owned_events = [
        make_event(event_id, f"Owned {event_id}", owner.id)
        for event_id in range(101, 106)
    ]
    other_only_event = make_event(999, "Other only", other_user.id)
    db_session.add_all([*owned_events, other_only_event])
    await db_session.flush()

    db_session.add_all(
        [
            models.EventAttendance(
                event_id=event.id,
                user_id=owner.id,
                qr_secret=_OWNER_QR_MATERIAL,
                qr_hmac="owner-hmac",
            )
            for event in owned_events
        ]
        + [
            models.EventAttendance(
                event_id=owned_events[-1].id,
                user_id=other_user.id,
                qr_secret=_OTHER_QR_MATERIAL,
                qr_hmac="other-hmac",
            ),
            models.EventAttendance(
                event_id=other_only_event.id,
                user_id=other_user.id,
                qr_secret=_OTHER_QR_MATERIAL,
                qr_hmac="other-hmac",
            ),
        ]
    )
    await db_session.flush()

    repo = EventRepository(db_session)
    service = EventService(
        cast(Any, SimpleNamespace(events=repo)), cast(VectorService, None)
    )
    select_statements: list[str] = []

    def capture_sql(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    engine = db_session.bind.sync_engine
    sqlalchemy_event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        with patch(
            "app.services.event_service.attendance_tokens.issue_token",
            side_effect=lambda attendance: f"qr-{attendance.user_id}",
        ):
            first = await service.get_my_events_page(owner.id, limit=2, locale="en")
            assert first.has_more is True
            assert first.total is None
            assert [item.id for item in first.items] == [
                owned_events[0].id,
                owned_events[1].id,
            ]
            assert all(item.my_qr_token == f"qr-{owner.id}" for item in first.items)

            second = await service.get_my_events_page(
                owner.id,
                limit=2,
                cursor=first.next_cursor,
                locale="en",
            )
            third = await service.get_my_events_page(
                owner.id,
                limit=2,
                cursor=second.next_cursor,
                locale="en",
            )

        pages = [first, second, third]
        page_ids = [item.id for page in pages for item in page.items]
        assert page_ids == [event.id for event in owned_events]
        assert len(page_ids) == len(set(page_ids))
        assert second.has_more is True
        assert third.has_more is False
        assert third.next_cursor is None
        assert other_only_event.id not in page_ids
        assert len(select_statements) == 3
        assert all(" LIMIT " in statement.upper() for statement in select_statements)

        other_page = await service.get_my_events_page(
            other_user.id, limit=10, locale="en"
        )
        assert [item.id for item in other_page.items] == [
            owned_events[-1].id,
            other_only_event.id,
        ]
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", capture_sql)


@pytest.mark.asyncio
async def test_my_event_category_filters_match_serialized_locale_and_precede_limit(
    db_session: AsyncSession, user_factory
) -> None:
    owner = await user_factory()
    outsider = await user_factory()
    now = datetime.now(UTC)

    def make_event(
        event_id: int,
        start_hours: int,
        *,
        event_type: str | None,
        event_type_en: str | None = None,
    ) -> Event:
        starts_at = now + timedelta(hours=start_hours)
        return Event(
            id=uuid.UUID(int=event_id),
            title=f"Event {event_id}",
            event_type=event_type,
            event_type_en=event_type_en,
            created_at=now + timedelta(minutes=event_id),
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            created_by=owner.id,
            is_active=True,
        )

    overlap = make_event(201, 1, event_type="lecture workshop")
    second_lecture = make_event(202, 2, event_type="lecture")
    empty_primary = make_event(203, 3, event_type="", event_type_en="seminar")
    pure_workshop = make_event(204, 4, event_type="workshop")
    empty_both = make_event(205, 5, event_type="", event_type_en="")
    null_both = make_event(206, 6, event_type=None, event_type_en=None)
    other_user_only = make_event(207, 7, event_type="lecture")
    db_session.add_all(
        [
            overlap,
            second_lecture,
            empty_primary,
            pure_workshop,
            empty_both,
            null_both,
            other_user_only,
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            models.EventAttendance(
                event_id=event.id,
                user_id=owner.id,
                qr_secret=_OWNER_QR_MATERIAL,
                qr_hmac="owner-hmac",
            )
            for event in [
                overlap,
                second_lecture,
                empty_primary,
                pure_workshop,
                empty_both,
                null_both,
            ]
        ]
        + [
            models.EventAttendance(
                event_id=other_user_only.id,
                user_id=outsider.id,
                qr_secret=_OUTSIDER_QR_MATERIAL,
                qr_hmac="outsider-hmac",
            )
        ]
    )
    await db_session.flush()

    repo = EventRepository(db_session)
    service = EventService(
        cast(Any, SimpleNamespace(events=repo)), cast(VectorService, None)
    )
    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        side_effect=lambda attendance: f"qr-{attendance.user_id}",
    ):
        lecture_first = await service.get_my_events_page(
            owner.id, locale="ru", category="lecture", limit=1
        )
        assert [item.id for item in lecture_first.items] == [overlap.id]
        assert lecture_first.has_more is True
        lecture_second = await service.get_my_events_page(
            owner.id,
            locale="ru",
            category="lecture",
            limit=1,
            cursor=lecture_first.next_cursor,
        )
        assert [item.id for item in lecture_second.items] == [second_lecture.id]
        with pytest.raises(InvalidMyEventsCursor):
            await service.get_my_events_page(
                owner.id,
                locale="ru",
                category="workshop",
                limit=1,
                cursor=lecture_first.next_cursor,
            )

        workshop = await service.get_my_events_page(
            owner.id, locale="ru", category="workshop", limit=1
        )
        assert [item.id for item in workshop.items] == [pure_workshop.id]
        seminar = await service.get_my_events_page(
            owner.id, locale="ru", category="seminar", limit=1
        )
        assert [item.id for item in seminar.items] == [empty_primary.id]
        assert seminar.items[0].event_type == "seminar"
        other = await service.get_my_events_page(
            owner.id, locale="ru", category="other", limit=10
        )

    assert {item.id for item in other.items} == {empty_both.id, null_both.id}
    assert other_user_only.id not in {item.id for item in other.items}


@pytest.mark.asyncio
async def test_my_event_date_filter_uses_campus_half_open_day_before_limit(
    db_session: AsyncSession, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await user_factory()
    campus_zone = ZoneInfo("Europe/Istanbul")
    monkeypatch.setattr(settings, "campus_timezone", "Europe/Istanbul")
    anchor = date(2026, 10, 12)
    start = datetime.combine(anchor, time.min, tzinfo=campus_zone).astimezone(UTC)
    end = datetime.combine(
        anchor + timedelta(days=1), time.min, tzinfo=campus_zone
    ).astimezone(UTC)
    starts = [
        start - timedelta(microseconds=1),
        start,
        end - timedelta(microseconds=1),
        end,
    ]
    events = [
        Event(
            id=uuid.UUID(int=301 + index),
            title=f"Boundary {index}",
            created_at=datetime.now(UTC) + timedelta(minutes=index),
            starts_at=event_start,
            ends_at=event_start + timedelta(hours=1),
            created_by=owner.id,
            is_active=True,
        )
        for index, event_start in enumerate(starts)
    ]
    db_session.add_all(events)
    await db_session.flush()
    db_session.add_all(
        [
            models.EventAttendance(
                event_id=event.id,
                user_id=owner.id,
                qr_secret=_OWNER_QR_MATERIAL,
                qr_hmac="owner-hmac",
            )
            for event in events
        ]
    )
    await db_session.flush()
    service = EventService(
        cast(Any, SimpleNamespace(events=EventRepository(db_session))),
        cast(VectorService, None),
    )

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        side_effect=lambda attendance: f"qr-{attendance.user_id}",
    ):
        page = await service.get_my_events_page(
            owner.id,
            locale="en",
            limit=2,
            date_range="today",
            date_anchor=anchor,
        )

    assert [item.id for item in page.items] == [events[1].id, events[2].id]
    assert page.has_more is False
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_my_event_popular_and_upcoming_orders_have_stable_keyset_pages(
    db_session: AsyncSession, user_factory
) -> None:
    owner, attendee_one, attendee_two = [await user_factory() for _ in range(3)]
    cutoff = datetime.now(UTC).replace(microsecond=0)

    def make_event(event_id: int, starts_at: datetime) -> Event:
        return Event(
            id=uuid.UUID(int=event_id),
            title=f"Event {event_id}",
            created_at=cutoff,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            created_by=owner.id,
            is_active=True,
        )

    before = make_event(401, cutoff - timedelta(hours=1))
    at_cutoff = make_event(402, cutoff)
    tie_low = make_event(403, cutoff + timedelta(hours=1))
    tie_high = make_event(404, cutoff + timedelta(hours=1))
    later = make_event(405, cutoff + timedelta(hours=2))
    events = [before, at_cutoff, tie_low, tie_high, later]
    db_session.add_all(events)
    await db_session.flush()
    attendance_rows = [
        models.EventAttendance(
            event_id=event.id,
            user_id=owner.id,
            qr_secret=_OWNER_QR_MATERIAL,
            qr_hmac="owner-hmac",
        )
        for event in events
    ]
    attendance_rows.extend(
        [
            models.EventAttendance(
                event_id=before.id, user_id=attendee_one.id, qr_secret="a", qr_hmac="a"
            ),
            models.EventAttendance(
                event_id=before.id, user_id=attendee_two.id, qr_secret="b", qr_hmac="b"
            ),
            models.EventAttendance(
                event_id=at_cutoff.id,
                user_id=attendee_one.id,
                qr_secret="a",
                qr_hmac="a",
            ),
            models.EventAttendance(
                event_id=tie_low.id, user_id=attendee_one.id, qr_secret="a", qr_hmac="a"
            ),
            models.EventAttendance(
                event_id=tie_high.id,
                user_id=attendee_one.id,
                qr_secret="a",
                qr_hmac="a",
            ),
        ]
    )
    db_session.add_all(attendance_rows)
    await db_session.flush()
    service = EventService(
        cast(Any, SimpleNamespace(events=EventRepository(db_session))),
        cast(VectorService, None),
    )

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        side_effect=lambda attendance: f"qr-{attendance.user_id}",
    ):
        popular_first = await service.get_my_events_page(
            owner.id, locale="en", limit=2, sort="popular"
        )
        popular_second = await service.get_my_events_page(
            owner.id,
            locale="en",
            limit=2,
            sort="popular",
            cursor=popular_first.next_cursor,
        )
        upcoming_first = await service.get_my_events_page(
            owner.id,
            locale="en",
            limit=1,
            sort="upcoming",
            upcoming_after=cutoff,
        )
        upcoming_second = await service.get_my_events_page(
            owner.id,
            locale="en",
            limit=1,
            sort="upcoming",
            upcoming_after=cutoff,
            cursor=upcoming_first.next_cursor,
        )
        upcoming_third = await service.get_my_events_page(
            owner.id,
            locale="en",
            limit=1,
            sort="upcoming",
            upcoming_after=cutoff,
            cursor=upcoming_second.next_cursor,
        )

    assert [item.id for item in popular_first.items] == [before.id, tie_high.id]
    assert [item.participant_count for item in popular_first.items] == [3, 2]
    assert [item.id for item in popular_second.items] == [tie_low.id, at_cutoff.id]
    assert popular_second.items[0].participant_count == 2
    assert [item.id for item in upcoming_first.items] == [tie_low.id]
    assert [item.id for item in upcoming_second.items] == [tie_high.id]
    assert [item.id for item in upcoming_third.items] == [later.id]
    assert before.id not in {item.id for item in upcoming_first.items}
    assert at_cutoff.id not in {item.id for item in upcoming_first.items}


def _empty_my_events_service() -> tuple[EventService, SimpleNamespace]:
    repository = SimpleNamespace(list_user_attended_events=AsyncMock())
    service = EventService(
        cast(Any, SimpleNamespace(events=repository)), cast(VectorService, None)
    )
    return service, repository


async def _call_my_events_page_api(
    service: EventService,
    *,
    date_range: str | None = None,
    date_anchor: date | None = None,
    sort: str = "newest",
    upcoming_after: datetime | None = None,
) -> Any:
    user = SimpleNamespace(id=uuid.uuid4())
    request = SimpleNamespace(
        method="GET",
        headers={},
        app=SimpleNamespace(state=SimpleNamespace(cache=object())),
    )
    with patch.object(events_api, "resolve_locale", return_value="en"):
        return await call_injected(
            events_api.my_events_page.__wrapped__,
            request=request,
            response=Response(),
            user=user,
            limit=1,
            cursor=None,
            category=None,
            date_range=date_range,
            date_anchor=date_anchor,
            sort=sort,
            upcoming_after=upcoming_after,
            if_none_match=None,
            provides={"EventService": service},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("date_range", ["today", "week", "month"])
async def test_my_events_rejects_date_windows_that_overflow_as_422(
    date_range: str,
) -> None:
    service, repository = _empty_my_events_service()

    with pytest.raises(HTTPException) as exc_info:
        await _call_my_events_page_api(
            service, date_range=date_range, date_anchor=date.max
        )

    assert exc_info.value.status_code == 422
    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cutoff",
    [
        pytest.param(
            datetime.min.replace(tzinfo=timezone(timedelta(hours=14))),
            id="utc-underflow",
        ),
        pytest.param(
            datetime.max.replace(tzinfo=timezone(-timedelta(hours=14))),
            id="utc-overflow",
        ),
    ],
)
async def test_my_events_rejects_unrepresentable_aware_cutoff_as_422(
    cutoff: datetime,
) -> None:
    service, repository = _empty_my_events_service()

    with pytest.raises(HTTPException) as exc_info:
        await _call_my_events_page_api(service, sort="upcoming", upcoming_after=cutoff)

    assert exc_info.value.status_code == 422
    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
async def test_my_events_invalid_campus_timezone_remains_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _empty_my_events_service()
    monkeypatch.setattr(settings, "campus_timezone", "Not/A_Real_Zone")

    with pytest.raises(RuntimeError, match="Configured campus timezone"):
        await _call_my_events_page_api(
            service, date_range="today", date_anchor=date(2026, 10, 18)
        )

    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
async def test_my_events_rejects_campus_conversion_out_of_bounds_as_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _empty_my_events_service()
    monkeypatch.setattr(settings, "campus_timezone", "Etc/GMT-14")

    with pytest.raises(HTTPException) as exc_info:
        await _call_my_events_page_api(
            service, date_range="today", date_anchor=date.min
        )

    assert exc_info.value.status_code == 422
    repository.list_user_attended_events.assert_not_awaited()


def _my_events_cursor(
    *, user_id: uuid.UUID, sort: str, version: Any, value: Any
) -> str:
    binding = _my_events_cursor_binding(
        user_id=user_id,
        locale="en",
        limit=1,
        category=None,
        date_range=None,
        date_anchor=None,
        sort=sort,
        upcoming_after=None,
    )
    payload = {
        "v": version,
        "sort": sort,
        "filter": binding,
        "key": {"id": str(uuid.UUID(int=501)), "value": value},
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    return encoded.decode().rstrip("=")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "score"),
    [
        pytest.param(True, 1, id="boolean-version"),
        pytest.param(1, 2**63, id="score-over-postgresql-bigint"),
    ],
)
async def test_my_events_rejects_noncanonical_or_unrepresentable_popular_cursor(
    version: Any, score: int
) -> None:
    user_id = uuid.uuid4()
    cursor = _my_events_cursor(
        user_id=user_id, sort="popular", version=version, value=score
    )
    service, repository = _empty_my_events_service()

    with pytest.raises(InvalidMyEventsCursor):
        await service.get_my_events_page(
            user_id, locale="en", limit=1, sort="popular", cursor=cursor
        )

    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
async def test_my_events_cursor_timestamp_overflow_is_invalid_cursor() -> None:
    user_id = uuid.uuid4()
    cursor = _my_events_cursor(
        user_id=user_id,
        sort="newest",
        version=1,
        value="0001-01-01T00:00:00+14:00",
    )
    service, repository = _empty_my_events_service()

    with pytest.raises(InvalidMyEventsCursor):
        await service.get_my_events_page(
            user_id, locale="en", limit=1, sort="newest", cursor=cursor
        )

    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["", "A" * 1025], ids=["empty", "over-limit"])
async def test_my_events_rejects_cursor_length_before_repository_access(
    cursor: str,
) -> None:
    service, repository = _empty_my_events_service()

    with pytest.raises(InvalidMyEventsCursor, match="Invalid My-events cursor"):
        await service.get_my_events_page(
            uuid.uuid4(), locale="en", limit=1, cursor=cursor
        )

    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "non-mapping-key",
        "missing-key-field",
        "extra-key-field",
        "noncanonical-uuid",
        "non-string-date",
        "naive-date",
    ],
)
async def test_my_events_rejects_invalid_cursor_keys_before_repository_access(
    mutation: str,
) -> None:
    user_id = uuid.uuid4()
    timestamp = datetime(2026, 10, 18, 12, tzinfo=UTC)
    cursor = _my_events_cursor(
        user_id=user_id, sort="newest", version=1, value=timestamp.isoformat()
    )
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    assert _decode_my_events_cursor(
        cursor, sort="newest", binding=payload["filter"]
    ) == (timestamp, uuid.UUID(int=501))

    if mutation == "non-mapping-key":
        payload["key"] = []
    elif mutation == "missing-key-field":
        del payload["key"]["id"]
    elif mutation == "extra-key-field":
        payload["key"]["unexpected"] = True
    elif mutation == "noncanonical-uuid":
        payload["key"]["id"] = str(uuid.UUID(int=0xABCDEF)).upper()
    elif mutation == "non-string-date":
        payload["key"]["value"] = 1
    else:
        payload["key"]["value"] = timestamp.replace(tzinfo=None).isoformat()

    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    invalid_cursor = encoded.decode().rstrip("=")
    service, repository = _empty_my_events_service()

    with pytest.raises(InvalidMyEventsCursor, match="Invalid My-events cursor"):
        await service.get_my_events_page(
            user_id, locale="en", limit=1, cursor=invalid_cursor
        )

    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("date_range", "date_anchor", "message"),
    [
        (None, date(2026, 10, 18), "A date anchor requires a date range"),
        ("today", None, "A date range requires its campus-local anchor date"),
        ("year", date(2026, 10, 18), "Unsupported date range"),
    ],
)
async def test_my_events_service_rejects_invalid_date_window_combinations(
    date_range: str | None,
    date_anchor: date | None,
    message: str,
) -> None:
    service, repository = _empty_my_events_service()

    with pytest.raises(ValueError, match=message):
        await service.get_my_events_page(
            uuid.uuid4(),
            locale="en",
            date_range=date_range,
            date_anchor=date_anchor,
        )

    repository.list_user_attended_events.assert_not_awaited()


class _OffsetlessTimezone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sort", "cutoff", "error_type", "message"),
    [
        ("unsupported", None, ValueError, "Unsupported event sort"),
        (
            "upcoming",
            datetime(2026, 10, 18, 12),
            InvalidMyEventsQuery,
            "upcoming_after must be timezone-aware",
        ),
        (
            "upcoming",
            datetime(2026, 10, 18, 12, tzinfo=_OffsetlessTimezone()),
            InvalidMyEventsQuery,
            "upcoming_after is outside supported bounds",
        ),
        ("upcoming", None, ValueError, "upcoming sort requires a time cutoff"),
        (
            "newest",
            datetime(2026, 10, 18, 12, tzinfo=UTC),
            ValueError,
            "upcoming_after only applies to upcoming sort",
        ),
    ],
)
async def test_my_events_service_rejects_invalid_sort_cutoff_combinations(
    sort: str,
    cutoff: datetime | None,
    error_type: type[ValueError],
    message: str,
) -> None:
    service, repository = _empty_my_events_service()

    with pytest.raises(error_type, match=message):
        await service.get_my_events_page(
            uuid.uuid4(), locale="en", sort=sort, upcoming_after=cutoff
        )

    repository.list_user_attended_events.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"sort": "unsupported"}, "Unsupported event sort"),
        ({"category": "unsupported"}, "Unsupported event category"),
        (
            {"sort": "newest", "cursor_key": (1, uuid.UUID(int=501))},
            "Invalid date-ordered cursor key",
        ),
        (
            {
                "sort": "upcoming",
                "upcoming_after": datetime(2026, 10, 18, 12, tzinfo=UTC),
                "cursor_key": (1, uuid.UUID(int=501)),
            },
            "Invalid date-ordered cursor key",
        ),
        (
            {"sort": "popular", "cursor_key": (True, uuid.UUID(int=501))},
            "Invalid popular cursor key",
        ),
        (
            {"sort": "popular", "cursor_key": ("1", uuid.UUID(int=501))},
            "Invalid popular cursor key",
        ),
    ],
)
async def test_my_events_repository_rejects_invalid_inputs_without_querying(
    options: dict[str, Any], message: str
) -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    repository = EventRepository(session)

    with pytest.raises(ValueError, match=message):
        await repository.list_user_attended_events(
            uuid.uuid4(), limit=2, locale="en", **options
        )

    session.execute.assert_not_awaited()
