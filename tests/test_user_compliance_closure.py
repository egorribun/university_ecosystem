"""Closure tests for successful compliance-service workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityNotFound,
    PermissionDenied,
)
from app.schemas import schemas
from app.services.user.compliance_service import UserComplianceService


class _Uow:
    def __init__(self, repo):
        self.users = repo
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def _repo():
    repo = AsyncMock()
    repo.db = AsyncMock()
    return repo


def _request():
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


def _user_create(**overrides):
    values = {
        "email": "New.User@Example.com",
        "password": "Password-123!",  # pragma: allowlist secret
        "full_name": "New User",
    }
    values.update(overrides)
    return schemas.UserCreate(**values)


@pytest.mark.asyncio
async def test_delete_user_data_success_anonymizes_revokes_logs_and_refreshes():
    repo = _repo()
    user_id = uuid4()
    orm_user = SimpleNamespace(id=user_id)
    updated = SimpleNamespace(email=f"deleted+{user_id}@deleted.example.com")
    repo._get_orm.return_value = orm_user
    repo.get.return_value = updated
    service = UserComplianceService(_Uow(repo), audit=MagicMock())

    with (
        patch(
            "app.services.user.compliance_service.anonymize_user_data", new=AsyncMock()
        ) as anonymize,
        patch.object(service, "_revoke_user_sessions", new=AsyncMock()) as revoke,
        patch(
            "app.services.user.compliance_service.log_data_access", new=AsyncMock()
        ) as log,
    ):
        result = await service.delete_user_data(
            SimpleNamespace(id=user_id), _request(), confirm=True
        )

    assert result.deleted is True
    assert result.anonymized_email == updated.email
    anonymize.assert_awaited_once_with(orm_user)
    revoke.assert_awaited_once_with(user_id)
    repo.delete_sensitive_data.assert_awaited_once_with(user_id)
    log.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_user_runs_hibp_check_when_enabled():
    repo = _repo()
    repo.check_email_exists.return_value = False
    repo.create_with_invite.return_value = SimpleNamespace(id=uuid4())
    service = UserComplianceService(_Uow(repo), audit=MagicMock())

    with (
        patch.object(service, "_revoke_user_sessions", new=AsyncMock()),
        patch(
            "app.services.user.compliance_service.settings.password_hibp_check_enabled",
            True,
        ),
        patch(
            "app.services.user.compliance_service.validate_password_hibp",
            new=AsyncMock(),
        ) as hibp,
        patch(
            "app.services.user.compliance_service.get_password_hash",
            new=AsyncMock(return_value="hashed"),
        ),
    ):
        await service.register_user(_user_create())

    hibp.assert_awaited_once_with("Password-123!")


@pytest.mark.asyncio
async def test_create_user_accepts_valid_invite_and_runs_hibp_check():
    repo = _repo()
    repo.get_invite_code.return_value = SimpleNamespace()
    repo.create.return_value = SimpleNamespace(id=uuid4())
    service = UserComplianceService(_Uow(repo), audit=MagicMock())
    admin = SimpleNamespace(role="admin")

    with (
        patch(
            "app.services.user.compliance_service.settings.password_hibp_check_enabled",
            True,
        ),
        patch(
            "app.services.user.compliance_service.validate_password_hibp",
            new=AsyncMock(),
        ) as hibp,
        patch(
            "app.services.user.compliance_service.get_password_hash",
            new=AsyncMock(return_value="hashed"),
        ),
    ):
        await service.create_user(_user_create(invite_code="INVITE"), _request(), admin)

    repo.get_invite_code.assert_awaited_once_with("INVITE")
    hibp.assert_awaited_once_with("Password-123!")


@pytest.mark.asyncio
async def test_export_user_data_serializes_all_sections_and_audits_access():
    repo = _repo()
    user_id = uuid4()
    now = datetime.now(UTC)
    session_id = uuid4()
    notification_id = uuid4()
    challenge_id = uuid4()
    enrollment_id = uuid4()
    access_log_id = uuid4()
    db_user = SimpleNamespace(
        model_dump=lambda: {"id": user_id, "email": "student@example.com"},
        mfa_challenges=[
            SimpleNamespace(
                id=challenge_id,
                challenge_type="totp",
                expires_at=now,
                consumed_at=None,
                created_at=now,
            )
        ],
        totp_enrollments=[
            SimpleNamespace(
                id=enrollment_id,
                label="phone",
                is_active=True,
                confirmed_at=now,
                revoked_at=None,
                created_at=now,
            )
        ],
    )
    repo.get.return_value = db_user
    repo.get_user_sessions.return_value = [
        SimpleNamespace(
            id=session_id,
            created_at=now,
            expires_at=now,
            revoked_at=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
            last_seen_at=now,
            mfa_completed_at=now,
        )
    ]
    repo.get_user_notifications.return_value = [
        SimpleNamespace(
            id=notification_id,
            title="Notice",
            body="Body",
            type="info",
            created_at=now,
            read_at=None,
        )
    ]
    repo.get_user_access_logs.return_value = [
        SimpleNamespace(
            id=access_log_id,
            resource_type="profile",
            resource_id=str(user_id),
            action="read",
            created_at=now,
            ip_address="127.0.0.1",
            user_agent="pytest",
            context={"source": "test"},
        )
    ]
    service = UserComplianceService(_Uow(repo), audit=MagicMock())

    with patch(
        "app.services.user.compliance_service.log_data_access", new=AsyncMock()
    ) as log:
        result = await service.export_user_data(SimpleNamespace(id=user_id), _request())

    assert result.profile["email"] == "student@example.com"
    assert result.sessions[0]["id"] == session_id
    assert result.notifications[0]["id"] == notification_id
    assert result.mfa_challenges[0]["type"] == "totp"
    assert result.mfa_enrollments[0]["label"] == "phone"
    assert result.access_logs[0]["resource_type"] == "profile"
    repo.get_user_access_logs.assert_awaited_once_with(user_id, limit=2000)
    log.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_delete_user_rejects_non_admin():
    repo = _repo()
    service = UserComplianceService(_Uow(repo), audit=MagicMock())

    with pytest.raises(PermissionDenied):
        await service.admin_delete_user(
            uuid4(), _request(), SimpleNamespace(id=uuid4(), role="student")
        )


@pytest.mark.asyncio
async def test_admin_delete_user_rejects_missing_target():
    repo = _repo()
    repo._get_orm.return_value = None
    service = UserComplianceService(_Uow(repo), audit=MagicMock())

    with pytest.raises(EntityNotFound):
        await service.admin_delete_user(
            uuid4(), _request(), SimpleNamespace(id=uuid4(), role="admin")
        )


@pytest.mark.asyncio
async def test_admin_delete_user_rejects_self_delete():
    repo = _repo()
    user_id = uuid4()
    repo._get_orm.return_value = SimpleNamespace(id=user_id)
    service = UserComplianceService(_Uow(repo), audit=MagicMock())

    with pytest.raises(BusinessRuleViolation):
        await service.admin_delete_user(
            user_id, _request(), SimpleNamespace(id=user_id, role="admin")
        )
