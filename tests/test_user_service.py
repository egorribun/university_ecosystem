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
    result = MagicMock()
    result.rowcount = 0
    db.execute.return_value = result
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
    repo._get_orm = AsyncMock()
    # W185 twin-bug fix: profile/media update paths now fetch via the eager-
    # loading get_orm_for_update_with_relations. Alias it to the same mock so
    # existing `repo._get_orm.return_value = ...` setups configure both (no call-
    # arg assertions on _get_orm exist, so aliasing is safe).
    repo.get_orm_for_update_with_relations = repo._get_orm
    repo._to_dto = MagicMock()
    repo.add = MagicMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_uow(mock_repo, mock_db):
    """Create mock UnitOfWork."""
    uow = AsyncMock()
    uow.users = mock_repo
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    # Handle context manager protocol
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    return uow


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
    user.hashed_password = "hashed_password"
    # Setup profile mock
    user.profile = MagicMock()
    user.profile.avatar_url = None
    user.profile.cover_url = None
    user.profile.full_name = "Test User"
    user.profile.about = None
    user.profile.telegram = None

    user.preferences = MagicMock()
    user.preferences.timezone = "UTC"
    user.preferences.dnd_enabled = False

    user.education_path = MagicMock()
    user.education_path.institute = None

    user.mfa_challenges = []
    user.totp_enrollments = []
    user.otp_enrollments = []
    return user


# ... (skipping unchanged parts) ...


@pytest.mark.asyncio
async def test_delete_avatar_with_existing(service, mock_db, mock_user):
    """Test delete_avatar when user has avatar."""
    mock_user.profile.avatar_url = "/static/avatars/test.jpg"
    mock_user.avatar_url = "/static/avatars/test.jpg"
    service.repo._get_orm.return_value = mock_user
    service.repo._to_dto.return_value = mock_user

    with patch("app.services.user.media_service.delete_static_file") as mock_delete:
        await service.delete_avatar(mock_user)

    mock_delete.assert_called_once_with("/static/avatars/test.jpg")
    service.uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_avatar_without_existing(service, mock_db, mock_user):
    """Test delete_avatar when user has no avatar."""
    mock_user.profile.avatar_url = None
    mock_user.avatar_url = None
    service.repo._get_orm.return_value = mock_user
    service.repo._to_dto.return_value = mock_user

    with patch("app.services.user.media_service.delete_static_file") as mock_delete:
        await service.delete_avatar(mock_user)

    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_cover_with_existing(service, mock_db, mock_user):
    """Test delete_cover when user has cover."""
    mock_user.profile.cover_url = "/static/covers/test.jpg"
    service.repo._get_orm.return_value = mock_user
    service.repo._to_dto.return_value = mock_user

    with patch("app.services.user.media_service.delete_static_file") as mock_delete:
        await service.delete_cover(mock_user)

    mock_delete.assert_called_once()


# ... (skipping unchanged parts) ...


@pytest.mark.asyncio
async def test_upload_avatar_success(service, mock_db, mock_user, mock_request):
    """Test successful avatar upload."""
    service.repo._get_orm.return_value = mock_user
    mock_file = MagicMock()
    mock_file.content_type = "image/jpeg"

    # Create an updated user mock to return from repo._to_dto
    updated_user = MagicMock()
    updated_user.profile.avatar_url = "/static/avatars/new.jpg"
    service.repo._to_dto.return_value = updated_user

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        with patch(
            "app.services.user.media_service.save_upload",
            return_value="/static/avatars/new.jpg",
        ):
            result = await service.upload_avatar(mock_user, mock_file)

    assert result.profile.avatar_url == "/static/avatars/new.jpg"
    service.uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upload_avatar_commit_failure(service, mock_db, mock_user, mock_request):
    """Test avatar upload rolls back on commit failure."""
    service.repo._get_orm.return_value = mock_user
    mock_user.profile.avatar_url = "/old.jpg"
    service.uow.commit.side_effect = Exception("Commit failed")
    mock_file = MagicMock()
    mock_file.content_type = "image/jpeg"

    # Ensure current state is mocked for UserMediaService.delete_avatar check
    mock_user.avatar_url = "/old.jpg"

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        with patch(
            "app.services.user.media_service.save_upload",
            return_value="/static/avatars/new.jpg",
        ):
            with patch(
                "app.services.user.media_service.delete_static_file"
            ) as mock_delete:
                with pytest.raises(Exception, match="Commit failed"):
                    await service.upload_avatar(mock_user, mock_file)

    service.uow.rollback.assert_called_once()
    assert mock_delete.call_count == 2
    mock_delete.assert_any_call("/old.jpg")
    mock_delete.assert_any_call("/static/avatars/new.jpg")


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
def service(mock_uow, mock_db, mock_repo, mock_audit, mock_notifications, monkeypatch):
    mock_repo.db = mock_db
    s = UserService(
        uow=mock_uow,
        audit=mock_audit,
        notifications=mock_notifications,
    )
    # Mock result chaining for repo.db
    result = MagicMock()
    result.rowcount = 0
    result.scalars.return_value = MagicMock()
    result.scalars.return_value.first.return_value = None
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    # Mock attach_pending_email to avoid cascaded repo calls in unit tests
    async def mock_attach(_db, user):
        return user

    monkeypatch.setattr(
        "app.services.user.profile_service.attach_pending_email", mock_attach
    )

    return s


# ============================================================
# update_user_profile tests
# ============================================================


@pytest.mark.asyncio
async def test_update_user_profile_success(service, mock_db, mock_user, mock_request):
    """Test successful profile update."""
    service.repo.get.return_value = mock_user
    data = MagicMock()
    data.model_dump.return_value = {"full_name": "New Name"}

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        service.repo._get_orm.return_value = mock_user
        service.repo._to_dto.return_value = mock_user
        result = await service.update_user_profile(mock_user, data, mock_request)

    assert result.id == mock_user.id
    service.uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_profile_schema_rejects_email() -> None:
    """The generic profile contract rejects email before service dispatch."""
    with pytest.raises(ValueError, match="use /users/me/email"):
        schemas.UserProfileUpdate.model_validate({"email": "not-an-email"})


@pytest.mark.asyncio
async def test_update_user_profile_does_not_query_email_uniqueness(
    service, mock_db, mock_user, mock_request
):
    """Ordinary profile fields do not enter the controlled email-change path."""
    service.repo.get.return_value = mock_user
    data = MagicMock()
    data.model_dump.return_value = {"full_name": "Updated Name"}
    service.repo._get_orm.return_value = mock_user
    service.repo._to_dto.return_value = mock_user

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        await service.update_user_profile(mock_user, data, mock_request)

    service.repo.check_email_exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_profile_preferences(
    service, mock_db, mock_user, mock_request
):
    """Test profile update with preferences fields."""
    service.repo.get.return_value = mock_user
    data = MagicMock()
    data.model_dump.return_value = {"dnd_enabled": True, "timezone": "UTC"}

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        service.repo._get_orm.return_value = mock_user
        await service.update_user_profile(mock_user, data, mock_request)

    service.uow.commit.assert_called_once()


# ============================================================
# create_user tests
# ============================================================


@pytest.mark.asyncio
async def test_create_user_forbidden_non_admin(
    service, mock_db, mock_user, mock_request
):
    """Test create_user fails for non-admin."""
    data = MagicMock()

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

    service.repo.db.execute.return_value.scalars.return_value.first.return_value = (
        None  # Changed from mock_db.execute
    )

    result = await service.create_user(data, mock_request, mock_admin_user)

    assert result.id == 100


# ============================================================
# get_users tests
# ============================================================


@pytest.mark.asyncio
async def test_get_users_non_admin_no_search(service, mock_db, mock_user, mock_request):
    """Test get_users fails for non-admin without search."""
    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        with pytest.raises(PermissionDenied):
            await service.get_users(mock_request, mock_user)


@pytest.mark.asyncio
async def test_get_users_non_admin_with_search(
    service, mock_db, mock_user, mock_request
):
    service.repo.list_users.return_value = []

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
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

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
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

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        with pytest.raises(PermissionDenied):
            await service.admin_update_user(2, data, mock_request, mock_user)


@pytest.mark.asyncio
async def test_admin_update_user_success(
    service, mock_db, mock_admin_user, mock_request, mock_audit
):
    """Test successful admin user update."""
    data = MagicMock()
    data.model_dump.return_value = {}
    updated_user = MagicMock()
    import uuid

    target_uuid = uuid.uuid4()
    updated_user.id = target_uuid

    service.repo.get.return_value = updated_user

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        # Mock database rowcount for reset_user_mfa check
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        service.repo._get_orm.return_value = updated_user
        service.repo._to_dto.return_value = updated_user
        result = await service.admin_update_user(
            target_uuid, data, mock_request, mock_admin_user
        )

    assert result.id == target_uuid
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

    import uuid

    target_uuid = uuid.uuid4()
    updated_user.id = target_uuid
    service.repo.get.return_value = updated_user

    # Mock database rowcount for reset_user_mfa check
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_db.execute.return_value = mock_result
    data.model_dump.return_value = {"reset_mfa": True}

    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        with patch("app.auth.mfa.reset_user_mfa", return_value=reset_stats):
            service.repo._get_orm.return_value = updated_user
            service.repo._to_dto.return_value = updated_user
            await service.admin_update_user(
                target_uuid, data, mock_request, mock_admin_user
            )

    service.notifications.send_security_notification.assert_called_once()


# ============================================================
# admin_delete_user tests
# ============================================================


@pytest.mark.asyncio
async def test_admin_delete_user_forbidden(service, mock_db, mock_user, mock_request):
    """Test admin_delete_user fails for non-admin."""
    import uuid

    target_uuid = uuid.uuid4()
    with pytest.raises(PermissionDenied):
        await service.admin_delete_user(target_uuid, mock_request, mock_user)


@pytest.mark.asyncio
async def test_admin_delete_user_not_found(
    service, mock_db, mock_admin_user, mock_request
):
    """Test admin_delete_user fails when user not found."""
    service.repo._get_orm.return_value = None
    service.repo.get.return_value = None

    with pytest.raises(EntityNotFound):
        await service.admin_delete_user(999, mock_request, mock_admin_user)


@pytest.mark.asyncio
async def test_admin_delete_user_self(service, mock_db, mock_admin_user, mock_request):
    """Test admin cannot delete themselves."""
    service.repo._get_orm.return_value = mock_admin_user
    service.repo.get.return_value = mock_admin_user

    with pytest.raises(BusinessRuleViolation):
        await service.admin_delete_user(
            mock_admin_user.id, mock_request, mock_admin_user
        )


@pytest.mark.asyncio
async def test_admin_delete_user_success(
    service, mock_db, mock_admin_user, mock_request, mock_user, mock_audit
):
    """Test successful admin user deletion."""
    service.repo._get_orm.return_value = mock_user
    service.repo.get.return_value = mock_user

    result = await service.admin_delete_user(
        mock_user.id, mock_request, mock_admin_user
    )

    assert result["deleted"] is True
    service.uow.commit.assert_called_once()
    mock_audit.log.assert_called()


# ============================================================
# delete_avatar/cover tests
