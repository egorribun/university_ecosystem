from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin
from app.models.enums import UserRole
from app.models.mixins import UUID7PrimaryKeyMixin
from app.models.spotify import SpotifyIntegration


class User(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "users"
    # DEBT-01 (RZ-W13): RFC 5321 §4.5.3.1.1 limits local-part to 64 chars and
    # domain to 255 chars → total max 320; we use 254 (RFC 5321 §4.5.3.1 total).
    # Prevents storage-amplification via unbounded email payloads.
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    # Argon2id hash format: $argon2id$v=19$m=32768,t=3,p=4$<salt>$<hash>
    # Max length: 97 bytes encoded (hex base64). Use 256 chars for safety margin.
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    pending_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    email_mfa_enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (Index("ix_users_email_lower", func.lower(email), unique=True),)

    role: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            native_enum=True,
            name="userrole",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=UserRole.STUDENT,
        index=True,
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    mfa_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    mfa_default_method: Mapped[str | None] = mapped_column(String(64))
    mfa_last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    mfa_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    preferences = relationship(
        "UserPreferences",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    # Integrations & other relationships
    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    education_path = relationship(
        "EducationPath",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        # PERF-NEW-002: Replaced selectin with noload to fix N+1 during bulk loads
        lazy="noload",
    )

    # Integrations & other relationships
    spotify = relationship(
        "SpotifyIntegration",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )

    group = (
        relationship(  # LOW-W19: add lazy="noload" to prevent N+1 on user list loads
            "Group", back_populates="users", passive_deletes=True, lazy="noload"
        )
    )
    # TD-5: lazy="noload" prevents N+1 when loading lists of users.
    # Load explicitly via selectinload(User.stats) in queries that need it.
    stats = relationship(
        "UserStats",
        uselist=False,
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    # PERF-1: Changed from lazy="selectin" to lazy="noload".
    # lazy="selectin" was firing an extra SELECT on EVERY User load, including
    # the hot path in auth-check deps (every HTTP request). At 100 rps this
    # caused 100 extra DB round-trips per second with no benefit outside the
    # /notifications endpoints. Use selectinload(User.notifications) at the
    # query site instead, only when notification data is actually needed.
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    # PERF-1: Changed from lazy="selectin" to lazy="noload" for the same
    # reason as notifications above — avoids SELECT on every User load.
    # Load with selectinload(User.push_subscriptions) only in the push
    # notification service where subscription data is actually consumed.
    push_subscriptions = relationship(
        "PushSubscription",
        back_populates="user",
        passive_deletes=True,
        lazy="noload",
    )
    push_topic_preferences = relationship(
        "UserPushTopic",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        # TD-5 (audit 2026-02-26): Changed from lazy="select" to lazy="noload" to
        # prevent an N+1 when loading lists of users (e.g. admin user list, event
        # attendees). Load with selectinload(User.push_topic_preferences) only in
        # endpoints that actually render push preferences.
        lazy="noload",
    )
    sessions = relationship(
        "ActiveSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    totp_enrollments = relationship(
        "MfaTotpEnrollment",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        # RZ-W19-15: changed from selectin to noload to prevent MissingGreenlet
        # in async context. Use explicit selectinload() via USER_MFA_LOAD_OPTIONS
        # when MFA data is actually needed.
        lazy="noload",
    )
    mfa_challenges = relationship(
        "MfaChallenge",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    email_change_tokens = relationship(
        "EmailChangeToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    trusted_devices = relationship(
        "TrustedDevice",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    recovery_codes = relationship(
        "RecoveryCode",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    # PERF-3: order_by on a relationship triggers a full-scan sort every time
    # the collection is accessed.  Use lazy="noload" and load explicitly with
    # an ordered query when login history is actually needed.
    login_history = relationship(
        "LoginHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    # Chat membership is an explicit bidirectional relation.  Do not use a
    # dynamically generated backref here: its implicit ``lazy="select"``
    # strategy performs synchronous IO when accessed from an async request.
    chats = relationship(
        "Chat",
        secondary="chat_participants",
        back_populates="participants",
        lazy="noload",
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)

        preferences_data = kwargs.pop("preferences", None)
        profile_data = kwargs.pop("profile", None) or kwargs.pop("profile_detail", None)
        education_data = kwargs.pop("education_path", None)

        super().__init__(**kwargs)

        if preferences_data is not None:
            if isinstance(preferences_data, dict):
                self.preferences = UserPreferences(**preferences_data)
            else:
                self.preferences = preferences_data

        if profile_data is not None:
            if isinstance(profile_data, dict):
                self.profile = UserProfile(**profile_data)
            else:
                self.profile = profile_data

        if education_data is not None:
            if isinstance(education_data, dict):
                self.education_path = EducationPath(**education_data)
            else:
                self.education_path = education_data

    @classmethod
    def create(
        cls,
        *,
        email: str,
        hashed_password: str,
        role: UserRole = UserRole.STUDENT,  # LOW-W19: use UserRole enum, not bare str
        is_active: bool = True,
        preferences: UserPreferences | dict[str, Any] | None = None,
        profile: UserProfile | dict[str, Any] | None = None,
        education_path: EducationPath | dict[str, Any] | None = None,
    ) -> User:
        """Factory method with explicit types over dynamic __init__ kwargs."""
        return cls(
            email=email,
            hashed_password=hashed_password,
            role=role,
            is_active=is_active,
            preferences=preferences,
            profile=profile,
            education_path=education_path,
        )

    @property
    def spotify_is_connected(self) -> bool:
        return bool(self.spotify and self.spotify.is_connected)

    @spotify_is_connected.setter
    def spotify_is_connected(self, value: bool) -> None:
        if not self.spotify:
            # LOW-W19: pass user_id so the new SpotifyIntegration is not an orphan
            self.spotify = SpotifyIntegration(user_id=self.id)
        self.spotify.is_connected = value

    @property
    def spotify_display_name(self) -> str | None:
        return self.spotify.display_name if self.spotify else None

    @spotify_display_name.setter
    def spotify_display_name(self, value: str | None) -> None:
        if not self.spotify:
            # LOW-W19: pass user_id so the new SpotifyIntegration is not an orphan
            self.spotify = SpotifyIntegration(user_id=self.id)
        self.spotify.display_name = value

    def __repr__(self) -> str:
        # Email is PII — omit from repr to prevent leakage into logs and tracebacks.
        return f"<User(id={self.id}, role='{self.role}')>"


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # TD-2: Use timezone-aware Time so the application can correctly compare DnD
    # window boundaries against UTC server time regardless of the user's locale.
    # Requires a new Alembic migration (ALTER COLUMN ... TYPE TIMETZ).
    dnd_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dnd_start: Mapped[time | None] = mapped_column(Time(timezone=True), nullable=True)
    dnd_end: Mapped[time | None] = mapped_column(Time(timezone=True), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user = relationship("User", back_populates="preferences", lazy="noload")  # RZ-33-06

    def __repr__(self) -> str:
        return f"<UserPreferences(user_id={self.user_id}, dnd={self.dnd_enabled})>"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # PERF-4 (audit 2026-02-26): All String columns were unbounded (TEXT in Postgres).
    # Without a column-level constraint a bug or attacker can store multi-MB values,
    # causing OOM on bulk user list queries.  Bounds reflect real-world field semantics.
    # Migration required: ALTER COLUMN ... TYPE VARCHAR(N)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    about: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(256), nullable=True)
    achievements: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    position: Mapped[str | None] = mapped_column(String(256), nullable=True)
    department: Mapped[str | None] = mapped_column(String(256), nullable=True)

    user = relationship("User", back_populates="profile", lazy="noload")  # RZ-33-06

    def __repr__(self) -> str:
        return f"<UserProfile(user_id={self.user_id})>"


class EducationPath(Base):
    __tablename__ = "user_education_paths"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # PERF-4 (audit 2026-02-26): Add length bounds — see UserProfile above.
    institute: Mapped[str | None] = mapped_column(String(512), nullable=True)
    course: Mapped[str | None] = mapped_column(String(64), nullable=True)
    education_level: Mapped[str | None] = mapped_column(String(128), nullable=True)
    track: Mapped[str | None] = mapped_column(String(256), nullable=True)
    program: Mapped[str | None] = mapped_column(String(512), nullable=True)
    record_book_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user = relationship(
        "User", back_populates="education_path", lazy="noload"
    )  # RZ-33-06

    def __repr__(self) -> str:
        return f"<EducationPath(user_id={self.user_id}, program='{self.program}')>"


class InviteCode(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(50))  # LOW-W19: bounded String
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    used_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<InviteCode(id={self.id}, code='{self.code}', used={self.is_used})>"


class UserStats(Base):
    """
    Pre-aggregated metrics to offload heavy OLAP queries from the OLTP critical path.
    Updated asynchronously via event consumers or cron jobs.
    """

    __tablename__ = "user_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # TD-1: Migrated from legacy Column() to typed Mapped[] for consistency with
    # the rest of the codebase and to benefit from SQLAlchemy 2.x type inference.
    # Attendance metrics
    attendance_percent: Mapped[float] = mapped_column(Float, default=0.0)
    attendance_present: Mapped[int] = mapped_column(Integer, default=0)
    attendance_total: Mapped[int] = mapped_column(Integer, default=0)
    attendance_trend: Mapped[float] = mapped_column(Float, default=0.0)

    # Grade metrics
    grades_average: Mapped[float] = mapped_column(Float, default=0.0)
    grades_trend: Mapped[float] = mapped_column(Float, default=0.0)

    # Participation metrics
    participation_events: Mapped[int] = mapped_column(Integer, default=0)
    participation_hours: Mapped[float] = mapped_column(Float, default=0.0)
    participation_groups: Mapped[int] = mapped_column(Integer, default=0)
    participation_trend: Mapped[int] = mapped_column(Integer, default=0)

    # General metadata
    last_computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="stats", lazy="noload")  # RZ-33-06

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<UserStats(user_id={self.user_id})>"
