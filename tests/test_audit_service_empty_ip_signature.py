"""Pin the v2 audit wire encoding for a missing client IP."""

import hashlib
import hmac
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.schemas.dtos.audit import DataAccessLogDTO
from app.services.audit_service import SecureAuditService


def test_v2_integrity_accepts_independent_fixture_with_missing_ip() -> None:
    fixture_key = b"test-only-audit-v2-empty-ip-key"
    canonical_payload = (
        '{"action":"read","actor_user_id":"",'
        '"context":null,"created_at":"2026-09-22T12:34:56+00:00",'
        '"id":"00000000-0000-0000-0000-000000000001","ip_address":"",'
        '"resource_id":"","resource_type":"user","subject_user_id":"",'
        '"user_agent":"","version":2}'
    )
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
        context=None,
        ip_address=None,
        user_agent=None,
        created_at=datetime(2026, 9, 22, 12, 34, 56, tzinfo=UTC),
        signature=signature,
    )
    rust = MagicMock()
    rust.verify_audit_signature.side_effect = RuntimeError("FFI unavailable")

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert SecureAuditService(signing_key=fixture_key).verify_integrity(log) is True

    rust.verify_audit_signature.assert_called_once()
