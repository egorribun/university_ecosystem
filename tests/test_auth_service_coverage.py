from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Request

import app.models as models
from app.schemas import schemas
from app.services.auth_service import AuthService


@pytest.fixture
def auth_service():
    audit = MagicMock()
    auth_repo = MagicMock()
    user_repo = MagicMock()
    session_repo = MagicMock()
    uow = MagicMock()
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


@pytest.fixture
def request_mock():
    req = MagicMock(spec=Request)
    req.state = MagicMock()
    req.headers = {"accept-language": "en"}
    return req


@pytest.mark.asyncio
async def test_initiate_password_reset_user_not_found(auth_service, request_mock):
    bg = MagicMock(spec=BackgroundTasks)
    auth_service.user_repo.get_by_email = AsyncMock(return_value=None)

    # Use patch to mock enforce_rate_limit to avoid Redis/Temporal dependencies
    with patch("app.core.ratelimit.enforce_rate_limit", AsyncMock()):
        await auth_service.initiate_password_reset(
            "nonexistent@example.com", request_mock, bg
        )

    auth_service.audit.log.assert_called_with(
        "password.reset.initiated",
        request_mock,
        level=10 + 20,  # logging.WARNING is 30
        reason="user_not_found",
    )


@pytest.mark.asyncio
async def test_perform_password_reset_expired_token(auth_service, request_mock):
    token = "some-token"
    rec = MagicMock()
    rec.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    rec.user_id = 1
    auth_service.auth_repo.get_valid_password_reset_token = AsyncMock(return_value=rec)

    with pytest.raises(HTTPException) as exc:
        await auth_service.perform_password_reset(
            token, "new-password-8-chars", request_mock
        )

    assert exc.value.status_code == 400
    auth_service.audit.log.assert_called_with(
        "password.reset.failed",
        request_mock,
        level=30,
        user_id=1,
        reason="token_expired",
    )


@pytest.mark.asyncio
async def test_perform_password_reset_inactive_user(auth_service, request_mock):
    token = "some-token"
    rec = MagicMock()
    rec.expires_at = datetime.now(UTC) + timedelta(minutes=10)
    rec.user_id = 1
    auth_service.auth_repo.get_valid_password_reset_token = AsyncMock(return_value=rec)

    user = MagicMock(spec=models.User)
    user.is_active = False
    auth_service.user_repo.get = AsyncMock(return_value=user)

    with pytest.raises(HTTPException) as exc:
        await auth_service.perform_password_reset(
            token, "new-password-8-chars", request_mock
        )

    assert exc.value.status_code == 400
    auth_service.audit.log.assert_called_with(
        "password.reset.failed",
        request_mock,
        level=30,
        user_id=1,
        reason="user_inactive",
    )


@pytest.mark.asyncio
async def test_initiate_email_change_email_in_use(auth_service, request_mock):
    user = MagicMock(spec=models.User)
    user.id = 1
    user.email = "old@example.com"
    user.hashed_password = "hashed_password"

    payload = schemas.UserEmailChangeIn(
        email="taken@example.com", password="correct_password"
    )

    with patch("app.auth.security.verify_password", AsyncMock(return_value=True)):
        auth_service.user_repo.check_email_exists = AsyncMock(return_value=True)

        with pytest.raises(HTTPException) as exc:
            await auth_service.initiate_email_change(
                user, payload, request_mock, MagicMock()
            )

        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_email_change_expired_token(auth_service, request_mock):
    user = MagicMock(spec=models.User)
    user.id = 1

    record = MagicMock()
    record.user_id = 1
    record.used = False
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)

    auth_service.auth_repo.get_valid_email_change_token = AsyncMock(return_value=record)

    with pytest.raises(HTTPException) as exc:
        await auth_service.confirm_email_change(user, "token", request_mock)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_email_change_conflict(auth_service, request_mock):
    user = MagicMock(spec=models.User)
    user.id = 1

    record = MagicMock()
    record.id = 100
    record.user_id = 1
    record.used = False
    record.new_email = "conflict@example.com"
    record.expires_at = datetime.now(UTC) + timedelta(minutes=10)

    auth_service.auth_repo.get_valid_email_change_token = AsyncMock(return_value=record)
    auth_service.user_repo.check_email_exists = AsyncMock(return_value=True)
    auth_service.auth_repo.mark_email_change_token_used = AsyncMock()
    auth_service.auth_repo.invalidate_other_email_change_tokens = AsyncMock()

    # Mock attach_pending_email to avoid DB calls
    with patch("app.services.auth_service.attach_pending_email", AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await auth_service.confirm_email_change(user, "token", request_mock)

        assert exc.value.status_code == 400

    auth_service.auth_repo.mark_email_change_token_used.assert_called_with(100)


@pytest.mark.asyncio
async def test_refresh_pending_email_none_user(auth_service):
    res = await auth_service.refresh_pending_email(None)
    assert res is None
