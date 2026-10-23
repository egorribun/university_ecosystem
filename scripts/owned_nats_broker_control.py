"""Private bounded primitives for an existing owner-scoped NATS outage.

This module is preparatory only: it exposes no command, coordinator, workflow,
Docker launch, database operation, or runtime activation. Control operations
use only the original captured NATS container ID. Broker reads use only the
existing CHAT_EVENTS stream. Local process reaping is not treated as proof that
an unfinished remote Docker exec has stopped; only a complete private response
containing the probe's successful bounded-close marker can yield receipt data.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit
from uuid import UUID

from scripts import owned_nats_docker as docker
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import (
    BrokerErrorEvidence,
    BrokerMessageEvidence,
    BrokerProbePhase,
    CommandEvidence,
    OwnerEvidence,
    RuntimeEvidence,
)
from scripts.owned_nats_docker import ComposeConfigPins, DockerReadPins
from scripts.owned_nats_outage import ContainerSnapshot, Deadline, DeadlineVerdict
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)
from scripts.owned_nats_runtime_adapter import OwnedCoreRuntimePort

_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_NATS_ENV_NAMES = frozenset({"NATS_URL", "NATS_AUTH_TOKEN", "NATS_AUTH_TOKEN_FILE"})
_NATS_SERVICES = frozenset({"backend", "outbox-worker"})
_COMPOSE_CONFIG_MAX = 1_048_576
_COMPOSE_DEPTH_MAX = 64
_SERVICE_INSPECT_STDOUT_MAX = 131_072
_SERVICE_INSPECT_STDERR_MAX = 1_024
_PROBE_STDOUT_MAX = 32_768
_PROBE_STDERR_MAX = 1_024
_PROBE_STDIN_MAX = 32_768
_PROBE_BUDGET_SECONDS = 6.0
_PROBE_POSTCHECK_RESERVE_SECONDS = 2.0


class BrokerControlNotReady(RuntimeError):
    """Closed, non-sensitive failure at this private adapter boundary."""


@dataclass(frozen=True, slots=True)
class EffectiveNatsSettings:
    """Resolved settings for the existing application services; secret fields stay hidden."""

    url: str = field(repr=False)
    endpoint_host: str
    endpoint_port: int
    token: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return "<EffectiveNatsSettings>"


@dataclass(frozen=True, slots=True)
class _RuntimeServiceInspection:
    container_id: str = field(repr=False)
    service: str
    settings: EffectiveNatsSettings | None = field(default=None, repr=False)
    running: bool | None = None
    status: str | None = None
    health: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class _PrivateBrokerMessageEvidence(BrokerMessageEvidence):
    """Coordinator evidence whose UUID/content-bearing envelope is never repr'd."""

    def __repr__(self) -> str:
        return "<BrokerMessageEvidence>"


def _live(deadline: object) -> bool:
    if type(deadline) is not Deadline:
        return False
    try:
        return deadline.timeout_for(1.0).verdict is DeadlineVerdict.VALID
    except Exception:
        return False


def _valid_container_id(value: object) -> bool:
    return type(value) is str and _CONTAINER_ID.fullmatch(value) is not None


def _canonical_subject(value: object) -> bool:
    if type(value) is not str or not value.startswith("chat."):
        return False
    chat_id = value[5:]
    if len(chat_id) != 36:
        return False
    try:
        parsed = UUID(chat_id)
    except ValueError:
        return False
    return parsed.int != 0 and str(parsed) == chat_id and value == f"chat.{parsed}"


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON value")


def _json_depth_is_bounded(value: object, max_depth: int) -> bool:
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if not isinstance(node, (dict, list)):
            continue
        if depth > max_depth:
            return False
        children = node.values() if isinstance(node, dict) else node
        pending.extend((child, depth + 1) for child in children)
    return True


def _load_strict_json(raw: bytes, *, limit: int, max_depth: int) -> object | None:
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        return None
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        return None
    return value if _json_depth_is_bounded(value, max_depth) else None


def _service_environment(project: object, service: str) -> dict[str, object] | None:
    if type(project) is not dict:
        return None
    services = project.get("services")
    if type(services) is not dict:
        return None
    service_model = services.get(service)
    if type(service_model) is not dict:
        return None
    environment = service_model.get("environment")
    if type(environment) is not dict:
        return None
    if any(type(key) is not str for key in environment):
        return None
    return environment


def _settings_from_environment(
    environment: dict[str, object],
) -> EffectiveNatsSettings | None:
    if any(
        key.startswith("NATS_") and ("TLS" in key or "SSL" in key)
        for key in environment
    ):
        return None
    if "NATS_AUTH_TOKEN_FILE" in environment:
        # The pinned full/live Compose model does not use file-based NATS auth.
        # Refuse a changed model instead of invoking the app's unbounded helper.
        return None
    url = environment.get("NATS_URL")
    token = environment.get("NATS_AUTH_TOKEN")
    if (
        type(url) is not str
        or not 1 <= len(url) <= 4_096
        or not url.isprintable()
        or (
            token is not None
            and (type(token) is not str or not 1 <= len(token) <= 4_096)
        )
    ):
        return None
    try:
        parsed = urlsplit(url)
        endpoint_host = parsed.hostname
        endpoint_port = parsed.port
        has_username = parsed.username is not None
        has_password = parsed.password is not None
    except ValueError:
        return None
    if (
        parsed.scheme != "nats"
        or endpoint_host != "nats"
        or endpoint_port != 4222
        or parsed.path != ""
        or parsed.query != ""
        or parsed.fragment != ""
        or has_username != has_password
        or (has_username and (not parsed.username or not parsed.password))
        or (has_username and token is not None)
        or (not has_username and token is None)
    ):
        return None
    return EffectiveNatsSettings(url, endpoint_host, endpoint_port, token)


def extract_effective_nats_settings(
    project: object,
) -> EffectiveNatsSettings | None:
    """Require one explicit, equal backend/outbox-worker setting from resolved Compose."""
    backend = _service_environment(project, "backend")
    worker = _service_environment(project, "outbox-worker")
    if backend is None or worker is None:
        return None
    backend_selected = {
        name: backend[name] for name in _NATS_ENV_NAMES if name in backend
    }
    worker_selected = {name: worker[name] for name in _NATS_ENV_NAMES if name in worker}
    if backend_selected != worker_selected:
        return None
    backend_settings = _settings_from_environment(backend)
    worker_settings = _settings_from_environment(worker)
    if backend_settings is None or worker_settings is None:
        return None
    if backend_settings != worker_settings:
        return None
    return backend_settings


def _runtime_settings_map(environment: object) -> dict[str, str] | None:
    if type(environment) is not list or len(environment) > 8_192:
        return None
    selected: dict[str, str] = {}
    for entry in environment:
        if type(entry) is not str or len(entry) > 65_536 or "=" not in entry:
            return None
        key, value = entry.split("=", 1)
        if not key or not key.isprintable() or not value.isprintable():
            return None
        if key.startswith("NATS_") and ("TLS" in key or "SSL" in key):
            return None
        if key in _NATS_ENV_NAMES:
            if key in selected or not value:
                return None
            selected[key] = value
    return selected


def _decode_runtime_inspections(
    stdout: bytes,
    *,
    expected_containers: dict[str, str],
    project_name: str,
    expected: EffectiveNatsSettings,
) -> dict[str, _RuntimeServiceInspection] | None:
    if (
        type(stdout) is not bytes
        or not 0 < len(stdout) <= _SERVICE_INSPECT_STDOUT_MAX
        or type(expected_containers) is not dict
        or len(expected_containers) not in {2, 3}
        or set(expected_containers.values())
        not in ({"backend", "outbox-worker"}, {"backend", "outbox-worker", "nats"})
        or type(project_name) is not str
        or not project_name
        or type(expected) is not EffectiveNatsSettings
    ):
        return None
    if any(not _valid_container_id(cid) for cid in expected_containers):
        return None
    if len(set(expected_containers.values())) != len(expected_containers):
        return None
    lines = stdout.splitlines()
    if len(lines) != len(expected_containers) or any(not line for line in lines):
        return None
    parsed: dict[str, _RuntimeServiceInspection] = {}
    for line in lines:
        value = _load_strict_json(line, limit=_SERVICE_INSPECT_STDOUT_MAX, max_depth=16)
        if type(value) is not dict or set(value) != {"Id", "Labels", "Env", "State"}:
            return None
        cid = value.get("Id")
        labels = value.get("Labels")
        env = value.get("Env")
        state = value.get("State")
        if (
            not _valid_container_id(cid)
            or cid not in expected_containers
            or cid in parsed
            or type(labels) is not dict
            or labels.get("com.docker.compose.project") != project_name
            or labels.get("com.docker.compose.service") != expected_containers[cid]
            or labels.get("com.docker.compose.oneoff") != "False"
            or type(state) is not dict
            or set(state) != {"Running", "Status", "Health"}
            or type(state.get("Running")) is not bool
            or (
                state.get("Status") is not None and type(state.get("Status")) is not str
            )
            or (
                state.get("Health") is not None
                and (
                    type(state.get("Health")) is not dict
                    or set(state["Health"]) != {"Status"}
                    or type(state["Health"].get("Status")) is not str
                )
            )
        ):
            return None
        service = expected_containers[cid]
        if service in _NATS_SERVICES:
            current_map = _runtime_settings_map(env)
            if current_map is None:
                return None
            expected_map = {"NATS_URL": expected.url}
            if expected.token is not None:
                expected_map["NATS_AUTH_TOKEN"] = expected.token
            if current_map != expected_map:
                return None
            runtime_settings = _settings_from_environment(current_map)
            if runtime_settings != expected:
                return None
        else:
            if env != []:
                return None
            runtime_settings = None
        health = state.get("Health")
        parsed[cid] = _RuntimeServiceInspection(
            container_id=cid,
            service=service,
            settings=runtime_settings,
            running=state["Running"],
            status=state["Status"],
            health=health.get("Status") if type(health) is dict else None,
        )
    if set(parsed) != set(expected_containers):
        return None
    if {row.service for row in parsed.values()} != set(expected_containers.values()):
        return None
    return parsed


def runtime_nats_configuration_matches(
    stdout: bytes,
    *,
    expected_containers: dict[str, str],
    project_name: str,
    expected: EffectiveNatsSettings,
) -> bool:
    """Compare only private selected container settings against Compose output."""
    return (
        _decode_runtime_inspections(
            stdout,
            expected_containers=expected_containers,
            project_name=project_name,
            expected=expected,
        )
        is not None
    )


def prepare_container_control_request(
    pins: DockerReadPins,
    container_id: str,
    action: str,
    *,
    deadline: Deadline,
) -> PrivateProcessRequest | None:
    """Prepare stop/start for one exact existing ID through the pinned daemon."""
    if (
        type(pins) is not DockerReadPins
        or not _valid_container_id(container_id)
        or type(action) is not str
        or action not in {"stop", "start"}
        or not _live(deadline)
    ):
        return None
    daemon = docker.prepare_daemon_read(pins, deadline=deadline)
    if daemon is None or len(daemon.argv) < 5:
        return None
    prefix = daemon.argv[:5]
    if action == "stop":
        argv = (*prefix, "stop", "--timeout", "10", container_id)
    else:
        argv = (*prefix, "start", container_id)
    request = PrivateProcessRequest(
        argv=argv,
        cwd=daemon.cwd,
        env=dict(daemon.env),
        stdin=b"",
        stdout_limit=256,
        stderr_limit=_SERVICE_INSPECT_STDERR_MAX,
        input_limit=0,
    )
    return request if _live(deadline) else None


def prepare_runtime_nats_inspect_request(
    pins: DockerReadPins,
    expected_containers: dict[str, str],
    *,
    deadline: Deadline,
) -> PrivateProcessRequest | None:
    """Inspect exact captured service IDs and retain only what the decoder needs."""
    if (
        type(pins) is not DockerReadPins
        or type(expected_containers) is not dict
        or len(expected_containers) not in {2, 3}
        or set(expected_containers.values())
        not in ({"backend", "outbox-worker"}, {"backend", "outbox-worker", "nats"})
        or len(set(expected_containers.values())) != len(expected_containers)
        or any(not _valid_container_id(cid) for cid in expected_containers)
        or not _live(deadline)
    ):
        return None
    daemon = docker.prepare_daemon_read(pins, deadline=deadline)
    if daemon is None or len(daemon.argv) < 5:
        return None
    env_format = (
        '{{if or (eq (index .Config.Labels "com.docker.compose.service") "backend") '
        '(eq (index .Config.Labels "com.docker.compose.service") "outbox-worker")}}'
        "{{ $first := true }}{{range .Config.Env}}"
        '{{ $key := index (split . "_") 0 }}{{if eq $key "NATS"}}'
        "{{if not $first}},{{end}}{{json .}}{{ $first = false }}"
        "{{end}}{{end}}{{else}}[]{{end}}"
    )
    format_string = (
        '{"Id":{{json .Id}},"Labels":{{json .Config.Labels}},"Env":'
        + env_format
        + ',"State":{"Running":{{json .State.Running}},'
        '"Status":{{json .State.Status}},"Health":'
        '{{if .State.Health}}{"Status":{{json .State.Health.Status}}}{{else}}null{{end}}}}'
    )
    request = PrivateProcessRequest(
        argv=(
            *daemon.argv[:5],
            "inspect",
            "--type",
            "container",
            "--format",
            format_string,
            *expected_containers.keys(),
        ),
        cwd=daemon.cwd,
        env=dict(daemon.env),
        stdin=b"",
        stdout_limit=_SERVICE_INSPECT_STDOUT_MAX,
        stderr_limit=_SERVICE_INSPECT_STDERR_MAX,
        input_limit=0,
    )
    return request if _live(deadline) else None


def _probe_result(
    result: object,
    *,
    deadline: Deadline,
    stdout_max: int,
    stderr_max: int,
) -> tuple[bytes, bytes] | None:
    if type(result) is not PrivateProcessResult or not _live(deadline):
        return None
    try:
        if (
            result.outcome is not ProcessOutcome.EXITED
            or type(result.returncode) is not int
            or result.returncode != 0
            or result.local_cleanup is not LocalCleanup.CONFIRMED
            or type(result.stdout) is not bytes
            or len(result.stdout) > stdout_max
            or type(result.stderr) is not bytes
            or len(result.stderr) > stderr_max
            or result.stderr != b""
        ):
            return None
        return result.stdout, result.stderr
    except AttributeError:
        return None


def decode_broker_probe_result(
    result: PrivateProcessResult,
    *,
    expected_subject: str,
    deadline: Deadline,
) -> BrokerMessageEvidence | BrokerErrorEvidence:
    """Decode only a full successful local response with the remote-close marker."""
    precheck_invalid = BrokerErrorEvidence(
        None, None, failure_phase=BrokerProbePhase.PRECHECK
    )
    execution_invalid = BrokerErrorEvidence(
        None, None, failure_phase=BrokerProbePhase.PRIVATE_EXEC
    )
    decode_invalid = BrokerErrorEvidence(
        None, None, failure_phase=BrokerProbePhase.DECODE
    )
    if not _canonical_subject(expected_subject):
        return precheck_invalid
    supplied = _probe_result(
        result,
        deadline=deadline,
        stdout_max=_PROBE_STDOUT_MAX,
        stderr_max=_PROBE_STDERR_MAX,
    )
    if supplied is None:
        return execution_invalid
    raw, _private_stderr = supplied
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        return decode_invalid
    value = _load_strict_json(raw[:-1], limit=_PROBE_STDOUT_MAX, max_depth=32)
    if type(value) is not dict:
        return decode_invalid
    kind = value.get("kind")
    if kind == "missing":
        if value.get("closed") is not True:
            return execution_invalid
        if (
            set(value) == {"kind", "closed", "status", "error_code"}
            and value.get("closed") is True
            and type(value.get("status")) is int
            and value["status"] == 404
            and type(value.get("error_code")) is int
            and value["error_code"] == 10037
            and _live(deadline)
        ):
            return BrokerErrorEvidence(404, 10037)
        return decode_invalid
    if kind == "invalid":
        if set(value) == {"kind", "closed"} and type(value.get("closed")) is bool:
            return execution_invalid
        return decode_invalid
    if kind == "message" and value.get("closed") is not True:
        return execution_invalid
    if (
        kind != "message"
        or set(value) != {"kind", "closed", "subject", "sequence", "envelope"}
        or value.get("closed") is not True
        or value.get("subject") != expected_subject
        or type(value.get("sequence")) is not int
        or value["sequence"] <= 0
        or type(value.get("envelope")) is not dict
        or not _live(deadline)
    ):
        return decode_invalid
    return _PrivateBrokerMessageEvidence(
        subject=expected_subject,
        sequence=value["sequence"],
        envelope=value["envelope"],
    )


def build_broker_probe_script(
    subject: str, *, budget_seconds: float = _PROBE_BUDGET_SECONDS
) -> bytes | None:
    """Return fixed Python stdin code; only the canonical subject and budget vary."""
    if (
        not _canonical_subject(subject)
        or type(budget_seconds) not in (int, float)
        or not math.isfinite(float(budget_seconds))
        or not 0.05 <= float(budget_seconds) <= _PROBE_BUDGET_SECONDS
    ):
        return None
    template = r"""import asyncio
import json
import os
from urllib.parse import urlsplit

from nats.aio.client import Client as NATS
from nats.js.errors import APIError

SUBJECT = __SUBJECT__
TOTAL_SECONDS = __BUDGET__
CLOSE_RESERVE_SECONDS = min(0.5, TOTAL_SECONDS / 4)
MAX_MESSAGE_BYTES = 16384
MAX_JSON_DEPTH = 32


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("invalid JSON constant")


def _depth(value):
    pending = [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if not isinstance(node, (dict, list)):
            continue
        if depth > MAX_JSON_DEPTH:
            return False
        children = node.values() if isinstance(node, dict) else node
        pending.extend((child, depth + 1) for child in children)
    return True


def _valid_settings():
    url = os.environ.get("NATS_URL")
    token = os.environ.get("NATS_AUTH_TOKEN")
    if (
        not isinstance(url, str)
        or not url
        or len(url) > 4096
        or not url.isprintable()
        or os.environ.get("NATS_AUTH_TOKEN_FILE") is not None
        or any("TLS" in name or "SSL" in name for name in os.environ if name.startswith("NATS_"))
        or (token is not None and (not token or len(token) > 4096 or not token.isprintable()))
    ):
        return None
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "nats"
            or parsed.hostname != "nats"
            or parsed.port != 4222
            or parsed.path
            or parsed.query
            or parsed.fragment
            or ((parsed.username is None) != (parsed.password is None))
            or (parsed.username is not None and (not parsed.username or not parsed.password))
            or (parsed.username is not None and token is not None)
            or (parsed.username is None and token is None)
        ):
            return None
    except ValueError:
        return None
    return url, token


async def _run():
    settings = _valid_settings()
    if settings is None:
        return {"kind": "invalid", "closed": True}
    url, token = settings
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TOTAL_SECONDS
    operation_deadline = deadline - CLOSE_RESERVE_SECONDS
    client = NATS()
    observation = {"kind": "invalid"}
    try:
        async with asyncio.timeout_at(operation_deadline):
            await client.connect(
                servers=[url],
                token=token,
                allow_reconnect=False,
                max_reconnect_attempts=0,
                connect_timeout=min(2.0, max(0.01, operation_deadline - loop.time())),
            )
            js = client.jetstream()
            try:
                message = await js.get_last_msg("CHAT_EVENTS", subject=SUBJECT, direct=False)
            except APIError as error:
                status = getattr(error, "code", None)
                error_code = getattr(error, "err_code", None)
                if type(status) is int and status == 404 and type(error_code) is int and error_code == 10037:
                    observation = {"kind": "missing", "status": 404, "error_code": 10037}
            else:
                data = getattr(message, "data", None)
                message_subject = getattr(message, "subject", None)
                sequence = getattr(message, "seq", None)
                if (
                    type(data) is bytes
                    and 0 < len(data) <= MAX_MESSAGE_BYTES
                    and type(message_subject) is str
                    and message_subject == SUBJECT
                    and type(sequence) is int
                    and sequence > 0
                ):
                    try:
                        envelope = json.loads(
                            data.decode("utf-8"),
                            object_pairs_hook=_pairs,
                            parse_constant=_constant,
                        )
                    except (UnicodeError, ValueError, RecursionError):
                        envelope = None
                    if type(envelope) is dict and _depth(envelope):
                        observation = {
                            "kind": "message",
                            "subject": message_subject,
                            "sequence": sequence,
                            "envelope": envelope,
                        }
    except BaseException:
        observation = {"kind": "invalid"}
    close_succeeded = False
    try:
        async with asyncio.timeout_at(deadline):
            await client.close()
        close_succeeded = True
    except BaseException:
        close_succeeded = False
    observation["closed"] = close_succeeded
    if not close_succeeded:
        observation = {"kind": "invalid", "closed": False}
    return observation


try:
    result = asyncio.run(_run())
    encoded = json.dumps(result, ensure_ascii=True, separators=(",", ":"))
    if len(encoded.encode("ascii")) > 32768:
        encoded = '{"kind":"invalid","closed":false}'
    print(encoded)
except BaseException:
    print('{"kind":"invalid","closed":false}')
"""
    try:
        script = template.replace("__SUBJECT__", json.dumps(subject)).replace(
            "__BUDGET__", repr(float(budget_seconds))
        )
        raw = script.encode("utf-8")
    except (UnicodeError, ValueError, TypeError):
        return None
    return raw if 0 < len(raw) <= _PROBE_STDIN_MAX else None


class OwnedNatsBrokerControlPort:
    """Partial coordinator port for exact-ID NATS control and broker storage reads.

    The complete coordinator still owns inventory admission, phase comparison,
    retry policy and restoration verdicts. This wrapper retains the first owner
    inventory and never refreshes it after drift. It intentionally does not expose
    SQL/HTTP operations or any runtime activation method.
    """

    __slots__ = (
        "_baseline",
        "_by_id",
        "_by_service",
        "_compose",
        "_owner",
        "_pins",
        "_runtime",
    )

    def __init__(
        self,
        runtime: OwnedCoreRuntimePort,
        pins: DockerReadPins,
        compose: ComposeConfigPins,
    ) -> None:
        if (
            type(runtime) is not OwnedCoreRuntimePort
            or type(pins) is not DockerReadPins
            or type(compose) is not ComposeConfigPins
        ):
            raise BrokerControlNotReady
        try:
            copied_pins = replace(pins)
            copied_compose = replace(compose)
            if (
                runtime._docker_pins != copied_pins
                or runtime._compose_pins != copied_compose
            ):
                raise BrokerControlNotReady
        except (AttributeError, TypeError, ValueError) as error:
            raise BrokerControlNotReady from error
        self._runtime = runtime
        self._pins = copied_pins
        self._compose = copied_compose
        self._owner: OwnerEvidence | None = None
        self._baseline: RuntimeEvidence | None = None
        self._by_id: dict[str, ContainerSnapshot] = {}
        self._by_service: dict[str, ContainerSnapshot] = {}

    def _active(self, deadline: object) -> bool:
        if not _live(deadline):
            return False
        try:
            return self._runtime._same_active_lease()
        except Exception:
            return False

    def acquire_lock(self, *, deadline: Deadline) -> object | None:
        if not _live(deadline):
            return None
        try:
            return self._runtime.acquire_lock(deadline=deadline)
        except Exception:
            return None

    def release_lock(self, lease: object, *, deadline: Deadline) -> None:
        if not self._active(deadline):
            raise BrokerControlNotReady
        try:
            self._runtime.release_lock(lease, deadline=deadline)
        except Exception:
            raise BrokerControlNotReady from None

    def read_signed_owner(self, *, deadline: Deadline) -> OwnerEvidence:
        if not self._active(deadline):
            raise BrokerControlNotReady
        try:
            owner = self._runtime.read_signed_owner(deadline=deadline)
            if type(owner) is not OwnerEvidence:
                raise BrokerControlNotReady
            snapshot = replace(owner)
            if self._owner is None:
                self._owner = snapshot
            elif snapshot != self._owner:
                raise BrokerControlNotReady
            if not self._active(deadline):
                raise BrokerControlNotReady
            return snapshot
        except Exception:
            raise BrokerControlNotReady from None

    def _runtime_snapshot(
        self, owner: OwnerEvidence, pinned_daemon: str, deadline: Deadline
    ) -> RuntimeEvidence:
        if (
            not self._active(deadline)
            or self._owner is None
            or owner != self._owner
            or type(pinned_daemon) is not str
            or pinned_daemon != owner.daemon_fingerprint
        ):
            raise BrokerControlNotReady
        try:
            evidence = self._runtime.observe_runtime(
                owner, pinned_daemon, deadline=deadline
            )
            if (
                type(evidence) is not RuntimeEvidence
                or evidence.daemon_fingerprint != owner.daemon_fingerprint
                or evidence.resource_fingerprint != owner.compose_resource_fingerprint
                or type(evidence.containers) is not tuple
                or any(
                    type(row) is not ContainerSnapshot for row in evidence.containers
                )
                or not self._active(deadline)
            ):
                raise BrokerControlNotReady
            copied = RuntimeEvidence(
                evidence.daemon_fingerprint,
                evidence.resource_fingerprint,
                tuple(replace(row) for row in evidence.containers),
            )
            rows_by_id = {row.container_id: row for row in copied.containers}
            rows_by_service = {row.service: row for row in copied.containers}
            if (
                len(rows_by_id) != len(copied.containers)
                or len(rows_by_service) != len(copied.containers)
                or any(not _valid_container_id(cid) for cid in rows_by_id)
            ):
                raise BrokerControlNotReady
            if self._baseline is None:
                self._baseline = copied
                self._by_id = rows_by_id
                self._by_service = rows_by_service
            elif (
                copied.daemon_fingerprint != self._baseline.daemon_fingerprint
                or copied.resource_fingerprint != self._baseline.resource_fingerprint
                or set(rows_by_id) != set(self._by_id)
                or set(rows_by_service) != set(self._by_service)
                or any(
                    rows_by_id.get(cid) is None
                    or rows_by_id[cid].service != base.service
                    or rows_by_id[cid].identity != base.identity
                    for cid, base in self._by_id.items()
                )
            ):
                # Never rebase after owner, project resource, ID or identity drift.
                raise BrokerControlNotReady
            return copied
        except Exception:
            raise BrokerControlNotReady from None

    def observe_runtime(
        self,
        owner: OwnerEvidence,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> RuntimeEvidence:
        """Forward complete evidence; never run healthy admission during outage."""
        if self._owner is None:
            raise BrokerControlNotReady
        return self._runtime_snapshot(owner, pinned_daemon, deadline)

    def _baseline_target(self) -> ContainerSnapshot:
        target = self._by_service.get("nats")
        if type(target) is not ContainerSnapshot or not _valid_container_id(
            target.container_id
        ):
            raise BrokerControlNotReady
        return target

    def inspect_container(
        self, container_id: str, pinned_daemon: str, *, deadline: Deadline
    ) -> ContainerSnapshot | None:
        try:
            original = self._baseline_target()
            if (
                container_id != original.container_id
                or self._owner is None
                or pinned_daemon != self._owner.daemon_fingerprint
            ):
                return None
            current = self._runtime_snapshot(self._owner, pinned_daemon, deadline)
            target = next(
                (row for row in current.containers if row.container_id == container_id),
                None,
            )
            return (
                target
                if target is not None
                and target.identity == original.identity
                and target.service == "nats"
                else None
            )
        except Exception:
            return None

    def _others_match_baseline(self, runtime: RuntimeEvidence) -> bool:
        if self._baseline is None:
            return False
        current = {row.container_id: row for row in runtime.containers}
        if len(current) != len(runtime.containers) or set(current) != set(self._by_id):
            return False
        target = self._baseline_target()
        return all(
            current[cid] == base
            for cid, base in self._by_id.items()
            if cid != target.container_id
        )

    @staticmethod
    def _process_finished(result: object) -> tuple[bool, bool, int | None]:
        """Return (success, timed_out, returncode), never raw output."""
        if type(result) is not PrivateProcessResult:
            return False, True, None
        try:
            timed_out = (
                result.outcome is not ProcessOutcome.EXITED
                or result.local_cleanup is not LocalCleanup.CONFIRMED
            )
            if timed_out:
                return False, True, None
            if (
                type(result.returncode) is not int
                or type(result.stdout) is not bytes
                or len(result.stdout) > 256
                or type(result.stderr) is not bytes
                or len(result.stderr) > _SERVICE_INSPECT_STDERR_MAX
                or result.stderr != b""
            ):
                return False, False, 1
            return result.returncode == 0, False, result.returncode
        except AttributeError:
            return False, True, None

    def _control_container(
        self,
        container_id: str,
        pinned_daemon: str,
        *,
        action: str,
        deadline: Deadline,
    ) -> CommandEvidence:
        if not _live(deadline) or self._owner is None or self._baseline is None:
            return CommandEvidence(None, True)
        try:
            target = self._baseline_target()
            if (
                container_id != target.container_id
                or pinned_daemon != self._owner.daemon_fingerprint
            ):
                return CommandEvidence(1, False)
            before = self._runtime_snapshot(self._owner, pinned_daemon, deadline)
            before_map = {row.container_id: row for row in before.containers}
            current = before_map.get(container_id)
            if current is None or not self._others_match_baseline(before):
                return CommandEvidence(1, False)
            if action == "stop":
                if current != target:
                    return CommandEvidence(1, False)
            elif action == "start":
                if (
                    current.identity != target.identity
                    or current.service != "nats"
                    or current.restart_count != target.restart_count
                    or current.exit_code != 0
                    or current.oom_killed
                ):
                    return CommandEvidence(1, False)
                if current.running and current.status == "running":
                    # The exact captured target is already restored; avoid an
                    # unnecessary start that would fail on an already-running ID.
                    return CommandEvidence(0, False)
                if current.running or current.status != "exited":
                    return CommandEvidence(1, False)
            else:
                return CommandEvidence(1, False)
            request = prepare_container_control_request(
                self._pins, container_id, action, deadline=deadline
            )
            if request is None or not _live(deadline):
                return CommandEvidence(None, True)
            result = process.run_private_process(request, deadline=deadline)
            success, timed_out, returncode = self._process_finished(result)
            if not success:
                return CommandEvidence(returncode, timed_out)
            if not _live(deadline):
                return CommandEvidence(None, True)
            after = self._runtime_snapshot(self._owner, pinned_daemon, deadline)
            after_map = {row.container_id: row for row in after.containers}
            observed = after_map.get(container_id)
            if observed is None or not self._others_match_baseline(after):
                return CommandEvidence(1, False)
            if (
                observed.identity != target.identity
                or observed.service != "nats"
                or observed.restart_count != target.restart_count
                or observed.oom_killed
            ):
                return CommandEvidence(1, False)
            if action == "stop" and (observed.running or observed.status != "exited"):
                return CommandEvidence(1, False)
            if action == "start" and (
                not observed.running or observed.status != "running"
            ):
                return CommandEvidence(1, False)
            return CommandEvidence(0, False)
        except Exception:
            return CommandEvidence(None, not _live(deadline))

    def stop_container(
        self, container_id: str, pinned_daemon: str, *, deadline: Deadline
    ) -> CommandEvidence:
        return self._control_container(
            container_id, pinned_daemon, action="stop", deadline=deadline
        )

    def start_container(
        self, container_id: str, pinned_daemon: str, *, deadline: Deadline
    ) -> CommandEvidence:
        return self._control_container(
            container_id, pinned_daemon, action="start", deadline=deadline
        )

    def _compose_nats_settings(
        self, owner: OwnerEvidence, deadline: Deadline
    ) -> EffectiveNatsSettings | None:
        if self._owner != owner or not self._active(deadline):
            return None
        if self._runtime.read_signed_owner(deadline=deadline) != owner:
            return None
        request = docker.prepare_compose_config(
            owner, self._pins, self._compose, deadline=deadline
        )
        if request is None or not _live(deadline):
            return None
        result = process.run_private_process(request, deadline=deadline)
        decoded = docker.decode_compose_config(result, owner=owner, deadline=deadline)
        if (
            decoded.status is not docker.ComposeMetadataStatus.MATCHED_METADATA
            or decoded.evidence is None
            or not _live(deadline)
        ):
            return None
        raw = _load_strict_json(
            result.stdout,
            limit=_COMPOSE_CONFIG_MAX,
            max_depth=_COMPOSE_DEPTH_MAX,
        )
        settings = extract_effective_nats_settings(raw)
        if (
            settings is None
            or self._runtime.read_signed_owner(deadline=deadline) != owner
            or not _active_daemon_matches(
                self._pins, owner.daemon_fingerprint, deadline
            )
            or not self._active(deadline)
        ):
            return None
        return settings

    def _runtime_config_inspection(
        self,
        expected_containers: dict[str, str],
        settings: EffectiveNatsSettings,
        deadline: Deadline,
    ) -> dict[str, _RuntimeServiceInspection] | None:
        if self._owner is None or not self._active(deadline):
            return None
        request = prepare_runtime_nats_inspect_request(
            self._pins, expected_containers, deadline=deadline
        )
        if request is None:
            return None
        result = process.run_private_process(request, deadline=deadline)
        supplied = _probe_result(
            result,
            deadline=deadline,
            stdout_max=_SERVICE_INSPECT_STDOUT_MAX,
            stderr_max=_SERVICE_INSPECT_STDERR_MAX,
        )
        if supplied is None:
            return None
        inspections = _decode_runtime_inspections(
            supplied[0],
            expected_containers=expected_containers,
            project_name=self._owner.project_name,
            expected=settings,
        )
        if (
            inspections is None
            or self._runtime.read_signed_owner(deadline=deadline) != self._owner
            or not _active_daemon_matches(
                self._pins, self._owner.daemon_fingerprint, deadline
            )
            or not self._active(deadline)
        ):
            return None
        return inspections

    def _probe_request(
        self, backend_id: str, subject: str, *, deadline: Deadline
    ) -> PrivateProcessRequest | None:
        daemon = docker.prepare_daemon_read(self._pins, deadline=deadline)
        if daemon is None or len(daemon.argv) < 5:
            return None
        remaining = deadline.timeout_for(
            _PROBE_BUDGET_SECONDS + _PROBE_POSTCHECK_RESERVE_SECONDS
        )
        if remaining.verdict is not DeadlineVerdict.VALID or remaining.seconds is None:
            return None
        budget = min(
            _PROBE_BUDGET_SECONDS,
            remaining.seconds - _PROBE_POSTCHECK_RESERVE_SECONDS,
        )
        if budget < 0.05:
            return None
        script = build_broker_probe_script(subject, budget_seconds=budget)
        if script is None:
            return None
        return PrivateProcessRequest(
            argv=(*daemon.argv[:5], "exec", "-i", backend_id, "python", "-"),
            cwd=daemon.cwd,
            env=dict(daemon.env),
            stdin=script,
            stdout_limit=_PROBE_STDOUT_MAX,
            stderr_limit=_PROBE_STDERR_MAX,
            input_limit=_PROBE_STDIN_MAX,
        )

    def broker_last_message(
        self,
        owner: OwnerEvidence,
        backend: ContainerSnapshot,
        subject: str,
        *,
        deadline: Deadline,
    ) -> BrokerMessageEvidence | BrokerErrorEvidence:
        phase = BrokerProbePhase.PRECHECK

        def invalid() -> BrokerErrorEvidence:
            return BrokerErrorEvidence(None, None, failure_phase=phase)

        if (
            not _canonical_subject(subject)
            or type(backend) is not ContainerSnapshot
            or self._owner is None
            or owner != self._owner
            or not self._active(deadline)
        ):
            return invalid()
        try:
            original_backend = self._by_service.get("backend")
            original_worker = self._by_service.get("outbox-worker")
            original_nats = self._baseline_target()
            if (
                original_backend is None
                or original_worker is None
                or backend.container_id != original_backend.container_id
                or backend.identity != original_backend.identity
                or backend.service != "backend"
            ):
                return invalid()
            phase = BrokerProbePhase.RUNTIME_SNAPSHOT
            before = self._runtime_snapshot(owner, owner.daemon_fingerprint, deadline)
            before_rows = {row.service: row for row in before.containers}
            backend_now = before_rows.get("backend")
            nats_now = before_rows.get("nats")
            if (
                backend_now is None
                or nats_now is None
                or backend_now.container_id != original_backend.container_id
                or backend_now.identity != original_backend.identity
                or not backend_now.running
                or backend_now.status != "running"
                or nats_now.container_id != original_nats.container_id
                or nats_now.identity != original_nats.identity
                or not nats_now.running
                or nats_now.status != "running"
                or nats_now.health != "healthy"
            ):
                return invalid()
            phase = BrokerProbePhase.RENDER
            settings = self._compose_nats_settings(owner, deadline)
            if settings is None:
                return invalid()
            containers = {
                original_backend.container_id: "backend",
                original_worker.container_id: "outbox-worker",
                original_nats.container_id: "nats",
            }
            phase = BrokerProbePhase.RUNTIME_CONFIG
            config_rows = self._runtime_config_inspection(
                containers, settings, deadline
            )
            if config_rows is None:
                return invalid()
            post_config_backend = config_rows.get(original_backend.container_id)
            post_config_worker = config_rows.get(original_worker.container_id)
            post_config_nats = config_rows.get(original_nats.container_id)
            if (
                post_config_backend is None
                or post_config_worker is None
                or post_config_nats is None
                or post_config_nats.service != "nats"
                or post_config_nats.running is not True
                or post_config_nats.status != "running"
                or post_config_nats.health != "healthy"
            ):
                return invalid()
            phase = BrokerProbePhase.PRIVATE_EXEC
            request = self._probe_request(
                original_backend.container_id, subject, deadline=deadline
            )
            if request is None or not _live(deadline):
                return invalid()
            result = process.run_private_process(request, deadline=deadline)
            evidence = decode_broker_probe_result(
                result, expected_subject=subject, deadline=deadline
            )
            if isinstance(evidence, BrokerErrorEvidence) and evidence.status is None:
                failure_phase = evidence.failure_phase
                if type(failure_phase) is BrokerProbePhase:
                    phase = failure_phase
                return invalid()
            # Recheck the exact backend/worker/NATS IDs, NATS settings and restored
            # NATS health after the remote probe. A local CLI reaper alone is not
            # remote-process completion evidence.
            phase = BrokerProbePhase.POSTCHECK
            after_probe = self._runtime_config_inspection(
                containers, settings, deadline
            )
            if after_probe is None:
                return invalid()
            after_backend = after_probe.get(original_backend.container_id)
            after_worker = after_probe.get(original_worker.container_id)
            after_nats = after_probe.get(original_nats.container_id)
            if (
                after_backend is None
                or after_worker is None
                or after_nats is None
                or after_backend.running is not True
                or after_backend.status != "running"
                or after_nats.service != "nats"
                or after_nats.running is not True
                or after_nats.status != "running"
                or after_nats.health != "healthy"
            ):
                return invalid()
            return evidence
        except Exception:
            return invalid()

    def close_clients(self, *, deadline: Deadline) -> None:
        # NATS client state lives only inside each bounded remote probe process.
        if not _live(deadline):
            raise BrokerControlNotReady

    def __repr__(self) -> str:
        return "<OwnedNatsBrokerControlPort>"


def _active_daemon_matches(
    pins: DockerReadPins, pinned_daemon: str, deadline: Deadline
) -> bool:
    result = docker.observe_daemon_metadata(pins, deadline=deadline)
    return (
        type(result) is docker.DaemonMetadataResult
        and result.status is docker.DaemonMetadataStatus.MATCHED_METADATA
        and result.fingerprint == pinned_daemon
        and _live(deadline)
    )
