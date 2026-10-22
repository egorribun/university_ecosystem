"""Helm render contract for off-peak scale-to-zero of hibernated workloads (AUD-088)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.test_helm_staging_contract import _helm, _render_staging, _values

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
HIBERNATION_OVERRIDES = (
    "--set",
    "keda.enabled=true",
    "--set",
    "hibernation.enabled=true",
)


def _scaled_object(resources: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    return next(
        item
        for item in resources
        if item.get("kind") == "ScaledObject"
        and item["metadata"]["name"].endswith(suffix)
    )


@pytest.mark.parametrize("workload", ["frontend", "gateway"])
def test_hibernated_workload_scales_to_zero_off_peak_and_keeps_daytime_floor(
    workload: str,
) -> None:
    _helm()
    values = _values(CHART / "values.yaml")["hibernation"]
    schedule = values["schedules"]["offPeak"]
    workload_values = values["workloads"][workload]
    resources = _render_staging(*HIBERNATION_OVERRIDES)

    scaled_object = _scaled_object(resources, f"-{workload}-hibernation")
    spec = scaled_object["spec"]
    # A non-zero floor makes the off-peak desiredReplicas of 0 unreachable.
    assert spec["minReplicaCount"] == 0
    assert spec["maxReplicaCount"] == workload_values["maxReplicasDay"]

    off_peak, daytime = spec["triggers"]
    assert off_peak["type"] == "cron"
    assert off_peak["metadata"] == {
        "timezone": schedule["timezone"],
        "start": schedule["start"],
        "end": schedule["end"],
        "desiredReplicas": str(schedule["desiredReplicas"]),
    }
    # The daytime window is the complement of the off-peak window, so the
    # day floor still applies whenever the off-peak trigger is inactive.
    assert daytime["type"] == "cron"
    assert daytime["metadata"] == {
        "timezone": schedule["timezone"],
        "start": schedule["end"],
        "end": schedule["start"],
        "desiredReplicas": str(workload_values["minReplicasDay"]),
    }


def test_hibernation_disabled_renders_no_frontend_or_gateway_scaled_objects() -> None:
    _helm()
    resources = _render_staging("--set", "keda.enabled=true")

    names = {
        item["metadata"]["name"]
        for item in resources
        if item.get("kind") == "ScaledObject"
    }
    assert not any(
        name.endswith(("-frontend-hibernation", "-gateway-hibernation"))
        for name in names
    )
