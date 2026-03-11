import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
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

    jti: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    signing_key: Mapped[str] = mapped_column(
        String, nullable=False, default=_generate_session_signing_key
    )
    mfa_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    mfa_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    mfa_method: Mapped[str | None] = mapped_column(String(64))
    mfa_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Session fingerprint for security binding
    accept_language: Mapped[str | None] = mapped_column(String(256))
    fingerprint_hash: Mapped[str | None] = mapped_column(
        String(64), index=True
    )  # SHA-256 hex digest

    user = relationship("User", back_populates="sessions")
    challenges = relationship(
        "MfaChallenge",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MfaTotpEnrollment(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "mfa_totp_enrollments"

    secret: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
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
    challenge_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )

    user = relationship("User", back_populates="mfa_challenges")
    session = relationship("ActiveSession", back_populates="challenges")

    __table_args__ = (
        Index("ix_mfa_challenges_user_expires", "user_id", "expires_at"),
        Index("ix_mfa_challenges_consumed_expires", "consumed_at", "expires_at"),
    )


class FailedLoginAttempt(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "failed_login_attempts"

    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # TD-3 (audit 2026-02-26): Added ip_address and user_agent for distributed
    # brute-force analysis. Without ip_address it was impossible to detect an
    # attacker rotating through multiple email addresses from one IP.
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True, index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
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
        # Allow brute-force detection by IP across multiple target emails.
        Index(
            "ix_failed_login_attempts_ip_attempted_at",
            "ip_address",
            "attempted_at",
        ),
    )


class PasswordResetToken(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user = relationship("User")

    @staticmethod
    def issue_token() -> str:
        return secrets.token_urlsafe(32)


class EmailChangeToken(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "email_change_tokens"

    new_email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user = relationship("User", back_populates="email_change_tokens")

    @property
    def is_active(self) -> bool:
        return bool(
            not self.used
            and (self.expires_at is None or self.expires_at > datetime.now(UTC))
        )


class TrustedDevice(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "trusted_devices"

    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="trusted_devices")


class WebAuthnCredential(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "webauthn_credentials"

    credential_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    # OZ-1 (audit 2026-02-26): Bound public_key to String(4096). Without a limit
    # an attacker could write multi-MB values during registration, causing OOM on
    # bulk credential list queries. COSE EC key ≈ 512 B base64, RSA-4096 ≈ 736 B base64.
    public_key: Mapped[str] = mapped_column(String(4096), nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transports: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True
    )  # List of allowed transports
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    backing_up: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_state: Mapped[bool] = mapped_column(Boolean, default=False)

    user = relationship("User", back_populates="webauthn_credentials")

    def __init__(self, **kwargs: Any) -> None:
        # TD-06: Prevent mass-assignment of immutable/system-controlled fields
        # RZ-01: Allow bypass for testing fixtures.
        allow_manual = kwargs.pop("_allow_system_managed_assignment", False)
        forbidden = {"id", "created_at"}
        if not allow_manual and (intersections := forbidden.intersection(kwargs.keys())):
            raise ValueError(
                f"Cannot manually assign system-controlled fields: {intersections}"
            )
        super().__init__(**kwargs)


class RecoveryCode(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "recovery_codes"

    code_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Argon2 hash of the code
    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("User", back_populates="recovery_codes")


class LoginHistory(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "login_history"

    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    city: Mapped[str | None] = mapped_column(String(128))
    # TD-2 (audit 2026-02-26): Changed from String(20) to Numeric(9,6) to enable
    # PostGIS spatial queries and correct numeric comparisons.
    # Numeric(9,6) supports ±179.999999° without floating-point imprecision.
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success, failed, locked
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="login_history")
