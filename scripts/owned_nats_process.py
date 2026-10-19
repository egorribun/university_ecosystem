"""Not-ready seam for a private, bounded subprocess collector.

Local process cleanup does not establish that a remote exec stopped.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from scripts.owned_nats_outage import Deadline


class ProcessOutcome(StrEnum):
    NOT_READY = "not_ready"
    EXITED = "exited"
    INVALID = "invalid"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMIT = "output_limit"
    START_FAILED = "start_failed"
    CONTAINMENT_UNAVAILABLE = "containment_unavailable"
    CLEANUP_UNCERTAIN = "cleanup_uncertain"


class LocalCleanup(StrEnum):
    NOT_STARTED = "not_started"
    CONFIRMED = "confirmed"
    UNPROVEN = "unproven"


@dataclass(frozen=True, slots=True)
class PrivateProcessRequest:
    argv: tuple[str, ...] = field(repr=False)
    cwd: str = field(repr=False)
    env: Mapping[str, str] = field(repr=False)
    stdin: bytes = field(default=b"", repr=False)
    stdout_limit: int = 65_536
    stderr_limit: int = 16_384
    input_limit: int = 65_536


@dataclass(frozen=True, slots=True)
class PrivateProcessResult:
    outcome: ProcessOutcome
    returncode: int | None
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    local_cleanup: LocalCleanup


def _process_tree_containment_available() -> bool:
    """The initial supported path is POSIX process-group containment."""
    return os.name == "posix" and callable(getattr(os, "killpg", None))


def run_private_process(
    request: PrivateProcessRequest, *, deadline: Deadline
) -> PrivateProcessResult:
    """NOT_READY placeholder; no validation, spawn, or other I/O."""
    del request, deadline
    return PrivateProcessResult(
        ProcessOutcome.NOT_READY, None, b"", b"", LocalCleanup.NOT_STARTED
    )
