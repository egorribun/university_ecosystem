"""Pure evidence contracts for a future owned NATS outage runner.

This module performs no I/O. Signed-owner, daemon and Compose-resource
verification belong to the future bounded adapter;
inventory validation is not a substitute for those authentication checks.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

_REQUIRED_HEALTHY = frozenset({"backend", "outbox-worker", "postgres", "minio", "nats"})
_INITIALIZERS = frozenset(
    {"migrations", "minio-init", "postgres-databases-init", "spicedb-migrate"}
)
_IDENTITY = re.compile(r"[0-9a-f]{64}")


class InventoryVerdict(StrEnum):
    VALID = "valid"
    INVALID_SELECTION = "invalid_selection"
    INVALID_IDENTITY = "invalid_identity"
    INVALID_RUNTIME = "invalid_runtime"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class ContainerSnapshot:
    """Identity digest uses live_stand's existing canonical inspect material."""

    container_id: str
    service: str
    identity: str
    running: bool
    status: str | None
    health: str | None
    restart_count: int
    exit_code: int
    oom_killed: bool


def validate_inventory(
    selected_services: tuple[str, ...],
    records: tuple[ContainerSnapshot, ...],
) -> InventoryVerdict:
    """Validate a complete snapshot against an already authenticated Core selection."""
    selected = set(selected_services)
    if (
        not selected
        or len(selected) != len(selected_services)
        or not _REQUIRED_HEALTHY <= selected
    ):
        return InventoryVerdict.INVALID_SELECTION

    services = {record.service for record in records}
    container_ids = {record.container_id for record in records}
    if (
        services != selected
        or len(services) != len(records)
        or len(container_ids) != len(records)
    ):
        return InventoryVerdict.INVALID_IDENTITY

    for record in records:
        if (
            _IDENTITY.fullmatch(record.container_id) is None
            or _IDENTITY.fullmatch(record.identity) is None
        ):
            return InventoryVerdict.INVALID_IDENTITY

        initializer = record.service in _INITIALIZERS
        expected_running = not initializer
        if (
            type(record.running) is not bool
            or record.running != expected_running
            or record.status != ("exited" if initializer else "running")
            or type(record.restart_count) is not int
            or record.restart_count < 0
            or type(record.exit_code) is not int
            or record.exit_code != 0
            or type(record.oom_killed) is not bool
            or record.oom_killed
        ):
            return InventoryVerdict.INVALID_RUNTIME

        if record.health != "healthy" and (
            record.health is not None or record.service in _REQUIRED_HEALTHY
        ):
            return InventoryVerdict.UNHEALTHY

    return InventoryVerdict.VALID


class CorrelationVerdict(StrEnum):
    VALID = "valid"
    INVALID_MESSAGE = "invalid_message"
    INVALID_EVENT = "invalid_event"


@dataclass(frozen=True)
class MessageIntent:
    chat_id: str
    sender_id: str
    content: str


@dataclass(frozen=True)
class MessageEvidence:
    message_id: str
    chat_id: str
    sender_id: str
    content: str


@dataclass(frozen=True)
class StoredMessageEvent:
    """event_id is stored_events.id, never the domain ID inside metadata."""

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: Mapping[str, object]


def _is_canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = UUID(value)
    except ValueError:
        return False
    return parsed.int != 0 and str(parsed) == value


def validate_message_correlation(
    intent: MessageIntent,
    http_message: MessageEvidence,
    database_message: MessageEvidence,
    events: tuple[StoredMessageEvent, ...],
) -> CorrelationVerdict:
    """Bind one committed event to the intended send and exact HTTP/DB message."""
    if (
        not all(
            _is_canonical_uuid(value)
            for value in (
                http_message.message_id,
                intent.chat_id,
                intent.sender_id,
            )
        )
        or not isinstance(intent.content, str)
        or http_message.chat_id != intent.chat_id
        or http_message.sender_id != intent.sender_id
        or http_message.content != intent.content
        or database_message != http_message
    ):
        return CorrelationVerdict.INVALID_MESSAGE

    if len(events) != 1:
        return CorrelationVerdict.INVALID_EVENT
    event = events[0]
    if (
        not _is_canonical_uuid(event.event_id)
        or event.event_type != "chat.message_sent"
        or event.aggregate_type != "Message"
        or event.aggregate_id != http_message.message_id
        or not isinstance(event.payload, Mapping)
    ):
        return CorrelationVerdict.INVALID_EVENT

    payload = event.payload
    version = payload.get("_schema_version")
    if (
        type(version) is not int
        or version != 1
        or payload.get("message_id") != http_message.message_id
        or payload.get("chat_id") != intent.chat_id
        or payload.get("sender_id") != intent.sender_id
        or payload.get("content_preview") != intent.content[:50]
    ):
        return CorrelationVerdict.INVALID_EVENT
    return CorrelationVerdict.VALID


class RestorationVerdict(StrEnum):
    NOT_READY = "not_ready"
    VALID = "valid"
    INVALID_SNAPSHOT = "invalid_snapshot"
    IDENTITY_CHANGED = "identity_changed"
    RUNTIME_CHANGED = "runtime_changed"


def validate_restored_inventory(
    selected_services: tuple[str, ...],
    before: tuple[ContainerSnapshot, ...],
    after: tuple[ContainerSnapshot, ...],
) -> RestorationVerdict:
    """Unavailable pure seam; does not restore containers or perform any I/O."""
    return RestorationVerdict.NOT_READY
