import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import PasswordResetToken
from app.schemas import schemas
from app.services.auth_service import AuthService


@pytest.fixture
def auth_service():
    audit = MagicMock()
    auth_repo = MagicMock()
    user_repo = MagicMock()
    session_repo = MagicMock()
    uow = MagicMock()
    # Simple mock for async context manager
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.commit = AsyncMock()

    return AuthService(
        audit=audit,
        auth_repo=auth_repo,
        user_repo=user_repo,
        session_repo=session_repo,
        uow=uow,
    )


@pytest.mark.asyncio
async def test_auth_initiate_password_reset_success(auth_service):
    email = "test@example.com"
    request = MagicMock()
    bg = MagicMock()

    auth_service.user_repo.get_by_email = AsyncMock(
        return_value=MagicMock(id=1, email=email)
    )
    auth_service.auth_repo.create_password_reset_token = AsyncMock()

    # Mocking the timing normalization
    with (
        patch("app.services.auth_service.resolve_locale", return_value="en"),
        patch("app.core.ratelimit.enforce_rate_limit", return_value=None),
        patch("app.services.auth_service.send_auth_email.kick", AsyncMock()),
    ):
        await auth_service.initiate_password_reset(email, request, bg)

    auth_service.auth_repo.create_password_reset_token.assert_called_once()
    bg.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_auth_perform_password_reset_success(auth_service):
    token = "valid_token"
    new_password = "new_password_888"  # Length >= 8
    request = MagicMock()

    # Mock token record
    token_rec = MagicMock(spec=PasswordResetToken)
    token_rec.id = 1
    token_rec.user_id = uuid.uuid4()
    token_rec.expires_at = datetime.now(UTC) + timedelta(hours=1)

    auth_service.auth_repo.get_valid_password_reset_token = AsyncMock(
        return_value=token_rec
    )
    auth_service.user_repo.get = AsyncMock(
        return_value=MagicMock(is_active=True, id=token_rec.user_id)
    )
    auth_service.user_repo.update = AsyncMock()
    auth_service.auth_repo.mark_password_reset_token_used = AsyncMock()
    auth_service.auth_repo.invalidate_all_user_password_reset_tokens = AsyncMock()

    with (
        patch("app.services.auth_service.resolve_locale", return_value="en"),
        patch("app.services.auth_service._hash_token", return_value="hash"),
        patch("app.auth.security.validate_password_hibp", return_value=None),
        patch("app.services.auth_service.get_password_hash", return_value="new_hash"),
    ):
        await auth_service.perform_password_reset(token, new_password, request)

    auth_service.user_repo.update.assert_called_once()
    auth_service.auth_repo.mark_password_reset_token_used.assert_called_once()


@pytest.mark.asyncio
async def test_auth_change_password_success(auth_service):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.hashed_password = "old_hash"
    request = MagicMock()
    request.state = MagicMock()
    request.state.active_session = MagicMock(id=uuid.uuid4())

    payload = schemas.UserPasswordChangeIn(
        current_password="old_password_888", new_password="new_password_888"
    )

    auth_service.user_repo.update = AsyncMock()
    auth_service.session_repo.revoke_all_except = AsyncMock(return_value=1)

    with (
        patch("app.services.auth_service.resolve_locale", return_value="en"),
        patch("app.services.auth_service.verify_password", side_effect=[True, False]),
        patch("app.auth.security.validate_password_hibp", return_value=None),
        patch("app.services.auth_service.get_password_hash", return_value="new_hash"),
        patch("app.core.csrf.signal_csrf_rotation", return_value=None),
    ):
        await auth_service.change_password(user, payload, request)

    auth_service.user_repo.update.assert_called_once()
    auth_service.session_repo.revoke_all_except.assert_called_once()
