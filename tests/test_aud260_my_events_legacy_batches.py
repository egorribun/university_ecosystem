from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.models import Event
from app.repositories.event_repository import EventRepository
from app.services.event_service import EventService, MyEventsPaginationRequired
from app.services.vector_service import VectorService


@pytest.mark.asyncio
@pytest.mark.parametrize("owned_count", [0, 1, 100, 101, 205])
async def test_legacy_my_events_returns_complete_array_or_explicit_overflow(
    db_session: AsyncSession,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
    owned_count: int,
) -> None:
    owner = await user_factory()
    other_user = await user_factory()
    base = datetime.now(UTC) + timedelta(days=1)
    owner_qr_secret = f"fixture-{uuid.uuid4().hex}"
    owner_qr_hmac = f"fixture-{uuid.uuid4().hex}"
    other_qr_secret = f"fixture-{uuid.uuid4().hex}"
    other_qr_hmac = f"fixture-{uuid.uuid4().hex}"

    owned_events: list[Event] = []
    for index in range(owned_count):
        # The group near the response limit exercises the ID tie-break.
        minute = 98 if 98 <= index <= 101 else index
        starts_at = base + timedelta(minutes=minute)
        owned_events.append(
            Event(
                id=uuid.UUID(int=20_000 + index),
                title=f"Owned {index}",
                created_at=base + timedelta(minutes=index),
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=1),
                created_by=owner.id,
                is_active=True,
            )
        )
    outsider_event = Event(
        id=uuid.UUID(int=99_999),
        title="Outsider only",
        created_at=base,
        starts_at=base,
        ends_at=base + timedelta(hours=1),
        created_by=other_user.id,
        is_active=True,
    )
    db_session.add_all([*owned_events, outsider_event])
    await db_session.flush()
    db_session.add_all(
        [
            models.EventAttendance(
                event_id=event.id,
                user_id=owner.id,
                qr_secret=owner_qr_secret,
                qr_hmac=owner_qr_hmac,
            )
            for event in owned_events
        ]
        + [
            models.EventAttendance(
                event_id=outsider_event.id,
                user_id=other_user.id,
                qr_secret=other_qr_secret,
                qr_hmac=other_qr_hmac,
            )
        ]
    )
    await db_session.flush()

    repository = EventRepository(db_session)
    original_list = repository.list_user_attended_events
    observed_pages: list[tuple[uuid.UUID, dict[str, Any], int]] = []

    async def observe_page(
        user_id: uuid.UUID | int | str, **kwargs: Any
    ) -> list[tuple[Event, models.EventAttendance, int]]:
        rows = await original_list(user_id, **kwargs)
        observed_pages.append((uuid.UUID(str(user_id)), kwargs, len(rows)))
        return rows

    monkeypatch.setattr(repository, "list_user_attended_events", observe_page)
    service = EventService(
        cast(Any, SimpleNamespace(events=repository)), cast(VectorService, None)
    )
    ordered_events = sorted(owned_events, key=lambda event: (event.starts_at, event.id))

    with patch(
        "app.services.event_service.attendance_tokens.issue_token",
        side_effect=lambda attendance: f"qr-{attendance.user_id}",
    ) as issue_token:
        if owned_count > 100:
            with pytest.raises(MyEventsPaginationRequired):
                await service.get_my_events(owner.id, locale="en")
            issue_token.assert_not_called()
            result = None
        else:
            result = await service.get_my_events(owner.id, locale="en")

    if result is not None:
        assert [item.id for item in result] == [event.id for event in ordered_events]
        assert len(result) == owned_count
        assert all(item.is_registered is True for item in result)
        assert all(item.participant_count == 0 for item in result)
        assert all(item.files == [] for item in result)
        assert all(item.my_qr_token == f"qr-{owner.id}" for item in result)
        assert outsider_event.id not in {item.id for item in result}

    assert [size for _, _, size in observed_pages] == [min(owned_count, 101)]
    assert all(user_id == owner.id for user_id, _, _ in observed_pages)
    assert all(kwargs["limit"] == 101 for _, kwargs, _ in observed_pages)
    assert all(kwargs["sort"] == "newest" for _, kwargs, _ in observed_pages)
    assert all(
        kwargs["include_participant_count"] is False for _, kwargs, _ in observed_pages
    )
    assert [kwargs["cursor_key"] for _, kwargs, _ in observed_pages] == [None]


@pytest.mark.asyncio
async def test_legacy_my_events_checks_overflow_before_qr_or_serialization() -> None:
    owner_id = uuid.uuid4()
    event = SimpleNamespace(id=uuid.uuid4(), starts_at=datetime.now(UTC))
    attendance = SimpleNamespace(user_id=owner_id)
    repeated_rows = [(event, attendance, 0)] * 101
    repository = SimpleNamespace(
        list_user_attended_events=AsyncMock(return_value=repeated_rows)
    )
    service = EventService(
        cast(Any, SimpleNamespace(events=repository)), cast(VectorService, None)
    )
    service.serialize_event = MagicMock(return_value=None)

    with (
        patch(
            "app.services.event_service.attendance_tokens.issue_token",
            return_value="unused-test-token",
        ) as issue_token,
        pytest.raises(MyEventsPaginationRequired),
    ):
        await service.get_my_events(owner_id, locale="en")

    repository.list_user_attended_events.assert_awaited_once()
    issue_token.assert_not_called()
    service.serialize_event.assert_not_called()
