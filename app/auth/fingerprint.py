"""
Session fingerprinting for suspicious activity detection.

This module provides:
- Device fingerprint generation from request headers
- Fingerprint validation against stored session data
- Suspicious activity detection and logging
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionFingerprint:
    """Immutable fingerprint of a user session."""

    user_agent: str
    accept_language: str
    ip_address: str
    fingerprint_hash: str

    def matches(self, other: SessionFingerprint) -> bool:
        """Check if this fingerprint matches another."""
        return self.fingerprint_hash == other.fingerprint_hash

    def partially_matches(self, other: SessionFingerprint) -> tuple[bool, list[str]]:
        """
        Check for partial match and return mismatched fields.

        Returns (is_suspicious, list of mismatched field names)
        """
        mismatches: list[str] = []

        if self.user_agent != other.user_agent:
            mismatches.append("user_agent")

        if self.accept_language != other.accept_language:
            mismatches.append("accept_language")

        # IP address changes are common (mobile, VPN)
        # only flag if everything else matches

        if self.ip_address != other.ip_address:
            mismatches.append("ip_address")

        # Consider suspicious if user_agent changed
        # (most indicative of session hijacking)

        is_suspicious = "user_agent" in mismatches

        return is_suspicious, mismatches

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for storage."""
        return {
            "user_agent": self.user_agent,
            "accept_language": self.accept_language,
            "ip_address": self.ip_address,
            "fingerprint_hash": self.fingerprint_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionFingerprint:
        """Create from stored dictionary."""
        return cls(
            user_agent=data.get("user_agent", ""),
            accept_language=data.get("accept_language", ""),
            ip_address=data.get("ip_address", ""),
            fingerprint_hash=data.get("fingerprint_hash", ""),
        )


def _get_client_ip(request: Request) -> str:
    """Extract client IP from the request.

    ``ProxyHeadersMiddleware`` (configured in middleware.py) rewrites
    ``request.client.host`` to the true client IP using trusted-proxy-sourced
    forwarded headers **before** this function runs.  Reading
    ``X-Forwarded-For`` or ``X-Real-IP`` directly here would allow an
    attacker who can craft arbitrary headers to spoof their IP address and
    bypass IP-based rate limiting and fingerprinting.
    (RZ-1b: audit 2026-02-24)
    """
    if request.client:
        return request.client.host
    return "unknown"


def _compute_fingerprint_hash(
    user_agent: str,
    accept_language: str,
    ip_address: str,
) -> str:
    """Compute a hash of the fingerprint components."""
    # Include user_agent as primary identifier
    # Accept-Language as secondary (rarely changes)
    # Note: IP is stored but NOT included in hash (too volatile)
    content = f"{user_agent}|{accept_language}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def extract_fingerprint(request: Request) -> SessionFingerprint:
    """
    Extract session fingerprint from an HTTP request.

    The fingerprint captures device/browser characteristics that
    should remain stable within a session.
    """
    user_agent = request.headers.get("user-agent", "")[:500]  # Limit length
    accept_language = request.headers.get("accept-language", "")[:100]
    ip_address = _get_client_ip(request)

    fingerprint_hash = _compute_fingerprint_hash(
        user_agent=user_agent,
        accept_language=accept_language,
        ip_address=ip_address,
    )

    return SessionFingerprint(
        user_agent=user_agent,
        accept_language=accept_language,
        ip_address=ip_address,
        fingerprint_hash=fingerprint_hash,
    )


@dataclass
class SuspiciousActivityEvent:
    """Record of a suspicious activity detection."""

    user_id: int
    session_id: int
    event_type: str
    details: dict[str, Any]
    timestamp: datetime
    severity: str  # "low", "medium", "high"

    def to_log_record(self) -> dict[str, Any]:
        """Convert to a structured log record."""
        return {
            "event": "suspicious_activity",
            "user_id": self.user_id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            **self.details,
        }


class SuspiciousActivityDetector:
    """Detects and logs suspicious session activity.

    Events are stored in a bounded ring buffer (``deque(maxlen=_MAX_EVENTS)``)
    to prevent unbounded memory growth under sustained attack traffic.
    At 10 000 entries × ~600 bytes each the ceiling is ~6 MB.
    (RZ-1a: audit 2026-02-24)
    """

    _MAX_EVENTS: int = 10_000

    def __init__(self) -> None:
        from collections import deque
        self._events: deque[SuspiciousActivityEvent] = deque(maxlen=self._MAX_EVENTS)

    def check_fingerprint_mismatch(
        self,
        user_id: int,
        session_id: int,
        stored_fingerprint: SessionFingerprint,
        current_fingerprint: SessionFingerprint,
    ) -> SuspiciousActivityEvent | None:
        """
        Check if current fingerprint differs from stored one.

        Returns a SuspiciousActivityEvent if mismatch is significant.
        """
        if stored_fingerprint.matches(current_fingerprint):
            return None

        _is_suspicious, mismatches = stored_fingerprint.partially_matches(
            current_fingerprint
        )

        if not mismatches:
            return None

        # Determine severity
        if "user_agent" in mismatches:
            severity = "high"  # Most indicative of session hijacking
        elif len(mismatches) > 1:
            severity = "medium"
        else:
            severity = "low"

        event = SuspiciousActivityEvent(
            user_id=user_id,
            session_id=session_id,
            event_type="fingerprint_mismatch",
            details={
                "mismatched_fields": mismatches,
                "stored_hash": stored_fingerprint.fingerprint_hash,
                "current_hash": current_fingerprint.fingerprint_hash,
                "current_ip": current_fingerprint.ip_address,
            },
            timestamp=datetime.now(UTC),
            severity=severity,
        )

        # Log the event
        log_level = {
            "high": logging.WARNING,
            "medium": logging.INFO,
            "low": logging.DEBUG,
        }.get(severity, logging.INFO)

        logger.log(
            log_level, "Suspicious activity detected", extra=event.to_log_record()
        )

        self._events.append(event)

        return event

    def check_rapid_location_change(
        self,
        user_id: int,
        session_id: int,
        previous_ip: str,
        current_ip: str,
        time_elapsed_seconds: float,
    ) -> SuspiciousActivityEvent | None:
        """
        Check for impossibly fast location changes.

        This can indicate session hijacking if the IP changed drastically
        in a very short time.
        """
        if previous_ip == current_ip:
            return None

        # Only flag if change happened very quickly (< 60 seconds)
        if time_elapsed_seconds > 60:
            return None

        event = SuspiciousActivityEvent(
            user_id=user_id,
            session_id=session_id,
            event_type="rapid_ip_change",
            details={
                "previous_ip": previous_ip,
                "current_ip": current_ip,
                "elapsed_seconds": time_elapsed_seconds,
            },
            timestamp=datetime.now(UTC),
            severity="medium",
        )

        logger.info("Rapid IP change detected", extra=event.to_log_record())

        self._events.append(event)

        return event

    def get_recent_events(
        self,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[SuspiciousActivityEvent]:
        """Return up to *limit* most-recent suspicious activity events.

        ``deque`` does not support negative-index slicing, so we convert to
        a list first.  The deque is already bounded (maxlen=10_000) so this
        materialisation is O(min(limit, len(deque))) and safe.
        """
        # Take the last `limit` events from the ring buffer.
        events: list[SuspiciousActivityEvent] = list(self._events)[-limit:]
        if user_id is not None:
            events = [e for e in events if e.user_id == user_id]
        return events


# Global detector instance
_detector: SuspiciousActivityDetector | None = None


def get_suspicious_activity_detector() -> SuspiciousActivityDetector:
    """Get or create the global suspicious activity detector."""
    global _detector
    if _detector is None:
        _detector = SuspiciousActivityDetector()
    return _detector
