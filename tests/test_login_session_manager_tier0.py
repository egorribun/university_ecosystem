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


@pytest.mark.asyncio
async def test_finalize_login_uses_model_copy_and_supports_password_login() -> None:
    from app.services.auth.login_session_manager import LoginSessionManager

    session_service = AsyncMock()
    session_service.create_access_token.return_value = (
        "token",
        SimpleNamespace(jti=uuid4(), mfa_verified_at=None),
    )
    redis_session = AsyncMock()
    audit = MagicMock()
    manager = LoginSessionManager(session_service, redis_session, MagicMock(), audit)
    manager.extract_client_info = MagicMock(return_value=("127.0.0.1", "pytest"))
    manager.build_token_response = AsyncMock(return_value=MagicMock())
    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        role=SimpleNamespace(value="student"),
    )
    user.model_copy = MagicMock(return_value=user)

    with (
        patch(
            "app.services.auth.login_session_manager.extract_fingerprint",
            return_value=SimpleNamespace(
                accept_language="en", fingerprint_hash="fingerprint"
            ),
        ),
        patch("app.services.auth.login_session_manager.metrics.record_login_success"),
        patch.dict(
            sys.modules,
            {"app.core.csrf": SimpleNamespace(signal_csrf_rotation=MagicMock())},
        ),
    ):
        await manager.finalize_login(
            user=user,
            request=MagicMock(),
            response=MagicMock(),
            bg_tasks=MagicMock(),
            db_session=MagicMock(),
            mfa_completed=True,
            method="webauthn",
        )

    user.model_copy.assert_called_once()
    metadata = session_service.create_access_token.await_args.kwargs["metadata"]
    assert metadata["mfa_method"] == "webauthn"

    session_service.create_access_token.reset_mock()
    user.model_copy.reset_mock()
    with (
        patch(
            "app.services.auth.login_session_manager.extract_fingerprint",
            return_value=SimpleNamespace(
                accept_language="en", fingerprint_hash="fingerprint"
            ),
        ),
        patch("app.services.auth.login_session_manager.metrics.record_login_success"),
        patch.dict(
            sys.modules,
            {"app.core.csrf": SimpleNamespace(signal_csrf_rotation=MagicMock())},
        ),
    ):
        await manager.finalize_login(
            user=user,
            request=MagicMock(),
            response=MagicMock(),
            bg_tasks=MagicMock(),
            db_session=MagicMock(),
            mfa_completed=False,
            method="password",
        )

    user.model_copy.assert_not_called()
    metadata = session_service.create_access_token.await_args.kwargs["metadata"]
    assert metadata["mfa_method"] is None
    assert "mfa_completed_at" not in metadata


@pytest.mark.asyncio
async def test_build_token_response_handles_pending_email_and_signing_key() -> None:
    from app.models.enums import UserRole
    from app.schemas.dtos import UserDTO
    from app.services.auth.login_session_manager import LoginSessionManager

    user = UserDTO(
        id=uuid4(),
        email="student@example.com",
        role=UserRole.STUDENT,
        group_id=None,
        is_active=True,
        mfa_required=False,
        mfa_default_method=None,
        mfa_last_verified_at=None,
        created_at=None,
    )
    pending_user = user.model_copy(update={"pending_email": "new@example.com"})
    manager = LoginSessionManager(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    session = SimpleNamespace(signing_key="key-1")

    with (
        patch(
            "app.services.auth.login_session_manager.ensure_mfa_relationships_loaded",
            AsyncMock(side_effect=[user, user]),
        ),
        patch(
            "app.services.auth_service.attach_pending_email",
            AsyncMock(side_effect=[pending_user, None]),
        ),
    ):
        with_pending = await manager.build_token_response(
            user, "token", session, MagicMock(), include_token=False
        )
        without_pending = await manager.build_token_response(
            user, "token", None, MagicMock(), include_token=True
        )

    assert with_pending.access_token is None
    assert with_pending.user.pending_email == "new@example.com"
    assert with_pending.session.signing_key == "key-1"
    assert without_pending.access_token == "token"
    assert without_pending.session is None


def test_extract_client_info_resolves_ip_and_user_agent() -> None:
    from app.services.auth.login_session_manager import LoginSessionManager

    manager = LoginSessionManager(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    request = MagicMock()
    request.headers.get.return_value = "pytest-agent"

    with patch("app.core.ratelimit.resolve_client_ip", return_value="192.0.2.10"):
        assert manager.extract_client_info(request) == (
            "192.0.2.10",
            "pytest-agent",
        )


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


@pytest.mark.asyncio
async def test_record_login_history_bg_persists_bounded_metadata() -> None:
    from app.services.auth.login_session_manager import LoginSessionManager

    db = MagicMock()
    db.commit = AsyncMock()
    db_context = MagicMock()
    db_context.__aenter__ = AsyncMock(return_value=db)
    db_context.__aexit__ = AsyncMock(return_value=None)
    location = SimpleNamespace(
        country="RU", city="Moscow", latitude=55.75, longitude=37.62
    )
    repository = MagicMock()
    repository.record_login_history = AsyncMock()
    user_id = uuid4()
    manager = LoginSessionManager(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    with (
        patch(
            "app.services.auth.login_session_manager.async_session",
            MagicMock(return_value=db_context),
        ),
        patch("asyncio.to_thread", AsyncMock(return_value=location)),
        patch(
            "app.repositories.auth_repository.AuthRepository",
            MagicMock(return_value=repository),
        ) as repository_cls,
    ):
        await manager.record_login_history_bg(
            user_id,
            "127.0.0.1",
            "u" * 600,
            "success",
            is_suspicious=True,
        )

    repository_cls.assert_called_once_with(db)
    repository.record_login_history.assert_awaited_once_with(
        user_id=user_id,
        ip_address="127.0.0.1",
        user_agent="u" * 512,
        country="RU",
        city="Moscow",
        latitude=55.75,
        longitude=37.62,
        status="success",
        is_suspicious=True,
    )
    db.commit.assert_awaited_once()
