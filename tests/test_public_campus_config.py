"""Public campus configuration API contract tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import public_config
from app.api.public import router as public_api_router
from app.core.config.app_gen import AppGeneralSettings


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(public_api_router)
    return TestClient(app)


def test_campus_config_is_public_versioned_and_contains_no_config_dump() -> None:
    with _client() as client:
        response = client.get("/api/v1/campus/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"campus_timezone": public_config.settings.campus_timezone}
    assert set(payload) == {"campus_timezone"}
    assert response.url.path == "/api/v1/campus/config"


def test_campus_config_uses_validated_non_utc_server_setting(monkeypatch) -> None:
    configured = AppGeneralSettings(
        _allow_missing=True,
        environment="development",
        campus_timezone=" Europe/Istanbul ",
    )
    assert configured.campus_timezone == "Europe/Istanbul"
    monkeypatch.setattr(public_config, "settings", configured)

    with _client() as client:
        response = client.get("/api/v1/campus/config")

    assert response.status_code == 200
    assert response.json() == {"campus_timezone": "Europe/Istanbul"}
