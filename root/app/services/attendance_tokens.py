from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings


class AttendanceTokenError(Exception):
    """Base error for attendance token failures."""


class AttendanceTokenInvalid(AttendanceTokenError):
    """Raised when the token payload or signature is invalid."""


class AttendanceTokenExpired(AttendanceTokenError):
    """Raised when the token has expired."""


TOKEN_PURPOSE = "event_attendance"


def _server_secret() -> bytes:
    secret = settings.attendance_token_secret or settings.secret_key
    normalized = secret.strip()
    if not normalized:
        raise AttendanceTokenError("Attendance token secret is not configured")
    return normalized.encode("utf-8")


def _now() -> datetime:
    return datetime.now(UTC)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def compute_secret_hmac(secret: str) -> str:
    digest = hmac.new(_server_secret(), secret.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def ensure_secret_material(attendance: Any) -> bool:
    """Ensure an attendance row has valid secret material.

    Returns ``True`` if the record was modified.
    """

    secret = getattr(attendance, "qr_secret", None)
    hmac_value = getattr(attendance, "qr_hmac", None)
    if secret and hmac_value:
        expected = compute_secret_hmac(secret)
        if secrets.compare_digest(expected, hmac_value):
            return False
    new_secret = secret or generate_secret()
    attendance.qr_secret = new_secret
    attendance.qr_hmac = compute_secret_hmac(new_secret)
    return True


@dataclass(slots=True)
class AttendanceTokenPayload:
    purpose: str
    event_id: int
    user_id: int
    secret: str
    issued_at: int
    expires_at: int

    def encode(self) -> bytes:
        payload = {
            "sub": self.purpose,
            "eid": self.event_id,
            "uid": self.user_id,
            "sec": self.secret,
            "iat": self.issued_at,
            "exp": self.expires_at,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    @classmethod
    def decode(cls, data: bytes) -> AttendanceTokenPayload:
        payload = json.loads(data.decode("utf-8"))
        return cls(
            purpose=payload["sub"],
            event_id=int(payload["eid"]),
            user_id=int(payload["uid"]),
            secret=str(payload["sec"]),
            issued_at=int(payload["iat"]),
            expires_at=int(payload["exp"]),
        )


def issue_token(
    attendance: Any, *, now: datetime | None = None, ttl_seconds: int | None = None
) -> str:
    secret = getattr(attendance, "qr_secret", None)
    if not isinstance(secret, str) or not secret:
        raise AttendanceTokenError("Attendance record is missing QR secret material")
    ttl = ttl_seconds or settings.attendance_token_ttl_seconds
    if ttl <= 0:
        raise AttendanceTokenError("Attendance token TTL must be positive")
    moment = now or _now()
    moment_seconds = int(moment.timestamp())
    issued_at = moment_seconds - (moment_seconds % ttl)
    expires_at = issued_at + ttl
    payload = AttendanceTokenPayload(
        purpose=TOKEN_PURPOSE,
        event_id=int(attendance.event_id),
        user_id=int(attendance.user_id),
        secret=secret,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    payload_bytes = payload.encode()
    signature = hmac.new(_server_secret(), payload_bytes, hashlib.sha256).digest()
    return f"{_b64encode(payload_bytes)}.{_b64encode(signature)}"


def verify_token(
    token: str,
    attendance: Any,
    *,
    now: datetime | None = None,
) -> AttendanceTokenPayload:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError as exc:
        raise AttendanceTokenInvalid("Token structure is invalid") from exc
    try:
        payload_bytes = _b64decode(payload_b64)
    except (ValueError, binascii.Error) as exc:
        raise AttendanceTokenInvalid("Token payload encoding is invalid") from exc
    if _b64encode(payload_bytes) != payload_b64:
        raise AttendanceTokenInvalid("Token payload encoding is non-canonical")
    expected_signature = hmac.new(_server_secret(), payload_bytes, hashlib.sha256).digest()
    try:
        provided_signature = _b64decode(signature_b64)
    except (ValueError, binascii.Error) as exc:
        raise AttendanceTokenInvalid("Token signature encoding is invalid") from exc
    if _b64encode(provided_signature) != signature_b64:
        raise AttendanceTokenInvalid("Token signature encoding is non-canonical")
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise AttendanceTokenInvalid("Token signature mismatch")
    try:
        payload = AttendanceTokenPayload.decode(payload_bytes)
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise AttendanceTokenInvalid("Token payload is invalid") from exc
    if payload.purpose != TOKEN_PURPOSE:
        raise AttendanceTokenInvalid("Token purpose mismatch")
    if payload.event_id != attendance.event_id:
        raise AttendanceTokenInvalid("Token event mismatch")
    if payload.user_id != attendance.user_id:
        raise AttendanceTokenInvalid("Token user mismatch")
    expected_hmac = getattr(attendance, "qr_hmac", None)
    if not expected_hmac:
        raise AttendanceTokenInvalid("Attendance record missing secret signature")
    calculated = compute_secret_hmac(payload.secret)
    if not hmac.compare_digest(calculated, expected_hmac):
        raise AttendanceTokenInvalid("Token secret is not active")
    ttl_window = max(1, payload.expires_at - payload.issued_at)
    valid_until = payload.expires_at + ttl_window
    moment = now or _now()
    if moment.timestamp() >= valid_until:
        raise AttendanceTokenExpired("Token has expired")
    return payload


__all__ = [
    "AttendanceTokenError",
    "AttendanceTokenExpired",
    "AttendanceTokenInvalid",
    "AttendanceTokenPayload",
    "TOKEN_PURPOSE",
    "compute_secret_hmac",
    "ensure_secret_material",
    "generate_secret",
    "issue_token",
    "verify_token",
]
