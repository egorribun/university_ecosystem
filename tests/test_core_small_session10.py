"""Coverage tests for three small core/service modules (testing session 10).

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

import asyncio
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

import app.core.orjson_utils as orjson_utils_module
import app.services.mfa_challenge_cleanup as mfa_cleanup_module
from app.core.etag import ETagMiddleware, compute_etag, format_etag
from app.services.mfa_challenge_cleanup import (
    MfaChallengeCleanupConfig,
    start_mfa_challenge_cleanup_scheduler,
)

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
# 2. app/core/etag.py — ETagMiddleware.__init__ + dispatch (88-89, 95-142)
# ---------------------------------------------------------------------------


def _build_request(
    *,
    method: str = "GET",
    path: str = "/api/v1/items",
    if_none_match: str | None = None,
) -> Request:
    """Minimal ASGI ``Request`` mirroring tests/test_cached_endpoint.py."""
    headers: list[tuple[bytes, bytes]] = []
    if if_none_match is not None:
        headers.append((b"if-none-match", if_none_match.encode("latin-1")))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("latin-1"),
        "headers": headers,
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)  # type: ignore[arg-type]


def _middleware(**kwargs: Any) -> ETagMiddleware:
    async def _app(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
        raise AssertionError("ASGI app must not be invoked in direct dispatch tests")

    return ETagMiddleware(_app, **kwargs)


def _next(response: Any) -> Any:
    async def call_next(_request: Request) -> Any:
        return response

    return call_next


def test_init_stores_custom_skip_paths() -> None:
    mw = _middleware(skip_paths=("/custom",))
    assert mw.skip_paths == ("/custom",)
    # Default skip paths preserved when not overridden.
    assert "/healthz" in _middleware().skip_paths


@pytest.mark.asyncio
async def test_dispatch_non_get_request_passes_through() -> None:
    sentinel = Response(content=b"{}", media_type="application/json")
    out = await _middleware().dispatch(_build_request(method="POST"), _next(sentinel))
    assert out is sentinel
    assert "etag" not in out.headers


@pytest.mark.asyncio
async def test_dispatch_skip_path_passes_through() -> None:
    sentinel = Response(content=b"{}", media_type="application/json")
    out = await _middleware().dispatch(_build_request(path="/healthz"), _next(sentinel))
    assert out is sentinel
    assert "etag" not in out.headers


@pytest.mark.asyncio
async def test_dispatch_non_200_response_passes_through() -> None:
    sentinel = Response(
        content=b'{"detail":"missing"}',
        status_code=404,
        media_type="application/json",
    )
    out = await _middleware().dispatch(_build_request(), _next(sentinel))
    assert out is sentinel
    assert "etag" not in out.headers


@pytest.mark.asyncio
async def test_dispatch_non_json_response_passes_through() -> None:
    sentinel = Response(content=b"<html></html>", media_type="text/html")
    out = await _middleware().dispatch(_build_request(), _next(sentinel))
    assert out is sentinel
    assert "etag" not in out.headers


@pytest.mark.asyncio
async def test_dispatch_streaming_response_skipped() -> None:
    # PERF-W19-09: StreamingResponse must not be buffered for ETag hashing.
    streaming = StreamingResponse(iter([b"{}"]), media_type="application/json")
    out = await _middleware().dispatch(_build_request(), _next(streaming))
    assert out is streaming
    assert "etag" not in out.headers


@pytest.mark.asyncio
async def test_dispatch_response_without_body_attribute_passes_through() -> None:
    class _NoBody:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}

    sentinel = _NoBody()
    out = await _middleware().dispatch(_build_request(), _next(sentinel))
    assert out is sentinel


@pytest.mark.asyncio
async def test_dispatch_adds_etag_to_json_response() -> None:
    body = b'{"a":1}'
    response = Response(content=body, media_type="application/json")
    out = await _middleware().dispatch(_build_request(), _next(response))
    assert out.status_code == 200
    assert out.body == body
    assert out.headers["etag"] == format_etag(compute_etag(body))
    assert "application/json" in out.headers["content-type"]


@pytest.mark.asyncio
async def test_dispatch_matching_if_none_match_returns_304() -> None:
    body = b'{"a":1}'
    etag = format_etag(compute_etag(body))
    response = Response(content=body, media_type="application/json")
    out = await _middleware().dispatch(
        _build_request(if_none_match=etag), _next(response)
    )
    assert out.status_code == 304
    assert out.body == b""
    assert out.headers["etag"] == etag


@pytest.mark.asyncio
async def test_dispatch_weak_if_none_match_matches() -> None:
    # RFC 7232 weak comparison: W/"<tag>" matches the strong ETag we compute.
    body = b'{"a":1}'
    weak = f'W/"{compute_etag(body)}"'
    response = Response(content=body, media_type="application/json")
    out = await _middleware().dispatch(
        _build_request(if_none_match=weak), _next(response)
    )
    assert out.status_code == 304


@pytest.mark.asyncio
async def test_dispatch_non_matching_if_none_match_returns_full_body() -> None:
    body = b'{"a":1}'
    response = Response(content=body, media_type="application/json")
    out = await _middleware().dispatch(
        _build_request(if_none_match='"deadbeef"'), _next(response)
    )
    assert out.status_code == 200
    assert out.body == body


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


def test_config_normalization_clamps_interval_and_grace() -> None:
    cfg = MfaChallengeCleanupConfig(interval_seconds=5, grace_period_seconds=-10)
    assert cfg.normalized_interval() == 30  # floor of 30 seconds
    assert cfg.normalized_grace_period() == 0  # never negative (line 39)
    cfg2 = MfaChallengeCleanupConfig(interval_seconds=120, grace_period_seconds=45)
    assert cfg2.normalized_interval() == 120
    assert cfg2.normalized_grace_period() == 45


@pytest.mark.asyncio
async def test_scheduler_runs_cleanup_then_stop_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: one loop iteration runs, then _stop() cancels the sleeper."""
    fake_metrics = _FakeMetrics()
    monkeypatch.setattr(mfa_cleanup_module, "_METRICS", fake_metrics)
    cleanup = AsyncMock(return_value=3)
    monkeypatch.setattr(mfa_cleanup_module, "cleanup_stale_mfa_challenges", cleanup)

    # Explicit config exercises the `config or ...` left branch + clamping.
    config = MfaChallengeCleanupConfig(interval_seconds=0, grace_period_seconds=-7)
    stop = await start_mfa_challenge_cleanup_scheduler(config=config)
    await asyncio.sleep(0.05)  # let the first loop iteration complete

    cleanup.assert_awaited_with(grace_period_seconds=0)
    assert fake_metrics.run.deleted == 3

    # Task is parked in asyncio.sleep(30) — _stop() cancels and awaits it.
    await stop()


@pytest.mark.asyncio
async def test_cancel_during_cleanup_hits_inner_cancelled_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling while cleanup is mid-flight exercises the inner
    ``except asyncio.CancelledError: raise`` re-raise (line 95)."""
    fake_metrics = _FakeMetrics()
    monkeypatch.setattr(mfa_cleanup_module, "_METRICS", fake_metrics)
    started = asyncio.Event()

    async def _blocking(**_kwargs: object) -> int:
        started.set()
        await asyncio.sleep(3600)  # parked here until the task is cancelled
        return 0  # pragma: no cover - never reached

    monkeypatch.setattr(mfa_cleanup_module, "cleanup_stale_mfa_challenges", _blocking)

    stop = await start_mfa_challenge_cleanup_scheduler()
    await asyncio.wait_for(started.wait(), timeout=2)

    # Cancellation propagates from inside the inner try: inner re-raise (95)
    # → outer CancelledError handler (100-102) → _stop awaits the task.
    await stop()


@pytest.mark.asyncio
async def test_stop_after_loop_crash_swallows_task_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the loop dies with a non-network error, _stop() hits the
    ``task.done()`` branch and suppresses the retrieved exception."""
    fake_metrics = _FakeMetrics()
    monkeypatch.setattr(mfa_cleanup_module, "_METRICS", fake_metrics)
    crashed = asyncio.Event()

    async def _boom(**_kwargs: object) -> int:
        crashed.set()
        raise ValueError("boom")

    monkeypatch.setattr(mfa_cleanup_module, "cleanup_stale_mfa_challenges", _boom)

    # config=None exercises the `config or MfaChallengeCleanupConfig()` branch.
    stop = await start_mfa_challenge_cleanup_scheduler()
    await asyncio.wait_for(crashed.wait(), timeout=2)
    await asyncio.sleep(0.05)  # let the ValueError finish the task

    # task.done() → task.result() raises ValueError → suppress(Exception).
    await stop()
