"""Evidence-validating coordinator for one owner-scoped NATS acceptance run.

The future adapter authenticates signed ownership and bounds every nested
operation. These projections are evidence, not authentication substitutes.
No runtime adapter or command invokes this coordinator yet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from scripts.owned_nats_outage import (
    BrokerVerdict,
    ContainerSnapshot,
    CorrelationVerdict,
    Deadline,
    DeadlineVerdict,
    InventoryVerdict,
    MessageEvidence,
    MessageIntent,
    OutboxVerdict,
    RestorationVerdict,
    StoredEventState,
    StoredMessageEvent,
    WorkerPolicy,
    WorkerPolicyVerdict,
    classify_broker_error,
    classify_outage_attempt,
    classify_outbox_drain,
    validate_broker_receipt,
    validate_inventory,
    validate_message_correlation,
    validate_restored_inventory,
    validate_worker_policy,
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
    """Sleep within the remaining budget, rejecting a stalled or invalid clock."""
    before = deadline.timeout_for(1e300)
    if before.verdict is DeadlineVerdict.EXPIRED:
        return WaitVerdict.EXPIRED
    budget = deadline.timeout_for(interval_seconds)
    if (
        before.verdict is not DeadlineVerdict.VALID
        or before.seconds is None
        or budget.verdict is not DeadlineVerdict.VALID
        or budget.seconds is None
    ):
        return WaitVerdict.INVALID
    try:
        sleep(budget.seconds)
    except Exception:
        return WaitVerdict.INVALID
    after = deadline.timeout_for(1e300)
    if after.verdict is DeadlineVerdict.EXPIRED:
        return WaitVerdict.EXPIRED
    if (
        after.verdict is not DeadlineVerdict.VALID
        or after.seconds is None
        or after.seconds >= before.seconds
    ):
        return WaitVerdict.INVALID
    return WaitVerdict.WAITED


class _EvidenceFailure(RuntimeError):
    """Private control flow with no raw transport details."""


def _require(condition: bool) -> None:
    if not condition:
        raise _EvidenceFailure


def _live(deadline: Deadline) -> None:
    _require(deadline.timeout_for(1).verdict is DeadlineVerdict.VALID)


def _call[T](
    phase: Deadline,
    operation: Callable[..., T],
    *args: object,
    cap: float = 10,
) -> T:
    local = phase.child(cap)
    _live(local)
    result = operation(*args, deadline=local)
    _live(local)
    return result


def _uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = UUID(value)
    except ValueError:
        return False
    return parsed.int != 0 and str(parsed) == value


def _fingerprint(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _same_target(
    original: ContainerSnapshot, current: ContainerSnapshot | None
) -> bool:
    return (
        isinstance(current, ContainerSnapshot)
        and current.container_id == original.container_id
        and current.service == original.service
        and current.identity == original.identity
    )


def _command_succeeded(command: CommandEvidence) -> bool:
    return (
        isinstance(command, CommandEvidence)
        and type(command.returncode) is int
        and command.returncode == 0
        and command.timed_out is False
    )


def _actors(admission: AdmissionEvidence) -> tuple[UserRow, UserRow]:
    principal = admission.principal
    _require(
        isinstance(principal.session_user, str)
        and bool(principal.session_user)
        and principal.session_user == principal.current_user
        and principal.current_user == principal.pg_role.rolname
        and principal.pg_role.rolsuper is True
    )
    _require(len(admission.users) == 2)
    admins = [row for row in admission.users if row.email == "admin@university.dev"]
    peers = [
        row
        for row in admission.users
        if row.email == "demo.peer@example.com"
        and row.demo_seed_key == "ue-demo-v1:user:primary-peer"
    ]
    _require(len(admins) == len(peers) == 1)
    admin, peer = admins[0], peers[0]
    _require(
        _uuid(admin.id)
        and _uuid(peer.id)
        and admin.id != peer.id
        and admin.role == "admin"
        and peer.role == "student"
        and admin.is_active is True
        and peer.is_active is True
    )
    for chat in admission.chats:
        participants = {
            row.user_id for row in admission.participants if row.chat_id == chat.id
        }
        _require(chat.chat_type != "dm" or not {admin.id, peer.id} <= participants)
    return admin, peer


def _chat_id(created: ChatCreateEvidence, admin: UserRow, peer: UserRow) -> str:
    _require(
        type(created.status_code) is int
        and created.status_code == 200
        and isinstance(created.id, str)
        and _uuid(created.id)
        and created.chat_type == "dm"
        and len(created.participants) == 2
        and {row.id for row in created.participants} == {admin.id, peer.id}
        and all(row.is_active is True for row in created.participants)
    )
    if created.id is None:
        raise _EvidenceFailure
    return created.id


@dataclass(frozen=True)
class _Context:
    owner: OwnerEvidence
    before: RuntimeEvidence
    daemon: str
    nats: ContainerSnapshot
    postgres: ContainerSnapshot
    backend: ContainerSnapshot
    admin: UserRow
    chat_id: str


class _Coordinator:
    def __init__(self, ports: OutagePorts, clock: Clock, sleep: Sleep) -> None:
        self.ports = ports
        self.clock = clock
        self.sleep = sleep
        self.primary = Deadline.after(180, clock=clock)
        self.stage = OutageStage.PREFLIGHT

    def _preflight(self) -> _Context:
        inventory = self.primary.child(45)
        owner = _call(inventory, self.ports.read_signed_owner)
        _require(
            owner.stack == "core"
            and _fingerprint(owner.daemon_fingerprint)
            and _fingerprint(owner.compose_resource_fingerprint)
        )
        daemon = owner.daemon_fingerprint
        if daemon is None:
            raise _EvidenceFailure
        before = _call(inventory, self.ports.observe_runtime, owner, daemon)
        _require(
            before.daemon_fingerprint == daemon
            and before.resource_fingerprint == owner.compose_resource_fingerprint
            and validate_inventory(owner.selected_services, before.containers)
            is InventoryVerdict.VALID
        )
        services = {row.service: row for row in before.containers}
        policy = _call(
            self.primary, self.ports.read_policy, owner, services["outbox-worker"]
        )
        _require(validate_worker_policy(policy) is WorkerPolicyVerdict.VALID)
        admin, peer = _actors(
            _call(self.primary, self.ports.read_admission, owner, services["postgres"])
        )
        login = _call(self.primary, self.ports.login_admin, owner, admin.id)
        _require(
            type(login.status_code) is int
            and login.status_code == 200
            and login.actor_id == admin.id
        )
        created = _call(self.primary, self.ports.create_dm_once, peer.id)
        chat_id = _chat_id(created, admin, peer)
        rows = _call(
            self.primary, self.ports.read_dm, owner, services["postgres"], chat_id
        )
        _require(
            rows.chat is not None
            and rows.chat.id == chat_id
            and rows.chat.chat_type == "dm"
            and rows.chat.demo_seed_key is None
            and len(rows.participants) == 2
            and {row.user_id for row in rows.participants} == {admin.id, peer.id}
            and all(row.chat_id == chat_id for row in rows.participants)
        )
        return _Context(
            owner,
            before,
            daemon,
            services["nats"],
            services["postgres"],
            services["backend"],
            admin,
            chat_id,
        )

    def _unchanged_owner(self, context: _Context, phase: Deadline) -> None:
        _require(_call(phase, self.ports.read_signed_owner) == context.owner)

    def _runtime(self, context: _Context, phase: Deadline) -> RuntimeEvidence:
        runtime = _call(
            phase, self.ports.observe_runtime, context.owner, context.daemon
        )
        _require(
            runtime.daemon_fingerprint == context.daemon
            and runtime.resource_fingerprint == context.before.resource_fingerprint
        )
        return runtime

    def _stopped(self, context: _Context) -> None:
        self._unchanged_owner(context, self.primary)
        runtime = self._runtime(context, self.primary)
        original = {row.container_id: row for row in context.before.containers}
        current = {row.container_id: row for row in runtime.containers}
        _require(
            len(current) == len(runtime.containers) and set(current) == set(original)
        )
        for container_id, row in current.items():
            if container_id != context.nats.container_id:
                _require(row == original[container_id])
            else:
                _require(
                    _same_target(context.nats, row)
                    and row.running is False
                    and row.status == "exited"
                    and row.oom_killed is False
                )
        inspected = _call(
            self.primary,
            self.ports.inspect_container,
            context.nats.container_id,
            context.daemon,
        )
        _require(
            _same_target(context.nats, inspected)
            and inspected is not None
            and inspected.running is False
            and inspected.status == "exited"
        )

    def _wait(self, phase: Deadline) -> None:
        _require(wait_for_poll(phase, 1, sleep=self.sleep) is WaitVerdict.WAITED)

    def _complete_inventory(self, context: _Context, phase: Deadline) -> None:
        self._unchanged_owner(context, phase)
        runtime = self._runtime(context, phase)
        _require(
            validate_restored_inventory(
                context.owner.selected_services,
                context.before.containers,
                runtime.containers,
            )
            is RestorationVerdict.VALID
        )

    def _restore(self, context: _Context) -> None:
        recovery = Deadline.after(120, clock=self.clock)
        target = _call(
            recovery,
            self.ports.inspect_container,
            context.nats.container_id,
            context.daemon,
        )
        _require(_same_target(context.nats, target))
        started = _call(
            recovery,
            self.ports.start_container,
            context.nats.container_id,
            context.daemon,
        )
        _require(_command_succeeded(started))
        while True:
            target = _call(
                recovery,
                self.ports.inspect_container,
                context.nats.container_id,
                context.daemon,
            )
            _require(_same_target(context.nats, target))
            if (
                target is not None
                and target.running is True
                and target.health == "healthy"
            ):
                break
            self._wait(recovery)
        self._complete_inventory(context, recovery)

    def _send_and_observe(self, context: _Context) -> tuple[MessageEvidence, str, int]:
        self.stage = OutageStage.SEND
        content = "owned NATS acceptance probe"
        response = _call(
            self.primary, self.ports.send_message_once, context.chat_id, content
        )
        _require(
            type(response.status_code) is int
            and response.status_code == 200
            and response.message is not None
        )
        message = response.message
        if message is None:
            raise _EvidenceFailure
        rows = _call(
            self.primary,
            self.ports.read_correlation,
            context.owner,
            context.postgres,
            message.message_id,
        )
        _require(
            rows.database_message is not None
            and validate_message_correlation(
                MessageIntent(context.chat_id, context.admin.id, content),
                message,
                rows.database_message,
                rows.stored_events,
            )
            is CorrelationVerdict.VALID
        )
        event_id = rows.stored_events[0].event_id
        self.stage = OutageStage.RETRY
        retry = self.primary.child(30)
        while True:
            state = _call(
                retry,
                self.ports.outbox_state,
                context.owner,
                context.postgres,
                event_id,
            )
            verdict = classify_outage_attempt(event_id, state)
            if verdict is OutboxVerdict.RETRYABLE and state is not None:
                return message, event_id, state.error_count
            _require(verdict is OutboxVerdict.WAIT)
            self._wait(retry)

    def _delivery(
        self,
        context: _Context,
        message: MessageEvidence,
        event_id: str,
        retry_count: int,
    ) -> None:
        self.stage = OutageStage.DRAIN
        drain = self.primary.child(60)
        while True:
            state = _call(
                drain,
                self.ports.outbox_state,
                context.owner,
                context.postgres,
                event_id,
            )
            verdict = classify_outbox_drain(event_id, retry_count, state)
            if verdict is OutboxVerdict.DRAINED:
                break
            _require(verdict is OutboxVerdict.WAIT)
            self._wait(drain)
        self.stage = OutageStage.BROKER
        receipt = self.primary.child(45)
        while True:
            evidence = _call(
                receipt,
                self.ports.broker_last_message,
                context.owner,
                context.backend,
                f"chat.{context.chat_id}",
            )
            if isinstance(evidence, BrokerMessageEvidence):
                _require(
                    validate_broker_receipt(
                        message,
                        subject=evidence.subject,
                        sequence=evidence.sequence,
                        envelope=evidence.envelope,
                    )
                    is BrokerVerdict.VALID
                )
                return
            _require(
                isinstance(evidence, BrokerErrorEvidence)
                and classify_broker_error(evidence.status, evidence.error_code)
                is BrokerVerdict.MISSING
            )
            self._wait(receipt)

    def run(self) -> OutageResult:
        lease: object | None = None
        accepted = False
        try:
            acquisition = self.primary.child(10)
            _live(acquisition)
            lease = self.ports.acquire_lock(deadline=acquisition)
            _live(acquisition)
            _require(lease is not None)
            context = self._preflight()
            count = _call(
                self.primary, self.ports.pending_count, context.owner, context.postgres
            )
            _require(type(count) is int and count == 0)
            self.stage = OutageStage.STOP
            stop_attempted = False
            try:
                stop_deadline = self.primary.child(15)
                _live(stop_deadline)
                # From this point even an exception can mean a partial stop.
                stop_attempted = True
                command = self.ports.stop_container(
                    context.nats.container_id,
                    context.daemon,
                    deadline=stop_deadline,
                )
                _live(stop_deadline)
                _require(_command_succeeded(command))
                self._stopped(context)
                message, event_id, retry_count = self._send_and_observe(context)
            finally:
                if stop_attempted:
                    previous_stage = self.stage
                    self.stage = OutageStage.RESTORE
                    self._restore(context)
                    self.stage = previous_stage
            _live(self.primary)
            self._delivery(context, message, event_id, retry_count)
            self._complete_inventory(context, self.primary)
            accepted = True
        except Exception:
            # Neither private exception text nor raw evidence leaves this boundary.
            accepted = False
        finally:
            try:
                _call(Deadline.after(10, clock=self.clock), self.ports.close_clients)
            except Exception:
                accepted = False
                self.stage = OutageStage.CLEANUP
            finally:
                if lease is not None:
                    try:
                        _call(
                            Deadline.after(10, clock=self.clock),
                            self.ports.release_lock,
                            lease,
                        )
                    except Exception:
                        accepted = False
                        self.stage = OutageStage.CLEANUP
        if accepted:
            return OutageResult(OutageOutcome.ACCEPTED, OutageStage.COMPLETE)
        return OutageResult(OutageOutcome.FAILED, self.stage)


def run_owned_outage(ports: OutagePorts, *, clock: Clock, sleep: Sleep) -> OutageResult:
    """Coordinate owned Core outage evidence without claiming live proof."""
    return _Coordinator(ports, clock, sleep).run()
