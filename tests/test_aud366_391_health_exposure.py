"""Public health response and worker-monitor binding security contracts."""

from __future__ import annotations

import secrets
from ipaddress import IPv4Address
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import health
from app.core import health as core_health
from app.core.config import Settings
from app.core.config.notifications import NotificationSettings


@pytest.fixture
def drift_probes(monkeypatch: pytest.MonkeyPatch):
    """Exercise the route with an actual migration drift and pool details."""
    health.reset_health_cache()
    health.reset_storage_probe_cache()
    health.reset_shutdown_flag()

    connection = SimpleNamespace(execute=AsyncMock())
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(health, "engine", SimpleNamespace(connect=lambda: context))
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(
            environment="production",
            notifications_queue_in_memory_only=False,
            health_storage_probe_enabled=False,
            health_storage_probe_min_interval_seconds=0.0,
            event_file_scanner_enabled=False,
        ),
    )
    migrations = AsyncMock(
        return_value=(
            False,
            {"internal-current-revision"},
            {"internal-target-revision"},
        )
    )
    monkeypatch.setattr(health, "migrations_are_current", migrations)
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.0)))
    monkeypatch.setattr(health, "get_cache", lambda: SimpleNamespace(enabled=False))
    monkeypatch.setattr(health, "get_pool_health_metrics", lambda: {"size": 7})
    monkeypatch.setattr(health, "record_health_probe", MagicMock())
    monkeypatch.setattr(
        core_health, "check_spicedb_health", AsyncMock(return_value=("ok", 1.5))
    )
    yield connection, migrations
    health.reset_health_cache()
    health.reset_storage_probe_cache()
    health.reset_shutdown_flag()


def _public_health_app() -> FastAPI:
    app = FastAPI()
    app.include_router(health.router)
    return app


def _assert_public_result(response) -> None:
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["db"] == "error"
    assert payload["db_migrations"] == "error"
    assert "pool" not in payload
    assert "db_migrations_current" not in payload
    assert "db_migrations_expected" not in payload
    assert not any(key.endswith("_latency_ms") for key in payload)


def test_aud366_legacy_brief_parameter_is_documented_as_ignored() -> None:
    operation = _public_health_app().openapi()["paths"]["/healthz"]["get"]
    brief = next(item for item in operation["parameters"] if item["name"] == "brief")
    assert "ignored" in brief.get("description", "").lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "?brief=true", "?brief=false"])
async def test_aud366_anonymous_drift_response_hides_diagnostics_on_miss_and_hit(
    drift_probes, query: str
) -> None:
    connection, migrations = drift_probes
    async with AsyncClient(
        transport=ASGITransport(app=_public_health_app()), base_url="http://test"
    ) as client:
        first = await client.get(f"/healthz{query}")
        calls_after_first = connection.execute.await_count
        second = await client.get(f"/healthz{query}")

    _assert_public_result(first)
    _assert_public_result(second)
    assert connection.execute.await_count == calls_after_first
    migrations.assert_awaited_once()


@pytest.mark.asyncio
async def test_aud366_cached_full_probe_cannot_be_read_anonymously(
    drift_probes,
) -> None:
    connection, migrations = drift_probes
    full = await health.healthz()
    assert b"internal-current-revision" in full.body
    assert b'"pool"' in full.body
    calls_after_full = connection.execute.await_count

    async with AsyncClient(
        transport=ASGITransport(app=_public_health_app()), base_url="http://test"
    ) as client:
        for path in ("/healthz", "/healthz?brief=false", "/healthz?brief=true"):
            _assert_public_result(await client.get(path))

    assert connection.execute.await_count == calls_after_full
    migrations.assert_awaited_once()


@pytest.mark.asyncio
async def test_aud366_liveness_and_readiness_remain_public(monkeypatch, drift_probes):
    monkeypatch.setattr(health, "wait_db", AsyncMock())
    async with AsyncClient(
        transport=ASGITransport(app=_public_health_app()), base_url="http://test"
    ) as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
        legacy_ready = await client.get("/ready")
        health._shutdown_flag.set()
        draining = await client.get("/health/ready")

    assert live.status_code == 200 and live.json() == {"status": "alive"}
    assert ready.status_code == 200 and ready.json() == {"status": "ready"}
    assert legacy_ready.status_code == 200 and legacy_ready.json() == {
        "status": "ready"
    }
    assert draining.status_code == 503


def test_aud391_worker_monitor_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("NOTIFICATIONS_WORKER_METRICS_HOST", raising=False)
    settings = NotificationSettings(_env_file=None, _allow_missing=True)
    assert settings.notifications_worker_metrics_host == "127.0.0.1"


def test_aud391_worker_monitor_allows_explicit_container_binding(monkeypatch):
    wildcard_host = str(IPv4Address(0))
    monkeypatch.setenv("NOTIFICATIONS_WORKER_METRICS_HOST", wildcard_host)
    settings = NotificationSettings(_env_file=None, _allow_missing=True)
    assert settings.notifications_worker_metrics_host == wildcard_host


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_override", [False, True])
async def test_aud391_worker_passes_composed_host_to_monitor(
    monkeypatch, explicit_override: bool
):
    from app.workers import notifications as worker

    expected_host = "127.0.0.1"
    if explicit_override:
        expected_host = str(IPv4Address(0))
        monkeypatch.setenv("NOTIFICATIONS_WORKER_METRICS_HOST", expected_host)
    else:
        monkeypatch.delenv("NOTIFICATIONS_WORKER_METRICS_HOST", raising=False)
    settings = Settings(
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        secret_key=secrets.token_urlsafe(48),
        elasticsearch_password="",
        _env_file=None,
    )
    monkeypatch.setattr(worker, "settings", settings)
    monkeypatch.setattr(worker, "configure_worker_observability", MagicMock())
    monkeypatch.setattr(worker, "create_worker_metrics", MagicMock())
    monitor_app = object()
    monkeypatch.setattr(worker, "create_worker_monitoring_app", lambda **_: monitor_app)
    stop_monitor = AsyncMock()
    start_monitor = AsyncMock(return_value=stop_monitor)
    monkeypatch.setattr(worker, "start_worker_monitoring_server", start_monitor)
    monkeypatch.setattr(worker, "wait_db", AsyncMock())
    monkeypatch.setattr(worker.NotificationsScheduler, "run_forever", AsyncMock())
    monkeypatch.setattr(worker.webpush, "cleanup", MagicMock())

    async def stop_on_signal(event):
        event.set()

    monkeypatch.setattr(worker, "_wait_for_signals", stop_on_signal)
    await worker.run_worker()
    start_monitor.assert_awaited_once_with(monitor_app, host=expected_host, port=9101)
    stop_monitor.assert_awaited_once()
