"""Transactional, bound email OTP challenges and encrypted delivery envelopes."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
import secrets
import smtplib
import ssl
import string
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import TYPE_CHECKING, Protocol

import orjson
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, or_, select, update

from app.auth.constants import CHALLENGE_TYPE_EMAIL_OTP, MFA_METHOD_EMAIL_OTP
from app.core.logging import get_logger
from app.core.ratelimit import RateLimitExceeded
from app.models import (
    ChallengeState,
    MfaChallenge,
    MfaEmailDelivery,
    StoredEvent,
    TrustedDevice,
    User,
)
from app.utils.uuid_v7 import generate_uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
_PENDING_DIGEST = "0" * 64

OTP_DIGITS = 6
OTP_TTL_SECONDS = 600
OTP_MAX_FAILED_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
_TEMPLATE = "mfa_email_otp"
_ALLOWED_FLOWS = frozenset(
    {"login", "step_up", "email_verification", "email_mfa_enablement"}
)
_ALLOWED_LOCALES = frozenset({"en", "ru"})


class MfaOtpRejected(ValueError):
    """Enumeration-safe rejection for invalid, expired, or replayed challenges."""

    def __init__(self) -> None:
        super().__init__("MFA verification failed")


class MfaNotEmailChallenge(MfaOtpRejected):
    """Internal routing signal; public callers still receive a generic rejection."""


class MfaOtpCooldown(MfaOtpRejected):
    """A resend was attempted before the bound cooldown elapsed."""


class MfaSecurityUnavailable(RuntimeError):
    """A required security dependency failed and the operation failed closed."""

    def __init__(self) -> None:
        super().__init__("MFA service unavailable")


class MfaDeliveryError(RuntimeError):
    """PII-free terminal error returned by the delivery boundary."""

    def __init__(self) -> None:
        super().__init__("MFA delivery failed")


class MfaRateLimiter(Protocol):
    async def enforce(self, *, action: str, identifier: str) -> None: ...


class MfaEmailSender(Protocol):
    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        plain: str,
        html: str,
        message_id: str,
    ) -> None: ...


class _DeliveryOnlyRateLimiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        raise MfaSecurityUnavailable()


class RuntimeMfaRateLimiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        from app.core.ratelimit import enforce_rate_limit, get_default_strategy

        await enforce_rate_limit(
            identifier=f"mfa-email:{action}:{identifier}",
            limit=OTP_MAX_FAILED_ATTEMPTS,
            window_seconds=OTP_TTL_SECONDS,
            strategy=get_default_strategy("mfa"),
        )


class SmtpMfaEmailSender:
    """Narrow SMTP boundary that never logs recipient or message content."""

    @staticmethod
    def _send_sync(
        *, to_email: str, subject: str, plain: str, html_body: str, message_id: str
    ) -> None:
        from app.core.config import settings

        host = settings.smtp_host or ""
        port = int(settings.smtp_port or 0)
        if not host or not port:
            raise OSError("SMTP unavailable")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.mail_from or "no-reply@example.com"
        message["To"] = to_email
        message["Message-ID"] = message_id
        message.set_content(plain)
        message.add_alternative(html_body, subtype="html")
        configured_security = settings.smtp_security
        if configured_security:
            security = configured_security.lower()
        elif settings.smtp_starttls:
            # Keep the legacy boolean fallback canonical so a configured
            # ``smtp_security`` value can remain case-insensitive without
            # making this security-sensitive branch depend on string casing.
            security = "starttls"
        else:
            security = "none"
        if security not in {"none", "starttls", "ssl"}:
            # Do not silently downgrade a malformed setting to unauthenticated
            # SMTP.  Configuration normally validates this value, but this
            # boundary also runs in workers and must fail closed when settings
            # are injected or loaded from an unexpected source.
            raise OSError("SMTP unavailable")
        context = ssl.create_default_context()
        try:
            client_context: smtplib.SMTP
            if security == "ssl":
                client_context = smtplib.SMTP_SSL(
                    host, port, context=context, timeout=10
                )
            else:
                client_context = smtplib.SMTP(host, port, timeout=10)
            with client_context as client:
                if security == "starttls":
                    client.ehlo()
                    client.starttls(context=context)
                    client.ehlo()
                if settings.smtp_user:
                    client.login(settings.smtp_user, settings.smtp_password or "")
                client.send_message(message)
        except smtplib.SMTPException as exc:
            raise OSError("SMTP unavailable") from exc

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        plain: str,
        html: str,
        message_id: str,
    ) -> None:
        import asyncio

        await asyncio.to_thread(
            self._send_sync,
            to_email=to_email,
            subject=subject,
            plain=plain,
            html_body=html,
            message_id=message_id,
        )


@dataclass(frozen=True, slots=True)
class IssuedEmailOtp:
    """Internal-only handoff; API schemas deliberately never expose ``otp``."""

    challenge_id: uuid.UUID
    challenge_token: str
    otp: str
    revision: int
    expires_at: datetime
    resend_available_at: datetime
    delivery_hint: str


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def mask_email(email: str) -> str:
    """Return a stable, non-enumerating hint without exposing the recipient."""
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    suffix = domain[domain.rfind(".") :] if "." in domain else ""
    return f"{local[:1]}***@{domain[:1]}***{suffix}"


def _generate_otp() -> str:
    return f"{secrets.randbelow(10**OTP_DIGITS):0{OTP_DIGITS}d}"


def _generate_challenge_token(challenge_id: uuid.UUID) -> str:
    return f"{_b64encode(challenge_id.bytes)}.{secrets.token_urlsafe(32)}"


def _parse_challenge_id(token: str) -> uuid.UUID:
    try:
        encoded_id, secret = token.split(".", 1)
        if len(secret) < 32:
            raise ValueError
        return uuid.UUID(bytes=_b64decode(encoded_id))
    except (ValueError, TypeError):
        raise MfaOtpRejected() from None


def _digest_message(
    *,
    purpose: str,
    user_id: uuid.UUID,
    challenge_id: uuid.UUID,
    flow: str,
    session_identifier: str,
    client_fingerprint: str,
    method: str,
    revision: int,
    secret_value: str,
) -> bytes:
    fields = (
        "mfa-v1",
        purpose,
        str(user_id),
        str(challenge_id),
        flow,
        session_identifier,
        client_fingerprint,
        method,
        str(revision),
        secret_value,
    )
    return "\x1f".join(fields).encode("utf-8")


class EmailOtpService:
    """Owns challenge state, envelope crypto, and atomic OTP transitions."""

    def __init__(
        self,
        *,
        hmac_keys: dict[str, bytes],
        active_hmac_key_id: str,
        delivery_keks: dict[str, bytes],
        active_kek_id: str,
        rate_limiter: MfaRateLimiter,
        delivery_only: bool = False,
    ) -> None:
        if not delivery_keks or active_kek_id not in delivery_keks:
            raise MfaSecurityUnavailable()
        if not delivery_only and active_hmac_key_id not in hmac_keys:
            raise MfaSecurityUnavailable()
        if not delivery_only and any(len(value) < 32 for value in hmac_keys.values()):
            raise MfaSecurityUnavailable()
        if any(len(value) not in {16, 24, 32} for value in delivery_keks.values()):
            raise MfaSecurityUnavailable()
        self._hmac_keys = dict(hmac_keys)
        self._active_hmac_key_id = active_hmac_key_id
        self._delivery_keks = dict(delivery_keks)
        self._active_kek_id = active_kek_id
        self._rate_limiter = rate_limiter

    async def _rate_limit(
        self, *, action: str, user_id: uuid.UUID, client_ip: str
    ) -> None:
        try:
            await self._rate_limiter.enforce(
                action=action, identifier=f"user:{user_id}"
            )
            await self._rate_limiter.enforce(
                action=action, identifier=f"ip:{client_ip}"
            )
        except RateLimitExceeded:
            raise
        except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth dependency
            raise MfaSecurityUnavailable() from exc

    def _digest(
        self,
        *,
        key_id: str,
        purpose: str,
        challenge: MfaChallenge,
        secret_value: str,
        revision: int | None = None,
    ) -> str:
        key = self._hmac_keys.get(key_id)
        if key is None:
            raise MfaSecurityUnavailable()
        return hmac.new(
            key,
            _digest_message(
                purpose=purpose,
                user_id=challenge.user_id,
                challenge_id=challenge.id,
                flow=challenge.flow,
                session_identifier=challenge.session_identifier,
                client_fingerprint=challenge.client_fingerprint,
                method=challenge.method,
                revision=challenge.revision if revision is None else revision,
                secret_value=secret_value,
            ),
            hashlib.sha256,
        ).hexdigest()

    def _recipient_digest(self, *, key_id: str, email: str) -> str:
        key = self._hmac_keys.get(key_id)
        if key is None:
            raise MfaSecurityUnavailable()
        return hmac.new(
            key,
            b"mfa-recipient-v1\x1f" + email.strip().casefold().encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _validate_binding(
        challenge: MfaChallenge,
        *,
        user_id: uuid.UUID,
        flow: str,
        session_identifier: str,
        client_fingerprint: str,
    ) -> None:
        if (
            challenge.user_id != user_id
            or challenge.flow != flow
            or challenge.method != MFA_METHOD_EMAIL_OTP
            or not hmac.compare_digest(challenge.session_identifier, session_identifier)
            or not hmac.compare_digest(challenge.client_fingerprint, client_fingerprint)
        ):
            raise MfaOtpRejected()

    @staticmethod
    def _validate_issue_values(
        *, flow: str, session_identifier: str, client_fingerprint: str
    ) -> None:
        if flow not in _ALLOWED_FLOWS:
            raise ValueError("unsupported MFA flow")
        if not session_identifier or len(session_identifier) > 128:
            raise ValueError("invalid session identifier")
        if len(client_fingerprint) != 64:
            raise ValueError("invalid client fingerprint")

    def _build_delivery(
        self,
        *,
        challenge: MfaChallenge,
        revision: int,
        email: str,
        otp: str,
        locale: str,
        display_name: str,
        now: datetime,
    ) -> MfaEmailDelivery:
        resolved_locale = locale if locale in _ALLOWED_LOCALES else "en"
        delivery_id = generate_uuid7()
        aad = (
            f"mfa-delivery-v1\x1f{delivery_id}\x1f{challenge.id}\x1f"
            f"{revision}\x1f{_TEMPLATE}\x1f{resolved_locale}"
        ).encode()
        envelope = orjson.dumps(
            {
                "email": email,
                "otp": otp,
                "display_name": display_name,
            }
        )

        dek = AESGCM.generate_key(bit_length=256)
        envelope_nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(dek).encrypt(envelope_nonce, envelope, aad)
        wrap_nonce = secrets.token_bytes(12)
        kek = self._delivery_keks[self._active_kek_id]
        wrapped_dek = AESGCM(kek).encrypt(wrap_nonce, dek, aad)
        return MfaEmailDelivery(
            id=delivery_id,
            challenge_id=challenge.id,
            revision=revision,
            message_id=f"<mfa-{delivery_id}@university-ecosystem>",
            template=_TEMPLATE,
            locale=resolved_locale,
            kek_id=self._active_kek_id,
            envelope_nonce=envelope_nonce,
            envelope_ciphertext=ciphertext,
            wrap_nonce=wrap_nonce,
            wrapped_dek=wrapped_dek,
            status="pending",
            attempt_count=0,
            created_at=now,
        )

    @staticmethod
    async def _resolve_recipient(
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        flow: str,
        for_update: bool = False,
    ) -> tuple[User, str]:
        stmt = select(User).where(User.id == user_id)
        if for_update:
            stmt = stmt.with_for_update(nowait=False)
        user = (await db.execute(stmt)).scalar_one_or_none()
        if user is None or not user.is_active:
            raise MfaOtpRejected()
        if flow == "email_verification":
            # Pending-email promotion is owned by the one-time email-change
            # token transaction; this flow verifies only the persisted address.
            recipient = user.email
        elif flow == "email_mfa_enablement":
            if user.email_verified_at is None:
                raise MfaOtpRejected()
            recipient = user.email
        else:
            if user.email_mfa_enabled_at is None:
                raise MfaOtpRejected()
            recipient = user.email
        return user, recipient

    @staticmethod
    def _build_outbox(delivery: MfaEmailDelivery) -> StoredEvent:
        return StoredEvent(
            event_type="auth.mfa_email.requested",
            aggregate_type="MfaChallenge",
            aggregate_id=str(delivery.challenge_id),
            aggregate_id_uuid=delivery.challenge_id,
            subject="auth.mfa.email.requested",
            payload={
                "delivery_id": str(delivery.id),
                "template": delivery.template,
                "locale": delivery.locale,
                "revision": delivery.revision,
            },
            metadata_={},
        )

    async def issue(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        flow: str,
        session_identifier: str,
        client_fingerprint: str,
        client_ip: str,
        locale: str,
        display_name: str = "",
        trust_device: bool = False,
        now: datetime | None = None,
    ) -> IssuedEmailOtp:
        self._validate_issue_values(
            flow=flow,
            session_identifier=session_identifier,
            client_fingerprint=client_fingerprint,
        )
        await self._rate_limit(action="issue", user_id=user_id, client_ip=client_ip)
        _user, recipient = await self._resolve_recipient(
            db, user_id=user_id, flow=flow, for_update=True
        )
        issued_at = now or datetime.now(UTC)
        challenge_id = generate_uuid7()
        revision = 1
        token = _generate_challenge_token(challenge_id)
        otp = _generate_otp()
        expires_at = issued_at + timedelta(seconds=OTP_TTL_SECONDS)
        resend_available_at = issued_at + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS)
        challenge = MfaChallenge(
            id=challenge_id,
            user_id=user_id,
            session_id=None,
            challenge_type=CHALLENGE_TYPE_EMAIL_OTP,
            flow=flow,
            session_identifier=session_identifier,
            client_fingerprint=client_fingerprint,
            method=MFA_METHOD_EMAIL_OTP,
            revision=revision,
            trust_device_requested=trust_device,
            token_digest=_PENDING_DIGEST,
            token_key_id=self._active_hmac_key_id,
            recipient_digest=self._recipient_digest(
                key_id=self._active_hmac_key_id,
                email=recipient,
            ),
            otp_digest=_PENDING_DIGEST,
            otp_key_id=self._active_hmac_key_id,
            expires_at=expires_at,
            resend_available_at=resend_available_at,
            consumed_at=None,
            locked_at=None,
            created_at=issued_at,
            payload=None,
            attempt_count=0,
            state=ChallengeState.PENDING,
        )
        challenge.token_digest = self._digest(
            key_id=self._active_hmac_key_id,
            purpose="challenge-token",
            challenge=challenge,
            secret_value=token,
        )
        challenge.otp_digest = self._digest(
            key_id=self._active_hmac_key_id,
            purpose="email-otp",
            challenge=challenge,
            secret_value=otp,
        )
        delivery = self._build_delivery(
            challenge=challenge,
            revision=revision,
            email=recipient,
            otp=otp,
            locale=locale,
            display_name=display_name,
            now=issued_at,
        )
        db.add_all([challenge, delivery, self._build_outbox(delivery)])
        await db.flush()
        return IssuedEmailOtp(
            challenge_id=challenge.id,
            challenge_token=token,
            otp=otp,
            revision=revision,
            expires_at=expires_at,
            resend_available_at=resend_available_at,
            delivery_hint=mask_email(recipient),
        )

    async def _load_bound_challenge(
        self,
        db: AsyncSession,
        *,
        challenge_token: str,
        user_id: uuid.UUID,
        flow: str,
        session_identifier: str,
        client_fingerprint: str,
    ) -> MfaChallenge:
        challenge_id = _parse_challenge_id(challenge_token)
        challenge = (
            await db.execute(
                select(MfaChallenge)
                .where(MfaChallenge.id == challenge_id)
                .with_for_update(nowait=False)
            )
        ).scalar_one_or_none()
        if challenge is None:
            raise MfaOtpRejected()
        self._validate_binding(
            challenge,
            user_id=user_id,
            flow=flow,
            session_identifier=session_identifier,
            client_fingerprint=client_fingerprint,
        )
        expected_token = self._digest(
            key_id=challenge.token_key_id,
            purpose="challenge-token",
            challenge=challenge,
            secret_value=challenge_token,
        )
        if not hmac.compare_digest(expected_token, challenge.token_digest):
            raise MfaOtpRejected()
        return challenge

    async def _user_id_from_token(
        self, db: AsyncSession, challenge_token: str
    ) -> uuid.UUID:
        challenge_id = _parse_challenge_id(challenge_token)
        user_id = await db.scalar(
            select(MfaChallenge.user_id).where(MfaChallenge.id == challenge_id)
        )
        if user_id is None:
            raise MfaOtpRejected()
        return user_id

    async def verify_opaque(
        self,
        db: AsyncSession,
        *,
        challenge_token: str,
        code: str,
        client_fingerprint: str,
        client_ip: str,
        login_session_identifier: str | None = None,
        active_session_identifier: str | None = None,
        now: datetime | None = None,
    ) -> MfaChallenge:
        challenge = await self._load_opaque_challenge(
            db,
            challenge_token=challenge_token,
            client_fingerprint=client_fingerprint,
            login_session_identifier=login_session_identifier,
            active_session_identifier=active_session_identifier,
        )
        return await self.verify(
            db,
            challenge_token=challenge_token,
            code=code,
            user_id=challenge.user_id,
            flow=challenge.flow,
            session_identifier=challenge.session_identifier,
            client_fingerprint=client_fingerprint,
            client_ip=client_ip,
            now=now,
        )

    async def resend_opaque(
        self,
        db: AsyncSession,
        *,
        challenge_token: str,
        client_fingerprint: str,
        client_ip: str,
        locale: str,
        login_session_identifier: str | None = None,
        active_session_identifier: str | None = None,
        now: datetime | None = None,
    ) -> IssuedEmailOtp:
        challenge = await self._load_opaque_challenge(
            db,
            challenge_token=challenge_token,
            client_fingerprint=client_fingerprint,
            login_session_identifier=login_session_identifier,
            active_session_identifier=active_session_identifier,
        )
        return await self.resend(
            db,
            challenge_token=challenge_token,
            user_id=challenge.user_id,
            flow=challenge.flow,
            session_identifier=challenge.session_identifier,
            client_fingerprint=client_fingerprint,
            client_ip=client_ip,
            locale=locale,
            now=now,
        )

    async def _load_opaque_challenge(
        self,
        db: AsyncSession,
        *,
        challenge_token: str,
        client_fingerprint: str,
        login_session_identifier: str | None,
        active_session_identifier: str | None,
    ) -> MfaChallenge:
        challenge_id = _parse_challenge_id(challenge_token)
        challenge = (
            await db.execute(
                select(MfaChallenge).where(MfaChallenge.id == challenge_id)
            )
        ).scalar_one_or_none()
        if challenge is None or challenge.method != MFA_METHOD_EMAIL_OTP:
            raise MfaNotEmailChallenge()
        expected_token = self._digest(
            key_id=challenge.token_key_id,
            purpose="challenge-token",
            challenge=challenge,
            secret_value=challenge_token,
        )
        if not hmac.compare_digest(expected_token, challenge.token_digest):
            raise MfaOtpRejected()
        if not hmac.compare_digest(client_fingerprint, challenge.client_fingerprint):
            raise MfaOtpRejected()
        expected_session = (
            active_session_identifier
            if challenge.flow
            in {"step_up", "email_verification", "email_mfa_enablement"}
            else login_session_identifier
        )
        if expected_session is None or not hmac.compare_digest(
            expected_session, challenge.session_identifier
        ):
            raise MfaOtpRejected()
        return challenge

    async def consume_recovery_opaque(
        self,
        db: AsyncSession,
        *,
        challenge_token: str,
        code: str,
        client_fingerprint: str,
        client_ip: str,
        login_session_identifier: str | None,
        active_session_identifier: str | None,
        now: datetime | None = None,
    ) -> MfaChallenge:
        from app.auth.mfa.recovery import verify_recovery_code

        opaque = await self._load_opaque_challenge(
            db,
            challenge_token=challenge_token,
            client_fingerprint=client_fingerprint,
            login_session_identifier=login_session_identifier,
            active_session_identifier=active_session_identifier,
        )
        if opaque.flow not in {"login", "step_up"}:
            raise MfaOtpRejected()
        await self._rate_limit(
            action="verify", user_id=opaque.user_id, client_ip=client_ip
        )
        user, recipient = await self._resolve_recipient(
            db,
            user_id=opaque.user_id,
            flow=opaque.flow,
            for_update=True,
        )
        challenge = await self._load_bound_challenge(
            db,
            challenge_token=challenge_token,
            user_id=opaque.user_id,
            flow=opaque.flow,
            session_identifier=opaque.session_identifier,
            client_fingerprint=client_fingerprint,
        )
        expected_recipient = self._recipient_digest(
            key_id=challenge.token_key_id,
            email=recipient,
        )
        checked_at = now or datetime.now(UTC)
        if (
            challenge.recipient_digest is None
            or not hmac.compare_digest(expected_recipient, challenge.recipient_digest)
            or challenge.state != ChallengeState.PENDING
            or _aware(challenge.expires_at) <= checked_at
        ):
            raise MfaOtpRejected()
        if not await verify_recovery_code(db, user=user, code=code):
            challenge.attempt_count += 1
            if challenge.attempt_count >= OTP_MAX_FAILED_ATTEMPTS:
                challenge.state = ChallengeState.LOCKED
                challenge.locked_at = checked_at
            await db.flush()
            raise MfaOtpRejected()
        challenge.state = ChallengeState.CONSUMED
        challenge.consumed_at = checked_at
        await db.flush()
        return challenge

    async def verify(
        self,
        db: AsyncSession,
        *,
        challenge_token: str,
        code: str,
        user_id: uuid.UUID,
        flow: str,
        session_identifier: str,
        client_fingerprint: str,
        client_ip: str,
        now: datetime | None = None,
    ) -> MfaChallenge:
        await self._rate_limit(action="verify", user_id=user_id, client_ip=client_ip)
        checked_at = now or datetime.now(UTC)
        user, recipient = await self._resolve_recipient(
            db,
            user_id=user_id,
            flow=flow,
            for_update=True,
        )
        challenge = await self._load_bound_challenge(
            db,
            challenge_token=challenge_token,
            user_id=user_id,
            flow=flow,
            session_identifier=session_identifier,
            client_fingerprint=client_fingerprint,
        )
        expected_recipient = self._recipient_digest(
            key_id=challenge.token_key_id,
            email=recipient,
        )
        if challenge.recipient_digest is None or not hmac.compare_digest(
            expected_recipient, challenge.recipient_digest
        ):
            raise MfaOtpRejected()
        if (
            challenge.state != ChallengeState.PENDING
            or _aware(challenge.expires_at) <= checked_at
            or challenge.attempt_count >= OTP_MAX_FAILED_ATTEMPTS
            or challenge.otp_digest is None
            or challenge.otp_key_id is None
        ):
            raise MfaOtpRejected()
        expected_otp = self._digest(
            key_id=challenge.otp_key_id,
            purpose="email-otp",
            challenge=challenge,
            secret_value=code,
        )
        if not hmac.compare_digest(expected_otp, challenge.otp_digest):
            next_attempt = challenge.attempt_count + 1
            values: dict[str, object] = {"attempt_count": next_attempt}
            if next_attempt >= OTP_MAX_FAILED_ATTEMPTS:
                values.update(
                    state=ChallengeState.LOCKED,
                    locked_at=checked_at,
                )
            row = (
                await db.execute(
                    update(MfaChallenge)
                    .where(
                        MfaChallenge.id == challenge.id,
                        MfaChallenge.revision == challenge.revision,
                        MfaChallenge.state == ChallengeState.PENDING,
                    )
                    .values(**values)
                    .returning(MfaChallenge.id)
                )
            ).one_or_none()
            if row is not None:
                await db.flush()
            raise MfaOtpRejected()
        consumed = (
            await db.execute(
                update(MfaChallenge)
                .where(
                    MfaChallenge.id == challenge.id,
                    MfaChallenge.revision == challenge.revision,
                    MfaChallenge.state == ChallengeState.PENDING,
                    MfaChallenge.attempt_count < OTP_MAX_FAILED_ATTEMPTS,
                )
                .values(state=ChallengeState.CONSUMED, consumed_at=checked_at)
                .returning(MfaChallenge.id)
            )
        ).one_or_none()
        if consumed is None:
            raise MfaOtpRejected()
        if challenge.flow in {"email_verification", "email_mfa_enablement"}:
            if challenge.flow == "email_verification":
                user.email_verified_at = checked_at
            else:
                user.email_mfa_enabled_at = checked_at
                user.mfa_required = True
                user.mfa_epoch = int(user.mfa_epoch or 0) + 1
                await db.execute(
                    delete(TrustedDevice).where(TrustedDevice.user_id == user.id)
                )
                if user.mfa_default_method is None:
                    user.mfa_default_method = MFA_METHOD_EMAIL_OTP
        await db.flush()
        await db.refresh(challenge)
        return challenge

    async def resend(
        self,
        db: AsyncSession,
        *,
        challenge_token: str,
        user_id: uuid.UUID,
        flow: str,
        session_identifier: str,
        client_fingerprint: str,
        client_ip: str,
        locale: str,
        display_name: str = "",
        now: datetime | None = None,
    ) -> IssuedEmailOtp:
        await self._rate_limit(action="resend", user_id=user_id, client_ip=client_ip)
        _user, recipient = await self._resolve_recipient(
            db, user_id=user_id, flow=flow, for_update=True
        )
        rotated_at = now or datetime.now(UTC)
        challenge = await self._load_bound_challenge(
            db,
            challenge_token=challenge_token,
            user_id=user_id,
            flow=flow,
            session_identifier=session_identifier,
            client_fingerprint=client_fingerprint,
        )
        expected_recipient = self._recipient_digest(
            key_id=challenge.token_key_id,
            email=recipient,
        )
        if challenge.recipient_digest is None or not hmac.compare_digest(
            expected_recipient, challenge.recipient_digest
        ):
            raise MfaOtpRejected()
        if challenge.state != ChallengeState.PENDING:
            raise MfaOtpRejected()
        if (
            challenge.resend_available_at is not None
            and _aware(challenge.resend_available_at) > rotated_at
        ):
            raise MfaOtpCooldown()
        old_revision = challenge.revision
        revision = old_revision + 1
        token = _generate_challenge_token(challenge.id)
        otp = _generate_otp()
        expires_at = rotated_at + timedelta(seconds=OTP_TTL_SECONDS)
        resend_available_at = rotated_at + timedelta(
            seconds=OTP_RESEND_COOLDOWN_SECONDS
        )
        token_digest = self._digest(
            key_id=self._active_hmac_key_id,
            purpose="challenge-token",
            challenge=challenge,
            secret_value=token,
            revision=revision,
        )
        otp_digest = self._digest(
            key_id=self._active_hmac_key_id,
            purpose="email-otp",
            challenge=challenge,
            secret_value=otp,
            revision=revision,
        )
        recipient_digest = self._recipient_digest(
            key_id=self._active_hmac_key_id,
            email=recipient,
        )
        won = (
            await db.execute(
                update(MfaChallenge)
                .where(
                    MfaChallenge.id == challenge.id,
                    MfaChallenge.revision == old_revision,
                    MfaChallenge.state == ChallengeState.PENDING,
                )
                .values(
                    revision=revision,
                    token_digest=token_digest,
                    token_key_id=self._active_hmac_key_id,
                    recipient_digest=recipient_digest,
                    otp_digest=otp_digest,
                    otp_key_id=self._active_hmac_key_id,
                    expires_at=expires_at,
                    resend_available_at=resend_available_at,
                )
                .returning(MfaChallenge.id)
            )
        ).one_or_none()
        if won is None:
            raise MfaOtpRejected()
        await db.execute(
            update(MfaEmailDelivery)
            .where(
                MfaEmailDelivery.challenge_id == challenge.id,
                MfaEmailDelivery.status == "pending",
            )
            .values(
                status="cancelled",
                envelope_nonce=None,
                envelope_ciphertext=None,
                wrap_nonce=None,
                wrapped_dek=None,
                shredded_at=rotated_at,
            )
        )
        challenge.revision = revision
        challenge.token_digest = token_digest
        challenge.token_key_id = self._active_hmac_key_id
        challenge.recipient_digest = recipient_digest
        challenge.otp_digest = otp_digest
        challenge.otp_key_id = self._active_hmac_key_id
        delivery = self._build_delivery(
            challenge=challenge,
            revision=revision,
            email=recipient,
            otp=otp,
            locale=locale,
            display_name=display_name,
            now=rotated_at,
        )
        db.add_all([delivery, self._build_outbox(delivery)])
        await db.flush()
        return IssuedEmailOtp(
            challenge_id=challenge.id,
            challenge_token=token,
            otp=otp,
            revision=revision,
            expires_at=expires_at,
            resend_available_at=resend_available_at,
            delivery_hint=mask_email(recipient),
        )

    @staticmethod
    def _delivery_aad(delivery: MfaEmailDelivery) -> bytes:
        return (
            f"mfa-delivery-v1\x1f{delivery.id}\x1f{delivery.challenge_id}\x1f"
            f"{delivery.revision}\x1f{delivery.template}\x1f{delivery.locale}"
        ).encode()

    def _decrypt_delivery(self, delivery: MfaEmailDelivery) -> dict[str, str]:
        kek = self._delivery_keks.get(delivery.kek_id)
        if (
            kek is None
            or delivery.wrap_nonce is None
            or delivery.wrapped_dek is None
            or delivery.envelope_nonce is None
            or delivery.envelope_ciphertext is None
        ):
            raise MfaDeliveryError()
        aad = self._delivery_aad(delivery)
        try:
            dek = AESGCM(kek).decrypt(delivery.wrap_nonce, delivery.wrapped_dek, aad)
            raw = AESGCM(dek).decrypt(
                delivery.envelope_nonce, delivery.envelope_ciphertext, aad
            )
            value = orjson.loads(raw)
            if not isinstance(value, dict):
                raise TypeError
            email = value.get("email")
            otp = value.get("otp")
            display_name = value.get("display_name", "")
            if (
                not isinstance(email, str)
                or not isinstance(otp, str)
                or not isinstance(display_name, str)
            ):
                raise TypeError
            return {"email": email, "otp": otp, "display_name": display_name}
        except (InvalidTag, TypeError, orjson.JSONDecodeError) as exc:
            raise MfaDeliveryError() from exc

    @staticmethod
    def _render_email(
        *, otp: str, display_name: str, locale: str
    ) -> tuple[str, str, str]:
        if locale == "ru":
            subject = "Код подтверждения"
            greeting = (
                f"Здравствуйте, {display_name}!" if display_name else "Здравствуйте!"
            )
            plain = f"{greeting}\nКод подтверждения: {otp}\nКод действует 10 минут."
        else:
            subject = "Your verification code"
            greeting = f"Hello, {display_name}!" if display_name else "Hello!"
            plain = (
                f"{greeting}\nVerification code: {otp}\nThe code expires in 10 minutes."
            )
        body = html.escape(plain).replace("\n", "<br>")
        return subject, plain, f"<p>{body}</p>"

    async def deliver(
        self,
        db: AsyncSession,
        *,
        delivery_id: uuid.UUID,
        sender: MfaEmailSender,
        now: datetime | None = None,
    ) -> None:
        claimed_at = now or datetime.now(UTC)
        lease_token = secrets.token_urlsafe(32)
        lease_expires_at = claimed_at + timedelta(minutes=2)
        claimed = (
            await db.execute(
                update(MfaEmailDelivery)
                .where(
                    MfaEmailDelivery.id == delivery_id,
                    or_(
                        MfaEmailDelivery.status == "pending",
                        (
                            (MfaEmailDelivery.status == "sending")
                            & (MfaEmailDelivery.lease_expires_at <= claimed_at)
                        ),
                    ),
                )
                .values(
                    status="sending",
                    lease_token=lease_token,
                    lease_expires_at=lease_expires_at,
                    attempt_count=MfaEmailDelivery.attempt_count + 1,
                )
                .returning(MfaEmailDelivery.id)
            )
        ).one_or_none()
        if claimed is None:
            status_value = await db.scalar(
                select(MfaEmailDelivery.status).where(
                    MfaEmailDelivery.id == delivery_id
                )
            )
            if status_value in {"sent", "sending"}:
                return
            raise MfaDeliveryError()
        # This is a worker lease boundary: commit before network I/O so no row
        # lock or transaction remains open while SMTP is unavailable or slow.
        await db.commit()
        delivery = await db.get(
            MfaEmailDelivery,
            delivery_id,
            populate_existing=True,
        )
        if delivery is None or delivery.lease_token != lease_token:
            raise MfaDeliveryError()
        challenge = (
            await db.execute(
                select(MfaChallenge)
                .where(MfaChallenge.id == delivery.challenge_id)
                .with_for_update(nowait=False)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        # A contended challenge lock can outlive the timestamp captured for the
        # lease CAS. Re-read the wall clock after acquiring it so an OTP that
        # expires while waiting is never sent. Explicit test clocks remain
        # deterministic by design.
        validation_time = now if now is not None else datetime.now(UTC)
        if (
            challenge is None
            or challenge.method != MFA_METHOD_EMAIL_OTP
            or challenge.state != ChallengeState.PENDING
            or challenge.revision != delivery.revision
            or _aware(challenge.expires_at) <= validation_time
        ):
            cancelled = await db.execute(
                update(MfaEmailDelivery)
                .where(
                    MfaEmailDelivery.id == delivery_id,
                    MfaEmailDelivery.status == "sending",
                    MfaEmailDelivery.lease_token == lease_token,
                )
                .values(
                    status="cancelled",
                    shredded_at=validation_time,
                    envelope_nonce=None,
                    envelope_ciphertext=None,
                    wrap_nonce=None,
                    wrapped_dek=None,
                    lease_token=None,
                    lease_expires_at=None,
                )
            )
            if getattr(cancelled, "rowcount", 0) != 1:
                raise MfaDeliveryError()
            await db.commit()
            return
        try:
            envelope = self._decrypt_delivery(delivery)
            subject, plain, html_body = self._render_email(
                otp=envelope["otp"],
                display_name=envelope["display_name"],
                locale=delivery.locale,
            )
            await sender.send(
                to_email=envelope["email"],
                subject=subject,
                plain=plain,
                html=html_body,
                message_id=delivery.message_id,
            )
        except MfaDeliveryError:
            await db.execute(
                update(MfaEmailDelivery)
                .where(
                    MfaEmailDelivery.id == delivery_id,
                    MfaEmailDelivery.lease_token == lease_token,
                )
                .values(status="pending", lease_token=None, lease_expires_at=None)
            )
            await db.commit()
            logger.error(
                "mfa_email_delivery_failed",
                extra={"delivery_id": str(delivery.id)},
            )
            raise
        except (OSError, TimeoutError) as exc:
            await db.execute(
                update(MfaEmailDelivery)
                .where(
                    MfaEmailDelivery.id == delivery_id,
                    MfaEmailDelivery.lease_token == lease_token,
                )
                .values(status="pending", lease_token=None, lease_expires_at=None)
            )
            await db.commit()
            logger.error(
                "mfa_email_delivery_failed",
                extra={"delivery_id": str(delivery.id)},
            )
            raise MfaDeliveryError() from exc
        sent_at = now or datetime.now(UTC)
        completed = await db.execute(
            update(MfaEmailDelivery)
            .where(
                MfaEmailDelivery.id == delivery_id,
                MfaEmailDelivery.status == "sending",
                MfaEmailDelivery.lease_token == lease_token,
            )
            .values(
                status="sent",
                sent_at=sent_at,
                shredded_at=sent_at,
                envelope_nonce=None,
                envelope_ciphertext=None,
                wrap_nonce=None,
                wrapped_dek=None,
                lease_token=None,
                lease_expires_at=None,
            )
        )
        if getattr(completed, "rowcount", 0) != 1:
            raise MfaDeliveryError()
        await db.flush()


def _parse_key_ring(raw: str) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for entry in raw.split(","):
        if not entry.strip():
            continue
        try:
            parts = entry.split(":")
            if len(parts) != 2:
                raise ValueError("key-ring entry must contain exactly one delimiter")
            key_id, encoded = (part.strip() for part in parts)
            if not key_id or key_id in keys:
                raise ValueError("key-ring identifier is empty or duplicated")
            if (
                not encoded
                or any(
                    character not in (string.ascii_letters + string.digits + "-_")
                    for character in encoded
                )
                or len(encoded) % 4 == 1
            ):
                raise ValueError("key-ring value is not strict base64url")
            decoded = _b64decode(encoded)
            if not decoded:
                # The parser intentionally exposes one generic security error
                # to callers.  There is no useful internal detail to retain
                # for an empty value, so raise a message-free sentinel and
                # avoid creating misleading diagnostics that are discarded by
                # the outer exception boundary.
                raise ValueError
            keys[key_id] = decoded
        except (ValueError, TypeError, binascii.Error):
            raise MfaSecurityUnavailable() from None
    return keys


def build_configured_email_otp_service(
    *, rate_limiter: MfaRateLimiter | None = None
) -> EmailOtpService:
    """Build the worker service from rotatable configured HMAC/KEK rings."""
    from app.core.config import settings

    return EmailOtpService(
        hmac_keys=_parse_key_ring(settings.mfa_email_otp_hmac_keys),
        active_hmac_key_id=settings.mfa_email_otp_active_hmac_key_id,
        delivery_keks=_parse_key_ring(settings.mfa_email_delivery_keks),
        active_kek_id=settings.mfa_email_delivery_active_kek_id,
        rate_limiter=rate_limiter or _DeliveryOnlyRateLimiter(),
    )


def build_configured_email_delivery_service() -> EmailOtpService:
    """Build a least-privilege worker that can only decrypt delivery envelopes."""
    from app.core.config import settings

    delivery_keks = _parse_key_ring(settings.mfa_email_delivery_keks)
    if not delivery_keks:
        raise MfaSecurityUnavailable()
    return EmailOtpService(
        hmac_keys={},
        active_hmac_key_id="",
        delivery_keks=delivery_keks,
        active_kek_id=next(iter(delivery_keks)),
        rate_limiter=_DeliveryOnlyRateLimiter(),
        delivery_only=True,
    )


__all__ = [
    "OTP_DIGITS",
    "OTP_MAX_FAILED_ATTEMPTS",
    "OTP_RESEND_COOLDOWN_SECONDS",
    "OTP_TTL_SECONDS",
    "EmailOtpService",
    "IssuedEmailOtp",
    "MfaDeliveryError",
    "MfaOtpCooldown",
    "MfaOtpRejected",
    "MfaSecurityUnavailable",
    "RuntimeMfaRateLimiter",
    "SmtpMfaEmailSender",
    "build_configured_email_delivery_service",
    "build_configured_email_otp_service",
]
