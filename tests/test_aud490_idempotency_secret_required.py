"""AUD-490: non-development environments must set IDEMPOTENCY_HMAC_SECRET."""

from __future__ import annotations

import os
import secrets
from unittest.mock import patch

import pytest

from app.core.config.integrations import IntegrationSettings

# Every other production secret is valid, so only the idempotency check varies.
# Values are generated per run; literal credential-shaped strings are not committed.
_OTHER_SECRETS: dict[str, str] = {
    "elasticsearch_password": secrets.token_urlsafe(24),
    "spicedb_preshared_key": secrets.token_urlsafe(24),
    "ws_hub_internal_secret": secrets.token_urlsafe(24),
}


def _environment(name: str, *, ci: str = "false") -> dict[str, str]:
    return {"ENVIRONMENT": name, "CI": ci, "GITHUB_ACTIONS": "false"}


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud490_empty_idempotency_secret_fails_closed_outside_development(
    environment: str,
) -> None:
    with patch.dict(os.environ, _environment(environment)):
        with pytest.raises(
            ValueError, match="IDEMPOTENCY_HMAC_SECRET must be set in production"
        ):
            IntegrationSettings(
                _allow_missing=True, idempotency_hmac_secret="", **_OTHER_SECRETS
            )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_aud490_configured_idempotency_secret_is_accepted(environment: str) -> None:
    secret = secrets.token_urlsafe(32)
    with patch.dict(os.environ, _environment(environment)):
        settings = IntegrationSettings(
            _allow_missing=True,
            idempotency_hmac_secret=secret,
            **_OTHER_SECRETS,
        )

    assert settings.idempotency_hmac_secret == secret


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_aud490_local_environments_keep_the_unkeyed_fallback(environment: str) -> None:
    with patch.dict(os.environ, _environment(environment)):
        settings = IntegrationSettings(
            _allow_missing=True, idempotency_hmac_secret="", **_OTHER_SECRETS
        )

    assert settings.idempotency_hmac_secret == ""


def test_aud490_ci_exemption_still_skips_the_production_secret_checks() -> None:
    with patch.dict(os.environ, _environment("production", ci="true")):
        settings = IntegrationSettings(
            _allow_missing=True, idempotency_hmac_secret="", **_OTHER_SECRETS
        )

    assert settings.idempotency_hmac_secret == ""
