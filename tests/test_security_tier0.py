"""Behavioral Tier0 tests for authentication security boundaries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest


def test_argon2_semaphore_is_cached_per_loop_key() -> None:
    from app.auth import security

    first = security._get_argon2_semaphore_for_loop(91001)
    second = security._get_argon2_semaphore_for_loop(91001)

    assert first is second


@pytest.mark.asyncio
async def test_async_password_wrappers_offload_sync_operations() -> None:
    from app.auth import security

    semaphore = security._get_argon2_semaphore()
    assert semaphore is security._get_argon2_semaphore()

    with patch.object(security, "verify_password_sync", return_value=True):
        assert await security.verify_password("password", "hash") is True

    with patch.object(
        security,
        "verify_and_update_password_sync",
        return_value=(True, None),
    ):
        assert await security.verify_and_update_password("password", "hash") == (
            True,
            None,
        )

    with patch.object(
        security,
        "get_password_hash_sync",
        return_value="$argon2id$test",
    ):
        assert await security.get_password_hash("password") == "$argon2id$test"


def test_verify_password_sync_accepts_valid_argon2_hash() -> None:
    from app.auth import security

    mock_hasher = MagicMock()
    mock_hasher.verify.return_value = None
    with patch.object(security, "argon2_hasher", mock_hasher):
        assert security.verify_password_sync("password", "$argon2id$valid") is True


def test_verify_and_update_rehashes_valid_argon2_hash() -> None:
    from app.auth import security

    mock_hasher = MagicMock()
    mock_hasher.check_needs_rehash.return_value = True
    mock_hasher.hash.return_value = "$argon2id$new"
    with patch.object(security, "argon2_hasher", mock_hasher):
        assert security.verify_and_update_password_sync(
            "password", "$argon2id$old"
        ) == (True, "$argon2id$new")


def test_password_policy_rejects_short_password(monkeypatch) -> None:
    from app.auth import security
    from app.core.config import settings

    monkeypatch.setattr(settings, "password_min_length", 8)
    monkeypatch.setattr(settings, "password_max_length", 200)

    with pytest.raises(ValueError, match="Password must be"):
        security.get_password_hash_sync("short", locale="en")


def test_mint_pure_jwt_emits_required_claims(monkeypatch) -> None:
    from app.auth import security
    from app.core.config import settings

    monkeypatch.setattr(settings, "algorithm", "HS256")
    monkeypatch.setattr(settings, "jwt_audience", "tier0-audience")

    with (
        patch.object(
            type(settings),
            "jwt_signing_active_kid",
            new=property(lambda _: "tier0"),
        ),
        patch.object(
            type(settings),
            "jwt_signing_active_secret",
            new=property(lambda _: "tier0-signing-secret-with-at-least-32-bytes"),
        ),
    ):
        token = security._mint_pure_jwt(
            "security-user",
            expires_minutes=1,
            extra_claims={"role": "student"},
        )
        signing_secret = settings.jwt_signing_active_secret

    payload = jwt.decode(
        token,
        signing_secret,
        algorithms=["HS256"],
        audience="tier0-audience",
    )

    assert jwt.get_unverified_header(token)["kid"] == "tier0"
    assert payload["sub"] == "security-user"
    assert payload["role"] == "student"
    assert {"aud", "iat", "nbf", "exp", "jti"} <= payload.keys()


@pytest.mark.asyncio
async def test_hibp_request_error_is_fail_closed_by_default(monkeypatch) -> None:
    from app.auth import security
    from app.core.config import settings

    monkeypatch.setattr(settings, "password_hibp_fail_open", False)

    with (
        patch.object(
            security,
            "_get_hibp_client",
            AsyncMock(side_effect=httpx.RequestError("HIBP unavailable")),
        ),
        patch.object(security, "translate", return_value="unavailable"),
    ):
        with pytest.raises(ValueError, match="unavailable"):
            await security.validate_password_hibp("password")


@pytest.mark.asyncio
async def test_hibp_request_error_can_fail_open(monkeypatch) -> None:
    from app.auth import security
    from app.core.config import settings

    monkeypatch.setattr(settings, "password_hibp_fail_open", True)

    with patch.object(
        security,
        "_get_hibp_client",
        AsyncMock(side_effect=httpx.RequestError("HIBP unavailable")),
    ):
        await security.validate_password_hibp("password")


@pytest.mark.asyncio
async def test_hibp_non_ok_response_is_fail_closed_or_open(monkeypatch) -> None:
    from app.auth import security
    from app.core.config import settings

    response = MagicMock(status_code=503, text="")
    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    monkeypatch.setattr(settings, "password_hibp_fail_open", False)
    with (
        patch.object(security, "_get_hibp_client", AsyncMock(return_value=client)),
        patch.object(security, "translate", return_value="unavailable"),
    ):
        with pytest.raises(ValueError, match="unavailable"):
            await security.validate_password_hibp("password")

    monkeypatch.setattr(settings, "password_hibp_fail_open", True)
    with patch.object(security, "_get_hibp_client", AsyncMock(return_value=client)):
        await security.validate_password_hibp("password")


@pytest.mark.asyncio
async def test_hibp_positive_match_rejects_compromised_password(monkeypatch) -> None:
    from app.auth import security
    from app.core.config import settings

    monkeypatch.setattr(settings, "password_hibp_fail_open", False)
    suffix = security._calculate_lookup_hash("password")[5:]
    response = MagicMock(status_code=200, text=f"{suffix}:7\n")
    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    with (
        patch.object(security, "_get_hibp_client", AsyncMock(return_value=client)),
        patch.object(security, "translate", return_value="compromised"),
    ):
        with pytest.raises(ValueError, match="compromised"):
            await security.validate_password_hibp("password")


@pytest.mark.asyncio
async def test_close_hibp_client_is_noop_when_not_initialized() -> None:
    from app.auth import security

    security._hibp_client = None
    await security.close_hibp_client()
    assert security._hibp_client is None
