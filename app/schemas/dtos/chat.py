from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import SecureBaseModel


class AttachmentDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    url: str
    file_type: str
    filename: str
    size: int
    created_at: datetime


class MessageReactionDTO(SecureBaseModel):
    # Wave 206 — raw reaction row (user_id + emoji) carried on MessageDTO. The
    # query service aggregates these into ReactionAggregate {emoji, count,
    # reacted_by_me}; only user_id + emoji are needed for that.
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    emoji: str


class ChatParticipantDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    is_active: bool = True


class MessageDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    sender_id: uuid.UUID
    content: str
    created_at: datetime
    read_status: bool = False
    read_at: datetime | None = None  # Wave 203 SW3 — read-receipt timestamp
    edited_at: datetime | None = None  # Wave 205 SW4
    deleted_at: datetime | None = None  # Wave 205 SW4
    sender: ChatParticipantDTO | None = None
    attachments: list[AttachmentDTO] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    # Wave 206 — raw reaction rows (populated by selectinload(Message.reactions)
    # in ChatRepository.get_messages; lazy="noload" yields [] when not loaded).
    reactions: list[MessageReactionDTO] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    # Wave 207 — the replied-to message (self-referential). Populated by
    # selectinload(Message.replied_to) in the repo read methods; lazy="noload"
    # yields None when not loaded. The nested DTO's own replied_to is noload →
    # None (no deep nesting). ChatQueryService flattens this into the lean
    # MessageResponse.reply_to preview.
    replied_to: MessageDTO | None = None


class ChatDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    participants: list[ChatParticipantDTO] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    messages: list[MessageDTO] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
