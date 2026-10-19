"""Pure inventory admission contracts; no Docker, database or network calls."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.owned_nats_outage import (
    ContainerSnapshot,
    InventoryVerdict,
    validate_inventory,
)

# A full signed Core projection fixture, not a duplicated production selector.
SERVICES = (
    "backend",
    "caddy",
    "flagd",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "mailpit",
    "migrations",
    "minio",
    "minio-init",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "postgres-databases-init",
    "redis",
    "revocation-redis",
    "spicedb",
    "spicedb-migrate",
    "tempo",
    "tempo-healthprobe",
    "ws-hub",
)
NO_HEALTHCHECK = frozenset({"caddy", "flagd", "gateway", "mailpit", "tempo", "ws-hub"})
INITIALIZERS = frozenset(
    {"migrations", "minio-init", "postgres-databases-init", "spicedb-migrate"}
)


def _records() -> tuple[ContainerSnapshot, ...]:
    return tuple(
        ContainerSnapshot(
            container_id=f"{index:064x}",
            service=service,
            identity=f"{index + 100:064x}",
            running=service not in INITIALIZERS,
            status="exited" if service in INITIALIZERS else "running",
            health=(
                None
                if service in INITIALIZERS or service in NO_HEALTHCHECK
                else "healthy"
            ),
            restart_count=0,
            exit_code=0,
            oom_killed=False,
        )
        for index, service in enumerate(SERVICES, 1)
    )


def _with_record(
    records: tuple[ContainerSnapshot, ...], updated: ContainerSnapshot
) -> tuple[ContainerSnapshot, ...]:
    return tuple(
        updated if record.service == updated.service else record for record in records
    )


def test_inventory_accepts_exact_core_projection_and_completed_initializers() -> None:
    assert validate_inventory(SERVICES, _records()) is InventoryVerdict.VALID


@pytest.mark.parametrize(
    "selected",
    [
        (),
        (*SERVICES, "backend"),
        tuple(service for service in SERVICES if service != "nats"),
        tuple(service for service in SERVICES if service != "postgres"),
        tuple(service for service in SERVICES if service != "minio"),
        tuple(service for service in SERVICES if service != "backend"),
        tuple(service for service in SERVICES if service != "outbox-worker"),
    ],
)
def test_inventory_rejects_incomplete_or_duplicate_selection(
    selected: tuple[str, ...],
) -> None:
    matching_records = tuple(
        record for record in _records() if record.service in selected
    )

    assert (
        validate_inventory(selected, matching_records)
        is InventoryVerdict.INVALID_SELECTION
    )


@pytest.mark.parametrize(
    "case", ["missing", "extra", "duplicate-service", "duplicate-id"]
)
def test_inventory_requires_one_unique_container_per_selected_service(
    case: str,
) -> None:
    records = _records()
    if case == "missing":
        records = records[1:]
    elif case == "extra":
        records += (replace(records[0], service="unselected", container_id="f" * 64),)
    elif case == "duplicate-service":
        records += (replace(records[0], container_id="f" * 64),)
    else:
        records = (
            records[0],
            replace(records[1], container_id=records[0].container_id),
            *records[2:],
        )

    assert validate_inventory(SERVICES, records) is InventoryVerdict.INVALID_IDENTITY


@pytest.mark.parametrize(
    "record",
    [
        replace(_records()[0], container_id=""),
        replace(_records()[0], container_id="a" * 63),
        replace(_records()[0], container_id="G" * 64),
        replace(_records()[0], identity=""),
        replace(_records()[0], identity="a" * 63),
        replace(_records()[0], identity="G" * 64),
    ],
)
def test_inventory_requires_exact_canonical_id_and_identity_digest(
    record: ContainerSnapshot,
) -> None:
    records = _with_record(_records(), record)

    assert validate_inventory(SERVICES, records) is InventoryVerdict.INVALID_IDENTITY


@pytest.mark.parametrize(
    "record",
    [
        replace(_records()[0], running=False),
        replace(_records()[0], running=1),
        replace(_records()[0], status=None),
        replace(_records()[0], status="unknown"),
        replace(_records()[0], status="restarting"),
        replace(_records()[0], restart_count=-1),
        replace(_records()[0], restart_count=True),
        replace(_records()[0], exit_code=True),
        replace(_records()[0], exit_code=137),
        replace(_records()[0], oom_killed=True),
    ],
)
def test_inventory_rejects_invalid_or_failed_runtime(record: ContainerSnapshot) -> None:
    records = _with_record(_records(), record)

    assert validate_inventory(SERVICES, records) is InventoryVerdict.INVALID_RUNTIME


@pytest.mark.parametrize(
    "service", ["backend", "outbox-worker", "postgres", "minio", "nats"]
)
@pytest.mark.parametrize("health", [None, "starting", "unhealthy"])
def test_inventory_requires_healthy_critical_services(
    service: str, health: str | None
) -> None:
    records = _records()
    original = next(record for record in records if record.service == service)
    records = _with_record(records, replace(original, health=health))

    assert validate_inventory(SERVICES, records) is InventoryVerdict.UNHEALTHY


@pytest.mark.parametrize("health", ["starting", "unhealthy"])
def test_inventory_rejects_unhealthy_other_healthchecked_services(health: str) -> None:
    records = _records()
    original = next(record for record in records if record.service == "frontend")
    records = _with_record(records, replace(original, health=health))

    assert validate_inventory(SERVICES, records) is InventoryVerdict.UNHEALTHY


@pytest.mark.parametrize("service", sorted(INITIALIZERS))
def test_inventory_rejects_failed_initializer(service: str) -> None:
    records = _records()
    original = next(record for record in records if record.service == service)
    records = _with_record(records, replace(original, exit_code=1))

    assert validate_inventory(SERVICES, records) is InventoryVerdict.INVALID_RUNTIME


@pytest.mark.parametrize("service", ["frontend", "gateway", "notifications-worker"])
def test_inventory_rejects_stopped_noncritical_runtime(service: str) -> None:
    records = _records()
    original = next(record for record in records if record.service == service)
    records = _with_record(
        records, replace(original, running=False, status="exited", exit_code=0)
    )

    assert validate_inventory(SERVICES, records) is InventoryVerdict.INVALID_RUNTIME
