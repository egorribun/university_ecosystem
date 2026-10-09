"""Tests for the enhanced audit service."""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request

from app.schemas.dtos.audit import DataAccessLogDTO
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


@pytest.mark.parametrize(
    ("method", "event", "logger_name", "level"),
    [
        ("logout", "auth.logout", "app.auth", logging.INFO),
        ("rate_limit_exceeded", "access.rate_limit", "app.access", logging.WARNING),
    ],
)
def test_convenience_audit_events_emit_identity_and_request_context(
    caplog, method, event, logger_name, level
):
    user_id = uuid4()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/account",
            "headers": [],
            "client": ("203.0.113.9", 4321),
        }
    )
    with caplog.at_level(logging.INFO, logger=logger_name):
        getattr(AuditService(), method)(request, user_id)

    records = [record for record in caplog.records if record.name == logger_name]
    assert len(records) == 1
    assert records[0].levelno == level
    payload = json.loads(records[0].getMessage())
    assert payload["event"] == event
    assert payload["user_id"] == str(user_id)
    assert payload["path"] == "/account"
    assert payload["method"] == "POST"
    assert payload["ip"] == "203.0.113.9"


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
        context={"detail": "original"},
        ip_address="10.0.0.1",
        user_agent="synthetic-agent-original",
        created_at=datetime.now(UTC),
        signature=signature,
    )


def test_secure_audit_init_with_single_key_and_explicit_keys():
    svc1 = SecureAuditService(signing_key=b"primary")
    assert svc1._signing_keys == [b"primary"]
    svc2 = SecureAuditService(signing_keys=[b"a", b"b"])
    assert svc2._primary_key == b"a"


def test_secure_audit_init_uses_configured_rotation_keys(monkeypatch):
    monkeypatch.setattr(
        "app.services.audit_service.settings",
        SimpleNamespace(audit_log_secret=" current-key , previous-key "),
    )

    service = SecureAuditService()

    assert service._signing_keys == [b"current-key", b"previous-key"]


def test_secure_audit_parse_signing_keys_empty_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        SecureAuditService._parse_signing_keys("  ,  ")


def test_secure_audit_parse_signing_keys_keeps_nonempty_rotation_entries():
    assert SecureAuditService._parse_signing_keys(" first , , second ") == [
        b"first",
        b"second",
    ]


def test_secure_audit_compute_signature_is_deterministic():
    svc = SecureAuditService(signing_key=b"k")
    log = _fake_log()
    sig1 = svc._compute_signature(log)
    sig2 = svc._compute_signature(log)
    assert sig1 == sig2
    assert sig1.startswith("v2:")
    assert len(sig1.removeprefix("v2:")) == 64  # hex SHA-256


def test_secure_audit_verifies_persisted_v2_format_with_nullable_ids() -> None:
    """Optional IDs retain their established empty-string encoding in v2."""
    # These None values are accepted by the DTO and are create_log's defaults.
    # Sign the wire fixture independently so signer/verifier drift is observable.
    canonical_payload = (
        '{"action":"read","actor_user_id":"",'
        '"context":{"detail":"original"},"created_at":"2026-09-22T12:34:56+00:00",'
        '"id":"00000000-0000-0000-0000-000000000001","ip_address":"192.0.2.1",'
        '"resource_id":"","resource_type":"user","subject_user_id":"",'
        '"user_agent":"synthetic-agent","version":2}'
    )
    fixture_key = b"test-only-audit-v2-key"
    signature = (
        "v2:"
        + hmac.new(
            fixture_key, canonical_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    )
    log = DataAccessLogDTO(
        id=UUID(int=1),
        actor_user_id=None,
        subject_user_id=None,
        resource_type="user",
        resource_id=None,
        action="read",
        context={"detail": "original"},
        ip_address="192.0.2.1",
        user_agent="synthetic-agent",
        created_at=datetime(2026, 9, 22, 12, 34, 56, tzinfo=UTC),
        signature=signature,
    )
    service = SecureAuditService(signing_key=fixture_key)

    assert service.verify_integrity(log) is True
    for field, value in (
        ("actor_user_id", UUID(int=2)),
        ("subject_user_id", UUID(int=3)),
        ("resource_id", "42"),
    ):
        tampered = log.model_copy(update={field: value})
        assert service.verify_integrity(tampered) is False, field


def test_secure_audit_verifies_persisted_v2_format_with_empty_action() -> None:
    """An accepted empty action retains its persisted v2 wire representation."""
    canonical_payload = (
        '{"action":"","actor_user_id":"",'
        '"context":{"detail":"original"},"created_at":"2026-09-22T12:34:56+00:00",'
        '"id":"00000000-0000-0000-0000-000000000001","ip_address":"192.0.2.1",'
        '"resource_id":"","resource_type":"user","subject_user_id":"",'
        '"user_agent":"synthetic-agent","version":2}'
    )
    fixture_key = b"test-only-audit-v2-key"
    # Independent wire fixture: do not sign with the service under test.
    signature = (
        "v2:"
        + hmac.new(
            fixture_key, canonical_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    )
    log = DataAccessLogDTO(
        id=UUID(int=1),
        actor_user_id=None,
        subject_user_id=None,
        resource_type="user",
        resource_id=None,
        action="",
        context={"detail": "original"},
        ip_address="192.0.2.1",
        user_agent="synthetic-agent",
        created_at=datetime(2026, 9, 22, 12, 34, 56, tzinfo=UTC),
        signature=signature,
    )
    service = SecureAuditService(signing_key=fixture_key)

    assert service.verify_integrity(log) is True
    tampered = DataAccessLogDTO.model_validate({**log.model_dump(), "action": "read"})
    assert service.verify_integrity(tampered) is False


def test_secure_audit_verify_integrity_roundtrip_and_tamper():
    svc = SecureAuditService(signing_key=b"signing-key")
    log = _fake_log()
    log.signature = svc._compute_signature(log)

    assert svc.verify_integrity(log) is True

    # Tampering the payload (or the signature) breaks verification.
    log.action = "delete"
    assert svc.verify_integrity(log) is False


@pytest.mark.parametrize("field", ["context", "user_agent"])
def test_secure_audit_integrity_detects_metadata_tampering(field: str) -> None:
    svc = SecureAuditService(signing_key=b"signing-key")
    log = _fake_log()
    log.signature = svc._compute_signature(log)

    if field == "context":
        log.context = {"detail": "changed"}
    else:
        log.user_agent = "synthetic-agent-changed"

    assert svc.verify_integrity(log) is False


def test_secure_audit_verify_integrity_accepts_legacy_signature() -> None:
    svc = SecureAuditService(signing_key=b"signing-key")
    log = _fake_log()
    legacy_parts = [
        str(log.id or ""),
        str(log.actor_user_id or ""),
        str(log.subject_user_id or ""),
        str(log.resource_type or ""),
        str(log.resource_id or ""),
        str(log.action or ""),
        str(log.ip_address or ""),
        log.created_at.isoformat(),
    ]
    legacy_data = "|".join(legacy_parts)
    log.signature = hmac.new(
        b"signing-key", legacy_data.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    assert svc.verify_integrity(log) is True
    status = svc.signature_status(log)
    assert status.signature_scheme == "legacy_pipe_v1"
    assert "id" in status.authenticated_fields
    for field in ("resource_type", "resource_id", "action", "ip_address"):
        assert field in status.authenticated_fields
        assert field not in status.unauthenticated_fields
    assert {"context", "user_agent"}.issubset(status.unauthenticated_fields)


def test_secure_audit_verifies_legacy_json_array_signature_with_exact_coverage() -> (
    None
):
    key = b"synthetic-json-array-legacy-key"
    svc = SecureAuditService(signing_key=key)
    log = _fake_log()
    legacy_payload = json.dumps(
        [
            str(log.actor_user_id) if log.actor_user_id else None,
            str(log.subject_user_id) if log.subject_user_id else None,
            log.resource_type,
            log.resource_id,
            log.action,
            log.context,
            log.ip_address,
            log.user_agent,
            log.created_at.isoformat(),
        ],
        separators=(",", ":"),
    )
    log.signature = hmac.new(
        key, legacy_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    status = svc.signature_status(log)

    assert status.is_valid is True
    assert status.signature_scheme == "legacy_json_array_v1"
    assert "id" in status.unauthenticated_fields
    assert {"context", "user_agent"}.issubset(status.authenticated_fields)
    assert "resource_id" in status.authenticated_fields
    assert "resource_id" not in status.unauthenticated_fields
    assert "actor_name" in status.unauthenticated_fields
    assert "subject_name" in status.unauthenticated_fields


def test_secure_audit_verifies_legacy_batch_json_array_normalization() -> None:
    key = b"synthetic-legacy-batch-key"
    service = SecureAuditService(signing_key=key)
    log = _fake_log()
    log.resource_type = None
    log.resource_id = ""
    log.action = None
    payload = json.dumps(
        [
            str(log.actor_user_id) if log.actor_user_id else None,
            str(log.subject_user_id) if log.subject_user_id else None,
            "",
            None,
            "",
            log.context,
            log.ip_address,
            log.user_agent,
            log.created_at.isoformat(),
        ],
        separators=(",", ":"),
    )
    log.signature = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    # The persisted empty string and the historical batch-normalized null have
    # identical signature bytes. Simulate loading the same signature after the
    # nullable column has been represented as NULL.
    log.resource_id = None

    status = service.signature_status(log)

    assert status.is_valid is True
    assert status.signature_scheme == "legacy_json_array_v1"
    assert "id" in status.unauthenticated_fields
    assert "resource_id" in status.unauthenticated_fields
    assert "resource_id" not in status.authenticated_fields


@pytest.mark.parametrize(
    ("field", "original", "substituted"),
    [
        (field, original, substituted)
        for field in ("resource_id", "ip_address", "user_agent")
        for original, substituted in ((None, ""), ("", None))
    ],
)
def test_v2_nullable_empty_substitution_is_not_reported_as_authenticated(
    field: str, original: str | None, substituted: str | None
) -> None:
    service = SecureAuditService(signing_key=b"nullable-field-audit-key")
    log = DataAccessLogDTO.model_validate(_fake_log())
    unsigned = log.model_copy(update={field: original, "signature": None})
    signed = unsigned.model_copy(
        update={"signature": service._compute_signature(unsigned)}
    )
    substituted_log = signed.model_copy(update={field: substituted})

    status = service.signature_status(substituted_log)

    assert status.is_valid is True
    assert status.signature_scheme == "canonical_v2"
    assert field in status.unauthenticated_fields
    assert field not in status.authenticated_fields
    assert "id" in status.authenticated_fields


@pytest.mark.parametrize("field", ["resource_id", "ip_address", "user_agent"])
def test_v2_nonempty_nullable_fields_remain_authenticated(field: str) -> None:
    service = SecureAuditService(signing_key=b"nullable-field-audit-key")
    log = DataAccessLogDTO.model_validate(_fake_log())
    signed = log.model_copy(update={"signature": service._compute_signature(log)})

    status = service.signature_status(signed)

    assert status.is_valid is True
    assert field in status.authenticated_fields
    assert field not in status.unauthenticated_fields


def test_legacy_pipe_delimiter_repartition_marks_mutable_strings_ambiguous() -> None:
    service = SecureAuditService(signing_key=b"legacy-pipe-audit-key")
    log = _fake_log()
    log.resource_type = "document|public"
    log.resource_id = "42"
    signed_payload = service._legacy_signature_payload(log)
    log.signature = service._compute_legacy_signature(log)

    # Both rows produce the same historical bare-pipe payload bytes:
    # "document|public|42" versus "document|public|42".
    log.resource_type = "document"
    log.resource_id = "public|42"
    assert service._legacy_signature_payload(log) == signed_payload
    status = service.signature_status(log)

    assert status.is_valid is True
    assert status.signature_scheme == "legacy_pipe_v1"
    for field in ("resource_type", "resource_id", "action", "ip_address"):
        assert field in status.unauthenticated_fields
        assert field not in status.authenticated_fields
    for field in ("id", "actor_user_id", "created_at"):
        assert field in status.authenticated_fields


@pytest.mark.parametrize(
    ("field", "original", "substituted"),
    [
        (field, original, substituted)
        for field in ("resource_id", "ip_address")
        for original, substituted in ((None, ""), ("", None))
    ],
)
def test_legacy_pipe_nullable_empty_substitution_is_not_authenticated(
    field: str, original: str | None, substituted: str | None
) -> None:
    service = SecureAuditService(signing_key=b"legacy-pipe-audit-key")
    log = _fake_log()
    setattr(log, field, original)
    log.signature = service._compute_legacy_signature(log)
    setattr(log, field, substituted)

    status = service.signature_status(log)

    assert status.is_valid is True
    assert status.signature_scheme == "legacy_pipe_v1"
    assert field in status.unauthenticated_fields
    assert field not in status.authenticated_fields


def test_secure_audit_verify_integrity_accepts_independent_v2_fixture() -> None:
    """Pin the persisted v2 format independently of the production serializer."""
    fixture_key = b"test-only-audit-v2-key"
    payload = (
        '{"action":"read","actor_user_id":"00000000-0000-0000-0000-000000000002",'
        '"context":{"detail":"original"},"created_at":"2026-09-22T12:34:56+00:00",'
        '"id":"00000000-0000-0000-0000-000000000001","ip_address":"192.0.2.1",'
        '"resource_id":"42","resource_type":"user",'
        '"subject_user_id":"00000000-0000-0000-0000-000000000003",'
        '"user_agent":"synthetic-agent","version":2}'
    )
    signature = hmac.new(
        fixture_key, payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    log = DataAccessLogDTO(
        id=UUID(int=1),
        actor_user_id=UUID(int=2),
        subject_user_id=UUID(int=3),
        resource_type="user",
        resource_id="42",
        action="read",
        context={"detail": "original"},
        ip_address="192.0.2.1",
        user_agent="synthetic-agent",
        created_at=datetime(2026, 9, 22, 12, 34, 56, tzinfo=UTC),
        signature=f"v2:{signature}",
    )
    service = SecureAuditService(signing_keys=[b"current-test-key", fixture_key])

    assert service.verify_integrity(log) is True
    status = service.signature_status(log)
    assert status.signature_scheme == "canonical_v2"
    assert "id" in status.authenticated_fields
    assert "context" not in status.unauthenticated_fields

    tampered = log.model_copy(update={"actor_user_id": UUID(int=4)})
    assert service.verify_integrity(tampered) is False


def test_secure_audit_verify_integrity_unsigned_is_false():
    svc = SecureAuditService(signing_key=b"k")
    assert svc.verify_integrity(_fake_log(signature=None)) is False
    status = svc.signature_status(_fake_log(signature=None))
    assert status.signature_scheme == "unsigned"
    assert status.authenticated_fields == ()


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


@pytest.mark.asyncio
async def test_verify_chain_integrity_rejects_deleted_prefix(db_session):
    svc = SecureAuditService(signing_key=b"domain-event-secret-key-32bytes")
    agg_id = uuid4()
    first = await svc.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "101"},
    )
    second = await svc.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "202"},
    )
    await db_session.delete(first)
    await db_session.flush()

    is_valid, failed_id, _ = await svc.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_id
    )

    assert is_valid is False
    assert failed_id == str(second.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["first_sequence", "first_root", "sequence_gap"])
async def test_verify_chain_integrity_rejects_invalid_sequence_or_root(
    db_session, tamper
):
    svc = SecureAuditService(signing_key=b"domain-event-secret-key-32bytes")
    agg_id = uuid4()
    first = await svc.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "101"},
    )
    if tamper == "sequence_gap":
        event = await svc.record_domain_event(
            db_session,
            event_type="SCHEDULE_UPDATED",
            aggregate_type="schedule",
            aggregate_id=agg_id,
            payload={"room": "202"},
        )
        event.sequence_number = 3
    elif tamper == "first_sequence":
        first.sequence_number = 3
    else:
        first.prev_hash = "f" * 64
        canonical = svc.canonicalize_event_payload(
            aggregate_type=first.aggregate_type,
            aggregate_id=first.aggregate_id,
            event_type=first.event_type,
            payload=first.payload,
            version=first.version,
        )
        first.hash = svc.compute_event_hash(
            first.prev_hash,
            canonical,
            first.created_at.isoformat(),
        )
    await db_session.flush()

    is_valid, _, _ = await svc.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_id
    )

    assert is_valid is False


@pytest.mark.asyncio
async def test_verify_chain_integrity_skips_only_unhashed_outbox_rows(db_session):
    from app.models.domain_events import StoredEvent

    svc = SecureAuditService(signing_key=b"domain-event-secret-key-32bytes")
    agg_id = uuid4()
    await svc.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "101"},
    )
    db_session.add(
        StoredEvent(
            event_type="NotificationsRequested",
            aggregate_type="NotificationBatch",
            aggregate_id=str(uuid4()),
            payload={"notification_ids": []},
        )
    )
    await db_session.flush()

    is_valid, failed_id, error = await svc.verify_chain_integrity(db_session)

    assert is_valid is True
    assert failed_id is None
    assert error is None


@pytest.mark.asyncio
async def test_verify_chain_integrity_rejects_partially_marked_outbox_row(db_session):
    from app.models.domain_events import StoredEvent

    event = StoredEvent(
        event_type="NotificationsRequested",
        aggregate_type="NotificationBatch",
        aggregate_id=str(uuid4()),
        payload={"notification_ids": []},
        sequence_number=1,
        prev_hash="0" * 64,
        hash=None,
    )
    db_session.add(event)
    await db_session.flush()

    is_valid, failed_id, error = await SecureAuditService(
        signing_key=b"domain-event-secret-key-32bytes"
    ).verify_chain_integrity(db_session)

    assert is_valid is False
    assert failed_id == str(event.id)
    assert "invalid chain hash" in (error or "").lower()


@pytest.mark.asyncio
async def test_verify_chain_integrity_rejects_chain_row_with_removed_markers(
    db_session,
):
    service = SecureAuditService(signing_key=b"domain-event-secret-key-32bytes")
    event = await service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=uuid4(),
        payload={"room": "101"},
    )
    event.sequence_number = None
    event.prev_hash = None
    event.hash = None
    await db_session.flush()

    is_valid, failed_id, error = await service.verify_chain_integrity(db_session)

    assert is_valid is False
    assert failed_id == str(event.id)
    assert "sequence" in (error or "").lower()
