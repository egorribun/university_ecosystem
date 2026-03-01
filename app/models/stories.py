import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    UUID,
    Boolean,
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

    title: Mapped[str] = mapped_column(String, nullable=False)
    title_en: Mapped[str | None] = mapped_column(String)
    short_text: Mapped[str] = mapped_column(Text, nullable=False)
    short_text_en: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(String)
    cta_url: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
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
    created_at: Mapped[datetime] = mapped_column(
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
        target.published_at = _utcnow()  # type: ignore[unreachable]
    if target.expires_at is None:
        if target.published_at is not None:  # type: ignore[unreachable]
            target.expires_at = target.published_at + timedelta(hours=24)


@event.listens_for(Story, "before_update")
def _ensure_story_expiration(_, __, target: "Story") -> None:
    if target.published_at is None:
        target.published_at = _utcnow()  # type: ignore[unreachable]
    if target.expires_at is None:
        if target.published_at is not None:  # type: ignore[unreachable]
            target.expires_at = target.published_at + timedelta(hours=24)
