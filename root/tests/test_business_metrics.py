"""Tests for business metrics helper functions."""

import pytest
from unittest.mock import patch, MagicMock


def test_record_login_success():
    """Test login success metric recording."""
    from app.core.metrics import record_login_success, _LOGIN_SUCCESS

    if _LOGIN_SUCCESS is not None:
        with patch.object(_LOGIN_SUCCESS, "inc") as mock_inc:
            record_login_success()
            mock_inc.assert_called_once()


def test_record_login_failure():
    """Test login failure metric recording with reason."""
    from app.core.metrics import record_login_failure, _LOGIN_FAILURE

    if _LOGIN_FAILURE is not None:
        mock_labels = MagicMock()
        with patch.object(_LOGIN_FAILURE, "labels", return_value=mock_labels) as mock_method:
            record_login_failure("invalid_password")
            mock_method.assert_called_once_with(reason="invalid_password")
            mock_labels.inc.assert_called_once()


def test_record_login_failure_default_reason():
    """Test login failure with default reason."""
    from app.core.metrics import record_login_failure, _LOGIN_FAILURE

    if _LOGIN_FAILURE is not None:
        mock_labels = MagicMock()
        with patch.object(_LOGIN_FAILURE, "labels", return_value=mock_labels) as mock_method:
            record_login_failure()
            mock_method.assert_called_once_with(reason="invalid_credentials")


def test_record_notification_delivered():
    """Test notification delivered metric."""
    from app.core.metrics import record_notification_delivered, _NOTIFICATIONS_DELIVERED

    if _NOTIFICATIONS_DELIVERED is not None:
        mock_labels = MagicMock()
        with patch.object(
            _NOTIFICATIONS_DELIVERED, "labels", return_value=mock_labels
        ) as mock_method:
            record_notification_delivered("push")
            mock_method.assert_called_once_with(type="push")
            mock_labels.inc.assert_called_once()


def test_record_notification_failed():
    """Test notification failed metric."""
    from app.core.metrics import record_notification_failed, _NOTIFICATIONS_FAILED

    if _NOTIFICATIONS_FAILED is not None:
        mock_labels = MagicMock()
        with patch.object(
            _NOTIFICATIONS_FAILED, "labels", return_value=mock_labels
        ) as mock_method:
            record_notification_failed("email", "timeout")
            mock_method.assert_called_once_with(type="email", reason="timeout")
            mock_labels.inc.assert_called_once()


def test_record_event_registration():
    """Test event registration metric."""
    from app.core.metrics import record_event_registration, _EVENT_REGISTRATIONS

    if _EVENT_REGISTRATIONS is not None:
        with patch.object(_EVENT_REGISTRATIONS, "inc") as mock_inc:
            record_event_registration()
            mock_inc.assert_called_once()


def test_set_active_users():
    """Test active users gauge."""
    from app.core.metrics import set_active_users, _ACTIVE_USERS

    if _ACTIVE_USERS is not None:
        mock_labels = MagicMock()
        with patch.object(_ACTIVE_USERS, "labels", return_value=mock_labels) as mock_method:
            set_active_users(150, period="weekly")
            mock_method.assert_called_once_with(period="weekly")
            mock_labels.set.assert_called_once_with(150.0)


def test_set_active_users_default_period():
    """Test active users gauge with default daily period."""
    from app.core.metrics import set_active_users, _ACTIVE_USERS

    if _ACTIVE_USERS is not None:
        mock_labels = MagicMock()
        with patch.object(_ACTIVE_USERS, "labels", return_value=mock_labels) as mock_method:
            set_active_users(100)
            mock_method.assert_called_once_with(period="daily")


def test_set_mfa_adoption():
    """Test MFA adoption gauge."""
    from app.core.metrics import set_mfa_adoption, _MFA_ADOPTION

    if _MFA_ADOPTION is not None:
        with patch.object(_MFA_ADOPTION, "set") as mock_set:
            set_mfa_adoption(50)
            mock_set.assert_called_once_with(50.0)
