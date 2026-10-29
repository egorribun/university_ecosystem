"""Focused edge-path coverage for the secure audit service."""

from __future__ import annotations

import json
import secrets
import sys
from collections import UserString
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.services.audit_service as audit_module
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
    sequence_number: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id or str(uuid4()),
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        event_type=event_type,
        payload=payload,
        version=1,
        sequence_number=sequence_number,
        created_at=created_at,
        prev_hash="0" * 64,
        hash="hash",
    )


class _EventWithChangingPrevHash:
    """Model a row-like value changing while the Python fallback rechecks it."""

    def __init__(self, event: SimpleNamespace, prev_hash_values: list[str]) -> None:
        self.__dict__.update(vars(event))
        self._prev_hash_values = prev_hash_values
        self._prev_hash_reads = 0

    @property
    def prev_hash(self) -> str:
        index = min(self._prev_hash_reads, len(self._prev_hash_values) - 1)
        self._prev_hash_reads += 1
        return self._prev_hash_values[index]


def _audit_log_stub(*, signature: str | None = None) -> SimpleNamespace:
    """Build the small DTO surface used by SecureAuditService's pure paths."""

    return SimpleNamespace(
        id=uuid4(),
        actor_user_id=None,
        subject_user_id=None,
        resource_type="user",
        resource_id="42",
        action="read",
        ip_address="127.0.0.1",
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        signature=signature,
    )


def _sign_event(
    service: SecureAuditService, event: SimpleNamespace, prev_hash: str
) -> None:
    event.prev_hash = prev_hash
    canonical = service.canonicalize_event_payload(
        event.aggregate_type,
        event.aggregate_id,
        event.event_type,
        event.payload,
        event.version,
    )
    event.hash = service.compute_event_hash(
        prev_hash, canonical, event.created_at.replace(tzinfo=UTC).isoformat()
    )


async def _record_v2_event(service: SecureAuditService):
    actor_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(first=None))
    db.flush = AsyncMock()
    event = await service.record_domain_event(
        db,
        event_type="CUSTOM",
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        payload={"value": 1},
        actor_id=actor_id,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    return db, event, actor_id


def test_audit_service_log_includes_reason_in_payload():
    service = audit_module.AuditService()
    target_logger = MagicMock()

    with patch.object(service, "_select_logger", return_value=target_logger):
        service.log("access.denied", reason="policy")

    target_logger.log.assert_called_once()
    payload = target_logger.log.call_args.args[1]
    assert '"reason": "policy"' in payload


def test_secure_audit_rejects_empty_explicit_key_list():
    with pytest.raises(ValueError, match="at least one signing key"):
        SecureAuditService(signing_keys=[])


def test_find_valid_key_returns_none_when_rust_matches_but_key_recheck_fails():
    service = SecureAuditService(signing_keys=[b"old", b"new"])
    log = _audit_log_stub()
    log.signature = service._compute_signature(log)
    rust = MagicMock()
    rust.verify_audit_signature.return_value = True

    with (
        patch.dict(sys.modules, {"rust_ext": rust}),
        patch.object(service, "_compute_signature", return_value="different"),
    ):
        assert service._find_valid_key(log) is None


@pytest.mark.parametrize("signature", ["v2:short", "v2:" + "g" * 64])
def test_find_valid_key_rejects_malformed_v2_digest(signature: str) -> None:
    service = SecureAuditService(signing_key=b"test-key")
    log = _audit_log_stub(signature=signature)

    assert service._find_valid_key(log) is None


def test_find_valid_key_rejects_unversioned_non_digest_signature() -> None:
    service = SecureAuditService(signing_key=b"test-key")
    log = _audit_log_stub(signature="not-a-digest")

    assert service._find_valid_key(log) is None


def test_find_valid_key_falls_back_to_python_when_rust_is_unavailable():
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
        signature=None,
    )
    log.signature = service._compute_signature(log, key=b"new")
    rust = MagicMock()
    rust.verify_audit_signature.side_effect = RuntimeError("ffi unavailable")

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert service._find_valid_key(log) == b"new"


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
async def test_record_domain_event_preserves_uuid_aggregate_identifier():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(first=None))
    db.flush = AsyncMock()
    aggregate_id = uuid4()

    event = await service.record_domain_event(
        db,
        event_type="CUSTOM",
        aggregate_type="aggregate",
        aggregate_id=aggregate_id,
        payload={"value": 1},
    )

    assert event.aggregate_id_uuid == aggregate_id


@pytest.mark.asyncio
async def test_record_domain_event_signs_actor_and_signature_version_metadata():
    service = SecureAuditService(signing_key=b"key")
    db, event, actor_id = await _record_v2_event(service)
    signature_metadata = {
        "actor_id": str(actor_id),
        audit_module._DOMAIN_EVENT_SIGNATURE_VERSION_KEY: (
            audit_module._DOMAIN_EVENT_SIGNATURE_VERSION
        ),
    }
    canonical = service.canonicalize_event_payload(
        event.aggregate_type,
        event.aggregate_id,
        event.event_type,
        event.payload,
        event.version,
        metadata=signature_metadata,
    )

    assert event.metadata_ == signature_metadata
    assert event.hash == service.compute_event_hash(
        event.prev_hash, canonical, event.created_at.isoformat()
    )
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["actor_id", "remove_signature_marker"])
async def test_verify_chain_integrity_rejects_actor_metadata_tampering(tamper: str):
    service = SecureAuditService(signing_key=b"key")
    db, event, _actor_id = await _record_v2_event(service)
    if tamper == "actor_id":
        event.metadata_["actor_id"] = str(uuid4())
    else:
        event.metadata_.pop(audit_module._DOMAIN_EVENT_SIGNATURE_VERSION_KEY)
    db.execute = AsyncMock(return_value=_Result([event]))

    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        is_valid, failed_id, error = await service.verify_chain_integrity(db)

    assert is_valid is False
    assert failed_id == str(event.id)
    assert error is not None


@pytest.mark.asyncio
async def test_verify_chain_integrity_passes_v2_metadata_to_mocked_rust_boundary():
    """Check the canonical payload passed to the Rust adapter mock, not native Rust."""
    service = SecureAuditService(signing_key=b"key")
    db, event, _actor_id = await _record_v2_event(service)
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.return_value = (True, -1, None)

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(db) == (True, None, None)

    chain_tuples = rust.verify_event_chain.call_args.args[2]
    canonical = json.loads(chain_tuples[0][2])
    assert canonical["metadata"] == event.metadata_


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"_audit_signature_version": 1, "actor_id": "actor"},
        {"_audit_signature_version": 3, "actor_id": "actor"},
        {"_audit_signature_version": "2", "actor_id": "actor"},
        {"_audit_signature_version": True, "actor_id": "actor"},
        ["actor"],
        "actor",
    ],
)
@pytest.mark.parametrize("rust_available", [False, True])
async def test_verify_chain_integrity_rejects_invalid_signature_metadata(
    metadata: object, rust_available: bool
):
    service = SecureAuditService(signing_key=b"key")
    db, event, _actor_id = await _record_v2_event(service)
    event.metadata_ = metadata
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.return_value = (True, -1, None)
    verifier = rust if rust_available else SimpleNamespace()

    with patch.dict(sys.modules, {"rust_ext": verifier}):
        is_valid, failed_id, error = await service.verify_chain_integrity(db)

    assert is_valid is False
    assert failed_id == str(event.id)
    assert "metadata" in str(error).lower()
    if rust_available:
        rust.verify_event_chain.assert_not_called()


@pytest.mark.asyncio
async def test_verify_chain_integrity_passes_historical_payload_to_mocked_rust_boundary():
    """Check legacy canonicalization at the mocked Rust adapter boundary."""
    service = SecureAuditService(signing_key=b"key")
    event = _event(
        "CUSTOM",
        {"value": 1},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    event.metadata_ = {"actor_id": str(uuid4())}
    _sign_event(service, event, "0" * 64)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.return_value = (True, -1, None)

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(db) == (True, None, None)

    chain_tuples = rust.verify_event_chain.call_args.args[2]
    assert "metadata" not in json.loads(chain_tuples[0][2])


@pytest.mark.asyncio
async def test_v2_event_accepts_secondary_rotation_key_and_rejects_other_keys():
    old_key = secrets.token_bytes(32)
    new_key = secrets.token_bytes(32)
    unknown_key = secrets.token_bytes(32)
    signer = SecureAuditService(signing_key=old_key)
    db, event, _actor_id = await _record_v2_event(signer)
    db.execute = AsyncMock(return_value=_Result([event]))

    primary_only = SecureAuditService(signing_key=new_key)
    rotating = SecureAuditService(signing_keys=[new_key, old_key])
    unknown = SecureAuditService(signing_key=unknown_key)
    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        primary_only_result = await primary_only.verify_chain_integrity(db)
        rotating_result = await rotating.verify_chain_integrity(db)
        unknown_result = await unknown.verify_chain_integrity(db)

    assert primary_only_result[0] is False
    assert rotating_result == (True, None, None)
    assert unknown_result[0] is False


@pytest.mark.asyncio
async def test_legacy_unmarked_signature_keeps_payload_only_coverage():
    """Legacy rows stay verifiable, but actor metadata is not authenticated."""
    service = SecureAuditService(signing_key=b"key")
    event = _event(
        "CUSTOM",
        {"value": 1},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    event.metadata_ = {"actor_id": str(uuid4())}
    _sign_event(service, event, "0" * 64)
    event.metadata_["actor_id"] = str(uuid4())
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result([event]))

    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        assert await service.verify_chain_integrity(db) == (True, None, None)


@pytest.mark.asyncio
async def test_create_log_returns_updated_row_after_signing_flushed_dto():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    created = _audit_log_stub()
    updated = _audit_log_stub()

    with patch.object(audit_module, "AuditRepository") as repository_type:
        repository = repository_type.return_value
        repository.create = AsyncMock(return_value=created)
        repository.update = AsyncMock(return_value=updated)

        result = await service.create_log(
            db,
            resource_type="user",
            resource_id="42",
            action="read",
        )

    assert result is updated
    repository.create.assert_awaited_once()
    repository.update.assert_awaited_once()
    assert repository.update.await_args.args[0] == created.id
    assert repository.update.await_args.args[1]["signature"]


@pytest.mark.asyncio
async def test_create_log_returns_signed_copy_when_update_has_no_row():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    created = _audit_log_stub()
    fallback = _audit_log_stub()
    created.model_copy = MagicMock(return_value=fallback)

    with patch.object(audit_module, "AuditRepository") as repository_type:
        repository = repository_type.return_value
        repository.create = AsyncMock(return_value=created)
        repository.update = AsyncMock(return_value=None)

        result = await service.create_log(
            db,
            resource_type="user",
            resource_id="42",
            action="read",
        )

    assert result is fallback
    created.model_copy.assert_called_once()
    assert created.model_copy.call_args.kwargs["update"]["signature"]


@pytest.mark.asyncio
async def test_create_logs_empty_batch_is_a_noop():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()

    assert await service.create_logs(db, entries=[]) == []

    db.add_all.assert_not_called()
    db.flush.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_chain_integrity_accepts_empty_result():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())

    assert await service.verify_chain_integrity(db) == (True, None, None)


@pytest.mark.asyncio
async def test_verify_chain_integrity_accepts_only_unchained_outbox_rows():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    unchained = _event("OUTBOX", {"kind": "notice"}, sequence_number=1)
    unchained.sequence_number = None
    unchained.prev_hash = None
    unchained.hash = None
    unchained.metadata_ = {"source": "outbox"}
    db.execute = AsyncMock(return_value=_Result([unchained]))

    assert await service.verify_chain_integrity(db) == (True, None, None)

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_chain_integrity_uses_rust_success_path():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    db.execute = AsyncMock(return_value=_Result([event]))
    rust = MagicMock()
    rust.verify_event_chain.return_value = (True, -1, None)

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(
            db, aggregate_type="aggregate", aggregate_id=uuid4()
        ) == (True, None, None)

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
async def test_verify_chain_integrity_python_fallback_accepts_rotated_key_and_groups_events():
    service = SecureAuditService(signing_keys=[b"old", b"key"])
    db = MagicMock()
    first = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    second = _event(
        "CUSTOM", {"value": 2}, created_at=datetime.now(UTC), sequence_number=2
    )
    _sign_event(service, first, "0" * 64)
    _sign_event(service, second, first.hash)
    rust = SimpleNamespace()
    db.execute = AsyncMock(return_value=_Result([first, second]))

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert await service.verify_chain_integrity(db) == (True, None, None)


@pytest.mark.asyncio
async def test_verify_chain_integrity_python_fallback_normalizes_naive_event_time():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"value": 1}, created_at=datetime(2026, 1, 1, 12, 0))
    _sign_event(service, event, "0" * 64)
    db.execute = AsyncMock(return_value=_Result([event]))

    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        assert await service.verify_chain_integrity(db) == (True, None, None)


@pytest.mark.asyncio
async def test_verify_chain_integrity_reports_link_discontinuity():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    first = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    second = _event(
        "CUSTOM", {"value": 2}, created_at=datetime.now(UTC), sequence_number=2
    )
    _sign_event(service, first, "0" * 64)
    second.prev_hash = "broken"
    db.execute = AsyncMock(return_value=_Result([first, second]))

    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        valid, failed_id, error = await service.verify_chain_integrity(db)

    assert valid is False
    assert failed_id == second.id
    assert "Chain discontinuity" in str(error)


@pytest.mark.asyncio
async def test_verify_chain_integrity_fallback_rechecks_link_discontinuity():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    first = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    _sign_event(service, first, "0" * 64)
    second = _event(
        "CUSTOM", {"value": 2}, created_at=datetime.now(UTC), sequence_number=2
    )
    second.hash = "nonempty-unverified-hash"
    changing_second = _EventWithChangingPrevHash(second, [first.hash, "broken"])
    db.execute = AsyncMock(return_value=_Result([first, changing_second]))

    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        valid, failed_id, error = await service.verify_chain_integrity(db)

    assert valid is False
    assert failed_id == second.id
    assert "Chain discontinuity at index 1" in str(error)


@pytest.mark.asyncio
async def test_verify_chain_integrity_fallback_rejects_non_string_prev_hash():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    first = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    _sign_event(service, first, "0" * 64)
    second = _event(
        "CUSTOM", {"value": 2}, created_at=datetime.now(UTC), sequence_number=2
    )
    second.prev_hash = UserString(first.hash)
    second.hash = "nonempty-unverified-hash"
    db.execute = AsyncMock(return_value=_Result([first, second]))

    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        valid, failed_id, error = await service.verify_chain_integrity(db)

    assert valid is False
    assert failed_id == second.id
    assert "Invalid previous hash at index 1" in str(error)


@pytest.mark.asyncio
async def test_verify_chain_integrity_reports_payload_tampering():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event("CUSTOM", {"value": 1}, created_at=datetime.now(UTC))
    event.hash = "tampered"
    db.execute = AsyncMock(return_value=_Result([event]))

    with patch.dict(sys.modules, {"rust_ext": SimpleNamespace()}):
        valid, failed_id, error = await service.verify_chain_integrity(db)

    assert valid is False
    assert failed_id == event.id
    assert "tampering" in str(error)


@pytest.mark.asyncio
async def test_reconstruct_state_covers_verified_creation_updates_and_deletion():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    created_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    events = [
        _event("SCHEDULE_CREATED", {"room": "A-101"}, created_at=created_at),
        _event(
            "SCHEDULE_UPDATED",
            {"current_state": {"room": "B-202"}},
            created_at=created_at,
        ),
        _event(
            "SCHEDULE_UPDATED",
            {"changes": {"teacher": {"old": "A", "new": "B"}}},
            created_at=created_at,
        ),
        _event("SCHEDULE_DELETED", {}, created_at=None),
    ]
    db.execute = AsyncMock(return_value=_Result(events))

    with patch.object(
        service,
        "verify_chain_integrity",
        new=AsyncMock(return_value=(False, events[1].id, "invalid")),
    ):
        state, count, valid = await service.reconstruct_state(
            db,
            aggregate_type="aggregate",
            aggregate_id="aggregate-1",
            target_timestamp=created_at,
            verify_chain=True,
        )

    assert state == {"_deleted": True, "_deleted_at": None}
    assert count == 4
    assert valid is False


@pytest.mark.asyncio
@pytest.mark.parametrize("verify_chain, expected_valid", [(True, True), (False, False)])
async def test_reconstruct_state_handles_naive_target_and_empty_events(
    verify_chain, expected_valid
):
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())

    result = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime(2026, 1, 1, 12, 0),
        verify_chain=verify_chain,
    )

    assert result == (None, 0, expected_valid)


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
    assert valid is False


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

    state, _, valid = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert valid is False
    assert state == {
        "comment": "kept",
        "_version": 1,
        "_updated_at": event.created_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_reconstruct_state_applies_new_score_update():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    event = _event(
        "GRADE_MODIFIED",
        {"old_score": 90, "new_score": 95},
        created_at=datetime.now(UTC),
    )
    db.execute = AsyncMock(return_value=_Result([event]))

    state, _, valid = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert valid is False
    assert state is not None
    assert state["score"] == 95


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

    state, count, valid = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert valid is False
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

    state, count, valid = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert valid is False
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

    state, _, valid = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert valid is False
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


def test_verify_integrity_accepts_rotated_legacy_signature_on_rust_fast_path() -> None:
    service = SecureAuditService(signing_keys=[b"old", b"new"])
    log = _audit_log_stub()
    log.signature = service._compute_legacy_signature(log, key=b"new")
    rust = MagicMock()
    rust.verify_audit_signature.return_value = True

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert service.verify_integrity(log) is True

    rust.verify_audit_signature.assert_called_once()


def test_secure_audit_verify_integrity_accepts_legacy_signature_in_python_fallback() -> (
    None
):
    service = SecureAuditService(signing_keys=[b"old", b"new"])
    log = _audit_log_stub()
    log.signature = service._compute_legacy_signature(log, key=b"new")
    rust = MagicMock()
    rust.verify_audit_signature.side_effect = RuntimeError("ffi unavailable")

    with patch.dict(sys.modules, {"rust_ext": rust}):
        assert service.verify_integrity(log) is True

    assert service.signature_covers_metadata(log) is False
    rust.verify_audit_signature.assert_called_once()


@pytest.mark.asyncio
async def test_reconstruct_state_never_replays_unchained_outbox_payload():
    service = SecureAuditService(signing_key=b"key")
    db = MagicMock()
    outbox_row = _event(
        "OUTBOX",
        {"kind": "notification", "sensitive_state": "must not become history"},
        sequence_number=1,
    )
    outbox_row.sequence_number = None
    outbox_row.prev_hash = None
    outbox_row.hash = None
    outbox_row.metadata_ = {"source": "transactional-outbox"}
    db.execute = AsyncMock(return_value=_Result([outbox_row]))

    result = await service.reconstruct_state(
        db,
        aggregate_type="aggregate",
        aggregate_id="aggregate-1",
        target_timestamp=datetime.now(UTC),
        verify_chain=False,
    )

    assert result == (None, 0, False)
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("isolation", "allowed"),
    [
        ("read committed", True),
        ("read uncommitted", True),
        ("repeatable read", False),
        ("serializable", False),
    ],
)
async def test_record_domain_event_checks_isolation_before_locking_the_aggregate(
    isolation: str, allowed: bool
) -> None:
    """Check emitted SQL and stable identity; real PostgreSQL proves locking."""
    service = SecureAuditService(signing_key=secrets.token_hex(32).encode("ascii"))
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.scalar = AsyncMock(return_value=isolation)
    db.execute = AsyncMock(return_value=_Result(first=None))
    db.flush = AsyncMock()
    event_arguments = {
        "event_type": "CUSTOM",
        "aggregate_type": "grade",
        "aggregate_id": "aud340-unit",
        "payload": {"value": 1},
    }

    if allowed:
        event = await service.record_domain_event(db, **event_arguments)
        assert event.sequence_number == 1
        assert event.prev_hash == "0" * 64
    else:
        with pytest.raises(
            ValueError, match=r"^Domain event writes require READ COMMITTED semantics$"
        ):
            await service.record_domain_event(db, **event_arguments)
        db.add.assert_not_called()
        db.flush.assert_not_awaited()

    assert db.scalar.await_count == 1
    isolation_statement = db.scalar.await_args.args[0]
    assert str(isolation_statement).startswith("SELECT pg_catalog.current_setting(")
    assert list(isolation_statement.compile().params.values()) == [
        "transaction_isolation"
    ]
    statements = [call.args[0] for call in db.execute.await_args_list]
    if not allowed:
        assert statements == []
        return

    assert len(statements) == 2
    lock_statement, head_statement = statements
    assert str(lock_statement).startswith("SELECT pg_catalog.pg_advisory_xact_lock(")
    # Fixed SHA-256 vector for the namespaced JSON tuple, not Python's hash().
    assert list(lock_statement.compile().params.values()) == [4157649041181095682]
    head_parameters = head_statement.compile().params
    assert head_parameters["aggregate_type_1"] == "grade"
    assert head_parameters["aggregate_id_1"] == "aud340-unit"
