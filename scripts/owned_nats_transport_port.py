"""Compose existing owner-scoped ports without enabling outage execution.

This is a coordinator-facing adapter composition only. It does not add a CLI,
workflow caller, retry policy, baseline, or restoration path. The coordinator
remains the sole phase and recovery authority.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import NoReturn, cast

from scripts import live_nats_transport as lifecycle
from scripts import owned_nats_broker_control as broker_control
from scripts import owned_nats_docker as docker
from scripts import owned_nats_http_adapter as http_adapter
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import (
    AdmissionEvidence,
    BrokerEvidence,
    ChatCreateEvidence,
    ChatRowsEvidence,
    CommandEvidence,
    CorrelationRows,
    LoginEvidence,
    MessagePostEvidence,
    OwnerEvidence,
    RuntimeEvidence,
    RuntimeObservationPhase,
)
from scripts.owned_nats_docker import ComposeConfigPins, DockerReadPins
from scripts.owned_nats_outage import (
    ContainerSnapshot,
    Deadline,
    StoredEventState,
    WorkerPolicy,
    WorkerPolicyVerdict,
    validate_worker_policy,
)
from scripts.owned_nats_owner_adapter import OwnerFilePins, SignedOwnerLeasePort
from scripts.owned_nats_process import PrivateProcessRequest, PrivateProcessResult
from scripts.owned_nats_runtime_adapter import OwnedCoreRuntimePort
from scripts.owned_nats_sql_adapter import OwnedNatsSqlAdapter

_POLICY_INSPECT_STDOUT_LIMIT = 4096
_POLICY_INSPECT_STDERR_LIMIT = 1024
_POLICY_INSPECT_FORMAT = (
    '{"id":{{json .Id}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"oneoff":{{json (index .Config.Labels "com.docker.compose.oneoff")}},'
    '"running":{{json .State.Running}},'
    '"status":{{json .State.Status}},'
    '"command_matches":{{if and (eq (len .Config.Cmd) 3) '
    '(eq (index .Config.Cmd 0) "python") '
    '(eq (index .Config.Cmd 1) "-m") '
    '(eq (index .Config.Cmd 2) "app.workers.outbox")}}true{{else}}false{{end}},'
    '"entrypoint_matches":{{if and (eq (len .Config.Entrypoint) 2) '
    '(eq (index .Config.Entrypoint 0) "/usr/bin/tini") '
    '(eq (index .Config.Entrypoint 1) "--")}}true{{else}}false{{end}}}'
    '{{println}}{{range .Config.Env}}{{ $parts := split . "=" }}'
    "{{ $key := lower (index $parts 0) }}"
    '{{if or (eq $key "outbox_poll_interval_seconds") '
    '(eq $key "outbox_batch_size") (eq $key "outbox_max_retries")}}'
    "{{println (json .)}}"
    '{{else if or (eq $key "env_file_path") (eq $key "env_example_path")}}'
    '{{if eq $key "env_file_path"}}{{println (json "ENV_FILE_PATH")}}'
    '{{else}}{{println (json "ENV_EXAMPLE_PATH")}}{{end}}'
    "{{end}}{{end}}"
)
_OUTBOX_ENV_KEYS = frozenset(
    {
        "outbox_poll_interval_seconds",
        "outbox_batch_size",
        "outbox_max_retries",
    }
)
_WORKER_DEFAULTS = WorkerPolicy(
    poll_interval_seconds=5.0,
    batch_size=20,
    max_retries=5,
)
_CANONICAL_ID = re.compile(r"[0-9a-f]{64}\Z")
_POLL_VALUE = re.compile(r"[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_INTEGER_VALUE = re.compile(r"[0-9]{1,9}\Z")


class TransportPortNotReady(RuntimeError):
    """Closed failure at the composed coordinator transport boundary."""

    def __str__(self) -> str:
        return "NATS transport is not ready"

    def __repr__(self) -> str:
        return "<TransportPortNotReady>"


def _not_ready() -> NoReturn:
    raise TransportPortNotReady from None


def _deadline_live(deadline: object) -> bool:
    return docker._live(deadline)


def _integer(value: str) -> int | None:
    if type(value) is not str or _INTEGER_VALUE.fullmatch(value) is None:
        return None
    try:
        return int(value)
    except (ValueError, OverflowError):
        return None


def _poll_interval(value: str) -> float | None:
    if type(value) is not str or _POLL_VALUE.fullmatch(value) is None:
        return None
    try:
        parsed = float(value)
    except (ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _decode_worker_policy_inspect(
    raw: bytes,
    *,
    owner: OwnerEvidence,
    worker: ContainerSnapshot,
) -> WorkerPolicy | None:
    """Decode only the selected, bounded metadata from one captured worker ID."""
    if (
        type(owner) is not OwnerEvidence
        or type(worker) is not ContainerSnapshot
        or owner.stack != "core"
        or "outbox-worker" not in owner.selected_services
        or worker.service != "outbox-worker"
        or _CANONICAL_ID.fullmatch(worker.container_id) is None
        or type(raw) is not bytes
        or not 0 < len(raw) <= _POLICY_INSPECT_STDOUT_LIMIT
        or not raw.endswith(b"\n")
    ):
        return None
    lines = raw.splitlines()
    if not 1 <= len(lines) <= 8:
        return None
    header = broker_control._load_strict_json(lines[0], limit=1024, max_depth=3)
    expected_header_keys = {
        "id",
        "project",
        "service",
        "oneoff",
        "running",
        "status",
        "command_matches",
        "entrypoint_matches",
    }
    if (
        type(header) is not dict
        or set(header) != expected_header_keys
        or type(header.get("id")) is not str
        or header["id"] != worker.container_id
        or type(header.get("project")) is not str
        or header["project"] != owner.project_name
        or type(header.get("service")) is not str
        or header["service"] != "outbox-worker"
        or type(header.get("oneoff")) is not str
        or header["oneoff"] != "False"
        or type(header.get("running")) is not bool
        or header["running"] is not True
        or type(header.get("status")) is not str
        or header["status"] != "running"
        or type(header.get("command_matches")) is not bool
        or header["command_matches"] is not True
        or type(header.get("entrypoint_matches")) is not bool
        or header["entrypoint_matches"] is not True
    ):
        return None

    supplied: dict[str, str] = {}
    for line in lines[1:]:
        entry = broker_control._load_strict_json(line, limit=1024, max_depth=2)
        if type(entry) is not str:
            return None
        if entry in {"ENV_FILE_PATH", "ENV_EXAMPLE_PATH"}:
            # These settings redirect Pydantic's config-file resolution. Their
            # raw values are intentionally neither retained nor reported.
            return None
        key, separator, value = entry.partition("=")
        normalized = key.casefold()
        if (
            not separator
            or normalized not in _OUTBOX_ENV_KEYS
            or normalized in supplied
            or len(value) > 64
        ):
            return None
        supplied[normalized] = value

    poll_raw = supplied.get("outbox_poll_interval_seconds")
    batch_raw = supplied.get("outbox_batch_size")
    retries_raw = supplied.get("outbox_max_retries")
    poll = _WORKER_DEFAULTS.poll_interval_seconds
    batch = _WORKER_DEFAULTS.batch_size
    retries = _WORKER_DEFAULTS.max_retries
    if poll_raw is not None:
        parsed_poll = _poll_interval(poll_raw)
        if parsed_poll is None:
            return None
        poll = parsed_poll
    if batch_raw is not None:
        parsed_batch = _integer(batch_raw)
        if parsed_batch is None:
            return None
        batch = parsed_batch
    if retries_raw is not None:
        parsed_retries = _integer(retries_raw)
        if parsed_retries is None:
            return None
        retries = parsed_retries
    policy = WorkerPolicy(poll, batch, retries)
    return (
        policy if validate_worker_policy(policy) is WorkerPolicyVerdict.VALID else None
    )


class OwnedNatsTransportPort:
    """Compose owner, runtime, SQL, HTTP and broker adapters for one coordinator.

    Construction is local and performs no reads. Each operation delegates once
    to the existing bounded adapter and retains its supplied absolute deadline.
    """

    __slots__ = (
        "_bootstrap_failed",
        "_bootstrap_owner",
        "_broker",
        "_compose_pins",
        "_docker_pins",
        "_http",
        "_lazy_bootstrap",
        "_owner_file_pins",
        "_owner_port",
        "_runtime",
        "_sql",
    )

    def __init__(
        self,
        owner_pins: OwnerFilePins,
        docker_pins: DockerReadPins,
        compose_pins: ComposeConfigPins,
        *,
        sleep: object,
    ) -> None:
        if (
            type(owner_pins) is not OwnerFilePins
            or type(docker_pins) is not DockerReadPins
            or type(compose_pins) is not ComposeConfigPins
            or not callable(sleep)
        ):
            _not_ready()
        try:
            self._owner_file_pins = replace(owner_pins)
            self._docker_pins = replace(docker_pins)
            self._compose_pins = replace(compose_pins)
            self._owner_port = SignedOwnerLeasePort(self._owner_file_pins, sleep=sleep)
            self._runtime = OwnedCoreRuntimePort(
                self._owner_port, self._docker_pins, self._compose_pins
            )
            self._sql = OwnedNatsSqlAdapter(
                self._owner_port, self._docker_pins, self._compose_pins
            )
            self._http = http_adapter.OwnedNatsHttpPort(
                self._owner_port, self._owner_file_pins
            )
            self._broker = broker_control.OwnedNatsBrokerControlPort(
                self._runtime, self._docker_pins, self._compose_pins
            )
            self._lazy_bootstrap = False
            self._bootstrap_failed = False
            self._bootstrap_owner: OwnerEvidence | None = None
        except Exception:
            _not_ready()

    @classmethod
    def for_owned_core(
        cls,
        owner_pins: OwnerFilePins,
        *,
        sleep: object,
    ) -> OwnedNatsTransportPort:
        """Build the fixed Core path; resolve Docker only after lease admission."""
        if type(owner_pins) is not OwnerFilePins or not callable(sleep):
            _not_ready()
        try:
            port = cls.__new__(cls)
            port._owner_file_pins = replace(owner_pins)
            port._owner_port = SignedOwnerLeasePort(port._owner_file_pins, sleep=sleep)
            port._runtime = OwnedCoreRuntimePort.for_owned_core(port._owner_port)
            port._docker_pins = None
            port._compose_pins = None
            port._sql = None
            port._http = None
            port._broker = None
            port._lazy_bootstrap = True
            port._bootstrap_failed = False
            port._bootstrap_owner = None
            return port
        except Exception:
            _not_ready()

    @property
    def runtime_diagnostic(self) -> RuntimeObservationPhase | None:
        phase = self._runtime.runtime_diagnostic
        return phase if type(phase) is RuntimeObservationPhase else None

    def __repr__(self) -> str:
        return "<OwnedNatsTransportPort>"

    def _delegate(
        self, adapter: object, method: str, *args: object, deadline: Deadline
    ) -> object:
        if (
            self._lazy_bootstrap
            or self._bootstrap_failed
            or not _deadline_live(deadline)
        ):
            _not_ready()
        try:
            result = getattr(adapter, method)(*args, deadline=deadline)
        except Exception:
            _not_ready()
        if not _deadline_live(deadline):
            _not_ready()
        return result

    def acquire_lock(self, *, deadline: Deadline) -> object | None:
        if self._lazy_bootstrap:
            if self._bootstrap_failed or not _deadline_live(deadline):
                return None
            try:
                return self._runtime.acquire_lock(deadline=deadline)
            except Exception:
                return None
        return self._delegate(self._broker, "acquire_lock", deadline=deadline)

    def release_lock(self, lease: object, *, deadline: Deadline) -> None:
        if self._lazy_bootstrap or self._bootstrap_failed:
            self._release_runtime_lease(lease, deadline=deadline)
            return
        self._delegate(self._broker, "release_lock", lease, deadline=deadline)

    def read_signed_owner(self, *, deadline: Deadline) -> OwnerEvidence:
        if self._bootstrap_failed:
            _not_ready()
        if self._lazy_bootstrap:
            lease = self._runtime._lease
            if type(
                lease
            ) is not lifecycle.LifecycleLockLease or not self._bootstrap_active(
                lease, deadline
            ):
                _not_ready()
            try:
                first_owner = self._runtime.read_signed_owner(deadline=deadline)
                if (
                    not self._bootstrap_active(lease, deadline)
                    or type(first_owner) is not OwnerEvidence
                ):
                    _not_ready()
                self._bootstrap_owner = replace(first_owner)
                self._build_lazy_adapters(deadline=deadline, lease=lease)
                if not self._bootstrap_active(lease, deadline) or self._broker is None:
                    _not_ready()
                second_owner = self._broker.read_signed_owner(deadline=deadline)
                if (
                    not self._bootstrap_active(lease, deadline)
                    or type(second_owner) is not OwnerEvidence
                    or second_owner != self._bootstrap_owner
                ):
                    _not_ready()
                result = replace(second_owner)
                if not self._bootstrap_active(lease, deadline):
                    _not_ready()
                self._docker_pins = replace(self._runtime._docker_pins)
                self._compose_pins = replace(self._runtime._compose_pins)
                self._bootstrap_owner = None
                self._lazy_bootstrap = False
                return result
            except Exception:
                self._bootstrap_failed = True
                _not_ready()
        return cast(
            OwnerEvidence,
            self._delegate(self._broker, "read_signed_owner", deadline=deadline),
        )

    def _bootstrap_active(self, lease: object, deadline: object) -> bool:
        return (
            type(lease) is lifecycle.LifecycleLockLease
            and self._runtime._lease is lease
            and self._runtime._same_active_lease()
            and _deadline_live(deadline)
        )

    def _build_lazy_adapters(
        self, *, deadline: Deadline, lease: lifecycle.LifecycleLockLease
    ) -> None:
        if (
            not self._bootstrap_active(lease, deadline)
            or type(self._runtime._docker_pins) is not DockerReadPins
            or type(self._runtime._compose_pins) is not ComposeConfigPins
            or not docker._factory_provenance_valid(self._runtime._docker_pins)
        ):
            _not_ready()
        self._docker_pins = replace(self._runtime._docker_pins)
        self._compose_pins = replace(self._runtime._compose_pins)
        self._sql = OwnedNatsSqlAdapter(
            self._owner_port, self._docker_pins, self._compose_pins
        )
        if not self._bootstrap_active(lease, deadline):
            _not_ready()
        self._http = http_adapter.OwnedNatsHttpPort(
            self._owner_port, self._owner_file_pins
        )
        if not self._bootstrap_active(lease, deadline):
            _not_ready()
        self._broker = broker_control.OwnedNatsBrokerControlPort(
            self._runtime, self._docker_pins, self._compose_pins
        )
        if not self._bootstrap_active(lease, deadline):
            _not_ready()

    def _release_runtime_lease(self, lease: object, *, deadline: Deadline) -> None:
        if (
            type(lease) is not lifecycle.LifecycleLockLease
            or self._runtime._lease is not lease
            or self._owner_port._lease is not lease
            or lease._released
            or not _deadline_live(deadline)
        ):
            _not_ready()
        try:
            self._runtime.release_lock(lease, deadline=deadline)
        except Exception:
            _not_ready()
        if self._runtime._lease is not None or self._owner_port._lease is not None:
            _not_ready()

    def observe_runtime(
        self,
        owner: OwnerEvidence,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> RuntimeEvidence:
        return cast(
            RuntimeEvidence,
            self._delegate(
                self._broker,
                "observe_runtime",
                owner,
                pinned_daemon,
                deadline=deadline,
            ),
        )

    def inspect_container(
        self,
        container_id: str,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> ContainerSnapshot | None:
        return cast(
            ContainerSnapshot | None,
            self._delegate(
                self._broker,
                "inspect_container",
                container_id,
                pinned_daemon,
                deadline=deadline,
            ),
        )

    def read_policy(
        self,
        owner: OwnerEvidence,
        worker: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> WorkerPolicy:
        try:
            return self._read_policy(owner, worker, deadline=deadline)
        except TransportPortNotReady:
            raise
        except Exception:
            _not_ready()

    def _read_policy(
        self,
        owner: OwnerEvidence,
        worker: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> WorkerPolicy:
        if not _deadline_live(deadline):
            _not_ready()
        if (
            type(owner) is not OwnerEvidence
            or type(worker) is not ContainerSnapshot
            or owner.source_sha != self._owner_file_pins.source_sha
            or owner.daemon_fingerprint != self._docker_pins.daemon_fingerprint
            or not self._policy_baseline_matches(owner, worker, deadline)
        ):
            _not_ready()
        before_owner = self._broker.read_signed_owner(deadline=deadline)
        if before_owner != owner:
            _not_ready()
        before = docker.observe_daemon_metadata(self._docker_pins, deadline=deadline)
        if (
            type(before) is not docker.DaemonMetadataResult
            or before.status is not docker.DaemonMetadataStatus.MATCHED_METADATA
            or before.fingerprint != owner.daemon_fingerprint
            or not _deadline_live(deadline)
        ):
            _not_ready()
        request = self._prepare_policy_inspect(worker, deadline=deadline)
        if request is None:
            _not_ready()
        try:
            result = process.run_private_process(request, deadline=deadline)
        except Exception:
            _not_ready()
        if not _deadline_live(deadline):
            _not_ready()
        policy = self._decode_policy_result(result, owner, worker, deadline=deadline)
        after = docker.observe_daemon_metadata(self._docker_pins, deadline=deadline)
        if not _deadline_live(deadline):
            _not_ready()
        current_owner = self._broker.read_signed_owner(deadline=deadline)
        if (
            type(after) is not docker.DaemonMetadataResult
            or after.status is not docker.DaemonMetadataStatus.MATCHED_METADATA
            or after.fingerprint != owner.daemon_fingerprint
            or current_owner != owner
            or not self._policy_baseline_matches(owner, worker, deadline)
            or policy is None
            or not _deadline_live(deadline)
        ):
            _not_ready()
        return policy

    def _policy_baseline_matches(
        self,
        owner: OwnerEvidence,
        worker: ContainerSnapshot,
        deadline: Deadline,
    ) -> bool:
        try:
            baseline = self._broker._baseline
            return (
                self._broker._active(deadline)
                and self._broker._owner == owner
                and type(baseline) is RuntimeEvidence
                and baseline.daemon_fingerprint == owner.daemon_fingerprint
                and baseline.resource_fingerprint == owner.compose_resource_fingerprint
                and self._broker._by_service.get("outbox-worker") == worker
                and self._broker._by_id.get(worker.container_id) == worker
                and worker.service == "outbox-worker"
                and worker.running is True
                and worker.status == "running"
                and _CANONICAL_ID.fullmatch(worker.container_id) is not None
                and self._broker._baseline is baseline
                and _deadline_live(deadline)
            )
        except Exception:
            return False

    def _prepare_policy_inspect(
        self,
        worker: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> PrivateProcessRequest | None:
        daemon_request = docker.prepare_daemon_read(
            self._docker_pins, deadline=deadline
        )
        if (
            type(daemon_request) is not PrivateProcessRequest
            or len(daemon_request.argv) < 6
            or daemon_request.argv[:5]
            != (
                self._docker_pins.executable,
                "--config",
                self._docker_pins.config_directory,
                "--host",
                self._docker_pins.endpoint,
            )
            or daemon_request.argv[5] != "info"
            or not _deadline_live(deadline)
        ):
            return None
        try:
            return PrivateProcessRequest(
                argv=(
                    *daemon_request.argv[:5],
                    "inspect",
                    "--type",
                    "container",
                    "--format",
                    _POLICY_INSPECT_FORMAT,
                    worker.container_id,
                ),
                cwd=daemon_request.cwd,
                env=dict(daemon_request.env),
                stdin=b"",
                stdout_limit=_POLICY_INSPECT_STDOUT_LIMIT,
                stderr_limit=_POLICY_INSPECT_STDERR_LIMIT,
                input_limit=0,
            )
        except (AttributeError, TypeError, ValueError):
            return None

    @staticmethod
    def _decode_policy_result(
        result: object,
        owner: OwnerEvidence,
        worker: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> WorkerPolicy | None:
        if (
            type(result) is not PrivateProcessResult
            or result.outcome is not process.ProcessOutcome.EXITED
            or type(result.returncode) is not int
            or result.returncode != 0
            or result.local_cleanup is not process.LocalCleanup.CONFIRMED
            or type(result.stdout) is not bytes
            or len(result.stdout) > _POLICY_INSPECT_STDOUT_LIMIT
            or type(result.stderr) is not bytes
            or len(result.stderr) > _POLICY_INSPECT_STDERR_LIMIT
            or result.stderr != b""
            or not _deadline_live(deadline)
        ):
            return None
        return _decode_worker_policy_inspect(result.stdout, owner=owner, worker=worker)

    def read_admission(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> AdmissionEvidence:
        return cast(
            AdmissionEvidence,
            self._delegate(
                self._sql, "read_admission", owner, postgres, deadline=deadline
            ),
        )

    def login_admin(
        self,
        owner: OwnerEvidence,
        admin_id: str,
        *,
        deadline: Deadline,
    ) -> LoginEvidence:
        return cast(
            LoginEvidence,
            self._delegate(
                self._http, "login_admin", owner, admin_id, deadline=deadline
            ),
        )

    def create_dm_once(
        self,
        peer_id: str,
        *,
        deadline: Deadline,
    ) -> ChatCreateEvidence:
        return cast(
            ChatCreateEvidence,
            self._delegate(self._http, "create_dm_once", peer_id, deadline=deadline),
        )

    def read_dm(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        chat_id: str,
        *,
        deadline: Deadline,
    ) -> ChatRowsEvidence:
        return cast(
            ChatRowsEvidence,
            self._delegate(
                self._sql,
                "read_dm",
                owner,
                postgres,
                chat_id,
                deadline=deadline,
            ),
        )

    def pending_count(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        *,
        deadline: Deadline,
    ) -> int:
        return cast(
            int,
            self._delegate(
                self._sql, "pending_count", owner, postgres, deadline=deadline
            ),
        )

    def stop_container(
        self,
        container_id: str,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> CommandEvidence:
        return cast(
            CommandEvidence,
            self._delegate(
                self._broker,
                "stop_container",
                container_id,
                pinned_daemon,
                deadline=deadline,
            ),
        )

    def send_message_once(
        self,
        chat_id: str,
        content: str,
        *,
        deadline: Deadline,
    ) -> MessagePostEvidence:
        return cast(
            MessagePostEvidence,
            self._delegate(
                self._http,
                "send_message_once",
                chat_id,
                content,
                deadline=deadline,
            ),
        )

    def read_correlation(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        message_id: str,
        *,
        deadline: Deadline,
    ) -> CorrelationRows:
        return cast(
            CorrelationRows,
            self._delegate(
                self._sql,
                "read_correlation",
                owner,
                postgres,
                message_id,
                deadline=deadline,
            ),
        )

    def outbox_state(
        self,
        owner: OwnerEvidence,
        postgres: ContainerSnapshot,
        stored_event_id: str,
        *,
        deadline: Deadline,
    ) -> StoredEventState | None:
        return cast(
            StoredEventState | None,
            self._delegate(
                self._sql,
                "outbox_state",
                owner,
                postgres,
                stored_event_id,
                deadline=deadline,
            ),
        )

    def start_container(
        self,
        container_id: str,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> CommandEvidence:
        return cast(
            CommandEvidence,
            self._delegate(
                self._broker,
                "start_container",
                container_id,
                pinned_daemon,
                deadline=deadline,
            ),
        )

    def broker_last_message(
        self,
        owner: OwnerEvidence,
        backend: ContainerSnapshot,
        subject: str,
        *,
        deadline: Deadline,
    ) -> BrokerEvidence:
        return cast(
            BrokerEvidence,
            self._delegate(
                self._broker,
                "broker_last_message",
                owner,
                backend,
                subject,
                deadline=deadline,
            ),
        )

    def close_clients(self, *, deadline: Deadline) -> None:
        if not _deadline_live(deadline):
            _not_ready()
        failed = False
        for adapter in (self._http, self._broker):
            if adapter is None:
                continue
            try:
                adapter.close_clients(deadline=deadline)
            except Exception:
                failed = True
        if failed or not _deadline_live(deadline):
            _not_ready()
