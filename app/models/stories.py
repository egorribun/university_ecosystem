import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

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

    title: Mapped[str] = mapped_column(
        String(512), nullable=False
    )  # LOW-W19: bounded String
    title_en: Mapped[str | None] = mapped_column(String(512))  # LOW-W19: bounded String
    short_text: Mapped[str] = mapped_column(Text, nullable=False)
    short_text_en: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(
        String(2048)
    )  # LOW-W19: bounded String
    cta_url: Mapped[str | None] = mapped_column(String(2048))  # LOW-W19: bounded String
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

    created_by_user = relationship(
        "User", lazy="noload"
    )  # DEBT-W19: avoid implicit load

    def __repr__(self) -> str:
        return (
            f"<Story(id={self.id}, title='{self.title[:20]}...', "
            f"active={self.is_active})>"
        )


@event.listens_for(Story, "before_insert")
def _set_story_expiration(_: Any, __: Any, target: "Story") -> None:
    if getattr(target, "published_at", None) is None:
        target.published_at = _utcnow()
    if getattr(target, "expires_at", None) is None:
        if target.published_at is not None:
            target.expires_at = target.published_at + timedelta(hours=24)


# LOW-W19: _ensure_story_expiration on "before_update" was a dead listener.
# expires_at is NOT NULL with no Python default, so on update it can never be
# None — the inner branch never fired.  published_at also has a server_default
# which guarantees it is set before any UPDATE. Removed to avoid confusion.
