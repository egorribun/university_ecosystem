"""Tests for the enhanced audit service."""

import logging

import pytest
from unittest.mock import MagicMock, patch

from app.services.audit_service import (
    AuditService,
    SecurityEvent,
    audit_service,
)


def test_security_event_enum_values():
    """Verify SecurityEvent enum values."""
    # Auth events
    assert SecurityEvent.AUTH_LOGIN_SUCCESS == "auth.login.success"
    assert SecurityEvent.AUTH_LOGIN_FAILURE == "auth.login.failure"
    assert SecurityEvent.AUTH_LOGOUT == "auth.logout"
    assert SecurityEvent.AUTH_REGISTER == "auth.register"

    # MFA events
    assert SecurityEvent.MFA_ENROLL_START == "mfa.enroll.start"
    assert SecurityEvent.MFA_VERIFY_SUCCESS == "mfa.verify.success"
    assert SecurityEvent.MFA_VERIFY_FAILURE == "mfa.verify.failure"

    # Password events
    assert SecurityEvent.PASSWORD_CHANGE == "password.change"
    assert SecurityEvent.PASSWORD_RESET_REQUEST == "password.reset.request"

    # Access events
    assert SecurityEvent.ACCESS_DENIED == "access.denied"
    assert SecurityEvent.RATE_LIMIT_EXCEEDED == "access.rate_limit"


def test_audit_service_singleton_exists():
    """Verify the singleton instance is exported."""
    assert audit_service is not None
    assert isinstance(audit_service, AuditService)


def test_audit_service_select_logger_auth():
    """Test logger routing for auth events."""
    svc = AuditService()
    logger = svc._select_logger("auth.login.success")
    assert logger.name == "app.auth"


def test_audit_service_select_logger_users():
    """Test logger routing for user events."""
    svc = AuditService()
    logger = svc._select_logger("users.profile.update")
    assert logger.name == "app.users.audit"

    logger = svc._select_logger("password.change")
    assert logger.name == "app.users.audit"


def test_audit_service_select_logger_mfa():
    """Test logger routing for MFA events."""
    svc = AuditService()
    logger = svc._select_logger("mfa.verify.success")
    assert logger.name == "app.mfa"


def test_audit_service_select_logger_admin():
    """Test logger routing for admin events."""
    svc = AuditService()
    logger = svc._select_logger("admin.user.create")
    assert logger.name == "app.admin"


def test_audit_service_select_logger_access():
    """Test logger routing for access events."""
    svc = AuditService()
    logger = svc._select_logger("access.denied")
    assert logger.name == "app.access"


def test_audit_service_select_logger_default():
    """Test logger routing for unknown events."""
    svc = AuditService()
    logger = svc._select_logger("unknown.event")
    assert logger.name == "app.audit"


@patch("app.services.audit_service.get_request_id")
def test_audit_service_log_basic(mock_get_request_id):
    """Test basic logging without request."""
    mock_get_request_id.return_value = "test-request-123"

    svc = AuditService()
    with patch.object(svc, "_select_logger") as mock_select:
        mock_logger = MagicMock()
        mock_select.return_value = mock_logger

        svc.log(SecurityEvent.AUTH_REGISTER, user_id=42)

        mock_logger.log.assert_called_once()
        call_args = mock_logger.log.call_args
        assert call_args[0][0] == logging.INFO


@patch("app.services.audit_service.get_request_id")
def test_audit_service_log_with_request(mock_get_request_id):
    """Test logging with request object."""
    mock_get_request_id.return_value = "req-456"

    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.1"
    mock_request.url.path = "/api/v1/auth/login"
    mock_request.method = "POST"

    svc = AuditService()
    with patch.object(svc, "_select_logger") as mock_select:
        mock_logger = MagicMock()
        mock_select.return_value = mock_logger

        svc.log(SecurityEvent.AUTH_LOGIN_SUCCESS, mock_request, user_id=1)

        mock_logger.log.assert_called_once()
        call_args = mock_logger.log.call_args
        extra = call_args[1]["extra"]
        assert extra["ip"] == "192.168.1.1"
        assert extra["path"] == "/api/v1/auth/login"
        assert extra["method"] == "POST"
