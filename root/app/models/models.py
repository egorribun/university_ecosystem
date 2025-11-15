import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import UserRole
from app.utils.encryption import EncryptedString

ROLE_VALUES_SQL = ", ".join(f"'{role.value}'" for role in UserRole)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"role IN ({ROLE_VALUES_SQL})",
            name="ck_users_role_valid",
        ),
    )

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    full_name = Column(String)
    role = Column(String, nullable=False, default=UserRole.STUDENT.value, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"))
    is_active = Column(Boolean, default=True, index=True)
    mfa_required = Column(Boolean, default=False, nullable=False, index=True)
    mfa_default_method = Column(String(64))
    mfa_last_verified_at = Column(DateTime(timezone=True), nullable=True, index=True)
    mfa_recovery_codes_generated_at = Column(
        DateTime(timezone=True), nullable=True, index=True
    )

    avatar_url = Column(String)
    cover_url = Column(String)
    about = Column(String)
    record_book_number = Column(String)
    status = Column(String)
    institute = Column(String)
    course = Column(String)
    education_level = Column(String)
    track = Column(String)
    program = Column(String)
    telegram = Column(String)
    achievements = Column(String)
    department = Column(String)
    position = Column(String)

    dnd_enabled = Column(Boolean, default=False, nullable=False)
    dnd_start = Column(Time(timezone=False))
    dnd_end = Column(Time(timezone=False))
    timezone = Column(String(64))

    spotify_user_id = Column(String, unique=True, index=True)
    spotify_access_token = Column(EncryptedString())
    spotify_refresh_token = Column(EncryptedString())
    spotify_token_expires_at = Column(DateTime(timezone=True), index=True)
    spotify_scope = Column(String)
    spotify_display_name = Column(String)
    spotify_is_connected = Column(Boolean, default=False, index=True)
    spotify_is_playing = Column(Boolean, default=False, index=True)
    spotify_last_checked_at = Column(DateTime(timezone=True), index=True)
    spotify_last_track_id = Column(String, index=True)
    spotify_last_track_name = Column(String)
    spotify_last_artist_name = Column(String)
    spotify_last_album_name = Column(String)
    spotify_last_track_url = Column(String)
    spotify_last_album_image_url = Column(String)

    group = relationship("Group", back_populates="students", passive_deletes=True)
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    push_subscriptions = relationship(
        "PushSubscription",
        back_populates="user",
        passive_deletes=True,
    )
    push_topic_preferences = relationship(
        "UserPushTopic",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    sessions = relationship(
        "ActiveSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    totp_enrollments = relationship(
        "MfaTotpEnrollment",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    webauthn_credentials = relationship(
        "MfaWebAuthnCredential",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    recovery_codes = relationship(
        "MfaRecoveryCode",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    mfa_challenges = relationship(
        "MfaChallenge",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    email_change_tokens = relationship(
        "EmailChangeToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def spotify_connected(self) -> bool:
        return bool(self.spotify_is_connected)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    course = Column(Integer)
    faculty = Column(String)

    students = relationship("User", back_populates="group", passive_deletes=True)


class Schedule(Base):
    __tablename__ = "schedule"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject = Column(String, nullable=False)
    teacher = Column(String)
    room = Column(String)
    weekday = Column(String, index=True, nullable=False)
    start_time = Column(DateTime(timezone=True), index=True, nullable=False)
    end_time = Column(DateTime(timezone=True), index=True, nullable=False)
    parity = Column(String, default="both", index=True)
    lesson_type = Column(String, default=None)

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_schedule_time_order"),
        Index("ix_schedule_group_start_time", "group_id", "start_time"),
    )


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
    search_vector = Column(Text().with_variant(TSVECTOR(), "postgresql"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_active = Column(Boolean, default=True, index=True)
    speaker = Column(String)
    image_url = Column(String)
    about = Column(Text)
    about_en = Column(Text)

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_event_time_order"),
    )


def _generate_session_signing_key() -> str:
    return secrets.token_urlsafe(32)


class ActiveSession(Base):
    __tablename__ = "active_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jti = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    ip_address = Column(String(64))
    user_agent = Column(String(512))
    last_seen_at = Column(DateTime(timezone=True), nullable=True, index=True)
    signing_key = Column(String, nullable=False, default=_generate_session_signing_key)
    mfa_required = Column(Boolean, default=False, nullable=False, index=True)
    mfa_completed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    mfa_method = Column(String(64))
    mfa_verified_at = Column(DateTime(timezone=True), nullable=True, index=True)

    user = relationship("User", back_populates="sessions")
    challenges = relationship(
        "MfaChallenge",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MfaTotpEnrollment(Base):
    __tablename__ = "mfa_totp_enrollments"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    secret = Column(EncryptedString(), nullable=False)
    label = Column(String(255))
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="totp_enrollments")

    __table_args__ = (Index("ix_mfa_totp_enrollments_active", "user_id", "is_active"),)


class MfaWebAuthnCredential(Base):
    __tablename__ = "mfa_webauthn_credentials"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id = Column(String(255), nullable=False, unique=True)
    public_key = Column(Text, nullable=False)
    sign_count = Column(Integer, nullable=False, default=0)
    transports = Column(JSON, nullable=True)
    device_name = Column(String(255))
    backed_up = Column(Boolean, nullable=False, default=False, index=True)
    clone_warning = Column(Boolean, nullable=False, default=False)
    aaguid = Column(String(64), nullable=True, index=True)
    attestation_format = Column(String(64), nullable=True)
    attestation_trust_score = Column(Integer, nullable=True)
    attestation_metadata = Column(JSON, nullable=True)
    metadata_warnings = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    user = relationship("User", back_populates="webauthn_credentials")

    __table_args__ = (Index("ix_mfa_webauthn_user_active", "user_id", "is_active"),)


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash = Column(String(255), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    label = Column(String(255))

    user = relationship("User", back_populates="recovery_codes")

    __table_args__ = (
        UniqueConstraint("user_id", "code_hash", name="uq_mfa_recovery_codes_hash"),
    )


class MfaChallenge(Base):
    __tablename__ = "mfa_challenges"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id = Column(
        Integer, ForeignKey("active_sessions.id", ondelete="CASCADE"), nullable=True
    )
    challenge_type = Column(String(64), nullable=False, index=True)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload = Column(JSON, nullable=True)
    attempt_count = Column(Integer, nullable=False, server_default="0", default=0)

    user = relationship("User", back_populates="mfa_challenges")
    session = relationship("ActiveSession", back_populates="challenges")

    __table_args__ = (Index("ix_mfa_challenges_user_expires", "user_id", "expires_at"),)


class FailedLoginAttempt(Base):
    __tablename__ = "failed_login_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email = Column(String, nullable=False, index=True)
    attempted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_failed_login_attempts_email_attempted_at",
            "email",
            "attempted_at",
        ),
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


class EventFile(Base):
    __tablename__ = "event_files"

    id = Column(Integer, primary_key=True)
    event_id = Column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_url = Column(String, nullable=False)
    description = Column(String)


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    title_en = Column(String)
    content_en = Column(Text)
    image_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


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


class InviteCode(Base):
    __tablename__ = "invite_codes"
    __table_args__ = (
        CheckConstraint(
            f"role IN ({ROLE_VALUES_SQL})",
            name="ck_invite_codes_role_valid",
        ),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    is_used = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    used_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User")

    @staticmethod
    def issue_token() -> str:
        return secrets.token_urlsafe(32)


class EmailChangeToken(Base):
    __tablename__ = "email_change_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    new_email = Column(String, nullable=False, index=True)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="email_change_tokens")

    @property
    def is_active(self) -> bool:
        return not self.used and (
            self.expires_at is None or self.expires_at > datetime.now(UTC)
        )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime(timezone=True), index=True)

    user = relationship("User", back_populates="notifications")
    deliveries = relationship(
        "NotificationDelivery",
        back_populates="notification",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_dupe_check", "user_id", "title", "url", "created_at"),
        Index("ix_notifications_user_dedupe", "user_id", "dedupe_key"),
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
        Boolean, nullable=False, server_default=text("0"), index=True
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

    id = Column(Integer, primary_key=True)
    notification_id = Column(
        Integer,
        ForeignKey("notifications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel = Column(String, nullable=False, default="inapp", index=True)
    status = Column(String, nullable=False, default="delivered", index=True)
    attempted_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    delivered_at = Column(DateTime(timezone=True), index=True)
    status_code = Column(Integer)
    detail = Column(Text)

    notification = relationship("Notification", back_populates="deliveries")

    __table_args__ = (
        Index("ix_notification_deliveries_notif_channel", "notification_id", "channel"),
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
