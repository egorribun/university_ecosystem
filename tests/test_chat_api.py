import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.api.deps import get_read_chat_service
from app.auth.security import get_password_hash
from app.core.database import get_db, get_read_db
from app.main import app
from app.models.chat import Chat, Message
from app.services.chat_service import ChatService
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor


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


@pytest.mark.asyncio
async def test_create_chat_errors(async_client, user_factory):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    headers = await _login(async_client, user.email, password)

    # 1. Create chat with self
    resp = await async_client.post(
        "/chats", json={"participant_id": str(user.id)}, headers=headers
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "errors.chat.self_chat" in detail or "Cannot create" in detail

    # 2. Create chat with non-existent user
    resp = await async_client.post(
        "/chats", json={"participant_id": str(uuid.uuid4())}, headers=headers
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "errors.users.not_found" in detail or "User not found" in detail


@pytest.mark.asyncio
async def test_create_chat_idempotency(async_client, user_factory):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    other = await user_factory()
    headers = await _login(async_client, user.email, password)

    # Create first time
    resp1 = await async_client.post(
        "/chats", json={"participant_id": str(other.id)}, headers=headers
    )
    assert resp1.status_code == 200
    chat_id = resp1.json()["id"]

    # Create second time - should return same chat
    resp2 = await async_client.post(
        "/chats", json={"participant_id": str(other.id)}, headers=headers
    )
    assert resp2.status_code == 200
    assert resp2.json()["id"] == chat_id


@pytest.mark.asyncio
async def test_get_chats_list_simple(async_client, user_factory, db_session):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    headers = await _login(async_client, user.email, password)

    # Create 3 chats
    chats = []
    for i in range(3):
        other_i = await user_factory()
        chat = Chat()
        chat.participants.extend([user, other_i])
        db_session.add(chat)
        chats.append(chat)

    await db_session.commit()
    for c in chats:
        await db_session.refresh(c)

    # Fetch all
    resp = await async_client.get("/chats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_get_messages_errors(async_client, user_factory, db_session):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    headers = await _login(async_client, user.email, password)

    # 1. Non-existent chat
    resp = await async_client.get(f"/chats/{uuid.uuid4()}/messages", headers=headers)
    assert resp.status_code == 404

    # 2. Not a participant
    other1 = await user_factory()
    other2 = await user_factory()
    chat = Chat()
    chat.participants.extend([other1, other2])
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)

    resp = await async_client.get(f"/chats/{chat.id}/messages", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_send_message_errors(async_client, user_factory, db_session, monkeypatch):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    headers = await _login(async_client, user.email, password)

    # 1. Non-existent chat
    resp = await async_client.post(
        f"/chats/{uuid.uuid4()}/messages", data={"content": "Hello"}, headers=headers
    )
    assert resp.status_code == 404

    # 2. Too many files
    other = await user_factory()
    chat = Chat()
    chat.participants.extend([user, other])
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)

    # Mock settings to allow 0 attachments
    from app.core.config import settings

    monkeypatch.setattr(settings, "chat_attachment_max_files", 0)

    # Create dummy upload
    files = [("files", ("test.txt", b"test", "text/plain"))]
    resp = await async_client.post(
        f"/chats/{chat.id}/messages",
        data={"content": "Hello"},
        files=files,
        headers=headers,
    )
    assert resp.status_code == 400
    assert (
        "errors.files.too_many_attachments" in str(resp.content)
        or "Too many attachments" in str(resp.content)
        or "too many" in str(resp.content).lower()
    )


@pytest.mark.asyncio
async def test_mark_read_logic(async_client, user_factory, db_session):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    other = await user_factory()
    headers = await _login(async_client, user.email, password)

    chat = Chat()
    chat.participants.extend([user, other])
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)

    # Create unread messages from 'other' to 'user'
    msg1 = Message(chat_id=chat.id, sender_id=other.id, content="Hi", read_status=False)
    msg2 = Message(
        chat_id=chat.id, sender_id=other.id, content="How are you", read_status=False
    )
    # Message from 'user' (should differ)
    msg3 = Message(
        chat_id=chat.id, sender_id=user.id, content="Im self", read_status=False
    )
    db_session.add_all([msg1, msg2, msg3])
    await db_session.commit()

    # Call mark read
    resp = await async_client.post(f"/chats/{chat.id}/read", headers=headers)
    assert resp.status_code == 200

    # Verify
    await db_session.refresh(msg1)
    await db_session.refresh(msg2)
    await db_session.refresh(msg3)

    assert msg1.read_status is True
    assert msg2.read_status is True
    assert (
        msg3.read_status is False
    )  # Should not affect my own messages technically, or logic ignores them


@pytest.mark.asyncio
async def test_cursor_helpers():
    dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    cid = "chat-123"

    encoded = encode_datetime_cursor(dt, cid)
    assert ":" in encoded

    decoded_dt, decoded_id = decode_datetime_cursor(encoded)
    assert abs((decoded_dt - dt).total_seconds()) < 0.002  # Precision check
    assert decoded_id == cid

    assert decode_datetime_cursor(None) is None
    assert decode_datetime_cursor("invalid") is None


@pytest.mark.asyncio
async def test_delete_chat_permissions(async_client, user_factory, db_session):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    other1 = await user_factory()
    other2 = await user_factory()
    headers = await _login(async_client, user.email, password)

    # Chat user is NOT in
    chat = Chat()
    chat.participants.extend([other1, other2])
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)

    resp = await async_client.delete(f"/chats/{chat.id}", headers=headers)
    assert resp.status_code == 403

    resp_clear = await async_client.post(f"/chats/{chat.id}/clear", headers=headers)
    assert resp_clear.status_code == 403


@pytest.mark.asyncio
async def test_messaging_flow_success(async_client, user_factory, db_session):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=get_password_hash(password))
    other = await user_factory()
    headers = await _login(async_client, user.email, password)

    # Override read dependencies to use same session
    app.dependency_overrides[get_read_db] = lambda: db_session
    app.dependency_overrides[get_read_chat_service] = lambda: ChatService(db_session)
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        # 1. Create chat
        create_resp = await async_client.post(
            "/chats", json={"participant_id": str(other.id)}, headers=headers
        )
        assert create_resp.status_code == 200
        chat_id = create_resp.json()["id"]

        # 2. Send message
        send_resp = await async_client.post(
            f"/chats/{chat_id}/messages",
            data={"content": "Hello World"},
            headers=headers,
        )
        assert send_resp.status_code == 200
        msg_data = send_resp.json()
        assert msg_data["content"] == "Hello World"
        assert msg_data["sender_id"] == str(user.id)

        # 3. Get messages
        get_resp = await async_client.get(f"/chats/{chat_id}/messages", headers=headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["content"] == "Hello World"
        assert data["items"][0]["id"] == msg_data["id"]

    finally:
        app.dependency_overrides.pop(get_read_db, None)
        app.dependency_overrides.pop(get_read_chat_service, None)
        app.dependency_overrides.pop(get_db, None)
