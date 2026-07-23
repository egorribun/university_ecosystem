"""Focused closure tests for schema validators and model flattening."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.enums import UserRole
from app.schemas import schemas

USER_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df79")
NOW = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)


def _orm_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=USER_ID,
        email="user@example.com",
        role=UserRole.STUDENT,
        group_id=None,
        is_active=True,
        mfa_required=False,
        mfa_default_method=None,
        mfa_last_verified_at=None,
        created_at=NOW,
        profile=None,
        education_path=None,
        preferences=None,
        spotify=None,
        spotify_is_connected=False,
        totp_enrollments=[],
        mfa_challenges=[],
        pending_email=None,
        recovery_codes=[],
    )


def test_orm_model_from_orm_and_preference_validator_edges() -> None:
    group = schemas.GroupOut.from_orm(
        SimpleNamespace(id=USER_ID, name="Group", course=None, faculty=None)
    )
    assert group.id == USER_ID

    assert schemas.UserPreferencesBase(dnd_enabled=False).dnd_enabled is False
    with pytest.raises(ValidationError, match="times"):
        schemas.UserPreferencesBase(dnd_enabled=True)
    assert schemas.UserPreferencesBase(timezone=None).timezone is None
    assert schemas.UserPreferencesBase(timezone=" ").timezone is None
    assert (
        schemas.UserPreferencesBase(timezone="Europe/Berlin").timezone
        == "Europe/Berlin"
    )
    with pytest.raises(ValidationError, match="timezone"):
        schemas.UserPreferencesBase(timezone="Invalid/Zone")


def test_user_out_flattens_dict_and_orm_inputs() -> None:
    from_dict = schemas.UserOut.model_validate(
        {
            "id": USER_ID,
            "email": "dict@example.com",
            "is_active": True,
            "dnd_enabled": None,
        }
    )
    assert from_dict.dnd_enabled is False

    from_orm = schemas.UserOut.model_validate(_orm_user())
    assert from_orm.id == USER_ID
    assert from_orm.email == "user@example.com"
    assert from_orm.spotify_is_connected is False


def test_public_user_flattens_dict_and_orm_inputs() -> None:
    from_dict = schemas.UserPublicOut.model_validate({"id": USER_ID, "is_active": True})
    assert from_dict.id == USER_ID

    orm_user = _orm_user()
    from_orm = schemas.UserPublicOut.model_validate(orm_user)
    assert from_orm.id == USER_ID
    assert from_orm.role is UserRole.STUDENT


def test_story_expiration_validators_cover_create_and_update() -> None:
    valid = schemas.StoryCreate(
        title="Story",
        short_text="Text",
        published_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    assert valid.expires_at > valid.published_at
    with pytest.raises(ValidationError):
        schemas.StoryCreate(
            title="Story",
            short_text="Text",
            published_at=NOW,
            expires_at=NOW,
        )

    assert schemas.StoryUpdate().model_fields_set == set()
    assert schemas.StoryUpdate(published_at=NOW).published_at == NOW
    assert schemas.StoryUpdate(expires_at=NOW).expires_at == NOW
    assert schemas.StoryUpdate(published_at=None, expires_at=NOW).expires_at == NOW
    assert (
        schemas.StoryUpdate(
            published_at=NOW, expires_at=NOW + timedelta(hours=1)
        ).expires_at
        > NOW
    )
    with pytest.raises(ValidationError):
        schemas.StoryUpdate(published_at=NOW, expires_at=NOW)


def test_event_time_validators_cover_success_and_missing_end() -> None:
    valid_create = schemas.EventCreate(
        title="Event",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=1),
    )
    assert valid_create.ends_at > valid_create.starts_at
    with pytest.raises(ValidationError):
        schemas.EventCreate(title="Event", starts_at=NOW, ends_at=NOW)

    assert schemas.EventUpdate().model_fields_set == set()
    with pytest.raises(ValidationError):
        schemas.EventUpdate(starts_at=NOW)
    with pytest.raises(ValidationError):
        schemas.EventUpdate(starts_at=NOW, ends_at=None)
    with pytest.raises(ValidationError):
        schemas.EventUpdate(starts_at=NOW, ends_at=NOW)
    valid_update = schemas.EventUpdate(starts_at=NOW, ends_at=NOW + timedelta(hours=1))
    assert valid_update.ends_at > valid_update.starts_at


def test_dead_letter_job_ids_are_unique_and_non_empty() -> None:
    payload = schemas.NotificationDeadLetterReplayIn(job_ids=["a", "a", "b"])
    assert payload.job_ids == ["a", "b"]

    with pytest.raises(ValueError, match="at least one"):
        schemas._NotificationDeadLetterJobIds._ensure_unique([])
