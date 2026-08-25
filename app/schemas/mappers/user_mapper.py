from __future__ import annotations

from typing import Any


def map_user_orm_to_dict(user: Any) -> dict[str, Any]:
    """Flatten UserProfile and UserPreferences into the main User dict.

    This logic corresponds to the internal _flatten_user_data in UserOut.
    """

    # Helper to safely get from related object
    def get_attr(obj: Any, attr: str, default: Any = None) -> Any:
        return getattr(obj, attr, default)

    out = {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "group_id": user.group_id,
        "is_active": user.is_active,
        "mfa_required": user.mfa_required,
        "mfa_default_method": user.mfa_default_method,
        "mfa_last_verified_at": user.mfa_last_verified_at,
        "created_at": getattr(user, "created_at", None),
    }

    # Profile fields
    profile = getattr(user, "profile", None)
    out.update(
        {
            "full_name": get_attr(profile, "full_name"),
            "avatar_url": get_attr(profile, "avatar_url"),
            "cover_url": get_attr(profile, "cover_url"),
            "about": get_attr(profile, "about"),
            "telegram": get_attr(profile, "telegram"),
            "profile_status": get_attr(profile, "status"),
            "achievements": get_attr(profile, "achievements"),
            "profile_department": get_attr(profile, "department"),
            "position": get_attr(profile, "position"),
        }
    )

    # Education fields
    edu = getattr(user, "education_path", None)
    out.update(
        {
            "institute": get_attr(edu, "institute"),
            "course": get_attr(edu, "course"),
            "education_level": get_attr(edu, "education_level"),
            "track": get_attr(edu, "track"),
            "program": get_attr(edu, "program"),
            "record_book_number": get_attr(edu, "record_book_number"),
        }
    )

    # Preferences fields
    prefs = getattr(user, "preferences", None)
    out.update(
        {
            "dnd_enabled": get_attr(prefs, "dnd_enabled", False),
            "dnd_start": get_attr(prefs, "dnd_start"),
            "dnd_end": get_attr(prefs, "dnd_end"),
            "timezone": get_attr(prefs, "timezone"),
        }
    )

    # Spotify fields
    spotify = getattr(user, "spotify", None)
    out.update(
        {
            "spotify_is_connected": get_attr(spotify, "is_connected", False),
        }
    )

    # Computed/Other
    out["spotify_connected"] = getattr(user, "spotify_is_connected", False)  # RZ-33-16
    out["spotify_display_name"] = (
        user.spotify.display_name
        if getattr(user, "spotify", None) and user.spotify.is_connected
        else None
    )

    # Publicly serializable relationship list. Challenge records contain
    # authentication state and bindings, so they must never enter UserOut.
    out["totp_enrollments"] = getattr(user, "totp_enrollments", [])

    # Pending email
    out["pending_email"] = getattr(user, "pending_email", None)
    out["recovery_codes_left"] = len(getattr(user, "recovery_codes", []))

    return out


def map_user_orm_to_public_dict(user: Any) -> dict[str, Any]:
    """Flatten UserProfile into a PII-safe public user dict.

    This logic corresponds to the internal _flatten_public_data in UserPublicOut.
    """

    def get_attr(obj: Any, attr: str, default: Any = None) -> Any:
        return getattr(obj, attr, default)

    out = {
        "id": user.id,
        "role": user.role,
        "group_id": user.group_id,
        "is_active": user.is_active,
    }

    profile = getattr(user, "profile", None)
    out.update(
        {
            "full_name": get_attr(profile, "full_name"),
            "avatar_url": get_attr(profile, "avatar_url"),
            "cover_url": get_attr(profile, "cover_url"),
            "about": get_attr(profile, "about"),
            "profile_status": get_attr(profile, "status"),
            "profile_department": get_attr(profile, "department"),
            "position": get_attr(profile, "position"),
        }
    )

    edu = getattr(user, "education_path", None)
    out.update(
        {
            "institute": get_attr(edu, "institute"),
            "course": get_attr(edu, "course"),
        }
    )

    return out
