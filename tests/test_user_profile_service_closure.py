"""Focused branch tests for the decomposed user profile service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions.domain import EntityNotFound, PermissionDenied
from app.services.user.profile_service import UserProfileService


@pytest.fixture
def profile_service() -> UserProfileService:
    repo = MagicMock()
    repo.db = AsyncMock()
    repo.get = AsyncMock()
    repo.get_by_email = AsyncMock()
    repo.get_auth_by_email = AsyncMock()
    repo.get_auth_by_id = AsyncMock()
    repo.get_orm_for_update_with_relations = AsyncMock()
    repo.list_users = AsyncMock()

    uow = MagicMock()
    uow.users = repo
    uow.commit = AsyncMock()
    uow.flush = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    return UserProfileService(uow, MagicMock(), AsyncMock())


@pytest.mark.asyncio
async def test_profile_lookup_delegates_to_repository(profile_service):
    user_id = uuid4()
    profile_service.repo.get.return_value = "user"
    profile_service.repo.get_by_email.return_value = "email-user"
    profile_service.repo.get_auth_by_email.return_value = "auth-email"
    profile_service.repo.get_auth_by_id.return_value = "auth-id"

    assert await profile_service.get_user_by_id(user_id) == "user"
    assert await profile_service.get_user_by_email("user@example.com") == "email-user"
    assert (
        await profile_service.get_auth_user_by_email("user@example.com") == "auth-email"
    )
    assert await profile_service.get_auth_user_by_id(user_id) == "auth-id"


@pytest.mark.asyncio
async def test_update_user_profile_raises_when_orm_user_is_missing(profile_service):
    profile_service.repo.get_orm_for_update_with_relations.return_value = None
    user_id = uuid4()
    data = MagicMock()
    data.model_dump.return_value = {}

    with pytest.raises(EntityNotFound):
        await profile_service.update_user_profile(user_id, data, MagicMock())


@pytest.mark.asyncio
async def test_update_user_profile_validates_and_normalizes_email(profile_service):
    user_id = uuid4()
    db_user = MagicMock()
    updated_user = SimpleNamespace(id=user_id)
    profile_service.repo.get_orm_for_update_with_relations.return_value = db_user
    profile_service.repo._to_dto.return_value = updated_user
    data = MagicMock()
    data.model_dump.return_value = {"email": "  USER@Example.COM  "}
    validate_email = AsyncMock(return_value="user@example.com")

    with (
        patch("app.services.user.logic.validate_user_email", validate_email),
        patch(
            "app.services.user.profile_service.update_user_attributes"
        ) as update_attributes,
        patch(
            "app.services.user.profile_service.attach_pending_email",
            new=AsyncMock(return_value=updated_user),
        ),
    ):
        result = await profile_service.update_user_profile(
            SimpleNamespace(id=user_id), data, MagicMock()
        )

    assert result is updated_user
    validate_email.assert_awaited_once_with(
        profile_service.repo, "  USER@Example.COM  ", exclude_user_id=user_id
    )
    update_attributes.assert_called_once_with(db_user, {"email": "user@example.com"})


@pytest.mark.asyncio
async def test_get_users_normalizes_whitespace_only_full_name(profile_service):
    profile_service.repo.list_users.return_value = []
    filters = SimpleNamespace(search=None, full_name="   ")

    result = await profile_service.get_users(MagicMock(), None, filters)

    assert result == []
    assert filters.full_name is None
    profile_service.repo.list_users.assert_awaited_once_with(filters=filters)


@pytest.mark.asyncio
async def test_get_users_strips_non_empty_full_name(profile_service):
    profile_service.repo.list_users.return_value = []
    filters = SimpleNamespace(search=None, full_name="  Ada Lovelace  ")

    await profile_service.get_users(MagicMock(), None, filters)

    assert filters.full_name == "Ada Lovelace"


@pytest.mark.asyncio
async def test_get_users_denies_unfiltered_non_admin_requests(profile_service):
    with pytest.raises(PermissionDenied):
        await profile_service.get_users(
            MagicMock(),
            SimpleNamespace(role="student"),
            SimpleNamespace(search=None, full_name=None),
        )


@pytest.mark.asyncio
async def test_get_users_allows_empty_name_for_admin(profile_service):
    profile_service.repo.list_users.return_value = []
    filters = SimpleNamespace(search=None, full_name=None)

    assert (
        await profile_service.get_users(
            MagicMock(), SimpleNamespace(role="admin"), filters
        )
        == []
    )
    profile_service.repo.list_users.assert_awaited_once_with(filters=filters)


@pytest.mark.asyncio
async def test_admin_update_user_normalizes_email(profile_service, monkeypatch):
    target_id = uuid4()
    db_user = MagicMock()
    updated_user = SimpleNamespace(id=target_id)
    profile_service.repo.get_orm_for_update_with_relations.return_value = db_user
    profile_service.repo._to_dto.return_value = updated_user
    data = MagicMock()
    data.model_dump.return_value = {"email": "  USER@Example.COM  "}
    admin = SimpleNamespace(role="admin")

    update_attributes = MagicMock()
    monkeypatch.setattr(
        "app.services.user.profile_service.update_user_attributes", update_attributes
    )

    result = await profile_service.admin_update_user(
        target_id, data, MagicMock(), admin
    )

    assert result is updated_user
    update_attributes.assert_called_once_with(db_user, {"email": "user@example.com"})
    profile_service.repo.add.assert_called_once_with(db_user)
    profile_service.uow.flush.assert_awaited_once()
    profile_service.uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_update_user_raises_when_orm_user_is_missing(profile_service):
    profile_service.repo.get_orm_for_update_with_relations.return_value = None
    data = MagicMock()
    data.model_dump.return_value = {}

    with pytest.raises(EntityNotFound):
        await profile_service.admin_update_user(
            uuid4(), data, MagicMock(), SimpleNamespace(role="admin")
        )


@pytest.mark.asyncio
async def test_admin_update_user_denies_non_admin(profile_service):
    with pytest.raises(PermissionDenied):
        await profile_service.admin_update_user(
            uuid4(), MagicMock(), MagicMock(), SimpleNamespace(role="student")
        )


@pytest.mark.asyncio
async def test_admin_update_user_resets_mfa_and_notifies_target(profile_service):
    user_id = uuid4()
    db_user = MagicMock()
    updated_user = SimpleNamespace(id=user_id)
    profile_service.repo.get_orm_for_update_with_relations.return_value = db_user
    profile_service.repo._to_dto.return_value = updated_user
    data = MagicMock()
    data.model_dump.return_value = {"reset_mfa": True}
    request = MagicMock()

    with (
        patch(
            "app.services.user.profile_service.mfa.reset_user_mfa",
            new=AsyncMock(),
        ) as reset_mfa,
        patch("app.services.user.profile_service.resolve_locale", return_value="en"),
        patch(
            "app.services.user.profile_service.translate",
            side_effect=lambda key, locale: key,
        ),
    ):
        result = await profile_service.admin_update_user(
            str(user_id), data, request, SimpleNamespace(role="admin")
        )

    assert result is updated_user
    reset_mfa.assert_awaited_once_with(profile_service.repo.db, user_id=str(user_id))
    profile_service.audit.log.assert_any_call(
        "users.mfa.reset", request, user_id=user_id, reason="admin_reset"
    )
    profile_service.notifications.send_security_notification.assert_awaited_once_with(
        user_ids=[user_id],
        title="notifications.mfa.reset.title",
        body="notifications.mfa.reset.body",
    )
