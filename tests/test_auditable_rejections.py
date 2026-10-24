import asyncio
import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Request

from app.core.exceptions.domain import PermissionDenied
from app.services.audit_service import AuditService, SecurityEvent, auditable
from app.services.user.profile_service import UserProfileService


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "PUT",
            "scheme": "http",
            "path": "/admin/users",
            "raw_path": b"/admin/users",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "client": ("203.0.113.9", 4312),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.asyncio
async def test_real_decorated_admin_rejection_is_audited_without_payload(caplog):
    actor_id = uuid4()
    subject_id = uuid4()
    password_marker = str(uuid4())
    api_token_marker = str(uuid4())
    audit = AuditService()
    service = UserProfileService(
        uow=SimpleNamespace(users=object()),
        audit=audit,
        notifications=object(),
    )
    non_admin = SimpleNamespace(id=actor_id, role="student")
    private_profile = SimpleNamespace(
        email="person@example.test",
        password=password_marker,
        api_token=api_token_marker,
    )

    with caplog.at_level(logging.INFO, logger="app.access"):
        with pytest.raises(PermissionDenied):
            await service.admin_update_user(
                subject_id,
                private_profile,
                _request(),
                non_admin,
            )

    records = [record for record in caplog.records if record.name == "app.access"]
    assert len(records) == 1
    payload = json.loads(records[0].getMessage())
    assert payload["event"] == SecurityEvent.ACCESS_DENIED.value
    assert payload["user_id"] == str(actor_id)
    assert payload["subject_user_id"] == str(subject_id)
    assert payload["action"] == SecurityEvent.ADMIN_USER_MODIFY.value
    assert payload["reason"] == "permission_denied"
    assert "person@example.test" not in records[0].getMessage()
    assert password_marker not in records[0].getMessage()
    assert api_token_marker not in records[0].getMessage()
    assert "api_token" not in records[0].getMessage()


@pytest.mark.asyncio
async def test_auditable_unexpected_failure_is_not_logged_or_swallowed():
    calls = []

    class Auditor:
        def log(self, event, **kwargs):
            calls.append((event, kwargs))

    class Service:
        audit = Auditor()

        @auditable("test.privileged")
        async def run(self, request=None):
            raise RuntimeError("unexpected failure")

    with pytest.raises(RuntimeError, match="unexpected failure"):
        await Service().run(request=_request())
    assert calls == []


@pytest.mark.asyncio
async def test_auditable_cancellation_is_not_logged_or_swallowed():
    calls = []

    class Auditor:
        def log(self, event, **kwargs):
            calls.append((event, kwargs))

    class Service:
        audit = Auditor()

        @auditable("test.privileged")
        async def run(self, request=None):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await Service().run(request=_request())
    assert calls == []


@pytest.mark.asyncio
async def test_denial_event_omits_sensitive_exception_details(caplog):
    token_marker = str(uuid4())
    password_marker = str(uuid4())

    class Service:
        audit = AuditService()

        @auditable("admin.sensitive")
        async def run(self, *, request=None):
            raise PermissionDenied(
                f"denied for person@example.test {token_marker}",
                details={"password": password_marker},
            )

    with caplog.at_level(logging.INFO, logger="app.access"):
        with pytest.raises(PermissionDenied, match="denied for person"):
            await Service().run(request=_request())

    records = [record for record in caplog.records if record.name == "app.access"]
    assert len(records) == 1
    payload = json.loads(records[0].getMessage())
    assert payload["reason"] == "permission_denied"
    assert payload["action"] == "admin.sensitive"
    assert "person@example.test" not in records[0].getMessage()
    assert token_marker not in records[0].getMessage()
    assert password_marker not in records[0].getMessage()


@pytest.mark.asyncio
async def test_unexpected_audit_logger_failure_propagates():
    class BrokenAuditor:
        def log(self, event, **kwargs):
            raise RuntimeError("audit logger failed")

    class Service:
        audit = BrokenAuditor()

        @auditable("test.success")
        async def run(self, *, request=None):
            return "completed"

    with pytest.raises(RuntimeError, match="audit logger failed"):
        await Service().run(request=_request())


@pytest.mark.asyncio
async def test_audit_sink_permission_error_is_not_misclassified_as_operation_denial():
    calls = []

    class PermissionFailingAuditor:
        def log(self, event, **kwargs):
            calls.append(event)
            raise PermissionDenied("audit sink rejected the event")

    class Service:
        audit = PermissionFailingAuditor()

        @auditable("test.success")
        async def run(self, *, request=None):
            return "completed"

    with pytest.raises(PermissionDenied, match="audit sink rejected"):
        await Service().run(request=_request())
    assert calls == ["test.success"]


@pytest.mark.asyncio
async def test_denial_audit_logger_failure_propagates():
    class BrokenAuditor:
        def log(self, event, **kwargs):
            raise RuntimeError("audit logger failed during denial")

    class Service:
        audit = BrokenAuditor()

        @auditable("test.privileged")
        async def run(self, *, request=None):
            raise PermissionDenied("operation denied")

    with pytest.raises(RuntimeError, match="audit logger failed during denial"):
        await Service().run(request=_request())
