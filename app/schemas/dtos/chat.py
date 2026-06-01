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
    # Wave 211 — denormalized "Forwarded from X" label (snapshot-copy forwarding).
    # The silent-gatekeeper discipline (see ChatDTO): the repo model_validates the
    # ORM Message, so without this field the forwarded_from_name column loads from
    # the DB but Pydantic drops it and the query/command services never see it. A
    # plain scalar — no replied_to-style nesting, no selectinload — so it rides
    # every select(Message) read for free once declared here. The audit-only
    # forwarded_from_{chat,message}_id columns are deliberately NOT carried (never
    # serialized, never dereferenced cross-chat — privacy).
    forwarded_from_name: str | None = None


class ChatDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Wave 209 G1 — group-chat identity. The silent gatekeeper: the repository
    # returns ChatDTO (model_validate over the ORM Chat), so without these the new
    # columns load from the DB but Pydantic drops them and the query service has
    # nothing to forward into ChatResponse. chat_type defaults "dm" so a DM DTO is
    # valid even if read before refresh; name/created_by are NULL for DMs.
    chat_type: str = "dm"
    name: str | None = None
    created_by: uuid.UUID | None = None
    participants: list[ChatParticipantDTO] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    messages: list[MessageDTO] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
