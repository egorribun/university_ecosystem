"""Nullable admin identity inputs are compatible no-ops, not database clears."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api import users as api
from app.models.enums import UserRole
from app.schemas.users import UserAdminUpdate, UserOut
from app.services.user.profile_service import UserProfileService
from tests.conftest import call_injected


@pytest.mark.parametrize("field", ["email", "role"])
def test_admin_update_accepts_published_null_identity(field: str) -> None:
    update = UserAdminUpdate.model_validate({field: None})

    assert update.model_dump(exclude_unset=True) == {field: None}


def test_admin_update_omitted_identity_fields_remain_unchanged() -> None:
    update = UserAdminUpdate(full_name="Updated Name")

    assert update.model_dump(exclude_unset=True) == {"full_name": "Updated Name"}


def test_admin_update_accepts_valid_email_and_role() -> None:
    update = UserAdminUpdate.model_validate(
        {"email": "updated@example.com", "role": "teacher"}
    )

    assert update.email == "updated@example.com"
    assert update.role is UserRole.TEACHER


def test_admin_update_can_still_clear_nullable_fields() -> None:
    update = UserAdminUpdate(full_name=None, group_id=None)

    assert update.model_dump(exclude_unset=True) == {
        "full_name": None,
        "group_id": None,
    }


def test_admin_update_schema_preserves_nullable_optional_identity() -> None:
    schema = UserAdminUpdate.model_json_schema()
    properties = schema["properties"]

    for field in ("email", "role", "full_name", "group_id"):
        assert {"type": "null"} in properties[field]["anyOf"]
        assert field not in schema.get("required", [])
    assert {"format": "email", "type": "string"} in properties["email"]["anyOf"]
    assert {"$ref": "#/$defs/UserRole"} in properties["role"]["anyOf"]


@pytest.mark.asyncio
@pytest.mark.parametrize("via_endpoint", [False, True])
@pytest.mark.parametrize(
    ("payload", "expected_email", "expected_role", "expected_name"),
    [
        ({}, "original@example.com", UserRole.STUDENT, "Original Name"),
        (
            {"email": None, "role": None},
            "original@example.com",
            UserRole.STUDENT,
            "Original Name",
        ),
        (
            {"email": None, "role": "teacher", "full_name": "Updated Name"},
            "original@example.com",
            UserRole.TEACHER,
            "Updated Name",
        ),
        (
            {"email": "UPDATED@example.com", "role": None, "full_name": None},
            "updated@example.com",
            UserRole.STUDENT,
            None,
        ),
    ],
)
async def test_admin_null_identity_preserves_mixed_updates(
    monkeypatch, via_endpoint, payload, expected_email, expected_role, expected_name
) -> None:
    """Exercise real attribute mutation through the service and endpoint adapter."""
    target_id = uuid4()
    old_group_id = uuid4()
    db_user = SimpleNamespace(
        id=target_id,
        email="original@example.com",
        role=UserRole.STUDENT,
        group_id=old_group_id,
        profile=SimpleNamespace(full_name="Original Name"),
    )
    repo = MagicMock()
    repo.get_orm_for_update_with_relations = AsyncMock(return_value=db_user)
    repo._to_dto.side_effect = lambda user: UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        full_name=user.profile.full_name,
        group_id=user.group_id,
        is_active=True,
    )
    uow = MagicMock()
    uow.users = repo
    uow.flush = AsyncMock()
    uow.commit = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    service = UserProfileService(uow, MagicMock(), AsyncMock())
    sync_group = AsyncMock()
    monkeypatch.setattr(
        "app.services.user.profile_service.sync_group_participant", sync_group
    )
    # group_id null must still clear membership in every identity scenario.
    update = UserAdminUpdate.model_validate({**payload, "group_id": None})
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN)
    request = MagicMock()

    if via_endpoint:
        result = await call_injected(
            api.update_user_admin,
            target_id,
            update,
            request,
            user=admin,
            provides={"UserProfileService": service},
        )
    else:
        result = await service.admin_update_user(target_id, update, request, admin)

    assert db_user.email == result.email == expected_email
    assert db_user.role == result.role == expected_role
    assert db_user.profile.full_name == result.full_name == expected_name
    assert db_user.group_id is result.group_id is None
    uow.flush.assert_awaited_once()
    uow.commit.assert_awaited_once()
    sync_group.assert_awaited_once_with(target_id, old_group_id, None)
