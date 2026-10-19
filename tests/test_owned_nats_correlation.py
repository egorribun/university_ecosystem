"""Exact message/outbox correlation contracts without external services."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.owned_nats_outage import (
    CorrelationVerdict,
    MessageEvidence,
    MessageIntent,
    StoredMessageEvent,
    validate_message_correlation,
)

CHAT = "00000000-0000-7000-8000-000000000001"
SENDER = "00000000-0000-7000-8000-000000000002"
MESSAGE = "00000000-0000-7000-8000-000000000003"
EVENT = "00000000-0000-7000-8000-000000000004"
OTHER = "00000000-0000-7000-8000-000000000005"


def _fixture(
    content: str = "owned NATS acceptance probe",
) -> tuple[MessageIntent, MessageEvidence, StoredMessageEvent]:
    intent = MessageIntent(chat_id=CHAT, sender_id=SENDER, content=content)
    message = MessageEvidence(
        message_id=MESSAGE, chat_id=CHAT, sender_id=SENDER, content=content
    )
    event = StoredMessageEvent(
        event_id=EVENT,
        event_type="chat.message_sent",
        aggregate_type="Message",
        aggregate_id=MESSAGE,
        payload={
            "_schema_version": 1,
            "message_id": MESSAGE,
            "chat_id": CHAT,
            "sender_id": SENDER,
            "content_preview": content[:50],
        },
    )
    return intent, message, event


@pytest.mark.parametrize("content", ["owned NATS acceptance probe", "Я" * 55])
def test_exact_committed_message_event_matches_request_and_unicode_preview(
    content: str,
) -> None:
    intent, message, event = _fixture(content)

    assert (
        validate_message_correlation(intent, message, message, (event,))
        is CorrelationVerdict.VALID
    )


@pytest.mark.parametrize(
    "http_message",
    [
        replace(_fixture()[1], message_id="not-a-uuid"),
        replace(_fixture()[1], message_id=None),
        replace(_fixture()[1], message_id="00000000-0000-7000-8000-00000000000A"),
        replace(_fixture()[1], message_id="00000000-0000-0000-0000-000000000000"),
        replace(_fixture()[1], chat_id=OTHER),
        replace(_fixture()[1], sender_id=OTHER),
        replace(_fixture()[1], content="other content"),
    ],
)
def test_http_message_must_match_intent_and_have_a_canonical_id(
    http_message: MessageEvidence,
) -> None:
    intent, _message, event = _fixture()

    assert (
        validate_message_correlation(intent, http_message, http_message, (event,))
        is CorrelationVerdict.INVALID_MESSAGE
    )


@pytest.mark.parametrize(
    "database_message",
    [
        replace(_fixture()[1], message_id=OTHER),
        replace(_fixture()[1], chat_id=OTHER),
        replace(_fixture()[1], sender_id=OTHER),
        replace(_fixture()[1], content="other persisted content"),
    ],
)
def test_database_message_must_match_each_http_field(
    database_message: MessageEvidence,
) -> None:
    intent, message, event = _fixture()

    assert (
        validate_message_correlation(intent, message, database_message, (event,))
        is CorrelationVerdict.INVALID_MESSAGE
    )


@pytest.mark.parametrize("count", [0, 2])
def test_exact_query_must_return_one_event_without_latest_row_fallback(
    count: int,
) -> None:
    intent, message, event = _fixture()

    assert (
        validate_message_correlation(intent, message, message, (event,) * count)
        is CorrelationVerdict.INVALID_EVENT
    )


@pytest.mark.parametrize(
    "event",
    [
        replace(_fixture()[2], event_id="not-a-uuid"),
        replace(_fixture()[2], event_id="00000000-0000-0000-0000-000000000000"),
        replace(_fixture()[2], event_type="MessageSent"),
        replace(_fixture()[2], aggregate_type="Chat"),
        replace(_fixture()[2], aggregate_id=OTHER),
    ],
)
def test_single_event_requires_exact_type_and_aggregate(
    event: StoredMessageEvent,
) -> None:
    intent, message, _event = _fixture()

    assert (
        validate_message_correlation(intent, message, message, (event,))
        is CorrelationVerdict.INVALID_EVENT
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("_schema_version", 2),
        ("_schema_version", True),
        ("_schema_version", "1"),
        ("message_id", OTHER),
        ("chat_id", OTHER),
        ("sender_id", OTHER),
        ("content_preview", "other preview"),
    ],
)
def test_each_payload_field_is_independently_bound_to_the_message(
    key: str, value: object
) -> None:
    intent, message, event = _fixture()
    event = replace(event, payload={**event.payload, key: value})

    assert (
        validate_message_correlation(intent, message, message, (event,))
        is CorrelationVerdict.INVALID_EVENT
    )


@pytest.mark.parametrize(
    "missing",
    ["_schema_version", "message_id", "chat_id", "sender_id", "content_preview"],
)
def test_missing_payload_fields_are_not_replaced_by_defaults(missing: str) -> None:
    intent, message, event = _fixture()
    payload = {key: value for key, value in event.payload.items() if key != missing}
    event = replace(event, payload=payload)

    assert (
        validate_message_correlation(intent, message, message, (event,))
        is CorrelationVerdict.INVALID_EVENT
    )


def test_schema_version_alias_does_not_replace_the_actual_storage_key() -> None:
    intent, message, event = _fixture()
    payload = dict(event.payload)
    del payload["_schema_version"]
    payload["schema_version"] = 1
    event = replace(event, payload=payload)

    assert (
        validate_message_correlation(intent, message, message, (event,))
        is CorrelationVerdict.INVALID_EVENT
    )


def test_preview_is_exactly_fifty_codepoints_without_ellipsis() -> None:
    intent, message, event = _fixture("Я" * 55)
    payload = {**event.payload, "content_preview": message.content[:50] + "..."}
    event = replace(event, payload=payload)

    assert (
        validate_message_correlation(intent, message, message, (event,))
        is CorrelationVerdict.INVALID_EVENT
    )


def test_mixed_query_rows_are_rejected_instead_of_filtering_to_one_match() -> None:
    intent, message, event = _fixture()
    unrelated = replace(event, event_id=OTHER, aggregate_id=OTHER)

    assert (
        validate_message_correlation(intent, message, message, (event, unrelated))
        is CorrelationVerdict.INVALID_EVENT
    )


@pytest.mark.parametrize("payload", [None, []])
def test_non_object_event_payload_is_rejected(payload: object) -> None:
    intent, message, event = _fixture()
    event = replace(event, payload=payload)

    verdict = validate_message_correlation(intent, message, message, (event,))

    assert verdict is CorrelationVerdict.INVALID_EVENT


@pytest.mark.parametrize(
    ("field", "value"),
    [("chat_id", "invalid-chat"), ("sender_id", "invalid-sender"), ("content", None)],
)
def test_intent_fields_must_be_valid_even_when_all_evidence_agrees(
    field: str, value: object
) -> None:
    intent, message, event = _fixture()
    intent = replace(intent, **{field: value})
    message = replace(message, **{field: value})
    payload_key = "content_preview" if field == "content" else field
    event = replace(event, payload={**event.payload, payload_key: value})

    verdict = validate_message_correlation(intent, message, message, (event,))

    assert verdict is CorrelationVerdict.INVALID_MESSAGE
