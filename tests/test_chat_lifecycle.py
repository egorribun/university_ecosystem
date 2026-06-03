import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash


async def _login(
    async_client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_chat_full_lifecycle(
    async_client, user_factory, _rate_limit_redis_client
):
    password = "Lifecycle123!"
    user = await user_factory(
        hashed_password=await get_password_hash(password), role="admin"
    )
    other = await user_factory()

    headers = await _login(async_client, user.email, password)
    headers["X-Disable-Query-Budget"] = "true"

    create_resp = await async_client.post(
        "/chats", json={"participant_id": str(other.id)}, headers=headers
    )
    assert create_resp.status_code == 200
    chat_id = create_resp.json()["id"]

    send_resp = await async_client.post(
        f"/chats/{chat_id}/messages",
        data={"content": "Hello"},
        headers=headers,
    )
    assert send_resp.status_code == 200

    initial_messages = await async_client.get(
        f"/chats/{chat_id}/messages", headers=headers
    )
    assert initial_messages.status_code == 200
    assert initial_messages.json()["items"]

    clear_resp = await async_client.post(f"/chats/{chat_id}/clear", headers=headers)
    assert clear_resp.status_code == 200
    assert clear_resp.json()["status"] == "cleared"
    assert clear_resp.json()["deleted_messages"] == 1

    cleared_messages = await async_client.get(
        f"/chats/{chat_id}/messages", headers=headers
    )
    assert cleared_messages.status_code == 200
    assert cleared_messages.json()["items"] == []

    # Flush rate limit counters before final operations to avoid 429
    await _rate_limit_redis_client.flushall()

    delete_resp = await async_client.delete(f"/chats/{chat_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deleted"

    missing_resp = await async_client.get(f"/chats/{chat_id}/messages", headers=headers)
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_chats_list(async_client, user_factory):
    password = "Lifecycle123!"
    user = await user_factory(hashed_password=await get_password_hash(password))
    other = await user_factory()
    headers = await _login(async_client, user.email, password)
    headers["X-Disable-Query-Budget"] = "true"

    # Create a chat
    create_resp = await async_client.post(
        "/chats", json={"participant_id": str(other.id)}, headers=headers
    )
    assert create_resp.status_code == 200

    # Get chats list - THIS WAS FAILING WITH 500
    chats_resp = await async_client.get("/chats", headers=headers)
    assert chats_resp.status_code == 200
    data = chats_resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == create_resp.json()["id"]
    # Verify last_message is None for new chat
    assert data["items"][0]["last_message"] is None
