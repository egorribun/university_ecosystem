"""Helm contract for the daily partition-retention CronJob and its failure alert.

The CronJob runs partition DDL, which only the schema owner login may perform. It
therefore carries the migration credential and never the runtime database URL.
The render uses the staging fixture, the same one the other chart contracts use.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.test_helm_staging_contract import (
    _helm,
    _render_staging,
)

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
RELEASE = "partition-maintenance"
CRONJOB_NAME = "university-ecosystem-partition-maintenance"
RUNTIME_DATABASE_KEY = re.compile(r"(?<![-\w])database-url(?![-\w])")


def _of_kind(resources: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [resource for resource in resources if resource.get("kind") == kind]


@pytest.fixture(scope="module")
def rendered() -> list[dict[str, Any]]:
    return _render_staging(release_name=RELEASE)


@pytest.fixture(scope="module")
def cronjob(rendered: list[dict[str, Any]]) -> dict[str, Any]:
    jobs = _of_kind(rendered, "CronJob")
    matches = [
        job
        for job in jobs
        if job["metadata"]["name"].endswith("-partition-maintenance")
    ]
    assert len(matches) == 1, [job["metadata"]["name"] for job in jobs]
    return matches[0]


def test_schedule_is_daily_utc_and_never_overlaps(cronjob: dict[str, Any]) -> None:
    spec = cronjob["spec"]
    assert spec["schedule"] == "30 3 * * *"
    assert spec["timeZone"] == "Etc/UTC"
    assert spec["concurrencyPolicy"] == "Forbid"


def test_deadlines_and_history_are_bounded(cronjob: dict[str, Any]) -> None:
    spec = cronjob["spec"]
    job = spec["jobTemplate"]["spec"]
    assert spec["startingDeadlineSeconds"] == 900
    assert spec["successfulJobsHistoryLimit"] == 3
    assert spec["failedJobsHistoryLimit"] == 3
    assert job["backoffLimit"] == 1
    assert job["activeDeadlineSeconds"] == 900
    assert job["ttlSecondsAfterFinished"] == 86400


def test_job_runs_partition_manager_as_non_root_without_token(
    cronjob: dict[str, Any],
) -> None:
    pod = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == 10001
    assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    container = pod["containers"][0]
    assert container["command"] == ["python", "-m", "app.services.partition_manager"]
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }


def test_job_uses_the_schema_owner_credential_only(cronjob: dict[str, Any]) -> None:
    pod = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]
    env = {item["name"]: item.get("value") for item in container["env"]}
    assert env["DATABASE_URL_FILE"] == (
        "/run/secrets/university-connections/migration-database-url"
    )
    assert "DATABASE_URL" not in env
    rendered_text = yaml.safe_dump(cronjob)
    assert RUNTIME_DATABASE_KEY.search(rendered_text) is None
    template_labels = cronjob["spec"]["jobTemplate"]["spec"]["template"]["metadata"][
        "labels"
    ]
    assert template_labels[f"{RELEASE}-revocation-redis-client"] == "true"


def test_cronjob_is_not_a_helm_hook(cronjob: dict[str, Any]) -> None:
    annotations = cronjob["metadata"].get("annotations") or {}
    assert not any(key.startswith("helm.sh/hook") for key in annotations)


def test_failure_alert_watches_only_this_cronjob_jobs(
    rendered: list[dict[str, Any]],
) -> None:
    rules = _of_kind(rendered, "PrometheusRule")
    matches = [
        rule for rule in rules if "partition-maintenance" in rule["metadata"]["name"]
    ]
    assert len(matches) == 1
    rule = matches[0]
    assert rule["metadata"]["labels"]["release"] == "prometheus"
    group = rule["spec"]["groups"][0]
    alert = group["rules"][0]
    assert alert["alert"] == "PartitionMaintenanceJobFailed"
    assert alert["expr"] == (
        'sum(kube_job_status_failed{namespace="university-ecosystem", '
        f'job_name=~"{CRONJOB_NAME}-[0-9]+"}}) > 0'
    )
    assert alert["for"] == "0m"
    assert alert["labels"] == {"severity": "critical"}


def test_disabling_the_job_removes_cronjob_and_alert() -> None:
    rendered = _render_staging(
        "--set",
        "partitionMaintenance.enabled=false",
        release_name=RELEASE,
    )
    assert not [
        resource
        for resource in rendered
        if resource.get("kind") in ("CronJob", "PrometheusRule")
        and "partition-maintenance" in resource.get("metadata", {}).get("name", "")
    ]


def test_alert_can_be_disabled_independently() -> None:
    rendered = _render_staging(
        "--set",
        "partitionMaintenance.alert.enabled=false",
        release_name=RELEASE,
    )
    assert _of_kind(rendered, "CronJob")
    assert not _of_kind(rendered, "PrometheusRule")


def test_values_schema_rejects_unknown_partition_keys() -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            RELEASE,
            str(CHART),
            "--dependency-update=false",
            "--set",
            "partitionMaintenance.schedul=@hourly",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode != 0
    assert "partitionMaintenance" in result.stderr


def test_chart_values_pin_the_documented_defaults() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    block = values["partitionMaintenance"]
    assert block["enabled"] is True
    assert block["schedule"] == "30 3 * * *"
    assert block["concurrencyPolicy"] == "Forbid"
    assert block["alert"]["enabled"] is True


def test_network_policy_isolates_the_partition_pods(
    rendered: list[dict[str, Any]],
) -> None:
    policies = [
        resource
        for resource in _of_kind(rendered, "NetworkPolicy")
        if resource["metadata"]["name"].endswith("-partition-maintenance-policy")
    ]
    assert len(policies) == 1
    spec = policies[0]["spec"]
    assert spec["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/component": "partition-maintenance"
    }
    assert spec["ingress"] == []
    ports = [
        (port["protocol"], port["port"])
        for rule in spec["egress"]
        for port in rule.get("ports", [])
    ]
    assert ("TCP", 5432) in ports
    assert ("TCP", 6379) in ports
    assert ("UDP", 53) in ports
    assert all(
        port in {("TCP", 5432), ("TCP", 6379), ("UDP", 53), ("TCP", 53)}
        for port in ports
    )
