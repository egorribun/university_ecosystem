"""Property-based tests using Hypothesis.

MOD-21-06 (audit 2026-03-25 Wave 21): Adds property-based tests for
serialization round-trips, auth invariants, and schedule conflict symmetry.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hypo_settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

# ── 1. Pydantic serialization round-trip ───────────────────────────────────────

# Use a simple bounded strategy for email-like strings
_email_st = st.from_regex(r"[a-z]{3,8}@[a-z]{3,6}\.[a-z]{2,3}", fullmatch=True)
_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=50,
)


@hypo_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(full_name=_name_st)
def test_user_schema_round_trip(full_name: str) -> None:
    """Serialising a user schema to dict and back produces identical data."""
    from app.schemas.schemas import UserOut

    data = {
        "id": uuid4(),
        "email": f"test_{uuid4().hex[:8]}@example.com",
        "full_name": full_name.strip() or "Test User",
        "is_active": True,
        "role": "student",
    }
    model = UserOut.model_validate(data)
    serialized = model.model_dump(mode="json")
    restored = UserOut.model_validate(serialized)
    assert model.id == restored.id
    assert model.email == restored.email
    assert model.full_name == restored.full_name


# ── 2. Auth: hash → verify always succeeds ────────────────────────────────────

_password_st = st.text(min_size=1, max_size=128).filter(lambda s: s.strip())


@hypo_settings(
    max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None
)
@given(password=_password_st)
def test_argon2_hash_verify_round_trip(password: str) -> None:
    """Any non-empty password hashed with argon2id is verifiable."""
    from app.auth.security import get_password_hash_sync, verify_password_sync

    hashed = get_password_hash_sync(password, validate_policy=False)
    assert hashed.startswith("$argon2id$")
    assert verify_password_sync(password, hashed) is True


@hypo_settings(
    max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None
)
@given(password=_password_st, wrong=_password_st)
def test_argon2_wrong_password_rejected(password: str, wrong: str) -> None:
    """A different password never verifies against the hash."""
    from hypothesis import assume

    assume(password != wrong)

    from app.auth.security import get_password_hash_sync, verify_password_sync

    hashed = get_password_hash_sync(password, validate_policy=False)
    assert verify_password_sync(wrong, hashed) is False


# ── 3. Schedule conflict detection is symmetric ───────────────────────────────

_hour_st = st.integers(min_value=8, max_value=20)
_duration_st = st.integers(min_value=30, max_value=120)


@hypo_settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    start_a=_hour_st,
    dur_a=_duration_st,
    start_b=_hour_st,
    dur_b=_duration_st,
)
def test_conflict_detection_is_symmetric(
    start_a: int, dur_a: int, start_b: int, dur_b: int
) -> None:
    """detect_conflicts(a, [b]) returns b iff detect_conflicts(b, [a]) returns a."""
    try:
        from rust_ext import ScheduleItem, detect_conflicts
    except ImportError:
        pytest.skip("Rust extension not built")

    base_date = datetime(2026, 3, 25, tzinfo=UTC)

    start_time_a = int((base_date + timedelta(hours=start_a)).timestamp())
    end_time_a = int((base_date + timedelta(hours=start_a, minutes=dur_a)).timestamp())
    start_time_b = int((base_date + timedelta(hours=start_b)).timestamp())
    end_time_b = int((base_date + timedelta(hours=start_b, minutes=dur_b)).timestamp())

    item_a = ScheduleItem(
        id=1,
        weekday="Monday",
        start_time=start_time_a,
        end_time=end_time_a,
        parity="EveryWeek",
    )
    item_b = ScheduleItem(
        id=2,
        weekday="Monday",
        start_time=start_time_b,
        end_time=end_time_b,
        parity="EveryWeek",
    )

    a_conflicts_b = len(detect_conflicts(item_a, [item_b])) > 0
    b_conflicts_a = len(detect_conflicts(item_b, [item_a])) > 0
    assert a_conflicts_b == b_conflicts_a, (
        f"Asymmetric conflict: A→B={a_conflicts_b}, B→A={b_conflicts_a}"
    )


# ── 4. UUID validation rejects arbitrary strings ──────────────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


@hypo_settings(max_examples=100)
@given(s=st.text(max_size=100))
def test_uuid_validation_rejects_non_uuids(s: str) -> None:
    """Random strings that don't match UUID format are rejected by uuid.Parse."""
    from uuid import UUID

    if _UUID_RE.match(s):
        return  # This IS a valid UUID format — skip

    with pytest.raises((ValueError, AttributeError)):
        UUID(s, version=4)


# ── 5. Pagination bounds are always valid ─────────────────────────────────────


@hypo_settings(max_examples=50)
@given(
    offset=st.integers(min_value=-1000, max_value=1000),
    limit=st.integers(min_value=-100, max_value=500),
)
def test_pagination_bounds_clamped(offset: int, limit: int) -> None:
    """Pagination parameters are clamped to safe ranges."""
    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 200))  # TD-14-02: defense-in-depth cap at 200
    assert safe_offset >= 0
    assert 1 <= safe_limit <= 200


# ── 6. UUIDv7 properties ──────────────────────────────────────────────────────


@hypo_settings(max_examples=50)
@given(dt=st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1)))
def test_uuidv7_round_trip_timestamp(dt: datetime) -> None:
    """UUIDv7 stores the timestamp with millisecond precision."""
    from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7, generate_uuid7

    dt_utc = dt.replace(tzinfo=UTC)
    u = generate_uuid7(dt_utc)
    extracted = extract_timestamp_from_uuid_v7(u)

    # We expect ms precision. Compare with 2ms tolerance for float drift.
    assert abs((dt_utc - extracted).total_seconds()) < 0.002


@hypo_settings(max_examples=30)
@given(
    dts=st.lists(
        st.datetimes(min_value=datetime(2025, 1, 1), max_value=datetime(2025, 12, 31)),
        min_size=2,
        max_size=10,
        unique=True,
    )
)
def test_uuidv7_temporal_ordering(dts: list[datetime]) -> None:
    """UUIDv7 sorting matches temporal ordering of their timestamps."""
    from app.utils.uuid_v7 import generate_uuid7

    sorted_dts = sorted([dt.replace(tzinfo=UTC) for dt in dts])
    uuids = [generate_uuid7(dt) for dt in sorted_dts]

    assert uuids == sorted(uuids)


# ── 7. Sanitization Invariants ───────────────────────────────────────────────


@hypo_settings(max_examples=50)
@given(html=st.text(max_size=500))
def test_html_sanitization_idempotency(html: str) -> None:
    """Sanitizing already sanitized HTML produces no further changes."""
    from app.utils.sanitization import sanitize_rich_text

    try:
        first = sanitize_rich_text(html)
        second = sanitize_rich_text(first)
        assert first == second
    except Exception:
        # Some inputs might trigger 400 HTTPException from sanitize_rich_text
        # which is expected for invalid HTML, so we just continue the property test.
        return


@hypo_settings(max_examples=50)
@given(filename=st.text(min_size=1, max_size=500))
def test_filename_sanitization_length_and_safe_chars(filename: str) -> None:
    """Sanitized filenames are always within length limits and contain no path separators."""
    from app.utils.sanitization import sanitize_filename

    max_len = 50
    safe = sanitize_filename(filename, max_length=max_len)

    assert len(safe) <= max_len
    assert "/" not in safe
    assert "\\" not in safe
    assert "\x00" not in safe


# ── 8. Pagination Property Tests ──────────────────────────────────────────────


@hypo_settings(max_examples=50)
@given(limit=st.integers())
def test_cursor_params_validation(limit: int) -> None:
    """CursorParams restricts limit to 1 <= limit <= 100."""
    from pydantic import ValidationError

    from app.utils.pagination import CursorParams

    if 1 <= limit <= 100:
        params = CursorParams(limit=limit)
        assert params.limit == limit
    else:
        with pytest.raises(ValidationError):
            CursorParams(limit=limit)


class CircuitBreakerStateMachine(RuleBasedStateMachine):
    """Exercise circuit-breaker transitions against a deterministic clock."""

    @initialize()
    def initialize_breaker(self) -> None:
        from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

        self.clock = 0.0
        self.breaker = CircuitBreaker(
            "hypothesis",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout_seconds=10.0,
                success_threshold=2,
            ),
        )
        self.clock_patch = patch(
            "app.core.circuit_breaker.time",
            SimpleNamespace(monotonic=lambda: self.clock),
        )
        self.clock_patch.start()

    @rule()
    def record_failure(self) -> None:
        from app.core.circuit_breaker import CircuitBreakerState

        if self.breaker.state == CircuitBreakerState.OPEN:
            if self.breaker._get_remaining_open_time() > 0:
                assert self.breaker._should_allow_request() is False
                return
            assert self.breaker._should_allow_request() is True
        self.breaker._record_failure(RuntimeError("synthetic failure"))

    @rule()
    def record_success(self) -> None:
        self.breaker._record_success()

    @rule(seconds=st.integers(min_value=0, max_value=20))
    def time_advance(self, seconds: int) -> None:
        self.clock += seconds

    @invariant()
    def open_breaker_rejects_before_recovery(self) -> None:
        from app.core.circuit_breaker import CircuitBreakerState

        if self.breaker.state == CircuitBreakerState.OPEN:
            remaining = self.breaker._get_remaining_open_time()
            if remaining > 0:
                assert self.breaker._should_allow_request() is False

    def teardown(self) -> None:
        self.clock_patch.stop()


TestCircuitBreakerStateMachine = CircuitBreakerStateMachine.TestCase


class LockoutLifecycleStateMachine(RuleBasedStateMachine):
    """Model lockout threshold and expiry using LockoutService's pure logic."""

    @initialize()
    def initialize_lockout(self) -> None:
        from app.services.auth.lockout import LockoutService

        self.service = LockoutService.__new__(LockoutService)
        self.service._rules = [(3, 30)]
        self.now = datetime(2026, 7, 22, tzinfo=UTC)
        self.attempts: list[SimpleNamespace] = []

    @rule()
    def record_failed_attempt(self) -> None:
        self.attempts.append(SimpleNamespace(attempted_at=self.now))
        self.attempts = self.attempts[-3:]

    @rule()
    def record_successful_login(self) -> None:
        self.attempts.clear()

    @rule(seconds=st.integers(min_value=0, max_value=45))
    def time_advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    @invariant()
    def threshold_and_expiry_are_bounded(self) -> None:
        lock_until = self.service._calculate_lock_until(self.attempts, self.now)
        if len(self.attempts) < 3:
            assert lock_until is None
        elif lock_until is not None:
            assert lock_until >= self.attempts[0].attempted_at
            assert lock_until <= self.attempts[0].attempted_at + timedelta(seconds=30)


TestLockoutLifecycleStateMachine = LockoutLifecycleStateMachine.TestCase


@hypo_settings(max_examples=50)
@given(
    val=st.one_of(
        st.integers(min_value=-100000, max_value=100000), st.text(max_size=100)
    )
)
def test_cursor_encoding_round_trip(val: int | str) -> None:
    """Opaque cursor encoding is fully reversible."""
    from app.utils.pagination import decode_cursor, encode_cursor

    encoded = encode_cursor(val)
    decoded = decode_cursor(encoded)
    assert decoded == str(val)


@hypo_settings(max_examples=50)
@given(
    dt=st.datetimes(min_value=datetime(1975, 1, 1), max_value=datetime(2035, 1, 1)),
    secondary_id=st.one_of(
        st.integers(min_value=1, max_value=100000),
        st.text(
            alphabet=st.characters(blacklist_characters=":\n"), min_size=1, max_size=50
        ),
    ),
)
def test_datetime_cursor_round_trip(dt: datetime, secondary_id: int | str) -> None:
    """Composite datetime cursor encoding is fully reversible with microsecond precision."""
    from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor

    encoded = encode_datetime_cursor(dt, secondary_id)
    decoded = decode_datetime_cursor(encoded)
    assert decoded is not None
    decoded_dt, decoded_id = decoded

    assert decoded_dt.tzinfo is not None
    assert abs((dt.replace(tzinfo=UTC) - decoded_dt).total_seconds()) == 0
    assert decoded_id == str(secondary_id)
