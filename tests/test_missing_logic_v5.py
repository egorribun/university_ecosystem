import base64
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.auth.auth as auth
from app.models import models
from app.schemas import schemas


@pytest.mark.asyncio
async def test_service_missing_branches():
    # 1. _decode_event_cursor error paths
    from app.utils.pagination import decode_datetime_cursor as _decode_event_cursor

    assert _decode_event_cursor("") is None
    assert _decode_event_cursor("invalid-base64") is None
    assert _decode_event_cursor(base64.urlsafe_b64encode(b"[]").decode()) is None

    # 2. sanitize_optional_text
    from app.utils.sanitization import sanitize_optional_text

    assert sanitize_optional_text(None) is None
    assert sanitize_optional_text(b"hello") == "hello"
    assert (
        sanitize_optional_text(b"\xff") is None
    )  # Decodes to empty string with 'ignore', then stripped
    assert sanitize_optional_text("") is None
    assert sanitize_optional_text(123) == "123"

    # 3. create_user/register_user error paths
    from app.services.user_service import UserService

    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    repo = AsyncMock()
    audit = MagicMock()
    notifications = AsyncMock()
    service = UserService(db, repo, audit, notifications)

    user_in = schemas.UserCreate(
        email="test@e.com",
        password="password123",
        full_name="Test",
        role="admin",
        invite_code="secret",
    )

    # Invalid invite code branch
    from app.core.exceptions.domain import BusinessRuleViolation, EntityAlreadyExists

    repo.get_invite_code.return_value = None
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(BusinessRuleViolation) as exc:
            await service.register_user(user_in)
    assert any(x in str(exc.value).lower() for x in ["инвайт", "invite"])

    # Email in use branch
    repo.get_invite_code.return_value = MagicMock(
        role="admin", is_active=True, is_used=False
    )
    repo.check_email_exists.return_value = True
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        with pytest.raises(EntityAlreadyExists) as exc:
            await service.register_user(user_in)
    assert any(
        x in str(exc.value).lower() for x in ["используется", "already", "in use"]
    )

    # 4. create_news
    from app.services.news_service import NewsService
    from app.services.vector_service import VectorService

    n_repo = AsyncMock()
    n_service = NewsService(n_repo, VectorService(db))
    news_in = schemas.NewsCreate(title="T", content="C")

    # Mock the repo.create to return a news object
    mock_news = models.News(id=1, title="T")
    n_repo.create.return_value = mock_news

    await n_service.create_news(news_in)
    n_repo.create.assert_called()


@pytest.mark.asyncio
async def test_auth_missing_branches():
    # 1. _format_duration
    assert auth._format_duration("en", 3600) == "1 hour"
    assert auth._format_duration("ru", 3600) == "1 час"
    assert auth._format_duration("en", 3661) == "2 hours"
    assert auth._format_duration("ru", 3661) == "2 часа"
    assert auth._format_duration("ru", 18000) == "5 часов"

    # 2. Lockout message
    lock_until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
    detail, retry = auth._lockout_message("ru", lock_until)
    assert "заблокирован" in detail
    assert retry > 0

    # 3. Perform login error paths
    db = AsyncMock()
    audit = MagicMock()
    request = MagicMock()
    response = MagicMock()

    # Default mock result to avoid 'coroutine' object errors
    def make_mock_res(user=None):
        m = MagicMock()
        m.scalars.return_value.first.return_value = user
        return m

    # Locked out
    db.execute.return_value = make_mock_res()
    mock_user_service = AsyncMock()
    mock_user_service.get_user_by_email.return_value = None
    with (
        patch(
            "app.auth.auth._active_lockout",
            new_callable=AsyncMock,
            return_value=lock_until,
        ),
        patch("app.auth.auth.send_lockout_alert.kiq", new_callable=AsyncMock),
    ):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login(
                "a@b.com",
                "p",
                request,
                response,
                db,
                audit,
                bg_tasks=MagicMock(),
                user_service=mock_user_service,
            )
        assert exc.value.status_code == 423

    # User not found (and triggers lockout)
    db.execute.side_effect = [make_mock_res(None), MagicMock()]
    mock_user_service = AsyncMock()
    mock_user_service.get_user_by_email.return_value = None
    with (
        patch(
            "app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=None
        ),
        patch(
            "app.auth.auth._register_failed_attempt",
            new_callable=AsyncMock,
            return_value=(lock_until, True, 5),
        ),
        patch("app.auth.auth.send_lockout_alert.kiq", new_callable=AsyncMock),
    ):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login(
                "not@found.com",
                "p",
                request,
                response,
                db,
                audit,
                bg_tasks=MagicMock(),
                user_service=mock_user_service,
            )
        assert exc.value.status_code == 423

    # Inactive user
    user_inactive = models.User(
        id=1, email="a@b.com", is_active=False, hashed_password="hash"
    )
    db.execute.side_effect = [make_mock_res(user_inactive), MagicMock()]
    mock_user_service = AsyncMock()
    mock_user_service.get_user_by_email.return_value = user_inactive
    with (
        patch(
            "app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=None
        ),
        patch("app.auth.auth.verify_and_update_password", return_value=(True, None)),
        patch("app.auth.auth.send_lockout_alert.kiq", new_callable=AsyncMock),
    ):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login(
                "a@b.com",
                "p",
                request,
                response,
                db,
                audit,
                bg_tasks=MagicMock(),
                user_service=mock_user_service,
            )
        assert exc.value.status_code == 401

    # MFA Missing (user requires MFA but has no methods)
    user_mfa = models.User(
        id=1, email="a@b.com", is_active=True, mfa_required=True, hashed_password="hash"
    )
    mock_res_mfa = make_mock_res(user_mfa)
    mock_res_del = MagicMock()
    mock_res_del.rowcount = 0
    db.execute.side_effect = [mock_res_mfa, mock_res_del, MagicMock()]
    mock_user_service = AsyncMock()
    mock_user_service.get_user_by_email.return_value = user_mfa
    with (
        patch(
            "app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=None
        ),
        patch("app.auth.auth.verify_and_update_password", return_value=(True, None)),
        patch(
            "app.auth.auth.ensure_mfa_relationships_loaded",
            new_callable=AsyncMock,
            return_value=user_mfa,
        ),
        patch(
            "app.auth.auth._resolve_mfa_capabilities",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch("app.auth.auth.send_lockout_alert.kiq", new_callable=AsyncMock),
    ):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login(
                "a@b.com",
                "p",
                request,
                response,
                db,
                audit,
                bg_tasks=MagicMock(),
                user_service=mock_user_service,
            )
        assert exc.value.status_code == 400
