"""In-memory raw evidence for owned coordinator safety tests."""

from __future__ import annotations

from dataclasses import dataclass, replace

from scripts.owned_nats_coordinator import (
    AdmissionEvidence,
    BrokerMessageEvidence,
    ChatCreateEvidence,
    ChatParticipantRow,
    ChatRow,
    ChatRowsEvidence,
    CommandEvidence,
    CorrelationRows,
    LoginEvidence,
    MessagePostEvidence,
    OwnerEvidence,
    ParticipantEvidence,
    PgRoleRow,
    PinnedDaemonDrift,
    PrincipalEvidence,
    RuntimeEvidence,
    UserRow,
)
from scripts.owned_nats_outage import (
    ContainerSnapshot,
    Deadline,
    DeadlineVerdict,
    MessageEvidence,
    StoredEventState,
    StoredMessageEvent,
    WorkerPolicy,
)
from tests.helpers.owned_nats_acceptance import CORE_SERVICES, core_container_snapshots

ADMIN = "10000000-0000-4000-8000-000000000001"
PEER = "10000000-0000-4000-8000-000000000002"
CHAT = "10000000-0000-4000-8000-000000000003"
MESSAGE = "10000000-0000-4000-8000-000000000004"
EVENT = "10000000-0000-4000-8000-000000000005"
OTHER = "10000000-0000-4000-8000-000000000006"
CONTENT = "owned NATS acceptance probe"
DAEMON = "d" * 64
RESOURCE = "e" * 64
_UNSET = object()
OWNER_PORT_NAMES = (
    "BACKEND",
    "FRONTEND",
    "POSTGRES",
    "GATEWAY",
    "WS_HUB",
    "TEMPORAL_GRPC",
    "TEMPORAL_WEB",
    "IMGPROXY",
    "GRAFANA",
    "PROMETHEUS",
    "ALLOY",
    "PYROSCOPE",
    "CADDY_HTTP",
    "CADDY_HTTPS",
    "MINIO",
    "MAILPIT",
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeSleeper:
    def __init__(self, clock: FakeClock, *, advances: bool = True) -> None:
        self.clock = clock
        self.advances = advances
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        assert 0 < seconds <= 120
        assert len(self.calls) < 1000, "polling must remain bounded"
        self.calls.append(seconds)
        if self.advances:
            self.clock.now += seconds


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple[object, ...]
    deadline: Deadline
    started_at: float


class FakePorts:
    """Known protocol operations with raw scripted evidence, never verdicts."""

    def __init__(self) -> None:
        self.clock = FakeClock()
        self.sleep = FakeSleeper(self.clock)
        self.calls: list[Call] = []
        self.contract_errors: list[str] = []
        self.script: dict[str, list[object]] = {}
        self.advance: dict[str, float] = {}
        self.stopped = False
        self.restore_started = False
        self.restored_healthy_at = 0.0
        self.stop_attempted = False
        self.keep_running_after_stop = False
        self.owner_after_stop: OwnerEvidence | None = None
        self.resource_after_stop: str | None = None
        self.daemon_drift_after_stop = False
        self.runtime_daemon = DAEMON
        self.lease = object()
        self.inspection_after_stop: object = _UNSET
        self.records = core_container_snapshots()
        self.records_after_start: tuple[ContainerSnapshot, ...] | None = None
        self.nats = next(record for record in self.records if record.service == "nats")
        self.owner = OwnerEvidence(
            repository="/workspace/owned-nats-repo",
            worktree="/tmp/ue-live-acceptance/run-owned-nats-core",
            project_name="ue-live-0123456789abcdef",
            published_ports=tuple(
                (name, 20000 + index) for index, name in enumerate(OWNER_PORT_NAMES)
            ),
            schema_version=11,
            daemon_fingerprint=DAEMON,
            compose_resource_fingerprint=RESOURCE,
            resume_compose_resource_fingerprint=None,
            resume_compose_resource_schema_version=None,
            source_sha="a" * 40,
            stack="core",
            service_roots=(
                "caddy",
                "mailpit",
                "notifications-worker",
                "outbox-worker",
                "spicedb",
            ),
            selected_services=CORE_SERVICES,
        )
        self.admission = AdmissionEvidence(
            principal=PrincipalEvidence(
                session_user="fixture_owner",
                current_user="fixture_owner",
                pg_role=PgRoleRow("fixture_owner", True),
            ),
            users=(
                UserRow(ADMIN, "admin@university.dev", "admin", True, None),
                UserRow(
                    PEER,
                    "demo.peer@example.com",
                    "student",
                    True,
                    "ue-demo-v1:user:primary-peer",
                ),
            ),
            chats=(),
            participants=(),
        )
        self.chat = ChatCreateEvidence(
            200,
            CHAT,
            "dm",
            (ParticipantEvidence(ADMIN, True), ParticipantEvidence(PEER, True)),
        )
        self.chat_rows = ChatRowsEvidence(
            ChatRow(CHAT, "dm", None),
            (ChatParticipantRow(CHAT, ADMIN), ChatParticipantRow(CHAT, PEER)),
        )
        self.message = MessageEvidence(MESSAGE, CHAT, ADMIN, CONTENT)
        self.event = StoredMessageEvent(
            EVENT,
            "chat.message_sent",
            "Message",
            MESSAGE,
            {
                "_schema_version": 1,
                "message_id": MESSAGE,
                "chat_id": CHAT,
                "sender_id": ADMIN,
                "content_preview": CONTENT[:50],
            },
        )
        self.broker = BrokerMessageEvidence(
            f"chat.{CHAT}",
            1,
            {
                "type": "new_message",
                "room": CHAT,
                "payload": {
                    "type": "new_message",
                    "chat_id": CHAT,
                    "message": {
                        "id": MESSAGE,
                        "chat_id": CHAT,
                        "sender_id": ADMIN,
                        "content": CONTENT,
                    },
                },
            },
        )

    def snapshot(self) -> ContainerSnapshot:
        if self.stopped:
            return replace(self.nats, running=False, status="exited", health=None)
        if self.restore_started and self.clock.now < self.restored_healthy_at:
            return replace(self.nats, health="starting")
        return self.nats

    def runtime(self) -> RuntimeEvidence:
        source = (
            self.records_after_start
            if self.restore_started and self.records_after_start is not None
            else self.records
        )
        records = tuple(
            self.snapshot() if record.service == "nats" else record
            for record in source
        )
        resource = (
            self.resource_after_stop
            if self.stop_attempted and self.resource_after_stop is not None
            else RESOURCE
        )
        return RuntimeEvidence(self.runtime_daemon, resource, records)

    def _default(self, name: str) -> object:
        defaults = {
            "acquire_lock": lambda: self.lease,
            "release_lock": lambda: None,
            "read_signed_owner": lambda: (
                self.owner_after_stop
                if self.stop_attempted and self.owner_after_stop is not None
                else self.owner
            ),
            "observe_runtime": self.runtime,
            "inspect_container": lambda: (
                self.inspection_after_stop
                if self.stop_attempted and self.inspection_after_stop is not _UNSET
                else self.snapshot()
            ),
            "read_policy": lambda: WorkerPolicy(1, 2, 5),
            "read_admission": lambda: self.admission,
            "login_admin": lambda: LoginEvidence(200, ADMIN),
            "create_dm_once": lambda: self.chat,
            "read_dm": lambda: self.chat_rows,
            "pending_count": lambda: 0,
            "stop_container": lambda: CommandEvidence(0, False),
            "send_message_once": lambda: MessagePostEvidence(200, self.message),
            "read_correlation": lambda: CorrelationRows(self.message, (self.event,)),
            "outbox_state": lambda: StoredEventState(EVENT, not self.stopped, 1, 0),
            "start_container": lambda: CommandEvidence(0, False),
            "broker_last_message": lambda: self.broker,
            "close_clients": lambda: None,
        }
        return defaults[name]()

    def _invoke(
        self, name: str, args: tuple[object, ...], deadline: Deadline
    ) -> object:
        self.calls.append(Call(name, args, deadline, self.clock.now))
        maximum = 15 if name == "stop_container" else 10
        if (
            deadline.timeout_for(maximum).verdict is not DeadlineVerdict.VALID
            or deadline.expires_at is None
            or not 0 < deadline.expires_at - self.clock.now <= maximum
        ):
            self.contract_errors.append("operation deadline was not bounded")
            raise AssertionError("invalid operation deadline")
        if name == "release_lock" and args != (self.lease,):
            self.contract_errors.append("release targeted a different lease")
            raise AssertionError("invalid lock lease")
        if (
            name in {"inspect_container", "start_container", "stop_container"}
            and args != (self.nats.container_id, DAEMON)
        ):
            self.contract_errors.append("operation targeted a different container")
            raise AssertionError("invalid container authority")
        if (
            name in {"inspect_container", "start_container", "observe_runtime"}
            and self.stop_attempted
            and self.daemon_drift_after_stop
        ):
            raise PinnedDaemonDrift("private daemon details")
        if name == "stop_container":
            self.stop_attempted = True
            self.stopped = not self.keep_running_after_stop
        queue = self.script.get(name)
        if queue:
            value = queue.pop(0) if len(queue) > 1 else queue[0]
        else:
            value = self._default(name)
        self.clock.now += self.advance.get(name, 0)
        if isinstance(value, BaseException):
            raise value
        if name == "start_container" and value == CommandEvidence(0, False):
            self.stopped = False
            self.restore_started = True
        return value

    def __getattr__(self, name: str):
        if name not in PORT_NAMES:
            raise AttributeError(name)

        def operation(*args: object, deadline: Deadline) -> object:
            return self._invoke(name, args, deadline)

        return operation


PORT_NAMES = frozenset(
    {
        "acquire_lock",
        "release_lock",
        "read_signed_owner",
        "observe_runtime",
        "inspect_container",
        "read_policy",
        "read_admission",
        "login_admin",
        "create_dm_once",
        "read_dm",
        "pending_count",
        "stop_container",
        "send_message_once",
        "read_correlation",
        "outbox_state",
        "start_container",
        "broker_last_message",
        "close_clients",
    }
)
