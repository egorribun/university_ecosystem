import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    user.role = "admin"
    return user


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.mark.asyncio
async def test_chat_api_exhaustive(mock_user, mock_db):
    from datetime import UTC, datetime

    from app.api.deps import (
        get_chat_creation_service,
        get_chat_maintenance_service,
        get_chat_message_dispatcher,
        get_locale,
        get_read_chat_query_service,
    )
    from app.schemas.chat import (
        ChatMaintenanceResult,
        ChatResponse,
        ChatsListOut,
        MessageResponse,
        MessagesListOut,
    )

    mock_maintenance = AsyncMock()
    mock_query = AsyncMock()
    mock_dispatcher = AsyncMock()
    mock_creation = AsyncMock()

    chat_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    mock_query.get_chats.return_value = ChatsListOut(items=[], next_cursor=None)
    mock_query.get_messages.return_value = MessagesListOut(items=[], next_cursor=None)
    mock_query.get_reactors.return_value = []
    mock_query.get_chat_details.return_value = ChatResponse(
        id=chat_id,
        participants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message=None,
        unread_count=0,
        presence={},
    )

    mock_dispatcher.send_message.return_value = MessageResponse(
        id=uuid.uuid4(),
        chat_id=chat_id,
        sender_id=user_id,
        content="hello",
        created_at=datetime.now(UTC),
        read_status=False,
    )

    mock_creation.create_group.return_value = ChatResponse(
        id=chat_id,
        participants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message=None,
        unread_count=0,
        presence={},
    )

    mock_maintenance.clear_history.return_value = ChatMaintenanceResult(
        chat_id=chat_id, status="ok"
    )
    mock_maintenance.delete_chat.return_value = ChatMaintenanceResult(
        chat_id=chat_id, status="ok"
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_chat_maintenance_service] = lambda: mock_maintenance
    app.dependency_overrides[get_read_chat_query_service] = lambda: mock_query
    app.dependency_overrides[get_locale] = lambda: "en"
    app.dependency_overrides[get_chat_message_dispatcher] = lambda: mock_dispatcher
    app.dependency_overrides[get_chat_creation_service] = lambda: mock_creation

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as ac:
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = []
            mock_res.scalars.return_value.first.return_value = None
            mock_db.execute.return_value = mock_res
            mock_db.get.return_value = None

            # get chats
            await ac.get("/api/v1/chats")
            csrf_token = ac.cookies.get("csrf_token")
            headers = {"x-csrf-token": csrf_token} if csrf_token else {}

            # get messages
            await ac.get("/api/v1/chats/00000000-0000-0000-0000-000000000000/messages")

            # create group chat
            await ac.post(
                "/api/v1/chats/groups",
                json={
                    "name": "test group",
                    "participant_ids": ["00000000-0000-0000-0000-000000000000"],
                },
                headers=headers,
            )

            # send message
            await ac.post(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages",
                data={"content": "hello"},
                headers=headers,
            )

            # edit message
            await ac.patch(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages/00000000-0000-0000-0000-000000000000",
                data={"content": "updated content"},
                headers=headers,
            )

            # delete message
            await ac.delete(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages/00000000-0000-0000-0000-000000000000",
                headers=headers,
            )

            # add reaction
            await ac.post(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages/00000000-0000-0000-0000-000000000000/reactions",
                data={"emoji": "👍"},
                headers=headers,
            )

            # remove reaction
            await ac.delete(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages/00000000-0000-0000-0000-000000000000/reactions?emoji=%F0%9F%91%8D",
                headers=headers,
            )

            # get reactors
            await ac.get(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages/00000000-0000-0000-0000-000000000000/reactions?emoji=%F0%9F%91%8D"
            )

            # typing indicator
            await ac.post(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/typing",
                headers=headers,
            )

            # get chat details
            await ac.get("/api/v1/chats/00000000-0000-0000-0000-000000000000")

            # mark read
            await ac.post(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/read",
                headers=headers,
            )

            # clear history
            await ac.post(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/clear",
                headers=headers,
            )

            # delete chat
            await ac.delete(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000", headers=headers
            )
    finally:
        del app.dependency_overrides[get_current_user]
        del app.dependency_overrides[get_db]
        del app.dependency_overrides[get_chat_maintenance_service]
        del app.dependency_overrides[get_read_chat_query_service]
        del app.dependency_overrides[get_locale]
        del app.dependency_overrides[get_chat_message_dispatcher]
        del app.dependency_overrides[get_chat_creation_service]
