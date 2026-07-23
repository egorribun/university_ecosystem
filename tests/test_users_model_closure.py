from __future__ import annotations

import uuid

from app.models.enums import UserRole
from app.models.users import (
    EducationPath,
    InviteCode,
    User,
    UserPreferences,
    UserProfile,
    UserStats,
)


def test_user_constructor_materializes_nested_dicts_and_aliases():
    user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        hashed_password="hash",  # pragma: allowlist secret
        role=UserRole.STUDENT,
        preferences={"timezone": "Europe/Moscow"},
        profile_detail={"full_name": "User"},
        education_path={"program": "Computer Science"},
        _allow_system_managed_assignment=True,
    )
    assert isinstance(user.preferences, UserPreferences)
    assert isinstance(user.profile, UserProfile)
    assert isinstance(user.education_path, EducationPath)
    assert user.profile.full_name == "User"
    assert user.education_path.program == "Computer Science"


def test_user_constructor_accepts_nested_objects_and_factory():
    preferences = UserPreferences(timezone="UTC")
    profile = UserProfile(full_name="Object")
    education = EducationPath(program="Physics")
    user = User(
        email="object@example.com",
        hashed_password="hash",  # pragma: allowlist secret
        preferences=preferences,
        profile=profile,
        education_path=education,
    )
    assert user.preferences is preferences
    assert user.profile is profile
    assert user.education_path is education

    created = User.create(
        email="factory@example.com",
        hashed_password="hash",  # pragma: allowlist secret
        role=UserRole.ADMIN,
        is_active=False,
        preferences={"dnd_enabled": True},
    )
    assert created.role == UserRole.ADMIN
    assert created.is_active is False
    assert created.preferences.dnd_enabled is True


def test_user_spotify_properties_create_and_update_integration():
    user = User(
        email="spotify@example.com",
        hashed_password="hash",  # pragma: allowlist secret
    )
    assert user.spotify_is_connected is False
    assert user.spotify_display_name is None

    user.spotify_is_connected = True
    user.spotify_display_name = "Artist"
    assert user.spotify_is_connected is True
    assert user.spotify_display_name == "Artist"
    user.spotify_is_connected = False
    assert user.spotify_is_connected is False

    second = User(
        email="spotify2@example.com",
        hashed_password="hash",  # pragma: allowlist secret
    )
    second.spotify_display_name = "Second Artist"
    assert second.spotify_display_name == "Second Artist"


def test_user_and_related_repr_are_pii_safe_and_stable():
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="private@example.com",
        hashed_password="hash",  # pragma: allowlist secret
    )
    assert "private@example.com" not in repr(user)
    assert str(user_id) in repr(user)

    prefs = UserPreferences(user_id=user_id, dnd_enabled=True)
    profile = UserProfile(user_id=user_id)
    education = EducationPath(user_id=user_id, program="Program")
    invite = InviteCode(id=user_id, code="INVITE", role="student", is_used=True)
    stats = UserStats(user_id=user_id)
    assert "dnd=True" in repr(prefs)
    assert str(user_id) in repr(profile)
    assert "Program" in repr(education)
    assert "INVITE" in repr(invite)
    assert str(user_id) in repr(stats)


def test_system_managed_pop_argument_is_removed_from_other_models():
    invite = InviteCode(
        code="CODE", role="student", _allow_system_managed_assignment=True
    )
    stats = UserStats(user_id=uuid.uuid4(), _allow_system_managed_assignment=True)
    assert invite.code == "CODE"
    assert stats.user_id is not None
