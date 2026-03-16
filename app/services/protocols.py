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
"""

from __future__ import annotations

import uuid
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
    from app.schemas.search import SearchResult


# ── Chat protocols ──────────────────────────────────────────────────────────


@runtime_checkable
class IChatCreationService(Protocol):
    """Creates DM chats with Redis-based deduplication."""

    async def create_chat(
        self,
        user: User,
        participant_id: uuid.UUID | None,
        locale: str,
    ) -> ChatResponse: ...


@runtime_checkable
class IChatQueryService(Protocol):
    """Read-only access to chats and messages."""

    async def get_chats(
        self,
        user: User,
        cursor: str | None,
        limit: int,
    ) -> ChatsListOut: ...

    async def get_chat_details(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> ChatResponse: ...

    async def get_messages(
        self,
        chat_id: uuid.UUID,
        user: User,
        cursor: str | None,
        limit: int,
        locale: str,
    ) -> MessagesListOut: ...


@runtime_checkable
class IChatCommandService(Protocol):
    """Message dispatch and chat maintenance commands."""

    async def send_message(
        self,
        chat_id: uuid.UUID,
        user: User,
        content: str,
        files: list[UploadFile],
        locale: str,
        idempotency_key: str | None = ...,
    ) -> MessageResponse: ...

    async def mark_read(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> None: ...

    async def clear_history(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> ChatMaintenanceResult: ...

    async def delete_chat(
        self,
        chat_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> ChatMaintenanceResult: ...


# ── Search protocol ──────────────────────────────────────────────────────────


@runtime_checkable
class ISearchService(Protocol):
    """Full-text search across indexed content."""

    async def search(
        self,
        query: str,
        indices: list[str] | None = ...,
        *,
        size: int = ...,
        offset: int = ...,
    ) -> list[SearchResult]: ...

    async def index_document(
        self,
        index: str,
        document_id: str,
        body: dict,
    ) -> None: ...

    async def delete_document(
        self,
        index: str,
        document_id: str,
    ) -> None: ...


__all__ = [
    "IChatCommandService",
    "IChatCreationService",
    "IChatQueryService",
    "ISearchService",
]
