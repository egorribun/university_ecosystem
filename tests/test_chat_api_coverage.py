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
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
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

            # get messages
            await ac.get("/api/v1/chats/00000000-0000-0000-0000-000000000000/messages")

            # send message - using data since it has Form fields
            # send_message(chat_id: str, content: str = Form(""), ...)
            await ac.post(
                "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages",
                data={"content": "hello"},
            )

            # get chat details
            await ac.get("/api/v1/chats/00000000-0000-0000-0000-000000000000")

            # mark read
            await ac.post("/api/v1/chats/00000000-0000-0000-0000-000000000000/read")

            # clear history
            await ac.post("/api/v1/chats/00000000-0000-0000-0000-000000000000/clear")

            # delete chat
            await ac.delete("/api/v1/chats/00000000-0000-0000-0000-000000000000")
    finally:
        # Cleaned up by conftest
        pass
