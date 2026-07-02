import base64
import datetime
import uuid
from dataclasses import dataclass

import pytest

from app.core.config import settings
from app.services.attendance_tokens import (
    TOKEN_PURPOSE,
    AttendanceTokenError,
    AttendanceTokenExpired,
    AttendanceTokenInvalid,
    AttendanceTokenPayload,
    _b64decode,
    _b64encode,
    compute_secret_hmac,
    ensure_secret_material,
    generate_secret,
    issue_token,
    verify_token,
)


@dataclass
class DummyAttendance:
    event_id: uuid.UUID
    user_id: uuid.UUID
    qr_secret: str | None = None
    qr_hmac: str | None = None


@pytest.fixture
def sample_attendance():
    return DummyAttendance(
        event_id=uuid.UUID("d03e5d4f-2ebb-48b7-baf6-a2c9676ffc5e"),
        user_id=uuid.UUID("53596bea-03c9-4dc0-a92d-a3960744b14d"),
    )


@pytest.fixture
def fixed_now():
    return datetime.datetime(2026, 1, 1, 12, 0, 15, tzinfo=datetime.UTC)


def test_server_secret_missing_config(monkeypatch):
    monkeypatch.setattr(settings, "attendance_token_secret", "")
    monkeypatch.setattr(settings, "secret_key", "")
    with pytest.raises(
        AttendanceTokenError, match="Attendance token secret is not configured"
    ):
        compute_secret_hmac("some_secret")


def test_generate_secret():
    secret = generate_secret()
    assert isinstance(secret, str)
    assert len(secret) > 0


def test_ensure_secret_material(sample_attendance):
    # Generates brand new secret material
    modified = ensure_secret_material(sample_attendance)
    assert modified is True
    assert sample_attendance.qr_secret is not None
    assert sample_attendance.qr_hmac is not None

    # Idempotent case - returns False and does not change values
    secret1 = sample_attendance.qr_secret
    hmac1 = sample_attendance.qr_hmac
    modified = ensure_secret_material(sample_attendance)
    assert modified is False
    assert sample_attendance.qr_secret == secret1
    assert sample_attendance.qr_hmac == hmac1

    # Regenerates if HMAC is mismatched/corrupted
    sample_attendance.qr_hmac = "corrupted_hmac"
    modified = ensure_secret_material(sample_attendance)
    assert modified is True
    assert sample_attendance.qr_secret == secret1
    assert sample_attendance.qr_hmac != "corrupted_hmac"


def test_issue_token_validation(sample_attendance, fixed_now, monkeypatch):
    # Missing QR secret
    with pytest.raises(
        AttendanceTokenError, match="Attendance record is missing QR secret material"
    ):
        issue_token(sample_attendance, now=fixed_now)

    ensure_secret_material(sample_attendance)

    # Positive TTL validation with negative value
    with pytest.raises(
        AttendanceTokenError, match="Attendance token TTL must be positive"
    ):
        issue_token(sample_attendance, now=fixed_now, ttl_seconds=-5)

    # Positive TTL validation with default TTL mocked to 0
    monkeypatch.setattr(settings, "attendance_token_ttl_seconds", 0)
    with pytest.raises(
        AttendanceTokenError, match="Attendance token TTL must be positive"
    ):
        issue_token(sample_attendance, now=fixed_now, ttl_seconds=None)


def test_issue_and_verify_token_happy_path(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    token = issue_token(sample_attendance, now=fixed_now, ttl_seconds=300)

    # Verification passes
    payload = verify_token(token, sample_attendance, now=fixed_now)
    assert payload.purpose == TOKEN_PURPOSE
    assert payload.event_id == sample_attendance.event_id
    assert payload.user_id == sample_attendance.user_id
    assert payload.secret == sample_attendance.qr_secret


def test_verify_token_invalid_structure(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)

    # No dots
    with pytest.raises(AttendanceTokenInvalid, match="Token structure is invalid"):
        verify_token("nodotsintoken", sample_attendance, now=fixed_now)

    # Too many dots - raises non-canonical signature because of multiple dots in signature_b64
    with pytest.raises(
        AttendanceTokenInvalid, match="Token signature encoding is non-canonical"
    ):
        verify_token("too.many.dots.here", sample_attendance, now=fixed_now)


def test_verify_token_invalid_payload_encoding(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    # Bad base64 alphabet characters will fail canonical check
    with pytest.raises(
        AttendanceTokenInvalid, match="Token payload encoding is non-canonical"
    ):
        verify_token("invalid_b64***.signature", sample_attendance, now=fixed_now)


def test_verify_token_non_canonical_payload(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    payload_bytes = b'{"sub":"event_attendance"}'
    # Non-canonical base64: standard b64 instead of urlsafe, or trailing padding characters left in place
    non_canonical_payload = base64.b64encode(payload_bytes).decode("ascii")
    with pytest.raises(
        AttendanceTokenInvalid, match="Token payload encoding is non-canonical"
    ):
        verify_token(
            f"{non_canonical_payload}.signature", sample_attendance, now=fixed_now
        )


def test_verify_token_invalid_signature_encoding(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    payload_bytes = b'{"sub":"event_attendance"}'
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")

    with pytest.raises(
        AttendanceTokenInvalid,
        match=r"Token signature encoding is invalid|non-canonical",
    ):
        verify_token(
            f"{payload_b64}.invalid_sig_chars***", sample_attendance, now=fixed_now
        )


def test_verify_token_non_canonical_signature(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    token = issue_token(sample_attendance, now=fixed_now, ttl_seconds=300)
    payload_b64, signature_b64 = token.split(".", 1)

    # Append padding to the signature to make it non-canonical
    non_canonical_sig = signature_b64 + "="
    with pytest.raises(
        AttendanceTokenInvalid, match="Token signature encoding is non-canonical"
    ):
        verify_token(
            f"{payload_b64}.{non_canonical_sig}", sample_attendance, now=fixed_now
        )


def test_verify_token_signature_mismatch(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    token = issue_token(sample_attendance, now=fixed_now, ttl_seconds=300)
    payload_b64, signature_b64 = token.split(".", 1)

    # Decode signature, flip first bit, then re-encode canonically
    sig_bytes = bytearray(_b64decode(signature_b64))
    sig_bytes[0] ^= 1  # flip 1 bit
    corrupted_sig = _b64encode(bytes(sig_bytes))

    with pytest.raises(AttendanceTokenInvalid, match="Token signature mismatch"):
        verify_token(f"{payload_b64}.{corrupted_sig}", sample_attendance, now=fixed_now)


def test_verify_token_invalid_json(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    bad_payload_bytes = b"not_json"
    bad_payload_b64 = (
        base64.urlsafe_b64encode(bad_payload_bytes).rstrip(b"=").decode("ascii")
    )

    # Generate a matching HMAC for this bad payload to bypass signature check
    import hashlib
    import hmac

    from app.services.attendance_tokens import _server_secret

    sig = hmac.new(_server_secret(), bad_payload_bytes, hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)

    with pytest.raises(AttendanceTokenInvalid, match="Token payload is invalid"):
        verify_token(f"{bad_payload_b64}.{sig_b64}", sample_attendance, now=fixed_now)


def test_verify_token_mismatches(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)

    # 1. Purpose Mismatch
    payload = AttendanceTokenPayload(
        purpose="wrong_purpose",
        event_id=sample_attendance.event_id,
        user_id=sample_attendance.user_id,
        secret=sample_attendance.qr_secret,
        issued_at=int(fixed_now.timestamp()),
        expires_at=int(fixed_now.timestamp()) + 300,
    )
    import hashlib
    import hmac

    from app.services.attendance_tokens import _server_secret

    payload_bytes = payload.encode()
    payload_b64 = _b64encode(payload_bytes)
    sig = hmac.new(_server_secret(), payload_bytes, hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)
    token = f"{payload_b64}.{sig_b64}"

    with pytest.raises(AttendanceTokenInvalid, match="Token purpose mismatch"):
        verify_token(token, sample_attendance, now=fixed_now)

    # 2. Event Mismatch
    payload.purpose = TOKEN_PURPOSE
    payload.event_id = uuid.uuid4()
    payload_bytes = payload.encode()
    payload_b64 = _b64encode(payload_bytes)
    sig = hmac.new(_server_secret(), payload_bytes, hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)
    token = f"{payload_b64}.{sig_b64}"

    with pytest.raises(AttendanceTokenInvalid, match="Token event mismatch"):
        verify_token(token, sample_attendance, now=fixed_now)

    # 3. User Mismatch
    payload.event_id = sample_attendance.event_id
    payload.user_id = uuid.uuid4()
    payload_bytes = payload.encode()
    payload_b64 = _b64encode(payload_bytes)
    sig = hmac.new(_server_secret(), payload_bytes, hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)
    token = f"{payload_b64}.{sig_b64}"

    with pytest.raises(AttendanceTokenInvalid, match="Token user mismatch"):
        verify_token(token, sample_attendance, now=fixed_now)


def test_verify_token_missing_expected_hmac(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    token = issue_token(sample_attendance, now=fixed_now, ttl_seconds=300)

    # Clear qr_hmac
    sample_attendance.qr_hmac = None
    with pytest.raises(
        AttendanceTokenInvalid, match="Attendance record missing secret signature"
    ):
        verify_token(token, sample_attendance, now=fixed_now)


def test_verify_token_secret_not_active(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    token = issue_token(sample_attendance, now=fixed_now, ttl_seconds=300)

    # Change the qr_secret and qr_hmac to represent a new active secret
    sample_attendance.qr_secret = "new_secret"  # pragma: allowlist secret
    sample_attendance.qr_hmac = compute_secret_hmac("new_secret")

    with pytest.raises(AttendanceTokenInvalid, match="Token secret is not active"):
        verify_token(token, sample_attendance, now=fixed_now)


def test_verify_token_expired(sample_attendance, fixed_now):
    ensure_secret_material(sample_attendance)
    token = issue_token(sample_attendance, now=fixed_now, ttl_seconds=300)

    # Exceed the expiration time + grace window (grace window is another 300 seconds, total 600)
    # The quantised issued_at for fixed_now (timestamp 1767268815) with TTL 300 is:
    # 1767268815 - (1767268815 % 300) = 1767268800.
    # expires_at = 1767268800 + 300 = 1767269100.
    # grace window expires at = 1767269100 + 300 = 1767269400.
    # So it expires at timestamp >= 1767269400.
    # Let's verify at timestamp 1767269400.
    expired_time = datetime.datetime.fromtimestamp(1767269400, datetime.UTC)
    with pytest.raises(AttendanceTokenExpired, match="Token has expired"):
        verify_token(token, sample_attendance, now=expired_time)

    # Within grace window should pass (timestamp 1767269399)
    grace_time = datetime.datetime.fromtimestamp(1767269399, datetime.UTC)
    payload = verify_token(token, sample_attendance, now=grace_time)
    assert payload.user_id == sample_attendance.user_id
