import gc
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.core.exceptions.domain import (
    EntityNotFound,
    PermissionDenied,
)
from app.models import (
    User,
    UserProfile,
)
from app.schemas.dtos import UserDTO
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService


@pytest.fixture
def mock_uow():
    uow = AsyncMock()
    users = MagicMock()
    users.get_orm_for_update_with_relations = AsyncMock()
    users._get_orm = AsyncMock()
    users.delete_sensitive_data = AsyncMock()
    users._to_dto = MagicMock()
    users.add = MagicMock()
    uow.users = users
    uow.__aenter__.return_value = uow
    return uow


@pytest.fixture
def mock_db():
    return AsyncMock()


# --- MediaService Tests ---


@pytest.mark.asyncio
async def test_upload_avatar_success(mock_uow, monkeypatch):
    user_id = uuid.uuid4()
    mock_user = User(id=user_id)
    mock_user.profile = UserProfile(avatar_url="old_url")
    mock_uow.users.get_orm_for_update_with_relations.return_value = mock_user
    mock_uow.users._to_dto.return_value = MagicMock(spec=UserDTO)

    mock_save = AsyncMock(return_value="new_url")
    monkeypatch.setattr("app.services.user.media_service.save_upload", mock_save)
    mock_delete = AsyncMock()
    monkeypatch.setattr(
        "app.services.user.media_service.delete_static_file", mock_delete
    )

    mock_update = MagicMock()
    monkeypatch.setattr(
        "app.services.user.media_service.update_user_attributes", mock_update
    )

    svc = UserMediaService(mock_uow)
    file_mock = MagicMock(spec=UploadFile)

    res = await svc.upload_avatar(user_id, file_mock)

    assert res is not None
    mock_delete.assert_called_once_with("old_url")
    mock_update.assert_called_once_with(mock_user, {"avatar_url": "new_url"})
    mock_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upload_avatar_not_found(mock_uow):
    mock_uow.users.get_orm_for_update_with_relations.return_value = None
    svc = UserMediaService(mock_uow)

    with pytest.raises(EntityNotFound):
        await svc.upload_avatar(uuid.uuid4(), MagicMock(spec=UploadFile))


@pytest.mark.asyncio
async def test_delete_avatar(mock_uow, monkeypatch, recwarn):
    user_id = uuid.uuid4()
    mock_user = User(id=user_id)
    mock_user.profile = UserProfile(avatar_url="to_delete")
    mock_uow.users.get_orm_for_update_with_relations.return_value = mock_user
    mock_uow.users._to_dto.return_value = MagicMock(spec=UserDTO)

    mock_delete = AsyncMock()
    monkeypatch.setattr(
        "app.services.user.media_service.delete_static_file", mock_delete
    )

    mock_update = MagicMock()
    monkeypatch.setattr(
        "app.services.user.media_service.update_user_attributes", mock_update
    )

    svc = UserMediaService(mock_uow)
    await svc.delete_avatar(user_id)
    gc.collect()

    mock_delete.assert_called_once_with("to_delete")
    mock_update.assert_called_once_with(mock_user, {"avatar_url": None})
    mock_uow.commit.assert_called_once()
    assert not any(issubclass(warning.category, RuntimeWarning) for warning in recwarn)


# --- ComplianceService Tests ---


@pytest.mark.asyncio
async def test_admin_delete_user(mock_uow, monkeypatch):
    mock_audit = MagicMock()
    svc = UserComplianceService(mock_uow, mock_audit)

    mock_current_user = MagicMock(role="admin")
    mock_current_user.id = uuid.uuid4()

    target_user_id = uuid.uuid4()
    mock_db_user = User(id=target_user_id)
    mock_uow.users._get_orm.return_value = mock_db_user

    mock_anonymize = AsyncMock()
    monkeypatch.setattr(
        "app.services.user.compliance_service.anonymize_user_data", mock_anonymize
    )

    mock_revoke = AsyncMock()
    monkeypatch.setattr(svc, "_revoke_user_sessions", mock_revoke)

    res = await svc.admin_delete_user(
        user_id=target_user_id, request=MagicMock(), current_user=mock_current_user
    )

    assert res["deleted"] is True
    mock_anonymize.assert_called_once()
    mock_revoke.assert_called_once_with(target_user_id)
    mock_uow.users.delete_sensitive_data.assert_called_once_with(target_user_id)
    mock_uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_admin_delete_user_not_admin(mock_uow):
    svc = UserComplianceService(mock_uow, MagicMock())
    with pytest.raises(PermissionDenied):
        await svc.admin_delete_user(
            uuid.uuid4(), MagicMock(), MagicMock(role="student")
        )
