"""Behavioral Tier0 tests for login-session finalization safeguards."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_finalize_login_updates_plain_user_after_mfa_completion() -> None:
    """MFA completion updates plain ORM-like objects without model_copy()."""
    from app.services.auth.login_session_manager import LoginSessionManager

    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        role=SimpleNamespace(value="student"),
    )
    session = SimpleNamespace(jti=uuid4(), mfa_verified_at=datetime.now(UTC))
    session_service = AsyncMock()
    session_service.create_access_token.return_value = ("token", session)
    redis_session = AsyncMock()
    audit = MagicMock()
    manager = LoginSessionManager(
        session_service=session_service,
        redis_session_service=redis_session,
        geolocation_service=MagicMock(),
        audit=audit,
    )
    manager.extract_client_info = MagicMock(return_value=("127.0.0.1", "pytest"))
    manager.build_token_response = AsyncMock(return_value=MagicMock())
    fingerprint = SimpleNamespace(
        accept_language="en",
        fingerprint_hash="fingerprint",
    )
    csrf_rotation = MagicMock()
    request = MagicMock()
    response = MagicMock()
    bg_tasks = MagicMock()

    with (
        patch(
            "app.services.auth.login_session_manager.extract_fingerprint",
            return_value=fingerprint,
        ),
        patch(
            "app.services.auth.login_session_manager.metrics.record_login_success"
        ) as record_login_success,
        patch.dict(
            sys.modules,
            {"app.core.csrf": SimpleNamespace(signal_csrf_rotation=csrf_rotation)},
        ),
    ):
        await manager.finalize_login(
            user=user,
            request=request,
            response=response,
            bg_tasks=bg_tasks,
            db_session=MagicMock(),
            mfa_completed=True,
            method="totp",
        )

    assert isinstance(user.mfa_last_verified_at, datetime)
    metadata = session_service.create_access_token.await_args.kwargs["metadata"]
    assert metadata["mfa_method"] == "totp"
    assert metadata["mfa_completed_at"] == user.mfa_last_verified_at
    csrf_rotation.assert_called_once_with(request)
    redis_session.create_session.assert_awaited_once()
    record_login_success.assert_called_once_with(method="totp")


def test_set_access_token_cookie_uses_safe_ttl_fallback(monkeypatch) -> None:
    """Malformed TTL configuration must fall back to a one-hour cookie."""
    from app.core.config import settings
    from app.services.auth.login_session_manager import LoginSessionManager

    manager = LoginSessionManager(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    response = MagicMock()
    monkeypatch.setattr(
        settings.security, "access_token_expire_minutes", "not-an-integer"
    )

    manager._set_access_token_cookie(response, "token")

    assert response.set_cookie.call_args.kwargs["max_age"] == 3600
