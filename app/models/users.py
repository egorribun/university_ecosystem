import uuid
from collections.abc import Callable
from datetime import datetime, time
from typing import Any, Generic, TypeVar

from sqlalchemy import (
    UUID,
    Boolean,
    Column,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin
from app.models.enums import UserRole
from app.models.mixins import UUID7PrimaryKeyMixin
from app.models.spotify import SpotifyIntegration

_T = TypeVar("_T")


class _DelegatedProperty(Generic[_T]):
    """Descriptor that transparently delegates a field to a related ORM object.

    Usage (on the *owner* model)::

        full_name = _DelegatedProperty[str | None](
            "profile", "full_name", str | None, lambda: UserProfile()
        )

    On read:  returns ``owner.profile.full_name`` or ``None`` if the relation
              is not loaded yet.
    On write: lazily creates the related object via *factory* if it is absent,
              then sets the attribute on it.

    This eliminates the repetitive property + setter boilerplate that previously
    spanned ~200 lines of the User model for 15 delegated fields across three
    related tables.
    """

    __slots__ = ("_attr", "_default", "_factory", "_public_name", "_relation")

    def __init__(
        self,
        relation: str,
        attr: str,
        default: _T,
        factory: Callable[[], Any],
    ) -> None:
        self._relation = relation
        self._attr = attr
        self._default = default
        self._factory = factory

    def __set_name__(self, owner: type, name: str) -> None:
        # TD-2 (audit 2026-02-26): Store the public attribute name so that
        # __get__ can produce actionable debug messages when a relation is not
        # loaded, instead of silently returning the default value.
        self._public_name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> _T:
        if obj is None:
            return self  # type: ignore[return-value]
        related = getattr(obj, self._relation, None)
        if related is None:
            # Relation not loaded (lazy="noload" or not joined).  Log at DEBUG
            # so N+1 / noload misconfigurations surface in development.
            import logging as _logging

            _logging.getLogger(__name__).debug(
                "DelegatedProperty %s.%s accessed with unloaded relation '%s'",
                type(obj).__name__,
                getattr(self, "_public_name", "<unknown>"),
                self._relation,
            )
            return self._default
        return getattr(related, self._attr)  # type: ignore[no-any-return]

    def __set__(self, obj: Any, value: _T) -> None:
        related = getattr(obj, self._relation, None)
        if related is None:
            related = self._factory()
            setattr(obj, self._relation, related)
        setattr(related, self._attr, value)


class User(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "users"
    __allow_unmapped__ = True
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    pending_email: str | None = None

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
    group_id: Mapped[uuid.UUID] = mapped_column(
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
    webauthn_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True, nullable=True
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
        lazy="joined",
    )
    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="joined",
    )
    education_path = relationship(
        "EducationPath",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="joined",
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

    group = relationship("Group", back_populates="students", passive_deletes=True)
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
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    push_subscriptions = relationship(
        "PushSubscription",
        back_populates="user",
        passive_deletes=True,
        lazy="selectin",
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
        lazy="selectin",
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
    webauthn_credentials = relationship(
        "WebAuthnCredential",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
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

    def __init__(self, **kwargs) -> None:
        preferences_data = kwargs.pop("preferences", None)
        profile_data = kwargs.pop("profile", None) or kwargs.pop("profile_detail", None)
        education_data = kwargs.pop("education_path", None)

        super().__init__(**kwargs)

        # Auto-discover delegated fields from _DelegatedProperty descriptors so
        # adding a new field to UserProfile/UserPreferences/EducationPath never
        # requires a manual update here — the descriptor set is the single source
        # of truth.
        for field_name, descriptor in _DELEGATED_FIELDS.items():
            if field_name in kwargs:
                setattr(self, field_name, kwargs[field_name])

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

    @property
    def spotify_connected(self) -> bool:
        return bool(self.spotify and self.spotify.is_connected)

    @property
    def spotify_is_connected(self) -> bool:
        return self.spotify_connected

    @spotify_is_connected.setter
    def spotify_is_connected(self, value: bool) -> None:
        if not self.spotify:
            self.spotify = SpotifyIntegration()
        self.spotify.is_connected = value

    @property
    def spotify_display_name(self) -> str | None:
        return self.spotify.display_name if self.spotify else None

    @spotify_display_name.setter
    def spotify_display_name(self, value: str | None) -> None:
        if not self.spotify:
            self.spotify = SpotifyIntegration()
        self.spotify.display_name = value

    # ------------------------------------------------------------------
    # Profile field delegation
    # ------------------------------------------------------------------
    full_name = _DelegatedProperty[str | None](
        "profile", "full_name", None, lambda: UserProfile()
    )
    avatar_url = _DelegatedProperty[str | None](
        "profile", "avatar_url", None, lambda: UserProfile()
    )
    cover_url = _DelegatedProperty[str | None](
        "profile", "cover_url", None, lambda: UserProfile()
    )
    about = _DelegatedProperty[str | None](
        "profile", "about", None, lambda: UserProfile()
    )
    telegram = _DelegatedProperty[str | None](
        "profile", "telegram", None, lambda: UserProfile()
    )
    status = _DelegatedProperty[str | None](
        "profile", "status", None, lambda: UserProfile()
    )
    achievements = _DelegatedProperty[str | None](
        "profile", "achievements", None, lambda: UserProfile()
    )
    position = _DelegatedProperty[str | None](
        "profile", "position", None, lambda: UserProfile()
    )
    department = _DelegatedProperty[str | None](
        "profile", "department", None, lambda: UserProfile()
    )

    # ------------------------------------------------------------------
    # Preferences field delegation
    # ------------------------------------------------------------------
    timezone = _DelegatedProperty[str | None](
        "preferences", "timezone", None, lambda: UserPreferences()
    )
    dnd_enabled = _DelegatedProperty[bool](
        "preferences", "dnd_enabled", False, lambda: UserPreferences()
    )
    dnd_start = _DelegatedProperty[time | None](
        "preferences", "dnd_start", None, lambda: UserPreferences()
    )
    dnd_end = _DelegatedProperty[time | None](
        "preferences", "dnd_end", None, lambda: UserPreferences()
    )

    # ------------------------------------------------------------------
    # EducationPath field delegation
    # ------------------------------------------------------------------
    institute = _DelegatedProperty[str | None](
        "education_path", "institute", None, lambda: EducationPath()
    )
    course = _DelegatedProperty[str | None](
        "education_path", "course", None, lambda: EducationPath()
    )
    education_level = _DelegatedProperty[str | None](
        "education_path", "education_level", None, lambda: EducationPath()
    )
    track = _DelegatedProperty[str | None](
        "education_path", "track", None, lambda: EducationPath()
    )
    program = _DelegatedProperty[str | None](
        "education_path", "program", None, lambda: EducationPath()
    )
    record_book_number = _DelegatedProperty[str | None](
        "education_path", "record_book_number", None, lambda: EducationPath()
    )

    def __repr__(self) -> str:
        # Email is PII — omit from repr to prevent leakage into logs and tracebacks.
        return f"<User(id={self.id}, role='{self.role}')>"


# Introspect User class once at import time to find all _DelegatedProperty descriptors.
# User.__init__ uses this mapping to set delegated fields from kwargs — adding a new
# descriptor to the User class automatically makes it settable in the constructor.
_DELEGATED_FIELDS: dict[str, _DelegatedProperty[object]] = {
    name: descriptor
    for name, descriptor in vars(User).items()
    if isinstance(descriptor, _DelegatedProperty)
}


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

    user = relationship("User", back_populates="preferences")

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

    user = relationship("User", back_populates="profile")

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

    user = relationship("User", back_populates="education_path")

    def __repr__(self) -> str:
        return f"<EducationPath(user_id={self.user_id}, program='{self.program}')>"


class InviteCode(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "invite_codes"

    code = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    is_used = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    used_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

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

    user = relationship("User", back_populates="stats")

    def __repr__(self) -> str:
        return f"<UserStats(user_id={self.user_id})>"
