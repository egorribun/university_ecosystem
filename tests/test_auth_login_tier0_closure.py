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
    MfaMethodChallengeOut,
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
async def test_login_and_json_commit_only_for_pending_mfa():
    pending = _pending_response()
    login_service = MagicMock()
    login_service.perform_login = AsyncMock(
        side_effect=[pending, "login-token", "token-result", pending]
    )
    db = MagicMock()
    db.commit = AsyncMock()

    result_pending = await _original("login")(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        login_service,
        db,
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
        db,
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
        db,
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
        db,
    )

    assert result_pending is pending
    assert result_login_token == "login-token"
    assert result_token == "token-result"
    assert result_json_pending is pending
    assert db.commit.await_count == 2


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
