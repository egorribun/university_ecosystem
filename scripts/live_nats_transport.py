"""Pure complete-Core marker boundary for a future bounded NATS transport.

The parser call performs no filesystem, lock, Docker, HTTP or database work.
It is not connected to the coordinator or CLI. Importing the existing live_stand
module retains that module's ordinary repository-path initialization.
A parsed claim is conditional on trusted caller-supplied key bytes and pins;
it does not establish file provenance or observe the current Docker daemon.
"""

from __future__ import annotations

import hmac
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from scripts import live_stand
from scripts.owned_nats_coordinator import OwnerEvidence

MAX_OWNER_MARKER_BYTES = 65_536
_V11_OWNER_KEYS = frozenset(
    {
        "version",
        "repository",
        "worktree",
        "project_name",
        "signature",
        "published_ports",
        "daemon_fingerprint",
        "compose_resource_fingerprint",
        "resume_compose_resource_fingerprint",
        "resume_compose_resource_schema_version",
        "stack",
        "service_roots",
        "selected_services",
        "source_sha",
    }
)
_SOURCE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_HEX_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")


class OwnerParseStatus(StrEnum):
    NOT_READY = "not_ready"
    SIGNED_METADATA = "signed_metadata"


@dataclass(frozen=True, slots=True)
class OwnerParseResult:
    status: OwnerParseStatus
    owner: OwnerEvidence | None = field(default=None, repr=False)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _absolute_pin(value: object) -> bool:
    # Lexical only: do not resolve, stat, or open paths.
    return type(value) is str and bool(value) and Path(value).is_absolute()


def parse_signed_owner_v11(
    marker_bytes: bytes,
    key_bytes: bytes,
    *,
    pinned_repository: str,
    pinned_state_root: str,
    pinned_source_sha: str,
) -> OwnerParseResult:
    """Parse bounded v11 bytes without inferring file or runtime ownership."""
    not_ready = OwnerParseResult(OwnerParseStatus.NOT_READY)
    try:
        if (
            type(marker_bytes) is not bytes
            or len(marker_bytes) > MAX_OWNER_MARKER_BYTES
            or type(key_bytes) is not bytes
            or len(key_bytes) != 32
            or not _absolute_pin(pinned_repository)
            or not _absolute_pin(pinned_state_root)
            or type(pinned_source_sha) is not str
            or _SOURCE_SHA_PATTERN.fullmatch(pinned_source_sha) is None
        ):
            return not_ready

        data = json.loads(
            marker_bytes.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
        if type(data) is not dict or set(data) != _V11_OWNER_KEYS:
            return not_ready
        if type(data["version"]) is not int or data["version"] != 11:
            return not_ready

        string_fields = (
            "repository",
            "worktree",
            "project_name",
            "signature",
            "daemon_fingerprint",
            "compose_resource_fingerprint",
            "stack",
            "source_sha",
        )
        if any(type(data[name]) is not str for name in string_fields):
            return not_ready
        if (
            data["repository"] != pinned_repository
            or data["worktree"] != pinned_state_root
            or data["source_sha"] != pinned_source_sha
        ):
            return not_ready

        live_stand._validate_project_name(data["project_name"])
        raw_ports = data["published_ports"]
        if type(raw_ports) is not dict or any(
            type(port) is not int for port in raw_ports.values()
        ):
            return not_ready
        ports = dict(live_stand._validate_published_ports(raw_ports))

        fingerprint_fields = (
            "daemon_fingerprint",
            "compose_resource_fingerprint",
            "signature",
        )
        if any(
            _HEX_FINGERPRINT_PATTERN.fullmatch(data[name]) is None
            for name in fingerprint_fields
        ):
            return not_ready
        if (
            data["resume_compose_resource_fingerprint"] is not None
            or data["resume_compose_resource_schema_version"] is not None
            or data["stack"] != live_stand.LIVE_STACK_CORE
            or type(data["service_roots"]) is not list
            or data["service_roots"] != list(live_stand.LIVE_CORE_SERVICE_ROOTS)
            or type(data["selected_services"]) is not list
            or data["selected_services"] != list(live_stand.LIVE_CORE_EXPECTED_SERVICES)
        ):
            return not_ready

        # Match the existing loader's validated, normalized canonical payload.
        payload = {key: value for key, value in data.items() if key != "signature"}
        payload["published_ports"] = ports
        expected_signature = live_stand._owner_signature(payload, key_bytes)
        if not hmac.compare_digest(data["signature"], expected_signature):
            return not_ready

        owner = OwnerEvidence(
            repository=pinned_repository,
            worktree=pinned_state_root,
            project_name=data["project_name"],
            published_ports=tuple(ports.items()),
            schema_version=11,
            daemon_fingerprint=data["daemon_fingerprint"],
            compose_resource_fingerprint=data["compose_resource_fingerprint"],
            resume_compose_resource_fingerprint=None,
            resume_compose_resource_schema_version=None,
            source_sha=pinned_source_sha,
            stack=live_stand.LIVE_STACK_CORE,
            service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
            selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
        )
        return OwnerParseResult(OwnerParseStatus.SIGNED_METADATA, owner)
    except (live_stand.StandError, RecursionError, TypeError, ValueError):
        return not_ready
