import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, UTC, timedelta
from fastapi import Request, BackgroundTasks, HTTPException

from app.services.auth.credential_validator import CredentialValidator


@pytest.fixture
def mocks():
    return {
        "uow": AsyncMock(),
        "user_repo": AsyncMock(),
        "profile_service": AsyncMock(),
        "lockout_service": AsyncMock(),
        "audit": MagicMock(),
        "session_manager": MagicMock(),
        "request": AsyncMock(spec=Request),
        "bg_tasks": MagicMock(spec=BackgroundTasks),
    }


@pytest.fixture
def validator(mocks):
    return CredentialValidator(
        uow=mocks["uow"],
        user_repo=mocks["user_repo"],
        profile_service=mocks["profile_service"],
        lockout_service=mocks["lockout_service"],
        audit=mocks["audit"],
        session_manager=mocks["session_manager"],
    )


@pytest.mark.asyncio
async def test_validate_credentials_active_lockout(validator, mocks):
    mocks["lockout_service"].get_active_lockout.return_value = datetime.now(UTC) + timedelta(minutes=5)
    mocks["lockout_service"].get_lockout_message.return_value = ("locked", 300)
    mocks["lockout_service"].format_duration.return_value = "5 minutes"
    mocks["profile_service"].get_auth_user_by_email.return_value = None

    with pytest.raises(HTTPException) as exc:
        await validator.validate_credentials("test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"])
    
    assert exc.value.status_code == 423
    mocks["audit"].log.assert_called_once()


@pytest.mark.asyncio
async def test_validate_credentials_invalid_user_triggers_lockout(validator, mocks):
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = None
    
    lock_until = datetime.now(UTC) + timedelta(minutes=5)
    mocks["lockout_service"].register_failed_attempt.return_value = (lock_until, True, 5)
    mocks["lockout_service"].get_lockout_message.return_value = ("locked", 300)
    mocks["lockout_service"].format_duration.return_value = "5 minutes"

    with patch("app.services.auth.credential_validator.send_lockout_alert.kick", new_callable=AsyncMock) as mock_kick:
        with pytest.raises(HTTPException) as exc:
            await validator.validate_credentials("test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"])
        
        assert exc.value.status_code == 423
        mock_kick.assert_awaited_once_with("test@example.com", "", "en")


@pytest.mark.asyncio
async def test_validate_credentials_invalid_user_no_lockout(validator, mocks):
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = None
    mocks["lockout_service"].register_failed_attempt.return_value = (None, False, 1)
    
    mocks["session_manager"].extract_client_info.return_value = ("1.2.3.4", "UA")

    with pytest.raises(HTTPException) as exc:
        await validator.validate_credentials("test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"])
    
    assert exc.value.status_code == 401
    mocks["bg_tasks"].add_task.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.auth.credential_validator.verify_and_update_password", return_value=(False, None))
@patch("app.core.localization.resolve_locale", return_value="en")
async def test_validate_credentials_invalid_password_triggers_lockout(mock_resolve_locale, mock_verify, validator, mocks):
    user = MagicMock(id="123", full_name="John Doe", hashed_password="hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    
    lock_until = datetime.now(UTC) + timedelta(minutes=5)
    mocks["lockout_service"].register_failed_attempt.return_value = (lock_until, True, 5)
    mocks["lockout_service"].get_lockout_message.return_value = ("locked", 300)
    mocks["lockout_service"].format_duration.return_value = "5 minutes"

    with patch("app.services.auth.credential_validator.send_lockout_alert.kick", new_callable=AsyncMock) as mock_kick:
        with pytest.raises(HTTPException) as exc:
            await validator.validate_credentials("test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"])
        
        assert exc.value.status_code == 423
        mock_kick.assert_awaited_once_with("test@example.com", "John Doe", lock_until, 5, "en")


@pytest.mark.asyncio
@patch("app.services.auth.credential_validator.verify_and_update_password", return_value=(False, None))
@patch("app.core.localization.resolve_locale", return_value="en")
async def test_validate_credentials_invalid_password_no_lockout(mock_resolve_locale, mock_verify, validator, mocks):
    user = MagicMock(id="123", full_name="John Doe", hashed_password="hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    mocks["lockout_service"].register_failed_attempt.return_value = (None, False, 1)
    
    mocks["session_manager"].extract_client_info.return_value = ("1.2.3.4", "UA")

    with pytest.raises(HTTPException) as exc:
        await validator.validate_credentials("test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"])
    
    assert exc.value.status_code == 401
    mocks["bg_tasks"].add_task.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.auth.credential_validator.verify_and_update_password", return_value=(True, "new_hash"))
async def test_validate_credentials_success_with_new_hash(mock_verify, validator, mocks):
    user = MagicMock(id="123", hashed_password="old_hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    mocks["lockout_service"].clear_failed_attempts.return_value = 1

    res_user = await validator.validate_credentials("test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"])
    
    assert res_user == user
    mocks["user_repo"].update.assert_awaited_once_with("123", {"hashed_password": "new_hash"})
    mocks["uow"].commit.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.auth.credential_validator.verify_and_update_password", return_value=(True, None))
async def test_validate_credentials_success_no_new_hash(mock_verify, validator, mocks):
    user = MagicMock(id="123", hashed_password="hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    mocks["lockout_service"].clear_failed_attempts.return_value = 0

    res_user = await validator.validate_credentials("test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"])
    
    assert res_user == user
    mocks["user_repo"].update.assert_not_awaited()
    mocks["uow"].commit.assert_not_awaited()
