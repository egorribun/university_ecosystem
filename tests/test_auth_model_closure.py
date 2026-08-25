"""Closure tests for executable helpers in the authentication models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models.auth import (
    EmailChangeToken,
    FailedLoginAttempt,
    LoginHistory,
    PasswordResetToken,
    _generate_session_signing_key,
)


def test_session_signing_key_is_urlsafe_and_random():
    with patch(
        "app.models.auth.secrets.token_urlsafe", return_value="generated-key"
    ) as token:
        assert _generate_session_signing_key() == "generated-key"
    token.assert_called_once_with(32)


def test_token_generators_return_values_from_secure_random_source():
    with patch(
        "app.models.auth.secrets.token_urlsafe", return_value="reset-token"
    ) as token:
        assert PasswordResetToken.issue_token() == "reset-token"
    token.assert_called_once_with(32)


def test_email_change_token_active_states_cover_expiry_and_usage():
    future = datetime.now(UTC) + timedelta(hours=1)
    past = datetime.now(UTC) - timedelta(hours=1)

    assert EmailChangeToken(expires_at=future, used=False).is_active is True
    assert EmailChangeToken(expires_at=past, used=False).is_active is False
    assert EmailChangeToken(expires_at=future, used=True).is_active is False
    assert EmailChangeToken(expires_at=None, used=False).is_active is False


def test_system_managed_assignment_flag_is_removed_by_model_constructors():
    failed = FailedLoginAttempt(
        _allow_system_managed_assignment=True,
        email="user@example.com",
        ip_address="127.0.0.1",
    )
    history = LoginHistory(
        _allow_system_managed_assignment=True,
        ip_address="127.0.0.1",
        status="success",
    )

    assert failed.email == "user@example.com"
    assert history.status == "success"
