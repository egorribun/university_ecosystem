from unittest.mock import MagicMock

from app.schemas.mappers.user_mapper import (
    map_user_orm_to_dict,
    map_user_orm_to_public_dict,
)


def test_map_user_orm_to_dict():
    """Verify map_user_orm_to_dict handles full user objects and missing optional fields."""
    user = MagicMock()
    user.id = 123
    user.email = "test@example.com"
    user.role = "student"
    user.group_id = 456
    user.is_active = True
    user.mfa_required = False
    user.mfa_default_method = None
    user.mfa_last_verified_at = None
    user.created_at = "2026-01-01T00:00:00Z"

    # 1. Profile, Edu, Prefs, Spotify set
    user.profile = MagicMock(
        full_name="John Doe",
        avatar_url="avatar",
        cover_url="cover",
        about="about",
        telegram="tg",
        status="active",
        achievements=[],
        department="CS",
        position="junior",
    )
    user.education_path = MagicMock(
        institute="MIT",
        course=3,
        education_level="BSc",
        track="SE",
        program="Computer Science",
        record_book_number="R1234",
    )
    user.preferences = MagicMock(
        dnd_enabled=True,
        dnd_start="22:00",
        dnd_end="08:00",
        timezone="EST",
    )
    user.spotify = MagicMock(
        is_connected=True,
        display_name="SpotifyUser",
    )
    user.spotify_is_connected = True
    user.totp_enrollments = ["totp1"]
    user.mfa_challenges = ["chal1"]
    user.pending_email = "pending@example.com"
    user.recovery_codes = ["code1", "code2"]

    res = map_user_orm_to_dict(user)
    assert res["id"] == 123
    assert res["email"] == "test@example.com"
    assert res["full_name"] == "John Doe"
    assert res["institute"] == "MIT"
    assert res["dnd_enabled"] is True
    assert res["spotify_connected"] is True
    assert res["spotify_display_name"] == "SpotifyUser"
    assert res["recovery_codes_left"] == 2

    # 2. None relations / defaults fallback
    user_none = MagicMock()
    user_none.id = 999
    user_none.profile = None
    user_none.education_path = None
    user_none.preferences = None
    user_none.spotify = None
    user_none.spotify_is_connected = False
    user_none.totp_enrollments = []
    user_none.mfa_challenges = []
    user_none.pending_email = None
    user_none.recovery_codes = []

    res_none = map_user_orm_to_dict(user_none)
    assert res_none["id"] == 999
    assert res_none["full_name"] is None
    assert res_none["institute"] is None
    assert res_none["dnd_enabled"] is False
    assert res_none["spotify_connected"] is False
    assert res_none["spotify_display_name"] is None
    assert res_none["recovery_codes_left"] == 0


def test_map_user_orm_to_public_dict():
    """Verify map_user_orm_to_public_dict flattens user to safe public fields."""
    user = MagicMock()
    user.id = 123
    user.role = "student"
    user.group_id = 456
    user.is_active = True
    user.profile = MagicMock(
        full_name="John Doe",
        avatar_url="avatar",
        cover_url="cover",
        about="about",
        status="active",
        department="CS",
        position="junior",
    )
    user.education_path = MagicMock(
        institute="MIT",
        course=3,
    )

    res = map_user_orm_to_public_dict(user)
    assert res["id"] == 123
    assert res["role"] == "student"
    assert res["full_name"] == "John Doe"
    assert res["institute"] == "MIT"
    assert res["course"] == 3
    # Verify private/MFA fields are not present
    assert "email" not in res
    assert "mfa_required" not in res

    # Check defaults fallback
    user_none = MagicMock()
    user_none.id = 999
    user_none.profile = None
    user_none.education_path = None

    res_none = map_user_orm_to_public_dict(user_none)
    assert res_none["id"] == 999
    assert res_none["full_name"] is None
    assert res_none["institute"] is None
