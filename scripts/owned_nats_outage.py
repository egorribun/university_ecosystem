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
    NOT_READY = "not_ready"
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
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: Mapping[str, object]


def validate_message_correlation(
    intent: MessageIntent,
    http_message: MessageEvidence,
    database_message: MessageEvidence,
    events: tuple[StoredMessageEvent, ...],
) -> CorrelationVerdict:
    """Unavailable pure seam; no message or event is accepted until implemented."""
    return CorrelationVerdict.NOT_READY
