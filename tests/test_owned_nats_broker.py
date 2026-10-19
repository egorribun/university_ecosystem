"""Exact broker response contracts; no NATS connection or stream mutation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.owned_nats_outage import (
    BrokerVerdict,
    MessageEvidence,
    classify_broker_error,
    validate_broker_receipt,
)

CHAT = "00000000-0000-7000-8000-000000000001"
SENDER = "00000000-0000-7000-8000-000000000002"
MESSAGE = "00000000-0000-7000-8000-000000000003"
OTHER = "00000000-0000-7000-8000-000000000004"


def _message() -> MessageEvidence:
    return MessageEvidence(
        message_id=MESSAGE,
        chat_id=CHAT,
        sender_id=SENDER,
        content="owned NATS acceptance probe",
    )


def _envelope(message: MessageEvidence) -> dict[str, object]:
    return {
        "type": "new_message",
        "room": message.chat_id,
        "payload": {
            "type": "new_message",
            "chat_id": message.chat_id,
            "message": {
                "id": message.message_id,
                "chat_id": message.chat_id,
                "sender_id": message.sender_id,
                "content": message.content,
            },
        },
    }


def _changed(path: tuple[str, ...], value: object) -> dict[str, object]:
    envelope = _envelope(_message())
    current = envelope
    for key in path[:-1]:
        child = current[key]
        assert isinstance(child, dict)
        current = child
    current[path[-1]] = value
    return envelope


def test_exact_existing_stream_message_is_receipt_evidence() -> None:
    message = _message()

    verdict = validate_broker_receipt(
        message, subject=f"chat.{CHAT}", sequence=1, envelope=_envelope(message)
    )

    assert verdict is BrokerVerdict.VALID


@pytest.mark.parametrize("subject", ["", f"chat.{OTHER}", f"room.{CHAT}.new_message"])
def test_only_actual_chat_subject_is_accepted(subject: str) -> None:
    message = _message()

    verdict = validate_broker_receipt(
        message, subject=subject, sequence=1, envelope=_envelope(message)
    )

    assert verdict is BrokerVerdict.INVALID


@pytest.mark.parametrize("sequence", [0, -1, True, 1.0, None])
def test_receipt_requires_positive_integer_storage_sequence(sequence: object) -> None:
    message = _message()

    verdict = validate_broker_receipt(
        message, subject=f"chat.{CHAT}", sequence=sequence, envelope=_envelope(message)
    )

    assert verdict is BrokerVerdict.INVALID


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("type",), "other"),
        (("room",), OTHER),
        (("room",), f"chat.{CHAT}"),
        (("payload",), None),
        (("payload",), []),
        (("payload", "type"), "other"),
        (("payload", "chat_id"), OTHER),
        (("payload", "message"), None),
        (("payload", "message"), []),
        (("payload", "message", "id"), OTHER),
        (("payload", "message", "chat_id"), OTHER),
        (("payload", "message", "sender_id"), OTHER),
        (("payload", "message", "content"), "different content"),
    ],
)
def test_each_envelope_binding_is_checked_independently(
    path: tuple[str, ...], value: object
) -> None:
    verdict = validate_broker_receipt(
        _message(), subject=f"chat.{CHAT}", sequence=1, envelope=_changed(path, value)
    )

    assert verdict is BrokerVerdict.INVALID


@pytest.mark.parametrize("envelope", [None, [], {}, {"type": "new_message"}])
def test_malformed_or_incomplete_envelopes_fail_closed(envelope: object) -> None:
    verdict = validate_broker_receipt(
        _message(), subject=f"chat.{CHAT}", sequence=1, envelope=envelope
    )

    assert verdict is BrokerVerdict.INVALID


def test_message_id_alias_does_not_replace_actual_serialized_id() -> None:
    message = _message()
    envelope = {
        "type": "new_message",
        "room": CHAT,
        "payload": {
            "type": "new_message",
            "chat_id": CHAT,
            "message": {
                "message_id": MESSAGE,
                "chat_id": CHAT,
                "sender_id": SENDER,
                "content": message.content,
            },
        },
    }

    verdict = validate_broker_receipt(
        message, subject=f"chat.{CHAT}", sequence=1, envelope=envelope
    )

    assert verdict is BrokerVerdict.INVALID


@pytest.mark.parametrize("field", ["message_id", "chat_id", "sender_id"])
def test_expected_identity_must_be_valid_even_if_envelope_agrees(field: str) -> None:
    message = replace(_message(), **{field: "not-a-uuid"})

    verdict = validate_broker_receipt(
        message,
        subject=f"chat.{message.chat_id}",
        sequence=1,
        envelope=_envelope(message),
    )

    assert verdict is BrokerVerdict.INVALID


@pytest.mark.parametrize(
    ("status", "error_code", "expected"),
    [
        (404, 10037, BrokerVerdict.MISSING),
        (404, 10059, BrokerVerdict.INVALID),
        (404, 0, BrokerVerdict.INVALID),
        (401, 10037, BrokerVerdict.INVALID),
        (500, 10037, BrokerVerdict.INVALID),
        (404.0, 10037, BrokerVerdict.INVALID),
        (404, 10037.0, BrokerVerdict.INVALID),
        (None, None, BrokerVerdict.INVALID),
        ("404", "10037", BrokerVerdict.INVALID),
    ],
)
def test_only_exact_missing_message_error_is_pollable(
    status: object, error_code: object, expected: BrokerVerdict
) -> None:
    assert classify_broker_error(status, error_code) is expected
