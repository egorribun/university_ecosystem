from datetime import UTC, datetime, time, timedelta

import pytest
from pydantic import ValidationError

import app.models as models
from app.schemas import schemas


def test_user_create_requires_valid_email():
    with pytest.raises(ValidationError):
        schemas.UserCreate(email="invalid-email", password="secret")


def test_user_profile_update_validates_email():
    with pytest.raises(ValidationError):
        schemas.UserProfileUpdate(email="not-an-email")


def test_user_profile_update_requires_dnd_times():
    with pytest.raises(ValidationError):
        schemas.UserProfileUpdate(dnd_enabled=True)


def test_user_profile_update_accepts_dnd_interval():
    payload = schemas.UserProfileUpdate(
        dnd_enabled=True,
        dnd_start=time(22, 0),
        dnd_end=time(7, 0),
    )
    assert payload.dnd_enabled is True


def test_user_profile_update_validates_timezone():
    payload = schemas.UserProfileUpdate(timezone="Europe/Berlin")
    assert payload.timezone == "Europe/Berlin"

    with pytest.raises(ValidationError):
        schemas.UserProfileUpdate(timezone="Invalid/Zone")


def test_event_create_requires_end_after_start():
    starts = datetime.now(UTC)
    with pytest.raises(ValidationError):
        schemas.EventCreate(
            title="Test",
            starts_at=starts,
            ends_at=starts,
        )


def test_event_update_requires_both_timestamps():
    starts = datetime.now(UTC)
    with pytest.raises(ValidationError):
        schemas.EventUpdate(starts_at=starts)


def test_event_update_requires_order():
    starts = datetime.now(UTC)
    with pytest.raises(ValidationError):
        schemas.EventUpdate(starts_at=starts, ends_at=starts)


def test_event_update_accepts_valid_interval():
    starts = datetime.now(UTC)
    payload = schemas.EventUpdate(
        starts_at=starts,
        ends_at=starts + timedelta(hours=1),
    )
    assert payload.starts_at == starts


@pytest.mark.asyncio(loop_scope="session")
async def test_user_out_contract(user_factory):
    user = await user_factory(full_name="Test User")
    if not user.spotify:
        user.spotify = models.SpotifyIntegration()
    user.spotify.is_connected = True
    user.spotify.display_name = "DJ Test"
    payload = schemas.UserOut.from_orm(user)
    data = payload.model_dump()

    assert data["id"] == user.id
    assert data["email"] == user.email
    assert data["spotify_is_connected"] is True
    assert data["dnd_enabled"] is False
    assert data["dnd_start"] is None
    assert data["dnd_end"] is None
    assert data["timezone"] is None
    assert "hashed_password" not in data
