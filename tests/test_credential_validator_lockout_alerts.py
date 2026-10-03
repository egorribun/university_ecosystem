from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Request, status

from app.services.auth.credential_validator import CredentialValidator


def _validator(*, triggered: bool) -> CredentialValidator:
    lock_until = datetime.now(UTC) + timedelta(minutes=10)
    lockout_service = MagicMock()
    lockout_service.register_failed_attempt = AsyncMock(
        return_value=(lock_until, triggered, 5)
    )
    lockout_service.format_duration.return_value = "10 minutes"
    lockout_service.get_lockout_message.return_value = ("Account locked", 600)
    return CredentialValidator(
        uow=MagicMock(),
        user_repo=MagicMock(),
        profile_service=MagicMock(),
        lockout_service=lockout_service,
        audit=MagicMock(),
        session_manager=MagicMock(),
    )


@pytest.mark.asyncio
async def test_unknown_login_lockout_does_not_email_unverified_address() -> None:
    validator = _validator(triggered=True)
    request = MagicMock(spec=Request)
    email = "unregistered@example.test"

    with patch.object(
        validator, "_trigger_lockout_alert", new_callable=AsyncMock
    ) as send_alert:
        with pytest.raises(HTTPException) as caught:
            await validator._handle_invalid_user(
                email, request, "en", BackgroundTasks()
            )

    assert caught.value.status_code == status.HTTP_423_LOCKED
    validator.lockout_service.register_failed_attempt.assert_awaited_once_with(
        email, None
    )
    send_alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_known_user_lockout_still_sends_alert() -> None:
    validator = _validator(triggered=True)
    request = MagicMock(spec=Request)
    email = "known@example.test"
    user = MagicMock()
    user.id = "user-id"
    user.full_name = "Known User"
    user.email_verified_at = datetime.now(UTC)

    with patch.object(
        validator, "_trigger_lockout_alert", new_callable=AsyncMock
    ) as send_alert:
        with pytest.raises(HTTPException) as caught:
            await validator._handle_invalid_password(
                user, email, request, "en", BackgroundTasks()
            )

    assert caught.value.status_code == status.HTTP_423_LOCKED
    validator.lockout_service.register_failed_attempt.assert_awaited_once_with(
        email, user.id
    )
    send_alert.assert_awaited_once_with(
        email,
        user.full_name,
        validator.lockout_service.register_failed_attempt.return_value[0],
        5,
        "en",
    )


@pytest.mark.asyncio
async def test_unverified_user_lockout_does_not_email_unverified_address() -> None:
    validator = _validator(triggered=True)
    request = MagicMock(spec=Request)
    email = "pending@example.test"
    user = MagicMock()
    user.id = "user-id"
    user.full_name = "Pending User"
    user.email_verified_at = None

    with patch.object(
        validator, "_trigger_lockout_alert", new_callable=AsyncMock
    ) as send_alert:
        with pytest.raises(HTTPException) as caught:
            await validator._handle_invalid_password(
                user, email, request, "en", BackgroundTasks()
            )

    assert caught.value.status_code == status.HTTP_423_LOCKED
    validator.lockout_service.register_failed_attempt.assert_awaited_once_with(
        email, user.id
    )
    send_alert.assert_not_awaited()
