"""Closure tests for user facade delegation and nested user-data logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions.domain import EntityAlreadyExists
from app.services.user.logic import (
    anonymize_user_data,
    update_user_attributes,
    validate_user_email,
)
from app.services.user_service import UserService


def _facade() -> UserService:
    uow = MagicMock()
    uow.users = MagicMock()
    service = UserService(uow, MagicMock(), MagicMock())
    service.profile_service = MagicMock()
    service.profile_service.get_user_by_id = AsyncMock(return_value="by-id")
    service.profile_service.get_user_by_email = AsyncMock(return_value="by-email")
    service.profile_service.get_auth_user_by_email = AsyncMock(
        return_value="auth-email"
    )
    service.profile_service.get_auth_user_by_id = AsyncMock(return_value="auth-id")
    service.compliance_service.delete_user_data = AsyncMock(return_value="deleted")
    return service


@pytest.mark.asyncio
async def test_user_service_delegates_remaining_profile_and_compliance_calls():
    service = _facade()
    user_id = uuid4()
    request = MagicMock()

    assert await service.get_user_by_id(user_id) == "by-id"
    assert await service.get_user_by_email("user@example.com") == "by-email"
    assert await service.get_auth_user_by_email("user@example.com") == "auth-email"
    assert await service.get_auth_user_by_id(user_id) == "auth-id"
    assert await service.delete_user_data("user", request, confirm=True) == "deleted"


def test_update_user_attributes_creates_all_nested_relations_and_handles_direct_fields():
    user = SimpleNamespace(
        id=uuid4(), preferences=None, profile=None, education_path=None
    )

    update_user_attributes(
        user,
        {
            "preferences": {"dnd_enabled": True},
            "timezone": "Europe/Moscow",
            "full_name": "New Name",
            "profile": {"about": "Bio"},
            "institute": "MIT",
            "is_active": False,
        },
    )

    assert user.preferences.dnd_enabled is True
    assert user.preferences.timezone == "Europe/Moscow"
    assert user.profile.full_name == "New Name"
    assert user.profile.about == "Bio"
    assert user.education_path.institute == "MIT"
    assert user.is_active is False


def test_update_user_attributes_creates_missing_scalar_preference_and_profile():
    preferences_user = SimpleNamespace(
        id=uuid4(), preferences=None, profile=object(), education_path=None
    )
    update_user_attributes(preferences_user, {"timezone": "UTC"})
    assert preferences_user.preferences.timezone == "UTC"

    profile_user = SimpleNamespace(
        id=uuid4(), preferences=None, profile=None, education_path=None
    )
    update_user_attributes(profile_user, {"profile": {"about": "Bio"}})
    assert profile_user.profile.about == "Bio"


def test_update_user_attributes_reuses_existing_nested_relations():
    user = SimpleNamespace(
        id=uuid4(),
        preferences=SimpleNamespace(timezone="UTC"),
        profile=SimpleNamespace(full_name="Old"),
        education_path=SimpleNamespace(course=1),
    )

    update_user_attributes(
        user,
        {
            "preferences": {"dnd_enabled": True},
            "full_name": "New",
            "course": 2,
        },
    )

    assert user.preferences.timezone == "UTC"
    assert user.preferences.dnd_enabled is True
    assert user.profile.full_name == "New"
    assert user.education_path.course == 2


@pytest.mark.asyncio
async def test_anonymize_user_data_cleans_existing_relations_and_files():
    user = SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        hashed_password="hash",
        is_active=True,
        mfa_required=True,
        mfa_default_method="totp",
        mfa_last_verified_at=object(),
        profile=SimpleNamespace(
            avatar_url="/avatar.jpg",
            cover_url="/cover.jpg",
            full_name="User",
            about="About",
            telegram="@user",
            achievements=["A"],
            position="Student",
            department="CS",
            status="active",
        ),
        education_path=SimpleNamespace(
            institute="MIT",
            course="3",
            education_level="bachelor",
            track="AI",
            program="CS",
            record_book_number="42",
        ),
        preferences=SimpleNamespace(dnd_enabled=True, timezone="UTC"),
        spotify=object(),
    )

    with patch("app.services.user.logic.delete_static_file", new=AsyncMock()) as delete:
        anonymized = await anonymize_user_data(user)

    assert anonymized == f"deleted+{user.id}@deleted.example.com"
    assert delete.await_count == 2
    assert user.profile.status == "deleted"
    assert user.education_path is None
    assert user.preferences.dnd_enabled is False


@pytest.mark.asyncio
async def test_anonymize_user_data_creates_profile_when_missing():
    user = SimpleNamespace(
        id=uuid4(),
        profile=None,
        education_path=None,
        preferences=None,
        spotify=None,
    )

    result = await anonymize_user_data(user)

    assert result.startswith("deleted+")
    assert user.profile.status == "deleted"


@pytest.mark.asyncio
async def test_anonymize_user_data_skips_falsy_placeholder_profile():
    class FalsyProfile(SimpleNamespace):
        def __bool__(self):
            return False

    user = SimpleNamespace(
        id=uuid4(),
        profile=None,
        education_path=None,
        preferences=None,
        spotify=None,
    )

    with patch(
        "app.services.user.logic.models.UserProfile",
        return_value=FalsyProfile(status="deleted"),
    ):
        result = await anonymize_user_data(user)

    assert result.startswith("deleted+")
    assert user.profile.status == "deleted"


@pytest.mark.asyncio
async def test_validate_user_email_normalizes_and_checks_uniqueness():
    repo = MagicMock()
    repo.check_email_exists = AsyncMock(return_value=False)

    assert await validate_user_email(repo, "  USER@Example.COM ") == "user@example.com"
    repo.check_email_exists.assert_awaited_once_with(
        "user@example.com", exclude_user_id=None
    )

    repo.check_email_exists.reset_mock()
    repo.check_email_exists.return_value = True
    with pytest.raises(EntityAlreadyExists):
        await validate_user_email(repo, "duplicate@example.com", exclude_user_id="user")


@pytest.mark.asyncio
async def test_anonymize_user_data_handles_profile_without_media_urls():
    user = SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        hashed_password="hash",
        is_active=True,
        mfa_required=True,
        mfa_default_method=None,
        mfa_last_verified_at=None,
        profile=SimpleNamespace(
            avatar_url=None,
            cover_url=None,
            full_name="User",
            status="active",
        ),
        education_path=None,
        preferences=None,
        spotify=None,
    )

    with patch("app.services.user.logic.delete_static_file", new=AsyncMock()) as delete:
        await anonymize_user_data(user)

    delete.assert_not_awaited()
