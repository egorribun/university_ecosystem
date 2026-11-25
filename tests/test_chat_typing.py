"""Live typing indicator tests for ChatMaintenanceService.broadcast_typing.

SW7 adds REST POST /chats/{id}/typing because the frontend WS connects to ws-hub, whose
allowedMessageTypes drops "typing" at its parse boundary — so typing can't relay
peer-to-peer over the socket. The endpoint does participant authz + broadcast_to_chat
(the W204 bridge → ws-hub fan-out). Covers:
  - a participant broadcasts the typing frame (exclude_user_id = self; correct shape);
  - user_name resolution: profile.full_name when usable, else a neutral label;
  - a non-participant → forbidden, NO broadcast.

Mirrors the W206/W207 mock pattern (mock the uow/repo + patch ws_manager, no DB).
The full live cross-user flip is exercised at SW9.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.chat.command_service import ChatMaintenanceService


def _mock_uow(is_participant: bool) -> MagicMock:
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.chats.check_participant = AsyncMock(return_value=is_participant)
    return uow


def _maintenance(uow: MagicMock) -> ChatMaintenanceService:
    # (uow, attachment_service) — attachment_service is unused by broadcast_typing.
    return ChatMaintenanceService(uow, MagicMock())


def _mock_user(full_name: str | None = "Alice") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    if full_name is None:
        user.profile = None  # not eager-loaded or no profile row
    else:
        profile = MagicMock()
        profile.full_name = full_name
        user.profile = profile
    return user


class _UserWithoutEmailAccess:
    def __init__(self, profile: object) -> None:
        self.id = uuid.uuid4()
        self.profile = profile

    @property
    def email(self) -> str:
        raise AssertionError("typing must not read a private attribute")


class _UserWithoutProfileAccess:
    def __init__(self) -> None:
        self.id = uuid.uuid4()

    @property
    def profile(self) -> None:
        raise AssertionError("membership must be checked before reading the profile")


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
        assert kwargs["db_session"] is uow.session

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("profile", "locale", "expected"),
        [
            (None, "en", "Unknown User"),
            (None, "ru", "Неизвестный пользователь"),
            (SimpleNamespace(full_name=None), "en", "Unknown User"),
            (SimpleNamespace(full_name=""), "ru", "Неизвестный пользователь"),
            (SimpleNamespace(full_name="   "), "en", "Unknown User"),
            (None, "unsupported", "Unknown User"),
        ],
    )
    async def test_missing_name_is_neutral_and_never_reads_email(
        self, profile: object, locale: str, expected: str
    ) -> None:
        uow = _mock_uow(is_participant=True)
        user = _UserWithoutEmailAccess(profile)
        chat_id = uuid.uuid4()

        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ) as broadcast:
            await _maintenance(uow).broadcast_typing(chat_id, user, locale=locale)

        frame = broadcast.await_args.args[1]
        assert frame["user_name"] == expected
        assert 1 <= len(frame["user_name"]) <= 256
        assert frame["user_id"] == str(user.id)
        assert set(frame) == {"type", "chat_id", "user_id", "user_name"}
        uow.chats.check_participant.assert_awaited_once_with(chat_id, user.id)
        assert broadcast.await_args.kwargs["exclude_user_id"] == user.id
        assert broadcast.await_args.kwargs["db_session"] is uow.session

    @pytest.mark.asyncio
    async def test_profile_name_equal_to_user_id_is_preserved(self) -> None:
        uow = _mock_uow(is_participant=True)
        user = _UserWithoutEmailAccess(None)
        user.profile = SimpleNamespace(full_name=str(user.id))
        chat_id = uuid.uuid4()

        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ) as broadcast:
            await _maintenance(uow).broadcast_typing(chat_id, user, locale="ru")

        assert broadcast.await_args.args[1]["user_name"] == str(user.id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("profile_name", ["  Alice  ", "A" * 256])
    async def test_nonempty_profile_name_is_preserved_verbatim(
        self, profile_name: str
    ) -> None:
        uow = _mock_uow(is_participant=True)
        user = _UserWithoutEmailAccess(SimpleNamespace(full_name=profile_name))
        chat_id = uuid.uuid4()

        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ) as broadcast:
            await _maintenance(uow).broadcast_typing(chat_id, user, locale="ru")

        assert broadcast.await_args.args[1]["user_name"] == profile_name

    @pytest.mark.asyncio
    async def test_non_participant_forbidden_no_broadcast(self) -> None:
        uow = _mock_uow(is_participant=False)
        user = _UserWithoutProfileAccess()
        chat_id = uuid.uuid4()

        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new_callable=AsyncMock,
        ) as broadcast:
            with pytest.raises(HTTPException) as error:
                await _maintenance(uow).broadcast_typing(chat_id, user, locale="en")

        assert error.value.status_code == 403
        uow.chats.check_participant.assert_awaited_once_with(chat_id, user.id)
        broadcast.assert_not_awaited()
