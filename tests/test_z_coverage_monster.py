import datetime
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    # 2. AUTH HELPERS - _pluralize methods moved to LockoutService
    from app.services.auth.lockout import LockoutService

    mock_db = MagicMock()
    lockout_svc = LockoutService(mock_db)
    assert lockout_svc._pluralize_ru(1, "minutes") == "минуту"
    assert lockout_svc._pluralize_en(2, "hour") == "hours"

    # 3. DATABASE MOCKING
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.flush = AsyncMock()

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one.return_value = 0
    mock_db.execute.return_value = result

    # event_service.get_events branches
    from app.repositories.event_repository import EventRepository

    e_repo = MagicMock(spec=EventRepository)
    e_repo.search_events = AsyncMock(return_value=[])
    e_repo.get_events = AsyncMock(return_value=MagicMock(items=[]))
    mock_vector = MagicMock()
    mock_vector.get_embedding = AsyncMock(return_value=[0.1])
    e_service = event_service.EventService(e_repo, mock_vector)
    user_id = uuid.uuid4()
    await e_service.get_events(user_id=user_id, search="s", locale="ru")

    # 4. STATS
    with (
        patch(
            "app.services.stats_cache.get_cached_stats",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.stats_cache.set_cached_stats", new_callable=AsyncMock),
    ):
        row = MagicMock(
            current_total=1,
            current_attended=1,
            previous_total=1,
            previous_attended=1,
            rn=1,
            starts_at=datetime.datetime.now(datetime.UTC),
            title="T",
        )
        from app.repositories.user_repository import UserRepository
        from app.services.notification_service import NotificationService

        u_repo = UserRepository(mock_db)
        u_notifications = NotificationService(mock_db)
        audit = MagicMock()
        m_stats_repo = AsyncMock()

        # Configure stats mocks
        m_stats_repo.get_attendance_stats_raw.return_value = [row]

        notif = models.Notification(
            body=json.dumps(
                {
                    "score": 5,
                    "course": "C",
                    "max": 5,
                    "date": datetime.datetime.now(datetime.UTC).isoformat(),
                }
            ),
            title="T",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        m_stats_repo.get_grade_notifications.return_value = [notif]

        p_row = MagicMock(
            id=uuid.uuid4(),
            title="T",
            event_type="lecture",
            starts_at=datetime.datetime.now(datetime.UTC),
            ends_at=datetime.datetime.now(datetime.UTC),
        )
        m_stats_repo.get_participation_stats_raw.return_value = [p_row]

        u_service = user_service.UserService(
            user_repo=u_repo,
            audit=audit,
            notifications=u_notifications,
        )

        user_id = uuid.uuid4()
        await u_service.get_attendance_stats(user_id=user_id, period_days=30)
        await u_service.get_grade_stats(user_id=user_id, period_days=30)
        await u_service.get_participation_stats(user_id=user_id, period_days=30)

    # 5. FILES
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

    # 6. AUTH LOGIN (Refactored for LoginService)
    from app.services.auth.login_service import LoginService

    user = models.User(
        id=uuid.uuid4(),
        email="a@b.com",
        is_active=True,
        mfa_required=False,
        role="student",
        full_name="Test User",
    )

    mock_user_service = AsyncMock()
    mock_user_service.get_user_by_email.return_value = user

    mock_session_service = AsyncMock()
    mock_session_service.create_access_token.return_value = (
        "token",
        MagicMock(signing_key=None),
    )

    mock_lockout_service = AsyncMock()
    mock_lockout_service.get_active_lockout.return_value = None
    mock_lockout_service.clear_failed_attempts.return_value = 0

    mock_audit = MagicMock()

    login_service = LoginService(
        db=mock_db,
        user_service=mock_user_service,
        session_service=mock_session_service,
        lockout_service=mock_lockout_service,
        audit=mock_audit,
    )

    with (
        patch(
            "app.services.auth.login_service.verify_and_update_password",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "app.services.auth.login_service.mfa.user_has_active_factor",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.auth.login_service.extract_fingerprint",
            return_value=MagicMock(accept_language="en", fingerprint_hash="h"),
        ),
        patch(
            "app.services.auth.login_service.ensure_mfa_relationships_loaded",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "app.services.auth_service.attach_pending_email",
            new_callable=AsyncMock,
            return_value=user,
        ),
    ):
        from fastapi import BackgroundTasks, Request, Response

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"

        await login_service.perform_login(
            email="a@b.com",
            password="p",
            request=mock_request,
            response=Response(),
            bg_tasks=BackgroundTasks(),
        )
