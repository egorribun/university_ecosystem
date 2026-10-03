"""Focused closure tests for admin audit validation and timestamp handling."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.admin.audit import get_time_travel_state, list_audit_logs
from app.services.audit_service import SecureAuditService
from tests.conftest import call_injected


def _dependencies() -> tuple[MagicMock, MagicMock, MagicMock]:
    return MagicMock(), MagicMock(), MagicMock()


@pytest.mark.asyncio
async def test_list_audit_logs_rejects_unknown_resource_type():
    db, secure_audit, admin = _dependencies()

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            list_audit_logs,
            limit=50,
            offset=0,
            resource_type="unknown",
            _=admin,
            provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "invalid_resource_type"
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_list_audit_logs_rejects_unknown_action():
    db, secure_audit, admin = _dependencies()

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            list_audit_logs,
            limit=50,
            offset=0,
            action="unknown.action",
            _=admin,
            provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "invalid_action"
    db.execute.assert_not_called()


@pytest.mark.parametrize("action", ["read", "export", "delete"])
@pytest.mark.asyncio
async def test_list_audit_logs_accepts_actions_emitted_by_data_access(action: str):
    db, secure_audit, admin = _dependencies()
    total_result = MagicMock()
    total_result.scalar_one.return_value = 0
    db.execute = AsyncMock(side_effect=[[], total_result])

    response = await call_injected(
        list_audit_logs,
        limit=50,
        offset=0,
        actor_id=None,
        subject_id=None,
        resource_type=None,
        action=action,
        _=admin,
        provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
    )

    assert response.total == 0
    assert db.execute.await_count == 2
    for call in db.execute.await_args_list:
        statement = call.args[0]
        assert "data_access_logs.action =" in str(statement)
        assert action in statement.compile().params.values()


@pytest.mark.asyncio
async def test_list_audit_logs_uses_a_unique_pagination_tiebreaker():
    db, secure_audit, admin = _dependencies()
    total_result = MagicMock()
    total_result.scalar_one.return_value = 0
    db.execute = AsyncMock(side_effect=[[], total_result])

    await call_injected(
        list_audit_logs,
        limit=50,
        offset=0,
        actor_id=None,
        subject_id=None,
        resource_type=None,
        action=None,
        _=admin,
        provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
    )

    statement = db.execute.await_args_list[0].args[0]
    order_by = tuple(str(clause) for clause in statement._order_by_clauses)

    assert order_by == (
        "data_access_logs.created_at DESC",
        "data_access_logs.id DESC",
    )


@pytest.mark.parametrize(
    ("signature_kind", "expected_valid", "expected_metadata"),
    [
        ("v2", True, True),
        ("legacy", True, False),
        ("invalid", False, False),
    ],
)
@pytest.mark.asyncio
async def test_list_audit_logs_only_exposes_authenticated_metadata(
    signature_kind: str, expected_valid: bool, expected_metadata: bool
):
    db, _, admin = _dependencies()
    secure_audit = SecureAuditService(signing_key=b"synthetic-admin-audit-test-key")
    log = SimpleNamespace(
        id=uuid4(),
        actor_user_id=uuid4(),
        subject_user_id=uuid4(),
        resource_type="profile",
        resource_id="42",
        action="data.view",
        context={"detail": "synthetic audit context"},
        ip_address="127.0.0.1",
        user_agent="synthetic-audit-test-agent",
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        signature=None,
    )
    if signature_kind == "v2":
        log.signature = secure_audit._compute_signature(log)
    elif signature_kind == "legacy":
        log.signature = secure_audit._compute_legacy_signature(log)
    else:
        log.signature = "invalid-signature"

    total_result = MagicMock()
    total_result.scalar_one.return_value = 1
    db.execute = AsyncMock(side_effect=[[(log, "Actor", "Subject")], total_result])

    response = await call_injected(
        list_audit_logs,
        limit=50,
        offset=0,
        actor_id=None,
        subject_id=None,
        resource_type=None,
        action=None,
        _=admin,
        provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
    )

    item = response.items[0]
    assert item.is_valid is expected_valid
    assert item.context == (log.context if expected_metadata else None)
    assert item.user_agent == (log.user_agent if expected_metadata else None)
    assert item.ip_address == (log.ip_address if expected_valid else None)
    assert item.actor_user_id == log.actor_user_id
    assert item.actor_name == "Actor"
    assert item.subject_user_id == log.subject_user_id
    assert item.subject_name == "Subject"


@pytest.mark.asyncio
async def test_time_travel_requires_timestamp():
    db, secure_audit, admin = _dependencies()

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            get_time_travel_state,
            aggregate_type="user",
            aggregate_id=uuid4(),
            target_timestamp=None,
            timestamp=None,
            verify_chain=True,
            _=admin,
            provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
        )

    assert exc_info.value.status_code == 400
    secure_audit.reconstruct_state.assert_not_called()


@pytest.mark.asyncio
async def test_time_travel_normalizes_naive_timestamp_and_uses_alias():
    db, secure_audit, admin = _dependencies()
    secure_audit.reconstruct_state = AsyncMock(return_value=({"_version": 7}, 2, True))
    aggregate_id = uuid4()

    response = await call_injected(
        get_time_travel_state,
        aggregate_type="USER",
        aggregate_id=aggregate_id,
        target_timestamp=None,
        timestamp=datetime(2026, 7, 26, 12, 0, 0),
        verify_chain=False,
        _=admin,
        provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
    )

    assert response.aggregate_type == "USER"
    assert response.version_at_timestamp == 7
    assert response.target_timestamp.tzinfo is not None
    secure_audit.reconstruct_state.assert_awaited_once()
    assert secure_audit.reconstruct_state.await_args.kwargs["aggregate_type"] == "user"
    assert secure_audit.reconstruct_state.await_args.kwargs["verify_chain"] is False


@pytest.mark.asyncio
async def test_time_travel_rejects_unsupported_aggregate_type_before_reconstruction():
    db, secure_audit, admin = _dependencies()

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            get_time_travel_state,
            aggregate_type="internal_table",
            aggregate_id=uuid4(),
            target_timestamp=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            timestamp=None,
            verify_chain=True,
            _=admin,
            provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "invalid_aggregate_type"
    secure_audit.reconstruct_state.assert_not_called()


@pytest.mark.asyncio
async def test_time_travel_returns_not_found_when_no_history_exists():
    db, secure_audit, admin = _dependencies()
    target = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    secure_audit.reconstruct_state = AsyncMock(return_value=(None, 0, True))

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            get_time_travel_state,
            aggregate_type="user",
            aggregate_id=uuid4(),
            target_timestamp=target,
            timestamp=None,
            verify_chain=True,
            _=admin,
            provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
        )

    assert exc_info.value.status_code == 404
    secure_audit.reconstruct_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_time_travel_prefers_target_timestamp_and_reports_invalid_chain():
    db, secure_audit, admin = _dependencies()
    target = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    alias = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    reconstructed = {"_version": 3, "name": "synthetic historical state"}
    secure_audit.reconstruct_state = AsyncMock(return_value=(reconstructed, 2, False))

    response = await call_injected(
        get_time_travel_state,
        aggregate_type="USER",
        aggregate_id=uuid4(),
        target_timestamp=target,
        timestamp=alias,
        verify_chain=True,
        _=admin,
        provides={"AsyncDatabaseSession": db, "SecureAuditService": secure_audit},
    )

    assert response.target_timestamp == target
    assert response.state_at_timestamp == reconstructed
    assert response.version_at_timestamp == 3
    assert response.chain_integrity_valid is False
    secure_audit.reconstruct_state.assert_awaited_once()
    assert (
        secure_audit.reconstruct_state.await_args.kwargs["target_timestamp"] == target
    )
