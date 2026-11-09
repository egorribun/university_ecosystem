"""Worker Sentry scrubbing and task UUID serialization for the NATS broker."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core import nats_broker as nats_module


def test_worker_event_without_top_level_stacktrace_keeps_its_shape() -> None:
    """A Sentry event that carries only exception frames gains no stacktrace key."""
    broker_frame: dict[str, Any] = {
        "module": nats_module.__name__,
        "function": "run_worker",
        "lineno": 7,
        "vars": {"batch": "raw-task-batch"},
    }
    event: Any = {
        "message": "task failed",
        "exception": {
            "values": [
                {"type": "RuntimeError", "stacktrace": {"frames": [broker_frame]}},
            ]
        },
    }

    protected = nats_module._worker_error_event_without_broker_vars(event, {})

    assert "stacktrace" not in protected
    assert "stacktrace" not in event
    assert protected["message"] == "task failed"
    frame = protected["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert frame is not broker_frame
    assert "vars" not in frame
    assert frame["function"] == "run_worker"
    assert frame["lineno"] == 7
    # The incoming event keeps its broker-frame locals; only the copy is scrubbed.
    assert event["exception"]["values"][0]["stacktrace"]["frames"][0] is broker_frame
    assert broker_frame["vars"] == {"batch": "raw-task-batch"}


def test_task_uuid_serializer_accepts_only_uuids() -> None:
    """Task JSON receives the canonical UUID text and nothing else is serialized."""
    value = uuid.uuid4()

    assert nats_module._serialize_task_uuid(value) == str(value)
    with pytest.raises(TypeError, match="not JSON serializable"):
        nats_module._serialize_task_uuid(object())
