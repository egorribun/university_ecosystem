import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from pydantic import ValidationError

import app.models as models
from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityNotFound,
    PermissionDenied,
)
from app.schemas import schemas
from app.schemas.dtos import UserDTO
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_user_service_mega():
    audit = MagicMock()
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    notifications = AsyncMock()
    repo = AsyncMock()
    repo.add = MagicMock()
    repo.add_all = MagicMock()
    repo._to_dto = MagicMock()
    mock_uow = AsyncMock()
    mock_uow.users = repo
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=None)
    mock_uow.commit = AsyncMock()
    mock_uow.rollback = AsyncMock()
    service = UserService(mock_uow, audit, notifications)

    admin_user = models.User(
        id=uuid.uuid4(),
        email="admin@e.com",
        role="admin",
        is_active=True,
        mfa_required=False,
        mfa_epoch=0,
        _allow_system_managed_assignment=True,
    )
    admin_dto = UserDTO.model_validate(admin_user, from_attributes=True)
    student_user = models.User(
        id=uuid.uuid4(),
        email="s@e.com",
        role="student",
        is_active=True,
        mfa_required=False,
        mfa_epoch=0,
        _allow_system_managed_assignment=True,
    )
    student_dto = UserDTO.model_validate(student_user, from_attributes=True)
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers.get.return_value = "PyTest"

    # 2. update_user_profile - duplicate email
    with pytest.raises(ValidationError, match="use /users/me/email"):
        schemas.UserProfileUpdate(email="taken@e.com")
    mock_res_dup = MagicMock()
    mock_res_dup.scalar_one_or_none.return_value = 3
    db.execute.return_value = mock_res_dup
    file = MagicMock(spec=UploadFile)
    repo.get.return_value = student_dto
    repo._get_orm.return_value = student_user
    # Commit is routed through service.uow.commit() after refactor.
    mock_uow.commit.side_effect = BusinessRuleViolation("db error")
    repo.check_email_exists.return_value = True
    with (
        patch("app.services.user.media_service.save_upload", return_value="/url"),
        patch(
            "app.services.user.media_service.delete_static_file", new_callable=AsyncMock
        ) as m_del,
        patch("app.services.user.profile_service.resolve_locale", return_value="en"),
    ):
        with pytest.raises(Exception, match="db error"):
            await service.upload_avatar(student_user, file)
        mock_uow.rollback.assert_called()
        m_del.assert_called_with("/url")

        # upload_cover error
        with pytest.raises(Exception, match="db error"):
            await service.upload_cover(student_user, file)

    # 4. admin create_user branches
    mock_uow.commit.side_effect = None
    repo.check_email_exists.return_value = False
    data_user = schemas.UserCreate(
        email="n@e.com",
        password="StrongP@ssw0rd!",
        full_name="N",
        role="teacher",
        invite_code="inv",
    )
    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        # Forbidden
        with pytest.raises(PermissionDenied):
            await service.create_user(data_user, request, student_user)

        # Missing invite code
        data_user.invite_code = None
        with pytest.raises(BusinessRuleViolation):
            await service.create_user(data_user, request, admin_user)

        # Invalid invite code
        data_user.invite_code = "inv"
        repo.get_invite_code.return_value = None
        mock_invite_res = MagicMock()
        mock_invite_res.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_invite_res
        with pytest.raises(BusinessRuleViolation):
            await service.create_user(data_user, request, admin_user)

    # 5. admin_update_user - MFA reset
    data_update = schemas.UserAdminUpdate(reset_mfa=True)
    db_user = models.User(
        id=uuid.uuid4(),
        email="u@e.com",
        role="student",
        is_active=True,
        mfa_required=False,
        mfa_epoch=0,
        _allow_system_managed_assignment=True,
    )
    repo.get.return_value = UserDTO.model_validate(db_user, from_attributes=True)
    repo.get_orm_for_update_with_relations.return_value = db_user
    repo._to_dto.return_value = UserDTO.model_validate(db_user, from_attributes=True)
    with (
        patch("app.auth.mfa.reset_user_mfa", new_callable=AsyncMock) as m_reset,
        patch("app.services.user.profile_service.resolve_locale", return_value="en"),
        patch(
            "app.services.notification_service.create_notifications_for_users",
            new_callable=AsyncMock,
        ),
    ):
        m_reset.return_value = MagicMock(changed=True, session_revocations=[])
        await service.admin_update_user(3, data_update, request, admin_user)
        service.notifications.send_security_notification.assert_called_once()

    # 6. admin_delete_user - forbidden/self/not found
    with patch("app.services.user.profile_service.resolve_locale", return_value="en"):
        # self deletion check
        repo.get.side_effect = None
        repo.get.return_value = admin_dto
        repo._get_orm.return_value = admin_user
        with pytest.raises(BusinessRuleViolation):
            await service.admin_delete_user(admin_user.id, request, admin_user)

        # not found check
        repo.get.return_value = None
        repo._get_orm.return_value = None
        with pytest.raises(EntityNotFound):
            await service.admin_delete_user(999, request, admin_user)

        # forbidden check
        with pytest.raises(PermissionDenied):
            await service.admin_delete_user(3, request, student_user)

    # 7. data_export - full
    repo.get.return_value = UserDTO.model_validate(student_user, from_attributes=True)
    repo.get_user_sessions.return_value = [
        MagicMock(
            id=uuid.uuid4(),
            ip_address="1.1.1.1",
            created_at=datetime.datetime.now(datetime.UTC),
            expires_at=None,
            revoked_at=None,
            user_agent="Mock",
            last_seen_at=None,
            mfa_completed_at=None,
        )
    ]
    repo.get_user_notifications.return_value = [
        MagicMock(
            id=uuid.uuid4(), title="T", created_at=datetime.datetime.now(datetime.UTC)
        )
    ]
    repo.get_user_access_logs.return_value = [
        MagicMock(
            id=uuid.uuid4(),
            resource_type="users",
            action="access",
            created_at=datetime.datetime.now(datetime.UTC),
        )
    ]
    repo.get_user_mfa_challenges.return_value = []
    repo.get_user_totp_enrollments.return_value = []
    with (
        patch(
            "app.services.user.compliance_service.log_data_access",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.user.profile_service.attach_pending_email",
            new_callable=AsyncMock,
        ),
        patch(
            "app.schemas.schemas.UserOut.model_validate",
            return_value=MagicMock(model_dump=lambda: {}),
        ),
    ):
        export = await service.export_user_data(student_user, request)
        assert len(export.sessions) == 1
        assert len(export.notifications) == 1
        assert len(export.access_logs) == 1


@pytest.mark.asyncio
async def test_service_advanced_branches():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()

    # 1. get_events with cursor
    from app.repositories.event_repository import EventRepository
    from app.services.event_service import EventService
    from app.services.vector_service import VectorService
    from app.utils.pagination import encode_datetime_cursor as _encode_event_cursor

    e_repo = EventRepository(db)
    mock_uow_events = AsyncMock()
    mock_uow_events.events = e_repo
    mock_uow_events.__aenter__ = AsyncMock(return_value=mock_uow_events)
    mock_uow_events.__aexit__ = AsyncMock(return_value=None)
    mock_uow_events.commit = AsyncMock()
    e_service = EventService(mock_uow_events, VectorService(db))

    cursor = _encode_event_cursor(
        datetime.datetime.now(datetime.UTC), str(uuid.uuid4())
    )
    mock_res_events = MagicMock()
    mock_res_events.all.return_value = []
    db.execute.return_value = mock_res_events

    items = await e_service.get_events(cursor=cursor, limit=10)
    assert items.items == []

    # 2. decode_datetime_cursor error paths
    from app.utils.pagination import decode_datetime_cursor

    assert decode_datetime_cursor("") is None
    assert decode_datetime_cursor("not-colon") is None
    assert decode_datetime_cursor("notint:1") is None
