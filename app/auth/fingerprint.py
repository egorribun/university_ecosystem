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
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import Request

logger = get_logger(__name__)


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
    if request.client is not None:
        return str(request.client.host)
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


def _normalize_accept_language(value: str) -> str:
    """Return a stable primary locale for session fingerprinting.

    Browsers send a locale preference list while the API client deliberately
    sends the selected application locale. Treat region and quality variants
    of the same language as one device characteristic so legitimate SSR and
    browser API requests share a fingerprint.
    """
    primary = value.split(",", 1)[0].split(";", 1)[0].strip().lower()
    return primary.split("-", 1)[0]


def extract_fingerprint(request: Request) -> SessionFingerprint:
    """
    Extract session fingerprint from an HTTP request.

    The fingerprint captures device/browser characteristics that
    should remain stable within a session.
    """
    user_agent = request.headers.get("user-agent", "")[:500]  # Limit length
    accept_language = _normalize_accept_language(
        request.headers.get("accept-language", "")[:100]
    )
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

    # RZ-006 (audit 2026-03-10): user_id and session_id are UUID in all models.
    # The previous `int` annotation caused TypeError at runtime when real UUIDs
    # were passed, silently disabling the entire fingerprint detection system.
    user_id: uuid.UUID
    session_id: uuid.UUID
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

    RZ-004 (audit 2026-03-10): A per-user index (defaultdict of lists) provides
    O(1) lookup by user_id in get_recent_events(), eliminating the timing oracle
    where filtering 10 000 events was measurably slower for active users than
    for non-existent ones, enabling user enumeration via response timing.
    """

    _MAX_EVENTS: int = 10_000

    def __init__(self) -> None:
        from collections import deque

        self._events: deque[SuspiciousActivityEvent] = deque(maxlen=self._MAX_EVENTS)
        # Per-user index: user_id → list of their events (unbounded per user,
        # but total is capped by the ring buffer eviction logic below).
        self._user_index: dict[uuid.UUID, list[SuspiciousActivityEvent]] = defaultdict(
            list
        )
        self._lock = threading.Lock()

    def check_fingerprint_mismatch(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
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

        with self._lock:
            # MED-W19: Remove stale _user_index entry for the event being evicted
            # from the ring buffer before appending the new one.  When deque is at
            # capacity, appendleft evicts the oldest event; we must mirror that
            # removal in the per-user index to prevent unbounded index growth.
            if len(self._events) == self._MAX_EVENTS:
                evicted = self._events[0]
                uid = evicted.user_id
                user_list = self._user_index.get(uid)
                if user_list:
                    try:
                        user_list.remove(evicted)
                    except ValueError:
                        pass
                    if not user_list:
                        del self._user_index[uid]
            self._events.append(event)
            self._user_index[user_id].append(event)

        return event

    def check_rapid_location_change(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
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

        with self._lock:
            # MED-W19: Mirror ring-buffer eviction in _user_index (check_rapid_location_change).
            if len(self._events) == self._MAX_EVENTS:
                evicted = self._events[0]
                uid = evicted.user_id
                user_list = self._user_index.get(uid)
                if user_list:
                    try:
                        user_list.remove(evicted)
                    except ValueError:
                        pass
                    if not user_list:
                        del self._user_index[uid]
            self._events.append(event)
            self._user_index[user_id].append(event)

        return event

    def get_recent_events(
        self,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[SuspiciousActivityEvent]:
        """Return up to *limit* most-recent suspicious activity events.

        RZ-004 (audit 2026-03-10): When ``user_id`` is provided, use the O(1)
        per-user index instead of O(n) linear scan of the full ring buffer.
        This eliminates the timing oracle where event-dense users had measurably
        longer response times than non-existent users, enabling enumeration.
        """
        with self._lock:
            if user_id is not None:
                # O(1) lookup — response time is constant regardless of total event volume
                return list(self._user_index.get(user_id, []))[-limit:]
            # Full ring buffer: materialise to list then slice
            return list(self._events)[-limit:]


# Global detector instance
# SuspiciousActivityDetector.__init__ is pure Python (no I/O).
# Module-level init is thread-safe via Python's import lock; no threading.Lock needed.
_detector: SuspiciousActivityDetector = SuspiciousActivityDetector()


def get_suspicious_activity_detector() -> SuspiciousActivityDetector:
    """Return the module-level suspicious activity detector singleton."""
    return _detector
