from app.core.constants import ANONYMIZED_USER_CREDENTIAL
from app.core.exceptions.domain import EntityAlreadyExists
from app.models import models
from app.repositories.user_repository import UserRepository
from app.utils.files import delete_static_file


def update_user_attributes(user: models.User, data: dict) -> None:
    """Update user attributes including nested relations."""
    for field, value in data.items():
        if field == "preferences" and isinstance(value, dict):
            if not user.preferences:
                user.preferences = models.UserPreferences(user_id=user.id)
            for k, v in value.items():
                setattr(user.preferences, k, v)
        elif field == "profile_detail" and isinstance(value, dict):
            if not user.profile_detail:
                user.profile_detail = models.UserProfileDetail(user_id=user.id)
            for k, v in value.items():
                setattr(user.profile_detail, k, v)
        elif field == "education_path" and isinstance(value, dict):
            if not user.education_path:
                user.education_path = models.EducationPath(user_id=user.id)
            for k, v in value.items():
                setattr(user.education_path, k, v)
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
    user.hashed_password = ANONYMIZED_USER_CREDENTIAL
    user.is_active = False
    user.mfa_required = False
    user.mfa_default_method = None
    user.mfa_last_verified_at = None

    # Clear nested relationships or stub them out
    if user.profile_detail:
        user.profile_detail.status = "deleted"
        user.profile_detail.about = None
        user.profile_detail.telegram = None
        user.profile_detail.achievements = None
        user.profile_detail.position = None
        user.profile_detail.department = None

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

    return anonymized_email


async def validate_user_email(
    repo: UserRepository, email: str, exclude_user_id: int | None = None
) -> str:
    """Validate email and check for uniqueness."""
    validated_email = str(email).strip().lower()
    if await repo.check_email_exists(validated_email, exclude_user_id=exclude_user_id):
        raise EntityAlreadyExists("User", validated_email)
    return validated_email


async def execute_user_anonymization(repo: UserRepository, user: models.User) -> str:
    """Perform full anonymization and sensitive data deletion."""
    anonymized_email = await anonymize_user_data(user)
    await repo.delete_sensitive_data(user.id)
    return anonymized_email
