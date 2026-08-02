"""Behavioral coverage for authentication route boundaries without app bootstrap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.api.auth import login as login_api
from app.auth.schemas import (
    LoginIn,
    LoginPasskeyStartIn,
    MfaMethodChallengeOut,
    MfaVerifyIn,
    PendingMfaResponse,
)


def _original(name: str):
    return getattr(login_api, name).__dishka_orig_func__


def _pending_response() -> PendingMfaResponse:
    return PendingMfaResponse(
        user_id=uuid4(),
        methods=[
            MfaMethodChallengeOut(
                method="totp",
                challenge_token="t" * 32,
                challenge_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        ],
    )


@pytest.mark.asyncio
async def test_login_passkey_start_uses_dummy_challenge_for_unknown_user():
    profile_service = MagicMock()
    profile_service.get_user_by_email = AsyncMock(return_value=None)
    db = AsyncMock()
    webauthn = MagicMock()
    webauthn.get_dummy_authentication_options.return_value = {"challenge": "dummy"}

    with (
        patch.object(login_api, "WebAuthnService", return_value=webauthn),
        patch(
            "app.auth.mfa.challenge.issue_dummy_challenge", AsyncMock()
        ) as issue_dummy,
        patch.object(login_api, "ensure_minimum_time", AsyncMock()),
        patch.object(login_api.secrets, "token_urlsafe", return_value="dummy-token"),
    ):
        result = await _original("login_passkey_start")(
            LoginPasskeyStartIn(email=" User@Example.com "),
            MagicMock(),
            profile_service,
            db,
            MagicMock(),
        )

    profile_service.get_user_by_email.assert_awaited_once_with("user@example.com")
    issue_dummy.assert_awaited_once_with(db)
    assert result.challenge_token == "dummy-token"
    assert result.publicKey == {"challenge": "dummy"}


@pytest.mark.asyncio
async def test_login_passkey_start_issues_real_challenge_for_active_user():
    user = SimpleNamespace(id=uuid4(), is_active=True)
    profile_service = MagicMock()
    profile_service.get_user_by_email = AsyncMock(return_value=user)
    db = AsyncMock()
    challenge = SimpleNamespace(id=uuid4(), token="real-token")
    webauthn = MagicMock()
    webauthn.get_authentication_options = AsyncMock(return_value={"challenge": "real"})
    audit = MagicMock()
    issue_challenge = AsyncMock(return_value=challenge)

    with (
        patch.object(login_api, "WebAuthnService", return_value=webauthn),
        patch.object(login_api.mfa, "issue_challenge", issue_challenge),
        patch.object(login_api, "ensure_minimum_time", AsyncMock()),
    ):
        result = await _original("login_passkey_start")(
            LoginPasskeyStartIn(email="student@example.com"),
            MagicMock(),
            profile_service,
            db,
            audit,
        )

    db.commit.assert_awaited_once()
    audit.log.assert_called_once()
    assert result.challenge_token == "real-token"
    assert result.publicKey == {"challenge": "real"}


@pytest.mark.asyncio
async def test_login_passkey_verify_maps_invalid_challenge_to_bad_request():
    with patch.object(
        login_api.mfa,
        "get_challenge",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="expired")),
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("login_passkey_verify")(
                SimpleNamespace(challenge_token="x", webauthn_response={}),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                AsyncMock(),
            )

    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    assert caught.value.detail == "Invalid challenge"


@pytest.mark.asyncio
async def test_login_passkey_verify_rejects_invalid_payload_and_inactive_user():
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=uuid4(), is_active=False)
    challenge = SimpleNamespace(user_id=uuid4(), payload=None)

    with patch.object(
        login_api.mfa, "get_challenge", AsyncMock(return_value=challenge)
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("login_passkey_verify")(
                SimpleNamespace(challenge_token="x", webauthn_response={}),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                db,
            )
    assert caught.value.status_code == status.HTTP_401_UNAUTHORIZED

    db.get.return_value = SimpleNamespace(id=uuid4(), is_active=True)
    with patch.object(
        login_api.mfa, "get_challenge", AsyncMock(return_value=challenge)
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("login_passkey_verify")(
                SimpleNamespace(challenge_token="x", webauthn_response={}),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                db,
            )
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    assert caught.value.detail == "Invalid challenge payload"


@pytest.mark.asyncio
async def test_login_passkey_verify_converts_webauthn_failure_and_finalizes_success():
    user = SimpleNamespace(id=uuid4(), is_active=True)
    challenge = SimpleNamespace(
        user_id=user.id,
        payload={"options": {"challenge": "challenge-value"}},
    )
    db = AsyncMock()
    db.get.return_value = user
    webauthn = MagicMock()
    webauthn.verify_authentication = AsyncMock(side_effect=RuntimeError("bad proof"))
    login_service = MagicMock()
    get_challenge = AsyncMock(return_value=challenge)

    with (
        patch.object(login_api.mfa, "get_challenge", get_challenge),
        patch.object(login_api, "WebAuthnService", return_value=webauthn),
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("login_passkey_verify")(
                SimpleNamespace(challenge_token="x", webauthn_response={"id": "x"}),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                login_service,
                db,
            )
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST

    webauthn.verify_authentication = AsyncMock()
    login_service.finalize_login = AsyncMock(return_value="token-result")
    with (
        patch.object(login_api.mfa, "get_challenge", get_challenge),
        patch.object(login_api, "WebAuthnService", return_value=webauthn),
    ):
        result = await _original("login_passkey_verify")(
            SimpleNamespace(challenge_token="x", webauthn_response={"id": "x"}),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            login_service,
            db,
        )
    assert result == "token-result"
    login_service.finalize_login.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_and_json_store_fingerprint_only_for_pending_mfa():
    pending = _pending_response()
    login_service = MagicMock()
    login_service.perform_login = AsyncMock(
        side_effect=[pending, "login-token", "token-result", pending]
    )
    store = AsyncMock()

    with patch.object(login_api, "store_mfa_challenge_fingerprints", store):
        result_pending = await _original("login")(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            login_service,
            True,
            SimpleNamespace(  # pragma: allowlist secret
                username="student@example.com",
                password="password",  # pragma: allowlist secret
            ),
        )
        result_login_token = await _original("login")(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            login_service,
            False,
            SimpleNamespace(  # pragma: allowlist secret
                username="student@example.com",
                password="password",  # pragma: allowlist secret
            ),
        )
        result_token = await _original("login_json")(
            LoginIn(  # pragma: allowlist secret
                email="student@example.com",
                password="password",  # pragma: allowlist secret
            ),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            login_service,
        )
        result_json_pending = await _original("login_json")(
            LoginIn(  # pragma: allowlist secret
                email="student@example.com",
                password="password",  # pragma: allowlist secret
            ),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            login_service,
        )

    assert result_pending is pending
    assert result_login_token == "login-token"
    assert result_token == "token-result"
    assert result_json_pending is pending
    assert store.await_count == 2


@pytest.mark.asyncio
async def test_verify_mfa_challenge_covers_methods_and_failure_guards():
    user = SimpleNamespace(id=uuid4())
    challenge = SimpleNamespace(user_id=user.id, challenge_type="totp")
    db = AsyncMock()
    db.get.return_value = user
    login_service = MagicMock()
    login_service.finalize_login = AsyncMock(return_value="finalized")

    for method in ("totp", "webauthn", "recovery_code"):
        payload = MfaVerifyIn(
            method=method,
            challenge_token="c" * 32,
            code="123456",
        )
        with (
            patch.object(
                login_api, "verify_mfa_fingerprint", AsyncMock(return_value=True)
            ),
            patch.object(
                login_api.mfa,
                "consume_challenge",
                AsyncMock(return_value=(challenge, None)),
            ),
        ):
            assert (
                await _original("verify_mfa_challenge")(
                    payload,
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                    login_service,
                    db,
                )
                == "finalized"
            )

    with patch.object(
        login_api, "verify_mfa_fingerprint", AsyncMock(return_value=True)
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("verify_mfa_challenge")(
                SimpleNamespace(method="invalid", challenge_token="c" * 32),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                login_service,
                db,
            )
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST

    with patch.object(
        login_api, "verify_mfa_fingerprint", AsyncMock(return_value=False)
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("verify_mfa_challenge")(
                SimpleNamespace(method="totp", challenge_token="c" * 32),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                login_service,
                db,
            )
    assert caught.value.status_code == status.HTTP_403_FORBIDDEN

    db.get.return_value = None
    with (
        patch.object(login_api, "verify_mfa_fingerprint", AsyncMock(return_value=True)),
        patch.object(
            login_api.mfa,
            "consume_challenge",
            AsyncMock(return_value=(challenge, None)),
        ),
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("verify_mfa_challenge")(
                MfaVerifyIn(method="totp", challenge_token="c" * 32, code="123456"),
                MagicMock(),
                MagicMock(),
                MagicMock(),
                login_service,
                db,
            )
    assert caught.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_csrf_cookie_and_signing_key_routes():
    assert await login_api.get_csrf_cookie() == {"detail": "CSRF cookie set"}

    request = SimpleNamespace(state=SimpleNamespace(active_session=None))
    with pytest.raises(HTTPException) as caught:
        await login_api.get_session_signing_key(request, MagicMock())
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST

    request.state.active_session = SimpleNamespace(signing_key="key-1")
    result = await login_api.get_session_signing_key(request, MagicMock())
    assert result.signing_key == "key-1"


@pytest.mark.asyncio
async def test_register_returns_success_and_maps_service_errors():
    user = SimpleNamespace(id=uuid4())
    compliance = MagicMock()
    compliance.register_user = AsyncMock(return_value=user)
    db = AsyncMock()
    request = MagicMock()

    result = await _original("register")(
        SimpleNamespace(email="student@example.com"),
        request,
        compliance,
        MagicMock(),
        db,
    )
    assert result == {"status": "ok", "id": user.id}

    compliance.register_user = AsyncMock(side_effect=ValueError("duplicate"))
    with pytest.raises(HTTPException) as caught:
        await _original("register")(
            SimpleNamespace(email="student@example.com"),
            request,
            compliance,
            MagicMock(),
            db,
        )
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    db.rollback.assert_awaited()

    compliance.register_user = AsyncMock(side_effect=RuntimeError("backend"))
    with (
        patch.object(login_api, "resolve_locale", return_value="en"),
        patch.object(login_api, "translate", return_value="create failed"),
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("register")(
                SimpleNamespace(email="student@example.com"),
                request,
                compliance,
                MagicMock(),
                db,
            )
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
