"""Relationship-creation tests for app/services/user/logic.py
update_user_attributes create-when-None branches (36/49/70/72 + profile-dict)
and anonymize_user_data's cover_url cleanup (line 87) — the noload-create arms
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
from app.services.user.logic import anonymize_user_data, update_user_attributes


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


async def test_anonymize_user_data_clears_avatar_and_cover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []

    async def _fake_delete(url: str) -> None:
        deleted.append(url)

    monkeypatch.setattr(
        logic_module, "delete_static_file", AsyncMock(side_effect=_fake_delete)
    )

    profile = SimpleNamespace(
        avatar_url="static/avatar.png",
        cover_url="static/cover.png",  # exercises the cover_url branch (line 87)
        full_name="Real Name",
        about="bio",
        telegram="@x",
        achievements="stuff",
        position="dev",
        department="eng",
        status="active",
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        profile=profile,
        education_path=None,
        preferences=None,
        spotify=None,
        email="real@example.com",
        hashed_password="hash",  # pragma: allowlist secret
        is_active=True,
        mfa_required=True,
        mfa_default_method="totp",
        mfa_last_verified_at=object(),
    )

    email = await anonymize_user_data(user)  # type: ignore[arg-type]

    assert email == f"deleted+{user.id}@deleted.example.com"
    assert "static/avatar.png" in deleted
    assert "static/cover.png" in deleted
    assert user.profile.full_name == "Deleted User"
    assert user.profile.status == "deleted"
    assert user.is_active is False
