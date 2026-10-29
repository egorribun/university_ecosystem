"""Pure, bounded contracts for owned client-IP acceptance.

These interfaces do not authenticate ownership or execute probes. A separately
reviewed adapter must obtain pins from existing signed-owner/daemon/resource
verification, execute only the fixed probe, and revalidate after its remote-close
marker. Local child reaping alone is not remote completion evidence.
No Docker, HTTP, Redis, credentials, deployment, or audit-ledger wiring belongs
to this module. Gateway and deployment acceptance remain explicitly unassessed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessResult,
    ProcessOutcome,
)

_HEX = re.compile(r"[0-9a-f]+\Z")
_PRIVATE_NETWORKS = tuple(
    IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_SOURCE_LABELS = ("public", "frontend_net")
_CASES = ("login", "register", "mfa", "forgot", "ws_hub")
_LIMITS = (60, 5, 5, 3, 10)
_EXPECTED_STATUSES = (422, 422, 422, 422, 401)
_CASE_BUDGETS_MS = (45000, 45000, 45000, 45000, 5000)
_TOTAL_BUDGET_MS = 120000
_MAX_OUTPUT_BYTES = 4096
_SETUP_REQUESTS = 2
_HTTP_REQUESTS = _SETUP_REQUESTS + sum(_LIMITS) + 6 * len(_CASES) + 4
_BACKEND_COMMAND = (
    "gunicorn",
    "app.main:app",
    "--worker-class",
    "uvicorn.workers.UvicornWorker",
    "--workers",
    "2",
    "--bind",
    "0.0.0.0:8000",
    "--graceful-timeout",
    "30",
    "--timeout",
    "60",
    "--keep-alive",
    "5",
    "--error-logfile",
    "-",
)
_ROOT_KEYS = frozenset(
    {
        "schema",
        "source_sha",
        "run_id",
        "closed",
        "sources_verified",
        "anonymous",
        "source_labels",
        "csrf_ready",
        "setup_requests",
        "http_requests",
        "elapsed_ms",
        "cases",
    }
)
_CASE_KEYS = frozenset(
    {
        "case",
        "allowed",
        "blocked",
        "other_client",
        "spoofed",
        "direct_untrusted",
        "backend_direct_untrusted",
        "elapsed_ms",
    }
)


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
    backend_direct_untrusted: int | None
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


def _hex_identity(value: object, length: int) -> bool:
    return (
        type(value) is str
        and len(value) == length
        and _HEX.fullmatch(value) is not None
    )


def _live(now_ms: int, deadline_ms: int) -> bool:
    return (
        type(now_ms) is int
        and type(deadline_ms) is int
        and 0 <= now_ms < deadline_ms
        and deadline_ms - now_ms <= _TOTAL_BUDGET_MS
    )


def _private_address(value: object) -> IPv4Address | None:
    if type(value) is not str:
        return None
    try:
        address = IPv4Address(value)
    except ValueError:
        return None
    if str(address) != value or not any(
        address in network for network in _PRIVATE_NETWORKS
    ):
        return None
    return address


def _route_network(route: ClientRoute) -> IPv4Network | None:
    if (
        type(route) is not ClientRoute
        or not _hex_identity(route.network_id, 64)
        or type(route.subnet) is not str
    ):
        return None
    try:
        network = IPv4Network(route.subnet)
    except ValueError:
        return None
    if str(network) != route.subnet or not any(
        network.subnet_of(private) for private in _PRIVATE_NETWORKS
    ):
        return None
    source = _private_address(route.source_ip)
    target = _private_address(route.caddy_ip)
    if source is None or target is None or source == target:
        return None
    for address in (source, target):
        if address not in network or address in (
            network.network_address,
            network.broadcast_address,
        ):
            return None
    return network


def _valid_pins(pins: AdmissionPins) -> bool:
    if type(pins) is not AdmissionPins or not _hex_identity(pins.source_sha, 40):
        return False
    if not all(
        _hex_identity(value, 64)
        for value in (
            pins.owner_identity,
            pins.daemon_identity,
            pins.resource_identity,
        )
    ):
        return False
    if (
        type(pins.container_ids) is not tuple
        or len(pins.container_ids) != 4
        or not all(_hex_identity(value, 64) for value in pins.container_ids)
        or len(set(pins.container_ids)) != 4
        or type(pins.image_ids) is not tuple
        or len(pins.image_ids) != 4
        or not all(
            type(value) is str
            and value.startswith("sha256:")
            and _hex_identity(value[7:], 64)
            for value in pins.image_ids
        )
        or type(pins.limits) is not tuple
        or any(type(value) is not int for value in pins.limits)
        or pins.limits != _LIMITS
        or type(pins.backend_command) is not tuple
        or pins.backend_command != _BACKEND_COMMAND
    ):
        return False
    if (
        type(pins.routes) is not tuple
        or len(pins.routes) != 2
        or any(type(route) is not ClientRoute for route in pins.routes)
        or tuple(route.network for route in pins.routes) != _SOURCE_LABELS
    ):
        return False
    first, second = pins.routes
    first_network = _route_network(first)
    second_network = _route_network(second)
    if (
        first_network is None
        or second_network is None
        or first_network.overlaps(second_network)
        or first.network_id == second.network_id
    ):
        return False
    if type(pins.trusted_proxies) is not tuple or len(pins.trusted_proxies) != 3:
        return False
    sources = {first.source_ip, second.source_ip}
    for peers in pins.trusted_proxies:
        if (
            type(peers) is not tuple
            or not 1 <= len(peers) <= 16
            or any(_private_address(peer) is None for peer in peers)
            or len(set(peers)) != len(peers)
            or sources.intersection(peers)
        ):
            return False
    return True


def validate_admission(
    expected: AdmissionPins,
    current: AdmissionPins,
    *,
    now_ms: int,
    deadline_ms: int,
) -> bool:
    """Require valid, unchanged private pins; never infer ownership from them."""
    return (
        _live(now_ms, deadline_ms)
        and _valid_pins(expected)
        and _valid_pins(current)
        and current == expected
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate observation key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite observation number")


def _bounded_integer(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _status(value: object) -> bool:
    return type(value) is int and 100 <= value <= 599


def _case_from_row(row: object, index: int) -> CaseObservation | None:
    if type(row) is not dict or row.keys() != _CASE_KEYS:
        return None
    allowed = row["allowed"]
    spoofed = row["spoofed"]
    if (
        row["case"] != _CASES[index]
        or type(allowed) is not list
        or len(allowed) != _LIMITS[index]
        or not all(_status(status) for status in allowed)
        or not _status(row["blocked"])
        or not _status(row["other_client"])
        or type(spoofed) is not list
        or len(spoofed) != 3
        or not all(_status(status) for status in spoofed)
        or not _status(row["direct_untrusted"])
        or (
            not _status(row["backend_direct_untrusted"])
            if index < 4
            else row["backend_direct_untrusted"] is not None
        )
        or not _bounded_integer(row["elapsed_ms"], _CASE_BUDGETS_MS[index])
    ):
        return None
    return CaseObservation(
        case=row["case"],
        allowed=tuple(allowed),
        blocked=row["blocked"],
        other_client=row["other_client"],
        spoofed=tuple(spoofed),
        direct_untrusted=row["direct_untrusted"],
        backend_direct_untrusted=row["backend_direct_untrusted"],
        elapsed_ms=row["elapsed_ms"],
    )


def _decode_frame(
    wire: object, expected_source_sha: str, expected_run_id: str
) -> ProbeObservations | None:
    if type(wire) is not dict or wire.keys() != _ROOT_KEYS:
        return None
    if (
        wire["schema"] != "ue-owned-client-ip-v2"
        or wire["source_sha"] != expected_source_sha
        or wire["run_id"] != expected_run_id
        or wire["closed"] is not True
        or wire["sources_verified"] is not True
        or wire["anonymous"] is not True
        or wire["source_labels"] != list(_SOURCE_LABELS)
        or type(wire["csrf_ready"]) is not list
        or len(wire["csrf_ready"]) != 2
        or any(ready is not True for ready in wire["csrf_ready"])
        or type(wire["setup_requests"]) is not int
        or wire["setup_requests"] != _SETUP_REQUESTS
        or type(wire["http_requests"]) is not int
        or wire["http_requests"] != _HTTP_REQUESTS
        or not _bounded_integer(wire["elapsed_ms"], _TOTAL_BUDGET_MS)
        or type(wire["cases"]) is not list
        or len(wire["cases"]) != len(_CASES)
    ):
        return None
    cases: list[CaseObservation] = []
    for index, row in enumerate(wire["cases"]):
        case = _case_from_row(row, index)
        if case is None:
            return None
        cases.append(case)
    if sum(case.elapsed_ms for case in cases) > wire["elapsed_ms"]:
        return None
    return ProbeObservations(
        source_sha=expected_source_sha,
        run_id=expected_run_id,
        cases=tuple(cases),
        http_requests=wire["http_requests"],
        elapsed_ms=wire["elapsed_ms"],
    )


def decode_observations(
    result: PrivateProcessResult,
    *,
    expected_source_sha: str,
    expected_run_id: str,
    now_ms: int,
    deadline_ms: int,
) -> ProbeObservations | None:
    """Decode one source-bound, private, closed frame without echoing bad input."""
    if (
        not _live(now_ms, deadline_ms)
        or not _hex_identity(expected_source_sha, 40)
        or not _hex_identity(expected_run_id, 64)
        or type(result) is not PrivateProcessResult
        or result.outcome is not ProcessOutcome.EXITED
        or type(result.returncode) is not int
        or result.returncode != 0
        or type(result.stdout) is not bytes
        or not 0 < len(result.stdout) <= _MAX_OUTPUT_BYTES
        or type(result.stderr) is not bytes
        or result.stderr
        or result.local_cleanup is not LocalCleanup.CONFIRMED
        or not result.stdout.endswith(b"\n")
        or result.stdout.count(b"\n") != 1
    ):
        return None
    try:
        wire = json.loads(
            result.stdout.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        return None
    return _decode_frame(wire, expected_source_sha, expected_run_id)


def _case_passes(case: CaseObservation, index: int) -> bool:
    expected = _EXPECTED_STATUSES[index]
    return (
        case.case == _CASES[index]
        and case.allowed == (expected,) * _LIMITS[index]
        and case.blocked == 429
        and case.other_client == expected
        and case.spoofed == (429, 429, 429)
        and case.direct_untrusted == 429
        and (
            case.backend_direct_untrusted == 429
            if index < 4
            else case.backend_direct_untrusted is None
        )
    )


def evaluate_observations(observed: ProbeObservations) -> SubsetVerdict:
    """Evaluate decoded statuses independently; never grant gateway/deploy credit."""
    passed = tuple(
        _case_passes(case, index) for index, case in enumerate(observed.cases)
    )
    return SubsetVerdict(backend=all(passed[:4]), ws_hub=passed[4])
