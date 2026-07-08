import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

# Removed postgresql UUID import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UserFK, UUID7PrimaryKeyMixin


class Notification(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "notifications"

    title: Mapped[str] = mapped_column(
        String(512), nullable=False, index=True
    )  # LOW-W19: bounded String
    title_en: Mapped[str | None] = mapped_column(String(512))  # LOW-W19: bounded String
    body: Mapped[str | None] = mapped_column(Text)
    body_en: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(
        String(128), index=True
    )  # LOW-W19: bounded String
    url: Mapped[str | None] = mapped_column(String(2048))  # LOW-W19: bounded String
    dedupe_key: Mapped[str | None] = mapped_column(String(255), index=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(  # MED-W19: was Mapped[DateTime]
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
        primary_key=True,
    )

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_dupe_check", "user_id", "title", "url", "created_at"),
        Index("ix_notifications_user_dedupe", "user_id", "dedupe_key"),
        Index("ix_notifications_user_id_read", "user_id", "read"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    # TD-20-05 (audit 2026-03-24): Explicit noload prevents N+1.
    user = relationship("User", back_populates="notifications", lazy="noload")
    deliveries = relationship(
        "NotificationDelivery",
        back_populates="notification",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, user_id={self.user_id}, "
            f"title='{self.title[:20]}...')>"
        )


class NotificationQueueJob(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "notification_queue_jobs"

    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    locale: Mapped[str | None] = mapped_column(String(16))
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    dead_lettered: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('event', 'news')",
            name="ck_notification_queue_jobs_kind",
        ),
        UniqueConstraint(
            "kind", "record_id", name="uq_notification_queue_jobs_kind_record"
        ),
        Index("ix_notification_queue_jobs_kind_record", "kind", "record_id"),
        Index(
            "ix_notification_queue_jobs_pending_claim",
            "next_retry_at",
            "enqueued_at",
            "id",
            sqlite_where=text("dead_lettered = 0 AND claimed_at IS NULL"),
            postgresql_where=text("dead_lettered = false AND claimed_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        # LOW-W19: fixed missing opening bracket and class name in format string
        return f"<NotificationQueueJob(kind='{self.kind}', record_id={self.record_id})>"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)


class NotificationDelivery(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "notification_deliveries"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
    )
    notification_created_at: Mapped[datetime] = (
        mapped_column(  # MED-W19: was Mapped[DateTime]
            DateTime(timezone=True), nullable=False
        )
    )
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="inapp",
        index=True,  # LOW-W19: bounded String
    )
    # DEBT-03: subscription_id records which push subscription received this delivery.
    # NULL = in-app notification or skipped-no-subscription rows.
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="delivered",
        index=True,  # LOW-W19: bounded String
    )
    attempted_at: Mapped[datetime] = mapped_column(  # MED-W19: was Mapped[DateTime]
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        primary_key=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    status_code: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)

    notification = relationship(
        "Notification", back_populates="deliveries", lazy="noload"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["notification_id", "notification_created_at"],
            ["notifications.id", "notifications.created_at"],
            ondelete="CASCADE",
        ),
        Index("ix_notification_deliveries_notif_channel", "notification_id", "channel"),
        # DEBT-03: Dedup index for fast duplicate detection.
        # On PostgreSQL (partitioned table) this is non-unique; deduplication
        # is enforced at the application layer via INSERT ... ON CONFLICT DO NOTHING.
        # On SQLite (CI) the UniqueConstraint below enforces the invariant in tests.
        Index(
            "ix_notification_deliveries_dedup",
            "notification_id",
            "channel",
            "subscription_id",
        ),
        UniqueConstraint(
            "notification_id",
            "channel",
            "subscription_id",
            "attempted_at",
            name="uq_notification_delivery_once",
        ),
        {"postgresql_partition_by": "RANGE (attempted_at)"},
    )

    def __repr__(self) -> str:
        # LOW-W19: fixed missing opening bracket and class name in format string
        return (
            f"<NotificationDelivery(channel='{self.channel}', status='{self.status}')>"
        )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)


class PushSubscription(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "push_subscriptions"

    endpoint: Mapped[str] = mapped_column(Text, nullable=False, index=True, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    user_agent: Mapped[str | None] = mapped_column(String(512))
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    topics: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    user = relationship("User", back_populates="push_subscriptions", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<PushSubscription(id={self.id}, user_id={self.user_id}, "
            f"endpoint='{self.endpoint[:20]}...')>"
        )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)


class UserPushTopic(Base):
    __tablename__ = "user_push_topics"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    topics: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", back_populates="push_topic_preferences", lazy="noload")

    def __repr__(self) -> str:
        return f"<UserPushTopic(user_id={self.user_id}, topics={self.topics})>"
