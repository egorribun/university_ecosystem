import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_current_admin_user_from_dishka,
    get_current_user_from_dishka,
)
from app.core.database import get_db
from app.main import app
from tests.conftest import install_dishka_override


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
        get_locale,
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
    chat_details = ChatResponse(
        id=chat_id,
        participants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message=None,
        unread_count=0,
        presence={},
    )
    mock_query.get_chat_details.return_value = chat_details

    message_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    reactions_url = (
        f"/api/v1/chats/{chat_id}/messages/{message_id}/reactions?emoji=%F0%9F%91%8D"
    )
    sent_message_id = uuid.uuid4()
    sent_message_created_at = datetime.now(UTC)
    mock_dispatcher.send_message.return_value = MessageResponse(
        id=sent_message_id,
        chat_id=chat_id,
        sender_id=user_id,
        content="hello",
        created_at=sent_message_created_at,
        read_status=False,
    )

    mock_creation.create_group.return_value = ChatResponse(
        id=chat_id,
        chat_type="group",
        name="test group",
        created_by=user_id,
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

    app.dependency_overrides[get_current_user_from_dishka] = lambda: mock_user
    app.dependency_overrides[get_current_admin_user_from_dishka] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    install_dishka_override(app, ChatMaintenanceService=mock_maintenance)
    install_dishka_override(app, ChatQueryService=mock_query)
    app.dependency_overrides[get_locale] = lambda: "en"
    install_dishka_override(app, ChatMessageDispatcher=mock_dispatcher)
    install_dishka_override(app, ChatCreationService=mock_creation)

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
            chats_response = await ac.get("/api/v1/chats")
            assert chats_response.status_code == 200
            assert chats_response.json() == {
                "items": [],
                "has_more": False,
                "next_cursor": None,
            }
            csrf_token = ac.cookies.get("csrf_token")
            headers = {"x-csrf-token": csrf_token} if csrf_token else {}

            # get messages
            messages_response = await ac.get(f"/api/v1/chats/{chat_id}/messages")
            assert messages_response.status_code == 200
            assert messages_response.json() == {
                "items": [],
                "has_more": False,
                "next_cursor": None,
            }

            # create group chat
            create_group_response = await ac.post(
                "/api/v1/chats/groups",
                json={
                    "name": "test group",
                    "participant_ids": [str(user_id)],
                },
                headers=headers,
            )
            assert create_group_response.status_code == 200
            assert create_group_response.json()["id"] == str(chat_id)
            assert create_group_response.json()["chat_type"] == "group"
            assert create_group_response.json()["name"] == "test group"
            assert create_group_response.json()["created_by"] == str(user_id)

            # send message
            send_message_response = await ac.post(
                f"/api/v1/chats/{chat_id}/messages",
                data={"content": "hello"},
                headers=headers,
            )
            assert send_message_response.status_code == 200
            assert send_message_response.json()["id"] == str(sent_message_id)
            assert send_message_response.json()["chat_id"] == str(chat_id)
            assert send_message_response.json()["sender_id"] == str(user_id)
            assert send_message_response.json()["content"] == "hello"

            # edit message
            edit_response = await ac.patch(
                f"/api/v1/chats/{chat_id}/messages/{message_id}",
                data={"content": "updated content"},
                headers=headers,
            )
            assert edit_response.status_code == 200
            assert edit_response.json() == {"status": "ok"}

            # delete message
            delete_message_response = await ac.delete(
                f"/api/v1/chats/{chat_id}/messages/{message_id}",
                headers=headers,
            )
            assert delete_message_response.status_code == 200
            assert delete_message_response.json() == {"status": "ok"}

            # add reaction
            add_reaction_response = await ac.post(
                f"/api/v1/chats/{chat_id}/messages/{message_id}/reactions",
                data={"emoji": "👍"},
                headers=headers,
            )
            assert add_reaction_response.status_code == 200
            assert add_reaction_response.json() == {"status": "ok"}

            # remove reaction
            remove_reaction_response = await ac.delete(
                reactions_url,
                headers=headers,
            )
            assert remove_reaction_response.status_code == 200
            assert remove_reaction_response.json() == {"status": "ok"}

            # get reactors
            reactors_response = await ac.get(reactions_url)
            assert reactors_response.status_code == 200
            assert reactors_response.json() == []

            # typing indicator
            typing_response = await ac.post(
                f"/api/v1/chats/{chat_id}/typing",
                headers=headers,
            )
            assert typing_response.status_code == 200
            assert typing_response.json() == {"status": "ok"}

            # get chat details
            chat_details_response = await ac.get(f"/api/v1/chats/{chat_id}")
            assert chat_details_response.status_code == 200
            assert chat_details_response.json()["id"] == str(chat_id)
            assert chat_details_response.json()["participants"] == []

            # mark read
            mark_read_response = await ac.post(
                f"/api/v1/chats/{chat_id}/read",
                headers=headers,
            )
            assert mark_read_response.status_code == 200
            assert mark_read_response.json() == {"status": "ok"}

            # clear history
            clear_history_response = await ac.post(
                f"/api/v1/chats/{chat_id}/clear",
                headers=headers,
            )
            assert clear_history_response.status_code == 200
            assert clear_history_response.json() == {
                "chat_id": str(chat_id),
                "status": "ok",
                "deleted_messages": 0,
                "deleted_attachments": 0,
            }

            # delete chat
            delete_chat_response = await ac.delete(
                f"/api/v1/chats/{chat_id}", headers=headers
            )
            assert delete_chat_response.status_code == 200
            assert delete_chat_response.json() == {
                "chat_id": str(chat_id),
                "status": "ok",
                "deleted_messages": 0,
                "deleted_attachments": 0,
            }

        mock_query.get_chats.assert_awaited_once_with(mock_user, None, 20)
        mock_query.get_messages.assert_awaited_once_with(
            chat_id, mock_user, cursor=None, limit=50, locale="en"
        )
        mock_creation.create_group.assert_awaited_once_with(
            mock_user, "test group", [user_id], locale="en"
        )
        mock_dispatcher.send_message.assert_awaited_once_with(
            chat_id,
            mock_user,
            "hello",
            [],
            locale="en",
            idempotency_key=None,
            reply_to_message_id=None,
        )
        mock_maintenance.edit_message.assert_awaited_once_with(
            chat_id, message_id, mock_user, "updated content", locale="en"
        )
        mock_maintenance.soft_delete_message.assert_awaited_once_with(
            chat_id, message_id, mock_user, locale="en"
        )
        mock_maintenance.add_reaction.assert_awaited_once_with(
            chat_id, message_id, mock_user, "👍", locale="en"
        )
        mock_maintenance.remove_reaction.assert_awaited_once_with(
            chat_id, message_id, mock_user, "👍", locale="en"
        )
        mock_query.get_reactors.assert_awaited_once_with(
            chat_id, message_id, "👍", mock_user, locale="en"
        )
        mock_maintenance.broadcast_typing.assert_awaited_once_with(
            chat_id, mock_user, locale="en"
        )
        mock_query.get_chat_details.assert_awaited_once_with(
            chat_id, mock_user, locale="en"
        )
        mock_maintenance.mark_read.assert_awaited_once_with(
            chat_id, mock_user, locale="en"
        )
        mock_maintenance.clear_history.assert_awaited_once_with(
            chat_id, mock_user, locale="en"
        )
        mock_maintenance.delete_chat.assert_awaited_once_with(
            chat_id, mock_user, locale="en"
        )
    finally:
        del app.dependency_overrides[get_current_user_from_dishka]
        del app.dependency_overrides[get_current_admin_user_from_dishka]
        del app.dependency_overrides[get_db]
        del app.dependency_overrides[get_locale]
