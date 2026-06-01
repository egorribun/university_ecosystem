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
    # Wave 209 G1 — group-chat identity. chat_type discriminates a 1-on-1 DM
    # ("dm") from a named group ("group"). A plain String(20) + CheckConstraint
    # (mirroring Attachment.file_type), NOT a StrEnum: it is a closed two-value
    # display discriminator, not a widely-used authz role like UserRole.
    # default="dm" (Python) populates the ORM object in-memory at flush so the
    # untouched create_chat DM path's _to_dto read is safe — a server-default-ONLY
    # column is left expired post-INSERT, and a sync pydantic model_validate of an
    # expired column in an async session would trigger a lazy refresh
    # (MissingGreenlet). server_default="dm" (DDL) backfills existing rows in the
    # same ALTER + covers non-ORM inserts; autogenerate only compares the DDL
    # default, so both-defaults stays diff-clean. name is the group's display
    # title (NULL for DMs — the FE derives a DM's label from the other
    # participant). created_by is the group owner; ondelete="SET NULL" so deleting
    # an owner account never cascade-deletes the group (it becomes ownerless —
    # only self-leave removes members until a later ownership-transfer wave).
    # chat_participants stays a plain M2M Table (no per-member role): the model is
    # already N-participant capable, so G1 adds identity + a create/membership
    # flow, not roles.
    chat_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="dm", server_default="dm"
    )  # 'dm' | 'group'
    name: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    __table_args__ = (
        CheckConstraint("chat_type IN ('dm', 'group')", name="ck_chats_chat_type"),
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
    # Wave 211 — foreign_keys="Message.chat_id" disambiguates the join: Message
    # now has TWO chats.id FKs (chat_id + the audit-only forwarded_from_chat_id),
    # so the Chat↔Message link is no longer inferable. chat_id is the membership
    # FK; forwarded_from_chat_id is never traversed by a relationship (privacy).
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="chat",
        foreign_keys="Message.chat_id",
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
    # Wave 211 — message forwarding (snapshot-copy). A forwarded message is a
    # fresh, self-contained copy in the DESTINATION chat: content + attachments
    # are copied at forward time and forwarded_from_name is a denormalized
    # "Forwarded from X" label. This is the privacy-safe model — the source may
    # live in a chat the destination viewer cannot access, so NOTHING here is
    # ever dereferenced to render source content cross-chat (contrast W207's
    # replied_to, safe only because message_exists_in_chat pins a reply to the
    # SAME chat). forwarded_from_name is the ONLY field the FE renders; the two
    # *_id columns are AUDIT-ONLY (never serialized, never dereferenced).
    # ondelete="SET NULL" (like reply_to_message_id, NOT CASCADE) so deleting the
    # source chat/message never deletes the forward. forwarded_from_message_id is
    # indexed — a self-FK to messages.id whose SET NULL sweep can fire in bulk
    # when a chat is hard-deleted (chat_id CASCADE), exactly the
    # reply_to_message_id / DEBT-02 rationale. forwarded_from_chat_id is NOT
    # indexed (matches the un-indexed Chat.created_by SET NULL FK: a chats.id
    # sweep fires only on the rare chat deletion and chats are few).
    forwarded_from_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=None
    )
    forwarded_from_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    forwarded_from_message_id: Mapped[uuid.UUID | None] = mapped_column(
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
    # Wave 211 — foreign_keys="Message.chat_id" (see Chat.messages): the audit-only
    # forwarded_from_chat_id is a second chats.id FK, so the membership join must
    # be stated explicitly.
    chat: Mapped[Chat] = relationship(
        "Chat",
        back_populates="messages",
        foreign_keys="Message.chat_id",
        lazy="noload",
    )
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
    # adjacency-list parent-pointer). Wave 211 added forwarded_from_message_id, a
    # SECOND Message→messages FK, so the join condition is no longer inferable —
    # foreign_keys="Message.reply_to_message_id" disambiguates which self-FK this
    # relationship traverses (without it SQLAlchemy raises AmbiguousForeignKeysError
    # at mapper configuration). No back_populates: we never render "messages that
    # replied to this", only the forward quote. lazy="noload" (MOD-30-01
    # explicit-lazy CI gate); ChatRepository.get_messages adds
    # selectinload(Message.replied_to) so the quote preview is a single extra
    # SELECT … WHERE id IN (…) per page, no N+1. forwarded_from_message_id is
    # AUDIT-ONLY and has NO relationship — it is never dereferenced (privacy).
    replied_to: Mapped[Message | None] = relationship(
        "Message",
        remote_side="Message.id",
        foreign_keys="Message.reply_to_message_id",
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


class ChatReadReceipt(Base, UUID7PrimaryKeyMixin):
    """Wave 210 G2 — per-recipient read high-water-mark for a GROUP chat.

    One row per (chat, user): ``last_read_at`` is the timestamp up to which this
    user has read the chat. Group unread = COUNT(messages WHERE sender_id != me
    AND (no receipt OR created_at > last_read_at)). DMs keep
    Message.read_status/read_at unchanged (Option A, W210 D1) — this table is
    GROUP-only in practice. No EventEmitterMixin: the read receipt broadcasts
    synchronously via broadcast_to_chat (the W203 rail), like MessageReaction —
    not through the domain-event outbox. The (chat_id, user_id) unique constraint
    makes mark_messages_read's upsert idempotent; the repo uses the dialect-
    agnostic SELECT-then-(UPDATE|INSERT) pattern (the add_participant precedent),
    NOT pg_insert.on_conflict (PG-only, would not compile on the SQLite test DB).
    last_read_at alone (no last_read_message_id): the high-water-mark count needs
    only the timestamp, and comparing created_at sidesteps the UUID7-ordering
    fragility a message-id comparison would carry. Unlike MessageReaction (whose
    unique key is user_id-leading, needing a separate message_id index), the
    (chat_id, user_id) unique key here is chat_id-leading, so it already serves
    both get_read_receipts (WHERE chat_id) and the unread-CTE join — no standalone
    index needed.
    """

    __tablename__ = "chat_read_receipts"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_read_receipts_chat_user"),
    )
