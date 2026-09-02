import secrets
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    UUID,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)

# Removed postgresql UUID import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UserFK, UUID7PrimaryKeyMixin
from app.utils.encryption import EncryptedString


class ChallengeState(StrEnum):
    """TD-W5-01: Explicit state machine for MFA challenges.

    Replaces the implicit dual-null convention (consumed_at=None, locked_at=None →
    active; consumed_at set → done; locked_at set → locked) with a single
    auditable column that is impossible to misread.
    """

    PENDING = "pending"
    CONSUMED = "consumed"
    LOCKED = "locked"
    EXPIRED = "expired"


def _generate_session_signing_key() -> str:
    return secrets.token_urlsafe(32)


class ActiveSession(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "active_sessions"
    __table_args__ = (
        Index("ix_active_sessions_user_id_expires_at", "user_id", "expires_at"),
    )

    # DEBT-01 (RZ-W13): JTI is a UUID4 string — 36 chars. Explicit bound prevents
    # index bloat and storage-amplification via crafted JTI values.
    jti: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )
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
    # TD-14-01 (audit 2026-03-23): Bounded to String(128). token_urlsafe(32)
    # produces 43 chars; 128 chars gives 3× headroom for future key-format
    # changes without a new migration.  Prevents storage-amplification if the
    # generator is ever swapped for a longer output.  Paired migration:
    # 202603230001_wave14_email_length_constraints.py.
    signing_key: Mapped[str] = mapped_column(
        String(128), nullable=False, default=_generate_session_signing_key
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
    mfa_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Session fingerprint for security binding
    accept_language: Mapped[str | None] = mapped_column(String(256))
    fingerprint_hash: Mapped[str | None] = mapped_column(
        String(64), index=True
    )  # SHA-256 hex digest

    # TD-20-05 (audit 2026-03-24): Explicit noload on all back-references.
    user = relationship("User", back_populates="sessions", lazy="noload")
    challenges = relationship(
        "MfaChallenge",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
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
    # MOD-W8-06: Belt-and-suspenders replay prevention.
    # SHA-256 hex digest (64 chars) of the last successfully verified TOTP code;
    # combined with last_used_at it lets verify_totp_for_user reject a replayed
    # code even in edge cases where the challenge was already consumed.
    last_used_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Monotonic RFC 6238 counter accepted for this enrollment.  Unlike a digest
    # of the submitted digits, this also rejects an older skew-window code after
    # a newer counter has already succeeded.
    last_used_timecode: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user = relationship("User", back_populates="totp_enrollments", lazy="noload")

    __table_args__ = (Index("ix_mfa_totp_enrollments_active", "user_id", "is_active"),)


class MfaChallenge(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "mfa_challenges"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("active_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    challenge_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    flow: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    session_identifier: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    client_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    trust_device_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    token_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    token_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    resend_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # TD-W5-01: Explicit state machine column — single source of truth.
    state: Mapped[ChallengeState] = mapped_column(
        SAEnum(
            ChallengeState,
            name="challenge_state_enum",
            values_callable=lambda x: [m.value for m in x],
        ),
        nullable=False,
        server_default="pending",
        default=ChallengeState.PENDING,
    )

    user = relationship("User", back_populates="mfa_challenges", lazy="noload")
    session = relationship("ActiveSession", back_populates="challenges", lazy="noload")

    __table_args__ = (
        CheckConstraint(
            "method != 'email_otp' OR recipient_digest IS NOT NULL",
            name="ck_mfa_challenges_email_recipient_digest",
        ),
        Index("ix_mfa_challenges_user_expires", "user_id", "expires_at"),
        Index("ix_mfa_challenges_consumed_expires", "consumed_at", "expires_at"),
        Index("ix_mfa_challenges_state", "state"),
        Index(
            "ix_mfa_challenges_binding",
            "user_id",
            "flow",
            "session_identifier",
            "method",
        ),
    )


class FailedLoginAttempt(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "failed_login_attempts"

    # W136 SW4: override UserFK's user_id to make it nullable + use SET NULL
    # on user delete. Closes W135 §Honesty #3.
    #
    # Failed login attempts MUST INSERT successfully even when the email maps
    # to no existing user (credential-stuffing attempts on harvested email
    # lists, typo'd emails, account-deletion races). Pre-W136 the inherited
    # UserFK declared user_id nullable=False with ondelete=CASCADE, so the
    # /login flow's call to register_failed_attempt(email, user_id=None)
    # raised NotNullViolation for unknown emails — surfaced in W135 SW2
    # Docker chain verification.
    #
    # Original migration 2025070100011_add_failed_login_attempts_table.py
    # created user_id as nullable=True with ondelete=SET NULL. The post-UUID
    # reconcile migration 202603280001 inadvertently inherited the model-side
    # NOT NULL through UserFK. Wave 136 SW4 restores nullability via override
    # + new alembic migration alter_failed_login_attempts_user_id_nullable.
    # W142 polish-v3: mypy[assignment] override — UserFK mixin's user_id is
    # Mapped[uuid.UUID] (non-nullable), but failed_login_attempts INTENTIONALLY
    # overrides with `Mapped[uuid.UUID | None]` per W136 SW4 (failed login
    # attempts must INSERT even when email maps to no user — credential-
    # stuffing on harvested email lists). Existing W136 SW4 commit landed
    # without this annotation; W142 CI surfaced the lint after pre-commit
    # fix (commit 41b23506f) unlocked downstream type-check.
    user_id: Mapped[uuid.UUID | None] = mapped_column(  # type: ignore[assignment]
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
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

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)

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
        String(255),
        unique=True,
        index=True,
        nullable=False,  # LOW-W19: bounded String
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

    user = relationship("User", lazy="noload")

    @staticmethod
    def issue_token() -> str:
        return secrets.token_urlsafe(32)


class EmailChangeToken(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "email_change_tokens"

    new_email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,  # LOW-W19: bounded String
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

    user = relationship("User", back_populates="email_change_tokens", lazy="noload")

    @property
    def is_active(self) -> bool:
        # RZ-W19-02: expires_at is non-nullable (Mapped[datetime]), so this branch
        # is unreachable at the type-checker level. The runtime guard is kept as a
        # belt-and-suspenders safety check for stale data or future schema changes.
        if self.expires_at is None:
            return False  # type: ignore[unreachable]
        return bool(not self.used and self.expires_at > datetime.now(UTC))


class TrustedDevice(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "trusted_devices"

    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    token_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # P1-W5-07: SHA-256 hex digests used for constant-time binding check.
    # Raw ip_address/user_agent kept for audit/display; hashes used for comparison.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ua_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="trusted_devices", lazy="noload")


class MfaEmailDelivery(Base, UUID7PrimaryKeyMixin):
    """Encrypted, PII-free-at-rest envelope for transactional MFA email."""

    __tablename__ = "mfa_email_deliveries"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mfa_challenges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(2), nullable=False)
    kek_id: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(12), nullable=True)
    envelope_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    wrap_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(12), nullable=True)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shredded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    challenge = relationship("MfaChallenge", lazy="noload")

    __table_args__ = (
        UniqueConstraint(
            "challenge_id",
            "revision",
            name="uq_mfa_email_delivery_challenge_revision",
        ),
        CheckConstraint("locale IN ('en','ru')", name="ck_mfa_email_delivery_locale"),
        CheckConstraint(
            "status IN ('pending','sending','sent','cancelled')",
            name="ck_mfa_email_delivery_status",
        ),
        CheckConstraint(
            "(status IN ('pending','sending') AND envelope_nonce IS NOT NULL "
            "AND envelope_ciphertext IS NOT NULL AND wrap_nonce IS NOT NULL "
            "AND wrapped_dek IS NOT NULL AND shredded_at IS NULL) OR "
            "(status IN ('sent','cancelled') AND envelope_nonce IS NULL "
            "AND envelope_ciphertext IS NULL AND wrap_nonce IS NULL "
            "AND wrapped_dek IS NULL AND shredded_at IS NOT NULL)",
            name="ck_mfa_email_delivery_envelope_lifecycle",
        ),
        Index(
            "ix_mfa_email_deliveries_pending_created",
            "created_at",
            "id",
            postgresql_where=(status == "pending"),
        ),
    )


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

    user = relationship("User", back_populates="recovery_codes", lazy="noload")


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

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)

    user = relationship("User", back_populates="login_history", lazy="noload")
