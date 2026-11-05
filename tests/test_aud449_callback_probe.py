"""Keep emitted-log probes pointed at the registered Spotify callback."""

from __future__ import annotations

import secrets
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

from tests import aud178_449_gunicorn_proof as gunicorn_proof
from tests import test_caddy_emitted_log_redaction_docker as caddy_proof


@pytest.fixture
def spotify_callback_path(monkeypatch: pytest.MonkeyPatch) -> str:
    # Import and build the actual public router without opening a database.
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setitem(sys.modules, "magic", None)
    from fastapi import FastAPI

    from app.api.public import router

    app = FastAPI()
    app.include_router(router)
    callbacks = [
        path
        for path, methods in app.openapi()["paths"].items()
        if methods.get("get", {}).get("operationId", "").startswith("spotify_callback_")
    ]
    assert len(callbacks) == 1
    return callbacks[0]


def test_caddy_probe_requests_the_registered_callback(
    spotify_callback_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths: list[str] = []

    def request(_scheme: str, _port: int, target: str, **_kwargs: object) -> int:
        path = urlsplit(target).path
        if path.endswith("/spotify/callback"):
            paths.append(path)
        return 502

    def logs(_container: str) -> str:
        callback = next(path for path in paths if path.endswith("/spotify/callback"))
        return " ".join(
            (
                "/login?",
                *caddy_proof._REDACTION_MARKERS,
                f"{callback}?code=REDACTED&state=REDACTED",
            )
        )

    monkeypatch.setattr(caddy_proof, "_request", request)
    monkeypatch.setattr(caddy_proof, "_container_logs", logs)
    caddy_proof._probe_edge("http", 0, "unused")

    assert spotify_callback_path in paths


def test_gunicorn_probe_requests_the_registered_callback(
    spotify_callback_path: str,
) -> None:
    marker = secrets.token_hex(12)
    oauth_target = gunicorn_proof._probe_targets(marker, "query", "path")[0]
    assert urlsplit(oauth_target).path == spotify_callback_path
    assert parse_qs(urlsplit(oauth_target).query)["code"] == [marker]
