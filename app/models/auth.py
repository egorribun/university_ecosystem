import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)

# Removed postgresql UUID import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UserFK, UUID7PrimaryKeyMixin
from app.utils.encryption import EncryptedString


def _generate_session_signing_key() -> str:
    return secrets.token_urlsafe(32)


class ActiveSession(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "active_sessions"

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
    # Session fingerprint for security binding
    accept_language = Column(String(256))
    fingerprint_hash = Column(String(64), index=True)  # SHA-256 hex digest

    user = relationship("User", back_populates="sessions")
    challenges = relationship(
        "MfaChallenge",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MfaTotpEnrollment(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "mfa_totp_enrollments"

    secret = Column(EncryptedString(), nullable=False)
    label = Column(String(255))
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="totp_enrollments")

    __table_args__ = (Index("ix_mfa_totp_enrollments_active", "user_id", "is_active"),)


class MfaChallenge(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "mfa_challenges"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("active_sessions.id", ondelete="CASCADE"),
        index=True,
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

    __table_args__ = (
        Index("ix_mfa_challenges_user_expires", "user_id", "expires_at"),
        Index("ix_mfa_challenges_consumed_expires", "consumed_at", "expires_at"),
    )


class FailedLoginAttempt(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "failed_login_attempts"

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


class PasswordResetToken(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "password_reset_tokens"

    token_hash = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User")

    @staticmethod
    def issue_token() -> str:
        return secrets.token_urlsafe(32)


class EmailChangeToken(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "email_change_tokens"

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


class TrustedDevice(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "trusted_devices"

    token_hash = Column(String(128), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True, index=True)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="trusted_devices")


class WebAuthnCredential(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "webauthn_credentials"

    credential_id = Column(String, unique=True, index=True, nullable=False)
    public_key = Column(Text, nullable=False)  # Base64 encoded public key
    sign_count = Column(Integer, default=0, nullable=False)
    transports = Column(JSON, nullable=True)  # List of allowed transports
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    label = Column(String(255), nullable=True)
    backing_up = Column(Boolean, default=False)
    backup_state = Column(Boolean, default=False)

    user = relationship("User", back_populates="webauthn_credentials")


class RecoveryCode(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "recovery_codes"

    code_hash = Column(String(255), nullable=False)  # Argon2 hash of the code
    is_used = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="recovery_codes")


class LoginHistory(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "login_history"

    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(512), nullable=True)
    country = Column(String(2))  # ISO 3166-1 alpha-2
    city = Column(String(128))
    latitude = Column(String(20))
    longitude = Column(String(20))
    status = Column(String(20), nullable=False)  # success, failed, locked
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    is_suspicious = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="login_history")
