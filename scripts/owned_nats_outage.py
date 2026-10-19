"""Pure evidence contracts for a future owned NATS outage runner.

This module performs no I/O. Signed-owner, daemon and Compose-resource
verification belong to the future bounded adapter;
inventory validation is not a substitute for those authentication checks.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    VALID = "valid"
    INVALID_SNAPSHOT = "invalid_snapshot"
    IDENTITY_CHANGED = "identity_changed"
    RUNTIME_CHANGED = "runtime_changed"


def validate_restored_inventory(
    selected_services: tuple[str, ...],
    before: tuple[ContainerSnapshot, ...],
    after: tuple[ContainerSnapshot, ...],
) -> RestorationVerdict:
    """Validate same-container recovery evidence without operating the stand."""
    if validate_inventory(selected_services, before) is not InventoryVerdict.VALID:
        return RestorationVerdict.INVALID_SNAPSHOT

    original = {record.container_id: record for record in before}
    restored = {record.container_id: record for record in after}
    original_identity = {
        container_id: (record.service, record.identity)
        for container_id, record in original.items()
    }
    restored_identity = {
        container_id: (record.service, record.identity)
        for container_id, record in restored.items()
    }
    if len(restored) != len(after) or restored_identity != original_identity:
        return RestorationVerdict.IDENTITY_CHANGED

    for container_id, record in restored.items():
        if record.service != "nats" and record != original[container_id]:
            return RestorationVerdict.RUNTIME_CHANGED

    if validate_inventory(selected_services, after) is not InventoryVerdict.VALID:
        return RestorationVerdict.INVALID_SNAPSHOT
    return RestorationVerdict.VALID


class WorkerPolicyVerdict(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class WorkerPolicy:
    poll_interval_seconds: float
    batch_size: int
    max_retries: int


def validate_worker_policy(policy: WorkerPolicy) -> WorkerPolicyVerdict:
    """Admit only bounded settings suitable for outage observation."""
    if not isinstance(policy, WorkerPolicy):
        return WorkerPolicyVerdict.INVALID

    poll_interval = policy.poll_interval_seconds
    if (
        type(poll_interval) not in (int, float)
        or not 1 <= poll_interval <= 10
        or not math.isfinite(poll_interval)
        or type(policy.batch_size) is not int
        or policy.batch_size < 2
        or type(policy.max_retries) is not int
        or policy.max_retries != 5
    ):
        return WorkerPolicyVerdict.INVALID
    return WorkerPolicyVerdict.VALID


class OutboxVerdict(StrEnum):
    INVALID = "invalid"
    WAIT = "wait"
    RETRYABLE = "retryable"
    DRAINED = "drained"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class StoredEventState:
    """The row ID and exact DLQ count both refer to stored_events.id."""

    stored_event_id: str
    processed_at_present: bool
    error_count: int
    dlq_count: int


def _valid_exact_stored_event_state(
    expected_event_id: str, state: StoredEventState | None
) -> bool:
    return (
        _is_canonical_uuid(expected_event_id)
        and isinstance(state, StoredEventState)
        and _is_canonical_uuid(state.stored_event_id)
        and state.stored_event_id == expected_event_id
        and type(state.processed_at_present) is bool
        and type(state.error_count) is int
        and state.error_count >= 0
        and type(state.dlq_count) is int
        and state.dlq_count >= 0
    )


def classify_outage_attempt(
    expected_event_id: str, state: StoredEventState | None
) -> OutboxVerdict:
    """Classify retry evidence for the exact retained StoredEvent row."""
    if state is None or not _valid_exact_stored_event_state(expected_event_id, state):
        return OutboxVerdict.INVALID

    if state.processed_at_present or state.dlq_count > 0 or state.error_count >= 5:
        return OutboxVerdict.TERMINAL
    if state.error_count == 0:
        return OutboxVerdict.WAIT
    return OutboxVerdict.RETRYABLE


def classify_outbox_drain(
    expected_event_id: str,
    observed_retry_count: int,
    state: StoredEventState | None,
) -> OutboxVerdict:
    """Classify completion for the same row without accepting counter reset."""
    if (
        state is None
        or type(observed_retry_count) is not int
        or not 1 <= observed_retry_count < 5
        or not _valid_exact_stored_event_state(expected_event_id, state)
    ):
        return OutboxVerdict.INVALID

    if state.error_count < observed_retry_count:
        return OutboxVerdict.INVALID
    if state.dlq_count > 0 or state.error_count >= 5:
        return OutboxVerdict.TERMINAL
    if state.processed_at_present:
        return OutboxVerdict.DRAINED
    return OutboxVerdict.WAIT


class BrokerVerdict(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    INVALID = "invalid"


def classify_broker_error(status: object, error_code: object) -> BrokerVerdict:
    """Only the server's exact missing-message error is pollable."""
    if (
        type(status) is int
        and status == 404
        and type(error_code) is int
        and error_code == 10037
    ):
        return BrokerVerdict.MISSING
    return BrokerVerdict.INVALID


def validate_broker_receipt(
    message: MessageEvidence,
    *,
    subject: str,
    sequence: int,
    envelope: object,
) -> BrokerVerdict:
    """Bind existing stream storage evidence to the exact committed message."""
    if (
        not all(
            _is_canonical_uuid(value)
            for value in (message.message_id, message.chat_id, message.sender_id)
        )
        or not isinstance(message.content, str)
        or subject != f"chat.{message.chat_id}"
        or type(sequence) is not int
        or sequence <= 0
        or not isinstance(envelope, Mapping)
        or envelope.get("type") != "new_message"
        or envelope.get("room") != message.chat_id
    ):
        return BrokerVerdict.INVALID

    payload = envelope.get("payload")
    if (
        not isinstance(payload, Mapping)
        or payload.get("type") != "new_message"
        or payload.get("chat_id") != message.chat_id
    ):
        return BrokerVerdict.INVALID

    stored_message = payload.get("message")
    if (
        not isinstance(stored_message, Mapping)
        or stored_message.get("id") != message.message_id
        or stored_message.get("chat_id") != message.chat_id
        or stored_message.get("sender_id") != message.sender_id
        or stored_message.get("content") != message.content
    ):
        return BrokerVerdict.INVALID
    return BrokerVerdict.VALID


class DeadlineVerdict(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass(frozen=True)
class DeadlineBudget:
    verdict: DeadlineVerdict
    seconds: float | None = None


def _finite_number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


@dataclass
class _DeadlineClockState:
    """Shared sample history for a deadline and its child phases."""

    reader: object
    last_sample: float | None = None
    invalid: bool = False

    def read(self) -> float | None:
        if self.invalid or not callable(self.reader):
            self.invalid = True
            return None
        try:
            value = self.reader()
        except Exception:
            self.invalid = True
            return None
        sample = _finite_number(value)
        if sample is None or (
            self.last_sample is not None and sample < self.last_sample
        ):
            self.invalid = True
            return None
        self.last_sample = sample
        return sample


@dataclass(frozen=True)
class Deadline:
    """Absolute-deadline evidence; no transport or lifecycle operations."""

    expires_at: float | None
    verdict: DeadlineVerdict
    _clock: _DeadlineClockState = field(repr=False, compare=False)

    @classmethod
    def after(cls, cap_seconds: object, *, clock: object) -> Deadline:
        state = _DeadlineClockState(clock)
        cap = _finite_number(cap_seconds)
        if cap is None or cap <= 0:
            return cls(None, DeadlineVerdict.INVALID, state)
        now = state.read()
        if now is None:
            return cls(None, DeadlineVerdict.INVALID, state)
        expires_at = now + cap
        if not math.isfinite(expires_at) or expires_at <= now:
            return cls(None, DeadlineVerdict.INVALID, state)
        return cls(expires_at, DeadlineVerdict.VALID, state)

    def child(self, cap_seconds: object) -> Deadline:
        budget = self.timeout_for(cap_seconds)
        now = self._clock.last_sample
        if budget.verdict is not DeadlineVerdict.VALID:
            return Deadline(None, budget.verdict, self._clock)
        if now is None or budget.seconds is None or self.expires_at is None:
            return Deadline(None, DeadlineVerdict.INVALID, self._clock)
        expires_at = min(self.expires_at, now + budget.seconds)
        if not math.isfinite(expires_at) or expires_at <= now:
            return Deadline(None, DeadlineVerdict.INVALID, self._clock)
        return Deadline(expires_at, DeadlineVerdict.VALID, self._clock)

    def timeout_for(self, cap_seconds: object) -> DeadlineBudget:
        cap = _finite_number(cap_seconds)
        if cap is None or cap <= 0:
            return DeadlineBudget(DeadlineVerdict.INVALID)
        if self.verdict is not DeadlineVerdict.VALID:
            return DeadlineBudget(self.verdict)
        if self.expires_at is None or not math.isfinite(self.expires_at):
            return DeadlineBudget(DeadlineVerdict.INVALID)
        now = self._clock.read()
        if now is None:
            return DeadlineBudget(DeadlineVerdict.INVALID)
        remaining = self.expires_at - now
        if remaining <= 0:
            return DeadlineBudget(DeadlineVerdict.EXPIRED)
        return DeadlineBudget(DeadlineVerdict.VALID, min(cap, remaining))
