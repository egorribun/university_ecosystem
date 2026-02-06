"""Comprehensive tests for UserService.

Coverage targets:
- update_user_profile: email validation, preferences, existing email check
- upload_avatar/cover: success, commit failure, refresh failure
- create_user: admin check, invite code validation
- get_users: admin vs non-admin, search params
- admin_update_user: forbidden, MFA reset notification
- admin_delete_user: forbidden, not found, self-delete, success with cleanup
- delete_avatar/cover: with and without existing file
- export_user_data: full data export
- delete_user_data: confirm check, full anonymization
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.schemas import schemas
from app.services.user_service import UserService


@pytest.fixture
def mock_db():
    """Create mock AsyncSession."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock()
    db.get = AsyncMock()
    return db


@pytest.fixture
def mock_audit():
    """Create mock AuditService."""
    audit = MagicMock()
    audit.log = MagicMock()
    return audit


@pytest.fixture
def mock_repo():
    """Create mock UserRepository."""
    repo = AsyncMock()
    repo.get = AsyncMock()
    repo.list_users = AsyncMock()
    repo.check_email_exists = AsyncMock()
    repo.delete_sensitive_data = AsyncMock()
    return repo


@pytest.fixture
def mock_notifications():
    """Create mock NotificationService."""
    notifications = AsyncMock()
    notifications.send_security_notification = AsyncMock()
    return notifications


@pytest.fixture
def mock_request():
    """Create mock Request."""
    request = MagicMock()
    request.headers = {}
    return request


@pytest.fixture
def mock_user():
    """Create mock User."""
    import uuid

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = "student"
    user.avatar_url = None
    user.cover_url = None
    user.preferences = None
    user.mfa_challenges = []
    user.totp_enrollments = []
    return user


@pytest.fixture
def mock_admin_user():
    """Create mock admin User."""
    import uuid

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@example.com"
    user.role = "admin"
    return user


@pytest.fixture
def service(mock_db, mock_repo, mock_audit, mock_notifications):
    """Create UserService instance."""
    return UserService(mock_db, mock_repo, mock_audit, mock_notifications)


# ============================================================
# update_user_profile tests
# ============================================================


@pytest.mark.asyncio
async def test_update_user_profile_success(service, mock_db, mock_user, mock_request):
    """Test successful profile update."""
    service.repo.get.return_value = mock_user
    data = MagicMock()
    data.model_dump.return_value = {"full_name": "New Name"}

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
            with patch("app.services.user_service.attach_pending_email"):
                result = await service.update_user_profile(
                    mock_user, data, mock_request
                )

    assert result == mock_user
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_profile_invalid_email(
    service, mock_db, mock_user, mock_request
):
    """Test profile update with invalid email."""
    service.repo.get.return_value = mock_user
    data = MagicMock()
    data.model_dump.return_value = {"email": "not-an-email"}

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(EntityAlreadyExists):
            await service.update_user_profile(mock_user, data, mock_request)


@pytest.mark.asyncio
async def test_update_user_profile_email_in_use(
    service, mock_db, mock_user, mock_request
):
    """Test profile update when email is already in use."""
    service.repo.get.return_value = mock_user
    data = MagicMock()
    data.model_dump.return_value = {"email": "existing@example.com"}

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = 2  # Another user has this email
    mock_db.execute.return_value = mock_result

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(EntityAlreadyExists):
            await service.update_user_profile(mock_user, data, mock_request)


@pytest.mark.asyncio
async def test_update_user_profile_preferences(
    service, mock_db, mock_user, mock_request
):
    """Test profile update with preferences fields."""
    service.repo.get.return_value = mock_user
    data = MagicMock()
    data.model_dump.return_value = {"dnd_enabled": True, "timezone": "UTC"}

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
            with patch("app.services.user_service.attach_pending_email"):
                await service.update_user_profile(mock_user, data, mock_request)

    mock_db.commit.assert_called_once()


# ============================================================
# create_user tests
# ============================================================


@pytest.mark.asyncio
async def test_create_user_forbidden_non_admin(
    service, mock_db, mock_user, mock_request
):
    """Test create_user fails for non-admin."""
    data = MagicMock()

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(PermissionDenied):
            await service.create_user(data, mock_request, mock_user)


@pytest.mark.asyncio
async def test_create_user_teacher_requires_invite(
    service, mock_db, mock_admin_user, mock_request
):
    """Test create_user for teacher requires invite code."""
    data = MagicMock()
    data.role = "teacher"
    data.invite_code = None

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(BusinessRuleViolation):
            await service.create_user(data, mock_request, mock_admin_user)


@pytest.mark.asyncio
async def test_create_user_invalid_invite(
    service, mock_db, mock_admin_user, mock_request
):
    """Test create_user with invalid invite code."""
    data = MagicMock()
    data.role = "admin"
    data.invite_code = "INVALID"

    service.repo.get_invite_code.return_value = None
    service.repo.check_email_exists.return_value = False

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(BusinessRuleViolation):
            await service.create_user(data, mock_request, mock_admin_user)


@pytest.mark.asyncio
async def test_create_user_success(service, mock_db, mock_admin_user, mock_request):
    """Test successful user creation by admin."""
    data = MagicMock()
    data.role = "student"
    data.invite_code = None
    data.password = "Valid_password_123"
    service.repo.check_email_exists.return_value = False

    mock_new_user = MagicMock()
    mock_new_user.id = 100
    service.repo.create.return_value = mock_new_user

    mock_db.execute.return_value.scalars.return_value.first.return_value = None

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        result = await service.create_user(data, mock_request, mock_admin_user)

    assert result.id == 100


# ============================================================
# get_users tests
# ============================================================


@pytest.mark.asyncio
async def test_get_users_non_admin_no_search(service, mock_db, mock_user, mock_request):
    """Test get_users fails for non-admin without search."""
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(PermissionDenied):
            await service.get_users(mock_request, mock_user)


@pytest.mark.asyncio
async def test_get_users_non_admin_with_search(
    service, mock_db, mock_user, mock_request
):
    service.repo.list_users.return_value = []

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        result = await service.get_users(
            mock_request, mock_user, filters=schemas.UserSearchFilter(search="test")
        )

    assert result == []
    service.repo.list_users.assert_called_once()


@pytest.mark.asyncio
async def test_get_users_admin(service, mock_db, mock_admin_user, mock_request):
    """Test get_users succeeds for admin."""
    mock_users = [MagicMock(), MagicMock()]
    service.repo.list_users.return_value = mock_users

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        result = await service.get_users(
            mock_request, mock_admin_user, filters=schemas.UserSearchFilter()
        )

    assert len(result) == 2


# ============================================================
# admin_update_user tests
# ============================================================


@pytest.mark.asyncio
async def test_admin_update_user_forbidden(service, mock_db, mock_user, mock_request):
    """Test admin_update_user fails for non-admin."""
    data = MagicMock()

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(PermissionDenied):
            await service.admin_update_user(2, data, mock_request, mock_user)


@pytest.mark.asyncio
async def test_admin_update_user_success(
    service, mock_db, mock_admin_user, mock_request, mock_audit
):
    """Test successful admin user update."""
    data = MagicMock()
    updated_user = MagicMock()
    updated_user.id = 2

    service.repo.get.return_value = updated_user

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
            result = await service.admin_update_user(
                2, data, mock_request, mock_admin_user
            )

    assert result.id == 2
    mock_audit.log.assert_called()


@pytest.mark.asyncio
async def test_admin_update_user_mfa_reset(
    service, mock_db, mock_admin_user, mock_request, mock_audit
):
    """Test admin user update with MFA reset creates notification."""
    data = MagicMock()
    updated_user = MagicMock()
    updated_user.id = 2
    reset_stats = MagicMock()
    reset_stats.changed = True

    updated_user.preferences = None
    service.repo.get.return_value = updated_user
    data.model_dump.return_value = {"reset_mfa": True}

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch("app.auth.mfa.reset_user_mfa", return_value=reset_stats):
            with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
                await service.admin_update_user(2, data, mock_request, mock_admin_user)

    service.notifications.send_security_notification.assert_called_once()


# ============================================================
# admin_delete_user tests
# ============================================================


@pytest.mark.asyncio
async def test_admin_delete_user_forbidden(service, mock_db, mock_user, mock_request):
    """Test admin_delete_user fails for non-admin."""
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(PermissionDenied):
            await service.admin_delete_user(2, mock_request, mock_user)


@pytest.mark.asyncio
async def test_admin_delete_user_not_found(
    service, mock_db, mock_admin_user, mock_request
):
    """Test admin_delete_user fails when user not found."""
    mock_db.get.return_value = None
    service.repo.get.return_value = None

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(EntityNotFound):
            await service.admin_delete_user(999, mock_request, mock_admin_user)


@pytest.mark.asyncio
async def test_admin_delete_user_self(service, mock_db, mock_admin_user, mock_request):
    """Test admin cannot delete themselves."""
    mock_db.get.return_value = mock_admin_user
    service.repo.get.return_value = mock_admin_user

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(BusinessRuleViolation):
            await service.admin_delete_user(
                mock_admin_user.id, mock_request, mock_admin_user
            )


@pytest.mark.asyncio
async def test_admin_delete_user_success(
    service, mock_db, mock_admin_user, mock_request, mock_user, mock_audit
):
    """Test successful admin user deletion."""
    service.repo.get.return_value = mock_user

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch("app.services.user_service.delete_static_file"):
            result = await service.admin_delete_user(
                mock_user.id, mock_request, mock_admin_user
            )

    assert result["deleted"] is True
    mock_db.commit.assert_called_once()
    mock_audit.log.assert_called()


# ============================================================
# delete_avatar/cover tests
# ============================================================


@pytest.mark.asyncio
async def test_delete_avatar_with_existing(service, mock_db, mock_user):
    """Test delete_avatar when user has avatar."""
    mock_user.avatar_url = "/static/avatars/test.jpg"
    service.repo.get.return_value = mock_user

    with patch("app.services.user_service.delete_static_file") as mock_delete:
        with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
            await service.delete_avatar(mock_user)

    mock_delete.assert_called_once_with("/static/avatars/test.jpg")
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_avatar_without_existing(service, mock_db, mock_user):
    """Test delete_avatar when user has no avatar."""
    mock_user.avatar_url = None
    service.repo.get.return_value = mock_user

    with patch("app.services.user_service.delete_static_file") as mock_delete:
        with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
            await service.delete_avatar(mock_user)

    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_cover_with_existing(service, mock_db, mock_user):
    """Test delete_cover when user has cover."""
    mock_user.cover_url = "/static/covers/test.jpg"
    service.repo.get.return_value = mock_user

    with patch("app.services.user_service.delete_static_file") as mock_delete:
        with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
            await service.delete_cover(mock_user)

    mock_delete.assert_called_once()


# ============================================================
# delete_user_data tests
# ============================================================


@pytest.mark.asyncio
async def test_delete_user_data_no_confirm(service, mock_db, mock_user, mock_request):
    """Test delete_user_data requires confirmation."""
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(BusinessRuleViolation):
            await service.delete_user_data(mock_user, mock_request, confirm=False)


@pytest.mark.asyncio
async def test_delete_user_data_success(
    service, mock_db, mock_user, mock_request, mock_audit
):
    """Test successful user data deletion."""
    service.repo.get.return_value = mock_user

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch("app.services.user_service.delete_static_file"):
            with patch("app.services.user_service.log_data_access"):
                result = await service.delete_user_data(
                    mock_user, mock_request, confirm=True
                )

    assert result.deleted is True
    assert "deleted+" in result.anonymized_email
    mock_db.commit.assert_called_once()


# ============================================================
# upload_avatar tests
# ============================================================


@pytest.mark.asyncio
async def test_upload_avatar_success(service, mock_db, mock_user, mock_request):
    """Test successful avatar upload."""
    service.repo.get.return_value = mock_user
    mock_file = MagicMock()

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch(
            "app.services.user_service.save_upload",
            return_value="/static/avatars/new.jpg",
        ):
            with patch("app.services.user_service.ensure_mfa_relationships_loaded"):
                await service.upload_avatar(mock_user, mock_file)

    assert mock_user.avatar_url == "/static/avatars/new.jpg"
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upload_avatar_commit_failure(service, mock_db, mock_user, mock_request):
    """Test avatar upload rolls back on commit failure."""
    service.repo.get.return_value = mock_user
    mock_user.avatar_url = "/old.jpg"
    mock_db.commit.side_effect = Exception("Commit failed")
    mock_file = MagicMock()

    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with patch(
            "app.services.user_service.save_upload",
            return_value="/static/avatars/new.jpg",
        ):
            with patch("app.services.user_service.delete_static_file") as mock_delete:
                with pytest.raises(Exception, match="Commit failed"):
                    await service.upload_avatar(mock_user, mock_file)

    mock_db.rollback.assert_called_once()
    assert mock_delete.call_count == 2
    mock_delete.assert_any_call("/old.jpg")
    mock_delete.assert_any_call("/static/avatars/new.jpg")
