from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Request

from app.services.auth.credential_validator import CredentialValidator


@pytest.fixture
def mocks():
    lockout_service = AsyncMock()
    lockout_service.get_lockout_message = MagicMock()
    lockout_service.format_duration = MagicMock()
    return {
        "uow": AsyncMock(),
        "user_repo": AsyncMock(),
        "profile_service": AsyncMock(),
        "lockout_service": lockout_service,
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
    mocks["lockout_service"].get_active_lockout.return_value = datetime.now(
        UTC
    ) + timedelta(minutes=5)
    mocks["lockout_service"].get_lockout_message.return_value = ("locked", 300)
    mocks["lockout_service"].format_duration.return_value = "5 minutes"
    mocks["profile_service"].get_auth_user_by_email.return_value = None

    with pytest.raises(HTTPException) as exc:
        await validator.validate_credentials(
            "test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"]
        )

    assert exc.value.status_code == 423
    mocks["audit"].log.assert_called_once()


@pytest.mark.asyncio
async def test_validate_credentials_invalid_user_locks_out_without_alert(
    validator, mocks
):
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = None

    lock_until = datetime.now(UTC) + timedelta(minutes=5)
    mocks["lockout_service"].register_failed_attempt.return_value = (
        lock_until,
        True,
        5,
    )
    mocks["lockout_service"].get_lockout_message.return_value = ("locked", 300)
    mocks["lockout_service"].format_duration.return_value = "5 minutes"

    with patch(
        "app.tasks.email.send_lockout_alert.kick", new_callable=AsyncMock
    ) as mock_kick:
        with pytest.raises(HTTPException) as exc:
            await validator.validate_credentials(
                "test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"]
            )

        assert exc.value.status_code == 423
        mocks["lockout_service"].register_failed_attempt.assert_awaited_once_with(
            "test@example.com", None
        )
        mock_kick.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_credentials_invalid_user_no_lockout(validator, mocks):
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = None
    mocks["lockout_service"].register_failed_attempt.return_value = (None, False, 1)

    mocks["session_manager"].extract_client_info.return_value = ("1.2.3.4", "UA")

    with pytest.raises(HTTPException) as exc:
        await validator.validate_credentials(
            "test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"]
        )

    assert exc.value.status_code == 401
    mocks["bg_tasks"].add_task.assert_called_once()


@pytest.mark.asyncio
@patch(
    "app.services.auth.credential_validator.verify_and_update_password",
    return_value=(False, None),
)
@patch("app.core.localization.resolve_locale", return_value="en")
async def test_validate_credentials_invalid_password_triggers_lockout(
    mock_resolve_locale, mock_verify, validator, mocks
):
    user = MagicMock(id="123", full_name="John Doe", hashed_password="hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user

    lock_until = datetime.now(UTC) + timedelta(minutes=5)
    mocks["lockout_service"].register_failed_attempt.return_value = (
        lock_until,
        True,
        5,
    )
    mocks["lockout_service"].get_lockout_message.return_value = ("locked", 300)
    mocks["lockout_service"].format_duration.return_value = "5 minutes"

    with patch(
        "app.tasks.email.send_lockout_alert.kick", new_callable=AsyncMock
    ) as mock_kick:
        with pytest.raises(HTTPException) as exc:
            await validator.validate_credentials(
                "test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"]
            )

        assert exc.value.status_code == 423
        mock_kick.assert_awaited_once_with("test@example.com", "John Doe", "en")


@pytest.mark.asyncio
@patch(
    "app.services.auth.credential_validator.verify_and_update_password",
    return_value=(False, None),
)
@patch("app.core.localization.resolve_locale", return_value="en")
async def test_validate_credentials_invalid_password_no_lockout(
    mock_resolve_locale, mock_verify, validator, mocks
):
    user = MagicMock(id="123", full_name="John Doe", hashed_password="hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    mocks["lockout_service"].register_failed_attempt.return_value = (None, False, 1)

    mocks["session_manager"].extract_client_info.return_value = ("1.2.3.4", "UA")

    with pytest.raises(HTTPException) as exc:
        await validator.validate_credentials(
            "test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"]
        )

    assert exc.value.status_code == 401
    mocks["bg_tasks"].add_task.assert_called_once()


@pytest.mark.asyncio
@patch(
    "app.services.auth.credential_validator.verify_and_update_password",
    return_value=(True, "new_hash"),
)
async def test_validate_credentials_success_with_new_hash(
    mock_verify, validator, mocks
):
    user = MagicMock(id="123", hashed_password="old_hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    mocks["lockout_service"].clear_failed_attempts.return_value = 1

    res_user = await validator.validate_credentials(
        "test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"]
    )

    assert res_user == user
    mocks["user_repo"].rehash_password_if_current.assert_awaited_once_with(
        "123", expected_hash="old_hash", new_hash="new_hash"
    )
    mocks["uow"].commit.assert_awaited_once()


@pytest.mark.asyncio
@patch(
    "app.services.auth.credential_validator.verify_and_update_password",
    return_value=(True, None),
)
async def test_validate_credentials_success_no_new_hash(mock_verify, validator, mocks):
    user = MagicMock(id="123", hashed_password="hash")
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    mocks["lockout_service"].clear_failed_attempts.return_value = 0

    res_user = await validator.validate_credentials(
        "test@example.com", "pass", mocks["request"], "en", mocks["bg_tasks"]
    )

    assert res_user == user
    mocks["user_repo"].update.assert_not_awaited()
    mocks["uow"].commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_account_dummy_argon2_check_uses_submitted_password(
    validator: CredentialValidator, mocks: dict[str, AsyncMock | MagicMock]
) -> None:
    from uuid import uuid4

    from app.auth import security

    attempted = uuid4().hex
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = None
    mocks["lockout_service"].register_failed_attempt.return_value = (None, False, 1)
    mocks["session_manager"].extract_client_info.return_value = (
        "127.0.0.1",
        "test-agent",
    )

    with (
        patch.object(security, "_dummy_password_hash", None),
        patch.object(
            security,
            "verify_password_sync",
            wraps=security.verify_password_sync,
        ) as verify,
        pytest.raises(HTTPException) as rejected,
    ):
        await validator.validate_credentials(
            "missing@example.invalid",
            attempted,
            mocks["request"],
            "en",
            mocks["bg_tasks"],
        )

    assert rejected.value.status_code == 401
    verify.assert_called_once()
    verification = verify.call_args
    assert verification is not None
    assert verification.args[0] == attempted


@pytest.mark.asyncio
async def test_rehash_compare_and_swap_loser_gets_generic_unauthorized(
    validator: CredentialValidator,
    mocks: dict[str, AsyncMock | MagicMock],
) -> None:
    from uuid import uuid4

    from app.core.localization import translate

    old_hash = uuid4().hex
    new_hash = uuid4().hex
    attempted_password = uuid4().hex
    user = MagicMock(id=uuid4(), hashed_password=old_hash)
    mocks["lockout_service"].get_active_lockout.return_value = None
    mocks["profile_service"].get_auth_user_by_email.return_value = user
    mocks["user_repo"].rehash_password_if_current.return_value = False

    with patch(
        "app.services.auth.credential_validator.verify_and_update_password",
        return_value=(True, new_hash),
    ) as verify_password:
        with pytest.raises(HTTPException) as rejected:
            await validator.validate_credentials(
                "test@example.invalid",
                attempted_password,
                mocks["request"],
                "ru",
                mocks["bg_tasks"],
            )

    assert rejected.value.status_code == 401
    assert rejected.value.detail == translate(
        "errors.auth.credentials_invalid", locale="ru"
    )
    verify_password.assert_awaited_once_with(attempted_password, old_hash)
    mocks["user_repo"].rehash_password_if_current.assert_awaited_once_with(
        user.id, expected_hash=old_hash, new_hash=new_hash
    )
    mocks["uow"].commit.assert_not_awaited()
    mocks["lockout_service"].clear_failed_attempts.assert_not_awaited()
