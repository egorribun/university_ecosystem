from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

from app.core.exceptions.domain import EntityNotFound
from app.models import models
from app.services import data_access
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_notification_service_news_enqueue_failure():
    db = AsyncMock()
    service = NotificationService(db)
    background = MagicMock(spec=BackgroundTasks)
    background.add_task.side_effect = Exception("error")

    # This should trigger line 50-51 (logger.exception)
    await service.dispatch_news_created(1, "en", background)
    background.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_user_service_delete_user_data_not_found():
    db = AsyncMock()
    db.get.return_value = None
    audit = MagicMock(spec=AuditService)
    notifications = MagicMock(spec=NotificationService)
    service = UserService(db, audit, notifications)

    user = models.User(id=999)
    request = MagicMock(spec=Request)

    with pytest.raises(EntityNotFound):
        await service.delete_user_data(user, request, confirm=True)


@pytest.mark.asyncio
async def test_user_service_upload_avatar_refresh_failure():
    db = AsyncMock()
    user = models.User(id=1, avatar_url="old")
    db.get.return_value = user
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=Exception("refresh failed"))

    audit = MagicMock(spec=AuditService)
    notifications = MagicMock(spec=NotificationService)
    service = UserService(db, audit, notifications)

    file = MagicMock()
    file.filename = "test.png"
    file.content_type = "image/png"
    file.read = AsyncMock(return_value=b"data")

    request = MagicMock(spec=Request)

    with (
        patch("app.services.user_service.save_upload", return_value="new_url"),
        patch(
            "app.services.user_service.delete_static_file", new_callable=AsyncMock
        ) as mock_delete,
        patch("app.services.user_service.resolve_locale", return_value="en"),
    ):
        with pytest.raises(Exception, match="refresh failed"):
            await service.upload_avatar(user, file, request)

        assert user.avatar_url == "old"
        mock_delete.assert_called_with("new_url")


@pytest.mark.asyncio
async def test_user_service_upload_cover_refresh_failure():
    db = AsyncMock()
    user = models.User(id=1, cover_url="old")
    db.get.return_value = user
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=Exception("refresh failed"))

    audit = MagicMock(spec=AuditService)
    notifications = MagicMock(spec=NotificationService)
    service = UserService(db, audit, notifications)

    file = MagicMock()
    file.filename = "test.png"
    file.content_type = "image/png"
    file.read = AsyncMock(return_value=b"data")

    request = MagicMock(spec=Request)

    with (
        patch("app.services.user_service.save_upload", return_value="new_url"),
        patch(
            "app.services.user_service.delete_static_file", new_callable=AsyncMock
        ) as mock_delete,
        patch("app.services.user_service.resolve_locale", return_value="en"),
    ):
        with pytest.raises(Exception, match="refresh failed"):
            await service.upload_cover(user, file, request)

        assert user.cover_url == "old"
        mock_delete.assert_called_with("new_url")


@pytest.mark.asyncio
async def test_data_access_batch_log_empty():
    db = AsyncMock()
    request = MagicMock(spec=Request)
    await data_access.batch_log_data_access(db, entries=[], request=request)
    db.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_data_access_log_with_request():
    db = AsyncMock()
    request = MagicMock(spec=Request)
    request.client.host = "1.2.3.4"
    request.headers = {"user-agent": "test-agent"}

    with patch("app.utils.audit.calculate_log_signature", return_value="sig"):
        log = await data_access.log_data_access(
            db,
            actor_user_id=1,
            subject_user_id=2,
            resource_type="test",
            action="view",
            request=request,
        )
        assert log.ip_address == "1.2.3.4"
        assert log.user_agent == "test-agent"
        assert log.signature == "sig"


@pytest.mark.asyncio
async def test_data_access_export_filters():
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_res

    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 2, tzinfo=UTC)

    await data_access.export_access_logs(
        db, start_at=start, end_at=end, actor_user_id=1, subject_user_id=2
    )
    db.execute.assert_called_once()


def test_serialize_access_logs_csv_empty():
    result = data_access.serialize_access_logs_csv([])
    assert "created_at,actor_user_id" in result


def test_normalize_time_naive():
    from app.services.data_access import _normalize_time

    naive = datetime(2023, 1, 1)  # noqa: DTZ001
    normalized = _normalize_time(naive)
    assert normalized.tzinfo == UTC
