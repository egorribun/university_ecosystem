import pytest
from fastapi import status
from sqlalchemy.exc import OperationalError

from app import main


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


@pytest.fixture
def missing_table_operational_error(monkeypatch):
    class _UndefinedTableError(Exception):
        pgcode = "42P01"
        sqlstate = "42P01"

        def __str__(self) -> str:
            return "relation notification_queue_job does not exist"

    error = OperationalError("SELECT", None, _UndefinedTableError())

    class _MissingTableSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            raise error

    monkeypatch.setattr(main, "async_session", lambda: _MissingTableSession())
    return error


@pytest.mark.anyio("asyncio")
async def test_healthcheck_reports_dependency_statuses(async_client):
    response = await async_client.get("/healthz")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert data["storage"] == "ok"
    assert data["notification_queue"] == "ok"
    assert "cache" in data
    assert "file_scanner" in data


@pytest.mark.anyio("asyncio")
async def test_healthcheck_database_failure_returns_503(async_client, monkeypatch):
    class _FailingConnection:
        async def __aenter__(self):
            raise RuntimeError("db offline")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FailingEngine:
        def connect(self):
            return _FailingConnection()

    monkeypatch.setattr(main, "engine", _FailingEngine())

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["status"] == "error"
    assert data["db"] == "error"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_cache_success(async_client, monkeypatch):
    cache = _SuccessfulCache()
    monkeypatch.setattr(main, "get_cache", lambda: cache)

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["cache"] == "ok"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_cache_failure(async_client, monkeypatch):
    monkeypatch.setattr(main, "get_cache", lambda: _FailingCache())

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["cache"] == "error"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_storage_failure(async_client, monkeypatch):
    class _FailingStorage:
        async def save_file(
            self, relative_path: str, data: bytes, *, content_type=None
        ):
            raise RuntimeError("storage down")

        async def delete_file(self, file_url: str) -> None:
            return None

    monkeypatch.setattr(main, "_get_storage_backend", lambda: _FailingStorage())

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["storage"] == "error"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_notification_queue_failure(async_client, monkeypatch):
    monkeypatch.setattr(main, "async_session", lambda: _FailingSession())

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["notification_queue"] == "error"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_notification_queue_missing_table(
    async_client, missing_table_operational_error, monkeypatch
):
    monkeypatch.setattr(main.settings, "notifications_queue_in_memory_only", True)
    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["notification_queue"] == "ok"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_file_scanner_success(async_client, monkeypatch):
    monkeypatch.setattr(main.settings, "event_file_scanner_enabled", True)

    async def _fake_health_check() -> None:
        return None

    monkeypatch.setattr(main, "check_file_scanner_health", _fake_health_check)

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["file_scanner"] == "ok"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_file_scanner_failure(async_client, monkeypatch):
    monkeypatch.setattr(main.settings, "event_file_scanner_enabled", True)

    async def _failing_health_check() -> None:
        raise RuntimeError("scanner offline")

    monkeypatch.setattr(main, "check_file_scanner_health", _failing_health_check)

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert data["file_scanner"] == "error"


@pytest.mark.anyio("asyncio")
async def test_healthcheck_file_scanner_uses_lightweight_probe(
    async_client, monkeypatch
):
    monkeypatch.setattr(main.settings, "event_file_scanner_enabled", True)

    async def _fake_health_check() -> None:
        return None

    async def _forbidden_scan(
        _payload, *, locale=None, size_bytes: int | None = None
    ) -> None:  # pragma: no cover
        raise AssertionError("health check should not trigger file scanning")

    monkeypatch.setattr(main, "check_file_scanner_health", _fake_health_check)
    monkeypatch.setattr(main, "scan_for_malware", _forbidden_scan)

    response = await async_client.get("/healthz")
    data = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert data["file_scanner"] == "ok"
