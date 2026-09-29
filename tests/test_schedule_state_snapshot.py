"""The schedule snapshot recorded in domain events is exact and JSON-safe."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time

from app.schemas.dtos.schedule import ScheduleDTO
from app.services.schedule_service import schedule_state


def test_snapshot_lists_every_recorded_field_in_json_form() -> None:
    group_id = uuid.uuid4()
    schedule = ScheduleDTO(
        id=uuid.uuid4(),
        group_id=group_id,
        weekday="monday",
        start_time=datetime(2026, 9, 28, 9, 0, tzinfo=UTC),
        end_time=time(10, 30),
        subject="Physics",
        teacher="Dr. Curie",
        room="101",
        parity="odd",
        lesson_type="lecture",
    )

    state = schedule_state(schedule)

    assert state == {
        "group_id": str(group_id),
        "subject": "Physics",
        "teacher": "Dr. Curie",
        "room": "101",
        "weekday": "monday",
        "start_time": "2026-09-28T09:00:00+00:00",
        "end_time": "10:30:00",
        "parity": "odd",
        "lesson_type": "lecture",
    }
    assert json.loads(json.dumps(state)) == state
