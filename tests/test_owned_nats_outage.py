"""Pure inventory admission contracts; no Docker, database or network calls."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.owned_nats_outage import (
    ContainerSnapshot,
    InventoryVerdict,
    validate_inventory,
)
from tests.helpers.owned_nats_acceptance import (
    CORE_INITIALIZERS,
    CORE_SERVICES,
    core_container_snapshots,
)


def _with_record(
    records: tuple[ContainerSnapshot, ...], updated: ContainerSnapshot
) -> tuple[ContainerSnapshot, ...]:
    return tuple(
        updated if record.service == updated.service else record for record in records
    )


def test_inventory_accepts_exact_core_projection_and_completed_initializers() -> None:
    verdict = validate_inventory(CORE_SERVICES, core_container_snapshots())
    assert verdict is InventoryVerdict.VALID


@pytest.mark.parametrize(
    "selected",
    [
        (),
        (*CORE_SERVICES, "backend"),
        tuple(service for service in CORE_SERVICES if service != "nats"),
        tuple(service for service in CORE_SERVICES if service != "postgres"),
        tuple(service for service in CORE_SERVICES if service != "minio"),
        tuple(service for service in CORE_SERVICES if service != "backend"),
        tuple(service for service in CORE_SERVICES if service != "outbox-worker"),
    ],
)
def test_inventory_rejects_incomplete_or_duplicate_selection(
    selected: tuple[str, ...],
) -> None:
    matching_records = tuple(
        record for record in core_container_snapshots() if record.service in selected
    )

    verdict = validate_inventory(selected, matching_records)
    assert verdict is InventoryVerdict.INVALID_SELECTION


@pytest.mark.parametrize(
    "case", ["missing", "extra", "duplicate-service", "duplicate-id"]
)
def test_inventory_requires_one_unique_container_per_selected_service(
    case: str,
) -> None:
    records = core_container_snapshots()
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

    verdict = validate_inventory(CORE_SERVICES, records)
    assert verdict is InventoryVerdict.INVALID_IDENTITY


@pytest.mark.parametrize(
    "record",
    [
        replace(core_container_snapshots()[0], container_id=""),
        replace(core_container_snapshots()[0], container_id="a" * 63),
        replace(core_container_snapshots()[0], container_id="G" * 64),
        replace(core_container_snapshots()[0], identity=""),
        replace(core_container_snapshots()[0], identity="a" * 63),
        replace(core_container_snapshots()[0], identity="G" * 64),
    ],
)
def test_inventory_requires_exact_canonical_id_and_identity_digest(
    record: ContainerSnapshot,
) -> None:
    records = _with_record(core_container_snapshots(), record)

    verdict = validate_inventory(CORE_SERVICES, records)
    assert verdict is InventoryVerdict.INVALID_IDENTITY


@pytest.mark.parametrize(
    "record",
    [
        replace(core_container_snapshots()[0], running=False),
        replace(core_container_snapshots()[0], running=1),
        replace(core_container_snapshots()[0], status=None),
        replace(core_container_snapshots()[0], status="unknown"),
        replace(core_container_snapshots()[0], status="restarting"),
        replace(core_container_snapshots()[0], restart_count=-1),
        replace(core_container_snapshots()[0], restart_count=True),
        replace(core_container_snapshots()[0], exit_code=True),
        replace(core_container_snapshots()[0], exit_code=137),
        replace(core_container_snapshots()[0], oom_killed=True),
    ],
)
def test_inventory_rejects_invalid_or_failed_runtime(record: ContainerSnapshot) -> None:
    records = _with_record(core_container_snapshots(), record)

    verdict = validate_inventory(CORE_SERVICES, records)
    assert verdict is InventoryVerdict.INVALID_RUNTIME


@pytest.mark.parametrize(
    "service", ["backend", "outbox-worker", "postgres", "minio", "nats"]
)
@pytest.mark.parametrize("health", [None, "starting", "unhealthy"])
def test_inventory_requires_healthy_critical_services(
    service: str, health: str | None
) -> None:
    records = core_container_snapshots()
    original = next(record for record in records if record.service == service)
    records = _with_record(records, replace(original, health=health))

    assert validate_inventory(CORE_SERVICES, records) is InventoryVerdict.UNHEALTHY


@pytest.mark.parametrize("health", ["starting", "unhealthy"])
def test_inventory_rejects_unhealthy_other_healthchecked_services(health: str) -> None:
    records = core_container_snapshots()
    original = next(record for record in records if record.service == "frontend")
    records = _with_record(records, replace(original, health=health))

    assert validate_inventory(CORE_SERVICES, records) is InventoryVerdict.UNHEALTHY


@pytest.mark.parametrize("service", sorted(CORE_INITIALIZERS))
def test_inventory_rejects_failed_initializer(service: str) -> None:
    records = core_container_snapshots()
    original = next(record for record in records if record.service == service)
    records = _with_record(records, replace(original, exit_code=1))

    verdict = validate_inventory(CORE_SERVICES, records)
    assert verdict is InventoryVerdict.INVALID_RUNTIME


@pytest.mark.parametrize("service", ["frontend", "gateway", "notifications-worker"])
def test_inventory_rejects_stopped_noncritical_runtime(service: str) -> None:
    records = core_container_snapshots()
    original = next(record for record in records if record.service == service)
    records = _with_record(
        records, replace(original, running=False, status="exited", exit_code=0)
    )

    verdict = validate_inventory(CORE_SERVICES, records)
    assert verdict is InventoryVerdict.INVALID_RUNTIME
