from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.auth import login as login_api
from app.auth.schemas import LoginIn, MfaVerifyIn, PendingMfaResponse


def _request() -> MagicMock:
    request = MagicMock()
    request.state.active_session = None
    request.cookies = {"mfa_pre_auth_v1": "preauth"}
    request.headers = {"user-agent": "test"}
    request.client.host = "203.0.113.8"
    return request


@pytest.mark.asyncio
async def test_register_value_error_rolls_back() -> None:
    compliance = AsyncMock()
    compliance.register_user.side_effect = ValueError("duplicate")
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await login_api.register.__dishka_orig_func__(
            MagicMock(), _request(), compliance, AsyncMock(), db
        )
    assert exc.value.status_code == 400
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_json_pending_mfa_commits_digest_bound_challenges() -> None:
    pending = PendingMfaResponse(user_id=uuid4(), methods=[])
    service = AsyncMock()
    service.perform_login.return_value = pending
    db = AsyncMock()
    result = await login_api.login_json.__dishka_orig_func__(
        LoginIn(
            email="student@example.com",
            password="valid-password",  # pragma: allowlist secret
        ),
        MagicMock(),
        _request(),
        MagicMock(),
        service,
        db,
    )
    assert result is pending
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["totp", "recovery_code"])
async def test_generic_verify_branches_finalize_login(method: str) -> None:
    challenge = SimpleNamespace(
        user_id=uuid4(),
        method=method,
        flow="login",
        trust_device_requested=False,
    )
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=challenge.user_id)
    service = AsyncMock()
    service.finalize_login.return_value = MagicMock()
    email_service = MagicMock()
    email_service.consume_recovery_opaque = AsyncMock(
        side_effect=login_api.MfaNotEmailChallenge()
    )
    service.get_email_otp_service = MagicMock(return_value=email_service)
    with (
        patch.object(
            login_api.mfa,
            "consume_challenge",
            AsyncMock(return_value=(challenge, None)),
        ),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.8"),
    ):
        await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(
                method=method,
                challenge_token="a" * 32,
                code="123456",
            ),
            MagicMock(),
            _request(),
            MagicMock(),
            service,
            db,
        )
    service.finalize_login.assert_awaited_once()
    assert service.finalize_login.await_args.kwargs["method"] == method


@pytest.mark.asyncio
async def test_failed_verify_commits_attempt_counter_before_generic_error() -> None:
    db = AsyncMock()
    with (
        patch.object(
            login_api.mfa,
            "consume_challenge",
            AsyncMock(side_effect=HTTPException(400, "invalid code")),
        ),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.8"),
    ):
        with pytest.raises(HTTPException) as exc:
            await login_api.verify_mfa_challenge.__dishka_orig_func__(
                MfaVerifyIn(
                    method="totp",
                    challenge_token="a" * 32,
                    code="000000",
                ),
                MagicMock(),
                _request(),
                MagicMock(),
                AsyncMock(),
                db,
            )
    assert exc.value.detail == "MFA verification failed"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_preserves_challenge_rate_limit_status() -> None:
    db = AsyncMock()
    with (
        patch.object(
            login_api.mfa,
            "consume_challenge",
            AsyncMock(side_effect=HTTPException(429, "rate limited")),
        ),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.8"),
    ):
        with pytest.raises(HTTPException) as exc:
            await login_api.verify_mfa_challenge.__dishka_orig_func__(
                MfaVerifyIn(method="totp", challenge_token="a" * 32, code="000000"),
                MagicMock(),
                _request(),
                MagicMock(),
                AsyncMock(),
                db,
            )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_login_json_normalizes_missing_mfa_keys_to_503() -> None:
    service = AsyncMock()
    service.perform_login.side_effect = login_api.MfaSecurityUnavailable()
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await login_api.login_json.__dishka_orig_func__(
            LoginIn(
                email="student@example.com",
                password="valid-password",  # pragma: allowlist secret
            ),
            MagicMock(),
            _request(),
            MagicMock(),
            service,
            db,
        )
    assert exc.value.status_code == 503
    assert exc.value.detail == "MFA service unavailable"
    db.rollback.assert_awaited_once()
