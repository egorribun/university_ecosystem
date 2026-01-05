from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
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
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title = Column(String, nullable=False)
    title_en = Column(String)
    body = Column(Text)
    body_en = Column(Text)
    type = Column(String, index=True)
    url = Column(String)
    dedupe_key = Column(String(255), index=True)
    read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime(timezone=True), index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
        primary_key=not settings.database_url.startswith("sqlite"),
    )

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_dupe_check", "user_id", "title", "url", "created_at"),
        Index("ix_notifications_user_dedupe", "user_id", "dedupe_key"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    user = relationship("User", back_populates="notifications")
    deliveries = relationship(
        "NotificationDelivery",
        back_populates="notification",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class NotificationQueueJob(Base):
    __tablename__ = "notification_queue_jobs"

    id = Column(Integer, primary_key=True)
    kind = Column(String(16), nullable=False, index=True)
    record_id = Column(Integer, nullable=False)
    locale = Column(String(16))
    enqueued_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    claimed_at = Column(DateTime(timezone=True), index=True)
    attempts = Column(Integer, nullable=False, server_default=text("0"))
    last_error = Column(Text)
    next_retry_at = Column(DateTime(timezone=True), index=True)
    dead_lettered = Column(
        Boolean, nullable=False, server_default=text("false"), index=True
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


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(Integer, nullable=False, index=True)
    notification_created_at = Column(DateTime(timezone=True), nullable=False)
    channel = Column(String, nullable=False, default="inapp", index=True)
    status = Column(String, nullable=False, default="delivered", index=True)
    attempted_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        primary_key=not settings.database_url.startswith("sqlite"),
    )
    delivered_at = Column(DateTime(timezone=True), index=True)
    status_code = Column(Integer)
    detail = Column(Text)

    notification = relationship("Notification", back_populates="deliveries")

    __table_args__ = (
        ForeignKeyConstraint(
            ["notification_id", "notification_created_at"],
            ["notifications.id", "notifications.created_at"],
            ondelete="CASCADE",
        ),
        Index("ix_notification_deliveries_notif_channel", "notification_id", "channel"),
        {"postgresql_partition_by": "RANGE (attempted_at)"},
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = Column(Text, unique=True, nullable=False, index=True)
    p256dh = Column(String(200), nullable=False)
    auth = Column(String(200), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    user_agent = Column(String(512))
    last_seen_at = Column(DateTime(timezone=True), index=True)
    topics = Column(JSON, nullable=False, default=list)

    user = relationship("User", back_populates="push_subscriptions")


class UserPushTopic(Base):
    __tablename__ = "user_push_topics"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    topics = Column(JSON, nullable=False, default=list)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", back_populates="push_topic_preferences")
