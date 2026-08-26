"""Unit tests for session fingerprinting module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.auth.fingerprint import (
    SessionFingerprint,
    SuspiciousActivityDetector,
    SuspiciousActivityEvent,
    _compute_fingerprint_hash,
    _get_client_ip,
    extract_fingerprint,
    get_suspicious_activity_detector,
)


class TestSessionFingerprint:
    """Tests for SessionFingerprint dataclass."""

    def test_matches_identical(self):
        fp1 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        fp2 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        assert fp1.matches(fp2)

    def test_matches_different_hash(self):
        fp1 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        fp2 = SessionFingerprint(
            user_agent="Firefox/119",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="def456",
        )
        assert not fp1.matches(fp2)

    def test_partially_matches_all_same(self):
        fp1 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        fp2 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        is_suspicious, mismatches = fp1.partially_matches(fp2)
        assert not is_suspicious
        assert mismatches == []

    def test_partially_matches_user_agent_change_is_suspicious(self):
        fp1 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        fp2 = SessionFingerprint(
            user_agent="Firefox/119",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="def456",
        )
        is_suspicious, mismatches = fp1.partially_matches(fp2)
        assert is_suspicious
        assert "user_agent" in mismatches

    def test_partially_matches_ip_change_not_suspicious(self):
        fp1 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        fp2 = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="10.0.0.1",
            fingerprint_hash="abc123",
        )
        is_suspicious, mismatches = fp1.partially_matches(fp2)
        assert not is_suspicious
        assert "ip_address" in mismatches

    def test_to_dict(self):
        fp = SessionFingerprint(
            user_agent="Chrome/120",
            accept_language="en-US",
            ip_address="192.168.1.1",
            fingerprint_hash="abc123",
        )
        result = fp.to_dict()
        assert result["user_agent"] == "Chrome/120"
        assert result["accept_language"] == "en-US"
        assert result["ip_address"] == "192.168.1.1"
        assert result["fingerprint_hash"] == "abc123"

    def test_from_dict(self):
        data = {
            "user_agent": "Chrome/120",
            "accept_language": "en-US",
            "ip_address": "192.168.1.1",
            "fingerprint_hash": "abc123",
        }
        fp = SessionFingerprint.from_dict(data)
        assert fp.user_agent == "Chrome/120"
        assert fp.accept_language == "en-US"
        assert fp.ip_address == "192.168.1.1"
        assert fp.fingerprint_hash == "abc123"

    def test_from_dict_missing_fields(self):
        data = {}
        fp = SessionFingerprint.from_dict(data)
        assert fp.user_agent == ""
        assert fp.accept_language == ""
        assert fp.ip_address == ""
        assert fp.fingerprint_hash == ""


class TestGetClientIp:
    """Tests for _get_client_ip function."""

    def test_x_forwarded_for_is_ignored(self):
        """X-Forwarded-For must NOT be read directly.

        ProxyHeadersMiddleware rewrites request.client.host before
        _get_client_ip runs.  Reading XFF here would allow spoofing.
        (RZ-1b: audit 2026-02-24)
        """
        request = MagicMock()
        request.headers.get.side_effect = lambda key, default="": {
            "x-forwarded-for": "attacker-injected, 5.6.7.8",
        }.get(key, default)
        request.client.host = "10.0.0.1"  # Real IP set by ProxyHeadersMiddleware

        result = _get_client_ip(request)
        # Must return the value from client.host, NOT from the XFF header.
        assert result == "10.0.0.1"

    def test_x_real_ip_is_ignored(self):
        """X-Real-IP must NOT be read directly for the same reason as XFF.

        After ProxyHeadersMiddleware runs, client.host already holds the
        correct client IP.  Trusting X-Real-IP here allows spoofing.
        (RZ-1b: audit 2026-02-24)
        """
        request = MagicMock()
        request.headers.get.side_effect = lambda key, default="": {
            "x-real-ip": "attacker-injected",
        }.get(key, default)
        request.client.host = "10.0.0.2"

        result = _get_client_ip(request)
        assert result == "10.0.0.2"

    def test_direct_connection(self):
        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "127.0.0.1"

        result = _get_client_ip(request)
        assert result == "127.0.0.1"

    def test_no_client(self):
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None

        result = _get_client_ip(request)
        assert result == "unknown"


class TestComputeFingerprintHash:
    """Tests for _compute_fingerprint_hash function."""

    def test_consistent_hash(self):
        hash1 = _compute_fingerprint_hash("Chrome", "en-US", "1.2.3.4")
        hash2 = _compute_fingerprint_hash("Chrome", "en-US", "1.2.3.4")
        assert hash1 == hash2

    def test_different_user_agent_different_hash(self):
        hash1 = _compute_fingerprint_hash("Chrome", "en-US", "1.2.3.4")
        hash2 = _compute_fingerprint_hash("Firefox", "en-US", "1.2.3.4")
        assert hash1 != hash2

    def test_ip_not_included_in_hash(self):
        hash1 = _compute_fingerprint_hash("Chrome", "en-US", "1.2.3.4")
        hash2 = _compute_fingerprint_hash("Chrome", "en-US", "5.6.7.8")
        assert hash1 == hash2  # IP should not affect hash

    def test_hash_is_32_chars(self):
        result = _compute_fingerprint_hash("Chrome", "en-US", "1.2.3.4")
        assert len(result) == 32


class TestExtractFingerprint:
    """Tests for extract_fingerprint function."""

    def test_extracts_from_request(self):
        request = MagicMock()
        request.headers.get.side_effect = lambda key, default="": {
            "user-agent": "Mozilla/5.0 Chrome/120",
            "accept-language": "en-US,en;q=0.9",
        }.get(key, default)
        request.client.host = "192.168.1.1"

        fp = extract_fingerprint(request)

        assert fp.user_agent == "Mozilla/5.0 Chrome/120"
        assert fp.accept_language == "en"
        assert fp.ip_address == "192.168.1.1"
        assert len(fp.fingerprint_hash) == 32

    def test_normalizes_browser_language_variant(self):
        request = MagicMock()
        request.headers = {
            "user-agent": "Chrome",
            "accept-language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        request.client.host = "192.0.2.1"

        assert extract_fingerprint(request).accept_language == "ru"


class TestSuspiciousActivityEvent:
    """Tests for SuspiciousActivityEvent."""

    def test_to_log_record(self):
        user_uuid = uuid.UUID("00000000-0000-0000-0000-000000000042")
        session_uuid = uuid.UUID("00000000-0000-0000-0000-000000000100")
        event = SuspiciousActivityEvent(
            user_id=user_uuid,
            session_id=session_uuid,
            event_type="fingerprint_mismatch",
            details={"mismatched_fields": ["user_agent"]},
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            severity="high",
        )

        record = event.to_log_record()

        assert record["event"] == "suspicious_activity"
        assert record["user_id"] == user_uuid
        assert record["session_id"] == session_uuid
        assert record["event_type"] == "fingerprint_mismatch"
        assert record["severity"] == "high"
        assert record["mismatched_fields"] == ["user_agent"]


class TestSuspiciousActivityDetector:
    """Tests for SuspiciousActivityDetector class."""

    def _uid(self, n: int = 1) -> uuid.UUID:
        """Generate a deterministic test UUID."""
        return uuid.UUID(f"00000000-0000-0000-0000-{n:012d}")

    def test_check_fingerprint_mismatch_no_mismatch(self):
        detector = SuspiciousActivityDetector()
        fp = SessionFingerprint(
            user_agent="Chrome",
            accept_language="en",
            ip_address="1.2.3.4",
            fingerprint_hash="abc",
        )

        result = detector.check_fingerprint_mismatch(self._uid(1), self._uid(1), fp, fp)
        assert result is None

    def test_check_fingerprint_mismatch_user_agent_change(self):
        detector = SuspiciousActivityDetector()
        fp1 = SessionFingerprint(
            user_agent="Chrome",
            accept_language="en",
            ip_address="1.2.3.4",
            fingerprint_hash="abc",
        )
        fp2 = SessionFingerprint(
            user_agent="Firefox",
            accept_language="en",
            ip_address="1.2.3.4",
            fingerprint_hash="def",
        )

        result = detector.check_fingerprint_mismatch(
            self._uid(1), self._uid(1), fp1, fp2
        )

        assert result is not None
        assert result.severity == "high"
        assert result.event_type == "fingerprint_mismatch"

    def test_check_rapid_location_change_same_ip(self):
        detector = SuspiciousActivityDetector()

        result = detector.check_rapid_location_change(
            user_id=self._uid(1),
            session_id=self._uid(1),
            previous_ip="1.2.3.4",
            current_ip="1.2.3.4",
            time_elapsed_seconds=10,
        )
        assert result is None

    def test_check_rapid_location_change_slow_change(self):
        detector = SuspiciousActivityDetector()

        result = detector.check_rapid_location_change(
            user_id=self._uid(1),
            session_id=self._uid(1),
            previous_ip="1.2.3.4",
            current_ip="5.6.7.8",
            time_elapsed_seconds=120,  # More than 60 seconds
        )
        assert result is None

    def test_check_rapid_location_change_detected(self):
        detector = SuspiciousActivityDetector()

        result = detector.check_rapid_location_change(
            user_id=self._uid(1),
            session_id=self._uid(1),
            previous_ip="1.2.3.4",
            current_ip="5.6.7.8",
            time_elapsed_seconds=30,  # Less than 60 seconds
        )

        assert result is not None
        assert result.event_type == "rapid_ip_change"
        assert result.severity == "medium"

    def test_get_recent_events(self):
        detector = SuspiciousActivityDetector()
        fp1 = SessionFingerprint("A", "en", "1.1.1.1", "h1")
        fp2 = SessionFingerprint("B", "en", "1.1.1.1", "h2")
        uid1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        uid2 = uuid.UUID("00000000-0000-0000-0000-000000000002")

        detector.check_fingerprint_mismatch(uid1, uid1, fp1, fp2)
        detector.check_rapid_location_change(uid2, uid2, "1.1.1.1", "2.2.2.2", 10)

        all_events = detector.get_recent_events()
        assert len(all_events) == 2

        user_1_events = detector.get_recent_events(user_id=uid1)
        assert len(user_1_events) == 1

    def test_get_recent_events_limit(self):
        detector = SuspiciousActivityDetector()
        fp1 = SessionFingerprint("A", "en", "1.1.1.1", "h1")
        fp2 = SessionFingerprint("B", "en", "1.1.1.1", "h2")

        for i in range(10):
            uid = uuid.UUID(f"00000000-0000-0000-0000-{i:012d}")
            detector.check_fingerprint_mismatch(uid, uid, fp1, fp2)

        events = detector.get_recent_events(limit=5)
        assert len(events) == 5


class TestGlobalDetector:
    """Tests for get_suspicious_activity_detector function."""

    def test_returns_same_instance(self):
        detector1 = get_suspicious_activity_detector()
        detector2 = get_suspicious_activity_detector()
        assert detector1 is detector2
