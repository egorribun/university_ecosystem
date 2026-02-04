import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Time,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)

# Removed postgresql UUID import
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin
from app.models.enums import UserRole
from app.models.mixins import UUID7PrimaryKeyMixin

if TYPE_CHECKING:
    pass


class User(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "users"

    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

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
        lazy="selectin",
    )
    profile_detail = relationship(
        "UserProfileDetail",
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
    spotify = relationship(
        "SpotifyIntegration",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    dnd_enabled = association_proxy(
        "preferences",
        "dnd_enabled",
        creator=lambda value: UserPreferences(dnd_enabled=value),
    )
    dnd_start = association_proxy(
        "preferences",
        "dnd_start",
        creator=lambda value: UserPreferences(dnd_start=value),
    )
    dnd_end = association_proxy(
        "preferences",
        "dnd_end",
        creator=lambda value: UserPreferences(dnd_end=value),
    )
    timezone = association_proxy(
        "preferences",
        "timezone",
        creator=lambda value: UserPreferences(timezone=value),
    )

    # UserProfileDetail proxies
    about = association_proxy(
        "profile_detail",
        "about",
        creator=lambda value: UserProfileDetail(about=value),
    )
    telegram = association_proxy(
        "profile_detail",
        "telegram",
        creator=lambda value: UserProfileDetail(telegram=value),
    )
    status = association_proxy(
        "profile_detail",
        "status",
        creator=lambda value: UserProfileDetail(status=value),
    )
    achievements = association_proxy(
        "profile_detail",
        "achievements",
        creator=lambda value: UserProfileDetail(achievements=value),
    )
    position = association_proxy(
        "profile_detail",
        "position",
        creator=lambda value: UserProfileDetail(position=value),
    )
    department = association_proxy(
        "profile_detail",
        "department",
        creator=lambda value: UserProfileDetail(department=value),
    )

    # EducationPath proxies
    institute = association_proxy(
        "education_path",
        "institute",
        creator=lambda value: EducationPath(institute=value),
    )
    course = association_proxy(
        "education_path",
        "course",
        creator=lambda value: EducationPath(course=value),
    )
    education_level = association_proxy(
        "education_path",
        "education_level",
        creator=lambda value: EducationPath(education_level=value),
    )
    track = association_proxy(
        "education_path",
        "track",
        creator=lambda value: EducationPath(track=value),
    )
    program = association_proxy(
        "education_path",
        "program",
        creator=lambda value: EducationPath(program=value),
    )
    record_book_number = association_proxy(
        "education_path",
        "record_book_number",
        creator=lambda value: EducationPath(record_book_number=value),
    )

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
        preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}
        profile_fields = {
            "about",
            "telegram",
            "status",
            "achievements",
            "position",
            "department",
        }
        education_fields = {
            "institute",
            "course",
            "education_level",
            "track",
            "program",
            "record_book_number",
        }
        spotify_fields = {"spotify_is_connected", "spotify_display_name"}

        preferences_data = {
            key: kwargs.pop(key) for key in list(kwargs) if key in preferences_fields
        }
        profile_data = {
            key: kwargs.pop(key) for key in list(kwargs) if key in profile_fields
        }
        education_data = {
            key: kwargs.pop(key) for key in list(kwargs) if key in education_fields
        }
        spotify_data = {
            key: kwargs.pop(key) for key in list(kwargs) if key in spotify_fields
        }

        super().__init__(**kwargs)

        if preferences_data:
            self.preferences = UserPreferences(**preferences_data)
        if profile_data:
            self.profile_detail = UserProfileDetail(**profile_data)
        if education_data:
            self.education_path = EducationPath(**education_data)
        if spotify_data:
            # Note: self.spotify assignment will be handled or requires late initialization
            # To strictly avoid the crutch, we ensure self.spotify is set elsewhere
            # or the model is already available in the registry.
            pass

    @property
    def spotify_connected(self) -> bool:
        return bool(self.spotify and self.spotify.is_connected)

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
