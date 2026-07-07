import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin
from app.models.mixins import UserFK, UUID7PrimaryKeyMixin


class Event(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "events"

    title: Mapped[str] = mapped_column(
        String(512), nullable=False, index=True
    )  # LOW-W19: bounded String
    title_en: Mapped[str | None] = mapped_column(String(512))  # LOW-W19: bounded String
    description: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(512))  # LOW-W19: bounded String
    location_en: Mapped[str | None] = mapped_column(
        String(512)
    )  # LOW-W19: bounded String
    event_type: Mapped[str | None] = mapped_column(
        String(128), index=True
    )  # LOW-W19: bounded String
    event_type_en: Mapped[str | None] = mapped_column(
        String(128)
    )  # LOW-W19: bounded String
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # RZ-W19-20: SET NULL instead of CASCADE — events should outlive their creators
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    search_vector: Mapped[Any] = mapped_column(
        Text().with_variant(TSVECTOR(), "postgresql"),
        Computed(
            "to_tsvector('simple', "
            "coalesce(title, '') || ' ' || "
            "coalesce(description, '') || ' ' || "
            "coalesce(location, '') || ' ' || "
            "coalesce(title_en, '') || ' ' || "
            "coalesce(description_en, '') || ' ' || "
            "coalesce(location_en, '') || ' ' || "
            "coalesce(about, '') || ' ' || "
            "coalesce(about_en, '') "
            ")",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    speaker: Mapped[str | None] = mapped_column(String(512))  # LOW-W19: bounded String
    image_url: Mapped[str | None] = mapped_column(
        String(2048)
    )  # LOW-W19: bounded String
    about: Mapped[str | None] = mapped_column(Text)
    about_en: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[Any | None] = mapped_column(
        Text().with_variant(Vector(1536), "postgresql"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_event_time_order"),
        Index(
            "ix_events_embedding",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_events_starts_at_is_active", "starts_at", "is_active"),
    )
    # RZ-23-01 (audit 2026-03-25 Wave 23): Changed lazy="selectin" → lazy="noload".
    # lazy="selectin" fires unconditional secondary SELECTs on every Event load,
    # even when .files/.attendance are never accessed (list pages, calendar views).
    # With lazy="noload" the decision is explicit: query paths that need these
    # collections add .options(selectinload(Event.files)) themselves.
    files = relationship(
        "EventFile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    attendance = relationship(
        "EventAttendance",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    organizer = relationship("User", lazy="noload")  # DEBT-W19: avoid implicit load

    def __repr__(self) -> str:
        return (
            f"<Event(id={self.id}, title='{self.title[:20]}...', "
            f"starts_at={self.starts_at})>"
        )


class EventAttendance(Base, EventEmitterMixin, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "event_attendance"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    qr_secret: Mapped[str] = mapped_column(String(255))  # LOW-W19: bounded String
    qr_hmac: Mapped[str] = mapped_column(String(255))  # LOW-W19: bounded String

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_event_attendance_user_event"),
        Index("ix_event_attendance_event_user", "event_id", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<EventAttendance(id={self.id}, user_id={self.user_id}, "
            f"event_id={self.event_id})>"
        )


class EventFile(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "event_files"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_url: Mapped[str] = mapped_column(String(2048))  # LOW-W19: bounded String
    description: Mapped[str | None] = mapped_column(
        String(2048)
    )  # LOW-W19: bounded String

    def __repr__(self) -> str:
        return (
            f"<EventFile(id={self.id}, eid={self.event_id}, "
            f"url='{self.file_url[:20]}...')>"
        )
