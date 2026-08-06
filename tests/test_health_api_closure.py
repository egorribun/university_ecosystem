from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

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
from app.services.storage import StorageBackend

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

    async def exists(self, path: str) -> bool:
        if self.exists_error is not None:
            raise self.exists_error
        return self.exists_value

    async def save_file(self, relative_path: str, data: bytes, *, content_type=None):
        if self.save_error is not None:
            raise self.save_error
        return "healthz/probe.txt"

    async def delete_file(self, file_url: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error


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
    assert status_value == "ok"

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

    cache = SimpleNamespace(enabled=True, set=AsyncMock(), invalidate=AsyncMock())
    monkeypatch.setattr(health, "get_cache", lambda: cache)
    response = await health.healthz()
    assert response.status_code == status.HTTP_200_OK

    health.reset_health_cache()
    cache.set = AsyncMock(side_effect=RuntimeError())
    cache.invalidate = AsyncMock()
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    cache.set = AsyncMock()
    cache.invalidate = AsyncMock(side_effect=RuntimeError())
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    monkeypatch.setattr(health, "get_cache", MagicMock(side_effect=TimeoutError()))
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    health.reset_health_cache()
    monkeypatch.setattr(health, "get_cache", MagicMock(side_effect=RuntimeError()))
    response = await health.healthz()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


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
