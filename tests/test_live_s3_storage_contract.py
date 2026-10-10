"""Contracts for live-only S3 configuration and standalone storage defaults."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from app.core.config import Settings
from app.core.config.storage import StorageSettings
from app.services.storage import S3Storage, get_storage_backend

ROOT = Path(__file__).resolve().parents[1]


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("compose document section must be a mapping")

    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise AssertionError("compose mapping keys must be strings")
        result[key] = item
    return result


def _compose(path: Path) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    return _mapping(
        yaml.safe_load(source.replace("!override", "").replace("!reset", ""))
    )


def _live_overlay() -> dict[str, object]:
    return _compose(ROOT / "docker-compose.live.yml")


def _compose_variable_name(value: object) -> str:
    if not isinstance(value, str):
        raise AssertionError("compose credential reference must be text")
    match = re.fullmatch(r"\$\{([A-Z][A-Z0-9_]*)(?::[-?][^}]*)?\}", value)
    if match is None:
        raise AssertionError("compose credential reference must use interpolation")
    return match.group(1)


def _required_live_variable(value: object) -> str:
    if not isinstance(value, str):
        raise AssertionError("live storage reference must be text")
    match = re.fullmatch(r"\$\{([A-Z][A-Z0-9_]*):\?required\}", value)
    if match is None:
        raise AssertionError("live storage variables must be required")
    return match.group(1)


def test_live_backend_and_delivery_workers_use_owned_s3_configuration() -> None:
    services = _mapping(_live_overlay()["services"])
    backend = _mapping(_mapping(services["backend"])["environment"])

    assert backend["STORAGE_BACKEND"] == "minio"
    assert backend["STORAGE_S3_BUCKET"] == "uploads"
    assert backend["STORAGE_S3_REGION"] == "us-east-1"
    assert backend["STORAGE_S3_ENDPOINT_URL"] == "http://minio:9000"
    assert backend["STORAGE_S3_BASE_URL"] == "${LIVE_BASE_URL:?required}/api/v1/img"

    base_compose = _compose(ROOT / "docker-compose.full.yml")
    base_services = _mapping(base_compose["services"])
    minio = _mapping(_mapping(base_services["minio"])["environment"])
    assert _required_live_variable(backend["STORAGE_S3_ACCESS_KEY_ID"]) == (
        _compose_variable_name(minio["AWS_ACCESS_KEY_ID"])
    )
    assert _required_live_variable(backend["STORAGE_S3_SECRET_ACCESS_KEY"]) == (
        _compose_variable_name(minio["AWS_SECRET_ACCESS_KEY"])
    )

    for worker in ("outbox-worker", "notifications-worker"):
        assert _mapping(_mapping(services[worker])["environment"]) == backend
    assert "STORAGE_BACKEND" not in _mapping(
        _mapping(services.get("migrations", {})).get("environment", {})
    )


def test_live_storage_settings_map_public_object_urls_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_origin = "http://127.0.0.1:49123"
    monkeypatch.setenv("STORAGE_BACKEND", "minio")
    monkeypatch.setenv("STORAGE_S3_BUCKET", "uploads")
    monkeypatch.setenv("STORAGE_S3_REGION", "us-east-1")
    monkeypatch.setenv("STORAGE_S3_ACCESS_KEY_ID", uuid4().hex)
    monkeypatch.setenv("STORAGE_S3_SECRET_ACCESS_KEY", uuid4().hex)
    monkeypatch.setenv("STORAGE_S3_ENDPOINT_URL", "http://minio:9000")
    live_services = _mapping(_live_overlay()["services"])
    live_backend = _mapping(_mapping(live_services["backend"])["environment"])
    base_url_template = live_backend["STORAGE_S3_BASE_URL"]
    assert isinstance(base_url_template, str)
    public_origin_variable = "${LIVE_BASE_URL:?required}"
    assert base_url_template.startswith(public_origin_variable)
    live_public_base_url = base_url_template.replace(
        public_origin_variable, public_origin, 1
    )
    monkeypatch.setenv("STORAGE_S3_BASE_URL", live_public_base_url)

    settings = Settings(
        _allow_missing=True,
        environment="testing",
        database_url="sqlite+aiosqlite:///./unused-private-test.db",
        secret_key=uuid4().hex,
    )
    storage = get_storage_backend(settings)

    assert isinstance(storage, S3Storage)
    assert settings.storage_s3_region == "us-east-1"
    assert settings.storage_s3_endpoint_url == "http://minio:9000"
    assert settings.storage_s3_access_key_id
    assert settings.storage_s3_secret_access_key
    assert storage.bucket == "uploads"
    assert storage.base_url == f"{public_origin}/api/v1/img"
    object_key = f"avatars/{uuid4().hex}.png"
    assert storage._extract_key(f"{storage.base_url}/{object_key}") == object_key
    legacy_url = f"{public_origin}/storage/uploads/{object_key}"
    assert storage._extract_key(legacy_url) is None


def test_standalone_storage_settings_keep_static_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "STORAGE_BACKEND",
        "STORAGE_S3_BUCKET",
        "STORAGE_S3_REGION",
        "STORAGE_S3_ACCESS_KEY_ID",
        "STORAGE_S3_SECRET_ACCESS_KEY",
        "STORAGE_S3_ENDPOINT_URL",
        "STORAGE_S3_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = StorageSettings(_allow_missing=True)

    assert settings.storage_backend == "static"
    assert settings.storage_s3_bucket == ""
    assert settings.storage_s3_endpoint_url == ""
    assert settings.storage_s3_base_url == ""
