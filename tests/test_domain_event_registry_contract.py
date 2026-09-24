"""Every outbox event type the application records must be dispatchable.

``SecureAuditService.record_domain_event`` stores rows in ``stored_events`` as
``pending``; the polling ``OutboxWorker`` then reconstructs them through
``app.core.events._EVENT_REGISTRY`` and fails closed on an unknown type. An
unregistered type therefore turns every such write into a permanently failed
outbox row.
"""

from __future__ import annotations

import ast
import os
import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.events import _EVENT_REGISTRY
from app.workers.outbox import OutboxWorker

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


_MUTANT_FUNCTION = re.compile(r"__mutmut_\d+$")


def _active_mutant() -> str:
    """Name of the mutmut variant under test, or an empty string."""
    return os.environ.get("MUTANT_UNDER_TEST", "").rpartition(".")[2]


class _RecorderScan(ast.NodeVisitor):
    """Collect literal ``record_domain_event`` event types from live code.

    mutmut rewrites each mutated module with one sibling function per mutant.
    Those inactive variants are not executable code, so they are skipped;
    the original and the variant currently under test are scanned.
    """

    def __init__(self, location: str, found: dict[str, list[str]]) -> None:
        self.location = location
        self.found = found

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if _MUTANT_FUNCTION.search(node.name) and node.name != _active_mutant():
            return
        self.generic_visit(node)

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = (
            func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        )
        if name == "record_domain_event":
            for keyword in node.keywords:
                if keyword.arg == "event_type":
                    assert isinstance(keyword.value, ast.Constant), (
                        f"{self.location}:{node.lineno} must pass a literal event_type"
                    )
                    self.found.setdefault(str(keyword.value.value), []).append(
                        f"{self.location}:{node.lineno}"
                    )
        self.generic_visit(node)


def _recorded_event_types() -> dict[str, list[str]]:
    """Map each literal ``event_type`` passed to ``record_domain_event`` to its sources."""
    found: dict[str, list[str]] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        _RecorderScan(str(path.relative_to(APP_ROOT.parent)), found).visit(tree)
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


def test_scan_ignores_inactive_mutmut_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    source = """
def record__mutmut_orig(audit):
    audit.record_domain_event(event_type="REAL")

def record__mutmut_1(audit):
    audit.record_domain_event(event_type="XXREALXX")

def record__mutmut_2(audit):
    audit.record_domain_event(event_type="OTHER")
"""
    tree = ast.parse(source)

    monkeypatch.delenv("MUTANT_UNDER_TEST", raising=False)
    inactive: dict[str, list[str]] = {}
    _RecorderScan("m.py", inactive).visit(tree)
    assert set(inactive) == {"REAL"}

    monkeypatch.setenv("MUTANT_UNDER_TEST", "app.m.record__mutmut_2")
    active: dict[str, list[str]] = {}
    _RecorderScan("m.py", active).visit(tree)
    assert set(active) == {"REAL", "OTHER"}
