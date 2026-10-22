from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.deps.cache import MemoryCache, RedisCache, TieredCache

_MISSING = object()

# ``app.api.health`` only needs the storage-backend selector from this module.
# Isolating that import keeps this focused endpoint suite independent from the
# optional Pillow native extension used by the upload helpers in ``files.py``.
_files_stub = type(sys)("app.utils.files")
_files_stub._get_storage_backend = lambda: object()
_ORIGINAL_FILES_MODULE = sys.modules.get("app.utils.files", _MISSING)
sys.modules.setdefault("app.utils.files", _files_stub)

from app.api import health
from app.core import health as core_health
from app.services.storage import S3Storage, StaticFSStorage, StorageBackend

if _ORIGINAL_FILES_MODULE is _MISSING:
    sys.modules.pop("app.utils.files", None)
else:
    sys.modules["app.utils.files"] = _ORIGINAL_FILES_MODULE


class _Connection:
    def __init__(self, *, execute_error: BaseException | None = None) -> None:
        self.execute = AsyncMock(side_effect=execute_error)


class _ConnectionContext:
    def __init__(
        self, connection: _Connection, error: BaseException | None = None
    ) -> None:
        self.connection = connection
        self.error = error

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self, context: _ConnectionContext) -> None:
        self.context = context

    def connect(self):
        return self.context


class _ProbeCache:
    enabled = True

    def __init__(self) -> None:
        self.payloads: dict[str, object] = {}
        self.silent_set = False
        self.corrupt_readback = False
        self.set_error: Exception | None = None
        self.get_error: Exception | None = None
        self.invalidate_error: Exception | None = None
        self.get_calls = 0

    async def set(self, key: str, payload: object, ttl: int | None = None) -> None:
        if self.set_error is not None:
            raise self.set_error
        if not self.silent_set:
            self.payloads[key] = payload

    async def get(self, key: str):
        self.get_calls += 1
        if self.get_error is not None:
            raise self.get_error
        payload = self.payloads.get(key)
        if payload is not None and self.corrupt_readback:
            payload = {"status": "unexpected"}
        return None if payload is None else SimpleNamespace(payload=payload)

    async def invalidate(self, key: str) -> None:
        if self.invalidate_error is not None:
            raise self.invalidate_error
        self.payloads.pop(key, None)


class _Storage(StorageBackend):
    def __init__(
        self,
        *,
        exists_value: bool = True,
        exists_error: BaseException | None = None,
        save_error: BaseException | None = None,
        delete_error: BaseException | None = None,
    ) -> None:
        self.exists_value = exists_value
        self.exists_error = exists_error
        self.save_error = save_error
        self.delete_error = delete_error
        self.probe_present = False

    async def exists(self, path: str) -> bool:
        if self.exists_error is not None:
            raise self.exists_error
        if path == "healthz/probe.txt":
            return self.probe_present
        return self.exists_value

    async def save_file(self, relative_path: str, data: bytes, *, content_type=None):
        if self.save_error is not None:
            raise self.save_error
        self.probe_present = True
        return "healthz/probe.txt"

    async def delete_file(self, file_url: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.probe_present = False


def _patch_common(monkeypatch, *, environment: str = "testing"):
    health.reset_health_cache()
    health.reset_storage_probe_cache()
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(
            environment=environment,
            notifications_queue_in_memory_only=False,
            health_storage_probe_enabled=False,
            health_storage_probe_min_interval_seconds=0.0,
            event_file_scanner_enabled=False,
        ),
    )
    monkeypatch.setattr(health, "record_health_probe", MagicMock())
    monkeypatch.setattr(health, "get_pool_health_metrics", lambda: {"size": 3})
    monkeypatch.setattr(
        core_health, "check_spicedb_health", AsyncMock(return_value=("ok", 1.5))
    )


@pytest.mark.asyncio
async def test_liveness_and_readiness_shutdown_paths(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(health, "wait_db", AsyncMock())

    assert await health.liveness() == {"status": "alive"}
    health.reset_shutdown_flag()
    assert await health.ready() == {"status": "ready"}
    health._shutdown_flag.set()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await health.ready()
        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    finally:
        health.reset_shutdown_flag()


def test_shutdown_flag_ignored_in_testing_and_cache_reset(monkeypatch):
    _patch_common(monkeypatch)
    health.reset_shutdown_flag()
    health.set_shutdown_flag()
    assert not health._shutdown_flag.is_set()

    health._health_cache.update(
        {"expires_at": 10, "payload": {"x": 1}, "status_code": 503}
    )
    health._storage_probe_cache.update({"expires_at": 10, "status": "ok", "latency": 2})
    health.reset_health_cache()
    health.reset_storage_probe_cache()
    assert health._health_cache == {
        "expires_at": 0.0,
        "payload": {},
        "status_code": 200,
    }
    assert health._storage_probe_cache == {
        "expires_at": 0.0,
        "status": "unknown",
        "latency": 0.0,
    }

    _patch_common(monkeypatch, environment="production")
    health.reset_shutdown_flag()
    health.set_shutdown_flag()
    assert health._shutdown_flag.is_set()
    health.reset_shutdown_flag()


@pytest.mark.asyncio
async def test_storage_helpers_cover_success_failure_and_type_guard(monkeypatch):
    _patch_common(monkeypatch)
    healthy = _Storage()
    assert await health._lightweight_storage_probe(healthy) == "ok"
    assert (
        await health._lightweight_storage_probe(_Storage(exists_value=False)) == "error"
    )
    assert (
        await health._lightweight_storage_probe(_Storage(exists_error=RuntimeError()))
        == "error"
    )
    assert await health._lightweight_storage_probe(object()) is None

    assert await health._write_delete_storage_probe(healthy) == "ok"
    assert (
        await health._write_delete_storage_probe(_Storage(save_error=RuntimeError()))
        == "error"
    )
    assert (
        await health._write_delete_storage_probe(_Storage(delete_error=RuntimeError()))
        == "error"
    )


@pytest.mark.asyncio
async def test_lightweight_s3_probe_checks_bucket_without_empty_object_key():
    client = AsyncMock()
    backend = S3Storage(bucket="uploads", client=client)

    assert await health._lightweight_storage_probe(backend) == "ok"
    client.head_bucket.assert_awaited_once_with(Bucket="uploads")
    client.head_object.assert_not_awaited()

    client.head_bucket.side_effect = OSError("S3 unavailable")
    assert await health._lightweight_storage_probe(backend) == "error"


@pytest.mark.asyncio
async def test_lightweight_static_probe_checks_storage_directory(tmp_path):
    assert await health._lightweight_storage_probe(StaticFSStorage(tmp_path)) == "ok"
    assert (
        await health._lightweight_storage_probe(StaticFSStorage(tmp_path / "missing"))
        == "error"
    )


@pytest.mark.asyncio
async def test_write_delete_probe_rejects_silently_failed_deletion(tmp_path):
    backend = StaticFSStorage(tmp_path)
    backend.delete_file = AsyncMock(return_value=None)

    assert await health._write_delete_storage_probe(backend) == "error"
    assert len(list((tmp_path / "healthz").glob("*.txt"))) == 1


@pytest.mark.asyncio
async def test_write_delete_probe_rejects_swallowed_s3_delete_error():
    client = AsyncMock()
    client.delete_object.side_effect = ConnectionError("storage unavailable")
    backend = S3Storage(bucket="uploads", client=client)

    assert await health._write_delete_storage_probe(backend) == "error"


@pytest.mark.asyncio
async def test_enabled_storage_probe_keeps_write_delete_error(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(health.settings, "health_storage_probe_enabled", True)
    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())
    monkeypatch.setattr(
        health, "_write_delete_storage_probe", AsyncMock(return_value="error")
    )
    monkeypatch.setattr(
        health, "_lightweight_storage_probe", AsyncMock(return_value="ok")
    )

    assert (await health._probe_storage())[0] == "error"


@pytest.mark.asyncio
async def test_probe_storage_cache_and_fallback_paths(monkeypatch):
    _patch_common(monkeypatch)
    backend = object()
    monkeypatch.setattr(health, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(
        health, "_lightweight_storage_probe", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        health, "_write_delete_storage_probe", AsyncMock(return_value="ok")
    )
    monkeypatch.setattr(health.settings, "health_storage_probe_enabled", True)

    status_value, latency = await health._probe_storage()
    assert status_value == "ok"
    assert latency >= 0
    cached = await health._probe_storage()
    assert cached[0] == "ok"
    assert cached[1] >= 0
    health._storage_probe_cache["expires_at"] = 0.0

    monkeypatch.setattr(
        health, "_write_delete_storage_probe", AsyncMock(return_value="error")
    )
    monkeypatch.setattr(
        health, "_lightweight_storage_probe", AsyncMock(return_value="ok")
    )
    status_value, _ = await health._probe_storage()
    assert status_value == "error"

    health._storage_probe_cache["expires_at"] = 0.0
    monkeypatch.setattr(
        health, "_lightweight_storage_probe", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        health, "_write_delete_storage_probe", AsyncMock(return_value="error")
    )
    status_value, _ = await health._probe_storage()
    assert status_value == "error"

    health._storage_probe_cache["expires_at"] = 0.0
    monkeypatch.setattr(
        health, "_get_storage_backend", MagicMock(side_effect=RuntimeError())
    )
    status_value, _ = await health._probe_storage()
    assert status_value == "error"

    health._storage_probe_cache["expires_at"] = 0.0
    monkeypatch.setattr(health.settings, "health_storage_probe_enabled", False)
    monkeypatch.setattr(health, "_get_storage_backend", lambda: backend)
    status_value, _ = await health._probe_storage()
    assert status_value == "disabled"

    health._storage_probe_cache["expires_at"] = 0.0
    monkeypatch.setattr(
        health, "_lightweight_storage_probe", AsyncMock(return_value="ok")
    )
    status_value, _ = await health._probe_storage()
    assert status_value == "ok"

    health._storage_probe_cache.update(
        {"expires_at": 10**12, "status": "cached", "latency": 0.25}
    )
    status_value, latency = await health._probe_storage()
    assert (status_value, latency) == ("cached", 0.25)


@pytest.mark.asyncio
async def test_storage_probe_uses_short_outcome_ttls_and_recovers(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        health.settings, "health_storage_probe_min_interval_seconds", 3600
    )

    class _Clock:
        now = 100.0

    clock = _Clock()
    monkeypatch.setattr(health.time, "monotonic", lambda: clock.now)
    available = False
    calls = 0

    async def _probe(_backend):
        nonlocal calls
        calls += 1
        return "ok" if available else "error"

    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())
    monkeypatch.setattr(health, "_lightweight_storage_probe", _probe)

    assert (await health._probe_storage())[0] == "error"
    assert health._storage_probe_cache["expires_at"] == 105.0

    clock.now = 104.999
    available = True
    assert (await health._probe_storage())[0] == "error"
    assert calls == 1

    clock.now = 105.0
    assert (await health._probe_storage())[0] == "ok"
    assert health._storage_probe_cache["expires_at"] == 165.0
    assert calls == 2

    clock.now = 164.999
    available = False
    assert (await health._probe_storage())[0] == "ok"
    assert calls == 2

    clock.now = 165.0
    assert (await health._probe_storage())[0] == "error"
    assert health._storage_probe_cache["expires_at"] == 170.0
    assert calls == 3

    clock.now = 169.999
    available = True
    assert (await health._probe_storage())[0] == "error"
    assert calls == 3

    clock.now = 170.0
    assert (await health._probe_storage())[0] == "ok"
    assert health._storage_probe_cache["expires_at"] == 230.0
    assert calls == 4


@pytest.mark.asyncio
async def test_storage_probe_ttl_starts_after_probe_completion(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        health.settings, "health_storage_probe_min_interval_seconds", 10
    )

    class _Clock:
        now = 100.0

    clock = _Clock()
    monkeypatch.setattr(health.time, "monotonic", lambda: clock.now)

    async def _probe(_backend):
        clock.now += 3.0
        return "ok"

    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())
    monkeypatch.setattr(health, "_lightweight_storage_probe", _probe)

    assert (await health._probe_storage())[0] == "ok"
    assert health._storage_probe_cache["expires_at"] == 113.0


@pytest.mark.asyncio
async def test_storage_probe_singleflights_concurrent_misses(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        health.settings, "health_storage_probe_min_interval_seconds", 60
    )
    probe_started = asyncio.Event()
    release_probe = asyncio.Event()
    calls = 0

    async def _probe(_backend):
        nonlocal calls
        calls += 1
        probe_started.set()
        await release_probe.wait()
        return "ok"

    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())
    monkeypatch.setattr(health, "_lightweight_storage_probe", _probe)
    tasks = [asyncio.create_task(health._probe_storage()) for _ in range(8)]
    try:
        await asyncio.wait_for(probe_started.wait(), timeout=2)
        release_probe.set()
        results = await asyncio.gather(*tasks)
    finally:
        release_probe.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert calls == 1
    assert [result[0] for result in results] == ["ok"] * 8


@pytest.mark.asyncio
async def test_zero_ttl_coalesces_waiters_but_not_sequential_probes(monkeypatch):
    _patch_common(monkeypatch)
    probe_started = asyncio.Event()
    all_callers_contending = asyncio.Event()
    release_probe = asyncio.Event()
    calls = 0

    class _ContendedLock(asyncio.Lock):
        requests = 0

        async def acquire(self):
            self.requests += 1
            if self.requests == 8:
                all_callers_contending.set()
            return await super().acquire()

    monkeypatch.setattr(health, "_get_storage_probe_lock", lambda: lock)
    lock = _ContendedLock()

    async def _probe(_backend):
        nonlocal calls
        calls += 1
        probe_started.set()
        await release_probe.wait()
        return "ok"

    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())
    monkeypatch.setattr(health, "_lightweight_storage_probe", _probe)
    tasks = [asyncio.create_task(health._probe_storage()) for _ in range(8)]
    try:
        await asyncio.wait_for(probe_started.wait(), timeout=2)
        await asyncio.wait_for(all_callers_contending.wait(), timeout=2)
        release_probe.set()
        results = await asyncio.gather(*tasks)
    finally:
        release_probe.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert calls == 1
    assert [result[0] for result in results] == ["ok"] * 8

    # A zero success TTL still means a later call must perform a fresh probe.
    assert (await health._probe_storage())[0] == "ok"
    assert calls == 2
    assert (await health._probe_storage())[0] == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_storage_probe_cancellation_releases_singleflight_without_caching_error(
    monkeypatch,
):
    _patch_common(monkeypatch)
    probe_started = asyncio.Event()
    never_release = asyncio.Event()

    async def _cancelled_probe(_backend):
        probe_started.set()
        await never_release.wait()
        return "ok"

    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())
    monkeypatch.setattr(health, "_lightweight_storage_probe", _cancelled_probe)
    task = asyncio.create_task(health._probe_storage())
    try:
        await asyncio.wait_for(probe_started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        never_release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert health._storage_probe_cache["expires_at"] == 0.0
    assert health._storage_probe_cache["status"] == "unknown"
    monkeypatch.setattr(
        health, "_lightweight_storage_probe", AsyncMock(return_value="ok")
    )
    assert (await health._probe_storage())[0] == "ok"


@pytest.mark.asyncio
async def test_healthz_success_brief_and_cache_hit(monkeypatch):
    _patch_common(monkeypatch)
    connection = _Connection()
    monkeypatch.setattr(health, "engine", _Engine(_ConnectionContext(connection)))
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.002)))
    monkeypatch.setattr(health, "get_cache", lambda: SimpleNamespace(enabled=False))

    full = await health.healthz()
    assert full.status_code == status.HTTP_200_OK
    assert full.body
    assert health.record_health_probe.call_count == 6

    health.reset_health_cache()
    brief = await health.healthz(brief=True)
    assert brief.status_code == status.HTTP_200_OK
    assert b"pool" not in brief.body
    assert b"latency_ms" not in brief.body

    monkeypatch.setattr(
        health, "engine", MagicMock(side_effect=AssertionError("cache miss"))
    )
    cached = await health.healthz()
    assert cached.status_code == status.HTTP_200_OK
    assert b'"pool"' in cached.body


@pytest.mark.asyncio
async def test_healthz_brief_cache_hit_filters_full_payload(monkeypatch):
    _patch_common(monkeypatch, environment="production")
    connection = _Connection()
    monkeypatch.setattr(health, "engine", _Engine(_ConnectionContext(connection)))
    migration_probe = AsyncMock(
        return_value=(
            False,
            {"internal-current-revision"},
            {"internal-expected-revision"},
        )
    )
    monkeypatch.setattr(health, "migrations_are_current", migration_probe)
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.0)))
    monkeypatch.setattr(health, "get_cache", lambda: SimpleNamespace(enabled=False))

    full = await health.healthz()
    assert full.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    full_payload = json.loads(full.body)
    assert "pool" in full_payload
    assert any(key.endswith("_latency_ms") for key in full_payload)
    assert "internal-current-revision" in full_payload["db_migrations_current"]
    database_calls = connection.execute.await_count

    brief = await health.healthz(brief=True)
    assert brief.status_code == full.status_code
    brief_payload = json.loads(brief.body)
    assert brief_payload == {
        key: value
        for key, value in full_payload.items()
        if key not in {"pool", "db_migrations_current", "db_migrations_expected"}
        and not key.endswith("_latency_ms")
    }
    assert brief_payload["status"] == "error"
    assert brief_payload["db_migrations"] == "error"

    cached_full = await health.healthz()
    assert cached_full.status_code == full.status_code
    assert "pool" in json.loads(cached_full.body)
    assert (
        "internal-current-revision"
        in json.loads(cached_full.body)["db_migrations_current"]
    )
    assert connection.execute.await_count == database_calls
    migration_probe.assert_awaited_once()

    # A brief-first request must not replace or truncate the cached full result.
    health.reset_health_cache()
    brief_first = await health.healthz(brief=True)
    assert brief_first.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    brief_first_payload = json.loads(brief_first.body)
    assert "pool" not in brief_first_payload
    assert "db_migrations_current" not in brief_first_payload
    assert not any(key.endswith("_latency_ms") for key in brief_first_payload)
    calls_after_brief_first = connection.execute.await_count

    cached_full_after_brief = await health.healthz()
    assert cached_full_after_brief.status_code == brief_first.status_code
    cached_full_payload = json.loads(cached_full_after_brief.body)
    assert "pool" in cached_full_payload
    assert "internal-current-revision" in cached_full_payload["db_migrations_current"]
    assert connection.execute.await_count == calls_after_brief_first
    assert migration_probe.await_count == 2


@pytest.mark.asyncio
async def test_healthz_db_migration_and_queue_failures(monkeypatch):
    _patch_common(monkeypatch, environment="production")
    connection = _Connection()
    monkeypatch.setattr(health, "engine", _Engine(_ConnectionContext(connection)))
    monkeypatch.setattr(
        health,
        "migrations_are_current",
        AsyncMock(return_value=(False, {"current"}, {"expected"})),
    )
    monkeypatch.setattr(health, "_check_queue", AsyncMock(side_effect=RuntimeError()))
    monkeypatch.setattr(
        health, "_probe_storage", AsyncMock(return_value=("disabled", 0.0))
    )
    monkeypatch.setattr(health, "get_cache", lambda: SimpleNamespace(enabled=False))

    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    payload = response.body.decode()
    assert '"db_migrations":"error"' in payload
    assert '"notification_queue":"error"' in payload

    health.reset_health_cache()
    monkeypatch.setattr(
        health, "migrations_are_current", AsyncMock(side_effect=RuntimeError())
    )
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    monkeypatch.setattr(
        health, "migrations_are_current", AsyncMock(return_value=(True, set(), set()))
    )
    monkeypatch.setattr(health, "_check_queue", AsyncMock())
    response = await health.healthz()
    assert response.status_code == status.HTTP_200_OK
    assert b'"db_migrations":"ok"' in response.body


@pytest.mark.asyncio
async def test_healthz_db_timeout_and_connection_error(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        health,
        "engine",
        _Engine(_ConnectionContext(_Connection(), error=TimeoutError())),
    )
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.0)))
    monkeypatch.setattr(health, "get_cache", lambda: SimpleNamespace(enabled=False))
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    monkeypatch.setattr(
        health,
        "engine",
        _Engine(_ConnectionContext(_Connection(), error=RuntimeError())),
    )
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_healthz_cache_variants(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(health, "engine", _Engine(_ConnectionContext(_Connection())))
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.0)))

    cache = _ProbeCache()
    monkeypatch.setattr(health, "get_cache", lambda: cache)
    response = await health.healthz()
    assert response.status_code == status.HTTP_200_OK
    assert cache.get_calls == 1

    health.reset_health_cache()
    cache.corrupt_readback = True
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert b'"cache":"error"' in response.body
    cache.corrupt_readback = False

    health.reset_health_cache()
    cache.get_error = RuntimeError()
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    cache.get_error = None

    health.reset_health_cache()
    cache.set_error = RuntimeError()
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    cache.set_error = None
    cache.invalidate_error = RuntimeError()
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    cache.invalidate_error = None
    cache.silent_set = True
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert b'"cache":"error"' in response.body

    health.reset_health_cache()
    monkeypatch.setattr(health, "get_cache", MagicMock(side_effect=TimeoutError()))
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    monkeypatch.setattr(health, "get_cache", MagicMock(side_effect=RuntimeError()))
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_healthz_tiered_cache_reports_unavailable_shared_layer(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(health, "engine", _Engine(_ConnectionContext(_Connection())))
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.0)))

    client = SimpleNamespace(
        set=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        get=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        delete=AsyncMock(side_effect=ConnectionError("redis unavailable")),
    )
    redis_cache = RedisCache(url="redis://health-test", default_ttl=5)
    monkeypatch.setattr(redis_cache, "_client", client)
    tiered_cache = TieredCache(MemoryCache(), redis_cache)
    monkeypatch.setattr(health, "get_cache", lambda: tiered_cache)

    response = await health.healthz()

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert b'"cache":"error"' in response.body
    client.set.assert_awaited_once()
    client.get.assert_awaited_once()
    client.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_healthz_storage_scanner_and_spicedb_failures(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(health, "engine", _Engine(_ConnectionContext(_Connection())))
    monkeypatch.setattr(health, "get_cache", lambda: SimpleNamespace(enabled=False))

    monkeypatch.setattr(health, "_probe_storage", AsyncMock(side_effect=TimeoutError()))
    monkeypatch.setattr(health.settings, "event_file_scanner_enabled", True)
    monkeypatch.setattr(
        health, "check_file_scanner_health", AsyncMock(side_effect=TimeoutError())
    )
    monkeypatch.setattr(
        core_health, "check_spicedb_health", AsyncMock(side_effect=TimeoutError())
    )
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    class _TimeoutContext:
        calls = 0

        async def __aenter__(self):
            type(self).calls += 1
            if type(self).calls == 4:
                raise TimeoutError()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    health.reset_health_cache()
    monkeypatch.setattr(health.asyncio, "timeout", lambda _seconds: _TimeoutContext())
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.0)))
    monkeypatch.setattr(health, "check_file_scanner_health", AsyncMock())
    monkeypatch.setattr(
        core_health, "check_spicedb_health", AsyncMock(return_value=("ok", 1.5))
    )
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    monkeypatch.setattr(
        health, "_probe_storage", AsyncMock(return_value=("error", 0.0))
    )
    monkeypatch.setattr(
        health, "check_file_scanner_health", AsyncMock(side_effect=RuntimeError())
    )
    monkeypatch.setattr(
        core_health, "check_spicedb_health", AsyncMock(return_value=("error", 1.5))
    )
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_check_queue_skips_in_memory_mode_and_queries_database(monkeypatch):
    _patch_common(monkeypatch)
    connection = _Connection()
    await health._check_queue(connection)
    connection.execute.assert_awaited_once()

    health.settings.notifications_queue_in_memory_only = True
    connection.execute.reset_mock()
    await health._check_queue(connection)
    connection.execute.assert_not_awaited()
