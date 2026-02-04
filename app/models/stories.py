import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    UUID,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    event,
    func,
    text,
)

# Removed postgresql UUID import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Story(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "stories"
    __table_args__ = (
        Index("ix_stories_expires_at_is_active", "expires_at", "is_active"),
    )

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
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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
        return (
            f"<Story(id={self.id}, title='{self.title[:20]}...', "
            f"active={self.is_active})>"
        )


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
