import re
from pathlib import PurePosixPath
from typing import Any, Literal
from uuid import UUID

import app.models as models
from app.core.constants import ANONYMIZED_USER_CREDENTIAL


async def delete_static_file(path: str) -> None:
    """Load the optional image backend only when a profile file is removed."""

    from app.utils.files import delete_static_file as _delete_static_file

    await _delete_static_file(path)


ProfileMediaKind = Literal["avatar", "cover"]


def _is_owned_profile_media_path(
    path: str, *, owner_id: UUID, media_kind: ProfileMediaKind
) -> bool:
    """Match only the upload key format that proves this profile owns the file."""

    from app.services.storage import S3Storage, StaticFSStorage
    from app.utils.files import _get_storage_backend, normalize_filename_prefix

    backend = _get_storage_backend()
    if isinstance(backend, StaticFSStorage):
        relative_path = backend._extract_relative_path(path)
        key = relative_path.as_posix() if relative_path is not None else None
    elif isinstance(backend, S3Storage):
        key = backend._extract_key(path)
    else:
        # Unknown storage implementations cannot prove which object the URL maps to.
        return False

    if not key:
        return False

    directory = {"avatar": "avatars", "cover": "covers"}.get(media_kind)
    if directory is None:
        return False

    parts = PurePosixPath(key).parts
    if len(parts) != 2 or parts[0] != directory:
        return False

    owner_prefix = normalize_filename_prefix(f"user_{owner_id}_{media_kind}")
    filename_pattern = rf"{re.escape(owner_prefix)}_[0-9a-f]{{32}}\.(?:jpg|png|webp)"
    return re.fullmatch(filename_pattern, parts[1]) is not None


async def delete_owned_profile_media(
    path: str, *, owner_id: UUID, media_kind: ProfileMediaKind
) -> bool:
    """Delete profile media only when its stored key matches the current owner.

    Older or poisoned URLs without the owner-scoped upload key are left in storage;
    profile references are still cleared by their caller.
    """

    if not _is_owned_profile_media_path(path, owner_id=owner_id, media_kind=media_kind):
        return False

    await delete_static_file(path)
    return True


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
            await delete_owned_profile_media(
                user.profile.avatar_url, owner_id=user.id, media_kind="avatar"
            )
        if user.profile.cover_url:
            await delete_owned_profile_media(
                user.profile.cover_url, owner_id=user.id, media_kind="cover"
            )

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
