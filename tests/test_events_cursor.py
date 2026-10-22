"""Canonical explicit-order main-feed cursors, independent of database I/O."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import event_service as service

_ORDER = "starts_at_asc"
_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000123")
_EVENT_ID = uuid.UUID("abcdefab-1234-5678-9abc-def012345678")
_STARTS_AT = datetime(2027, 1, 2, 3, 4, 5, tzinfo=UTC)


def _context(**changes):
    values = {
        "user_id": _USER_ID,
        "locale": "ru",
        "limit": 20,
        "search": "",
        "event_type": "",
        "location": "",
        "is_active": True,
        "order": _ORDER,
    }
    values.update(changes)
    return service._events_cursor_binding(**values)


def _token(raw):
    return "e2:" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _payload():
    return {
        "v": 2,
        "order": _ORDER,
        "filter": _context(),
        "key": {"starts_at": _STARTS_AT.isoformat(), "id": str(_EVENT_ID)},
    }


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


@pytest.mark.parametrize(
    "starts_at",
    [
        _STARTS_AT,
        _STARTS_AT.replace(tzinfo=None),
        _STARTS_AT.astimezone(timezone(timedelta(hours=3))),
    ],
    ids=["utc", "sqlite-naive", "offset"],
)
def test_explicit_event_cursor_round_trip_is_canonical(starts_at):
    binding = _context()
    cursor = service._encode_events_cursor(
        order=_ORDER, binding=binding, starts_at=starts_at, event_id=_EVENT_ID
    )
    assert cursor == _token(_canonical(_payload()))
    assert service._decode_events_cursor(cursor, order=_ORDER, binding=binding) == (
        _STARTS_AT,
        _EVENT_ID,
    )


def test_absent_explicit_event_cursor_starts_a_first_page():
    assert service._decode_events_cursor(None, order=_ORDER, binding=_context()) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", uuid.UUID("00000000-0000-0000-0000-000000000789")),
        ("locale", "en"),
        ("limit", 21),
        ("search", "seminar"),
        ("event_type", "conference"),
        ("location", "Main Hall"),
        ("is_active", False),
        ("order", "starts_at_desc"),
    ],
)
def test_explicit_event_cursor_binds_every_query_context_field(field, value):
    binding = _context()
    changed = _context(**{field: value})
    assert changed != binding
    cursor = _token(_canonical(_payload()))
    with pytest.raises(service.InvalidEventsCursor):
        service._decode_events_cursor(cursor, order=_ORDER, binding=changed)


@pytest.mark.parametrize("user_id", [None, _USER_ID])
def test_explicit_event_cursor_binding_is_deterministic(user_id):
    assert _context(user_id=user_id) == _context(user_id=user_id)


def test_explicit_event_cursor_rejects_opposite_direction():
    cursor = _token(_canonical(_payload()))
    with pytest.raises(service.InvalidEventsCursor):
        service._decode_events_cursor(
            cursor, order="starts_at_desc", binding=_context()
        )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {**_payload(), "v": True},
        {**_payload(), "v": "2"},
        {**_payload(), "v": 3},
        {**_payload(), "unknown": "field"},
        {**_payload(), "key": []},
        {**_payload(), "key": {"id": str(_EVENT_ID)}},
        {**_payload(), "key": {"starts_at": 12, "id": str(_EVENT_ID)}},
        {**_payload(), "key": {"starts_at": _STARTS_AT.isoformat(), "id": 12}},
        {**_payload(), "key": {"starts_at": "not-a-date", "id": str(_EVENT_ID)}},
        {
            **_payload(),
            "key": {"starts_at": "2027-01-02T03:04:05", "id": str(_EVENT_ID)},
        },
        {
            **_payload(),
            "key": {"starts_at": "2027-01-02T03:04:05Z", "id": str(_EVENT_ID)},
        },
        {
            **_payload(),
            "key": {"starts_at": "2027-01-02T06:04:05+03:00", "id": str(_EVENT_ID)},
        },
        {
            **_payload(),
            "key": {"starts_at": _STARTS_AT.isoformat(), "id": "not-a-uuid"},
        },
        {
            **_payload(),
            "key": {"starts_at": _STARTS_AT.isoformat(), "id": str(_EVENT_ID).upper()},
        },
        {
            **_payload(),
            "key": {"starts_at": _STARTS_AT.isoformat(), "id": _EVENT_ID.hex},
        },
    ],
)
def test_explicit_event_cursor_rejects_invalid_payload(payload):
    with pytest.raises(service.InvalidEventsCursor):
        service._decode_events_cursor(
            _token(_canonical(payload)), order=_ORDER, binding=_context()
        )


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "legacy-cursor",
        "e2:" + "A" * 1024,
        "e2:",
        "e2:A",
        "e2:bad!base64",
        "e2:Zh",
        "e2:Zg==",
        _token(b"\xff"),
        _token(b"{"),
        _token(json.dumps(_payload()).encode()),
        _token(_canonical(_payload()).replace(b'"v":2', b'"v":2,"v":2')),
    ],
)
def test_explicit_event_cursor_rejects_malformed_or_noncanonical_encoding(cursor):
    with pytest.raises(service.InvalidEventsCursor):
        service._decode_events_cursor(cursor, order=_ORDER, binding=_context())


def test_explicit_event_cursor_does_not_hide_unrelated_parser_errors(monkeypatch):
    def unexpected_failure(_raw):
        raise RuntimeError("synthetic unrelated failure")

    cursor = _token(_canonical(_payload()))
    monkeypatch.setattr(service.json, "loads", unexpected_failure)
    with pytest.raises(RuntimeError, match="synthetic unrelated failure"):
        service._decode_events_cursor(cursor, order=_ORDER, binding=_context())


@pytest.mark.asyncio
async def test_invalid_explicit_cursor_is_rejected_before_embedding_or_database():
    repository = SimpleNamespace(
        search_events=AsyncMock(), count_search_events=AsyncMock()
    )
    vector = SimpleNamespace(
        get_embedding=AsyncMock(side_effect=RuntimeError("must not call provider"))
    )
    events = service.EventService(SimpleNamespace(events=repository), vector)

    with pytest.raises(service.InvalidEventsCursor):
        await events.get_events(
            search="seminar", cursor="invalid", order="starts_at_desc"
        )

    vector.get_embedding.assert_not_awaited()
    repository.search_events.assert_not_awaited()
    repository.count_search_events.assert_not_awaited()
