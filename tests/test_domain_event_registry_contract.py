"""Every outbox event type the application records must be dispatchable.

``SecureAuditService.record_domain_event`` stores rows in ``stored_events`` as
``pending``; the polling ``OutboxWorker`` then reconstructs them through
``app.core.events._EVENT_REGISTRY`` and fails closed on an unknown type. An
unregistered type therefore turns every such write into a permanently failed
outbox row.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.events import _EVENT_REGISTRY
from app.workers.outbox import OutboxWorker

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _recorded_event_types() -> dict[str, list[str]]:
    """Map each literal ``event_type`` passed to ``record_domain_event`` to its sources."""
    found: dict[str, list[str]] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", None)
            )
            if name != "record_domain_event":
                continue
            for keyword in node.keywords:
                if keyword.arg == "event_type":
                    assert isinstance(keyword.value, ast.Constant), (
                        f"{path}:{node.lineno} must pass a literal event_type"
                    )
                    location = f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}"
                    found.setdefault(str(keyword.value.value), []).append(location)
    return found


def test_scan_finds_the_known_recorders() -> None:
    recorded = _recorded_event_types()
    assert {"SCHEDULE_CREATED", "SCHEDULE_UPDATED", "SCHEDULE_DELETED"} <= set(recorded)


def test_every_recorded_event_type_is_registered() -> None:
    unregistered = {
        event_type: sources
        for event_type, sources in _recorded_event_types().items()
        if event_type not in _EVENT_REGISTRY
    }
    assert unregistered == {}


@pytest.mark.asyncio
async def test_outbox_dispatches_a_recorded_schedule_deletion() -> None:
    schedule_id = uuid.uuid4()
    stored = MagicMock()
    stored.id = uuid.uuid4()
    stored.event_type = "SCHEDULE_DELETED"
    stored.payload = {"deleted": True, "subject": "Physics"}
    stored.metadata_ = None
    stored.aggregate_id_uuid = schedule_id
    stored.sequence_number = 2
    stored.aggregate_type = "schedule"
    bus = AsyncMock()

    with patch("app.workers.outbox.event_bus", bus):
        await OutboxWorker()._dispatch_event(stored)

    event = bus.publish.await_args.args[0]
    assert event.EVENT_TYPE == "SCHEDULE_DELETED"
    assert event.subject == "Physics"


def test_schedule_deletion_rebuilds_from_a_stored_payload() -> None:
    from app.core.events import ScheduleDeleted

    event = ScheduleDeleted.from_dict(
        {
            "_schema_version": 1,
            "schedule_id": "s-1",
            "subject": "Physics",
            "group_id": "g-1",
            "previous_state": {"room": "101"},
            "unexpected": "ignored",
        }
    )

    assert (event.schedule_id, event.subject, event.group_id) == (
        "s-1",
        "Physics",
        "g-1",
    )
    assert event.previous_state == {"room": "101"}
    assert event.deleted is True
    assert not hasattr(event, "unexpected")


@pytest.mark.parametrize(
    "event_type", ["NOTIFICATION_DEAD_LETTER_RETRY", "NOTIFICATION_DEAD_LETTER_PURGE"]
)
def test_dead_letter_audit_events_rebuild_their_batch_count(event_type: str) -> None:
    event_cls = _EVENT_REGISTRY[event_type]

    assert (
        event_cls.from_dict({"_schema_version": 1, "batch_count": "3"}).batch_count == 3
    )
    assert event_cls.from_dict({}).batch_count == 0
    assert event_cls.EVENT_TYPE == event_type
