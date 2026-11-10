"""The exact-row deferral receipt never renders inherited private context."""

import io
import json
import logging
import runpy
import sys
from pathlib import Path

import pytest

from app.core import logging as logging_mod

pytest_plugins = ("pytester",)
pytestmark = pytest.mark.usefixtures("preserve_logging_configuration")
EVENT_ID = "10000000-0000-4000-8000-000000000005"


@pytest.fixture(params=[True, False], ids=["json", "console"])
def diagnostic_stream(monkeypatch, request):
    stream = io.StringIO()
    monkeypatch.setattr(
        logging.getLogger(), "handlers", [logging.StreamHandler(stream)]
    )
    monkeypatch.setattr(logging.getLogger(), "level", logging.INFO)
    monkeypatch.setattr(
        logging.getLogger("app.workers.outbox"), "level", logging.NOTSET
    )
    monkeypatch.setattr(logging_mod, "_configured", False)
    logging_mod.configure_logging(json_output=request.param)
    return stream


def test_deferred_receipt_is_exact_row_only(diagnostic_stream):
    logging_mod.get_logger("app.workers.outbox").bind(
        payload="private-content", user_id="private-user", exception="private-exception"
    ).info("outbox_event_deferred", stored_event_id=EVENT_ID)
    assert json.loads(diagnostic_stream.getvalue()) == {
        "message": "outbox_event_deferred",
        "logger": "app.workers.outbox",
        "stored_event_id": EVENT_ID,
    }
    assert set(logging_mod.OUTBOX_DEFERRED_DIAGNOSTIC_FIELDS) == {
        "message",
        "logger",
        "stored_event_id",
    }


@pytest.mark.parametrize("event_id", [None, 3, "private-content", "", "x" + EVENT_ID])
def test_invalid_identifier_is_omitted(diagnostic_stream, event_id):
    logging_mod.get_logger("app.workers.outbox").info(
        "outbox_event_deferred", stored_event_id=event_id
    )
    assert json.loads(diagnostic_stream.getvalue()) == {
        "message": "outbox_event_deferred",
        "logger": "app.workers.outbox",
    }


@pytest.mark.parametrize(
    ("logger", "message"),
    [("app.other", "outbox_event_deferred"), ("app.workers.outbox", "other_event")],
)
def test_other_events_keep_normal_rendering(diagnostic_stream, logger, message):
    logging_mod.get_logger(logger).info(message, ordinary="kept")
    assert "kept" in diagnostic_stream.getvalue()


def test_module_entrypoint_keeps_canonical_diagnostic_logger(
    diagnostic_stream, monkeypatch
):
    from app.workers import outbox

    # Execute the real module as __main__, but close its startup coroutine
    # instead of contacting the database, NATS, or signal APIs.
    monkeypatch.setattr("asyncio.run", lambda coroutine: coroutine.close())
    namespace = runpy.run_path(outbox.__file__, run_name="__main__")
    namespace["_deferred_logger"].info(
        "outbox_event_deferred", stored_event_id=EVENT_ID
    )
    assert namespace["__name__"] == "__main__"
    assert json.loads(diagnostic_stream.getvalue()) == {
        "message": "outbox_event_deferred",
        "logger": "app.workers.outbox",
        "stored_event_id": EVENT_ID,
    }


def test_cold_worker_startup_initializes_closed_json_logging(pytester, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "app/workers/outbox.py"
    probe = r"""
import contextlib
import io
import json
import runpy
import sys
import structlog
from unittest.mock import patch
from app.core import database

class StopBeforeDatabase(Exception):
    pass

def stop_before_database():
    assert structlog.is_configured()
    sys.modules["__main__"]._deferred_logger.bind(
        payload="private-content"
    ).info(
        "outbox_event_deferred",
        stored_event_id="10000000-0000-4000-8000-000000000005",
    )
    raise StopBeforeDatabase

assert not structlog.is_configured()
output = io.StringIO()
with patch.object(database, "init_database", stop_before_database), \
     patch("pathlib.Path.mkdir"), patch("pathlib.Path.unlink"), \
     contextlib.redirect_stdout(output):
    try:
        runpy.run_path(sys.argv[1], run_name="__main__")
    except StopBeforeDatabase:
        pass
    else:
        raise AssertionError("startup must stop before database or NATS I/O")
record = json.loads(output.getvalue())
assert record == {
    "message": "outbox_event_deferred",
    "logger": "app.workers.outbox",
    "stored_event_id": "10000000-0000-4000-8000-000000000005",
}, record
print("cold-worker-logging-ok")
"""
    monkeypatch.setenv("PYTHONPATH", str(source.parents[2]))
    result = pytester.run(sys.executable, "-c", probe, str(source), timeout=30)
    assert result.ret == 0, result.stderr.str()
    assert result.stdout.str().strip() == "cold-worker-logging-ok"
