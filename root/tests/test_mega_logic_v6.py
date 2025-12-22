import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

import app.crud as crud
from app.models import models
from app.schemas import schemas
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_user_service_mega():
    audit = MagicMock()
    service = UserService(audit)
    db = AsyncMock()

    admin_user = models.User(id=1, email="admin@e.com", role="admin")
    student_user = models.User(id=2, email="s@e.com", role="student")
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers.get.return_value = "PyTest"

    # 1. update_user_profile - invalid email
    data = schemas.UserProfileUpdate.model_construct(email="invalid")
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await service.update_user_profile(db, student_user, data, request)
        assert exc.value.status_code == 400

    # 2. update_user_profile - duplicate email
    data = schemas.UserProfileUpdate(email="taken@e.com")
    mock_res_dup = MagicMock()
    mock_res_dup.scalar_one_or_none.return_value = 3
    db.execute.return_value = mock_res_dup
    db.get.return_value = student_user
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await service.update_user_profile(db, student_user, data, request)
        assert exc.value.status_code == 400

    # 3. upload_avatar/cover - rollback/error paths
    file = MagicMock(spec=UploadFile)
    db.get.return_value = student_user
    db.commit.side_effect = Exception("db error")
    with (
        patch("app.services.user_service.save_upload", return_value="/url"),
        patch(
            "app.services.user_service.delete_static_file", new_callable=AsyncMock
        ) as m_del,
        patch("app.services.user_service.resolve_locale", return_value="en"),
    ):
        with pytest.raises(Exception):
            await service.upload_avatar(db, student_user, file, request)
        db.rollback.assert_called()
        m_del.assert_called_with("/url")

        # upload_cover error
        with pytest.raises(Exception):
            await service.upload_cover(db, student_user, file, request)

    # 4. admin create_user branches
    db.commit.side_effect = None
    data_user = schemas.UserCreate(
        email="n@e.com",
        password="password123",
        full_name="N",
        role="teacher",
        invite_code="inv",
    )
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        # Forbidden
        with pytest.raises(HTTPException) as exc:
            await service.create_user(db, data_user, request, student_user)
        assert exc.value.status_code == 403

        # Missing invite code
        data_user.invite_code = None
        with pytest.raises(HTTPException) as exc:
            await service.create_user(db, data_user, request, admin_user)
        assert exc.value.status_code == 400

        # Invalid invite code
        data_user.invite_code = "inv"
        mock_invite_res = MagicMock()
        mock_invite_res.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_invite_res
        with pytest.raises(HTTPException) as exc:
            await service.create_user(db, data_user, request, admin_user)
        assert exc.value.status_code == 400

    # 5. admin_update_user - MFA reset
    data_update = schemas.UserAdminUpdate(mfa_reset=True)
    db_user = models.User(id=3, email="u@e.com")
    with (
        patch(
            "app.services.user_service.crud.admin_update_user",
            return_value=(db_user, MagicMock(changed=True)),
        ),
        patch("app.services.user_service.resolve_locale", return_value="en"),
        patch(
            "app.services.user_service.create_notifications_for_users",
            new_callable=AsyncMock,
        ) as m_notif,
    ):
        await service.admin_update_user(db, 3, data_update, request, admin_user)
        m_notif.assert_called_once()

    # 6. admin_delete_user - forbidden/self/not found
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        # self deletion check
        db.get.side_effect = None
        db.get.return_value = admin_user
        with pytest.raises(HTTPException) as exc:
            await service.admin_delete_user(db, 1, request, admin_user)
        assert exc.value.status_code == 400

        # not found check
        db.get.return_value = None
        with pytest.raises(HTTPException) as exc:
            await service.admin_delete_user(db, 999, request, admin_user)
        assert exc.value.status_code == 404

        # forbidden check
        with pytest.raises(HTTPException) as exc:
            await service.admin_delete_user(db, 3, request, student_user)
        assert exc.value.status_code == 403

    # 7. data_export - full
    db.get.return_value = student_user
    mock_res_sessions = MagicMock()
    mock_res_sessions.scalars.return_value = [
        models.ActiveSession(id=1, ip_address="1.1.1.1")
    ]
    mock_res_notifs = MagicMock()
    mock_res_notifs.scalars.return_value = [models.Notification(id=1, title="T")]
    mock_res_logs = MagicMock()
    mock_res_logs.scalars.return_value.all.return_value = [
        models.DataAccessLog(id=1, resource_type="users", action="access")
    ]
    db.execute.side_effect = [
        mock_res_sessions,
        mock_res_notifs,
        mock_res_logs,
        MagicMock(),
    ]  # sessions, notifications, logs, challenges

    with (
        patch(
            "app.services.user_service.ensure_mfa_relationships_loaded",
            new_callable=AsyncMock,
        ),
        patch("app.services.user_service.attach_pending_email", new_callable=AsyncMock),
        patch(
            "app.schemas.schemas.UserOut.from_orm",
            return_value=MagicMock(model_dump=lambda: {}),
        ),
    ):
        export = await service.export_user_data(db, student_user, request)
        assert len(export.sessions) == 1
        assert len(export.notifications) == 1
        assert len(export.access_logs) == 1


@pytest.mark.asyncio
async def test_crud_advanced_branches():
    db = AsyncMock()

    # 1. get_all_events with cursor
    cursor = crud._encode_event_cursor(datetime.datetime.now(datetime.UTC), 10)
    mock_res_events = MagicMock()
    mock_res_events.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_res_events

    paginated = await crud.get_all_events(db, cursor=cursor, limit=10)
    assert paginated.items == []
    assert paginated.next_cursor is None

    # 2. _decode_news_cursor error paths
    assert crud._decode_news_cursor("") is None
    assert crud._decode_news_cursor("not-colon") is None
    assert crud._decode_news_cursor("notint:1") is None
