from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.notifications import (
    _coerce_int,
    _decode_cursor,
    _is_missing_column_error,
    _parse_datetime,
)
from app.models import models


@pytest.mark.asyncio
async def test_notifications_helper_logic():
    # _is_missing_column_error
    exc = SQLAlchemyError()
    exc.orig = MagicMock()
    exc.orig.__str__ = MagicMock(return_value="no such column: test")
    assert _is_missing_column_error(exc) is True

    exc.orig.__str__ = MagicMock(return_value="other error")
    assert _is_missing_column_error(exc) is False

    # _parse_datetime
    assert _parse_datetime(None) is None
    assert _parse_datetime(123) is not None
    assert _parse_datetime("invalid") is None
    assert _parse_datetime(" ") is None
    assert _parse_datetime("1234567890123.0") is not None  # ms branch

    # _coerce_int
    assert _coerce_int(None, 10) == 10
    assert _coerce_int(True) == 1
    assert _coerce_int(False) == 0
    assert _coerce_int(1.5) == 1
    assert _coerce_int("abc") == 0
    assert _coerce_int("") == 0

    # _decode_cursor
    assert _decode_cursor("invalid") is None
    assert _decode_cursor("2023-10-10T10:00:00Z:abc") is None


@pytest.mark.asyncio
async def test_mark_read_single_forbidden(
    root_client: AsyncClient, db_session, user_factory
):
    user1 = await user_factory()
    user2 = await user_factory()

    notif = models.Notification(user_id=user1.id, title="Test", body="Test")
    db_session.add(notif)
    await db_session.commit()
    await db_session.refresh(notif)

    from app.auth.security import create_access_token

    token2, _ = await create_access_token(sub=str(user2.id), db=db_session)

    response = await root_client.patch(
        f"/api/v1/notifications/{notif.id}/read",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_read_single_already_read(
    root_client: AsyncClient, db_session, user_factory
):
    user = await user_factory()
    notif = models.Notification(user_id=user.id, title="Test", body="Test", read=True)
    db_session.add(notif)
    await db_session.commit()
    await db_session.refresh(notif)

    from app.auth.security import create_access_token

    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    response = await root_client.patch(
        f"/api/v1/notifications/{notif.id}/read",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_list_notifications_bad_cursor(
    root_client: AsyncClient, user_factory, db_session
):
    user = await user_factory()
    from app.auth.security import create_access_token

    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    response = await root_client.get(
        "/api/v1/notifications?cursor=invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_clear_notifications(root_client: AsyncClient, db_session, user_factory):
    user = await user_factory()
    notif = models.Notification(user_id=user.id, title="Test", body="Test")
    db_session.add(notif)
    await db_session.commit()

    from app.auth.security import create_access_token

    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    response = await root_client.delete(
        "/api/v1/notifications", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["deleted"] >= 1


@pytest.mark.asyncio
async def test_auth_service_coverage(db_session, user_factory):
    user = await user_factory()
    from app.auth.security import get_password_hash
    from app.services.auth_service import AuthService

    user.hashed_password = get_password_hash("Password123!", validate_policy=False)

    audit = MagicMock()
    service = AuthService(db_session, audit)

    request = MagicMock()
    request.state.active_session = None

    # initiate_password_reset user not found
    bg = MagicMock()
    await service.initiate_password_reset("nonexistent@e.com", request, bg)
    audit.log.assert_called()

    # perform_password_reset invalid token
    with pytest.raises(HTTPException):
        await service.perform_password_reset("invalid", "newpass", request)

    # initiate_email_change invalid password
    from app.schemas import schemas

    payload = schemas.UserEmailChangeIn(email="new@e.com", password="wrong")  # NOSONAR
    with pytest.raises(HTTPException):
        await service.initiate_email_change(user, payload, request, bg)


@pytest.mark.asyncio
async def test_check_schedule_no_group(
    root_client: AsyncClient, user_factory, db_session
):
    user = await user_factory(group_id=None)
    from app.auth.security import create_access_token

    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    response = await root_client.post(
        "/api/v1/notifications/check-schedule",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
