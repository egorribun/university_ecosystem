import base64
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    MagicMock()
    service = UserService(repo, audit, notifications)

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
async def test_lockout_service_functions():
    """Test LockoutService format_duration and get_lockout_message methods.

    These functions were previously in auth.py as _format_duration and _lockout_message.
    They were refactored into LockoutService for better separation of concerns.
    """
    from app.services.auth.lockout import LockoutService

    db = AsyncMock()
    lockout = LockoutService(db)

    # 1. format_duration
    assert lockout.format_duration("en", 3600) == "1 hour"
    assert lockout.format_duration("ru", 3600) == "1 час"
    assert lockout.format_duration("en", 3661) == "2 hours"
    assert lockout.format_duration("ru", 3661) == "2 часа"
    assert lockout.format_duration("ru", 18000) == "5 часов"

    # 2. Lockout message
    lock_until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
    with patch("app.services.auth.lockout.translate") as mock_translate:
        mock_translate.return_value = "Аккаунт заблокирован"
        detail, retry = lockout.get_lockout_message("ru", lock_until)
    assert "заблокирован" in detail
    assert retry > 0

    # 3. Edge cases for format_duration
    # Less than 60 seconds
    assert "second" in lockout.format_duration("en", 30)
    # Less than 3600 seconds (minutes)
    assert "minute" in lockout.format_duration("en", 120)

    # 4. Pluralization edge cases
    assert lockout._pluralize_en(1, "hours") == "hour"
    assert lockout._pluralize_en(2, "hours") == "hours"
    assert lockout._pluralize_ru(1, "hours") == "час"
    assert lockout._pluralize_ru(2, "hours") == "часа"
    assert lockout._pluralize_ru(5, "hours") == "часов"
    assert lockout._pluralize_ru(11, "hours") == "часов"  # 11-14 exception
    assert lockout._pluralize_ru(21, "hours") == "час"  # 21 ends in 1
