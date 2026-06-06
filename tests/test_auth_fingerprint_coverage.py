"""Coverage for the previously-untested branches of app/auth/fingerprint.py.

Targets the medium-severity classification (lang+ip differ, user-agent stable)
and the bounded ring-buffer eviction logic in both detector methods — the
``len(self._events) == self._MAX_EVENTS`` cleanup arms that mirror a deque
eviction into the per-user index. We shrink ``_MAX_EVENTS`` on a fresh detector
instance so the eviction branch fires after one event instead of 10 000.
"""

from __future__ import annotations

import uuid

from app.auth.fingerprint import (
    SessionFingerprint,
    SuspiciousActivityDetector,
    _compute_fingerprint_hash,
    get_suspicious_activity_detector,
)


def _fp(user_agent: str, accept_language: str, ip: str) -> SessionFingerprint:
    return SessionFingerprint(
        user_agent=user_agent,
        accept_language=accept_language,
        ip_address=ip,
        fingerprint_hash=_compute_fingerprint_hash(user_agent, accept_language, ip),
    )


def test_no_event_when_fingerprints_match() -> None:
    d = SuspiciousActivityDetector()
    fp = _fp("UA", "en", "1.1.1.1")
    # Same hash (UA + lang identical) → matches() short-circuits to None even
    # though the ip differs (ip is not part of the hash).
    other = _fp("UA", "en", "9.9.9.9")
    assert d.check_fingerprint_mismatch(uuid.uuid4(), uuid.uuid4(), fp, other) is None


def test_high_severity_when_user_agent_differs() -> None:
    d = SuspiciousActivityDetector()
    event = d.check_fingerprint_mismatch(
        uuid.uuid4(),
        uuid.uuid4(),
        _fp("UA1", "en", "1.1.1.1"),
        _fp("UA2", "en", "1.1.1.1"),
    )
    assert event is not None
    assert event.severity == "high"


def test_medium_severity_when_lang_and_ip_differ() -> None:
    # Same user_agent, both accept_language AND ip differ → >1 mismatch, no
    # user_agent → "medium" (the elif branch).
    d = SuspiciousActivityDetector()
    event = d.check_fingerprint_mismatch(
        uuid.uuid4(),
        uuid.uuid4(),
        _fp("UA", "en", "1.1.1.1"),
        _fp("UA", "fr", "2.2.2.2"),
    )
    assert event is not None
    assert event.severity == "medium"


def test_low_severity_when_only_language_differs() -> None:
    # Only accept_language differs → exactly 1 non-user_agent mismatch → "low".
    d = SuspiciousActivityDetector()
    event = d.check_fingerprint_mismatch(
        uuid.uuid4(),
        uuid.uuid4(),
        _fp("UA", "en", "1.1.1.1"),
        _fp("UA", "fr", "1.1.1.1"),
    )
    assert event is not None
    assert event.severity == "low"


def test_fingerprint_mismatch_eviction_branch() -> None:
    d = SuspiciousActivityDetector()
    d._MAX_EVENTS = 1  # shrink so the 2nd append hits the eviction cleanup arm
    uid, sid = uuid.uuid4(), uuid.uuid4()
    stored, current = _fp("UA1", "en", "1.1.1.1"), _fp("UA2", "en", "1.1.1.1")
    assert d.check_fingerprint_mismatch(uid, sid, stored, current) is not None
    # 2nd call: len == _MAX_EVENTS → evict oldest from _user_index, then append.
    assert d.check_fingerprint_mismatch(uid, sid, stored, current) is not None
    assert d.get_recent_events(user_id=uid)  # index path returns events


def test_rapid_location_change_paths_and_eviction() -> None:
    d = SuspiciousActivityDetector()
    uid, sid = uuid.uuid4(), uuid.uuid4()
    # Same ip → None.
    assert d.check_rapid_location_change(uid, sid, "1.1.1.1", "1.1.1.1", 5) is None
    # Slow change (>60s) → None.
    assert d.check_rapid_location_change(uid, sid, "1.1.1.1", "2.2.2.2", 120) is None
    # Fast change → medium event.
    e = d.check_rapid_location_change(uid, sid, "1.1.1.1", "2.2.2.2", 10)
    assert e is not None and e.severity == "medium"

    # Eviction arm.
    d2 = SuspiciousActivityDetector()
    d2._MAX_EVENTS = 1
    assert d2.check_rapid_location_change(uid, sid, "1.1.1.1", "2.2.2.2", 5) is not None
    assert d2.check_rapid_location_change(uid, sid, "3.3.3.3", "4.4.4.4", 5) is not None


def test_get_recent_events_full_buffer_and_singleton() -> None:
    d = SuspiciousActivityDetector()
    d.check_rapid_location_change(uuid.uuid4(), uuid.uuid4(), "1.1.1.1", "2.2.2.2", 5)
    # No user_id → full ring-buffer path.
    assert len(d.get_recent_events()) >= 1
    # Module singleton accessor.
    assert isinstance(get_suspicious_activity_detector(), SuspiciousActivityDetector)
