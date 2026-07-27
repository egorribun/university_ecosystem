"""Focused edge-path coverage for the secure audit service."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.services.audit_service as audit_module
from app.models.logs import DataAccessLog
from app.services.audit_service import SecureAuditService, auditable


class _Result:
    def __init__(self, rows=(), first=None):
        self.rows = list(rows)
        self._first = first

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self._first


def _event(
    event_type: str,
    payload: dict,
    *,
    created_at: datetime | None = None,
    event_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id or str(uuid4()),
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        event_type=event_type,
        payload=payload,
        version=1,
        created_at=created_at,
        prev_hash="0" * 64,
        hash="hash",
    )


def test_secure_audit_rejects_empty_explicit_key_list():
    with pytest.raises(ValueError, match="at least one signing key"):
        SecureAuditService(signing_keys=[])


def test_find_valid_key_returns_none_when_rust_matches_but_key_recheck_fails():
    service = SecureAuditService(signing_keys=[b"old", b"new"])
    log = SimpleNamespace(
        id=uuid4(),
        actor_user_id=None,
        subject_user_id=None,
        resource_type="user",
        resource_id="42",
        action="read",
        ip_address=None,
        created_at=datetime.now(UTC),
        signature="signature",
    )
    rust = MagicMock()
    rust.verify_audit_signature.return_value = True

    with (
        patch.dict(sys.modules, {"rust_ext": rust}),
        patch.object(service, "_compute_signature", return_value="different"),
    ):
        assert service._find_valid_key(log) is None


def test_resign_log_updates_mutable_orm_log():
    service = SecureAuditService(signing_key=b"primary")
    log = DataAccessLog(
        id=uuid4(),
        resource_type="user",
        resource_id="42",
        action="read",
        created_at=datetime.now(UTC),
    )
    log.signature = service._compute_signature(log)
    rust = MagicMock()
    rust.verify_audit_signature.return_value = True

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert service.resign_log(log) is True

    assert log.signature == service._compute_signature(log)


def test_resign_log_rejects_unsigned_log():
    service = SecureAuditService(signing_key=b"primary")
    log = DataAccessLog(
        id=uuid4(),
        resource_type="user",
        resource_id="42",
        action="read",
        created_at=datetime.now(UTC),
    )

    assert service.resign_log(log) is False


@pytest.mark.asyncio
async def test_record_domain_event_normalizes_naive_time_and_invalid_uuid():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(first=None))
    db.flush = AsyncMock()
    created_at = datetime(2026, 1, 1, 12, 0)

    event = await service.record_domain_event(
        db,
        event_type="CUSTOM",
        aggregate_type="aggregate",
        aggregate_id="not-a-uuid",
        payload={"value": 1},
        created_at=created_at,
    )

    assert event.aggregate_id_uuid is None
    assert event.created_at.tzinfo is UTC
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_domain_event_accepts_non_string_aggregate_identifier():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(first=None))
    db.flush = AsyncMock()

    event = await service.record_domain_event(
        db,
        event_type="CUSTOM",
        aggregate_type="aggregate",
        aggregate_id=123,
        payload={"value": 1},
    )

    assert event.aggregate_id == "123"
    assert event.aggregate_id_uuid is None


@pytest.mark.asyncio
async def test_verify_chain_integrity_accepts_empty_result():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())

    assert await service.verify_chain_integrity(db) == (True, None, None)


@pytest.mark.asyncio
async def test_verify_chain_integrity_uses_rust_success_path():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.return_value = (True, -1, None)

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(db) == (True, None, None)

    rust.verify_event_chain.assert_called_once()


@pytest.mark.asyncio
async def test_verify_chain_integrity_normalizes_naive_rust_event_time():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"value": 1}, created_at=datetime(2026, 1, 1, 12, 0))
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.return_value = (True, -1, None)

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(db) == (True, None, None)


@pytest.mark.asyncio
async def test_verify_chain_integrity_reports_rust_failure():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.return_value = (False, 0, "invalid chain")

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(db) == (
            False,
            event.id,
            "invalid chain",
        )


@pytest.mark.asyncio
async def test_verify_chain_integrity_falls_back_when_rust_raises():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    event.hash = service.compute_event_hash(
        event.prev_hash,
        service.canonicalize_event_payload(
            event.aggregate_type,
            event.aggregate_id,
            event.event_type,
            event.payload,
            event.version,
        ),
        event.created_at.isoformat(),
    )
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.side_effect = RuntimeError("ffi unavailable")

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(db) == (True, None, None)


@pytest.mark.asyncio
async def test_reconstruct_state_handles_naive_target_and_empty_events():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())

    result = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime(2026, 1, 1, 12, 0),
    )

    assert result == (None, 0, True)


@pytest.mark.asyncio
async def test_reconstruct_state_handles_update_without_existing_state():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("SCHEDULE_UPDATED", {"changes": {"room": "B-202"}})
    db.execute = AsyncMock(return_value=_Result([event]))

    state, count, valid = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert state == {"room": "B-202", "_version": 1}
    assert count == 1
    assert valid is True


@pytest.mark.asyncio
async def test_reconstruct_state_handles_score_update_without_new_score():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event(
        "GRADE_MODIFIED",
        {"old_score": 90, "reason": "manual review", "comment": "kept"},
        created_at=datetime.now(UTC),
    )
    db.execute = AsyncMock(return_value=_Result([event]))

    state, _, _ = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert state == {
        "comment": "kept",
        "_version": 1,
        "_updated_at": event.created_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_reconstruct_state_covers_creation_and_generic_event_folds():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    creation = _event("SCHEDULE_CREATED", {"room": "A-101"})
    generic_first = _event("CUSTOM", {"a": 1}, created_at=datetime.now(UTC))
    generic_second = _event("CUSTOM", {"b": 2})
    db.execute = AsyncMock(
        return_value=_Result([creation, generic_first, generic_second])
    )

    state, count, _ = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert state is not None
    assert state["a"] == 1
    assert state["b"] == 2
    assert count == 3


@pytest.mark.asyncio
async def test_reconstruct_state_starts_with_generic_event():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"first": True}, created_at=datetime.now(UTC))
    db.execute = AsyncMock(return_value=_Result([event]))

    state, count, _ = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert state is not None
    assert state["first"] is True
    assert count == 1


@pytest.mark.asyncio
async def test_reconstruct_state_creation_without_timestamp():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_Result([_event("SCHEDULE_CREATED", {"room": "A-101"})])
    )

    state, _, _ = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert state is not None
    assert "_created_at" not in state


@pytest.mark.asyncio
async def test_auditable_allows_missing_optional_user_id():
    auditor = MagicMock()

    class Service:
        audit = auditor

        @auditable("event", user_id_param="actor")
        async def run(self, actor=None, request=None):
            return "ok"

    assert await Service().run(request=MagicMock()) == "ok"
    auditor.log.assert_called_once()
    assert auditor.log.call_args.kwargs["user_id"] is None


def test_secure_audit_service_uses_double_checked_singleton():
    original = audit_module._secure_audit_service
    instance = object()
    try:
        with patch.object(audit_module, "SecureAuditService", return_value=instance):
            audit_module._secure_audit_service = None
            assert audit_module.get_secure_audit_service() is instance
            assert audit_module.get_secure_audit_service() is instance
    finally:
        audit_module._secure_audit_service = original


def test_secure_audit_service_handles_race_inside_lock():
    original = audit_module._secure_audit_service
    instance = object()

    class RaceLock:
        def __enter__(self):
            audit_module._secure_audit_service = instance
            return self

        def __exit__(self, *_args):
            return False

    try:
        audit_module._secure_audit_service = None
        with patch.object(audit_module, "_secure_audit_service_lock", RaceLock()):
            assert audit_module.get_secure_audit_service() is instance
    finally:
        audit_module._secure_audit_service = original
