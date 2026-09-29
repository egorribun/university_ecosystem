"""Environment gates for the token HMAC key and the revocation datastore."""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.revocation import get_revocation_redis_client
from app.core.config.cache import DEFAULT_REVOCATION_REDIS_URL
from app.services.auth_service import _token_hmac_secret

FALLBACK_KEY = "fallback-signing-key"  # pragma: allowlist secret
DEDICATED_KEY = "dedicated-signing-key"  # pragma: allowlist secret


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "token_hmac_secret": None,
        "environment": "development",
        "secret_key": FALLBACK_KEY,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_an_explicit_token_key_wins_everywhere() -> None:
    with patch(
        "app.services.auth_service.settings",
        _settings(token_hmac_secret=DEDICATED_KEY, environment="production"),
    ):
        assert _token_hmac_secret() == DEDICATED_KEY


@pytest.mark.parametrize("environment", ["production", "staging", "Staging"])
def test_production_like_environments_refuse_the_fallback(environment: str) -> None:
    message = (
        "TOKEN_HMAC_SECRET must be set explicitly in production/staging. "
        "Falling back to secret_key couples JWT rotation to token invalidation."
    )
    with (
        patch("app.services.auth_service.settings", _settings(environment=environment)),
        pytest.raises(RuntimeError, match=f"^{re.escape(message)}$"),
    ):
        _token_hmac_secret()


@pytest.mark.parametrize("environment", ["development", "testing", ""])
def test_other_environments_fall_back_loudly(environment: str) -> None:
    logger = MagicMock()
    with (
        patch("app.services.auth_service.settings", _settings(environment=environment)),
        patch("app.services.auth_service.logger", logger),
    ):
        assert _token_hmac_secret() == FALLBACK_KEY

    logger.warning.assert_called_once_with(
        "TOKEN_HMAC_SECRET is unset — falling back to secret_key (DEV/TESTING ONLY). "
        "Set TOKEN_HMAC_SECRET before deploying to staging or production."
    )


def _revocation_settings(url: str, environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        revocation_redis_access_enabled=True,
        app_process_role="api",
        revocation_redis_url=url,
        environment=environment,
    )


@pytest.mark.asyncio
async def test_a_role_without_revocation_access_is_named_in_the_refusal() -> None:
    settings = _revocation_settings("redis://revocation.internal:6379/0", "production")
    settings.revocation_redis_access_enabled = False
    settings.app_process_role = "outbox-worker"
    with (
        patch("app.core.config.settings", settings),
        pytest.raises(
            RuntimeError,
            match=re.escape(
                "REVOCATION_REDIS access is disabled for this process role "
                "('outbox-worker')"
            ),
        ),
    ):
        await get_revocation_redis_client()


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["development", "local", "testing", "Testing"])
async def test_the_loopback_default_serves_development_environments(
    environment: str,
) -> None:
    client = object()
    connect = AsyncMock(return_value=client)
    with (
        patch(
            "app.core.config.settings",
            _revocation_settings(DEFAULT_REVOCATION_REDIS_URL, environment),
        ),
        patch("app.core.ratelimit.get_shared_client", connect),
    ):
        assert await get_revocation_redis_client() is client

    connect.assert_awaited_once_with(DEFAULT_REVOCATION_REDIS_URL)


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["production", "staging", ""])
async def test_the_loopback_default_fails_closed_elsewhere(environment: str) -> None:
    with (
        patch(
            "app.core.config.settings",
            _revocation_settings(DEFAULT_REVOCATION_REDIS_URL, environment),
        ),
        patch("app.core.ratelimit.get_shared_client", AsyncMock()) as connect,
        pytest.raises(RuntimeError, match=r"^REVOCATION_REDIS_URL is not configured$"),
    ):
        await get_revocation_redis_client()

    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_explicit_url_serves_production() -> None:
    connect = AsyncMock(return_value="client")
    with (
        patch(
            "app.core.config.settings",
            _revocation_settings(" redis://revocation.internal:6379/0 ", "production"),
        ),
        patch("app.core.ratelimit.get_shared_client", connect),
    ):
        assert await get_revocation_redis_client() == "client"

    connect.assert_awaited_once_with("redis://revocation.internal:6379/0")
