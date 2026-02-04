import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Column,
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

    title = Column(String, nullable=False, index=True)
    title_en = Column(String)
    description = Column(Text)
    description_en = Column(Text)
    location = Column(String)
    location_en = Column(String)
    event_type = Column(String, index=True)
    event_type_en = Column(String)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    search_vector = Column(
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_active = Column(Boolean, default=True, index=True)
    speaker = Column(String)
    image_url = Column(String)
    about = Column(Text)
    about_en = Column(Text)
    embedding = Column(Text().with_variant(Vector(1536), "postgresql"))

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_event_time_order"),
        Index(
            "ix_events_embedding",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    files = relationship(
        "EventFile", cascade="all, delete-orphan", passive_deletes=True
    )
    attendance = relationship(
        "EventAttendance", cascade="all, delete-orphan", passive_deletes=True
    )
    organizer = relationship("User")

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
    registered_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    qr_secret = Column(String, nullable=False)
    qr_hmac = Column(String, nullable=False)

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
    file_url = Column(String, nullable=False)
    description = Column(String)

    def __repr__(self) -> str:
        return (
            f"<EventFile(id={self.id}, eid={self.event_id}, "
            f"url='{self.file_url[:20]}...')>"
        )
