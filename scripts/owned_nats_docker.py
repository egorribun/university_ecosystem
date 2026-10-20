"""Unavailable no-I/O boundaries for a future pinned Docker observation.

Prepared requests and supplied process results do not prove execution,
executable/config provenance, daemon authenticity or complete inventory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_process import PrivateProcessRequest, PrivateProcessResult


@dataclass(frozen=True, slots=True)
class DockerReadPins:
    executable: str = field(repr=False)
    endpoint: str = field(repr=False)
    config_directory: str = field(repr=False)
    cwd: str = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    daemon_fingerprint: str = field(repr=False)


class DaemonMetadataStatus(StrEnum):
    NOT_READY = "not_ready"
    MATCHED_METADATA = "matched_metadata"


@dataclass(frozen=True, slots=True)
class DaemonMetadataResult:
    status: DaemonMetadataStatus
    fingerprint: str | None = field(default=None, repr=False)


def prepare_daemon_read(
    pins: DockerReadPins, *, deadline: Deadline
) -> PrivateProcessRequest | None:
    """Unavailable request-only seam; never starts a process."""
    return None


def decode_daemon_read(
    result: PrivateProcessResult,
    *,
    pinned_daemon: str,
    deadline: Deadline,
) -> DaemonMetadataResult:
    """Unavailable classification of caller-supplied private bytes."""
    return DaemonMetadataResult(DaemonMetadataStatus.NOT_READY)
