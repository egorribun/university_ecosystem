import uuid
from datetime import datetime, time

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


class User(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)

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
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    mfa_default_method: Mapped[str | None] = mapped_column(String(64))
    mfa_last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    webauthn_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

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

        # Legacy field shim support
        for field in ["dnd_enabled", "dnd_start", "dnd_end", "timezone"]:
            if field in kwargs:
                setattr(self, field, kwargs[field])

        for field in [
            "full_name",
            "about",
            "telegram",
            "status",
            "achievements",
            "position",
            "department",
        ]:
            if field in kwargs:
                setattr(self, field, kwargs[field])

        for field in [
            "institute",
            "course",
            "education_level",
            "track",
            "program",
            "record_book_number",
        ]:
            if field in kwargs:
                setattr(self, field, kwargs[field])

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

    @property
    def full_name(self) -> str | None:
        return self.profile.full_name if self.profile else None

    @full_name.setter
    def full_name(self, value: str) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.full_name = value

    @property
    def avatar_url(self) -> str | None:
        return self.profile.avatar_url if self.profile else None

    @avatar_url.setter
    def avatar_url(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.avatar_url = value

    @property
    def cover_url(self) -> str | None:
        return self.profile.cover_url if self.profile else None

    @cover_url.setter
    def cover_url(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.cover_url = value

    @property
    def timezone(self) -> str | None:
        return self.preferences.timezone if self.preferences else None

    @timezone.setter
    def timezone(self, value: str | None) -> None:
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.timezone = value

    @property
    def dnd_enabled(self) -> bool:
        return self.preferences.dnd_enabled if self.preferences else False

    @dnd_enabled.setter
    def dnd_enabled(self, value: bool) -> None:
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.dnd_enabled = value

    @property
    def dnd_start(self) -> time | None:
        return self.preferences.dnd_start if self.preferences else None

    @dnd_start.setter
    def dnd_start(self, value: time | None) -> None:
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.dnd_start = value

    @property
    def dnd_end(self) -> time | None:
        return self.preferences.dnd_end if self.preferences else None

    @dnd_end.setter
    def dnd_end(self, value: time | None) -> None:
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.dnd_end = value

    @property
    def about(self) -> str | None:
        return self.profile.about if self.profile else None

    @about.setter
    def about(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.about = value

    @property
    def telegram(self) -> str | None:
        return self.profile.telegram if self.profile else None

    @telegram.setter
    def telegram(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.telegram = value

    @property
    def status(self) -> str | None:
        return self.profile.status if self.profile else None

    @status.setter
    def status(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.status = value

    @property
    def achievements(self) -> str | None:
        return self.profile.achievements if self.profile else None

    @achievements.setter
    def achievements(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.achievements = value

    @property
    def position(self) -> str | None:
        return self.profile.position if self.profile else None

    @position.setter
    def position(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.position = value

    @property
    def department(self) -> str | None:
        return self.profile.department if self.profile else None

    @department.setter
    def department(self, value: str | None) -> None:
        if not self.profile:
            self.profile = UserProfile()
        self.profile.department = value

    @property
    def institute(self) -> str | None:
        return self.education_path.institute if self.education_path else None

    @institute.setter
    def institute(self, value: str | None) -> None:
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.institute = value

    @property
    def course(self) -> str | None:
        return self.education_path.course if self.education_path else None

    @course.setter
    def course(self, value: str | None) -> None:
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.course = value

    @property
    def education_level(self) -> str | None:
        return self.education_path.education_level if self.education_path else None

    @education_level.setter
    def education_level(self, value: str | None) -> None:
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.education_level = value

    @property
    def track(self) -> str | None:
        return self.education_path.track if self.education_path else None

    @track.setter
    def track(self, value: str | None) -> None:
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.track = value

    @property
    def program(self) -> str | None:
        return self.education_path.program if self.education_path else None

    @program.setter
    def program(self, value: str | None) -> None:
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.program = value

    @property
    def record_book_number(self) -> str | None:
        return self.education_path.record_book_number if self.education_path else None

    @record_book_number.setter
    def record_book_number(self, value: str | None) -> None:
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.record_book_number = value

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
