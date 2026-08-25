"""Behavioral Tier0 tests for login route boundary branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException


def _request_with_services(
    *,
    login_service: object | None = None,
    profile_service: object | None = None,
    compliance_service: object | None = None,
    audit: object | None = None,
    db: object | None = None,
) -> MagicMock:
    request = MagicMock()
    login_service = login_service or AsyncMock()
    profile_service = profile_service or AsyncMock()
    compliance_service = compliance_service or AsyncMock()
    audit = audit or MagicMock()
    db = db or AsyncMock()

    async def resolve(dep, *args, **kwargs):
        dependency = str(dep)
        if "LoginService" in dependency:
            return login_service
        if "UserProfileService" in dependency:
            return profile_service
        if "UserComplianceService" in dependency:
            return compliance_service
        if "AuditService" in dependency:
            return audit
        return db

    request.state.dishka_container.get = AsyncMock(side_effect=resolve)
    return request


@pytest.mark.asyncio
async def test_login_form_delegates_to_login_service() -> None:
    from app.api.auth.login import login

    login_service = AsyncMock()
    login_service.perform_login.return_value = MagicMock()
    request = _request_with_services(login_service=login_service)
    form_data = MagicMock(username="user@example.com", password="Password1!")

    result = await login(
        response=MagicMock(),
        request=request,
        bg_tasks=MagicMock(),
        trust_device=True,
        form_data=form_data,
    )

    assert result is login_service.perform_login.return_value
    login_service.perform_login.assert_awaited_once()
    assert login_service.perform_login.await_args.kwargs["email"] == "user@example.com"
    assert login_service.perform_login.await_args.kwargs["trust_device"] is True


@pytest.mark.asyncio
async def test_login_form_commits_opaque_pending_mfa_challenge() -> None:
    from app.api.auth.login import login
    from app.auth.schemas import MfaMethodChallengeOut, PendingMfaResponse

    method = MfaMethodChallengeOut(
        method="totp",
        challenge_token="a" * 32,
        challenge_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    pending = PendingMfaResponse(
        user_id=uuid4(),
        session_id=uuid4(),
        default_method="totp",
        methods=[method],
    )
    login_service = AsyncMock()
    login_service.perform_login.return_value = pending
    request = _request_with_services(login_service=login_service)
    form_data = MagicMock(username="user@example.com", password="Password1!")

    result = await login(
        response=MagicMock(),
        request=request,
        bg_tasks=MagicMock(),
        trust_device=False,
        form_data=form_data,
    )

    assert result is pending
    db = await request.state.dishka_container.get("database")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_json_returns_completed_login_without_pending_commit() -> None:
    from app.api.auth.login import login_json

    login_service = AsyncMock()
    result = MagicMock()
    login_service.perform_login.return_value = result
    request = _request_with_services(login_service=login_service)
    payload = MagicMock(
        email="user@example.com", password="Password1!", trust_device=False
    )

    assert (
        await login_json(
            payload=payload,
            response=MagicMock(),
            request=request,
            bg_tasks=MagicMock(),
        )
        is result
    )

    db = await request.state.dishka_container.get("database")
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_mfa_challenge_genericizes_binding_mismatch() -> None:
    from app.api.auth.login import verify_mfa_challenge

    request = _request_with_services()
    payload = MagicMock(method="totp", challenge_token="a" * 32, code="123456")

    with patch(
        "app.api.auth.login.mfa.consume_challenge",
        new_callable=AsyncMock,
        side_effect=HTTPException(400, "binding mismatch"),
    ) as consume_challenge:
        with pytest.raises(HTTPException) as exc:
            await verify_mfa_challenge(
                payload=payload,
                response=MagicMock(),
                request=request,
                bg_tasks=MagicMock(),
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "MFA verification failed"
    consume_challenge.assert_awaited_once()


@pytest.mark.asyncio
async def test_csrf_cookie_endpoint_returns_initialization_response() -> None:
    from app.api.auth.login import get_csrf_cookie

    assert await get_csrf_cookie() == {"detail": "CSRF cookie set"}


@pytest.mark.asyncio
async def test_register_returns_created_user_id() -> None:
    from app.api.auth.login import register

    new_user = SimpleNamespace(id=uuid4())
    compliance_service = AsyncMock()
    compliance_service.register_user.return_value = new_user
    request = _request_with_services(compliance_service=compliance_service)

    with patch("app.api.auth.login.resolve_locale", return_value="en"):
        result = await register(user=MagicMock(), request=request)

    assert result == {"status": "ok", "id": new_user.id}
    compliance_service.register_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_signing_key_requires_active_session() -> None:
    from app.api.auth.login import get_session_signing_key

    request = MagicMock()
    request.state.active_session = None

    with patch("app.api.auth.login.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await get_session_signing_key(request, MagicMock())

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_session_signing_key_returns_active_key() -> None:
    from app.api.auth.login import get_session_signing_key

    request = MagicMock()
    request.state.active_session = SimpleNamespace(signing_key="session-key")

    result = await get_session_signing_key(request, MagicMock())

    assert result.signing_key == "session-key"
