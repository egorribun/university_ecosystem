"""Focused closure tests for admin audit validation and timestamp handling."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.admin.audit import get_time_travel_state, list_audit_logs
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
