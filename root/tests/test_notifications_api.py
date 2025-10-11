import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.models.models import Notification


async def _login(
    async_client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_clear_notifications_removes_only_current_user(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "ClearIt123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    other = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    notices = [
        Notification(user_id=user.id, title="Первое уведомление", body="Тест 1"),
        Notification(user_id=user.id, title="Второе уведомление"),
        Notification(user_id=other.id, title="Чужое уведомление"),
    ]
    db_session.add_all(notices)
    await db_session.commit()

    response = await async_client.delete("/notifications", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["deleted"] == 2

    remaining_user = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    remaining_other = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == other.id)
            )
        )
        .scalars()
        .all()
    )

    assert remaining_user == []
    assert len(remaining_other) == 1
