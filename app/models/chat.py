import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    UUID,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


def utc_now():
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

    participants = relationship(
        "User", secondary=chat_participants, backref="chats", lazy="noload"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan", lazy="noload"
    )


class Message(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "messages"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    read_status: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    chat: Mapped["Chat"] = relationship(
        "Chat", back_populates="messages", lazy="joined"
    )
    sender = relationship("User", lazy="joined")
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class Attachment(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "attachments"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # 'image', 'video', 'file'
    filename: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    # Relationships
    message: Mapped["Message"] = relationship(
        "Message", back_populates="attachments", lazy="joined"
    )
