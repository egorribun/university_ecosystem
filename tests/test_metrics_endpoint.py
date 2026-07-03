import base64
from collections.abc import Iterator

import pytest

from app.core import metrics as metrics_module
from app.core import observability
from app.core.config import settings


@pytest.fixture
def _configure_metrics() -> Iterator[str]:
    previous_enable = settings.enable_metrics_endpoint
    previous_username = settings.metrics_basic_auth_username
    previous_password = settings.metrics_basic_auth_password
    previous_allowlist = settings.metrics_allowlist

    settings.enable_metrics_endpoint = True
    settings.metrics_basic_auth_username = "metrics"
    settings.metrics_basic_auth_password = "secret"
    settings.metrics_allowlist = ""
    credentials = base64.b64encode(b"metrics:secret").decode("ascii")
    try:
        yield credentials
    finally:
        settings.enable_metrics_endpoint = previous_enable
        settings.metrics_basic_auth_username = previous_username
        settings.metrics_basic_auth_password = previous_password
        settings.metrics_allowlist = previous_allowlist


@pytest.mark.asyncio
async def test_metrics_endpoint_requires_auth(root_client, _configure_metrics: str):
    response = await root_client.get("/metrics")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="Metrics"'


@pytest.mark.asyncio
async def test_metrics_endpoint_rejects_missing_credentials_when_public(root_client):
    previous_enable = settings.enable_metrics_endpoint
    previous_username = settings.metrics_basic_auth_username
    previous_password = settings.metrics_basic_auth_password
    previous_allowlist = settings.metrics_allowlist

    settings.enable_metrics_endpoint = True
    settings.metrics_basic_auth_username = ""
    settings.metrics_basic_auth_password = ""
    settings.metrics_allowlist = ""
    try:
        response = await root_client.get("/metrics")
    finally:
        settings.enable_metrics_endpoint = previous_enable
        settings.metrics_basic_auth_username = previous_username
        settings.metrics_basic_auth_password = previous_password
        settings.metrics_allowlist = previous_allowlist

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_payload(
    root_client, _configure_metrics: str
):
    # Emit a request to ensure counters are incremented.
    health_response = await root_client.get("/healthz")
    assert health_response.status_code == 200

    response = await root_client.get(
        "/metrics",
        headers={"Authorization": f"Basic {_configure_metrics}"},
    )
    assert response.status_code == 200
    assert (
        response.headers["content-type"].split(";", 1)[0]
        == metrics_module.CONTENT_TYPE_LATEST.split(";", 1)[0]
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    body = response.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "notification_queue_dead_lettered_jobs" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_rejects_partial_credentials(root_client):
    previous_enable = settings.enable_metrics_endpoint
    previous_username = settings.metrics_basic_auth_username
    previous_password = settings.metrics_basic_auth_password
    previous_allowlist = settings.metrics_allowlist

    settings.enable_metrics_endpoint = True
    settings.metrics_basic_auth_username = "metrics"
    settings.metrics_basic_auth_password = ""
    settings.metrics_allowlist = ""
    try:
        response = await root_client.get("/metrics")
    finally:
        settings.enable_metrics_endpoint = previous_enable
        settings.metrics_basic_auth_username = previous_username
        settings.metrics_basic_auth_password = previous_password
        settings.metrics_allowlist = previous_allowlist

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_metrics_endpoint_respects_allowlist(
    root_client, _configure_metrics: str
):
    settings.metrics_allowlist = "10.0.0.0/8"

    response = await root_client.get(
        "/metrics",
        headers={"Authorization": f"Basic {_configure_metrics}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_metrics_endpoint_allows_loopback_allowlist_without_auth(root_client):
    previous_enable = settings.enable_metrics_endpoint
    previous_username = settings.metrics_basic_auth_username
    previous_password = settings.metrics_basic_auth_password
    previous_allowlist = settings.metrics_allowlist

    settings.enable_metrics_endpoint = True
    settings.metrics_basic_auth_username = ""
    settings.metrics_basic_auth_password = ""
    settings.metrics_allowlist = "127.0.0.1,::1,localhost"
    try:
        response = await root_client.get("/metrics")
    finally:
        settings.enable_metrics_endpoint = previous_enable
        settings.metrics_basic_auth_username = previous_username
        settings.metrics_basic_auth_password = previous_password
        settings.metrics_allowlist = previous_allowlist

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check_metrics_recorded(root_client, _configure_metrics: str):
    probe = await root_client.get("/healthz")
    assert probe.status_code == 200

    response = await root_client.get(
        "/metrics",
        headers={"Authorization": f"Basic {_configure_metrics}"},
    )

    assert response.status_code == 200
    body = response.text
    assert 'healthcheck_status_total{component="db",status="ok"}' in body
    assert 'healthcheck_duration_seconds_count{component="cache"}' in body


def test_otel_resource_attributes_include_service_version():
    previous_version = settings.service_version
    try:
        settings.service_version = " 2024.05.01 "
        attributes = observability._build_otel_resource_attributes()
        assert attributes["service.version"] == "2024.05.01"
    finally:
        settings.service_version = previous_version


@pytest.mark.asyncio
async def test_custom_business_metrics_increment(root_client, _configure_metrics: str):
    """Verify custom business metrics increment correctly and reflect on /metrics."""
    from app.core.metrics import record_login_failure, record_login_success

    record_login_success("password")
    record_login_failure("invalid_password")

    response = await root_client.get(
        "/metrics",
        headers={"Authorization": f"Basic {_configure_metrics}"},
    )
    assert response.status_code == 200
    body = response.text
    assert 'login_success_total{method="password"}' in body
    assert 'login_failure_total{reason="invalid_password"}' in body


def test_metrics_reset_isolation():
    """Verify that calling reset on metrics collectors zeroes out values and ensures isolation."""
    from app.core.observability import get_notification_queue_metrics

    metrics_bundle = get_notification_queue_metrics()
    metrics_bundle.queue_size.set(42)
    assert metrics_bundle.queue_size._value.get() == 42.0

    # Reset metrics bundle
    metrics_bundle.reset()
    # After reset, the fresh collector should be zeroed (default 0.0)
    assert metrics_bundle.queue_size._value.get() == 0.0
