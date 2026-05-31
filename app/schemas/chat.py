from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from app.schemas.base import SecureBaseModel


# Simplified User schema for chat participants (avoids lazy-loaded relationships)
class ChatParticipant(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool


class PresenceStatus(SecureBaseModel):
    """Represents a participant's presence state."""

    active: bool = False
    last_seen_at: datetime | None = None


class MessageBase(SecureBaseModel):
    # TD-W5-02: Enforce maximum length so the DB column and HTTP body are both bounded.
    content: str = Field(..., min_length=1, max_length=2000)


class MessageCreate(MessageBase):
    # Wave 207 — optional reply target. The send endpoint accepts this as a Form
    # field; this schema documents the create shape.
    reply_to_message_id: UUID | None = None


class AttachmentResponse(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    file_type: str
    filename: str
    size: int
    created_at: datetime | None = None
    message_id: UUID | None = None


class ReactionAggregate(SecureBaseModel):
    """Wave 206 — per-emoji reaction tally on a message.

    `reacted_by_me` is computed server-side for the requesting user on the REST
    path (the aggregation in ChatQueryService knows current_user). On the WS
    delta-frame path the client derives it locally — it's per-viewer, so it can
    never travel in a broadcast frame.
    """

    emoji: str
    count: int
    reacted_by_me: bool = False


class ReactorOut(SecureBaseModel):
    """Wave 207 — one user in the reactor-list ("who reacted") popover.

    Built by ChatQueryService.get_reactors from the User rows the repository joins
    via message_reactions. ``user_id`` is remapped explicitly in the service (the
    User row has ``.id``, not ``.user_id``) — no from_attributes auto-mapping; only
    plain User columns (no relationship access → no N+1).
    """

    user_id: UUID
    name: str | None = None
    avatar_url: str | None = None


# Wave 207 — a reply quote-preview carries only what the FE renders above a reply
# bubble: who + a snippet + a deleted flag. Content is truncated so a reply never
# ships its target's full body; the FE line-clamps the rest. A LEAN preview (not a
# nested MessageResponse) keeps the payload small and sidesteps recursion.
REPLY_PREVIEW_MAX_CHARS = 200


class ReplyPreview(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    sender_name: str | None = None
    content: str
    deleted_at: datetime | None = None

    @classmethod
    def from_message(cls, dto: Any) -> ReplyPreview | None:
        """Build a preview from a (possibly None) replied-to message DTO.

        Duck-typed (``Any``) to avoid a response→DTO-layer import. Returns None
        when there is no reply target. ``content`` is truncated to
        REPLY_PREVIEW_MAX_CHARS; a soft-deleted target carries content="" +
        deleted_at set, which the FE renders as an "original deleted" placeholder.
        """
        if dto is None:
            return None
        sender = getattr(dto, "sender", None)
        return cls(
            id=dto.id,
            sender_id=dto.sender_id,
            sender_name=(sender.full_name if sender else None),
            content=(dto.content or "")[:REPLY_PREVIEW_MAX_CHARS],
            deleted_at=dto.deleted_at,
        )


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    # Wave 205 SW4 — override MessageBase.content's min_length=1. A soft-deleted
    # message (D1 tombstone) carries content="" in the RESPONSE, so the strict
    # create-time min_length must not apply on the way out, or GET /messages 500s
    # (pydantic string_too_short) the moment a chat contains a deleted message.
    # `Field(...)` keeps content REQUIRED (the producer always sends it) — only the
    # min_length floor is dropped. Input validation stays strict: MessageCreate
    # keeps min_length=1, and the POST/PATCH routes parse content via
    # Form(..., min_length=1).
    content: str = Field(..., max_length=2000)
    id: UUID
    chat_id: UUID
    sender_id: UUID
    created_at: datetime
    read_status: bool
    read_at: datetime | None = None  # Wave 203 SW3 — read-receipt timestamp
    edited_at: datetime | None = None  # Wave 205 SW4 — edit timestamp
    deleted_at: datetime | None = None  # Wave 205 SW4 — soft-delete tombstone
    sender: ChatParticipant | None = None
    sender_presence: PresenceStatus | None = None
    attachments: list[AttachmentResponse] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    # Wave 206 — per-emoji reaction aggregates. Built field-by-field in
    # ChatQueryService.get_messages (W203-SW8 two-site rule); the chat-list
    # last-message preview leaves this [] (lightweight projection).
    reactions: list[ReactionAggregate] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    # Wave 207 — quote preview of the message this one replies to (None = not a
    # reply). Built in ChatQueryService.get_messages from the selectinload'd
    # replied_to; the chat-list last-message preview leaves it None (lightweight
    # projection, W203-SW8 two-site rule).
    reply_to: ReplyPreview | None = None


class ChatBase(SecureBaseModel):
    pass


class ChatCreate(ChatBase):
    participant_id: UUID  # The ID of the user to start a chat with


class ChatResponse(ChatBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    participants: list[ChatParticipant]
    last_message: MessageResponse | None = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime
    presence: dict[UUID, PresenceStatus] | None = None


class ChatsListOut(SecureBaseModel):
    """Paginated list of chats."""

    items: list[ChatResponse]
    has_more: bool = False
    next_cursor: str | None = None


class MessagesListOut(SecureBaseModel):
    """Paginated list of messages."""

    items: list[MessageResponse]
    has_more: bool = False
    next_cursor: str | None = None


class ChatMaintenanceResult(SecureBaseModel):
    """Represents the result of a maintenance operation on a chat."""

    chat_id: UUID
    status: str
    deleted_messages: int = 0
    deleted_attachments: int = 0
