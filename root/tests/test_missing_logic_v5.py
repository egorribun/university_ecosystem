import pytest
import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from app.models import models
from app.schemas import schemas
import app.crud as crud
import app.auth.auth as auth
from app.localization import translate

@pytest.mark.asyncio
async def test_crud_missing_branches():
    # 1. _decode_event_cursor error paths
    assert crud._decode_event_cursor("") is None
    assert crud._decode_event_cursor("invalid-json") is None
    assert crud._decode_event_cursor("[]") is None
    assert crud._decode_event_cursor(json.dumps({"starts_at": 123})) is None
    assert crud._decode_event_cursor(json.dumps({"starts_at": "invalid-date", "id": 1})) is None
    assert crud._decode_event_cursor(json.dumps({"starts_at": "2023-10-10T10:00:00Z", "id": "not-int"})) is None

    # 2. sanitize_optional_text
    assert crud.sanitize_optional_text(None) is None
    assert crud.sanitize_optional_text(b"hello") == "hello"
    assert crud.sanitize_optional_text(b"\xff") is None # Decodes to empty string with 'ignore', then stripped
    assert crud.sanitize_optional_text("") is None
    assert crud.sanitize_optional_text(123) == "123"

    # 3. create_user error paths
    db = AsyncMock()
    user_in = schemas.UserCreate(
        email="test@e.com", 
        password="password123", 
        full_name="Test",
        role="admin",
        invite_code="secret"
    )
    
    # Invalid invite code branch
    mock_res_invite = MagicMock()
    mock_res_invite.scalar_one_or_none.return_value = None
    db.execute.side_effect = [mock_res_invite]
    with pytest.raises(ValueError) as exc:
        await crud.create_user(db, user_in)
    assert any(x in str(exc.value).lower() for x in ["инвайт", "invite"])
        
    # Email in use branch
    user_in_simple = schemas.UserCreate(email="test@e.com", password="password123", full_name="Test")
    mock_res_exists = MagicMock()
    mock_res_exists.scalar_one_or_none.return_value = models.User()
    db.execute.side_effect = [mock_res_exists]
    with pytest.raises(ValueError) as exc:
        await crud.create_user(db, user_in_simple)
    assert any(x in str(exc.value).lower() for x in ["используется", "already", "in use"])

    # 4. create_news
    news_in = schemas.NewsCreate(title="T", content="C")
    db.execute.side_effect = None
    await crud.create_news(db, news_in)
    db.add.assert_called()
    db.commit.assert_called()

    # 5. _is_postgres_session Variations
    db.bind = MagicMock()
    db.bind.dialect.name = "postgresql"
    assert await crud._is_postgres_session(db) is True
    
    db.bind = None
    db.get_bind = AsyncMock()
    db.get_bind.return_value.dialect.name = "sqlite"
    assert await crud._is_postgres_session(db) is False

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
    with patch("app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=lock_until):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login("a@b.com", "p", request, response, db, audit)
        assert exc.value.status_code == 423
        
    # User not found (and triggers lockout)
    db.execute.side_effect = [make_mock_res(None), MagicMock()]
    with patch("app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=None), \
         patch("app.auth.auth._register_failed_attempt", new_callable=AsyncMock, return_value=(lock_until, True, 5)):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login("not@found.com", "p", request, response, db, audit)
        assert exc.value.status_code == 423

    # Inactive user
    user_inactive = models.User(id=1, email="a@b.com", is_active=False, hashed_password="hash")
    db.execute.side_effect = [make_mock_res(user_inactive), MagicMock()]
    with patch("app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=None), \
         patch("app.auth.auth.verify_and_update_password", return_value=(True, None)):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login("a@b.com", "p", request, response, db, audit)
        assert exc.value.status_code == 401

    # MFA Missing (user requires MFA but has no methods)
    user_mfa = models.User(id=1, email="a@b.com", is_active=True, mfa_required=True, hashed_password="hash")
    mock_res_mfa = make_mock_res(user_mfa)
    mock_res_del = MagicMock()
    mock_res_del.rowcount = 0
    db.execute.side_effect = [mock_res_mfa, mock_res_del, MagicMock()]
    with patch("app.auth.auth._active_lockout", new_callable=AsyncMock, return_value=None), \
         patch("app.auth.auth.verify_and_update_password", return_value=(True, None)), \
         patch("app.auth.auth.ensure_mfa_relationships_loaded", new_callable=AsyncMock, return_value=user_mfa), \
         patch("app.auth.auth._resolve_mfa_capabilities", new_callable=AsyncMock, return_value={}):
        with pytest.raises(auth.HTTPException) as exc:
            await auth._perform_login("a@b.com", "p", request, response, db, audit)
        assert exc.value.status_code == 400
