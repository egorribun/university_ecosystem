"""Regression tests for required ws-hub environment variables.

The ws-hub service requires THREE environment variables to operate
correctly within the dev Docker compose stack:

1. REDIS_URL — ws-hub config defaults to "redis:6379" (W173 polish-v1
   Fix D). Without this explicit env, ws-hub fell back to defaults
   AND attempted to authenticate against the Redis broker, which
   requires REDIS_PASSWORD.

2. REDIS_PASSWORD — ws-hub uses ${REDIS_PASSWORD} interpolation (W173
   polish-v1 Fix E) for Redis AUTH. Without this, ws-hub got
   "NOAUTH Authentication required" startup error, fell back to
   "L2 cache disabled" mode, AND failed OTT (one-time-ticket)
   validation in handlers.go:195 (redisClient.GetDel for
   "ott:ws:<ticket>") → all real tickets received 401 at WS upgrade.

3. ALLOWED_ORIGINS — ws-hub gorilla/websocket Upgrader.CheckOrigin
   rejects requests where the Origin header doesn't match the list
   (default: localhost:3000 + localhost:5173 — Vite dev ports).
   In production-like dev (Caddy on port 80), browsers send
   `Origin: http://localhost` (no port). Without explicit
   ALLOWED_ORIGINS env (W173 polish-v3 Fix F), ws-hub returned 403
   Forbidden on WS upgrade.

The 3 fixes together unblocked chat WS flow that had been dormant
≥17 waves between W131 SW4/SW7 service-split arc and W173 polish-v3
real-user bug report.

This test uses PyYAML to parse docker-compose.full.yml and asserts
each invariant per ws-hub service block.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.full.yml"


@pytest.fixture(scope="module")
def ws_hub_env() -> dict[str, str]:
    """Parse docker-compose.full.yml and return ws-hub service env block."""
    assert COMPOSE_FILE.exists(), f"Expected compose file at {COMPOSE_FILE}"
    with COMPOSE_FILE.open(encoding="utf-8") as fh:
        compose = yaml.safe_load(fh)
    ws_hub = compose["services"].get("ws-hub")
    assert ws_hub is not None, "ws-hub service must exist in docker-compose.full.yml"
    env = ws_hub.get("environment")
    assert env is not None, "ws-hub service must have environment block"
    # docker-compose environment can be either dict OR list-of-strings
    # ("KEY=value"). Normalize to dict.
    if isinstance(env, list):
        normalized: dict[str, str] = {}
        for entry in env:
            if "=" in entry:
                key, value = entry.split("=", 1)
                normalized[key] = value
            else:
                normalized[entry] = ""
        return normalized
    assert isinstance(env, dict), (
        f"ws-hub environment must be dict or list, got {type(env)}"
    )
    # Coerce all values to strings (compose YAML may yield int/bool for some)
    return {k: str(v) for k, v in env.items()}


def test_redis_url_set_for_ws_hub(ws_hub_env: dict[str, str]) -> None:
    """W173 polish-v1 Fix D: ws-hub REDIS_URL must be set explicitly."""
    assert "REDIS_URL" in ws_hub_env, (
        "W173 polish-v1 Fix D regression: ws-hub must set REDIS_URL env"
    )
    redis_url = ws_hub_env["REDIS_URL"]
    # ws-hub config expects "host:port" format (NOT redis:// URL scheme)
    assert ":" in redis_url, f"REDIS_URL must include port (got {redis_url!r})"


def test_redis_password_set_via_interpolation(ws_hub_env: dict[str, str]) -> None:
    """W173 polish-v1 Fix E: ws-hub REDIS_PASSWORD uses ${REDIS_PASSWORD}."""
    assert "REDIS_PASSWORD" in ws_hub_env, (
        "W173 polish-v1 Fix E regression: ws-hub must set REDIS_PASSWORD env"
    )
    password_value = ws_hub_env["REDIS_PASSWORD"]
    # Must use compose interpolation syntax so the .env REDIS_PASSWORD
    # is forwarded into the ws-hub container. Allows either $REDIS_PASSWORD
    # or ${REDIS_PASSWORD} (YAML escaping variants).
    assert "REDIS_PASSWORD" in password_value, (
        f"REDIS_PASSWORD must use ${{REDIS_PASSWORD}} interpolation, got {password_value!r}"
    )


def test_allowed_origins_includes_caddy_canonical(ws_hub_env: dict[str, str]) -> None:
    """W173 polish-v3 Fix F: ALLOWED_ORIGINS must include http://localhost.

    The dev Caddy proxy listens on port 80, so browser Origin header
    is `http://localhost` (no port). ws-hub CheckOrigin must accept
    this value or WS upgrade returns 403.
    """
    assert "ALLOWED_ORIGINS" in ws_hub_env, (
        "W173 polish-v3 Fix F regression: ws-hub must set ALLOWED_ORIGINS env"
    )
    origins = ws_hub_env["ALLOWED_ORIGINS"]
    # Origins are comma-separated in the env var
    origin_list = [o.strip() for o in origins.split(",")]
    assert "http://localhost" in origin_list, (
        f"ALLOWED_ORIGINS must include 'http://localhost' (Caddy canonical port-80 "
        f"origin per W173 polish-v3), got {origin_list!r}"
    )


def test_allowed_origins_includes_vite_dev_ports(ws_hub_env: dict[str, str]) -> None:
    """Sanity: ALLOWED_ORIGINS should preserve Vite dev parity (localhost:5173).

    Wave 173 polish-v3 framework note: "covers Caddy canonical + direct
    frontend port + Vite dev parity". This guards against future regressions
    that might strip the dev ports during deploy infra changes.
    """
    origins = ws_hub_env["ALLOWED_ORIGINS"]
    origin_list = [o.strip() for o in origins.split(",")]
    assert "http://localhost:5173" in origin_list, (
        f"ALLOWED_ORIGINS must preserve Vite dev port (http://localhost:5173) per "
        f"W173 polish-v3, got {origin_list!r}"
    )
