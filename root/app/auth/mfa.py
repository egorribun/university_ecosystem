"""Helpers for managing multi-factor authentication secrets and challenges."""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.authentication.verify_authentication_response import (
    VerifiedAuthentication,
)
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialCreationOptions,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRequestOptions,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.registration.verify_registration_response import (
    VerifiedRegistration,
)

from app.core.config import settings
from app.core.rate_limit import RateLimitExceeded, enforce_rate_limit
from app.localization import translate
from app.models.models import (
    ActiveSession,
    MfaChallenge,
    MfaRecoveryCode,
    MfaTotpEnrollment,
    MfaWebAuthnCredential,
    User,
)
from app.utils import ratelimit as ratelimit_utils

_RECOVERY_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_RECOVERY_CODE_LENGTH = 10
_RECOVERY_CODE_CHUNK = 5
_RECOVERY_CODE_COUNT = 10
_TOTP_SECRET_LENGTH = 32
_TOTP_VALID_WINDOW = settings.mfa_totp_initial_skew_windows
_TOTP_DIGITS = 6

CHALLENGE_TYPE_TOTP_ENROLL = "totp-enroll"
CHALLENGE_TYPE_TOTP_VERIFY = "totp-verify"
CHALLENGE_TYPE_WEBAUTHN_ENROLL = "webauthn-enroll"
CHALLENGE_TYPE_WEBAUTHN_ASSERT = "webauthn-assert"
CHALLENGE_TYPE_RECOVERY = "recovery-code"

MFA_METHOD_TOTP = "totp"
MFA_METHOD_WEBAUTHN = "webauthn"
MFA_METHOD_RECOVERY = "recovery"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _base64url_encode(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(data).decode("utf-8")
    return encoded.rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _normalize_recovery_code(value: str) -> str:
    normalized = "".join(ch for ch in value if ch.isalnum())
    return normalized.upper()


def hash_recovery_code(value: str) -> str:
    normalized = _normalize_recovery_code(value)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest


def generate_recovery_codes(count: int = _RECOVERY_CODE_COUNT) -> list[str]:
    codes: list[str] = []
    seen_hashes: set[str] = set()
    while len(codes) < count:
        raw = "".join(
            secrets.choice(_RECOVERY_CODE_ALPHABET)
            for _ in range(_RECOVERY_CODE_LENGTH)
        )
        grouped = "-".join(
            raw[index : index + _RECOVERY_CODE_CHUNK]
            for index in range(0, len(raw), _RECOVERY_CODE_CHUNK)
        )
        digest = hash_recovery_code(grouped)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        codes.append(grouped)
    return codes


def create_totp_secret(length: int = _TOTP_SECRET_LENGTH) -> str:
    return pyotp.random_base32(length=length)


def build_totp_uri(secret: str, *, account_name: str, issuer: str | None = None) -> str:
    issuer_name = issuer or settings.mfa_totp_issuer
    totp = pyotp.TOTP(secret, digits=_TOTP_DIGITS)
    return totp.provisioning_uri(name=account_name, issuer_name=issuer_name)


def verify_totp(secret: str, code: str, *, window: int | None = None) -> bool:
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != _TOTP_DIGITS:
        return False
    totp = pyotp.TOTP(secret, digits=_TOTP_DIGITS)
    valid_window = _TOTP_VALID_WINDOW if window is None else window
    return bool(
        totp.verify(
            normalized,
            valid_window=valid_window,
            for_time=None,
        )
    )


def _resolve_rate_limit_backend() -> str | None:
    backend = settings.rate_limit_storage_backend.strip().lower()
    uri = settings.rate_limit_storage_uri.strip()
    if backend == "redis" and uri.lower().startswith(("redis://", "rediss://")):
        return uri
    return None


async def _enforce_challenge_rate_limit(
    *,
    user_id: int,
    challenge_type: str,
    locale: str | None = None,
) -> None:
    limit = max(0, settings.mfa_challenge_max_attempts)
    window = max(0, settings.mfa_challenge_ttl_seconds)
    if limit == 0 or window == 0:
        return
    key = f"mfa:{challenge_type}:{user_id}"
    message = translate("errors.rate_limit.generic", locale=locale)
    redis_url = _resolve_rate_limit_backend()
    if redis_url:
        try:
            await enforce_rate_limit(
                identifier=key,
                namespace="mfa",
                limit=limit,
                window_seconds=window,
                redis_url=redis_url,
            )
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=message,
            ) from exc
    else:
        ratelimit_utils.limiter.check(key, limit, window, message=message)


async def issue_challenge(
    db: AsyncSession,
    *,
    user_id: int,
    challenge_type: str,
    session_id: int | None = None,
    payload: MutableMapping[str, Any] | None = None,
    ttl_seconds: int | None = None,
    locale: str | None = None,
) -> MfaChallenge:
    await _enforce_challenge_rate_limit(
        user_id=user_id, challenge_type=challenge_type, locale=locale
    )
    token = secrets.token_urlsafe(48)
    now = _utcnow()
    ttl = (
        ttl_seconds
        if ttl_seconds and ttl_seconds > 0
        else settings.mfa_challenge_ttl_seconds
    )
    expires_at = now + timedelta(seconds=ttl)
    challenge = MfaChallenge(
        user_id=user_id,
        session_id=session_id,
        challenge_type=challenge_type,
        token=token,
        expires_at=expires_at,
        payload=dict(payload or {}),
    )
    db.add(challenge)
    await db.flush()
    return challenge


async def get_challenge(
    db: AsyncSession,
    *,
    token: str,
    challenge_type: str,
    user_id: int | None = None,
    session_id: int | None = None,
    consume: bool = False,
) -> MfaChallenge:
    stmt = select(MfaChallenge).where(MfaChallenge.token == token)
    stmt = stmt.where(MfaChallenge.challenge_type == challenge_type)
    if user_id is not None:
        stmt = stmt.where(MfaChallenge.user_id == user_id)
    if session_id is not None:
        stmt = stmt.where(MfaChallenge.session_id == session_id)
    result = await db.execute(stmt)
    challenge = result.scalars().first()
    if not challenge:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired challenge")
    now = _utcnow()
    if challenge.consumed_at is not None or challenge.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired challenge")
    if consume:
        challenge.consumed_at = now
        await db.flush()
    return challenge


async def consume_challenge(db: AsyncSession, challenge: MfaChallenge) -> None:
    if challenge.consumed_at is None:
        challenge.consumed_at = _utcnow()
        await db.flush()


async def purge_expired_challenges(db: AsyncSession) -> int:
    now = _utcnow()
    result = await db.execute(
        delete(MfaChallenge).where(MfaChallenge.expires_at <= now)
    )
    await db.flush()
    return result.rowcount or 0


async def create_recovery_codes(
    db: AsyncSession,
    *,
    user: User,
    count: int = _RECOVERY_CODE_COUNT,
) -> list[str]:
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    codes = generate_recovery_codes(count)
    now = _utcnow()
    for code in codes:
        digest = hash_recovery_code(code)
        record = MfaRecoveryCode(user_id=user.id, code_hash=digest)
        db.add(record)
    user.mfa_recovery_codes_generated_at = now
    await db.flush()
    return codes


async def use_recovery_code(
    db: AsyncSession,
    *,
    user: User,
    code: str,
    challenge_token: str | None = None,
    session_id: int | None = None,
) -> tuple[MfaRecoveryCode, MfaChallenge | None]:
    normalized_hash = hash_recovery_code(code)
    stmt = (
        select(MfaRecoveryCode)
        .where(MfaRecoveryCode.user_id == user.id)
        .where(MfaRecoveryCode.code_hash == normalized_hash)
    )
    result = await db.execute(stmt)
    record = result.scalars().first()
    if not record or record.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid recovery code")
    challenge: MfaChallenge | None = None
    if challenge_token:
        challenge = await get_challenge(
            db,
            token=challenge_token,
            challenge_type=CHALLENGE_TYPE_RECOVERY,
            user_id=user.id,
            session_id=session_id,
        )
        await consume_challenge(db, challenge)
    record.used_at = _utcnow()
    await db.flush()
    return record, challenge


async def start_totp_enrollment(
    db: AsyncSession,
    *,
    user: User,
    label: str | None = None,
) -> tuple[MfaTotpEnrollment, str, str]:
    secret = create_totp_secret()
    enrollment = MfaTotpEnrollment(
        user_id=user.id,
        secret=secret,
        label=label or user.email,
        is_active=True,
    )
    db.add(enrollment)
    await db.flush()
    account_name = label or user.email
    otpauth_url = build_totp_uri(secret, account_name=account_name)
    return enrollment, secret, otpauth_url


async def complete_totp_enrollment(
    db: AsyncSession,
    *,
    enrollment: MfaTotpEnrollment,
    code: str,
) -> MfaTotpEnrollment:
    if not verify_totp(enrollment.secret, code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid verification code")
    now = _utcnow()
    enrollment.confirmed_at = now
    enrollment.revoked_at = None
    enrollment.is_active = True
    await db.flush()
    return enrollment


async def disable_totp(
    db: AsyncSession,
    *,
    user: User,
    enrollment_id: int | None = None,
) -> int:
    stmt = select(MfaTotpEnrollment).where(MfaTotpEnrollment.user_id == user.id)
    if enrollment_id is not None:
        stmt = stmt.where(MfaTotpEnrollment.id == enrollment_id)
    result = await db.execute(stmt)
    count = 0
    now = _utcnow()
    for record in result.scalars():
        if record.is_active:
            record.is_active = False
            record.revoked_at = now
            count += 1
    await db.flush()
    return count


async def start_totp_verification(
    db: AsyncSession,
    *,
    user: User,
    session: ActiveSession | None = None,
    locale: str | None = None,
    payload: MutableMapping[str, Any] | None = None,
) -> MfaChallenge:
    challenge = await issue_challenge(
        db,
        user_id=user.id,
        session_id=session.id if session else None,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        locale=locale,
        payload=dict(payload or {}),
    )
    return challenge


async def verify_totp_for_user(
    db: AsyncSession,
    *,
    user: User,
    code: str,
    challenge_token: str | None = None,
    challenge: MfaChallenge | None = None,
    session_id: int | None = None,
) -> tuple[MfaTotpEnrollment, MfaChallenge | None]:
    stmt = (
        select(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.is_active.is_(True))
        .where(MfaTotpEnrollment.revoked_at.is_(None))
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
    )
    result = await db.execute(stmt)
    enrollments = list(result.scalars())
    if not enrollments:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active TOTP enrollment")
    loaded_challenge = challenge
    if challenge_token and loaded_challenge is None:
        loaded_challenge = await get_challenge(
            db,
            token=challenge_token,
            challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
            user_id=user.id,
            session_id=session_id,
        )
    if loaded_challenge is not None:
        if loaded_challenge.challenge_type != CHALLENGE_TYPE_TOTP_VERIFY:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Invalid or expired challenge"
            )
        if loaded_challenge.user_id != user.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Invalid or expired challenge"
            )
        if session_id is not None and loaded_challenge.session_id != session_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Invalid or expired challenge"
            )
    for enrollment in enrollments:
        if verify_totp(enrollment.secret, code):
            if loaded_challenge is not None:
                await consume_challenge(db, loaded_challenge)
            return enrollment, loaded_challenge
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid verification code")


def _serialize_registration_options(
    options: PublicKeyCredentialCreationOptions,
) -> dict[str, Any]:
    payload = options.model_dump()
    payload["challenge"] = _base64url_encode(payload["challenge"])
    payload["user"]["id"] = _base64url_encode(payload["user"]["id"])
    exclude = []
    for descriptor in payload.get("exclude_credentials", []) or []:
        descriptor["id"] = _base64url_encode(descriptor["id"])
        exclude.append(descriptor)
    payload["exclude_credentials"] = exclude
    return payload


def _serialize_authentication_options(
    options: PublicKeyCredentialRequestOptions,
) -> dict[str, Any]:
    payload = options.model_dump()
    payload["challenge"] = _base64url_encode(payload["challenge"])
    allow = []
    for descriptor in payload.get("allow_credentials", []) or []:
        descriptor["id"] = _base64url_encode(descriptor["id"])
        allow.append(descriptor)
    payload["allow_credentials"] = allow
    return payload


def _credential_descriptor_from_db(
    credential: MfaWebAuthnCredential,
) -> PublicKeyCredentialDescriptor:
    transports: list[AuthenticatorTransport] | None = None
    if credential.transports:
        resolved: list[AuthenticatorTransport] = []
        for entry in credential.transports:
            try:
                resolved.append(AuthenticatorTransport(entry))
            except ValueError:
                continue
        transports = resolved or None
    return PublicKeyCredentialDescriptor(
        id=_base64url_decode(credential.credential_id),
        type="public-key",
        transports=transports,
    )


async def start_webauthn_enrollment(
    db: AsyncSession,
    *,
    user: User,
    session: ActiveSession | None = None,
    locale: str | None = None,
) -> tuple[dict[str, Any], MfaChallenge]:
    stmt = (
        select(MfaWebAuthnCredential)
        .where(MfaWebAuthnCredential.user_id == user.id)
        .where(MfaWebAuthnCredential.is_active.is_(True))
    )
    result = await db.execute(stmt)
    exclude = [
        _credential_descriptor_from_db(credential) for credential in result.scalars()
    ]
    options = generate_registration_options(
        rp_id=settings.mfa_webauthn_rp_id,
        rp_name=settings.mfa_webauthn_rp_name,
        user_id=str(user.id),
        user_name=user.email,
        user_display_name=user.full_name or user.email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude or None,
    )
    challenge_payload = {"challenge": _base64url_encode(options.challenge)}
    challenge = await issue_challenge(
        db,
        user_id=user.id,
        session_id=session.id if session else None,
        challenge_type=CHALLENGE_TYPE_WEBAUTHN_ENROLL,
        payload=challenge_payload,
        locale=locale,
    )
    return _serialize_registration_options(options), challenge


async def complete_webauthn_enrollment(
    db: AsyncSession,
    *,
    user: User,
    credential: RegistrationCredential | Mapping[str, Any],
    challenge_token: str,
    device_name: str | None = None,
) -> MfaWebAuthnCredential:
    challenge = await get_challenge(
        db,
        token=challenge_token,
        challenge_type=CHALLENGE_TYPE_WEBAUTHN_ENROLL,
        user_id=user.id,
        consume=True,
    )
    stored_challenge = challenge.payload.get("challenge") if challenge.payload else None
    if not stored_challenge:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Challenge payload missing")
    expected_challenge = _base64url_decode(stored_challenge)
    verified: VerifiedRegistration = verify_registration_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=settings.mfa_webauthn_rp_id,
        expected_origin=settings.mfa_webauthn_origin,
        require_user_verification=True,
    )
    credential_id = _base64url_encode(verified.credential_id)
    public_key = _base64url_encode(verified.credential_public_key)
    transports: list[str] | None = None
    if isinstance(credential, RegistrationCredential):
        if credential.response.transports:
            transports = [
                transport.value for transport in credential.response.transports
            ]
    elif isinstance(credential, Mapping):
        transports = credential.get("transports")
    record = MfaWebAuthnCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=public_key,
        sign_count=verified.sign_count,
        transports=transports,
        device_name=device_name,
        backed_up=verified.credential_backed_up,
        clone_warning=False,
    )
    db.add(record)
    await db.flush()
    return record


async def start_webauthn_assertion(
    db: AsyncSession,
    *,
    user: User,
    session: ActiveSession | None = None,
    locale: str | None = None,
    payload: MutableMapping[str, Any] | None = None,
) -> tuple[dict[str, Any], MfaChallenge]:
    stmt = (
        select(MfaWebAuthnCredential)
        .where(MfaWebAuthnCredential.user_id == user.id)
        .where(MfaWebAuthnCredential.is_active.is_(True))
    )
    result = await db.execute(stmt)
    credentials = list(result.scalars())
    if not credentials:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No active WebAuthn credentials",
        )
    allow_credentials = [
        _credential_descriptor_from_db(credential) for credential in credentials
    ]
    options = generate_authentication_options(
        rp_id=settings.mfa_webauthn_rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_payload = {"challenge": _base64url_encode(options.challenge)}
    merged_payload = dict(payload or {})
    merged_payload.update(challenge_payload)
    challenge = await issue_challenge(
        db,
        user_id=user.id,
        session_id=session.id if session else None,
        challenge_type=CHALLENGE_TYPE_WEBAUTHN_ASSERT,
        payload=merged_payload,
        locale=locale,
    )
    return _serialize_authentication_options(options), challenge


async def verify_webauthn_assertion(
    db: AsyncSession,
    *,
    user: User,
    credential: AuthenticationCredential | Mapping[str, Any],
    challenge_token: str,
    session_id: int | None = None,
) -> tuple[MfaWebAuthnCredential, MfaChallenge]:
    challenge = await get_challenge(
        db,
        token=challenge_token,
        challenge_type=CHALLENGE_TYPE_WEBAUTHN_ASSERT,
        user_id=user.id,
        session_id=session_id,
        consume=False,
    )
    stored_challenge = challenge.payload.get("challenge") if challenge.payload else None
    if not stored_challenge:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Challenge payload missing")
    expected_challenge = _base64url_decode(stored_challenge)
    raw_id: bytes
    if isinstance(credential, AuthenticationCredential):
        raw_id = credential.raw_id
    else:
        raw_id_encoded = credential.get("rawId") or credential.get("raw_id")
        if not raw_id_encoded:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Credential missing raw_id",
            )
        if isinstance(raw_id_encoded, str):
            raw_id = _base64url_decode(raw_id_encoded)
        else:
            raw_id = raw_id_encoded
    stmt = (
        select(MfaWebAuthnCredential)
        .where(MfaWebAuthnCredential.user_id == user.id)
        .where(MfaWebAuthnCredential.credential_id == _base64url_encode(raw_id))
        .where(MfaWebAuthnCredential.is_active.is_(True))
    )
    result = await db.execute(stmt)
    record = result.scalars().first()
    if not record:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown credential")
    verified: VerifiedAuthentication = verify_authentication_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=settings.mfa_webauthn_rp_id,
        expected_origin=settings.mfa_webauthn_origin,
        credential_public_key=_base64url_decode(record.public_key),
        credential_current_sign_count=record.sign_count,
        require_user_verification=True,
    )
    record.clone_warning = verified.new_sign_count <= record.sign_count
    record.sign_count = verified.new_sign_count
    record.last_used_at = _utcnow()
    record.backed_up = verified.credential_backed_up
    await db.flush()
    await consume_challenge(db, challenge)
    return record, challenge


async def disable_webauthn_credential(
    db: AsyncSession,
    *,
    user: User,
    credential_id: str | None = None,
) -> int:
    stmt = select(MfaWebAuthnCredential).where(MfaWebAuthnCredential.user_id == user.id)
    if credential_id is not None:
        stmt = stmt.where(MfaWebAuthnCredential.credential_id == credential_id)
    result = await db.execute(stmt)
    count = 0
    for credential in result.scalars():
        if credential.is_active:
            credential.is_active = False
            count += 1
    await db.flush()
    return count


async def record_mfa_success(
    db: AsyncSession,
    *,
    user: User,
    session: ActiveSession | None,
    method: str,
) -> None:
    now = _utcnow()
    user.mfa_last_verified_at = now
    if session is not None:
        session.mfa_completed_at = now
        session.mfa_required = False
        session.mfa_method = method[:64]
        session.mfa_verified_at = now
    await db.flush()
