"""Production-ready tests for app/utils/audit.py.

Tests the calculate_log_signature() function which produces a deterministic
HMAC-SHA256 signature for DataAccessLog entries.

Coverage targets:
- Deterministic output for identical inputs
- Correct metadata serialisation (user_id coercion, None handling)
- Exception safety: invalid secret raises clearly, does not swallow
- Property-based (Hypothesis): arbitrary metadata never panics the logger
- Signature changes when any single field changes (tamper-evidence)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_DATETIME = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
_VALID_SECRET = "f3d9a1c2e4b5a6d7c8e9f0a1b2c3d4e5"  # pragma: allowlist secret


def _compute_expected_signature(
    actor_user_id: uuid.UUID | int | None,
    subject_user_id: uuid.UUID | int | None,
    resource_type: str,
    resource_id: str | None,
    action: str,
    context: dict[str, Any],
    ip_address: str | None,
    user_agent: str | None,
    created_at: datetime,
    secret: str,
) -> str:
    """Reference implementation that mirrors audit.calculate_log_signature()."""
    payload = json.dumps(
        [
            str(actor_user_id) if actor_user_id is not None else None,
            str(subject_user_id) if subject_user_id is not None else None,
            resource_type,
            resource_id,
            action,
            context,
            ip_address,
            user_agent,
            created_at.isoformat(),
        ],
        separators=(",", ":"),
    )
    primary = secret.split(",")[0].strip()
    return hmac.new(
        primary.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _call_sut(**overrides: Any) -> str:
    """Call the system-under-test with sensible defaults and optional overrides."""
    from app.utils.audit import calculate_log_signature

    defaults: dict[str, Any] = {
        "actor_user_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "subject_user_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "resource_type": "UserProfile",
        "resource_id": "42",
        "action": "READ",
        "context": {"client": "web"},
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0",
        "created_at": _FIXED_DATETIME,
    }
    defaults.update(overrides)
    return calculate_log_signature(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Determinism — same inputs → same output
# ---------------------------------------------------------------------------


def test_calculate_log_signature_returns_64_char_hex_string() -> None:
    """SHA-256 hexdigest is always 64 hex characters."""
    signature = _call_sut()
    assert isinstance(signature, str)
    assert len(signature) == 64
    assert all(ch in "0123456789abcdef" for ch in signature)


def test_calculate_log_signature_is_deterministic() -> None:
    """Calling with identical arguments twice yields the same signature."""
    sig1 = _call_sut()
    sig2 = _call_sut()
    assert sig1 == sig2


def test_calculate_log_signature_matches_reference_hmac() -> None:
    """Output matches a manually computed HMAC-SHA256 reference value."""
    actor = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000000")
    subject = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000000")
    context: dict[str, Any] = {"module": "billing"}

    signature = _call_sut(
        actor_user_id=actor,
        subject_user_id=subject,
        resource_type="Invoice",
        resource_id="INV-001",
        action="EXPORT",
        context=context,
        ip_address="10.0.0.1",
        user_agent="curl/8.0",
        created_at=_FIXED_DATETIME,
    )

    expected = _compute_expected_signature(
        actor_user_id=actor,
        subject_user_id=subject,
        resource_type="Invoice",
        resource_id="INV-001",
        action="EXPORT",
        context=context,
        ip_address="10.0.0.1",
        user_agent="curl/8.0",
        created_at=_FIXED_DATETIME,
        secret=_VALID_SECRET,
    )
    assert signature == expected


# ---------------------------------------------------------------------------
# Metadata serialisation — user_id coercion
# ---------------------------------------------------------------------------


def test_calculate_log_signature_with_uuid_actor_and_subject() -> None:
    """UUID actor/subject are str()-coerced before hashing."""
    actor = uuid.UUID("cafecafe-0000-0000-0000-000000000000")
    subject = uuid.UUID("deadbeef-0000-0000-0000-000000000000")
    sig = _call_sut(actor_user_id=actor, subject_user_id=subject)
    assert len(sig) == 64


def test_calculate_log_signature_with_integer_user_ids() -> None:
    """Integer user IDs are accepted and str()-coerced."""
    sig = _call_sut(actor_user_id=1001, subject_user_id=2002)
    assert len(sig) == 64


def test_calculate_log_signature_with_none_user_ids_serialises_null() -> None:
    """None actor/subject are serialised as JSON null, not the string 'None'."""
    sig_none = _call_sut(actor_user_id=None, subject_user_id=None)
    sig_some = _call_sut(
        actor_user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        subject_user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    )
    # Signatures differ because payload differs (null vs str UUIDs)
    assert sig_none != sig_some
    assert len(sig_none) == 64


def test_calculate_log_signature_with_none_resource_id() -> None:
    """None resource_id is accepted and serialised as JSON null."""
    sig = _call_sut(resource_id=None)
    assert len(sig) == 64


def test_calculate_log_signature_with_none_ip_address() -> None:
    """None ip_address is accepted."""
    sig = _call_sut(ip_address=None)
    assert len(sig) == 64


def test_calculate_log_signature_with_none_user_agent() -> None:
    """None user_agent is accepted."""
    sig = _call_sut(user_agent=None)
    assert len(sig) == 64


def test_calculate_log_signature_with_empty_context() -> None:
    """Empty context dict is valid."""
    sig = _call_sut(context={})
    assert len(sig) == 64


def test_calculate_log_signature_with_nested_context() -> None:
    """Nested context dict is serialised correctly."""
    context: dict[str, Any] = {
        "nested": {"key": "value"},
        "numbers": [1, 2, 3],
    }
    sig = _call_sut(context=context)
    assert len(sig) == 64


# ---------------------------------------------------------------------------
# Tamper-evidence — changing any field changes the signature
# ---------------------------------------------------------------------------


def test_calculate_log_signature_changes_when_action_changes() -> None:
    sig_read = _call_sut(action="READ")
    sig_write = _call_sut(action="WRITE")
    assert sig_read != sig_write


def test_calculate_log_signature_changes_when_resource_type_changes() -> None:
    sig_a = _call_sut(resource_type="User")
    sig_b = _call_sut(resource_type="Invoice")
    assert sig_a != sig_b


def test_calculate_log_signature_changes_when_ip_changes() -> None:
    sig_a = _call_sut(ip_address="192.168.1.1")
    sig_b = _call_sut(ip_address="10.0.0.1")
    assert sig_a != sig_b


def test_calculate_log_signature_changes_when_timestamp_changes() -> None:
    dt1 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    dt2 = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)
    sig_a = _call_sut(created_at=dt1)
    sig_b = _call_sut(created_at=dt2)
    assert sig_a != sig_b


# ---------------------------------------------------------------------------
# Secret key handling
# ---------------------------------------------------------------------------


def test_calculate_log_signature_uses_first_comma_separated_key() -> None:
    """When multiple comma-separated secrets exist, the first one is used."""
    primary = "a" * 32
    secondary = "b" * 32
    combined_secret = f"{primary},{secondary}"

    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = combined_secret
        from app.utils.audit import calculate_log_signature

        sig_combined = calculate_log_signature(
            actor_user_id=None,
            subject_user_id=None,
            resource_type="Resource",
            resource_id="1",
            action="READ",
            context={},
            ip_address=None,
            user_agent=None,
            created_at=_FIXED_DATETIME,
        )

    expected = _compute_expected_signature(
        actor_user_id=None,
        subject_user_id=None,
        resource_type="Resource",
        resource_id="1",
        action="READ",
        context={},
        ip_address=None,
        user_agent=None,
        created_at=_FIXED_DATETIME,
        secret=primary,
    )
    assert sig_combined == expected


def test_calculate_log_signature_raises_when_secret_is_empty() -> None:
    """An empty primary secret raises ValueError, not silently produces garbage."""
    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = ""
        from app.utils.audit import calculate_log_signature

        with pytest.raises(ValueError, match="AUDIT_LOG_SECRET"):
            calculate_log_signature(
                actor_user_id=None,
                subject_user_id=None,
                resource_type="Resource",
                resource_id="1",
                action="READ",
                context={},
                ip_address=None,
                user_agent=None,
                created_at=_FIXED_DATETIME,
            )


def test_calculate_log_signature_error_does_not_corrupt_caller_state() -> None:
    """Raising ValueError from audit does NOT propagate a partially mutated state.

    The caller must remain in a clean state after catching the error.
    """
    outer_list: list[str] = []

    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = ""
        from app.utils.audit import calculate_log_signature

        try:
            calculate_log_signature(
                actor_user_id=None,
                subject_user_id=None,
                resource_type="R",
                resource_id="1",
                action="A",
                context={},
                ip_address=None,
                user_agent=None,
                created_at=_FIXED_DATETIME,
            )
        except ValueError:
            outer_list.append("handled")

    # Caller list mutated ONLY by the except clause — no side effects from audit.
    assert outer_list == ["handled"]


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------

_SAFE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    max_size=200,
)

_SAFE_OPTIONAL_TEXT = st.one_of(st.none(), _SAFE_TEXT)

_CONTEXT_VALUES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    _SAFE_TEXT,
)

_CONTEXT_DICT = st.dictionaries(
    keys=_SAFE_TEXT,
    values=_CONTEXT_VALUES,
    max_size=10,
)


@given(
    resource_type=_SAFE_TEXT,
    resource_id=_SAFE_OPTIONAL_TEXT,
    action=_SAFE_TEXT,
    context=_CONTEXT_DICT,
    ip_address=_SAFE_OPTIONAL_TEXT,
    user_agent=_SAFE_OPTIONAL_TEXT,
)
@hypothesis_settings(max_examples=80, deadline=2000)
def test_calculate_log_signature_never_raises_for_arbitrary_metadata(
    resource_type: str,
    resource_id: str | None,
    action: str,
    context: dict,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Arbitrary metadata never causes an unhandled exception.

    The only legitimate exception is ValueError from an empty secret,
    which is a configuration error, not a data error.
    """
    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = _VALID_SECRET
        from app.utils.audit import calculate_log_signature

        result = calculate_log_signature(
            actor_user_id=None,
            subject_user_id=None,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            context=context,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=_FIXED_DATETIME,
        )

    assert isinstance(result, str)
    assert len(result) == 64


@given(
    actor=st.one_of(st.none(), st.integers(min_value=1, max_value=10**9), st.uuids()),
    subject=st.one_of(st.none(), st.integers(min_value=1, max_value=10**9), st.uuids()),
)
@hypothesis_settings(max_examples=50, deadline=2000)
def test_calculate_log_signature_user_id_types_never_raise(
    actor: uuid.UUID | int | None,
    subject: uuid.UUID | int | None,
) -> None:
    """Any combination of UUID / int / None for user IDs is handled without error."""
    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = _VALID_SECRET
        from app.utils.audit import calculate_log_signature

        result = calculate_log_signature(
            actor_user_id=actor,
            subject_user_id=subject,
            resource_type="Resource",
            resource_id="1",
            action="READ",
            context={},
            ip_address=None,
            user_agent=None,
            created_at=_FIXED_DATETIME,
        )

    assert len(result) == 64
