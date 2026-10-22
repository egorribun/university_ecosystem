from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile

from app.core.protocols import AsyncDatabaseSession
from app.models import User
from app.models.chat import Chat, Message
from app.repositories.unit_of_work import uow_from_session
from app.schemas.dtos.chat import AttachmentDTO
from app.services.chat.command_service import (
    AttachmentProcessorProtocol,
    ChatMessageDispatcher,
)
from app.services.chat.notification_service import ChatNotificationService


class _Scalars:
    def __init__(self, rows: list[Message]) -> None:
        self._rows = rows

    def scalars(self) -> _Scalars:
        return self

    def all(self) -> list[Message]:
        return self._rows


class _PostgresSession:
    def __init__(self) -> None:
        self.active = True
        self.message: Message | None = None
        self.rls_user_ids: list[str] = []
        self.message_queries = 0
        self.commit_count = 0

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def in_transaction(self) -> bool:
        return self.active

    async def begin(self) -> None:
        self.active = True

    def add(self, _instance: object) -> None:
        return None

    async def execute(
        self, statement: object, parameters: object | None = None
    ) -> _Scalars | None:
        if "set_config" in str(statement):
            if not isinstance(parameters, dict):
                raise AssertionError("rls_parameters_must_be_mapping")
            value = parameters.get("uid")
            if not isinstance(value, str):
                raise AssertionError("rls_user_id_must_be_text")
            self.rls_user_ids.append(value)
            return None
        self.message_queries += 1
        if self.message is None:
            raise AssertionError("reloaded_message_must_exist")
        return _Scalars([self.message])

    async def commit(self) -> None:
        self.commit_count += 1
        self.active = False

    async def flush(self) -> None:
        return None

    async def rollback(self) -> None:
        self.active = False

    async def refresh(self, _instance: object) -> None:
        return None


class _NoAttachments:
    async def process_upload(
        self, upload: UploadFile, chat_id: uuid.UUID, *, locale: str | None
    ) -> dict[str, str | int]:
        del upload, chat_id, locale
        raise AssertionError("unexpected_upload_processing")

    async def cleanup_files(self, urls: list[str]) -> None:
        del urls
        return None

    async def copy_for_forward(
        self,
        attachment: AttachmentDTO,
        chat_id: uuid.UUID,
        *,
        locale: str | None,
    ) -> dict[str, str | int]:
        del attachment, chat_id, locale
        raise AssertionError("unexpected_attachment_forward")

    async def collect_urls(self, chat: Any) -> list[str]:
        del chat
        return []


@pytest.mark.asyncio
async def test_send_message_reloads_with_authorized_postgres_rls_context() -> None:
    chat_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session = _PostgresSession()
    uow = uow_from_session(cast(AsyncDatabaseSession, session))
    repository = uow.chats
    chat = cast(Chat, SimpleNamespace(id=chat_id, participants=[]))
    user = cast(User, SimpleNamespace(id=user_id))
    get_by_id = AsyncMock(return_value=chat)
    check_participant = AsyncMock(return_value=True)
    update_timestamp = AsyncMock()

    async def persist_message(message: Message) -> None:
        message.id = uuid.uuid4()
        message.created_at = datetime.now(UTC)
        message.read_status = False
        message.read_at = None
        message.edited_at = None
        message.deleted_at = None
        message.sender = None
        message.attachments = []
        message.reactions = []
        message.replied_to = None
        message.forwarded_from_name = None
        session.message = message

    create_message = AsyncMock(side_effect=persist_message)
    dispatcher = ChatMessageDispatcher(
        uow,
        cast(AttachmentProcessorProtocol, _NoAttachments()),
        ChatNotificationService(cast(AsyncDatabaseSession, session)),
    )

    with (
        patch.object(repository, "get_by_id", new=get_by_id),
        patch.object(repository, "check_participant", new=check_participant),
        patch.object(repository, "create_message", new=create_message),
        patch.object(repository, "update_timestamp_by_id", new=update_timestamp),
        patch("app.services.chat.command_service.ws_manager") as ws_manager,
    ):
        ws_manager.is_online.return_value = False
        response = await dispatcher.send_message(
            chat_id,
            user,
            "hello",
            [],
            "en",
        )

    if session.message is None:
        raise AssertionError("send_message_must_persist_message")
    if response.id != session.message.id:
        raise AssertionError("response_must_use_reloaded_message")
    if session.commit_count != 1:
        raise AssertionError("message_must_commit_once")
    if session.rls_user_ids != [str(user_id)]:
        raise AssertionError("reload_must_set_authenticated_rls_identity")
    if session.message_queries != 1:
        raise AssertionError("reload_must_query_persisted_message_once")
    get_by_id.assert_awaited_once_with(chat_id)
    check_participant.assert_awaited_once_with(chat_id, user_id)
    create_message.assert_awaited_once()
