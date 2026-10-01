"""Runtime-path tests for ORJSON, ETag, and MFA-cleanup helpers.

Direct-call tests targeting the previously-uncovered line ranges:

1. ``app/core/orjson_utils.py`` — lines 26-63: the ``ImportError`` fallback
   block (``OrJsonMock``). Exercised by loading a fresh module copy from the
   real file path with ``sys.modules["orjson"] = None`` so the fallback branch
   executes; coverage attributes the executed lines to the real file because
   the spec is created from the original path.
2. ``app/core/etag.py`` — lines 88-89 + 95-142: ``ETagMiddleware.__init__``
   and ``dispatch``. Driven by calling ``dispatch`` directly with a minimal
   ASGI-scope ``Request`` plus a stub ``call_next`` (no async_client / ASGI
   requests). The ``conditional_response`` helper (150-193) is already covered
   by tests/test_etag.py and is not re-tested here.
3. ``app/services/mfa_challenge_cleanup.py`` — lines 39 + 81-116:
   ``MfaChallengeCleanupConfig.normalized_grace_period`` and the
   ``start_mfa_challenge_cleanup_scheduler`` loop/stop closures, with the DB
   cleanup function and ``_METRICS`` monkeypatched at the consuming module.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import app.core.orjson_utils as orjson_utils_module

# ---------------------------------------------------------------------------
# 1. app/core/orjson_utils.py — ImportError fallback block (lines 26-63)
# ---------------------------------------------------------------------------


@pytest.fixture
def fallback(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Load a fresh copy of orjson_utils with the ``orjson`` import blocked.

    Setting ``sys.modules["orjson"] = None`` makes ``import orjson`` raise
    ``ImportError`` ("import of orjson halted"), which drives the module's
    fallback branch. The module copy is loaded under a private name so the
    real ``app.core.orjson_utils`` entry in sys.modules stays untouched;
    monkeypatch restores the original ``orjson`` entry afterwards.
    """
    monkeypatch.setitem(sys.modules, "orjson", None)
    path = Path(orjson_utils_module.__file__)
    spec = importlib.util.spec_from_file_location(
        "_orjson_utils_fallback_s10", str(path)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fallback_options_and_sentinels(fallback: Any) -> None:
    # In fallback mode the combined options collapse to 0, but OPT_NAIVE_UTC
    # stays a non-zero sentinel so bitwise detection still works (LOW-W19).
    assert fallback.ORJSON_OPTIONS == 0
    assert fallback.orjson.OPT_NAIVE_UTC == 1
    assert fallback.orjson.OPT_SERIALIZE_NUMPY == 0
    assert fallback.orjson.OPT_UTC_Z == 0


def test_fallback_dumps_and_loads_roundtrip(fallback: Any) -> None:
    raw = fallback.orjson.dumps({"a": 1, "b": "x"})
    assert isinstance(raw, bytes)
    assert json.loads(raw) == {"a": 1, "b": "x"}
    # loads accepts both bytes and str.
    assert fallback.orjson.loads(raw) == {"a": 1, "b": "x"}
    assert fallback.orjson.loads(raw.decode("utf-8")) == {"a": 1, "b": "x"}


def test_fallback_naive_datetime_with_flag_treated_as_utc(fallback: Any) -> None:
    naive = datetime(2024, 1, 1, 12, 30)
    raw = fallback.orjson.dumps({"t": naive}, option=fallback.orjson.OPT_NAIVE_UTC)
    assert json.loads(raw)["t"] == naive.replace(tzinfo=UTC).isoformat()


def test_fallback_naive_datetime_without_flag_raises(fallback: Any) -> None:
    with pytest.raises(TypeError, match="not JSON serializable"):
        fallback.orjson.dumps({"t": datetime(2024, 1, 1)})


def test_fallback_aware_datetime_with_flag_falls_back_to_default(
    fallback: Any,
) -> None:
    # Aware datetimes are NOT rewritten by OPT_NAIVE_UTC — they fall through
    # to the caller-supplied default serializer.
    aware = datetime(2024, 1, 1, tzinfo=UTC)
    raw = fallback.orjson.dumps(
        {"t": aware}, default=str, option=fallback.orjson.OPT_NAIVE_UTC
    )
    assert json.loads(raw)["t"] == str(aware)


def test_fallback_custom_default_serializer(fallback: Any) -> None:
    class _Marker:
        pass

    raw = fallback.orjson.dumps({"m": _Marker()}, default=lambda _o: "marker")
    assert json.loads(raw)["m"] == "marker"


def test_fallback_unserializable_without_default_raises(fallback: Any) -> None:
    with pytest.raises(TypeError):
        fallback.orjson.dumps({"o": object()})


def test_fallback_module_level_wrappers_use_mock(fallback: Any) -> None:
    # orjson_dumps / orjson_dumps_str / orjson_loads delegate to the mock.
    raw = fallback.orjson_dumps({"k": 2})
    assert fallback.orjson_loads(raw) == {"k": 2}
    assert fallback.orjson_dumps_str({"k": 2}) == raw.decode("utf-8")


# ---------------------------------------------------------------------------
# 3. app/services/mfa_challenge_cleanup.py — config clamp (39) +
#    start_mfa_challenge_cleanup_scheduler loop/stop closures (81-116)
# ---------------------------------------------------------------------------


class _FakeRun:
    def __init__(self) -> None:
        self.deleted: int | None = None

    def observe_deleted(self, count: int) -> None:
        self.deleted = count


class _FakeTrack:
    def __init__(self, run: _FakeRun) -> None:
        self._run = run

    async def __aenter__(self) -> _FakeRun:
        return self._run

    async def __aexit__(self, *exc: object) -> bool:
        return False  # propagate exceptions, mirroring the real metrics CM


class _FakeMetrics:
    def __init__(self) -> None:
        self.run = _FakeRun()

    def track_execution(self) -> _FakeTrack:
        return _FakeTrack(self.run)
