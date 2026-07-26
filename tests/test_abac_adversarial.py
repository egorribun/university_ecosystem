"""Adversarial and Edge Case Stress Tests for Context-Aware Access Guard (ABAC + ReBAC)."""

import ipaddress
import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.auth.abac import (
    ContextAwareAccessGuard,
    _check_ip_in_subnets,
    _check_schedule_window,
    _parse_subnets,
    _to_utc,
)
from app.core.config import settings


class DummyLesson:
    """Dummy lesson model for schedule testing."""

    def __init__(
        self,
        start_time: datetime,
        end_time: datetime,
        lesson_id: uuid.UUID | str | None = None,
    ):
        self.id = lesson_id or uuid.uuid4()
        self.start_time = start_time
        self.end_time = end_time


@pytest.fixture
def mock_request():
    """Create a mock Request with configurable client IP and headers."""
    req = MagicMock()
    req.client.host = "192.168.1.50"
    req.headers.get = lambda h, d=None: None
    return req


@pytest.fixture
def mock_permission_checker():
    """Create a mock PermissionChecker returning True."""
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    return checker


# ============================================================================
# 1. IP Subnet & Address Edge Cases (IPv6, Dual-Stack, 0.0.0.0/0, Invalid IPs)
# ============================================================================


def test_check_ip_in_subnets_ipv6_valid():
    """IPv6 client IP matching IPv6 subnet."""
    assert _check_ip_in_subnets("2001:db8::1", ["2001:db8::/32"]) is True
    assert _check_ip_in_subnets("2001:db8:ffff::1", ["2001:db8::/32"]) is True
    assert _check_ip_in_subnets("2001:db9::1", ["2001:db8::/32"]) is False


def test_check_ip_in_subnets_ipv6_client_with_ipv4_subnet():
    """EMPIRICAL TEST: IPv6 client IP evaluated against IPv4-only campus subnets."""
    try:
        result = _check_ip_in_subnets("2001:db8::1", ["192.168.0.0/16"])
        assert result is False
    except TypeError as exc:
        pytest.fail(
            f"UNHANDLED BUG: _check_ip_in_subnets raised TypeError on IPv6 client vs IPv4 subnet: {exc}"
        )


def test_check_ip_in_subnets_ipv4_client_with_ipv6_subnet():
    """EMPIRICAL TEST: IPv4 client IP evaluated against IPv6-only campus subnets."""
    try:
        result = _check_ip_in_subnets("192.168.1.50", ["2001:db8::/32"])
        assert result is False
    except TypeError as exc:
        pytest.fail(
            f"UNHANDLED BUG: _check_ip_in_subnets raised TypeError on IPv4 client vs IPv6 subnet: {exc}"
        )


def test_check_ip_in_subnets_dual_stack_subnets():
    """Campus subnets configured with both IPv4 and IPv6 CIDRs."""
    subnets = ["192.168.0.0/16", "2001:db8::/32"]

    assert _check_ip_in_subnets("192.168.1.50", subnets) is True
    assert _check_ip_in_subnets("2001:db8::100", subnets) is True

    assert _check_ip_in_subnets("10.0.0.1", subnets) is False
    assert _check_ip_in_subnets("2001:db9::1", subnets) is False


def test_check_ip_in_subnets_wildcard_subnets():
    """Test 0.0.0.0/0 and ::/0 wildcard subnets."""
    assert _check_ip_in_subnets("1.2.3.4", ["0.0.0.0/0"]) is True

    try:
        result_v6 = _check_ip_in_subnets("2001:db8::1", ["0.0.0.0/0"])
        assert result_v6 is False
    except TypeError as exc:
        pytest.fail(
            f"UNHANDLED BUG: _check_ip_in_subnets raised TypeError on IPv6 client vs 0.0.0.0/0: {exc}"
        )

    assert _check_ip_in_subnets("2001:db8::1", ["::/0"]) is True

    assert _check_ip_in_subnets("1.2.3.4", ["0.0.0.0/0", "::/0"]) is True
    assert _check_ip_in_subnets("2001:db8::1", ["0.0.0.0/0", "::/0"]) is True


def test_check_ip_in_subnets_invalid_ip_strings():
    """Test malformed, injected, or invalid IP strings."""
    subnets = ["192.168.0.0/16"]

    assert _check_ip_in_subnets("invalid_ip", subnets) is False
    assert _check_ip_in_subnets("256.256.256.256", subnets) is False
    assert _check_ip_in_subnets("", subnets) is False
    assert _check_ip_in_subnets("   ", subnets) is False
    assert _check_ip_in_subnets("192.168.1.1/24", subnets) is False
    assert _check_ip_in_subnets("192.168.1.1:8080", subnets) is False
    assert _check_ip_in_subnets("<script>alert(1)</script>", subnets) is False


def test_parse_subnets_invalid_cidrs():
    """Verify behavior when subnet list contains invalid CIDR entries."""
    parsed = _parse_subnets(["192.168.0.0/16", "invalid-cidr", "2001:db8::/32"])
    assert len(parsed) == 2
    assert ipaddress.ip_network("192.168.0.0/16") in parsed
    assert ipaddress.ip_network("2001:db8::/32") in parsed

    parsed_str = _parse_subnets("192.168.0.0/16, invalid-cidr, 10.0.0.0/8")
    assert len(parsed_str) == 2


# ============================================================================
# 2. Schedule Time Window Edge Cases (Zero/Negative Grace, Microseconds, Timezones)
# ============================================================================


def test_check_schedule_window_zero_grace():
    """Grace period of 0 minutes."""
    now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)
    start = datetime(2026, 7, 25, 11, 0, 0, tzinfo=UTC)
    end = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)

    assert _check_schedule_window(now, start, end, grace_minutes=0) is True

    now_after = datetime(2026, 7, 25, 12, 0, 1, tzinfo=UTC)
    assert _check_schedule_window(now_after, start, end, grace_minutes=0) is False


def test_check_schedule_window_negative_grace():
    """EMPIRICAL TEST: Negative grace minutes (e.g. -15)."""
    now = datetime(2026, 7, 25, 11, 30, 0, tzinfo=UTC)
    start = datetime(2026, 7, 25, 11, 0, 0, tzinfo=UTC)
    end = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)

    assert _check_schedule_window(now, start, end, grace_minutes=-15) is True

    now_late = datetime(2026, 7, 25, 11, 50, 0, tzinfo=UTC)
    assert _check_schedule_window(now_late, start, end, grace_minutes=-15) is False

    assert _check_schedule_window(now, start, end, grace_minutes=-90) is False


def test_check_schedule_window_microsecond_boundaries():
    """Exact microsecond boundaries for start_time and window_end."""
    start = datetime(2026, 7, 25, 10, 0, 0, 500000, tzinfo=UTC)
    end = datetime(2026, 7, 25, 11, 0, 0, 500000, tzinfo=UTC)
    grace = 15
    window_end = end + timedelta(minutes=grace)

    assert _check_schedule_window(start, start, end, grace) is True

    before_start = start - timedelta(microseconds=1)
    assert _check_schedule_window(before_start, start, end, grace) is False

    assert _check_schedule_window(window_end, start, end, grace) is True

    after_window_end = window_end + timedelta(microseconds=1)
    assert _check_schedule_window(after_window_end, start, end, grace) is False


def test_to_utc_timezone_conversions():
    """Verification of naive and non-UTC timezone conversions in _to_utc."""
    naive_dt = datetime(2026, 7, 25, 12, 0, 0)
    utc_from_naive = _to_utc(naive_dt)
    assert utc_from_naive.tzinfo == UTC
    assert utc_from_naive.hour == 12

    tz_plus_3 = timezone(timedelta(hours=3))
    dt_plus_3 = datetime(2026, 7, 25, 15, 0, 0, tzinfo=tz_plus_3)
    utc_from_tz = _to_utc(dt_plus_3)
    assert utc_from_tz.tzinfo == UTC
    assert utc_from_tz.hour == 12


# ============================================================================
# 3. Spoofed & Missing Headers Attack Verification
# ============================================================================


@pytest.mark.asyncio
async def test_spoofed_x_forwarded_for_from_untrusted_client(
    mock_request, mock_permission_checker, monkeypatch
):
    """ATTACK SCENARIO: Untrusted client directly sends X-Forwarded-For header containing campus IP."""
    monkeypatch.setattr(settings, "trusted_proxies_list", ["10.0.0.1"])

    mock_request.client.host = "203.0.113.1"
    mock_request.headers.get = lambda header, default=None: {
        "X-Forwarded-For": "192.168.1.50",
    }.get(header, default)

    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10), end_time=now + timedelta(minutes=50)
    )
    guard = ContextAwareAccessGuard(
        permission_checker=mock_permission_checker, campus_subnets=["192.168.0.0/16"]
    )

    with pytest.raises(HTTPException) as exc_info:
        await guard.check_control_work_access(
            request=mock_request,
            user_id=uuid.uuid4(),
            lesson=lesson,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_spoofed_first_ip_in_x_forwarded_for_chain_via_trusted_proxy(
    mock_request, mock_permission_checker, monkeypatch
):
    """ATTACK SCENARIO: Attacker sends X-Forwarded-For: 192.168.1.50 to ingress proxy (10.0.0.1)."""
    monkeypatch.setattr(settings, "trusted_proxies_list", ["10.0.0.1"])

    mock_request.client.host = "10.0.0.1"
    mock_request.headers.get = lambda header, default=None: {
        "X-Forwarded-For": "192.168.1.50, 203.0.113.1",
    }.get(header, default)

    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10), end_time=now + timedelta(minutes=50)
    )
    guard = ContextAwareAccessGuard(
        permission_checker=mock_permission_checker, campus_subnets=["192.168.0.0/16"]
    )

    try:
        await guard.check_control_work_access(
            request=mock_request,
            user_id=uuid.uuid4(),
            lesson=lesson,
        )
        pytest.fail(
            "SECURITY VULNERABILITY FOUND: resolve_client_ip accepted spoofed left-most X-Forwarded-For header from trusted proxy chain!"
        )
    except HTTPException as exc:
        assert exc.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_missing_client_object_in_request(mock_permission_checker):
    """Test request.client is None."""
    req = MagicMock()
    req.client = None
    req.headers.get = lambda h, d=None: None
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10), end_time=now + timedelta(minutes=50)
    )
    guard = ContextAwareAccessGuard(
        permission_checker=mock_permission_checker, campus_subnets=["192.168.0.0/16"]
    )

    with pytest.raises(HTTPException) as exc_info:
        await guard.check_control_work_access(
            request=req,
            user_id=uuid.uuid4(),
            lesson=lesson,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
