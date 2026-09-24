"""Schedule mutations must record JSON-safe, hash-chained outbox payloads.

``SecureAuditService.canonicalize_event_payload`` hashes the payload with plain
``json.dumps``, and ``stored_events.payload`` is a JSON column, so datetime
values from ``ScheduleDTO`` must be serialized before they are recorded.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app import models
from app.core.database import async_session
from app.models.domain_events import StoredEvent
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services.schedule_service import ScheduleService

START = dt.datetime(2026, 9, 28, 9, 0, tzinfo=dt.UTC)
END = dt.datetime(2026, 9, 28, 10, 30, tzinfo=dt.UTC)


def _instant(value: str) -> dt.datetime:
    """Parse an ISO timestamp; SQLite drops the offset that PostgreSQL keeps."""
    parsed = dt.datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def _service(db) -> ScheduleService:
    optimizer = AsyncMock()
    optimizer.detect_conflicts.return_value = []
    return ScheduleService(uow_from_session(db), optimizer)


async def _payloads(db, schedule_id) -> dict[str, dict]:
    rows = await db.execute(
        select(StoredEvent).where(StoredEvent.aggregate_id == str(schedule_id))
    )
    return {row.event_type: row.payload for row in rows.scalars()}


@pytest.mark.asyncio
async def test_schedule_create_update_and_delete_record_json_payloads() -> None:
    async with async_session() as db:
        group = models.Group(name="AUDIT-PAYLOAD-1")
        db.add(group)
        await db.commit()
        group_id = group.id
        service = _service(db)

        created = await service.create_schedule(
            schemas.ScheduleCreate(
                group_id=group.id,
                subject="Physics",
                teacher="Dr. Curie",
                room="101",
                weekday="monday",
                start_time=START,
                end_time=END,
            ),
            locale="en",
        )
        await service.update_schedule(
            created.id,
            schemas.ScheduleUpdate(
                room="202",
                start_time=START + dt.timedelta(hours=1),
                end_time=END + dt.timedelta(hours=1),
            ),
        )
        assert await service.delete_schedule(created.id) is True
        assert await db.get(models.Schedule, created.id) is None
        assert await service.delete_schedule(created.id) is False

        payloads = await _payloads(db, created.id)
        aggregate_types = set(
            (
                await db.execute(
                    select(StoredEvent.aggregate_type).where(
                        StoredEvent.aggregate_id == str(created.id)
                    )
                )
            ).scalars()
        )

    assert set(payloads) == {"SCHEDULE_CREATED", "SCHEDULE_UPDATED", "SCHEDULE_DELETED"}
    assert aggregate_types == {"schedule"}
    for payload in payloads.values():
        json.dumps(payload)
    assert _instant(payloads["SCHEDULE_CREATED"]["start_time"]) == START
    updated = payloads["SCHEDULE_UPDATED"]
    assert updated["previous_state"]["room"] == "101"
    assert _instant(updated["previous_state"]["start_time"]) == START
    assert updated["current_state"]["room"] == "202"
    later = START + dt.timedelta(hours=1)
    assert _instant(updated["current_state"]["start_time"]) == later
    deleted = payloads["SCHEDULE_DELETED"]
    assert set(deleted) == {
        "schedule_id",
        "deleted",
        "subject",
        "group_id",
        "previous_state",
    }
    assert deleted["schedule_id"] == str(created.id)
    assert deleted["deleted"] is True
    assert deleted["subject"] == "Physics"
    assert deleted["group_id"] == str(group_id)
    assert deleted["previous_state"]["room"] == "202"


@pytest.mark.asyncio
async def test_recorded_schedule_payloads_rebuild_the_notified_events() -> None:
    """The outbox keeps only dataclass fields; the handler needs id and snapshots."""
    from app.core.events import ScheduleDeleted, ScheduleUpdated
    from app.workers.outbox import OutboxWorker

    async with async_session() as db:
        group = models.Group(name="AUDIT-PAYLOAD-2")
        db.add(group)
        await db.commit()
        service = _service(db)
        created = await service.create_schedule(
            schemas.ScheduleCreate(
                group_id=group.id,
                subject="Chemistry",
                weekday="tuesday",
                start_time=START,
                end_time=END,
            ),
            locale="en",
        )
        await service.update_schedule(created.id, schemas.ScheduleUpdate(room="303"))
        await service.delete_schedule(created.id)
        rows = await db.execute(
            select(StoredEvent).where(StoredEvent.aggregate_id == str(created.id))
        )
        stored = {row.event_type: row for row in rows.scalars()}

    published: list[object] = []
    bus = AsyncMock()
    bus.publish.side_effect = published.append
    with patch("app.workers.outbox.event_bus", bus):
        for event_type in ("SCHEDULE_UPDATED", "SCHEDULE_DELETED"):
            await OutboxWorker()._dispatch_event(stored[event_type])

    updated, deleted = published
    assert isinstance(updated, ScheduleUpdated)
    assert updated.schedule_id == str(created.id)
    assert updated.previous_state["room"] is None
    assert updated.current_state["room"] == "303"
    assert isinstance(deleted, ScheduleDeleted)
    assert deleted.schedule_id == str(created.id)
    assert deleted.previous_state["room"] == "303"
