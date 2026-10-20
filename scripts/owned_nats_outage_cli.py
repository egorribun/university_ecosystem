"""Lazy no-output facade for guarded owned Core outage acceptance.

The coordinator creates the only primary deadline and calls ``acquire_lock``
first. That callback performs bounded local source/state preflight, then builds
one lazy transport and acquires its existing lifecycle lease. All owner, Docker,
SQL, HTTP and broker operations are delegated only after that lease is retained;
restoration, close ordering and release remain coordinator-owned.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, NoReturn

from scripts import owned_nats_coordinator as coordinator
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import OutageOutcome, OutageResult, OutageStage
from scripts.owned_nats_outage import Deadline, DeadlineVerdict
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)

if TYPE_CHECKING:
    from scripts.owned_nats_owner_adapter import OwnerFilePins
    from scripts.owned_nats_transport_port import OwnedNatsTransportPort

_GIT_PATH = Path("/usr/bin/git")
_GIT_STDOUT_LIMIT = 4096
_GIT_STDERR_LIMIT = 1024
_GIT_ENV = MappingProxyType(
    {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "LANG": "C",
        "PATH": "/usr/bin:/bin",
    }
)
_SOURCE_SHA_LENGTH = 40
_DELEGATED_METHODS = frozenset(
    {
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
    }
)


class _FacadeNotReady(RuntimeError):
    """Closed non-sensitive failure inside the coordinator port boundary."""

    def __str__(self) -> str:
        return "owned NATS facade is not ready"

    def __repr__(self) -> str:
        return "<_FacadeNotReady>"


def _not_ready() -> NoReturn:
    raise _FacadeNotReady from None


def _deadline_live(deadline: object) -> bool:
    if type(deadline) is not Deadline:
        return False
    try:
        return deadline.timeout_for(1.0).verdict is DeadlineVerdict.VALID
    except Exception:
        return False


def _repository_root(deadline: Deadline) -> Path | None:
    if not _deadline_live(deadline):
        return None
    from scripts import live_stand

    if not _deadline_live(deadline):
        return None
    live_stand_path = Path(live_stand.__file__).resolve(strict=True)
    if not _deadline_live(deadline):
        return None
    repository = live_stand.REPO_ROOT.resolve(strict=True)
    if (
        not _deadline_live(deadline)
        or live_stand_path != repository / "scripts" / "live_stand.py"
    ):
        return None
    return repository


def _facade_source_path(deadline: Deadline) -> Path | None:
    if not _deadline_live(deadline):
        return None
    source_path = Path(__file__).resolve(strict=True)
    return source_path if _deadline_live(deadline) else None


def _validated_state_root(raw_path: str | Path, deadline: Deadline) -> Path | None:
    if not _deadline_live(deadline):
        return None
    from scripts import live_stand

    if not _deadline_live(deadline):
        return None
    state_root = live_stand._validated_in_place_state_root(raw_path, create=False)
    return state_root if _deadline_live(deadline) else None


def _owner_file_pins_type() -> type[OwnerFilePins]:
    from scripts.owned_nats_owner_adapter import OwnerFilePins

    return OwnerFilePins


def _transport_type() -> type[OwnedNatsTransportPort]:
    from scripts.owned_nats_transport_port import OwnedNatsTransportPort

    return OwnedNatsTransportPort


def _git_executable() -> Path:
    """Use the supported Linux runner's fixed Git path, never ambient PATH."""
    return _GIT_PATH


def _git_executable_identity(path: Path) -> tuple[int, int, int, int, int] | None:
    try:
        resolved = path.resolve(strict=True)
        if resolved != path or not resolved.is_absolute():
            return None
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o111 == 0:
            return None
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _run_git_read(
    executable: Path,
    executable_identity: tuple[int, int, int, int, int],
    repository: Path,
    command: tuple[str, ...],
    *,
    deadline: Deadline,
) -> bytes | None:
    if not _deadline_live(deadline):
        return None
    if _git_executable_identity(executable) != executable_identity:
        return None
    argv = (
        str(executable),
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-C",
        str(repository),
        *command,
    )
    request = PrivateProcessRequest(
        argv=argv,
        cwd=str(repository),
        env=_GIT_ENV,
        stdout_limit=_GIT_STDOUT_LIMIT,
        stderr_limit=_GIT_STDERR_LIMIT,
    )
    try:
        result = process.run_private_process(request, deadline=deadline)
    except Exception:
        return None
    if (
        not _deadline_live(deadline)
        or _git_executable_identity(executable) != executable_identity
        or type(result) is not PrivateProcessResult
        or result.outcome is not ProcessOutcome.EXITED
        or type(result.returncode) is not int
        or result.returncode != 0
        or result.local_cleanup is not LocalCleanup.CONFIRMED
        or type(result.stdout) is not bytes
        or len(result.stdout) > _GIT_STDOUT_LIMIT
        or type(result.stderr) is not bytes
        or result.stderr
    ):
        return None
    return result.stdout


def _prepare_owner_file_pins(
    state_dir: str | Path,
    *,
    in_place: object,
    deadline: Deadline,
) -> OwnerFilePins | None:
    """Derive exact local pins under the coordinator's acquisition deadline."""
    if (
        type(in_place) is not bool
        or in_place is not True
        or not isinstance(state_dir, (str, Path))
        or not _deadline_live(deadline)
        or os.name != "posix"
        or not callable(getattr(os, "getuid", None))
        or not callable(getattr(os, "geteuid", None))
    ):
        return None
    try:
        raw_state = str(state_dir)
        if not raw_state or "\x00" in raw_state or not Path(raw_state).is_absolute():
            return None
        state_root = _validated_state_root(raw_state, deadline)
        if (
            not _deadline_live(deadline)
            or not isinstance(state_root, Path)
            or not state_root.is_absolute()
            or state_root.resolve(strict=True) != state_root
            or not state_root.is_dir()
        ):
            return None
        repository = _repository_root(deadline)
        if repository is None:
            return None
        source_path = _facade_source_path(deadline)
        if source_path is None:
            return None
        if (
            not _deadline_live(deadline)
            or not isinstance(repository, Path)
            or not repository.is_absolute()
            or not repository.is_dir()
            or source_path != repository / "scripts" / "owned_nats_outage_cli.py"
        ):
            return None
        owner_uid = os.getuid()
        effective_uid = os.geteuid()
        if (
            type(owner_uid) is not int
            or owner_uid < 0
            or type(effective_uid) is not int
            or effective_uid != owner_uid
            or not _deadline_live(deadline)
        ):
            return None
        executable = _git_executable()
        if (
            not isinstance(executable, Path)
            or executable != _GIT_PATH
            or not executable.is_absolute()
        ):
            return None
        executable_identity = _git_executable_identity(executable)
        if executable_identity is None or not _deadline_live(deadline):
            return None
        root_output = _run_git_read(
            executable,
            executable_identity,
            repository,
            ("rev-parse", "--show-toplevel"),
            deadline=deadline,
        )
        if root_output != os.fsencode(str(repository)) + b"\n":
            return None
        revision_output = _run_git_read(
            executable,
            executable_identity,
            repository,
            ("rev-parse", "--verify", "--end-of-options", "HEAD^{commit}"),
            deadline=deadline,
        )
        if (
            revision_output is None
            or len(revision_output) != _SOURCE_SHA_LENGTH + 1
            or revision_output[-1:] != b"\n"
            or any(byte not in b"0123456789abcdef" for byte in revision_output[:-1])
        ):
            return None
        status_output = _run_git_read(
            executable,
            executable_identity,
            repository,
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ),
            deadline=deadline,
        )
        if status_output != b"" or not _deadline_live(deadline):
            return None
        pins_type = _owner_file_pins_type()
        if not _deadline_live(deadline):
            return None
        return pins_type(
            repository=str(repository),
            state_root=str(state_root),
            source_sha=revision_output[:-1].decode("ascii"),
            owner_uid=owner_uid,
        )
    except Exception:
        return None


def _make_transport(
    owner_pins: OwnerFilePins, *, sleep: object
) -> OwnedNatsTransportPort:
    transport_type = _transport_type()
    return transport_type.for_owned_core(owner_pins, sleep=sleep)


class _LazyOwnedNatsPorts:
    """Acquire one local lease before enabling any owner-scoped transport call."""

    __slots__ = (
        "_attempted",
        "_in_place",
        "_lease",
        "_sleep",
        "_state_dir",
        "_transport",
    )

    def __init__(
        self, state_dir: str | Path, *, in_place: object, sleep: object
    ) -> None:
        self._state_dir = state_dir
        self._in_place = in_place
        self._sleep = sleep
        self._transport: Any | None = None
        self._lease: object | None = None
        self._attempted = False

    def acquire_lock(self, *, deadline: Deadline) -> object | None:
        if (
            self._attempted
            or type(self._in_place) is not bool
            or self._in_place is not True
            or not isinstance(self._state_dir, (str, Path))
        ):
            return None
        self._attempted = True
        pins = _prepare_owner_file_pins(
            self._state_dir,
            in_place=self._in_place,
            deadline=deadline,
        )
        if not callable(self._sleep) or not _deadline_live(deadline):
            return None
        try:
            pins_type = _owner_file_pins_type()
            if not _deadline_live(deadline) or type(pins) is not pins_type:
                return None
            transport = _make_transport(pins, sleep=self._sleep)
            transport_type = _transport_type()
        except Exception:
            return None
        if type(transport) is not transport_type:
            return None
        self._transport = transport
        if not _deadline_live(deadline):
            return None
        try:
            lease = transport.acquire_lock(deadline=deadline)
        except Exception:
            return None
        if lease is not None:
            # Preserve a late lease so the coordinator's finally can release it.
            self._lease = lease
        return lease

    def release_lock(self, lease: object, *, deadline: Deadline) -> None:
        transport = self._transport
        if transport is None or lease is not self._lease:
            _not_ready()
        transport.release_lock(lease, deadline=deadline)
        self._lease = None

    def close_clients(self, *, deadline: Deadline) -> None:
        transport = self._transport
        if transport is not None:
            transport.close_clients(deadline=deadline)

    def __getattr__(self, name: str) -> Any:
        if name not in _DELEGATED_METHODS:
            raise AttributeError(name)

        def operation(*args: object, deadline: Deadline) -> object:
            transport = self._transport
            lease = self._lease
            if transport is None or lease is None or not _deadline_live(deadline):
                _not_ready()
            try:
                result = getattr(transport, name)(*args, deadline=deadline)
            except Exception:
                raise _FacadeNotReady from None
            if self._lease is not lease or not _deadline_live(deadline):
                _not_ready()
            return result

        return operation

    def __repr__(self) -> str:
        return "<_LazyOwnedNatsPorts>"


def run_owned_nats_outage(state_dir: str | Path, *, in_place: object) -> OutageResult:
    """Run the coordinator once for guarded owned Core acceptance."""
    ports = _LazyOwnedNatsPorts(
        state_dir,
        in_place=in_place,
        sleep=time.sleep,
    )
    try:
        return coordinator.run_owned_outage(
            ports,
            clock=time.monotonic,
            sleep=time.sleep,
        )
    except Exception:
        return OutageResult(OutageOutcome.FAILED, OutageStage.PREFLIGHT)
