"""Coverage for the previously-untested branches of app/auth/fingerprint.py.

Targets the medium-severity classification (lang+ip differ, user-agent stable)
and the bounded ring-buffer eviction logic in both detector methods — the
``len(self._events) == self._MAX_EVENTS`` cleanup arms that mirror a deque
eviction into the per-user index. We shrink ``_MAX_EVENTS`` on a fresh detector
instance so the eviction branch fires after one event instead of 10 000.
"""

from __future__ import annotations

import uuid
from collections import deque
from unittest.mock import MagicMock

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
    d._events = deque(maxlen=1)
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
    d2._events = deque(maxlen=1)
    assert d2.check_rapid_location_change(uid, sid, "1.1.1.1", "2.2.2.2", 5) is not None
    assert d2.check_rapid_location_change(uid, sid, "3.3.3.3", "4.4.4.4", 5) is not None


def test_get_recent_events_full_buffer_and_singleton() -> None:
    d = SuspiciousActivityDetector()
    d.check_rapid_location_change(uuid.uuid4(), uuid.uuid4(), "1.1.1.1", "2.2.2.2", 5)
    # No user_id → full ring-buffer path.
    assert len(d.get_recent_events()) >= 1
    # Module singleton accessor.
    assert isinstance(get_suspicious_activity_detector(), SuspiciousActivityDetector)


def test_fingerprint_dict_conversion() -> None:
    fp = _fp("Mozilla", "en-US", "8.8.8.8")
    d = fp.to_dict()
    assert d["user_agent"] == "Mozilla"
    assert d["accept_language"] == "en-US"
    assert d["ip_address"] == "8.8.8.8"
    assert d["fingerprint_hash"] == fp.fingerprint_hash

    fp2 = SessionFingerprint.from_dict(d)
    assert fp2.user_agent == fp.user_agent
    assert fp2.accept_language == fp.accept_language
    assert fp2.ip_address == fp.ip_address
    assert fp2.fingerprint_hash == fp.fingerprint_hash


def test_extract_fingerprint_and_client_ip() -> None:
    from fastapi import Request

    from app.auth.fingerprint import _get_client_ip, extract_fingerprint

    # 1. client host is present
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"user-agent": "Mozilla", "accept-language": "en"}
    mock_request.client.host = "1.2.3.4"
    fp = extract_fingerprint(mock_request)
    assert fp.user_agent == "Mozilla"
    assert fp.ip_address == "1.2.3.4"

    # 2. client is None
    mock_request_no_client = MagicMock(spec=Request)
    mock_request_no_client.headers = {"user-agent": "Mozilla", "accept-language": "en"}
    mock_request_no_client.client = None
    assert _get_client_ip(mock_request_no_client) == "unknown"


def test_fingerprint_mismatch_no_fields() -> None:
    # Test line 217: mismatches is empty but matches is False
    stored = SessionFingerprint("UA", "en", "1.1.1.1", "hash1")
    current = SessionFingerprint("UA", "en", "1.1.1.1", "hash2")
    d = SuspiciousActivityDetector()
    assert (
        d.check_fingerprint_mismatch(uuid.uuid4(), uuid.uuid4(), stored, current)
        is None
    )


def test_fingerprint_eviction_missing_from_user_index() -> None:
    # Test line 318-319: evicted event not in user_list (ValueError caught)
    d = SuspiciousActivityDetector()
    d._MAX_EVENTS = 1
    d._events = deque(maxlen=1)
    uid1, uid2 = uuid.uuid4(), uuid.uuid4()
    sid = uuid.uuid4()

    # Event 1 for user 1
    d.check_rapid_location_change(uid1, sid, "1.1.1.1", "2.2.2.2", 5)

    # Put a different event in user 1 list so it is truthy but doesn't contain Event 1
    d._user_index[uid1] = ["some-other-object"]

    # Event 2 for user 2: triggers eviction of Event 1.
    # Since Event 1 is not in uid1 list, it raises ValueError which is caught.
    d.check_rapid_location_change(uid2, sid, "3.3.3.3", "4.4.4.4", 5)
    assert len(d._events) == 1

    # Test line 315->322: user_list is None (uid1 deleted entirely from _user_index)
    d3 = SuspiciousActivityDetector()
    d3._MAX_EVENTS = 1
    d3._events = deque(maxlen=1)
    d3.check_rapid_location_change(uid1, sid, "1.1.1.1", "2.2.2.2", 5)
    del d3._user_index[uid1]
    d3.check_rapid_location_change(uid2, sid, "3.3.3.3", "4.4.4.4", 5)
    assert len(d3._events) == 1


def test_fingerprint_eviction_non_empty_user_list() -> None:
    # Test line 266-267: user_list is not empty after removal
    d = SuspiciousActivityDetector()
    d._MAX_EVENTS = 2
    d._events = deque(maxlen=2)
    uid = uuid.uuid4()
    sid = uuid.uuid4()

    # Add two events for same user
    d.check_rapid_location_change(uid, sid, "1.1.1.1", "2.2.2.2", 5)
    d.check_rapid_location_change(uid, sid, "3.3.3.3", "4.4.4.4", 5)

    # 3rd event triggers eviction of 1st event.
    # User list still has 2nd event, so uid is NOT deleted from _user_index.
    d.check_rapid_location_change(uuid.uuid4(), sid, "5.5.5.5", "6.6.6.6", 5)
    assert uid in d._user_index
    assert len(d._user_index[uid]) == 1


def test_fingerprint_mismatch_eviction_complex_branches() -> None:
    # Test lines 261-268: check_fingerprint_mismatch eviction branches
    d = SuspiciousActivityDetector()
    d._MAX_EVENTS = 1
    d._events = deque(maxlen=1)
    uid1, uid2 = uuid.uuid4(), uuid.uuid4()
    sid = uuid.uuid4()
    stored, current = _fp("UA1", "en", "1.1.1.1"), _fp("UA2", "en", "1.1.1.1")

    # 1. Add event for user 1
    d.check_fingerprint_mismatch(uid1, sid, stored, current)

    # 2. Put a different event in user 1 list to trigger ValueError caught on eviction
    d._user_index[uid1] = ["some-other-object"]

    # 3. Add event for user 2 to trigger eviction of event 1
    d.check_fingerprint_mismatch(uid2, sid, stored, current)
    assert len(d._events) == 1

    # 3.5. Test line 261->268: user_list is None (uid1 deleted entirely from _user_index)
    d3 = SuspiciousActivityDetector()
    d3._MAX_EVENTS = 1
    d3._events = deque(maxlen=1)
    d3.check_fingerprint_mismatch(uid1, sid, stored, current)
    del d3._user_index[uid1]
    d3.check_fingerprint_mismatch(uid2, sid, stored, current)
    assert len(d3._events) == 1

    # 4. Eviction with non-empty list (del user_index branch not taken)
    d2 = SuspiciousActivityDetector()
    d2._MAX_EVENTS = 2
    d2._events = deque(maxlen=2)

    d2.check_fingerprint_mismatch(uid1, sid, stored, current)
    d2.check_fingerprint_mismatch(uid1, sid, stored, current)
    # 3rd event evicts 1st event. User index for uid1 still has 2nd event.
    d2.check_fingerprint_mismatch(uid2, sid, stored, current)
    assert uid1 in d2._user_index
    assert len(d2._user_index[uid1]) == 1
