import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import PasswordResetToken
from app.schemas import schemas
from app.services.auth_service import AuthService


@pytest.fixture
def auth_service():
    audit = MagicMock()
    auth_repo = MagicMock()
    user_repo = MagicMock()
    user_repo.change_password_if_current = AsyncMock(return_value=1)
    session_repo = MagicMock()
    session_repo.update = AsyncMock()
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
        # change_password uses the service's imported validator directly;
        # patch that exact binding so the unit test never reaches HIBP.
        patch("app.services.auth_service.validate_password_hibp", return_value=None),
        patch("app.services.auth_service.get_password_hash", return_value="new_hash"),
        patch("app.core.csrf.signal_csrf_rotation", return_value=None),
    ):
        await auth_service.change_password(user, payload, request)

    auth_service.user_repo.change_password_if_current.assert_awaited_once_with(
        user.id, expected_hash="old_hash", new_hash="new_hash"
    )
    auth_service.session_repo.revoke_all_except.assert_called_once()


@pytest.mark.asyncio
async def test_password_change_losing_compare_and_swap_preserves_winner_and_sessions(
    db_session, test_user, mock_global_redis
):
    from fastapi import HTTPException, Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.security import get_password_hash
    from app.models import ActiveSession
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.unit_of_work import uow_from_session
    from app.repositories.user_repository import UserRepository

    user_id = test_user.id
    original_hash = test_user.hashed_password
    original_epoch = test_user.mfa_epoch
    current = ActiveSession(
        user_id=user_id,
        jti="password-cas-current",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=original_epoch,
    )
    sibling = ActiveSession(
        user_id=user_id,
        jti="password-cas-sibling",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=original_epoch,
    )
    db_session.add_all([current, sibling])
    await db_session.commit()
    uow = uow_from_session(db_session)
    service = AuthService(
        audit=MagicMock(),
        auth_repo=AuthRepository(db_session),
        user_repo=UserRepository(db_session),
        session_repo=uow.sessions,
        uow=uow,
    )
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "POST",
        }
    )
    request.state.active_session = current
    payload = schemas.UserPasswordChangeIn(
        current_password="old_password_888",
        new_password=f"ChangeA1!{uuid.uuid4().hex}",
    )
    winning_hash = await get_password_hash(f"WinnerA1!{uuid.uuid4().hex}")
    losing_hash = await get_password_hash(payload.new_password)

    async def hash_after_competing_change(*args, **kwargs):
        # Another request commits while this request is hashing its new password.
        async with AsyncSession(bind=db_session.bind) as competing:
            epoch = await UserRepository(competing).change_password_if_current(
                user_id, expected_hash=original_hash, new_hash=winning_hash
            )
            assert epoch == original_epoch + 1
            await competing.commit()
        return losing_hash

    with (
        patch("app.services.auth_service.verify_password", side_effect=[True, False]),
        patch("app.services.auth_service.validate_password_hibp", AsyncMock()),
        patch(
            "app.services.auth_service.get_password_hash",
            AsyncMock(side_effect=hash_after_competing_change),
        ),
        pytest.raises(HTTPException) as denied,
    ):
        await service.change_password(test_user, payload, request)

    assert denied.value.status_code == 401
    await db_session.refresh(test_user)
    await db_session.refresh(current)
    await db_session.refresh(sibling)
    assert test_user.hashed_password == winning_hash
    assert test_user.mfa_epoch == original_epoch + 1
    assert current.mfa_epoch == original_epoch
    assert sibling.mfa_epoch == original_epoch
    assert current.revoked_at is None
    assert sibling.revoked_at is None
    assert await mock_global_redis.exists("revoked:jti:password-cas-sibling") == 0
    assert not getattr(request.state, "rotate_csrf", False)
