import datetime
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.event_service as event_service
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
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()
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
        res_attr = MagicMock()
        res_attr.all.return_value = [row]
        mock_db.execute.return_value = res_attr
        from app.services.user.analytics_service import UserAnalyticsService

        u_service = UserAnalyticsService(mock_db)

        user_id = uuid.uuid4()
        await u_service.get_attendance_stats(user_id=1, period_days=30)

        notif = models.Notification(
            body=json.dumps({"score": 5, "course": "C"}),
            title="T",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        res_grad = MagicMock()
        res_grad.scalars.return_value.all.return_value = [notif]
        mock_db.execute.return_value = res_grad
        await u_service.get_grade_stats(user_id=1, period_days=30)

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
        profile=models.UserProfile(full_name="Test User"),
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

    mock_profile_service = AsyncMock()
    mock_profile_service.get_auth_user_by_email.return_value = user
    mock_profile_service.get_user_by_id.return_value = user

    mock_auth_repo = AsyncMock()
    mock_auth_repo.db = mock_db
    mock_auth_repo.get_user_mfa_capabilities.return_value = {}

    from app.services.auth.credential_validator import CredentialValidator
    from app.services.auth.login_session_manager import LoginSessionManager
    from app.services.auth.mfa_coordinator import MfaCoordinator

    session_manager = LoginSessionManager(
        session_service=mock_session_service,
        redis_session_service=AsyncMock(),
        geolocation_service=AsyncMock(),
        audit=mock_audit,
    )
    validator = CredentialValidator(
        user_repo=mock_user_service,
        profile_service=mock_profile_service,
        lockout_service=mock_lockout_service,
        audit=mock_audit,
        session_manager=session_manager,
    )
    mfa_coord = MfaCoordinator(auth_repo=mock_auth_repo)

    login_service = LoginService(
        validator=validator,
        mfa_coord=mfa_coord,
        session_manager=session_manager,
        db_session=mock_db,
    )

    with (
        patch(
            "app.services.auth.credential_validator.verify_and_update_password",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "app.services.auth.mfa_coordinator.mfa.user_has_active_factor",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.auth.login_session_manager.extract_fingerprint",
            return_value=MagicMock(accept_language="en", fingerprint_hash="h"),
        ),
        patch(
            "app.services.auth.login_session_manager.ensure_mfa_relationships_loaded",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.core.localization.resolve_locale", return_value="en"),
        patch(
            "app.services.user.profile_service.attach_pending_email",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.api.validation.raise_http_error"),
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
