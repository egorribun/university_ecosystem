"""Account deletion loads persisted relations in a fresh request identity map."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import select

from app import models
from app.auth.security import get_password_hash
from app.core.exceptions.domain import BusinessRuleViolation, EntityNotFound
from app.repositories.unit_of_work import uow_from_session
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.user.compliance_service import UserComplianceService


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["admin", "self"])
async def test_delete_account_anonymizes_existing_relations(
    operation, user_factory, db_session
):
    target = await user_factory(
        full_name="Deletion Target",
        about="Private profile text",
        timezone="Europe/London",
    )
    target.education_path = models.EducationPath(institute="Private institute")
    await db_session.commit()
    target_id = target.id
    # A new request does not retain the seed's eagerly populated ORM objects.
    db_session.expunge_all()
    service = UserComplianceService(uow_from_session(db_session), AuditService())
    request = Request(
        {"type": "http", "method": "DELETE", "path": "/users", "headers": []}
    )
    if operation == "admin":
        admin = await user_factory(role="admin")
        result = await service.admin_delete_user(target_id, request, admin)
        assert result["deleted"] is True
    else:
        # Authentication may already have materialized noload attributes in
        # this request; deletion must refresh these too.
        loaded = await db_session.get(models.User, target_id)
        assert loaded.profile is None
        result = await service.delete_user_data(
            SimpleNamespace(id=target_id), request, confirm=True
        )
        assert result.deleted is True

    db_session.expunge_all()
    account = await db_session.get(models.User, target_id)
    profile = await db_session.scalar(
        select(models.UserProfile).where(models.UserProfile.user_id == target_id)
    )
    preferences = await db_session.get(models.UserPreferences, target_id)
    assert account.is_active is False
    assert account.email == f"deleted+{target_id}@deleted.example.com"
    assert profile.full_name == "Deleted User"
    assert profile.about is None
    assert profile.status == "deleted"
    assert preferences.timezone is None
    assert await db_session.get(models.EducationPath, target_id) is None
    assert await db_session.get(models.SpotifyIntegration, target_id) is None


@pytest.mark.asyncio
async def test_admin_delete_route_succeeds_for_separately_loaded_persisted_user(
    root_client, user_factory, db_session
):
    password = "RegisteredTarget123!"  # pragma: allowlist secret
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    admin_email = admin.email
    target = await user_factory(full_name="Registered Target")
    target_id = target.id
    db_session.expunge_all()
    login = await root_client.post(
        "/api/v1/auth/login", data={"username": admin_email, "password": password}
    )
    assert login.status_code == 200

    response = await root_client.delete(f"/api/v1/users/{target_id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "user_id": str(target_id)}


@pytest.mark.asyncio
async def test_anonymization_loader_returns_none_for_missing_account(db_session):
    assert await UserRepository(db_session).get_orm_for_anonymization(uuid4()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("confirm", "error"), [(False, BusinessRuleViolation), (True, EntityNotFound)]
)
async def test_self_deletion_rejects_unconfirmed_or_missing_account(
    db_session, confirm, error
):
    service = UserComplianceService(uow_from_session(db_session), AuditService())
    request = Request(
        {"type": "http", "method": "POST", "path": "/users/me/delete", "headers": []}
    )
    with pytest.raises(error):
        await service.delete_user_data(
            SimpleNamespace(id=uuid4()), request, confirm=confirm
        )
