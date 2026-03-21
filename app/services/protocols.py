"""Protocol interfaces for the service layer.

TD-W9-02 (audit 2026-03-16): Define structural (Protocol) interfaces for all
public service contracts.  Callers in API handlers depend on these abstractions
rather than on concrete implementations — satisfying the Dependency Inversion
Principle (SOLID-D).

Why Protocols (structural) instead of ABCs (nominal)?
- No inheritance needed: concrete services remain unchanged.
- ``runtime_checkable`` enables isinstance() assertions in tests.
- mypy verifies structural compatibility at the call site without explicit
  declaration in the implementation class.

PY-P2-01 (audit Wave 10): each abstract method now uses `@abstractmethod` and
`raise NotImplementedError(...)` instead of the bare `...` ellipsis.  This
ensures that if a concrete class accidentally omits an implementation AND
somehow a Protocol instance is called directly (e.g. a stub injected in a test
that wasn't mocked), Python raises an informative error rather than returning
None silently.
"""

from __future__ import annotations

import uuid
from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fastapi import UploadFile

    from app.models.models import User
    from app.schemas.chat import (
        ChatMaintenanceResult,
        ChatResponse,
        ChatsListOut,
        MessageResponse,
        MessagesListOut,
    )

# ── Chat protocols ──────────────────────────────────────────────────────────


@runtime_checkable
class IChatCreationService(Protocol):
    """Creates DM chats with Redis-based deduplication."""

    @abstractmethod
    async def create_chat(
        self,
        user: User,
        participant_id: uuid.UUID | None,
        locale: str,
    ) -> ChatResponse:
        raise NotImplementedError(f"{type(self).__name__} must implement create_chat")


@runtime_checkable
class IChatQueryService(Protocol):
    """Read-only access to chats and messages."""

    @abstractmethod
    async def get_chats(
        self,
        user: User,
        cursor: str | None,
        limit: int,
    ) -> ChatsListOut:
        raise NotImplementedError(f"{type(self).__name__} must implement get_chats")

    @abstractmethod
    async def get_chat_details(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> ChatResponse:
        raise NotImplementedError(
            f"{type(self).__name__} must implement get_chat_details"
        )

    @abstractmethod
    async def get_messages(
        self,
        chat_id: uuid.UUID,
        user: User,
        cursor: str | None,
        limit: int,
        locale: str,
    ) -> MessagesListOut:
        raise NotImplementedError(f"{type(self).__name__} must implement get_messages")


@runtime_checkable
class IChatCommandService(Protocol):
    """Message dispatch and chat maintenance commands."""

    @abstractmethod
    async def send_message(
        self,
        chat_id: uuid.UUID,
        user: User,
        content: str,
        files: list[UploadFile],
        locale: str,
        idempotency_key: str | None = ...,
    ) -> MessageResponse:
        raise NotImplementedError(f"{type(self).__name__} must implement send_message")

    @abstractmethod
    async def mark_read(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement mark_read")

    @abstractmethod
    async def clear_history(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> ChatMaintenanceResult:
        raise NotImplementedError(f"{type(self).__name__} must implement clear_history")

    @abstractmethod
    async def delete_chat(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> ChatMaintenanceResult:
        raise NotImplementedError(f"{type(self).__name__} must implement delete_chat")


__all__ = [
    "IChatCommandService",
    "IChatCreationService",
    "IChatQueryService",
]
