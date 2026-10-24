"""Non-executing RED-stage contracts for owned client-IP acceptance.

This candidate admits no execution and accepts no observations yet. These pure
interfaces do not authenticate ownership: a later, separately reviewed adapter
must obtain pins from the existing signed-owner/daemon/resource verification,
execute only the fixed probe, and revalidate after its remote-close marker.
No Docker, HTTP, Redis, credentials, deployment, or audit-ledger wiring belongs
to this stage. Gateway and deployment acceptance remain explicitly unassessed.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.owned_nats_process import PrivateProcessResult


@dataclass(frozen=True, slots=True, repr=False)
class ClientRoute:
    network: str
    network_id: str
    subnet: str
    source_ip: str
    caddy_ip: str


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionPins:
    source_sha: str
    owner_identity: str
    daemon_identity: str
    resource_identity: str
    # Ordered backend, Caddy, gateway, ws-hub, obtained from verified inventory.
    container_ids: tuple[str, ...]
    image_ids: tuple[str, ...]
    routes: tuple[ClientRoute, ...]
    # Ordered backend, gateway, ws-hub. Each retains its independent peer list.
    trusted_proxies: tuple[tuple[str, ...], ...]
    # Login, register, MFA, forgot-password and ws-hub; never changed by probes.
    limits: tuple[int, ...]
    backend_command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaseObservation:
    case: str
    allowed: tuple[int, ...]
    blocked: int
    other_client: int
    spoofed: tuple[int, ...]
    direct_untrusted: int
    elapsed_ms: int


@dataclass(frozen=True, slots=True, repr=False)
class ProbeObservations:
    source_sha: str
    run_id: str
    cases: tuple[CaseObservation, ...]
    http_requests: int
    elapsed_ms: int


@dataclass(frozen=True, slots=True)
class SubsetVerdict:
    backend: bool
    ws_hub: bool
    gateway: str = "not_assessed"
    deployment: str = "not_assessed"


def validate_admission(
    expected: AdmissionPins,
    current: AdmissionPins,
    *,
    now_ms: int,
    deadline_ms: int,
) -> bool:
    """RED stub: reject until structural and unchanged-pin checks are implemented."""
    return False


def decode_observations(
    result: PrivateProcessResult,
    *,
    expected_source_sha: str,
    expected_run_id: str,
    now_ms: int,
    deadline_ms: int,
) -> ProbeObservations | None:
    """RED stub: never treat local cleanup alone as remote completion evidence."""
    return None


def evaluate_observations(observed: ProbeObservations) -> SubsetVerdict:
    """RED stub: report neither subset as passing until actual statuses are checked."""
    return SubsetVerdict(backend=False, ws_hub=False)
