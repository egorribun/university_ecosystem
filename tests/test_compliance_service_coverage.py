"""Behavior and failure-path tests for user compliance services.

AsyncMock repo + fake-UoW harness (mirrors tests/test_audit_service.py style)
targeting the previously-uncovered branches: register_user invite validation
(L249-264) + generic-exception rollback wrap (L291-301), create_user permission
/ invite branches (L312-320) and the IntegrityError email-vs-other split
(L336-341), plus export/delete guard clauses (L103, 207, 213).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.models.enums import UserRole
from app.schemas import schemas
from app.services.user import compliance_service as compliance_module
from app.services.user.compliance_service import UserComplianceService


class _FakeUoW:
    """Minimal async-context UoW double exposing the repo + commit/rollback."""

    def __init__(self, repo: AsyncMock) -> None:
        self.users = repo
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def __aenter__(self) -> _FakeUoW:
        return self

    async def __aexit__(self, *exc) -> None:
        return None


@pytest.fixture
def repo() -> AsyncMock:
    mock = AsyncMock()
    mock.db = AsyncMock()
    return mock


@pytest.fixture
def svc(repo: AsyncMock) -> UserComplianceService:
    return UserComplianceService(_FakeUoW(repo), audit=MagicMock())  # type: ignore[arg-type]


@pytest.fixture
def fast_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compliance_module, "get_password_hash", AsyncMock(return_value="hashed")
    )
    monkeypatch.setattr(
        compliance_module.settings, "password_hibp_check_enabled", False
    )


def _user_create(**overrides) -> schemas.UserCreate:
    defaults = {
        "email": "New.User@Example.com",
        "password": "Password-123!",  # pragma: allowlist secret
        "full_name": "New User",
    }
    defaults.update(overrides)
    return schemas.UserCreate(**defaults)


def _request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


# ---------------------------------------------------------------------------
# export_user_data / delete_user_data guard clauses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_user_data_missing_user_raises(svc, repo):
    repo.get.return_value = None
    user = MagicMock(id=uuid.uuid4())
    with pytest.raises(EntityNotFound):
        await svc.export_user_data(user, request=_request())


@pytest.mark.asyncio
async def test_delete_user_data_requires_confirmation(svc):
    user = MagicMock(id=uuid.uuid4())
    with pytest.raises(BusinessRuleViolation):
        await svc.delete_user_data(user, request=_request(), confirm=False)


@pytest.mark.asyncio
async def test_delete_user_data_missing_user_raises(svc, repo):
    repo._get_orm.return_value = None
    user = MagicMock(id=uuid.uuid4())
    with pytest.raises(EntityNotFound):
        await svc.delete_user_data(user, request=_request(), confirm=True)


# ---------------------------------------------------------------------------
# register_user — invite-code validation (L249-264)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code_obj",
    [
        None,
        MagicMock(role="student", is_active=True, is_used=False),  # wrong role
        MagicMock(role="teacher", is_active=False, is_used=False),  # inactive
        MagicMock(role="teacher", is_active=True, is_used=True),  # already used
    ],
)
async def test_register_user_rejects_invalid_invite(svc, repo, fast_hash, code_obj):
    repo.check_email_exists.return_value = False
    repo.get_invite_code.return_value = code_obj

    user_in = _user_create(role=UserRole.TEACHER, invite_code="CODE-1")
    with pytest.raises(BusinessRuleViolation):
        await svc.register_user(user_in)
    repo.create_with_invite.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_user_duplicate_email_raises(svc, repo, fast_hash):
    repo.check_email_exists.return_value = True
    with pytest.raises(EntityAlreadyExists):
        await svc.register_user(_user_create())


@pytest.mark.asyncio
async def test_register_user_success_with_valid_invite(svc, repo, fast_hash):
    repo.check_email_exists.return_value = False
    valid_code = MagicMock(role="teacher", is_active=True, is_used=False)
    repo.get_invite_code.return_value = valid_code
    created = MagicMock()
    repo.create_with_invite.return_value = created

    user_in = _user_create(role=UserRole.TEACHER, invite_code="CODE-OK")
    result = await svc.register_user(user_in)

    assert result is created
    repo.create_with_invite.assert_awaited_once()
    call_args = repo.create_with_invite.await_args.args
    user_data = call_args[0]
    # Email normalized, password replaced by hash, role threaded through.
    assert user_data["email"] == "new.user@example.com"
    assert user_data["hashed_password"] == "hashed"  # pragma: allowlist secret
    assert user_data["role"] == "teacher"
    assert user_data["mfa_required"] is False
    assert user_data["mfa_default_method"] is None
    assert "email_verified_at" not in user_data
    assert "password" not in user_data
    assert call_args[1] is valid_code


@pytest.mark.asyncio
async def test_register_user_wraps_generic_failure(svc, repo, fast_hash):
    repo.check_email_exists.return_value = False
    repo.create_with_invite.side_effect = RuntimeError("db down")

    with pytest.raises(BusinessRuleViolation):
        await svc.register_user(_user_create())
    svc.uow.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# create_user — admin guard + invite branches + IntegrityError split
# ---------------------------------------------------------------------------


def _admin() -> MagicMock:
    admin = MagicMock()
    admin.role = "admin"
    return admin


@pytest.mark.asyncio
async def test_create_user_requires_admin(svc, fast_hash):
    student = MagicMock()
    student.role = "student"
    with pytest.raises(PermissionDenied):
        await svc.create_user(_user_create(), request=_request(), current_user=student)


@pytest.mark.asyncio
async def test_create_user_unknown_invite_code_rejected(svc, repo, fast_hash):
    repo.get_invite_code.return_value = None
    data = _user_create(invite_code="MISSING")
    with pytest.raises(BusinessRuleViolation):
        await svc.create_user(data, request=_request(), current_user=_admin())


@pytest.mark.asyncio
async def test_create_user_teacher_requires_invite(svc, repo, fast_hash):
    data = _user_create(role=UserRole.TEACHER)
    with pytest.raises(BusinessRuleViolation):
        await svc.create_user(data, request=_request(), current_user=_admin())


@pytest.mark.asyncio
async def test_create_user_success(svc, repo, fast_hash):
    created = MagicMock()
    repo.create.return_value = created
    result = await svc.create_user(
        _user_create(), request=_request(), current_user=_admin()
    )
    assert result is created
    repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_integrity_error_on_email(svc, repo, fast_hash):
    repo.create.side_effect = IntegrityError(
        "INSERT", {}, Exception("duplicate key value violates users_email_key")
    )
    with pytest.raises(EntityAlreadyExists):
        await svc.create_user(_user_create(), request=_request(), current_user=_admin())
    svc.uow.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_integrity_error_other_constraint(svc, repo, fast_hash):
    repo.create.side_effect = IntegrityError(
        "INSERT", {}, Exception("foreign key constraint groups_fk failed")
    )
    with pytest.raises(BusinessRuleViolation):
        await svc.create_user(_user_create(), request=_request(), current_user=_admin())
    svc.uow.rollback.assert_awaited_once()
