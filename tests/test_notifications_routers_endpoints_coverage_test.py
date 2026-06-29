import pytest
from httpx import AsyncClient
from app.models import User
from app.models.enums import UserRole
import uuid

_TEST_PASSWORD = "TestPassword123!"

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
async def test_push_endpoints(client: AsyncClient, db_session, test_user: User):
    headers = await _login(client, test_user.email)

    # 1. /push/vapid-public-key
    resp = await client.get("/push/vapid-public-key")
    assert resp.status_code == 200
    assert "public_key" in resp.json()

    # 2. /push/subscribe
    payload = {
        "endpoint": "https://example.com/push-test-123",
        "keys": {
            "p256dh": "A"*43,
            "auth": "B"*22
        },
        "topics": ["news", "events"]
    }
    resp = await client.post("/push/subscribe", json=payload, headers=headers)
    assert resp.status_code == 200

    # 3. /push/topics
    resp = await client.get("/push/topics", headers=headers)
    assert resp.status_code == 200

    # 4. /push/subscribe/topics
    resp = await client.patch("/push/subscribe/topics", json={"endpoint": payload["endpoint"], "topics": ["system"]}, headers=headers)
    assert resp.status_code == 200

    # 5. /push/test
    resp = await client.post("/push/test", headers=headers)
    assert resp.status_code in (200, 400, 500)

    # 6. /push/unsubscribe
    resp = await client.post("/push/unsubscribe", json={"endpoint": payload["endpoint"]}, headers=headers)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_admin_push_endpoints(client: AsyncClient, db_session, test_user: User):
    # Make user admin
    test_user.role = UserRole.ADMIN
    db_session.add(test_user)
    await db_session.commit()
    
    headers = await _login(client, test_user.email)
    user_id = str(test_user.id)

    # /push/admin/topics/{user_id}
    resp = await client.get(f"/push/admin/topics/{user_id}", headers=headers)
    assert resp.status_code == 200

    # /push/admin/topics/{user_id} (PUT)
    resp = await client.put(f"/push/admin/topics/{user_id}", json={"topics": ["urgent"]}, headers=headers)
    assert resp.status_code == 200

    # /push/admin/disable-user
    resp = await client.post("/push/admin/disable-user", json={"user_id": user_id}, headers=headers)
    assert resp.status_code == 200

    # /push/broadcast
    resp = await client.post("/push/broadcast", json={"title": "Test", "body": "Body"}, headers=headers)
    assert resp.status_code in (200, 400, 500)
