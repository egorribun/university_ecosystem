import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.api.deps import get_read_chat_query_service
from app.auth.security import get_password_hash
from app.core.database import get_db, get_read_db
from app.main import app
from app.models.chat import Chat, Message
from app.services.chat.query_service import ChatQueryService
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
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_chat_errors(async_client, user_factory):
    password = "TestPassword123!"
    user = await user_factory(hashed_password=await get_password_hash(password))
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
    user = await user_factory(hashed_password=await get_password_hash(password))
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
    user = await user_factory(hashed_password=await get_password_hash(password))
    headers = await _login(async_client, user.email, password)
    headers["X-Query-Budget"] = "15"

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
    user = await user_factory(hashed_password=await get_password_hash(password))
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
    user = await user_factory(hashed_password=await get_password_hash(password))
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
    user = await user_factory(hashed_password=await get_password_hash(password))
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
async def test_forward_cross_chat_leak_403(async_client, user_factory, db_session):
    # Wave 211 track F — the headline cross-chat-leak guard end-to-end. The actor
    # is a participant of the DEST chat (can send) but NOT of the SOURCE chat, so
    # forwarding a source message must 403 (the source participant check fires
    # before any source message is read).
    password = "TestPassword123!"
    actor = await user_factory(hashed_password=await get_password_hash(password))
    outsider1 = await user_factory()
    outsider2 = await user_factory()
    dest_peer = await user_factory()
    headers = await _login(async_client, actor.email, password)

    # Source chat the actor is NOT in, with a message.
    source = Chat()
    source.participants.extend([outsider1, outsider2])
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    secret = Message(chat_id=source.id, sender_id=outsider1.id, content="private")
    db_session.add(secret)
    await db_session.commit()
    await db_session.refresh(secret)

    # Dest chat the actor IS in.
    dest = Chat()
    dest.participants.extend([actor, dest_peer])
    db_session.add(dest)
    await db_session.commit()
    await db_session.refresh(dest)

    resp = await async_client.post(
        f"/chats/{dest.id}/forward",
        json={"source_chat_id": str(source.id), "message_ids": [str(secret.id)]},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_forward_snapshot_lands_in_dest(async_client, user_factory, db_session):
    # Wave 211 track F — a forwarded message is a snapshot copy in the dest chat:
    # the content is copied and the message lands in the destination's message list.
    password = "TestPassword123!"
    actor = await user_factory(hashed_password=await get_password_hash(password))
    source_peer = await user_factory(full_name="Source Author")
    dest_peer = await user_factory()
    headers = await _login(async_client, actor.email, password)
    headers["X-Disable-Query-Budget"] = "true"

    source = Chat()
    source.participants.extend([actor, source_peer])
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    original = Message(
        chat_id=source.id, sender_id=source_peer.id, content="forward me"
    )
    db_session.add(original)
    await db_session.commit()
    await db_session.refresh(original)

    dest = Chat()
    dest.participants.extend([actor, dest_peer])
    db_session.add(dest)
    await db_session.commit()
    await db_session.refresh(dest)

    resp = await async_client.post(
        f"/chats/{dest.id}/forward",
        json={"source_chat_id": str(source.id), "message_ids": [str(original.id)]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["content"] == "forward me"
    # The forward is a NEW message authored by the forwarder in the dest chat.
    assert body[0]["chat_id"] == str(dest.id)
    assert body[0]["sender_id"] == str(actor.id)
    # The "Forwarded from X" label snapshots the ORIGINAL sender's display name,
    # resolved from UserProfile.full_name (not the forwarder's). A bare
    # selectinload(Message.sender) would leave this None (W207 SW5 gotcha) — this
    # guards the get_user_display_names profile-loaded fix at the real-repo level.
    assert body[0]["forwarded_from_name"] == "Source Author"

    # It appears in the destination's message list.
    listing = await async_client.get(f"/chats/{dest.id}/messages", headers=headers)
    assert listing.status_code == 200
    contents = [m["content"] for m in listing.json()["items"]]
    assert "forward me" in contents


@pytest.mark.asyncio
async def test_forward_message_not_in_source_404(
    async_client, user_factory, db_session
):
    # Wave 211 track F — a message id that is not in the source chat 404s before
    # any message is created (all-or-nothing validation).
    password = "TestPassword123!"
    actor = await user_factory(hashed_password=await get_password_hash(password))
    source_peer = await user_factory(full_name="Source Author")
    dest_peer = await user_factory()
    headers = await _login(async_client, actor.email, password)

    source = Chat()
    source.participants.extend([actor, source_peer])
    db_session.add(source)
    dest = Chat()
    dest.participants.extend([actor, dest_peer])
    db_session.add(dest)
    await db_session.commit()
    await db_session.refresh(source)
    await db_session.refresh(dest)

    resp = await async_client.post(
        f"/chats/{dest.id}/forward",
        json={"source_chat_id": str(source.id), "message_ids": [str(uuid.uuid4())]},
        headers=headers,
    )
    assert resp.status_code == 404


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
    user = await user_factory(hashed_password=await get_password_hash(password))
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
    user = await user_factory(hashed_password=await get_password_hash(password))
    other = await user_factory()
    headers = await _login(async_client, user.email, password)
    headers["X-Disable-Query-Budget"] = "true"

    # Override read dependencies to use same session (TD-W9-05: ChatService removed)
    def _get_mock_query_service():
        from app.repositories.unit_of_work import uow_from_session

        uow = uow_from_session(db_session)
        return ChatQueryService(db_session, uow.chats)

    app.dependency_overrides[get_read_db] = lambda: db_session
    app.dependency_overrides[get_read_chat_query_service] = _get_mock_query_service
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
        app.dependency_overrides.pop(get_read_chat_query_service, None)
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Group chats (Wave 209 G1)
# ---------------------------------------------------------------------------

_GROUP_PASSWORD = "TestPassword123!"


async def _login_user(async_client, user_factory):
    user = await user_factory(hashed_password=await get_password_hash(_GROUP_PASSWORD))
    headers = await _login(async_client, user.email, _GROUP_PASSWORD)
    return user, headers


@pytest.mark.asyncio
async def test_create_group_too_few_members(async_client, user_factory):
    _creator, headers = await _login_user(async_client, user_factory)
    other = await user_factory()
    resp = await async_client.post(
        "/chats/groups",
        json={"name": "Team", "participant_ids": [str(other.id)]},
        headers=headers,
    )
    assert resp.status_code == 400  # total 2 < min 3


@pytest.mark.asyncio
async def test_create_group_happy_path(async_client, user_factory):
    _creator, headers = await _login_user(async_client, user_factory)
    m1 = await user_factory()
    m2 = await user_factory()
    resp = await async_client.post(
        "/chats/groups",
        json={"name": "Team Chat", "participant_ids": [str(m1.id), str(m2.id)]},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chat_type"] == "group"
    assert data["name"] == "Team Chat"
    assert data["created_by"] == str(_creator.id)
    assert len(data["participants"]) == 3


@pytest.mark.asyncio
async def test_rename_group(async_client, user_factory):
    _creator, headers = await _login_user(async_client, user_factory)
    m1, m2 = await user_factory(), await user_factory()
    created = await async_client.post(
        "/chats/groups",
        json={"name": "Old", "participant_ids": [str(m1.id), str(m2.id)]},
        headers=headers,
    )
    chat_id = created.json()["id"]

    resp = await async_client.patch(
        f"/chats/{chat_id}", json={"name": "New Name"}, headers=headers
    )
    assert resp.status_code == 200
    # Persistence is covered by the SW2 repo test (test_rename_chat_persists);
    # GET /chats/{id} (get_unread_count → SET LOCAL RLS) is PostgreSQL-only and
    # can't run on the SQLite test DB, so the integration test asserts the
    # endpoint contract (status + routing + authz) only.


@pytest.mark.asyncio
async def test_add_participant(async_client, user_factory):
    _creator, headers = await _login_user(async_client, user_factory)
    m1, m2, newcomer = (
        await user_factory(),
        await user_factory(),
        await user_factory(),
    )
    created = await async_client.post(
        "/chats/groups",
        json={"name": "Team", "participant_ids": [str(m1.id), str(m2.id)]},
        headers=headers,
    )
    chat_id = created.json()["id"]

    resp = await async_client.post(
        f"/chats/{chat_id}/participants",
        json={"user_id": str(newcomer.id)},
        headers=headers,
    )
    assert resp.status_code == 200
    # Count persistence covered by SW2 (test_add_participant_is_idempotent);
    # GET /chats/{id} is PostgreSQL-RLS-only (see test_rename_group note).


@pytest.mark.asyncio
async def test_owner_removes_member(async_client, user_factory):
    _creator, headers = await _login_user(async_client, user_factory)
    m1, m2 = await user_factory(), await user_factory()
    created = await async_client.post(
        "/chats/groups",
        json={"name": "Team", "participant_ids": [str(m1.id), str(m2.id)]},
        headers=headers,
    )
    chat_id = created.json()["id"]

    resp = await async_client.delete(
        f"/chats/{chat_id}/participants/{m1.id}", headers=headers
    )
    assert resp.status_code == 200
    # Count persistence covered by SW2 (test_remove_participant_is_idempotent);
    # GET /chats/{id} is PostgreSQL-RLS-only (see test_rename_group note).


@pytest.mark.asyncio
async def test_dm_rejects_rename(async_client, user_factory):
    _creator, headers = await _login_user(async_client, user_factory)
    other = await user_factory()
    dm = await async_client.post(
        "/chats", json={"participant_id": str(other.id)}, headers=headers
    )
    dm_id = dm.json()["id"]

    resp = await async_client.patch(
        f"/chats/{dm_id}", json={"name": "Not allowed"}, headers=headers
    )
    assert resp.status_code == 400  # not_a_group


@pytest.mark.asyncio
async def test_non_owner_remove_forbidden_then_self_leave(async_client, user_factory):
    _creator, headers = await _login_user(async_client, user_factory)
    member1, m1_headers = await _login_user(async_client, user_factory)
    m2 = await user_factory()
    created = await async_client.post(
        "/chats/groups",
        json={"name": "Team", "participant_ids": [str(member1.id), str(m2.id)]},
        headers=headers,
    )
    chat_id = created.json()["id"]

    # member1 (not owner) tries to remove m2 → 403
    forbidden = await async_client.delete(
        f"/chats/{chat_id}/participants/{m2.id}", headers=m1_headers
    )
    assert forbidden.status_code == 403

    # member1 leaves (self-removal) → 200
    leave = await async_client.delete(
        f"/chats/{chat_id}/participants/{member1.id}", headers=m1_headers
    )
    assert leave.status_code == 200
