import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.main import app
from app.models import User


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    yield
    # Cleaned up by conftest
    pass


# Helper to create fresh users in DB
async def create_test_user(db, email="test@example.com", role="student"):
    user = User(
        id=uuid.uuid4(),
        email=email,
        role=role,
        is_active=True,
        hashed_password="mock_hashed_password",
    )
    db.add(user)
    await db.commit()
    return user


async def override_get_current_user_factory(user):
    async def _override():
        return user

    return _override


@pytest.mark.asyncio
async def test_get_vapid_public_key_success():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.get("/api/v1/push/vapid-public-key")
    assert response.status_code == 200
    assert "publicKey" in response.json()


@pytest.mark.asyncio
async def test_subscribe_success(db_session):
    user = await create_test_user(db_session)
    app.dependency_overrides[get_current_user] = lambda: user

    payload = {
        "endpoint": f"https://example.com/push/{uuid.uuid4()}",
        "keys": {"p256dh": "test_p256dh", "auth": "test_auth"},
        "topics": ["system"],
    }

    headers = {"Authorization": "Bearer test"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.post(
            "/api/v1/push/subscribe", json=payload, headers=headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["endpoint"] == payload["endpoint"]


@pytest.mark.asyncio
async def test_get_push_topics_empty(db_session):
    user = await create_test_user(db_session, email="topics@example.com")
    app.dependency_overrides[get_current_user] = lambda: user

    headers = {"Authorization": "Bearer test"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.get("/api/v1/push/topics", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "topics" in data
    assert isinstance(data["topics"], list)


@pytest.mark.asyncio
async def test_admin_get_user_topics_success(db_session):
    admin = await create_test_user(db_session, email="admin@example.com", role="admin")
    target = await create_test_user(db_session, email="target@example.com")
    app.dependency_overrides[get_current_user] = lambda: admin

    headers = {"Authorization": "Bearer test"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.get(
            f"/api/v1/push/admin/topics/{target.id}", headers=headers
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_disable_user_push_success(db_session):
    admin = await create_test_user(db_session, email="admin2@example.com", role="admin")
    target = await create_test_user(db_session, email="target2@example.com")
    app.dependency_overrides[get_current_user] = lambda: admin

    payload = {"user_id": str(target.id)}
    headers = {"Authorization": "Bearer test"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.post(
            "/api/v1/push/admin/disable-user", json=payload, headers=headers
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unsubscribe_endpoint_not_found(db_session):
    user = await create_test_user(db_session, email="unsub@example.com")
    app.dependency_overrides[get_current_user] = lambda: user

    payload = {"endpoint": "https://nonexistent.com/push"}
    headers = {"Authorization": "Bearer test"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.post(
            "/api/v1/push/unsubscribe", json=payload, headers=headers
        )

    assert response.status_code == 200
    assert response.json()["removed"] is False


@pytest.mark.asyncio
async def test_send_test_forbidden(db_session):
    user = await create_test_user(db_session, email="notadmin@example.com")
    app.dependency_overrides[get_current_user] = lambda: user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.post("/api/v1/push/test", json={"title": "Test"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_send_test_success(db_session):
    admin = await create_test_user(db_session, email="admin3@example.com", role="admin")
    target = await create_test_user(db_session, email="target3@example.com")
    app.dependency_overrides[get_current_user] = lambda: admin

    # Ensure user exists in DB
    headers = {"Authorization": "Bearer test"}
    payload = {"title": "Admin Test", "topic": "system", "user_id": str(target.id)}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.post("/api/v1/push/test", json=payload, headers=headers)

    assert response.status_code == 200

    payload_update = {"endpoint": "https://example.com/notfound", "topics": ["system"]}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as ac:
        response = await ac.patch(
            "/api/v1/push/subscribe/topics", json=payload_update, headers=headers
        )

    assert response.status_code == 404
