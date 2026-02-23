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

    __slots__ = ("_attr", "_default", "_factory", "_relation")

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
        # Keep track of the public name for clearer error messages if needed.
        pass

    def __get__(self, obj: Any, objtype: type | None = None) -> _T:
        if obj is None:
            return self  # type: ignore[return-value]
        related = getattr(obj, self._relation, None)
        if related is None:
            # Return a falsy neutral value that matches the declared type.
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
        lazy="selectin",
    )
    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    education_path = relationship(
        "EducationPath",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
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
    stats = relationship(
        "UserStats",
        uselist=False,
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
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
        lazy="select",
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
    trusted_devices = relationship(
        "TrustedDevice",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    webauthn_credentials = relationship(
        "WebAuthnCredential",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    recovery_codes = relationship(
        "RecoveryCode",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    login_history = relationship(
        "LoginHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="desc(LoginHistory.created_at)",
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
    full_name        = _DelegatedProperty[str | None]("profile",        "full_name",        None,               lambda: UserProfile())
    avatar_url       = _DelegatedProperty[str | None]("profile",        "avatar_url",       None,               lambda: UserProfile())
    cover_url        = _DelegatedProperty[str | None]("profile",        "cover_url",        None,               lambda: UserProfile())
    about            = _DelegatedProperty[str | None]("profile",        "about",            None,               lambda: UserProfile())
    telegram         = _DelegatedProperty[str | None]("profile",        "telegram",         None,               lambda: UserProfile())
    status           = _DelegatedProperty[str | None]("profile",        "status",           None,               lambda: UserProfile())
    achievements     = _DelegatedProperty[str | None]("profile",        "achievements",     None,               lambda: UserProfile())
    position         = _DelegatedProperty[str | None]("profile",        "position",         None,               lambda: UserProfile())
    department       = _DelegatedProperty[str | None]("profile",        "department",       None,               lambda: UserProfile())

    # ------------------------------------------------------------------
    # Preferences field delegation
    # ------------------------------------------------------------------
    timezone         = _DelegatedProperty[str | None]("preferences",    "timezone",         None,               lambda: UserPreferences())
    dnd_enabled      = _DelegatedProperty[bool]       ("preferences",    "dnd_enabled",      False,              lambda: UserPreferences())
    dnd_start        = _DelegatedProperty[time | None]("preferences",    "dnd_start",        None,               lambda: UserPreferences())
    dnd_end          = _DelegatedProperty[time | None]("preferences",    "dnd_end",          None,               lambda: UserPreferences())

    # ------------------------------------------------------------------
    # EducationPath field delegation
    # ------------------------------------------------------------------
    institute        = _DelegatedProperty[str | None]("education_path", "institute",        None,               lambda: EducationPath())
    course           = _DelegatedProperty[str | None]("education_path", "course",           None,               lambda: EducationPath())
    education_level  = _DelegatedProperty[str | None]("education_path", "education_level",  None,               lambda: EducationPath())
    track            = _DelegatedProperty[str | None]("education_path", "track",            None,               lambda: EducationPath())
    program          = _DelegatedProperty[str | None]("education_path", "program",          None,               lambda: EducationPath())
    record_book_number = _DelegatedProperty[str | None]("education_path", "record_book_number", None,         lambda: EducationPath())

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

    dnd_enabled = Column(Boolean, default=False, nullable=False)
    dnd_start = Column(Time(timezone=False))
    dnd_end = Column(Time(timezone=False))
    timezone = Column(String(64))

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

    # Fields moved from User
    full_name = Column(String)
    avatar_url = Column(String)
    cover_url = Column(String)

    # Fields moved from UserProfileDetail
    about = Column(String)
    telegram = Column(String)
    status = Column(String)
    achievements = Column(String)
    position = Column(String)
    department = Column(String)

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
    institute = Column(String)
    course = Column(String)
    education_level = Column(String)
    track = Column(String)
    program = Column(String)
    record_book_number = Column(String)

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

    # Attendance metrics
    attendance_percent = Column(Float, default=0.0)
    attendance_present = Column(Integer, default=0)
    attendance_total = Column(Integer, default=0)
    attendance_trend = Column(Float, default=0.0)

    # Grade metrics
    grades_average = Column(Float, default=0.0)
    grades_trend = Column(Float, default=0.0)

    # Participation metrics
    participation_events = Column(Integer, default=0)
    participation_hours = Column(Float, default=0.0)
    participation_groups = Column(Integer, default=0)
    participation_trend = Column(Integer, default=0)

    # General metadata
    last_computed_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="stats")

    def __repr__(self) -> str:
        return f"<UserStats(user_id={self.user_id})>"
