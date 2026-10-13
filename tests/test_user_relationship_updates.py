"""Relationship-creation tests for app/services/user/logic.py
update_user_attributes create-when-None branches (36/49/70/72 + profile-dict)
and anonymize_user_data's cover_url cleanup branch — the noload-create arms
the existing test_services_mock.py tests skip (they pass users with
pre-populated relations).

Pure in-memory: build a User stub whose profile/preferences/education_path are
all None and assert update_user_attributes creates each child + the else-setattr
fallback. delete_static_file is patched (no real I/O).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.models as models
import app.services.user.logic as logic_module
from app.core.constants import ANONYMIZED_USER_CREDENTIAL
from app.services.user.logic import anonymize_user_data, update_user_attributes
from tests.helpers.synthetic_credentials import make_test_marker


def _bare_user() -> SimpleNamespace:
    # All nested relations None → exercises the "if not user.X: create" arms.
    return SimpleNamespace(
        id=uuid.uuid4(),
        preferences=None,
        profile=None,
        education_path=None,
        email="u@example.com",
        full_name=None,
    )


def test_update_attributes_creates_all_nested_children() -> None:
    user = _bare_user()
    update_user_attributes(
        user,  # type: ignore[arg-type]
        {
            "preferences": {"timezone": "UTC"},  # preferences-dict create (36)
            "dnd_enabled": True,  # preferences_fields (already-created reuse)
            "full_name": "Ann",  # profile_fields create (49)
            "profile": {"about": "hi"},  # profile-dict branch
            "course": 2,  # education_fields create (70-72)
            "some_core_field": "x",  # else: setattr on user (87)
        },
    )
    assert isinstance(user.preferences, models.UserPreferences)
    assert user.preferences.timezone == "UTC"
    assert user.preferences.dnd_enabled is True
    assert isinstance(user.profile, models.UserProfile)
    assert user.profile.full_name == "Ann"
    assert user.profile.about == "hi"
    assert isinstance(user.education_path, models.EducationPath)
    assert user.education_path.course == 2
    assert user.some_core_field == "x"


def test_nested_updates_ignore_fields_outside_child_allowlists() -> None:
    user = models.User(
        id=uuid.uuid4(),
        email="nested-update@example.test",
        hashed_password=ANONYMIZED_USER_CREDENTIAL,
    )
    user.profile = models.UserProfile(
        user_id=user.id,
        about="Existing bio",
        department="Existing department",
    )
    user.education_path = models.EducationPath(
        user_id=user.id,
        institute="Existing institute",
        course="Existing course",
    )

    update_user_attributes(
        user,
        {
            "profile_detail": {
                "department": "Updated department",
                "unmapped_profile_attribute": "must not be assigned",
            },
            "education_path": {
                "course": "Updated course",
                "unmapped_education_attribute": "must not be assigned",
            },
        },
    )

    assert user.profile.about == "Existing bio"
    assert user.profile.department == "Updated department"
    assert not hasattr(user.profile, "unmapped_profile_attribute")
    assert user.education_path.institute == "Existing institute"
    assert user.education_path.course == "Updated course"
    assert not hasattr(user.education_path, "unmapped_education_attribute")


def test_nested_profile_update_creates_missing_profile() -> None:
    user = models.User(
        id=uuid.uuid4(),
        email="new-profile@example.test",
        hashed_password=ANONYMIZED_USER_CREDENTIAL,
    )

    update_user_attributes(
        user,
        {"profile_detail": {"about": "New profile bio", "department": "Physics"}},
    )

    assert isinstance(user.profile, models.UserProfile)
    assert user.profile.user_id == user.id
    assert user.profile.about == "New profile bio"
    assert user.profile.department == "Physics"


def test_invalid_education_payload_preserves_existing_relation() -> None:
    user = models.User(
        id=uuid.uuid4(),
        email="existing-education@example.test",
        hashed_password=ANONYMIZED_USER_CREDENTIAL,
    )
    education_path = models.EducationPath(
        user_id=user.id,
        institute="Existing institute",
        course="Existing course",
    )
    user.education_path = education_path

    update_user_attributes(user, {"education_path": object()})

    assert user.education_path is education_path
    assert user.education_path.institute == "Existing institute"
    assert user.education_path.course == "Existing course"


async def test_anonymize_user_data_clears_avatar_and_cover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []

    async def _fake_delete(url: str) -> None:
        deleted.append(url)

    monkeypatch.setattr(
        logic_module, "delete_static_file", AsyncMock(side_effect=_fake_delete)
    )

    user_id = uuid.uuid4()
    profile = SimpleNamespace(
        avatar_url=(f"/static/avatars/user_{user_id}_avatar_{'a' * 32}.png"),
        cover_url=(
            f"/static/covers/user_{user_id}_cover_{'b' * 32}.png"
        ),  # exercises the cover_url cleanup branch
        full_name="Real Name",
        about="bio",
        telegram="@x",
        achievements="stuff",
        position="dev",
        department="eng",
        status="active",
    )
    password_marker = make_test_marker(length=4, required_classes=frozenset({"lower"}))
    user = SimpleNamespace(
        id=user_id,
        profile=profile,
        education_path=None,
        preferences=None,
        spotify=None,
        email="real@example.com",
        hashed_password=password_marker,
        is_active=True,
        mfa_required=True,
        mfa_default_method="totp",
        mfa_last_verified_at=object(),
    )

    email = await anonymize_user_data(user)  # type: ignore[arg-type]

    assert email == f"deleted+{user.id}@deleted.example.com"
    assert profile.avatar_url is None
    assert profile.cover_url is None
    assert len(deleted) == 2
    assert user.profile.full_name == "Deleted User"
    assert user.profile.status == "deleted"
    assert user.is_active is False


@pytest.mark.asyncio
async def test_anonymize_deletes_owned_avatar_but_preserves_legacy_foreign_cover(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.utils.files as file_utils
    from app.services.storage import StaticFSStorage

    owner_id = uuid.uuid4()
    avatar_rel = f"avatars/user_{owner_id}_avatar_{'a' * 32}.png"
    legacy_cover_rel = "covers/another-users-file.png"
    avatar_path = tmp_path / avatar_rel
    legacy_cover_path = tmp_path / legacy_cover_rel
    avatar_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_cover_path.parent.mkdir(parents=True, exist_ok=True)
    avatar_path.write_bytes(b"owner avatar")
    legacy_cover_path.write_bytes(b"foreign cover")
    monkeypatch.setattr(
        file_utils, "_get_storage_backend", lambda: StaticFSStorage(tmp_path, "/static")
    )

    user = SimpleNamespace(
        id=owner_id,
        profile=SimpleNamespace(
            avatar_url=f"/static/{avatar_rel}",
            cover_url=f"/static/{legacy_cover_rel}",
            full_name="Real Name",
            about="bio",
            telegram="@x",
            achievements="stuff",
            position="dev",
            department="eng",
            status="active",
        ),
        education_path=None,
        preferences=None,
        spotify=None,
        email="real@example.com",
        hashed_password="hash",  # pragma: allowlist secret
        is_active=True,
        mfa_required=False,
        mfa_default_method=None,
        mfa_last_verified_at=None,
    )

    await anonymize_user_data(user)  # type: ignore[arg-type]

    assert not avatar_path.exists()
    assert legacy_cover_path.read_bytes() == b"foreign cover"
    assert user.profile.avatar_url is None
    assert user.profile.cover_url is None
