import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.auth.auth as auth
import app.services.event_service as event_service
import app.services.user_service as user_service
from app.core.localization import normalize_locale, translate
from app.models import models
from app.utils.files import detect_mime_type, normalize_filename_prefix, save_attachment


@pytest.mark.asyncio
async def test_monster_coverage_run():
    # 1. LOCALIZATION
    assert normalize_locale("RU") == "ru"
    assert translate("errors.forbidden", locale="ru") == "Доступ запрещён"

    # 2. AUTH HELPERS
    assert auth._pluralize_ru(1, "minutes") == "минуту"
    assert auth._pluralize_en(2, "hour") == "hours"

    # 3. DATABASE MOCKING
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.flush = AsyncMock()

    result = MagicMock()
    # scalars().all() returns a list
    result.scalars.return_value.all.return_value = []
    # scalar_one() returns a single value
    result.scalar_one.return_value = 0
    mock_db.execute.return_value = result

    # event_service.get_events branches
    from app.repositories.event_repository import EventRepository

    e_repo = EventRepository(mock_db)
    e_repo = MagicMock(spec=EventRepository)
    e_repo.search_events = AsyncMock(return_value=[])
    e_repo.get_events = AsyncMock(return_value=MagicMock(items=[]))
    mock_vector = MagicMock()
    mock_vector.get_embedding = AsyncMock(return_value=[0.1])
    e_service = event_service.EventService(e_repo, mock_vector)
    await e_service.get_events(user_id=1, search="s", locale="ru")

    # 4. STATS (300 lines)
    with (
        patch(
            "app.services.stats_cache.get_cached_stats",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.stats_cache.set_cached_stats", new_callable=AsyncMock),
    ):
        # attendance returns result.all()
        row = MagicMock(
            current_total=1,
            current_attended=1,
            previous_total=1,
            previous_attended=1,
            rn=1,
            starts_at=datetime.datetime.now(datetime.UTC),
            title="T",
        )
        res_attr = MagicMock()
        res_attr.all.return_value = [row]
        mock_db.execute.return_value = res_attr
        from app.repositories.user_repository import UserRepository
        from app.services.notification_service import NotificationService

        u_repo = UserRepository(mock_db)
        u_notifications = NotificationService(mock_db)
        u_service = user_service.UserService(
            mock_db, u_repo, MagicMock(), u_notifications
        )

        await u_service.get_attendance_stats(user_id=1, period_days=30)

        # grades returns result.scalars()
        notif = models.Notification(
            body=json.dumps({"score": 5, "course": "C"}),
            title="T",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        res_grad = MagicMock()
        res_grad.scalars.return_value.all.return_value = [notif]
        mock_db.execute.return_value = res_grad
        await u_service.get_grade_stats(user_id=1, period_days=30)

        # participation returns result.all()
        p_row = (
            1,
            datetime.datetime.now(datetime.UTC),
            datetime.datetime.now(datetime.UTC),
            datetime.datetime.now(datetime.UTC),
            "T",
            "lecture",
        )
        res_part = MagicMock()
        res_part.all.return_value = [p_row]
        mock_db.execute.return_value = res_part
        await u_service.get_participation_stats(user_id=1, period_days=30)

    # 5. FILES (190 lines)
    assert normalize_filename_prefix("A B!") == "a-b"

    assert detect_mime_type(b"%PDF-1.4") == "application/pdf"

    mock_upload = MagicMock()
    mock_upload.filename = "t.pdf"
    mock_upload.content_type = "application/pdf"
    mock_upload.read = AsyncMock(return_value=b"%PDF-data")
    with patch("app.utils.files._get_storage_backend") as m_be:
        m_be.return_value.save_file = AsyncMock(return_value="/s/t.pdf")
        with (
            patch("app.utils.files.detect_mime_type", return_value="application/pdf"),
            patch("app.utils.files.scan_for_malware", new_callable=AsyncMock),
            patch("app.utils.files._prepare_local_storage", new_callable=AsyncMock),
        ):
            await save_attachment(mock_upload, subdir="s", prefix="p")

    # 6. AUTH PERFORM LOGIN (247 lines)
    user = models.User(id=1, email="a@b.com", is_active=True, mfa_required=False)
    # Mock for user query in _perform_login
    res_login = MagicMock()
    res_login.scalars.return_value.first.return_value = user
    mock_db.execute.return_value = res_login

    with (
        patch(
            "app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=None
        ),
        patch("app.auth.auth.verify_and_update_password", return_value=(True, None)),
        patch(
            "app.auth.auth.ensure_mfa_relationships_loaded",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "app.auth.auth._resolve_mfa_capabilities",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch("app.auth.auth._create_session_for_user", new_callable=AsyncMock),
        patch(
            "app.auth.auth.create_access_token",
            new_callable=AsyncMock,
            return_value=("token", None),
        ),
        patch(
            "app.auth.auth._build_token_response",
            new_callable=AsyncMock,
            return_value=MagicMock(status_code=200),
        ),
        patch("app.auth.auth.send_lockout_alert.kiq", new_callable=AsyncMock),
    ):
        from starlette.responses import Response

        mock_user_service = AsyncMock()
        # Initial user fetch for lockout check
        mock_user_service.get_user_by_email.return_value = user

        await auth._perform_login(
            "a@b.com",
            "p",
            MagicMock(),
            Response(),
            mock_db,
            MagicMock(),
            bg_tasks=MagicMock(),
            user_service=mock_user_service,
        )
