"""Pure evidence contracts for a future owned NATS outage runner.

This first slice is deliberately unavailable and performs no I/O. Signed-owner,
daemon and Compose-resource verification belong to the future bounded adapter;
inventory validation is not a substitute for those authentication checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InventoryVerdict(StrEnum):
    NOT_READY = "not_ready"
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
    """Fail closed until the pure admission checks have their observed RED."""
    return InventoryVerdict.NOT_READY
