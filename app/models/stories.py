from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (
        Index("ix_stories_expires_at_is_active", "expires_at", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    title_en = Column(String)
    short_text = Column(Text, nullable=False)
    short_text_en = Column(Text)
    cover_url = Column(String)
    cta_url = Column(String)
    published_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        index=True,
    )

    created_by_user = relationship("User")

    def __repr__(self) -> str:
        return f"<Story(id={self.id}, title='{self.title[:30]}...', active={self.is_active})>"


@event.listens_for(Story, "before_insert")
def _set_story_expiration(_, __, target: "Story") -> None:
    if target.published_at is None:
        target.published_at = _utcnow()
    if target.expires_at is None and target.published_at is not None:
        target.expires_at = target.published_at + timedelta(hours=24)


@event.listens_for(Story, "before_update")
def _ensure_story_expiration(_, __, target: "Story") -> None:
    if target.published_at is None:
        target.published_at = _utcnow()
    if target.expires_at is None and target.published_at is not None:
        target.expires_at = target.published_at + timedelta(hours=24)
