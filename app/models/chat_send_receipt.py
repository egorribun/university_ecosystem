"""Private durable evidence of a completed keyed chat send."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class ChatSendReceipt(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "chat_send_receipts"

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
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "user_id",
            "key_digest",
            name="uq_chat_send_receipts_chat_user_key",
        ),
        Index("ix_chat_send_receipts_message_id", "message_id"),
        Index("ix_chat_send_receipts_user_id", "user_id"),
        Index("ix_chat_send_receipts_expires_at", "expires_at", "id"),
    )
