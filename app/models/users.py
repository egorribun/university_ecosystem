import uuid
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    pass


class User(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "users"
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    __table_args__ = (Index("ix_users_email_lower", func.lower(email), unique=True),)

    full_name = Column(String)
    role = Column(
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
    is_active = Column(Boolean, default=True, index=True)
    mfa_required = Column(Boolean, default=False, nullable=False, index=True)
    mfa_default_method = Column(String(64))
    mfa_last_verified_at = Column(DateTime(timezone=True), nullable=True, index=True)
    webauthn_id = Column(String(128), unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    avatar_url = Column(String)
    cover_url = Column(String)

    preferences = relationship(
        "UserPreferences",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    profile_detail = relationship(
        "UserProfileDetail",
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
        lazy="noload",
    )
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
        profile_data = kwargs.pop("profile_detail", None)
        education_data = kwargs.pop("education_path", None)

        super().__init__(**kwargs)

        # Legacy field shim support
        for field in ["dnd_enabled", "dnd_start", "dnd_end", "timezone"]:
            if field in kwargs:
                setattr(self, field, kwargs[field])
        for field in [
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
                self.profile_detail = UserProfileDetail(**profile_data)
            else:
                self.profile_detail = profile_data

        if education_data is not None:
            if isinstance(education_data, dict):
                self.education_path = EducationPath(**education_data)
            else:
                self.education_path = education_data

    @property
    def spotify_connected(self) -> bool:
        return bool(self.spotify and self.spotify.is_connected)

    # Legacy field shims for backward compatibility with existing tests
    @property
    def dnd_enabled(self):
        return self.preferences.dnd_enabled if self.preferences else False

    @dnd_enabled.setter
    def dnd_enabled(self, value):
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.dnd_enabled = value

    @property
    def dnd_start(self):
        return self.preferences.dnd_start if self.preferences else None

    @dnd_start.setter
    def dnd_start(self, value):
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.dnd_start = value

    @property
    def dnd_end(self):
        return self.preferences.dnd_end if self.preferences else None

    @dnd_end.setter
    def dnd_end(self, value):
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.dnd_end = value

    @property
    def timezone(self):
        return self.preferences.timezone if self.preferences else None

    @timezone.setter
    def timezone(self, value):
        if not self.preferences:
            self.preferences = UserPreferences()
        self.preferences.timezone = value

    @property
    def about(self):
        return self.profile_detail.about if self.profile_detail else None

    @about.setter
    def about(self, value):
        if not self.profile_detail:
            self.profile_detail = UserProfileDetail()
        self.profile_detail.about = value

    @property
    def telegram(self):
        return self.profile_detail.telegram if self.profile_detail else None

    @telegram.setter
    def telegram(self, value):
        if not self.profile_detail:
            self.profile_detail = UserProfileDetail()
        self.profile_detail.telegram = value

    @property
    def status(self):
        return self.profile_detail.status if self.profile_detail else None

    @status.setter
    def status(self, value):
        if not self.profile_detail:
            self.profile_detail = UserProfileDetail()
        self.profile_detail.status = value

    @property
    def achievements(self):
        return self.profile_detail.achievements if self.profile_detail else None

    @achievements.setter
    def achievements(self, value):
        if not self.profile_detail:
            self.profile_detail = UserProfileDetail()
        self.profile_detail.achievements = value

    @property
    def position(self):
        return self.profile_detail.position if self.profile_detail else None

    @position.setter
    def position(self, value):
        if not self.profile_detail:
            self.profile_detail = UserProfileDetail()
        self.profile_detail.position = value

    @property
    def department(self):
        return self.profile_detail.department if self.profile_detail else None

    @department.setter
    def department(self, value):
        if not self.profile_detail:
            self.profile_detail = UserProfileDetail()
        self.profile_detail.department = value

    @property
    def institute(self):
        return self.education_path.institute if self.education_path else None

    @institute.setter
    def institute(self, value):
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.institute = value

    @property
    def course(self):
        return self.education_path.course if self.education_path else None

    @course.setter
    def course(self, value):
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.course = value

    @property
    def education_level(self):
        return self.education_path.education_level if self.education_path else None

    @education_level.setter
    def education_level(self, value):
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.education_level = value

    @property
    def track(self):
        return self.education_path.track if self.education_path else None

    @track.setter
    def track(self, value):
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.track = value

    @property
    def program(self):
        return self.education_path.program if self.education_path else None

    @program.setter
    def program(self, value):
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.program = value

    @property
    def record_book_number(self):
        return self.education_path.record_book_number if self.education_path else None

    @record_book_number.setter
    def record_book_number(self, value):
        if not self.education_path:
            self.education_path = EducationPath()
        self.education_path.record_book_number = value

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


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


class UserProfileDetail(Base):
    __tablename__ = "user_profile_details"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    about = Column(String)
    telegram = Column(String)
    status = Column(String)
    achievements = Column(String)
    position = Column(String)
    department = Column(String)

    user = relationship("User", back_populates="profile_detail")

    def __repr__(self) -> str:
        return f"<UserProfileDetail(user_id={self.user_id})>"


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
