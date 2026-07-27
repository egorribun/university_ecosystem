"""Closure tests for successful compliance-service workflows."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

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
