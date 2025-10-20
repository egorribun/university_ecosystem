import base64
from collections.abc import Iterator

import pytest

from app.core import metrics as metrics_module
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


@pytest.mark.anyio
async def test_metrics_endpoint_requires_auth(async_client, _configure_metrics: str):
    response = await async_client.get("/metrics")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="Metrics"'


@pytest.mark.anyio
async def test_metrics_endpoint_exposes_prometheus_payload(
    async_client, _configure_metrics: str
):
    # Emit a request to ensure counters are incremented.
    health_response = await async_client.get("/healthz")
    assert health_response.status_code == 200

    response = await async_client.get(
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


@pytest.mark.anyio
async def test_metrics_endpoint_respects_allowlist(
    async_client, _configure_metrics: str
):
    settings.metrics_allowlist = "10.0.0.0/8"

    response = await async_client.get(
        "/metrics",
        headers={"Authorization": f"Basic {_configure_metrics}"},
    )
    assert response.status_code == 403
