from typing import Any

import app.models as models
from app.core.constants import ANONYMIZED_USER_CREDENTIAL


async def delete_static_file(path: str) -> None:
    """Load the optional image backend only when a profile file is removed."""

    from app.utils.files import delete_static_file as _delete_static_file

    await _delete_static_file(path)


def update_user_attributes(user: models.User, data: dict[str, Any]) -> None:
    """Update user attributes including nested relations."""
    preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}
    profile_fields = {
        "full_name",
        "avatar_url",
        "cover_url",
        "about",
        "telegram",
        "status",
        "achievements",
        "position",
        "department",
    }
    profile_detail_fields = {
        "about",
        "telegram",
        "status",
        "achievements",
        "department",
        "position",
    }
    education_fields = {
        "institute",
        "course",
        "education_level",
        "track",
        "program",
        "record_book_number",
    }
    for field, value in data.items():
        if field == "preferences" and isinstance(value, dict):
            if not user.preferences:
                user.preferences = models.UserPreferences(user_id=user.id)
            for k, v in value.items():
                setattr(user.preferences, k, v)
        elif field in preferences_fields:
            if not user.preferences:
                user.preferences = models.UserPreferences(user_id=user.id)
            setattr(user.preferences, field, value)
        elif field in profile_fields:
            if not user.profile:
                user.profile = models.UserProfile(user_id=user.id)
            setattr(user.profile, field, value)
        elif field == "profile_detail":
            if isinstance(value, dict):
                if not user.profile:
                    user.profile = models.UserProfile(user_id=user.id)
                for key, nested_value in value.items():
                    if key in profile_detail_fields:
                        setattr(user.profile, key, nested_value)
        elif field == "profile" and isinstance(value, dict):
            if not user.profile:
                user.profile = models.UserProfile(user_id=user.id)
            for k, v in value.items():
                setattr(user.profile, k, v)
        elif field in education_fields:
            if not user.education_path:
                user.education_path = models.EducationPath(user_id=user.id)
            setattr(user.education_path, field, value)
        elif field == "education_path":
            if value is None:
                user.education_path = None
            elif isinstance(value, dict):
                if not user.education_path:
                    user.education_path = models.EducationPath(user_id=user.id)
                for key, nested_value in value.items():
                    if key in education_fields:
                        setattr(user.education_path, key, nested_value)
        else:
            setattr(user, field, value)


async def anonymize_user_data(user: models.User) -> str:
    """
    Anonymize user data for deletion.
    Returns the anonymized email.
    """
    anonymized_email = f"deleted+{user.id}@deleted.example.com"

    # Profile fields handling
    if user.profile:
        if user.profile.avatar_url:
            await delete_static_file(user.profile.avatar_url)
        if user.profile.cover_url:
            await delete_static_file(user.profile.cover_url)

        # We want to keep the profile to store "deleted" status,
        # but clear all other PII.
        user.profile.full_name = "Deleted User"
        user.profile.avatar_url = None
        user.profile.cover_url = None
        user.profile.about = None
        user.profile.telegram = None
        user.profile.achievements = None
        user.profile.position = None
        user.profile.department = None
        user.profile.status = "deleted"
    else:
        # Create a placeholder profile if it didn't exist
        user.profile = models.UserProfile(
            user_id=user.id, full_name="Deleted User", status="deleted"
        )

    user.email = anonymized_email
    user.hashed_password = ANONYMIZED_USER_CREDENTIAL
    user.is_active = False
    user.mfa_required = False
    user.mfa_default_method = None
    user.mfa_last_verified_at = None

    # Clear nested relationships
    if user.profile:
        user.profile.status = "deleted"
        user.profile.about = None
        user.profile.telegram = None
        user.profile.achievements = None
        user.profile.position = None
        user.profile.department = None

    if user.education_path:
        user.education_path.institute = None
        user.education_path.course = None
        user.education_path.education_level = None
        user.education_path.track = None
        user.education_path.program = None
        user.education_path.record_book_number = None

    if user.preferences:
        user.preferences.dnd_enabled = False
        user.preferences.timezone = None

    user.spotify = None
    user.education_path = None

    return anonymized_email
