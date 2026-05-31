from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin
from app.models.mixins import UUID7PrimaryKeyMixin


def utc_now() -> datetime:
    return datetime.now(UTC)


# Association table for many-to-many relationship between Chat and User
chat_participants = Table(
    "chat_participants",
    Base.metadata,
    Column(
        "chat_id",
        UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Chat(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "chats"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    # RZ-14-01 (audit 2026-03-23): Changed lazy="selectin" → lazy="noload".
    # lazy="selectin" is an *unconditional* load strategy — SQLAlchemy fires a
    # second SELECT … WHERE chat_id IN (…) for every Chat loaded, even when the
    # participants collection is never accessed (e.g. feed queries, updated_at
    # checks).  This produces 2 round-trips for any endpoint that loads Chats.
    # With lazy="noload" (mirroring Chat.messages on line 58) the decision is
    # explicit at the call site: query paths that need participants add
    # .options(selectinload(Chat.participants)) themselves.
    participants = relationship(
        "User", secondary=chat_participants, backref="chats", lazy="noload"
    )
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class Message(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "messages"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # DEBT-01 (RZ-W13): 32 KB cap matches frontend WS validation; prevents
    # storage-amplification via oversized message payloads.
    content: Mapped[str] = mapped_column(String(32768), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    read_status: Mapped[bool] = mapped_column(Boolean, default=False)
    # Wave 203 SW2 — read-receipt timestamp. NULL until the message is marked
    # read; set to utc_now() by ChatRepository.mark_messages_read. A column (not
    # a relationship), so the MOD-30-01 explicit-lazy CI gate does not apply.
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # Wave 205 SW2 — edit + soft-delete timestamps. Both NULL until the message is
    # edited / soft-deleted. Columns (not relationships), so the MOD-30-01
    # explicit-lazy CI gate does not apply. Soft-delete keeps the row as a tombstone
    # (content is cleared in the repo) so a "Message deleted" placeholder survives a
    # refetch; queries deliberately do NOT filter deleted_at (W205 D1).
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # Wave 207 — reply/quote self-FK. NULL = not a reply. ondelete="SET NULL"
    # (NOT CASCADE like Attachment/MessageReaction): a reply is a standalone
    # message that merely *references* an earlier one, so if the target is
    # deleted the reply survives — this column nulls out and the FE renders an
    # "original deleted" placeholder. DEBT-02 pattern: explicit index — a FK
    # without an index full-scans on the SET NULL sweep (PG must find every row
    # referencing a just-deleted message id to null it). The get_messages
    # selectinload of replied_to filters on messages.id (the PK, already
    # indexed), so this index serves the delete sweep, not the read.
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )

    # Relationships
    # RZ-23-03 (audit 2026-03-25 Wave 23): Changed lazy="joined" → lazy="noload".
    # lazy="joined" fires unconditional JOINs on every Message load. On bulk
    # message fetches (50-msg pagination), this adds 2 JOINs where the parent
    # context (chat_id, sender_id) is already known as FK columns.
    # Repository already uses selectinload(Message.sender) at all call sites.
    chat: Mapped[Chat] = relationship("Chat", back_populates="messages", lazy="noload")
    sender = relationship("User", lazy="noload")
    attachments: Mapped[list[Attachment]] = relationship(
        "Attachment",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    # Wave 206 — message reactions (👍❤️😂😮😢). lazy="noload" per MOD-30-01
    # (explicit-lazy CI gate); ChatRepository.get_messages adds
    # selectinload(Message.reactions) so the aggregation is a single extra
    # SELECT … WHERE message_id IN (…) per page, never an N+1.
    reactions: Mapped[list[MessageReaction]] = relationship(
        "MessageReaction",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    # Wave 207 — the message this one replies to (self-referential many-to-one).
    # remote_side="Message.id" marks id as the parent/target side (Context7
    # adjacency-list parent-pointer); reply_to_message_id is the sole Message→
    # messages FK, so the join condition is inferred (no foreign_keys needed).
    # No back_populates: we never render "messages that replied to this", only
    # the forward quote. lazy="noload" (MOD-30-01 explicit-lazy CI gate);
    # ChatRepository.get_messages adds selectinload(Message.replied_to) so the
    # quote preview is a single extra SELECT … WHERE id IN (…) per page, no N+1.
    replied_to: Mapped[Message | None] = relationship(
        "Message",
        remote_side="Message.id",
        lazy="noload",
    )


class Attachment(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "attachments"

    # DEBT-02 (RZ-W13): explicit index — FK without index causes full-table scan
    # on DELETE CASCADE from messages and on attachment load per message.
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    __table_args__ = (
        # MED-W19: prevent javascript: and other non-http(s) URL schemes.
        CheckConstraint(
            "url LIKE 'http://%' OR url LIKE 'https://%'",
            name="ck_attachment_url_scheme",
        ),
    )

    # DEBT-01 (RZ-W13): bounded String columns prevent storage-amplification attacks.
    file_type: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # 'image', 'video', 'file'
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    # Relationships
    # RZ-23-03 (audit 2026-03-25 Wave 23): Changed lazy="joined" → lazy="noload".
    message: Mapped[Message] = relationship(
        "Message", back_populates="attachments", lazy="noload"
    )


class MessageReaction(Base, UUID7PrimaryKeyMixin):
    """Wave 206 — a single emoji reaction by one user on one message.

    Per-(user, message, emoji) child row of Message (the first many-per-message
    fact in the chat domain — mirrors the Attachment child-table pattern). The
    (user_id, message_id, emoji) unique constraint makes a reaction idempotent;
    the repo's pg_insert(...).on_conflict_do_nothing targets it. No
    EventEmitterMixin: reactions broadcast synchronously via broadcast_to_chat
    (the W203/W205 rail), not through the domain-event outbox.
    """

    __tablename__ = "message_reactions"

    # DEBT-02 pattern (mirrors Attachment.message_id): explicit index — the
    # get_messages aggregation does selectinload → WHERE message_id IN (…); the
    # (user_id, message_id, emoji) unique constraint is user_id-leading, so it
    # does NOT serve message_id lookups.
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Bounded — holds one multi-codepoint emoji (e.g. ❤️ = U+2764 U+FE0F);
    # matches the POST /reactions Form(max_length=16) cap.
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "message_id",
            "emoji",
            name="uq_message_reactions_user_message_emoji",
        ),
    )

    # lazy="noload" (MOD-30-01 explicit-lazy CI gate).
    message: Mapped[Message] = relationship(
        "Message", back_populates="reactions", lazy="noload"
    )
