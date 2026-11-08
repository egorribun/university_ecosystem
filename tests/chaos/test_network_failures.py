"""W19: ToxiProxy network-failure proof for the PostgreSQL health path.

The nightly ``Chaos Engineering (ToxiProxy)`` job publishes a ``postgres``
ToxiProxy listener on port 9004, points the application's DATABASE_URL at
that listener and runs this module in its own pytest invocation.  The
application's asyncpg engine therefore really traverses ToxiProxy, so the
latency toxic delays the database path that ``/healthz`` probes.

Outside that job the module skips when ToxiProxy is unreachable or DATABASE_URL
does not use the listener.  With ``CHAOS_NETWORK_REQUIRED=1`` (set by the nightly
job) those conditions fail the run instead of skipping it.

The Valkey and NATS outage proofs live in ``tests/chaos/test_resilience.py``.
"""

from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.api.health import reset_health_cache
from app.core.database import engine

TOXIPROXY_URL = os.getenv("TOXIPROXY_URL", "http://localhost:8474").rstrip("/")
POSTGRES_PROXY_NAME = "postgres"
POSTGRES_PROXY_PORT = 9004
TOXIC_NAME = "pg_lag"
NETWORK_CHAOS_REQUIRED = os.getenv("CHAOS_NETWORK_REQUIRED") == "1"
_HEALTH_SOURCE = Path(__file__).resolve().parents[2] / "app" / "api" / "health.py"


def _health_probe_timeout_seconds() -> float:
    """Return the per-subsystem probe timeout that healthz() enforces.

    The constant is local to healthz(), so it cannot be imported.  The single
    annotated assignment is read from the production source instead of being
    copied, which keeps the injected latency tied to the real timeout.
    """
    tree = ast.parse(_HEALTH_SOURCE.read_text(encoding="utf-8"))
    for function in ast.walk(tree):
        if not isinstance(function, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        if function.name != "healthz":
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "_PROBE_TIMEOUT_SECONDS"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, int | float)
            ):
                return float(node.value.value)
    raise RuntimeError("healthz() does not define _PROBE_TIMEOUT_SECONDS")


PROBE_TIMEOUT_SECONDS = _health_probe_timeout_seconds()
# Hold the database handshake well past the probe timeout so the db probe must
# time out rather than complete.
LATENCY_MS = int((PROBE_TIMEOUT_SECONDS + 3) * 1000)
# The db probe is bounded by PROBE_TIMEOUT_SECONDS; the remaining probes are
# fast when the database is the only fault, so three timeouts is a generous bound.
HEALTH_RESPONSE_BOUND_SECONDS = PROBE_TIMEOUT_SECONDS * 3


def _toxiproxy_available() -> bool:
    """Return True when the ToxiProxy HTTP API is reachable."""
    try:
        response = httpx.get(f"{TOXIPROXY_URL}/version", timeout=2.0)
        return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _database_url_uses_proxy() -> bool:
    """Return True when DATABASE_URL targets the ToxiProxy PostgreSQL listener."""
    try:
        url = make_url(os.getenv("DATABASE_URL", ""))
    except ArgumentError:
        return False
    return (
        url.drivername.startswith("postgresql")
        and url.host in {"localhost", "127.0.0.1"}
        and url.port == POSTGRES_PROXY_PORT
    )


pytestmark = [
    pytest.mark.chaos,
    pytest.mark.integration,
    pytest.mark.skipif(
        not NETWORK_CHAOS_REQUIRED and not _database_url_uses_proxy(),
        reason="DATABASE_URL does not route through the ToxiProxy postgres listener",
    ),
    pytest.mark.skipif(
        not NETWORK_CHAOS_REQUIRED and not _toxiproxy_available(),
        reason="ToxiProxy not available",
    ),
]


@pytest.fixture(autouse=True)
def _network_chaos_environment() -> None:
    """Fail, never skip, when the nightly job's required environment is absent."""
    if not NETWORK_CHAOS_REQUIRED:
        return
    if not _toxiproxy_available():
        pytest.fail(
            f"CHAOS_NETWORK_REQUIRED=1 but ToxiProxy is unreachable at {TOXIPROXY_URL}"
        )
    if not _database_url_uses_proxy():
        pytest.fail(
            "CHAOS_NETWORK_REQUIRED=1 but DATABASE_URL does not target "
            f"localhost:{POSTGRES_PROXY_PORT}"
        )


async def _toxiproxy(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async with httpx.AsyncClient(base_url=TOXIPROXY_URL, timeout=10.0) as http:
        return await http.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_postgres_latency_triggers_timeout_response(root_client) -> None:
    """Latency on the app's PostgreSQL path makes /healthz answer 503.

    WHY: the engine dials the ToxiProxy listener named in DATABASE_URL, so the
    latency toxic delays the real asyncpg handshake.  The db probe then exceeds
    its timeout, and the endpoint must report that outage instead of hanging
    or answering 200.
    """
    assert engine.url.port == POSTGRES_PROXY_PORT, (
        "the application engine must traverse the ToxiProxy postgres listener"
    )

    created = await _toxiproxy(
        "POST",
        f"/proxies/{POSTGRES_PROXY_NAME}/toxics",
        json={
            "name": TOXIC_NAME,
            "type": "latency",
            "stream": "downstream",
            "toxicity": 1.0,
            "attributes": {"latency": LATENCY_MS},
        },
    )
    assert created.status_code in {200, 201, 204}, (
        f"ToxiProxy refused the latency toxic: {created.status_code} {created.text}"
    )
    try:
        reset_health_cache()
        async with asyncio.timeout(HEALTH_RESPONSE_BOUND_SECONDS):
            response = await root_client.get("/healthz")
        assert response.status_code == 503, response.text
        body = response.json()
        assert body["status"] == "error"
        assert body["db"] == "error"
    finally:
        removed = await _toxiproxy(
            "DELETE", f"/proxies/{POSTGRES_PROXY_NAME}/toxics/{TOXIC_NAME}"
        )
        assert removed.status_code in {200, 204}, (
            f"ToxiProxy did not remove the latency toxic: {removed.status_code}"
        )

    reset_health_cache()
    response = await root_client.get("/healthz")
    assert response.status_code == 200, response.text
    assert response.json()["db"] == "ok"
