from app.core.constants import DELETED_PASSWORD_HASH
from app.models import models
from app.utils.files import delete_static_file


def update_user_attributes(user: models.User, data: dict) -> None:
    """Update user attributes including nested relations."""
    preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}
    profile_fields = {
        "about",
        "telegram",
        "status",
        "achievements",
        "position",
        "department",
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
        if field in preferences_fields:
            if not user.preferences:
                user.preferences = models.UserPreferences(user_id=user.id)
            setattr(user.preferences, field, value)
        elif field in profile_fields:
            if not user.profile_detail:
                user.profile_detail = models.UserProfileDetail(user_id=user.id)
            setattr(user.profile_detail, field, value)
        elif field in education_fields:
            if not user.education_path:
                user.education_path = models.EducationPath(user_id=user.id)
            setattr(user.education_path, field, value)
        else:
            setattr(user, field, value)


async def anonymize_user_data(user: models.User) -> str:
    """
    Anonymize user data for deletion.
    Returns the anonymized email.
    """
    anonymized_email = f"deleted+{user.id}@deleted.example.com"

    if user.avatar_url:
        await delete_static_file(user.avatar_url)
    if user.cover_url:
        await delete_static_file(user.cover_url)

    user.full_name = None
    user.email = anonymized_email
    user.avatar_url = None
    user.cover_url = None
    user.hashed_password = DELETED_PASSWORD_HASH
    user.is_active = False
    user.status = "deleted"
    user.mfa_required = False
    user.mfa_default_method = None
    user.mfa_last_verified_at = None

    # Clear nested relationships
    user.preferences = None
    user.spotify = None
    user.profile_detail = None
    user.education_path = None
    user.about = None
    user.telegram = None
    user.achievements = None
    user.record_book_number = None

    return anonymized_email
