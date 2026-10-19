"""Unavailable coordinator boundary for one owner-scoped NATS acceptance run.

The future adapter authenticates signed ownership and bounds every nested
operation. These projections are evidence, not authentication substitutes.
No runtime adapter or command invokes this scaffold.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from scripts.owned_nats_outage import (
    ContainerSnapshot,
    Deadline,
    MessageEvidence,
    StoredEventState,
    StoredMessageEvent,
    WorkerPolicy,
)


@dataclass(frozen=True)
class OwnerEvidence:
    repository: str
    worktree: str
    project_name: str
    published_ports: tuple[tuple[str, int], ...]
    schema_version: int
    daemon_fingerprint: str | None
    compose_resource_fingerprint: str | None
    resume_compose_resource_fingerprint: str | None
    resume_compose_resource_schema_version: int | None
    source_sha: str | None
    stack: str
    service_roots: tuple[str, ...]
    selected_services: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeEvidence:
    daemon_fingerprint: str | None
    resource_fingerprint: str | None
    containers: tuple[ContainerSnapshot, ...]


@dataclass(frozen=True)
class PgRoleRow:
    rolname: str
    rolsuper: bool


@dataclass(frozen=True)
class PrincipalEvidence:
    session_user: str
    current_user: str
    pg_role: PgRoleRow


@dataclass(frozen=True)
class UserRow:
    id: str
    email: str
    role: str
    is_active: bool
    demo_seed_key: str | None


@dataclass(frozen=True)
class ChatRow:
    id: str
    chat_type: str
    demo_seed_key: str | None


@dataclass(frozen=True)
class ChatParticipantRow:
    chat_id: str
    user_id: str


@dataclass(frozen=True)
class AdmissionEvidence:
    principal: PrincipalEvidence
    users: tuple[UserRow, ...]
    chats: tuple[ChatRow, ...]
    participants: tuple[ChatParticipantRow, ...]


@dataclass(frozen=True)
class LoginEvidence:
    status_code: int
    actor_id: str | None


@dataclass(frozen=True)
class ParticipantEvidence:
    id: str
    is_active: bool


@dataclass(frozen=True)
class ChatCreateEvidence:
    status_code: int
    id: str | None
    chat_type: str | None
    participants: tuple[ParticipantEvidence, ...]


@dataclass(frozen=True)
class ChatRowsEvidence:
    chat: ChatRow | None
    participants: tuple[ChatParticipantRow, ...]


@dataclass(frozen=True)
class MessagePostEvidence:
    status_code: int | None
    message: MessageEvidence | None


@dataclass(frozen=True)
class CorrelationRows:
    database_message: MessageEvidence | None
    stored_events: tuple[StoredMessageEvent, ...]


@dataclass(frozen=True)
class CommandEvidence:
    returncode: int | None
    timed_out: bool


@dataclass(frozen=True)
class BrokerMessageEvidence:
    subject: str
    sequence: int
    envelope: object


@dataclass(frozen=True)
class BrokerErrorEvidence:
    status: int | None
    error_code: int | None


type BrokerEvidence = BrokerMessageEvidence | BrokerErrorEvidence
type Clock = Callable[[], float]
type Sleep = Callable[[float], None]


class PinnedDaemonDrift(RuntimeError):
    """Observed daemon does not match the captured authority."""


class OutageOutcome(StrEnum):
    NOT_READY = "not_ready"
    ACCEPTED = "accepted"
    FAILED = "failed"


class OutageStage(StrEnum):
    PREFLIGHT = "preflight"
    STOP = "stop"
    SEND = "send"
    RETRY = "retry"
    RESTORE = "restore"
    DRAIN = "drain"
    BROKER = "broker"
    CLEANUP = "cleanup"
    COMPLETE = "complete"


@dataclass(frozen=True)
class OutageResult:
    outcome: OutageOutcome
    stage: OutageStage


class WaitVerdict(StrEnum):
    NOT_READY = "not_ready"
    WAITED = "waited"
    EXPIRED = "expired"
    INVALID = "invalid"


class OutagePorts(Protocol):
    """Each call receives a positive operation-local deadline.

    Signed-owner reads validate the existing signature. Runtime reads use the
    explicit owner project/overlay. Container inspect/stop/start independently
    verify the observed daemon against pinned_daemon before touching the exact
    captured container ID. No creating/recreating operation exists here.
    Credentials, cookies, raw process output and HTTP bodies remain private.
    """

    def acquire_lock(self, *, deadline: Deadline) -> object | None: ...

    def release_lock(self, lease: object, *, deadline: Deadline) -> None: ...

    def read_signed_owner(self, *, deadline: Deadline) -> OwnerEvidence: ...

    def observe_runtime(
        self,
        owner: OwnerEvidence,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> RuntimeEvidence: ...

    def inspect_container(
        self,
        container_id: str,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> ContainerSnapshot | None: ...

    def read_policy(
        self,
        owner: OwnerEvidence,
        worker: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> WorkerPolicy: ...

    def read_admission(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> AdmissionEvidence: ...

    def login_admin(
        self,
        owner: OwnerEvidence,
        admin_id: str,
        *,
        deadline: Deadline,
    ) -> LoginEvidence: ...

    def create_dm_once(
        self,
        peer_id: str,
        *,
        deadline: Deadline,
    ) -> ChatCreateEvidence: ...

    def read_dm(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        chat_id: str,
        *,
        deadline: Deadline,
    ) -> ChatRowsEvidence: ...

    def pending_count(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> int: ...

    def stop_container(
        self,
        container_id: str,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> CommandEvidence: ...

    def send_message_once(
        self,
        chat_id: str,
        content: str,
        *,
        deadline: Deadline,
    ) -> MessagePostEvidence: ...

    def read_correlation(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        message_id: str,
        *,
        deadline: Deadline,
    ) -> CorrelationRows: ...

    def outbox_state(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        stored_event_id: str,
        *,
        deadline: Deadline,
    ) -> StoredEventState | None: ...

    def start_container(
        self,
        container_id: str,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> CommandEvidence: ...

    def broker_last_message(
        self,
        owner: OwnerEvidence,
        backend: ContainerSnapshot,
        subject: str,
        *,
        deadline: Deadline,
    ) -> BrokerEvidence: ...

    def close_clients(self, *, deadline: Deadline) -> None: ...


def wait_for_poll(
    deadline: Deadline, interval_seconds: float, *, sleep: Sleep
) -> WaitVerdict:
    """Unavailable bounded-wait seam, including no-progress detection."""
    return WaitVerdict.NOT_READY


def run_owned_outage(ports: OutagePorts, *, clock: Clock, sleep: Sleep) -> OutageResult:
    """Unavailable until behavioral RED; does not call any port or sleep."""
    return OutageResult(OutageOutcome.NOT_READY, OutageStage.PREFLIGHT)
