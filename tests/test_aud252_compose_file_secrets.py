"""Production Compose uses explicit file-backed secret sources, not Swarm refs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_s3_cutover_compose_contract import (
    _PRODUCTION_SECRET_SOURCE_VARIABLES,
    _compose_config_result,
    _production_secret_source_overrides,
    _rendered,
)

_PRODUCTION_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.prod.yml")
_SECRET_NAMES = (
    "secret_key",
    "database_url",
    "nats_auth_token",
    "cache_redis_url",
    "rate_limit_storage_uri",
    "revocation_redis_url",
    "postgres_password",
    "mfa_totp_encryption_keys",
    "vapid_private_key",
    "spotify_client_secret",
    "spotify_oauth_state_secret",
    "spotify_token_secret",
    "audit_log_secret",
    "elasticsearch_password",
    "internal_auth_token",
    "internal_hmac_secret",
    "spicedb_preshared_key",
    "token_hmac_secret",
    "idempotency_hmac_secret",
    "ws_hub_internal_secret",
)
# Every Compose secret name uses the matching <NAME>_SOURCE_FILE variable.
_SECRET_SOURCE_VARIABLES = {
    name: f"{name.upper()}_SOURCE_FILE" for name in _SECRET_NAMES
}
_PRODUCTION_SERVICE_SECRETS = {
    "backend": {
        "secret_key",
        "database_url",
        "nats_auth_token",
        "cache_redis_url",
        "rate_limit_storage_uri",
        "revocation_redis_url",
        "mfa_totp_encryption_keys",
        "vapid_private_key",
        "spotify_client_secret",
        "spotify_oauth_state_secret",
        "spotify_token_secret",
        "audit_log_secret",
        "elasticsearch_password",
        "internal_auth_token",
        "internal_hmac_secret",
        "spicedb_preshared_key",
        "token_hmac_secret",
        "idempotency_hmac_secret",
        "ws_hub_internal_secret",
    },
    "notifications-worker": {
        "secret_key",
        "database_url",
        "nats_auth_token",
        "cache_redis_url",
        "rate_limit_storage_uri",
        "vapid_private_key",
        "spotify_token_secret",
        "audit_log_secret",
        "elasticsearch_password",
        "internal_auth_token",
        "internal_hmac_secret",
        "spicedb_preshared_key",
        "token_hmac_secret",
        "idempotency_hmac_secret",
        "ws_hub_internal_secret",
    },
    "outbox-worker": {
        "secret_key",
        "database_url",
        "nats_auth_token",
        "cache_redis_url",
        "spotify_token_secret",
        "audit_log_secret",
        "elasticsearch_password",
        "internal_auth_token",
        "internal_hmac_secret",
        "spicedb_preshared_key",
        "token_hmac_secret",
        "idempotency_hmac_secret",
        "ws_hub_internal_secret",
    },
    "migrations": {
        "secret_key",
        "database_url",
        "nats_auth_token",
        "cache_redis_url",
        "revocation_redis_url",
        "mfa_totp_encryption_keys",
        "spotify_token_secret",
        "audit_log_secret",
        "elasticsearch_password",
        "internal_auth_token",
        "internal_hmac_secret",
        "spicedb_preshared_key",
        "token_hmac_secret",
        "idempotency_hmac_secret",
        "ws_hub_internal_secret",
    },
    "postgres": {"postgres_password"},
    "pgbouncer": {"postgres_password"},
}
_SERVICE_FILE_ENVIRONMENT = {
    "backend": {
        "SECRET_KEY_FILE": "/run/secrets/secret_key",
        "DATABASE_URL_FILE": "/run/secrets/database_url",
        "NATS_AUTH_TOKEN_FILE": "/run/secrets/nats_auth_token",
        "CACHE_REDIS_URL_FILE": "/run/secrets/cache_redis_url",
        "RATE_LIMIT_STORAGE_URI_FILE": "/run/secrets/rate_limit_storage_uri",
        "REVOCATION_REDIS_URL_FILE": "/run/secrets/revocation_redis_url",
        "MFA_TOTP_ENCRYPTION_KEYS_FILE": "/run/secrets/mfa_totp_encryption_keys",
        "VAPID_PRIVATE_KEY_FILE": "/run/secrets/vapid_private_key",
        "SPOTIFY_CLIENT_SECRET_FILE": "/run/secrets/spotify_client_secret",
        "SPOTIFY_OAUTH_STATE_SECRET_FILE": "/run/secrets/spotify_oauth_state_secret",
        "SPOTIFY_TOKEN_SECRET_FILE": "/run/secrets/spotify_token_secret",
        "AUDIT_LOG_SECRET_FILE": "/run/secrets/audit_log_secret",
        "ELASTICSEARCH_PASSWORD_FILE": "/run/secrets/elasticsearch_password",
        "INTERNAL_AUTH_TOKEN_FILE": "/run/secrets/internal_auth_token",
        "INTERNAL_HMAC_SECRET_FILE": "/run/secrets/internal_hmac_secret",
        "SPICEDB_PRESHARED_KEY_FILE": "/run/secrets/spicedb_preshared_key",
        "TOKEN_HMAC_SECRET_FILE": "/run/secrets/token_hmac_secret",
        "IDEMPOTENCY_HMAC_SECRET_FILE": "/run/secrets/idempotency_hmac_secret",
        "WS_HUB_INTERNAL_SECRET_FILE": "/run/secrets/ws_hub_internal_secret",
    },
    "notifications-worker": {
        "SECRET_KEY_FILE": "/run/secrets/secret_key",
        "DATABASE_URL_FILE": "/run/secrets/database_url",
        "NATS_AUTH_TOKEN_FILE": "/run/secrets/nats_auth_token",
        "CACHE_REDIS_URL_FILE": "/run/secrets/cache_redis_url",
        "RATE_LIMIT_STORAGE_URI_FILE": "/run/secrets/rate_limit_storage_uri",
        "VAPID_PRIVATE_KEY_FILE": "/run/secrets/vapid_private_key",
        "SPOTIFY_TOKEN_SECRET_FILE": "/run/secrets/spotify_token_secret",
        "AUDIT_LOG_SECRET_FILE": "/run/secrets/audit_log_secret",
        "ELASTICSEARCH_PASSWORD_FILE": "/run/secrets/elasticsearch_password",
        "INTERNAL_AUTH_TOKEN_FILE": "/run/secrets/internal_auth_token",
        "INTERNAL_HMAC_SECRET_FILE": "/run/secrets/internal_hmac_secret",
        "SPICEDB_PRESHARED_KEY_FILE": "/run/secrets/spicedb_preshared_key",
        "TOKEN_HMAC_SECRET_FILE": "/run/secrets/token_hmac_secret",
        "IDEMPOTENCY_HMAC_SECRET_FILE": "/run/secrets/idempotency_hmac_secret",
        "WS_HUB_INTERNAL_SECRET_FILE": "/run/secrets/ws_hub_internal_secret",
    },
    "outbox-worker": {
        "SECRET_KEY_FILE": "/run/secrets/secret_key",
        "DATABASE_URL_FILE": "/run/secrets/database_url",
        "NATS_AUTH_TOKEN_FILE": "/run/secrets/nats_auth_token",
        "CACHE_REDIS_URL_FILE": "/run/secrets/cache_redis_url",
        "SPOTIFY_TOKEN_SECRET_FILE": "/run/secrets/spotify_token_secret",
        "AUDIT_LOG_SECRET_FILE": "/run/secrets/audit_log_secret",
        "ELASTICSEARCH_PASSWORD_FILE": "/run/secrets/elasticsearch_password",
        "INTERNAL_AUTH_TOKEN_FILE": "/run/secrets/internal_auth_token",
        "INTERNAL_HMAC_SECRET_FILE": "/run/secrets/internal_hmac_secret",
        "SPICEDB_PRESHARED_KEY_FILE": "/run/secrets/spicedb_preshared_key",
        "TOKEN_HMAC_SECRET_FILE": "/run/secrets/token_hmac_secret",
        "IDEMPOTENCY_HMAC_SECRET_FILE": "/run/secrets/idempotency_hmac_secret",
        "WS_HUB_INTERNAL_SECRET_FILE": "/run/secrets/ws_hub_internal_secret",
    },
    "migrations": {
        "SECRET_KEY_FILE": "/run/secrets/secret_key",
        "DATABASE_URL_FILE": "/run/secrets/database_url",
        "NATS_AUTH_TOKEN_FILE": "/run/secrets/nats_auth_token",
        "CACHE_REDIS_URL_FILE": "/run/secrets/cache_redis_url",
        "REVOCATION_REDIS_URL_FILE": "/run/secrets/revocation_redis_url",
        "MFA_TOTP_ENCRYPTION_KEYS_FILE": "/run/secrets/mfa_totp_encryption_keys",
        "SPOTIFY_TOKEN_SECRET_FILE": "/run/secrets/spotify_token_secret",
        "AUDIT_LOG_SECRET_FILE": "/run/secrets/audit_log_secret",
        "ELASTICSEARCH_PASSWORD_FILE": "/run/secrets/elasticsearch_password",
        "INTERNAL_AUTH_TOKEN_FILE": "/run/secrets/internal_auth_token",
        "INTERNAL_HMAC_SECRET_FILE": "/run/secrets/internal_hmac_secret",
        "SPICEDB_PRESHARED_KEY_FILE": "/run/secrets/spicedb_preshared_key",
        "TOKEN_HMAC_SECRET_FILE": "/run/secrets/token_hmac_secret",
        "IDEMPOTENCY_HMAC_SECRET_FILE": "/run/secrets/idempotency_hmac_secret",
        "WS_HUB_INTERNAL_SECRET_FILE": "/run/secrets/ws_hub_internal_secret",
    },
}
_SECRET_PLAINTEXT_ENVIRONMENT = (
    "SECRET_KEY",
    "DATABASE_URL",
    "NATS_AUTH_TOKEN",
    "CACHE_REDIS_URL",
    "RATE_LIMIT_STORAGE_URI",
    "REVOCATION_REDIS_URL",
    "MFA_TOTP_ENCRYPTION_KEYS",
    "VAPID_PRIVATE_KEY",
    "SPOTIFY_CLIENT_SECRET",
    "SPOTIFY_OAUTH_STATE_SECRET",
    "SPOTIFY_TOKEN_SECRET",
    "AUDIT_LOG_SECRET",
    "ELASTICSEARCH_PASSWORD",
    "INTERNAL_AUTH_TOKEN",
    "INTERNAL_HMAC_SECRET",
    "SPICEDB_PRESHARED_KEY",
    "TOKEN_HMAC_SECRET",
    "WS_HUB_INTERNAL_SECRET",
)


def _secret_names(service: dict[str, Any]) -> set[str]:
    return {str(secret["source"]) for secret in service.get("secrets", [])}


def test_production_profile_renders_only_file_backed_secret_sources(
    tmp_path: Path,
) -> None:
    compose_source = (
        Path(__file__).resolve().parents[1] / "docker-compose.prod.yml"
    ).read_text(encoding="utf-8")
    for source_variable in _SECRET_SOURCE_VARIABLES.values():
        required_source = (
            f"file: ${{{source_variable}:?Set {source_variable} for production}}"
        )
        assert required_source in compose_source

    overrides = _production_secret_source_overrides(tmp_path)
    overrides["MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID"] = "synthetic-active-key-id"
    model = _rendered(
        tmp_path,
        "aud252-file-secrets",
        *_PRODUCTION_COMPOSE_FILES,
        profiles=("prod",),
        environment_overrides=overrides,
    )

    assert set(model["secrets"]) == set(_SECRET_SOURCE_VARIABLES)
    for secret_name, variable in _SECRET_SOURCE_VARIABLES.items():
        rendered = model["secrets"][secret_name]
        assert Path(rendered["file"]).resolve() == Path(overrides[variable]).resolve()
        assert rendered.get("external") is not True
        assert not {"uid", "gid", "mode"}.intersection(rendered)

    assert "synthetic compose contract fixture" not in json.dumps(model)

    services = model["services"]
    python_services = {"backend", "notifications-worker", "outbox-worker", "migrations"}
    for service_name, expected_secrets in _PRODUCTION_SERVICE_SECRETS.items():
        service = services[service_name]
        assert _secret_names(service) == expected_secrets
        if service_name in python_services:
            environment = service["environment"]
            assert environment["ENVIRONMENT"] == "production"
            assert str(environment["MINIO_SECURE"]).lower() == "true"
            assert environment["ELASTICSEARCH_URL"] == overrides["ELASTICSEARCH_URL"]
            assert environment["SPICEDB_ENDPOINT"] == overrides["SPICEDB_ENDPOINT"]
            assert str(environment["EVENT_FILE_SCANNER_ENABLED"]).lower() == "true"
            assert (
                environment["EVENT_FILE_SCANNER_HOST"]
                == (overrides["EVENT_FILE_SCANNER_HOST"])
            )
            assert str(environment["EVENT_FILE_SCANNER_PORT"]) == "3310"
            assert not set(_SECRET_PLAINTEXT_ENVIRONMENT).intersection(environment)

    for service_name, expected_environment in _SERVICE_FILE_ENVIRONMENT.items():
        environment = services[service_name]["environment"]
        for variable, path in expected_environment.items():
            assert environment[variable] == path
        for secret_variable in expected_environment:
            assert secret_variable.removesuffix("_FILE") not in environment

    backend_environment = services["backend"]["environment"]
    assert "VAPID_PRIVATE_KEY" not in backend_environment
    assert "SPOTIFY_CLIENT_SECRET" not in backend_environment
    notifications_environment = services["notifications-worker"]["environment"]
    assert "VAPID_PRIVATE_KEY" not in notifications_environment
    assert "SPOTIFY_CLIENT_SECRET" not in notifications_environment
    assert "SPOTIFY_CLIENT_SECRET_FILE" not in notifications_environment
    assert "SPOTIFY_CLIENT_ID" not in notifications_environment

    for service_name in (
        "backend",
        "notifications-worker",
        "outbox-worker",
        "migrations",
    ):
        environment = services[service_name]["environment"]
        assert "SPOTIFY_TOKEN_SECRET" not in environment
        assert environment["SPOTIFY_TOKEN_SECRET_FILE"] == (
            "/run/secrets/spotify_token_secret"
        )
    backend_environment = services["backend"]["environment"]
    assert "SPOTIFY_OAUTH_STATE_SECRET" not in backend_environment
    assert backend_environment["SPOTIFY_OAUTH_STATE_SECRET_FILE"] == (
        "/run/secrets/spotify_oauth_state_secret"
    )

    for service_name in ("backend", "migrations"):
        environment = services[service_name]["environment"]
        assert (
            environment["MFA_TOTP_ENCRYPTION_KEYS_FILE"]
            == "/run/secrets/mfa_totp_encryption_keys"
        )
        assert (
            environment["MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID"]
            == "synthetic-active-key-id"
        )
        assert "MFA_TOTP_ENCRYPTION_KEYS" not in environment
        assert "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID_FILE" not in environment

    for service_name in ("notifications-worker", "outbox-worker"):
        environment = services[service_name]["environment"]
        assert "MFA_TOTP_ENCRYPTION_KEYS" not in environment
        assert "MFA_TOTP_ENCRYPTION_KEYS_FILE" not in environment
        assert "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID" not in environment
        assert "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID_FILE" not in environment

    postgres_environment = services["postgres"]["environment"]
    assert postgres_environment["POSTGRES_PASSWORD_FILE"] == (
        "/run/secrets/postgres_password"
    )


@pytest.mark.parametrize(
    "missing_variable",
    (
        *_PRODUCTION_SECRET_SOURCE_VARIABLES,
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID",
        "ELASTICSEARCH_URL",
        "SPICEDB_ENDPOINT",
        "EVENT_FILE_SCANNER_HOST",
        "TRUSTED_PROXIES",
    ),
)
def test_production_render_fails_when_required_secret_path_or_key_id_is_missing(
    tmp_path: Path, missing_variable: str
) -> None:
    overrides = _production_secret_source_overrides(tmp_path)
    overrides.pop(missing_variable, None)
    result = _compose_config_result(
        tmp_path,
        "aud252-missing-secret-input",
        *_PRODUCTION_COMPOSE_FILES,
        profiles=("prod",),
        environment_overrides=overrides,
        unset_environment=(missing_variable,),
    )

    assert result.returncode != 0
    assert missing_variable in result.stderr
