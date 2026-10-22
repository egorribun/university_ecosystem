"""Pure post-restoration snapshot invariants; no container operations."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.owned_nats_outage import (
    ContainerSnapshot,
    RestorationVerdict,
    validate_restored_inventory,
)
from tests.helpers.owned_nats_acceptance import (
    CORE_SERVICES,
    core_container_snapshots,
)


def _changed(
    records: tuple[ContainerSnapshot, ...],
    service: str,
    field: str,
    value: object,
) -> tuple[ContainerSnapshot, ...]:
    return tuple(
        replace(record, **{field: value}) if record.service == service else record
        for record in records
    )


@pytest.mark.parametrize("reorder", [False, True])
def test_unchanged_restored_inventory_is_order_independent(reorder: bool) -> None:
    before = core_container_snapshots()
    after = tuple(reversed(before)) if reorder else before

    verdict = validate_restored_inventory(CORE_SERVICES, before, after)

    assert verdict is RestorationVerdict.VALID


@pytest.mark.parametrize(("before_count", "after_count"), [(0, 1), (1, 0)])
def test_same_healthy_nats_may_change_its_restart_counter(
    before_count: int, after_count: int
) -> None:
    before = _changed(core_container_snapshots(), "nats", "restart_count", before_count)
    after = _changed(before, "nats", "restart_count", after_count)

    verdict = validate_restored_inventory(CORE_SERVICES, before, after)

    assert verdict is RestorationVerdict.VALID


def test_invalid_original_snapshot_cannot_authorize_restoration_acceptance() -> None:
    after = core_container_snapshots()
    before = _changed(after, "postgres", "health", "unhealthy")

    verdict = validate_restored_inventory(CORE_SERVICES, before, after)

    assert verdict is RestorationVerdict.INVALID_SNAPSHOT


@pytest.mark.parametrize(
    "case", ["missing", "extra", "duplicate-id", "duplicate-service"]
)
def test_restored_snapshot_requires_same_unique_container_set(case: str) -> None:
    before = core_container_snapshots()
    if case == "missing":
        after = before[1:]
    elif case == "extra":
        after = (
            *before,
            replace(before[0], container_id="f" * 64, service="unexpected"),
        )
    elif case == "duplicate-id":
        after = (
            before[0],
            replace(before[1], container_id=before[0].container_id),
            *before[2:],
        )
    else:
        after = (
            before[0],
            replace(before[1], service=before[0].service),
            *before[2:],
        )

    verdict = validate_restored_inventory(CORE_SERVICES, before, after)

    assert verdict is RestorationVerdict.IDENTITY_CHANGED


@pytest.mark.parametrize("service", ["nats", "backend", "minio"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("container_id", "f" * 64), ("identity", "e" * 64), ("service", "unexpected")],
)
def test_restoration_does_not_accept_replacement_or_changed_identity(
    service: str, field: str, value: str
) -> None:
    before = core_container_snapshots()
    after = _changed(before, service, field, value)

    verdict = validate_restored_inventory(CORE_SERVICES, before, after)

    assert verdict is RestorationVerdict.IDENTITY_CHANGED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("running", False),
        ("status", "restarting"),
        ("health", "unhealthy"),
        ("health", None),
        ("restart_count", 1),
        ("exit_code", 137),
        ("oom_killed", True),
    ],
)
def test_every_non_nats_runtime_field_must_remain_unchanged(
    field: str, value: object
) -> None:
    before = core_container_snapshots()
    after = _changed(before, "frontend", field, value)

    verdict = validate_restored_inventory(CORE_SERVICES, before, after)

    assert verdict is RestorationVerdict.RUNTIME_CHANGED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("running", False),
        ("status", "restarting"),
        ("health", None),
        ("health", "unhealthy"),
        ("restart_count", -1),
        ("exit_code", 137),
        ("oom_killed", True),
    ],
)
def test_same_nats_identity_without_healthy_runtime_is_not_restored(
    field: str, value: object
) -> None:
    before = core_container_snapshots()
    after = _changed(before, "nats", field, value)

    verdict = validate_restored_inventory(CORE_SERVICES, before, after)

    assert verdict is RestorationVerdict.INVALID_SNAPSHOT
