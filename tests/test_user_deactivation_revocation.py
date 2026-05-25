"""W136 SW2 — User deactivation publishes session revocations to gateway.

Closes immediate-effect part of W135 §Honesty #2. anonymize_user_data flow now
revokes all active sessions via revoke_sessions_matching which:

- Marks session.revoked_at=now in DB
- Publishes JTI to session:revocations Redis channel (gateway picks up via
  existing ListenForRevocations consumer)
- SETs revoked:jti:{jti} in Redis with TTL (gateway L2 cache hit)
- Rotates signing_key

Without this SW2, delete_sensitive_data DELETEs the ActiveSession rows but
gateway's L1 cache still reports the JTI as not-revoked for up to 30s
(default TTL) — deactivated user keeps access until cache expires.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from sqlalchemy import and_

from app.models import ActiveSession


def _build_test_request(path: str = "/admin/users/x") -> Request:
    """Minimal valid ASGI scope for FastAPI Request."""
    scope = {
        "type": "http",
        "method": "DELETE",
        "path": path,
        "headers": [(b"user-agent", b"pytest")],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 8080),
        "root_path": "",
    }
    return Request(scope)


async def _create_active_session(db_session, user_id, ip_octet=1):
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user_id,
        jti=str(uuid.uuid4()),
        expires_at=now + timedelta(hours=1),
        created_at=now,
        last_seen_at=now,
        ip_address=f"10.0.0.{ip_octet}",
        user_agent="pytest",
    )
    db_session.add(session)
    return session


@pytest.mark.asyncio
async def test_revoke_sessions_matching_marks_db_revoked_and_publishes(
    db_session, user_factory
):
    """revoke_sessions_matching marks DB rows revoked + calls Redis backend per JTI."""
    user = await user_factory(is_active=True)

    s1 = await _create_active_session(db_session, user.id, ip_octet=1)
    s2 = await _create_active_session(db_session, user.id, ip_octet=2)
    s3 = await _create_active_session(db_session, user.id, ip_octet=3)
    await db_session.commit()
    expected_jtis = {s1.jti, s2.jti, s3.jti}

    mock_backend = AsyncMock()
    mock_backend.revoke_session = AsyncMock()

    with patch(
        "app.services.session_cleanup.get_session_backend",
        return_value=mock_backend,
    ):
        from app.services.session_cleanup import revoke_sessions_matching

        revoked = await revoke_sessions_matching(
            db=db_session,
            whereclause=and_(
                ActiveSession.user_id == user.id,
                ActiveSession.revoked_at.is_(None),
            ),
        )
        await db_session.commit()

        assert revoked == 3, "should revoke 3 sessions"

    for session in (s1, s2, s3):
        await db_session.refresh(session)
        assert session.revoked_at is not None, f"{session.jti} not revoked in DB"

    revoked_jtis = {call.args[0] for call in mock_backend.revoke_session.call_args_list}
    assert revoked_jtis == expected_jtis


@pytest.mark.asyncio
async def test_revoke_sessions_matching_skips_already_revoked(db_session, user_factory):
    """revoke_sessions_matching does not double-revoke already-revoked sessions."""
    user = await user_factory(is_active=True)

    active = await _create_active_session(db_session, user.id, ip_octet=1)
    revoked = await _create_active_session(db_session, user.id, ip_octet=2)
    revoked.revoked_at = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.commit()

    mock_backend = AsyncMock()
    mock_backend.revoke_session = AsyncMock()

    with patch(
        "app.services.session_cleanup.get_session_backend",
        return_value=mock_backend,
    ):
        from app.services.session_cleanup import revoke_sessions_matching

        revoked_count = await revoke_sessions_matching(
            db=db_session,
            whereclause=and_(
                ActiveSession.user_id == user.id,
                ActiveSession.revoked_at.is_(None),
            ),
        )
        await db_session.commit()

        assert revoked_count == 1

    revoked_jtis = {call.args[0] for call in mock_backend.revoke_session.call_args_list}
    assert revoked_jtis == {active.jti}


@pytest.mark.asyncio
async def test_compliance_service_revoke_user_sessions_helper(db_session, user_factory):
    """UserComplianceService._revoke_user_sessions revokes all user's active sessions."""
    from app.repositories.unit_of_work import UnitOfWork
    from app.services.audit_service import AuditService
    from app.services.user.compliance_service import UserComplianceService

    user = await user_factory(is_active=True)
    s1 = await _create_active_session(db_session, user.id, ip_octet=1)
    s2 = await _create_active_session(db_session, user.id, ip_octet=2)
    await db_session.commit()
    expected_jtis = {s1.jti, s2.jti}

    mock_backend = AsyncMock()
    mock_backend.revoke_session = AsyncMock()

    with patch(
        "app.services.session_cleanup.get_session_backend",
        return_value=mock_backend,
    ):
        uow = UnitOfWork(lambda: db_session)
        uow._session = db_session  # type: ignore[assignment]
        uow._bind_repositories(db_session)

        audit = AuditService()
        service = UserComplianceService(uow, audit)

        revoked_count = await service._revoke_user_sessions(user.id)
        await db_session.commit()

        assert revoked_count == 2

    for session in (s1, s2):
        await db_session.refresh(session)
        assert session.revoked_at is not None

    revoked_jtis = {call.args[0] for call in mock_backend.revoke_session.call_args_list}
    assert revoked_jtis == expected_jtis


@pytest.mark.asyncio
async def test_revoke_user_sessions_noop_when_no_active_sessions(
    db_session, user_factory
):
    """No-op if user has 0 active sessions (e.g. deactivation while logged out)."""
    from app.repositories.unit_of_work import UnitOfWork
    from app.services.audit_service import AuditService
    from app.services.user.compliance_service import UserComplianceService

    user = await user_factory(is_active=True)
    # No sessions created.

    mock_backend = AsyncMock()
    mock_backend.revoke_session = AsyncMock()

    with patch(
        "app.services.session_cleanup.get_session_backend",
        return_value=mock_backend,
    ):
        uow = UnitOfWork(lambda: db_session)
        uow._session = db_session  # type: ignore[assignment]
        uow._bind_repositories(db_session)

        audit = AuditService()
        service = UserComplianceService(uow, audit)

        revoked_count = await service._revoke_user_sessions(user.id)
        await db_session.commit()

        assert revoked_count == 0

    mock_backend.revoke_session.assert_not_called()


@pytest.mark.asyncio
async def test_admin_delete_user_revokes_sessions_via_redis(db_session, user_factory):
    """admin_delete_user → revoke_user_sessions → Redis backend.revoke_session per JTI."""
    from app.repositories.unit_of_work import UnitOfWork
    from app.services.audit_service import AuditService
    from app.services.user.compliance_service import UserComplianceService

    target = await user_factory(is_active=True)
    admin = await user_factory(role="admin", is_active=True)

    session = await _create_active_session(db_session, target.id, ip_octet=1)
    await db_session.commit()
    target_jti = session.jti

    mock_backend = AsyncMock()
    mock_backend.revoke_session = AsyncMock()

    with patch(
        "app.services.session_cleanup.get_session_backend",
        return_value=mock_backend,
    ):
        uow = UnitOfWork(lambda: db_session)
        uow._session = db_session  # type: ignore[assignment]
        uow._bind_repositories(db_session)

        audit = AuditService()
        service = UserComplianceService(uow, audit)

        request = _build_test_request(f"/admin/users/{target.id}")
        result = await service.admin_delete_user(
            user_id=target.id,
            request=request,
            current_user=admin,
        )

    assert result["deleted"] is True

    revoked_jtis = {call.args[0] for call in mock_backend.revoke_session.call_args_list}
    assert target_jti in revoked_jtis, "target session JTI not revoked via Redis"


@pytest.mark.asyncio
async def test_delete_user_data_revokes_sessions_via_redis(db_session, user_factory):
    """delete_user_data (self-delete) → revoke_user_sessions → Redis backend per JTI."""
    from app.repositories.unit_of_work import UnitOfWork
    from app.services.audit_service import AuditService
    from app.services.user.compliance_service import UserComplianceService

    user = await user_factory(is_active=True)

    session = await _create_active_session(db_session, user.id, ip_octet=1)
    await db_session.commit()
    target_jti = session.jti

    mock_backend = AsyncMock()
    mock_backend.revoke_session = AsyncMock()

    with patch(
        "app.services.session_cleanup.get_session_backend",
        return_value=mock_backend,
    ):
        uow = UnitOfWork(lambda: db_session)
        uow._session = db_session  # type: ignore[assignment]
        uow._bind_repositories(db_session)

        audit = AuditService()
        service = UserComplianceService(uow, audit)

        request = _build_test_request("/me")
        await service.delete_user_data(
            user=user,
            request=request,
            confirm=True,
        )

    revoked_jtis = {call.args[0] for call in mock_backend.revoke_session.call_args_list}
    assert target_jti in revoked_jtis, "user session JTI not revoked via Redis"
