"""Wave 207 — live typing indicator (ChatMaintenanceService.broadcast_typing).

SW7 adds REST POST /chats/{id}/typing because the frontend WS connects to ws-hub, whose
allowedMessageTypes drops "typing" at its parse boundary — so typing can't relay
peer-to-peer over the socket. The endpoint does participant authz + broadcast_to_chat
(the W204 bridge → ws-hub fan-out). Covers:
  - a participant broadcasts the typing frame (exclude_user_id = self; correct shape);
  - user_name resolution: profile.full_name when loaded, else the email fallback
    (mirrors dispatcher.py — User.profile is lazy="noload");
  - a non-participant → forbidden, NO broadcast.

Mirrors the W206/W207 mock pattern (mock the uow/repo + patch ws_manager, no DB).
The full live cross-user flip is exercised at SW9.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat.command_service import ChatMaintenanceService


def _mock_uow(is_participant: bool) -> MagicMock:
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.chats.check_participant = AsyncMock(return_value=is_participant)
    return uow


def _maintenance(uow: MagicMock) -> ChatMaintenanceService:
    # (uow, attachment_service) — attachment_service is unused by broadcast_typing.
    return ChatMaintenanceService(uow, MagicMock())


def _mock_user(
    full_name: str | None = "Alice", email: str = "alice@example.com"
) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    if full_name is None:
        user.profile = None  # not eager-loaded (or no profile row) → email fallback
    else:
        profile = MagicMock()
        profile.full_name = full_name
        user.profile = profile
    return user


class TestBroadcastTyping:
    @pytest.mark.asyncio
    async def test_participant_broadcasts_typing_frame(self) -> None:
        uow = _mock_uow(is_participant=True)
        user = _mock_user(full_name="Alice")
        chat_id = uuid.uuid4()

        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ) as broadcast:
            await _maintenance(uow).broadcast_typing(chat_id, user, locale="en")

        uow.chats.check_participant.assert_awaited_once_with(chat_id, user.id)
        broadcast.assert_awaited_once()
        args, kwargs = broadcast.await_args
        assert args[0] == chat_id
        frame = args[1]
        assert frame["type"] == "typing"
        assert frame["chat_id"] == str(chat_id)
        assert frame["user_id"] == str(user.id)
        assert frame["user_name"] == "Alice"
        assert kwargs["exclude_user_id"] == user.id

    @pytest.mark.asyncio
    async def test_user_name_falls_back_to_email_without_profile(self) -> None:
        uow = _mock_uow(is_participant=True)
        user = _mock_user(full_name=None, email="bob@example.com")
        chat_id = uuid.uuid4()

        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ) as broadcast:
            await _maintenance(uow).broadcast_typing(chat_id, user, locale="en")

        frame = broadcast.await_args.args[1]
        assert frame["user_name"] == "bob@example.com"

    @pytest.mark.asyncio
    async def test_non_participant_forbidden_no_broadcast(self) -> None:
        uow = _mock_uow(is_participant=False)
        user = _mock_user()
        chat_id = uuid.uuid4()

        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ) as broadcast:
            with pytest.raises(Exception):  # noqa: B017 — raise_forbidden
                await _maintenance(uow).broadcast_typing(chat_id, user, locale="en")

        uow.chats.check_participant.assert_awaited_once_with(chat_id, user.id)
        broadcast.assert_not_awaited()
