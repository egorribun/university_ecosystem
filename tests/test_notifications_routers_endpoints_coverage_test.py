import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash
from app.models import User
from app.models.enums import UserRole

_TEST_PASSWORD = "TestPassword123!"  # pragma: allowlist secret


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    token = resp.cookies.get("access_token_v2") or client.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_push_endpoints(async_client: AsyncClient, db_session, test_user: User):
    hashed = await get_password_hash(_TEST_PASSWORD)
    test_user.hashed_password = hashed
    db_session.add(test_user)
    await db_session.commit()

    headers = await _login(async_client, test_user.email)

    # 1. /push/vapid-public-key
    resp = await async_client.get("/push/vapid-public-key")
    assert resp.status_code == 200
    assert "publicKey" in resp.json()

    # 2. /push/subscribe
    payload = {
        "endpoint": "https://example.com/push-test-123",
        "keys": {"p256dh": "A" * 43, "auth": "B" * 22},
        "topics": ["news", "events"],
    }
    resp = await async_client.post("/push/subscribe", json=payload, headers=headers)
    assert resp.status_code == 200

    # 3. /push/topics
    resp = await async_client.get("/push/topics", headers=headers)
    assert resp.status_code == 200

    # 4. /push/subscribe/topics
    resp = await async_client.patch(
        "/push/subscribe/topics",
        json={"endpoint": payload["endpoint"], "topics": ["system"]},
        headers=headers,
    )
    assert resp.status_code == 200

    # 5. /push/test
    resp = await async_client.post("/push/test", headers=headers)
    assert resp.status_code == 403

    # 6. /push/unsubscribe
    resp = await async_client.post(
        "/push/unsubscribe", json={"endpoint": payload["endpoint"]}, headers=headers
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_push_endpoints(
    async_client: AsyncClient, db_session, test_user: User
):
    # Make user admin
    test_user.role = UserRole.ADMIN
    hashed = await get_password_hash(_TEST_PASSWORD)
    test_user.hashed_password = hashed
    db_session.add(test_user)
    await db_session.commit()

    headers = await _login(async_client, test_user.email)
    user_id = str(test_user.id)

    # /push/admin/topics/{user_id}
    resp = await async_client.get(f"/push/admin/topics/{user_id}", headers=headers)
    assert resp.status_code == 200

    # /push/admin/topics/{user_id} (PUT)
    resp = await async_client.put(
        f"/push/admin/topics/{user_id}", json={"topics": ["system"]}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    # /push/admin/disable-user
    resp = await async_client.post(
        "/push/admin/disable-user", json={"user_id": user_id}, headers=headers
    )
    assert resp.status_code == 200

    # /push/broadcast
    resp = await async_client.post(
        "/push/broadcast", json={"title": "Test", "body": "Body"}, headers=headers
    )
    assert resp.status_code in (200, 400, 500)
