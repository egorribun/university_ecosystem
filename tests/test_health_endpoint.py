from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.api import health
from app.services.storage import StorageBackend
from app.utils import migrations


class _SuccessfulCache:
    enabled = True

    def __init__(self) -> None:
        self._last_key: str | None = None

    async def set(self, key: str, payload, ttl=None):
        self._last_key = key

    async def invalidate(self, key: str) -> None:
        assert key == self._last_key


class _FailingCache:
    enabled = True

    async def set(self, key: str, payload, ttl=None):
        raise RuntimeError("cache set failed")

    async def invalidate(self, key: str) -> None:
        return None


class _FailingSession:
    async def __aenter__(self):
        raise RuntimeError("queue unavailable")

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _assert_latency_present(data: dict, key: str) -> None:
    assert key in data
    assert isinstance(data[key], int | float)
    assert 0 <= data[key] < 60_000


@pytest.fixture(autouse=True)
def reset_health_caches():
    health.reset_storage_probe_cache()
    migrations.reset_migration_cache()
    health.reset_health_cache()
    yield
    health.reset_storage_probe_cache()
    migrations.reset_migration_cache()
    health.reset_health_cache()


@pytest.mark.asyncio
async def test_healthcheck_reports_dependency_statuses(async_client):
    response = await async_client.get("http://testserver/healthz")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert data["storage"] == "ok"
    assert data["notification_queue"] == "ok"
    assert "cache" in data
    assert "file_scanner" in data
    for component in [
        "db_latency_ms",
        "cache_latency_ms",
        "storage_latency_ms",
        "notification_queue_latency_ms",
        "file_scanner_latency_ms",
    ]:
        _assert_latency_present(data, component)


@pytest.mark.asyncio
async def test_healthcheck_database_failure_returns_503(async_client, monkeypatch):
    class _FailingConnection:
        async def __aenter__(self):
            raise RuntimeError("db offline")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FailingEngine:
        def connect(self):
            return _FailingConnection()

    monkeypatch.setattr(health, "engine", _FailingEngine())

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["status"] == "error"
    assert data["db"] == "error"
    _assert_latency_present(data, "db_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_cache_success(async_client, monkeypatch):
    cache = _SuccessfulCache()
    monkeypatch.setattr(health, "get_cache", lambda: cache)

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["cache"] == "ok"
    _assert_latency_present(data, "cache_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_cache_failure(async_client, monkeypatch):
    monkeypatch.setattr(health, "get_cache", lambda: _FailingCache())

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["cache"] == "error"
    _assert_latency_present(data, "cache_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_storage_failure(async_client, monkeypatch):
    class _FailingStorage:
        async def save_file(
            self, relative_path: str, data: bytes, *, content_type=None
        ):
            raise RuntimeError("storage down")

        async def delete_file(self, file_url: str) -> None:
            return None

    monkeypatch.setattr(health.settings, "health_storage_probe_enabled", True)
    monkeypatch.setattr(health, "_get_storage_backend", lambda: _FailingStorage())

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["storage"] == "error"
    _assert_latency_present(data, "storage_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_storage_probe_skips_heavy_when_disabled(
    async_client, monkeypatch
):
    monkeypatch.setattr(health.settings, "health_storage_probe_enabled", False)

    probes = {"light": 0, "heavy": 0}

    async def _fake_lightweight_probe(_backend):
        probes["light"] += 1
        return "ok"

    async def _unexpected_heavy_probe(_backend):  # pragma: no cover - guarded
        probes["heavy"] += 1
        raise AssertionError("heavy probe should not run when disabled")

    monkeypatch.setattr(health, "_lightweight_storage_probe", _fake_lightweight_probe)
    monkeypatch.setattr(health, "_write_delete_storage_probe", _unexpected_heavy_probe)
    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())

    response = await async_client.get("http://testserver/healthz")
    data = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert data["storage"] == "ok"
    assert probes == {"light": 1, "heavy": 0}
    _assert_latency_present(data, "storage_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_storage_probe_uses_cache(async_client, monkeypatch):
    monkeypatch.setattr(health.settings, "health_storage_probe_enabled", True)
    monkeypatch.setattr(
        health.settings, "health_storage_probe_min_interval_seconds", 60.0
    )

    probes = {"light": 0, "heavy": 0}

    async def _heavy_probe(_backend):
        probes["heavy"] += 1
        return "ok"

    async def _lightweight_probe(_backend):
        probes["light"] += 1
        return None

    monkeypatch.setattr(health, "_lightweight_storage_probe", _lightweight_probe)
    monkeypatch.setattr(health, "_write_delete_storage_probe", _heavy_probe)
    monkeypatch.setattr(health, "_get_storage_backend", lambda: object())

    first = await async_client.get("http://testserver/healthz")
    second = await async_client.get("http://testserver/healthz")

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert probes == {"light": 0, "heavy": 1}
    assert first.json()["storage"] == "ok"
    assert second.json()["storage"] == "ok"


@pytest.mark.asyncio
async def test_healthcheck_notification_queue_failure(async_client, monkeypatch):
    async def _failing_queue_check(conn):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(health, "_check_queue", _failing_queue_check)

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["notification_queue"] == "error"
    _assert_latency_present(data, "notification_queue_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_notification_queue_missing_table(async_client, monkeypatch):
    monkeypatch.setattr(health.settings, "notifications_queue_in_memory_only", True)
    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["notification_queue"] == "ok"
    _assert_latency_present(data, "notification_queue_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_reports_migration_versions_on_drift(
    async_client, monkeypatch
):
    async def _mock_migrations_are_current(
        conn=None,
    ) -> tuple[bool, set[str], set[str]]:
        return False, {"current"}, {"expected"}

    monkeypatch.setattr(health, "migrations_are_current", _mock_migrations_are_current)
    # Drift only causes 503 if NOT in testing environment
    monkeypatch.setattr(health.settings, "environment", "production")

    response = await async_client.get("http://testserver/healthz")
    data = response.json()

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["db"] == "error"
    assert data["db_migrations"] == "error"
    assert data["db_migrations_current"] == ["current"]
    assert data["db_migrations_expected"] == ["expected"]
    _assert_latency_present(data, "db_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_file_scanner_success(async_client, monkeypatch):
    monkeypatch.setattr(health.settings, "event_file_scanner_enabled", True)

    async def _fake_health_check() -> None:
        return None

    monkeypatch.setattr(health, "check_file_scanner_health", _fake_health_check)

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["file_scanner"] == "ok"
    _assert_latency_present(data, "file_scanner_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_file_scanner_failure(async_client, monkeypatch):
    monkeypatch.setattr(health.settings, "event_file_scanner_enabled", True)

    async def _failing_health_check() -> None:
        raise RuntimeError("scanner offline")

    monkeypatch.setattr(health, "check_file_scanner_health", _failing_health_check)

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["file_scanner"] == "error"
    _assert_latency_present(data, "file_scanner_latency_ms")


@pytest.mark.asyncio
async def test_healthcheck_file_scanner_uses_lightweight_probe(
    async_client, monkeypatch
):
    monkeypatch.setattr(health.settings, "event_file_scanner_enabled", True)

    async def _fake_health_check() -> None:
        return None

    async def _forbidden_scan(
        _payload, *, locale=None, size_bytes: int | None = None
    ) -> None:  # pragma: no cover
        raise AssertionError("health check should not trigger file scanning")

    monkeypatch.setattr(health, "check_file_scanner_health", _fake_health_check)
    monkeypatch.setattr(health, "scan_for_malware", _forbidden_scan)

    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["file_scanner"] == "ok"
    _assert_latency_present(data, "file_scanner_latency_ms")


# --------------------------------------------------------------------------- #
# Track C (session 6) additions — liveness / readiness / brief mode +          #
# storage-probe real bodies + cache-invalidate error branch.                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_liveness_always_alive():
    assert await health.liveness() == {"status": "alive"}


@pytest.mark.asyncio
async def test_ready_returns_ready_when_not_shutting_down():
    health.reset_shutdown_flag()
    assert await health.ready() == {"status": "ready"}


@pytest.mark.asyncio
async def test_ready_returns_503_during_shutdown():
    health.set_shutdown_flag()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await health.ready()
        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    finally:
        health.reset_shutdown_flag()


@pytest.mark.asyncio
async def test_healthcheck_brief_omits_internals(async_client):
    response = await async_client.get("http://testserver/healthz?brief=true")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["status"] == "ok"
    assert data["db"] == "ok"  # top-level statuses kept
    assert "pool" not in data  # infra internals omitted
    assert "db_migrations_current" not in data
    assert not any(k.endswith("_latency_ms") for k in data)  # latencies omitted


@pytest.mark.asyncio
async def test_lightweight_storage_probe_ok_error_and_non_backend():
    backend = MagicMock(spec=StorageBackend)  # passes isinstance(StorageBackend)
    backend.exists = AsyncMock(return_value=True)
    assert await health._lightweight_storage_probe(backend) == "ok"

    backend.exists = AsyncMock(return_value=False)
    assert await health._lightweight_storage_probe(backend) == "error"

    backend.exists = AsyncMock(side_effect=RuntimeError("boom"))
    assert await health._lightweight_storage_probe(backend) == "error"

    # A non-StorageBackend short-circuits to None before any probe.
    assert await health._lightweight_storage_probe(object()) is None


@pytest.mark.asyncio
async def test_write_delete_storage_probe_delete_failure_and_success():
    backend = MagicMock()
    backend.save_file = AsyncMock(return_value="healthz/probe.txt")
    backend.delete_file = AsyncMock(side_effect=RuntimeError("delete failed"))
    assert await health._write_delete_storage_probe(backend) == "error"

    backend.delete_file = AsyncMock(return_value=None)
    assert await health._write_delete_storage_probe(backend) == "ok"


@pytest.mark.asyncio
async def test_healthcheck_cache_invalidate_failure(async_client, monkeypatch):
    class _InvalidateFailingCache:
        enabled = True

        async def set(self, key, payload, ttl=None):
            return None  # set succeeds

        async def invalidate(self, key):
            raise RuntimeError("invalidate failed")  # finally-block error path

    monkeypatch.setattr(health, "get_cache", lambda: _InvalidateFailingCache())
    response = await async_client.get("http://testserver/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["cache"] == "error"
