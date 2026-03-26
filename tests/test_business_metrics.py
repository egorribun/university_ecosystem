"""Tests for business metrics helper functions."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.metrics import (
    _ACTIVE_USERS,
    _CHAT_MESSAGES_TOTAL,
    _EVENT_REGISTRATIONS,
    _LOGIN_FAILURE,
    _LOGIN_SUCCESS,
    _MFA_ADOPTION,
    _NOTIFICATIONS_DELIVERED,
    _NOTIFICATIONS_FAILED,
    _WS_CONNECTIONS_ACTIVE,
)

_skip_no_prom = pytest.mark.skipif(
    _LOGIN_SUCCESS is None, reason="prometheus_client not configured"
)


@_skip_no_prom
def test_record_login_success():
    """Test login success metric recording."""
    from app.core.metrics import record_login_success

    mock_labels = MagicMock()
    with patch.object(
        _LOGIN_SUCCESS, "labels", return_value=mock_labels
    ) as mock_method:
        record_login_success()
        mock_method.assert_called_once_with(method="password")
        mock_labels.inc.assert_called_once()


@pytest.mark.skipif(_LOGIN_FAILURE is None, reason="prometheus_client not configured")
def test_record_login_failure():
    """Test login failure metric recording with reason."""
    from app.core.metrics import record_login_failure

    mock_labels = MagicMock()
    with patch.object(
        _LOGIN_FAILURE, "labels", return_value=mock_labels
    ) as mock_method:
        record_login_failure("invalid_password")
        mock_method.assert_called_once_with(reason="invalid_password")
        mock_labels.inc.assert_called_once()


@pytest.mark.skipif(_LOGIN_FAILURE is None, reason="prometheus_client not configured")
def test_record_login_failure_default_reason():
    """Test login failure with default reason."""
    from app.core.metrics import record_login_failure

    mock_labels = MagicMock()
    with patch.object(
        _LOGIN_FAILURE, "labels", return_value=mock_labels
    ) as mock_method:
        record_login_failure()
        mock_method.assert_called_once_with(reason="invalid_credentials")


@pytest.mark.skipif(
    _NOTIFICATIONS_DELIVERED is None, reason="prometheus_client not configured"
)
def test_record_notification_delivered():
    """Test notification delivered metric."""
    from app.core.metrics import record_notification_delivered

    mock_labels = MagicMock()
    with patch.object(
        _NOTIFICATIONS_DELIVERED, "labels", return_value=mock_labels
    ) as mock_method:
        record_notification_delivered("push")
        mock_method.assert_called_once_with(type="push")
        mock_labels.inc.assert_called_once()


@pytest.mark.skipif(
    _NOTIFICATIONS_FAILED is None, reason="prometheus_client not configured"
)
def test_record_notification_failed():
    """Test notification failed metric."""
    from app.core.metrics import record_notification_failed

    mock_labels = MagicMock()
    with patch.object(
        _NOTIFICATIONS_FAILED, "labels", return_value=mock_labels
    ) as mock_method:
        record_notification_failed("email", "timeout")
        mock_method.assert_called_once_with(type="email", reason="timeout")
        mock_labels.inc.assert_called_once()


@pytest.mark.skipif(
    _EVENT_REGISTRATIONS is None, reason="prometheus_client not configured"
)
def test_record_event_registration():
    """Test event registration metric."""
    from app.core.metrics import record_event_registration

    with patch.object(_EVENT_REGISTRATIONS, "inc") as mock_inc:
        record_event_registration()
        mock_inc.assert_called_once()


@pytest.mark.skipif(_ACTIVE_USERS is None, reason="prometheus_client not configured")
def test_set_active_users():
    """Test active users gauge."""
    from app.core.metrics import set_active_users

    mock_labels = MagicMock()
    with patch.object(_ACTIVE_USERS, "labels", return_value=mock_labels) as mock_method:
        set_active_users(150, period="weekly")
        mock_method.assert_called_once_with(period="weekly")
        mock_labels.set.assert_called_once_with(150.0)


@pytest.mark.skipif(_ACTIVE_USERS is None, reason="prometheus_client not configured")
def test_set_active_users_default_period():
    """Test active users gauge with default daily period."""
    from app.core.metrics import set_active_users

    mock_labels = MagicMock()
    with patch.object(_ACTIVE_USERS, "labels", return_value=mock_labels) as mock_method:
        set_active_users(100)
        mock_method.assert_called_once_with(period="daily")


@pytest.mark.skipif(_MFA_ADOPTION is None, reason="prometheus_client not configured")
def test_set_mfa_adoption():
    """Test MFA adoption gauge."""
    from app.core.metrics import set_mfa_adoption

    with patch.object(_MFA_ADOPTION, "set") as mock_set:
        set_mfa_adoption(50)
        mock_set.assert_called_once_with(50.0)


@pytest.mark.skipif(
    _CHAT_MESSAGES_TOTAL is None, reason="prometheus_client not configured"
)
def test_record_chat_message():
    """Test chat message metric recording."""
    from app.core.metrics import record_chat_message

    mock_labels = MagicMock()
    with patch.object(
        _CHAT_MESSAGES_TOTAL, "labels", return_value=mock_labels
    ) as mock_method:
        record_chat_message("123")
        mock_method.assert_called_once_with(channel="123")
        mock_labels.inc.assert_called_once()


@pytest.mark.skipif(
    _WS_CONNECTIONS_ACTIVE is None, reason="prometheus_client not configured"
)
def test_set_ws_connections_active():
    """Test websocket connections gauge."""
    from app.core.metrics import set_ws_connections_active

    mock_labels = MagicMock()
    with patch.object(
        _WS_CONNECTIONS_ACTIVE, "labels", return_value=mock_labels
    ) as mock_method:
        set_ws_connections_active("/ws/chat", 5)
        mock_method.assert_called_once_with(path="/ws/chat")
        mock_labels.set.assert_called_once_with(5.0)
