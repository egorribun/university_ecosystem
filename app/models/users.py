from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    func,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    pass


def _create_spotify_integration(value):
    from app.models.spotify import SpotifyIntegration

    return SpotifyIntegration(is_connected=value)


def _create_spotify_display_name(value):
    from app.models.spotify import SpotifyIntegration

    return SpotifyIntegration(display_name=value)


ROLE_VALUES_SQL = ", ".join(f"'{role.value}'" for role in UserRole)


class User(Base, EventEmitterMixin):
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
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), index=True)
    is_active = Column(Boolean, default=True, index=True)
    mfa_required = Column(Boolean, default=False, nullable=False, index=True)
    mfa_default_method = Column(String(64))
    mfa_last_verified_at = Column(DateTime(timezone=True), nullable=True, index=True)
    webauthn_id = Column(String(128), unique=True, index=True, nullable=True)

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

    preferences = relationship(
        "UserPreferences",
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

    spotify_is_connected = association_proxy(
        "spotify",
        "is_connected",
        creator=_create_spotify_integration,
    )
    spotify_display_name = association_proxy(
        "spotify",
        "display_name",
        creator=_create_spotify_display_name,
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
        spotify_fields = {"spotify_is_connected", "spotify_display_name"}

        preferences_data = {
            key: kwargs.pop(key) for key in list(kwargs) if key in preferences_fields
        }
        spotify_data = {
            key: kwargs.pop(key) for key in list(kwargs) if key in spotify_fields
        }

        super().__init__(**kwargs)

        if preferences_data:
            self.preferences = UserPreferences(**preferences_data)
        if spotify_data:
            from app.models.spotify import SpotifyIntegration

            self.spotify = SpotifyIntegration(
                is_connected=spotify_data.get("spotify_is_connected"),
                display_name=spotify_data.get("spotify_display_name"),
            )

    @property
    def spotify_connected(self) -> bool:
        return bool(self.spotify and self.spotify.is_connected)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id = Column(
        Integer,
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

    def __repr__(self) -> str:
        return f"<InviteCode(id={self.id}, code='{self.code}', used={self.is_used})>"
