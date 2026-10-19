"""Pure complete-Core marker boundary for a future bounded NATS transport.

No filesystem, lock, Docker, HTTP, database, coordinator or CLI is connected.
A parsed claim is conditional on trusted caller-supplied key bytes and pins;
it does not establish file provenance or observe the current Docker daemon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.owned_nats_coordinator import OwnerEvidence

MAX_OWNER_MARKER_BYTES = 65_536


class OwnerParseStatus(StrEnum):
    NOT_READY = "not_ready"
    SIGNED_METADATA = "signed_metadata"


@dataclass(frozen=True, slots=True)
class OwnerParseResult:
    status: OwnerParseStatus
    owner: OwnerEvidence | None = field(default=None, repr=False)


def parse_signed_owner_v11(
    marker_bytes: bytes,
    key_bytes: bytes,
    *,
    pinned_repository: str,
    pinned_state_root: str,
    pinned_source_sha: str,
) -> OwnerParseResult:
    """Unavailable seam; no I/O or runtime-admission claim is made."""
    del marker_bytes, key_bytes
    del pinned_repository, pinned_state_root, pinned_source_sha
    return OwnerParseResult(OwnerParseStatus.NOT_READY)
