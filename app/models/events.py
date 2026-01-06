from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import relationship

from app.core.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    title_en = Column(String)
    description = Column(Text)
    description_en = Column(Text)
    location = Column(String)
    location_en = Column(String)
    event_type = Column(String, index=True)
    event_type_en = Column(String)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    search_vector = Column(
        Text().with_variant(TSVECTOR(), "postgresql"),
        server_default=FetchedValue(),
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_active = Column(Boolean, default=True, index=True)
    speaker = Column(String)
    image_url = Column(String)
    about = Column(Text)
    about_en = Column(Text)

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_event_time_order"),
    )
    files = relationship(
        "EventFile", cascade="all, delete-orphan", passive_deletes=True
    )
    attendance = relationship(
        "EventAttendance", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return (
            f"<Event(id={self.id}, title='{self.title[:20]}...', "
            f"starts_at={self.starts_at})>"
        )


class EventAttendance(Base):
    __tablename__ = "event_attendance"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id = Column(
        Integer,
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


class EventFile(Base):
    __tablename__ = "event_files"

    id = Column(Integer, primary_key=True)
    event_id = Column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_url = Column(String, nullable=False)
    description = Column(String)

    def __repr__(self) -> str:
        return (
            f"<EventFile(id={self.id}, eid={self.event_id}, "
            f"url='{self.file_url[:20]}...')>"
        )
