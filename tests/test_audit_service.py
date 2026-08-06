"""Tests for the enhanced audit service."""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.audit_service import (
    AuditService,
    SecureAuditService,
    SecurityEvent,
    audit_service,
    auditable,
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


# --------------------------------------------------------------------------- #
# _redact_sensitive — sensitive-key + nested + list-of-dicts redaction        #
# --------------------------------------------------------------------------- #


def test_redact_sensitive_redacts_keys_nested_and_in_lists():
    """Sensitive keys are masked at the top level, inside nested dicts, and
    inside dicts within a list; non-sensitive scalars pass through untouched."""
    svc = AuditService()

    redacted = svc._redact_sensitive(
        {
            "password": "hunter2",  # pragma: allowlist secret
            "session_token": "abc",  # pragma: allowlist secret
            "username": "alice",  # passthrough scalar
            "profile": {"email": "a@b.co", "city": "NY"},  # nested dict
            "events": [{"otp": "000000"}, "plain-string"],  # list of dict + scalar
        }
    )

    assert redacted["password"] == "***REDACTED***"
    assert redacted["session_token"] == "***REDACTED***"
    assert redacted["username"] == "alice"
    assert redacted["profile"]["email"] == "***REDACTED***"
    assert redacted["profile"]["city"] == "NY"
    assert redacted["events"][0]["otp"] == "***REDACTED***"
    assert redacted["events"][1] == "plain-string"


# --------------------------------------------------------------------------- #
# Convenience wrappers — each delegates to .log with the right event/level     #
# --------------------------------------------------------------------------- #


def test_convenience_wrappers_delegate_to_log():
    svc = AuditService()
    req = MagicMock()
    uid = uuid4()
    with patch.object(svc, "log") as mock_log:
        svc.login_success(req, uid)
        svc.login_failure(req, reason="bad_pw")
        svc.logout(req, uid)
        svc.mfa_failure(req, uid, reason="bad_otp")
        svc.access_denied(req, uid, reason="rbac")
        svc.rate_limit_exceeded(req, uid)

    events = [c.args[0] for c in mock_log.call_args_list]
    assert events == [
        SecurityEvent.AUTH_LOGIN_SUCCESS,
        SecurityEvent.AUTH_LOGIN_FAILURE,
        SecurityEvent.AUTH_LOGOUT,
        SecurityEvent.MFA_VERIFY_FAILURE,
        SecurityEvent.ACCESS_DENIED,
        SecurityEvent.RATE_LIMIT_EXCEEDED,
    ]
    # login_failure / mfa_failure / access_denied / rate_limit escalate to WARNING.
    assert mock_log.call_args_list[1].kwargs["level"] == logging.WARNING
    assert mock_log.call_args_list[3].kwargs["level"] == logging.WARNING


# --------------------------------------------------------------------------- #
# auditable decorator — success logging, result redaction, exception re-raise  #
# --------------------------------------------------------------------------- #


class _FakeAuditor:
    def __init__(self):
        self.calls = []

    def log(self, event, request=None, user_id=None, **kwargs):
        self.calls.append((event, user_id, kwargs))


@pytest.mark.asyncio
async def test_auditable_logs_success_with_args_and_result():
    auditor = _FakeAuditor()

    class Svc:
        audit = auditor

        @auditable(
            "test.event",
            user_id_param="user",
            include_args=True,
            include_result=True,
        )
        async def do(self, *, user=None, request=None):
            return "all-good"

    user_obj = SimpleNamespace(id=uuid4())
    result = await Svc().do(user=user_obj, request=MagicMock())

    assert result == "all-good"
    assert len(auditor.calls) == 1
    event, user_id, kwargs = auditor.calls[0]
    assert event == "test.event"
    assert user_id == user_obj.id  # resolved via .id on the user object
    assert kwargs["result"] == "all-good"
    assert "args" in kwargs


@pytest.mark.asyncio
async def test_auditable_redacts_sensitive_result():
    auditor = _FakeAuditor()

    class Svc:
        audit = auditor

        @auditable("test.event", include_result=True)
        async def do(self, *, request=None):
            return "your token is sk-secret"

    await Svc().do(request=MagicMock())
    assert auditor.calls[0][2]["result"] == "***REDACTED_BY_SECURITY_POLICY***"


@pytest.mark.asyncio
async def test_auditable_resolves_request_from_positional_and_raw_user_id():
    auditor = _FakeAuditor()

    class Svc:
        audit = auditor

        # request passed positionally (exercises the signature-bind fallback);
        # user_id_param points at a raw uuid (no .id attribute branch).
        @auditable("test.event", user_id_param="actor")
        async def do(self, request, actor=None):
            return None

    raw_uid = uuid4()
    await Svc().do(MagicMock(), actor=raw_uid)
    assert auditor.calls[0][1] == raw_uid


@pytest.mark.asyncio
async def test_auditable_reraises_on_exception():
    class Svc:
        audit = _FakeAuditor()

        @auditable("test.event")
        async def boom(self):
            raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        await Svc().boom()


# --------------------------------------------------------------------------- #
# SecureAuditService — key parsing, HMAC signing, integrity verify, re-sign    #
# --------------------------------------------------------------------------- #


def _fake_log(signature=None):
    return SimpleNamespace(
        id=uuid4(),
        actor_user_id=uuid4(),
        subject_user_id=None,
        resource_type="user",
        resource_id="42",
        action="read",
        ip_address="10.0.0.1",
        created_at=datetime.now(UTC),
        signature=signature,
    )


def test_secure_audit_init_with_single_key_and_explicit_keys():
    svc1 = SecureAuditService(signing_key=b"primary")
    assert svc1._signing_keys == [b"primary"]
    svc2 = SecureAuditService(signing_keys=[b"a", b"b"])
    assert svc2._primary_key == b"a"


def test_secure_audit_parse_signing_keys_empty_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        SecureAuditService._parse_signing_keys("  ,  ")


def test_secure_audit_compute_signature_is_deterministic():
    svc = SecureAuditService(signing_key=b"k")
    log = _fake_log()
    sig1 = svc._compute_signature(log)
    sig2 = svc._compute_signature(log)
    assert sig1 == sig2
    assert len(sig1) == 64  # hex SHA-256


def test_secure_audit_verify_integrity_roundtrip_and_tamper():
    svc = SecureAuditService(signing_key=b"signing-key")
    log = _fake_log()
    log.signature = svc._compute_signature(log)

    assert svc.verify_integrity(log) is True

    # Tampering the payload (or the signature) breaks verification.
    log.action = "delete"
    assert svc.verify_integrity(log) is False


def test_secure_audit_verify_integrity_unsigned_is_false():
    svc = SecureAuditService(signing_key=b"k")
    assert svc.verify_integrity(_fake_log(signature=None)) is False


def test_secure_audit_resign_frozen_dto_returns_false():
    # _fake_log is not a DataAccessLog ORM instance, so resign cannot mutate it.
    svc = SecureAuditService(signing_key=b"k")
    log = _fake_log()
    log.signature = svc._compute_signature(log)
    assert svc.resign_log(log) is False


@pytest.mark.asyncio
async def test_secure_audit_create_log_and_verify_batch(db_session, user_factory):
    # actor_user_id must reference a real users row: the PostgreSQL integration
    # tier enforces the data_access_logs.actor_user_id FK (SQLite does not by
    # default), so a synthetic uuid4() raises ForeignKeyViolationError on CI.
    actor = await user_factory()
    svc = SecureAuditService(signing_key=b"db-signing-key")

    dto = await svc.create_log(
        db_session,
        actor_user_id=actor.id,
        resource_type="user",
        resource_id="7",
        action="read",
        ip_address="127.0.0.1",
    )
    # The signature is computed over the flushed row (id + created_at locked in).
    assert dto.signature
    assert svc.verify_integrity(dto) is True

    total, valid, invalid_ids = await svc.verify_batch(db_session)
    assert total >= 1
    assert valid == total - len(invalid_ids)


@pytest.mark.asyncio
async def test_record_domain_event_hmac_chaining(db_session):
    """Verify record_domain_event links events sequentially with HMAC chaining."""
    svc = SecureAuditService(signing_key=b"domain-event-secret-key-32bytes")
    agg_id = uuid4()

    event1 = await svc.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"subject": "Math", "room": "101"},
    )
    assert event1.prev_hash == "0" * 64
    assert event1.hash is not None
    assert len(event1.hash) == 64

    event2 = await svc.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "202"},
    )
    assert event2.prev_hash == event1.hash
    assert event2.hash is not None
    assert len(event2.hash) == 64

    is_valid, failed_id, err_msg = await svc.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_id
    )
    assert is_valid is True
    assert failed_id is None
    assert err_msg is None


@pytest.mark.asyncio
async def test_verify_chain_integrity_tamper_detection(db_session):
    """Verify tamper detection catches broken prev_hash or payload modification."""
    svc = SecureAuditService(signing_key=b"domain-event-secret-key-32bytes")
    agg_id = uuid4()

    _ = await svc.record_domain_event(
        db_session,
        event_type="GRADE_ASSIGNED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={"score": 90},
    )
    e2 = await svc.record_domain_event(
        db_session,
        event_type="GRADE_MODIFIED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={"score": 95},
    )

    # Verify initial integrity passes
    is_valid, _, _ = await svc.verify_chain_integrity(
        db_session, aggregate_type="grade", aggregate_id=agg_id
    )
    assert is_valid is True

    # Tamper with e2 payload
    e2.payload = {"score": 100}
    await db_session.flush()

    is_valid, failed_id, err_msg = await svc.verify_chain_integrity(
        db_session, aggregate_type="grade", aggregate_id=agg_id
    )
    assert is_valid is False
    assert failed_id == str(e2.id)
    assert (
        "tampering detected" in (err_msg or "").lower()
        or "discontinuity" in (err_msg or "").lower()
    )
