from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.quality.evaluate_cwv_field import (
    CwvCertificationError,
    evaluate_report,
    main,
    nearest_rank,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "quality" / "cwv-field-report.schema.json"
DEPLOYMENT_SCHEMA = ROOT / "quality" / "cwv-deployment-metadata.schema.json"
POLICY = ROOT / "quality" / "cwv-field-policy.json"
COMMIT_SHA = "1" * 40
IMAGE_DIGEST = f"sha256:{'2' * 64}"
DEPLOYED_AT = datetime(2026, 8, 24, 23, tzinfo=UTC)
WINDOW_START = datetime(2026, 8, 25, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 26, tzinfo=UTC)
GENERATED_AT = datetime(2026, 8, 26, 1, tzinfo=UTC)
NOW = datetime(2026, 8, 26, 2, tzinfo=UTC)
DEPLOYMENT_URL = "https://staging.university.example"
ROUTE_GROUPS = [
    "core",
    "content",
    "map_activity",
    "messenger_profile_settings_admin",
]
THRESHOLDS = {"LCP": ("ms", 2500.0), "INP": ("ms", 200.0), "CLS": ("score", 0.1)}


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _report() -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for device in ("mobile", "desktop"):
        for metric, (unit, maximum) in THRESHOLDS.items():
            for index in range(100):
                route_group = ROUTE_GROUPS[index % len(ROUTE_GROUPS)]
                observations.append(
                    {
                        "metric": metric,
                        "unit": unit,
                        "value": maximum,
                        "metric_id": f"metric-{device}-{metric.lower()}-{index:04d}",
                        "collector_id": f"collector-{device}-{index % 25:04d}",
                        "navigation_id": (
                            f"navigation-{device}-{route_group}-"
                            f"{index // len(ROUTE_GROUPS):04d}"
                        ),
                        "session_id": f"session-{device}-{index % 25:04d}",
                        "device_class": device,
                        "route_group": route_group,
                        "observed_at": _timestamp(
                            WINDOW_START + timedelta(hours=index % 6)
                        ),
                        "release_sha": COMMIT_SHA,
                        "frontend_image_digest": IMAGE_DIGEST,
                        "automated": False,
                        "final": True,
                    }
                )
    return {
        "schema_version": 1,
        "generated_at": _timestamp(GENERATED_AT),
        "release_sha": COMMIT_SHA,
        "frontend_image_digest": IMAGE_DIGEST,
        "environment": "staging",
        "deployment": {
            "workflow_run_id": 123456,
            "workflow_run_attempt": 2,
            "deployed_at": _timestamp(DEPLOYED_AT),
            "deployment_url": DEPLOYMENT_URL,
        },
        "collector": {
            "kind": "web-vitals-rum",
            "library": "web-vitals",
            "library_version": "6.1.1",
            "exporter_version": "1",
            "eligibility": "operator-curated-manual-testers",
            "sampling": "one-final-metric-per-collector-route-hour",
            "maximum_collectors": 50,
        },
        "window": {"start": _timestamp(WINDOW_START), "end": _timestamp(WINDOW_END)},
        "observations": observations,
    }


def _write_evidence(tmp_path: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    report_path = tmp_path / "cwv-field-report.json"
    report_path.write_text(json.dumps(report, allow_nan=True), encoding="utf-8")
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    checksum_path = tmp_path / "cwv-field-report.json.sha256"
    checksum_path.write_text(f"{digest}  {report_path.name}\n", encoding="utf-8")
    return report_path, checksum_path


def _write_deployment_evidence(tmp_path: Path) -> tuple[Path, Path]:
    metadata_path = tmp_path / "staging-deployment.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "environment": "staging",
                "release_sha": COMMIT_SHA,
                "frontend_image_digest": IMAGE_DIGEST,
                "deployment_url": DEPLOYMENT_URL,
                "deployed_at": _timestamp(DEPLOYED_AT),
                "workflow_run_id": 123456,
                "workflow_run_attempt": 2,
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    checksum_path = tmp_path / "staging-deployment.json.sha256"
    checksum_path.write_text(f"{digest}  {metadata_path.name}\n", encoding="utf-8")
    return metadata_path, checksum_path


def _evaluate(
    tmp_path: Path,
    report: dict[str, Any] | None = None,
    **overrides: object,
) -> dict[str, object]:
    report_path, checksum_path = _write_evidence(tmp_path, report or _report())
    deployment_path, deployment_checksum_path = _write_deployment_evidence(tmp_path)
    arguments: dict[str, object] = {
        "report_path": report_path,
        "checksum_path": checksum_path,
        "schema_path": SCHEMA,
        "deployment_metadata_path": deployment_path,
        "deployment_checksum_path": deployment_checksum_path,
        "deployment_schema_path": DEPLOYMENT_SCHEMA,
        "policy_path": POLICY,
        "expected_commit_sha": COMMIT_SHA,
        "expected_image_digest": IMAGE_DIGEST,
        "expected_environment": "staging",
        "expected_deployment_run_id": 123456,
        "expected_deployment_run_attempt": 2,
        "now": NOW,
    }
    arguments.update(overrides)
    return evaluate_report(**arguments)  # type: ignore[arg-type]


def test_field_cwv_report_passes_at_exact_thresholds(tmp_path: Path) -> None:
    verdict = _evaluate(tmp_path)

    assert verdict["valid"] is True
    assert verdict["release_sha"] == COMMIT_SHA
    assert verdict["frontend_image_digest"] == IMAGE_DIGEST
    segments = verdict["segments"]
    assert isinstance(segments, dict)
    assert set(segments) == {
        f"{device}/{metric}"
        for device in ("mobile", "desktop")
        for metric in THRESHOLDS
    }
    assert segments["mobile/INP"]["p75"] == 200.0
    assert len(verdict["report_sha256"]) == 64
    assert len(verdict["policy_sha256"]) == 64


def test_nearest_rank_has_stable_boundaries() -> None:
    assert nearest_rank(list(range(1, 101))) == 75
    assert nearest_rank(list(range(1, 102))) == 76
    with pytest.raises(CwvCertificationError, match="empty"):
        nearest_rank([])
    with pytest.raises(CwvCertificationError, match="range"):
        nearest_rank([1.0], 0)


def test_p75_fails_on_the_first_value_above_the_boundary(tmp_path: Path) -> None:
    report = _report()
    segment = [
        item
        for item in report["observations"]
        if item["device_class"] == "mobile" and item["metric"] == "INP"
    ]
    for observation in segment[:26]:
        observation["value"] = 200.000001

    with pytest.raises(CwvCertificationError, match="p75"):
        _evaluate(tmp_path, report)


def test_route_metric_p75_cannot_hide_behind_other_routes(tmp_path: Path) -> None:
    report = _report()
    route_values = [
        item
        for item in report["observations"]
        if item["device_class"] == "mobile"
        and item["route_group"] == "content"
        and item["metric"] == "LCP"
    ]
    for observation in route_values[:7]:
        observation["value"] = 2500.000001

    with pytest.raises(CwvCertificationError, match="mobile/content/LCP p75"):
        _evaluate(tmp_path, report)


def test_each_route_requires_each_core_web_vital(tmp_path: Path) -> None:
    report = _report()
    content_lcp = [
        item
        for item in report["observations"]
        if item["device_class"] == "mobile"
        and item["route_group"] == "content"
        and item["metric"] == "LCP"
    ]
    removed_ids = {id(item) for item in content_lcp[:21]}
    report["observations"] = [
        item for item in report["observations"] if id(item) not in removed_ids
    ]
    with pytest.raises(
        CwvCertificationError,
        match="mobile/content/LCP has insufficient route observations",
    ):
        _evaluate(tmp_path, report)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("sha", "release_sha mismatch"),
        ("digest", "frontend_image_digest mismatch"),
        ("run", "run ID mismatch"),
        ("attempt", "run attempt mismatch"),
        ("environment", "schema validation"),
    ],
)
def test_report_is_bound_to_release_identity(
    tmp_path: Path, mutation: str, message: str
) -> None:
    report = _report()
    if mutation == "sha":
        report["release_sha"] = "3" * 40
    elif mutation == "digest":
        report["frontend_image_digest"] = f"sha256:{'4' * 64}"
    elif mutation == "run":
        report["deployment"]["workflow_run_id"] = 654321
    elif mutation == "attempt":
        report["deployment"]["workflow_run_attempt"] = 3
    else:
        report["environment"] = "production"

    with pytest.raises(CwvCertificationError, match=message):
        _evaluate(tmp_path, report)


@pytest.mark.parametrize("field", ["deployed_at", "deployment_url"])
def test_report_deployment_identity_matches_trusted_metadata(
    tmp_path: Path, field: str
) -> None:
    report = _report()
    report["deployment"][field] = (
        _timestamp(DEPLOYED_AT - timedelta(minutes=1))
        if field == "deployed_at"
        else "https://other-staging.example"
    )

    with pytest.raises(CwvCertificationError, match="trusted deployment metadata"):
        _evaluate(tmp_path, report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("library_version", "99.0.0"),
        ("exporter_version", "untrusted-exporter"),
    ],
)
def test_report_rejects_noncanonical_collector(
    tmp_path: Path, field: str, value: str
) -> None:
    report = _report()
    report["collector"][field] = value

    with pytest.raises(CwvCertificationError, match="collector contract mismatch"):
        _evaluate(tmp_path, report)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("observations", "insufficient observations"),
        ("sessions", "insufficient distinct sessions"),
        ("hours", "insufficient active hours"),
        ("routes", "insufficient route observations"),
    ],
)
def test_report_requires_representative_segment_coverage(
    tmp_path: Path, mutation: str, message: str
) -> None:
    report = _report()
    observations = report["observations"]
    if mutation == "observations":
        target = next(
            item
            for item in observations
            if item["device_class"] == "mobile" and item["metric"] == "LCP"
        )
        observations.remove(target)
    elif mutation == "sessions":
        for item in observations:
            if item["device_class"] == "mobile":
                item["session_id"] = "session-mobile-single"
    elif mutation == "hours":
        for item in observations:
            if item["device_class"] == "mobile":
                item["observed_at"] = _timestamp(WINDOW_START)
    else:
        for item in observations:
            if item["device_class"] == "mobile" and item["route_group"] == "content":
                item["route_group"] = "core"

    with pytest.raises(CwvCertificationError, match=message):
        _evaluate(tmp_path, report)


def test_report_requires_representative_manual_collector_cohort(
    tmp_path: Path,
) -> None:
    report = _report()
    mobile_observations = [
        item for item in report["observations"] if item["device_class"] == "mobile"
    ]
    for index, item in enumerate(mobile_observations):
        item["collector_id"] = f"collector-mobile-{index % 19:04d}"
        item["observed_at"] = _timestamp(WINDOW_START + timedelta(hours=index % 6))

    with pytest.raises(CwvCertificationError, match="insufficient distinct collectors"):
        _evaluate(tmp_path, report)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate", "duplicate metric identity"),
        ("automated", "final and non-automated"),
        ("not_final", "final and non-automated"),
        ("outside", "outside the collection window"),
        ("foreign_sha", "release SHA mismatch"),
        ("foreign_digest", "image digest mismatch"),
    ],
)
def test_observations_fail_closed(tmp_path: Path, mutation: str, message: str) -> None:
    report = _report()
    first = report["observations"][0]
    if mutation == "duplicate":
        report["observations"].append(copy.deepcopy(first))
    elif mutation == "automated":
        first["automated"] = True
    elif mutation == "not_final":
        first["final"] = False
    elif mutation == "outside":
        first["observed_at"] = _timestamp(WINDOW_START - timedelta(seconds=1))
    elif mutation == "foreign_sha":
        first["release_sha"] = "3" * 40
    else:
        first["frontend_image_digest"] = f"sha256:{'4' * 64}"

    with pytest.raises(CwvCertificationError, match=message):
        _evaluate(tmp_path, report)


def test_navigation_cannot_submit_multiple_final_values_for_one_metric(
    tmp_path: Path,
) -> None:
    report = _report()
    duplicate = copy.deepcopy(report["observations"][0])
    duplicate["metric_id"] = "metric-duplicate-final-0001"
    report["observations"].append(duplicate)

    with pytest.raises(CwvCertificationError, match="duplicate navigation metric"):
        _evaluate(tmp_path, report)


def test_manual_collector_cannot_submit_multiple_samples_in_one_route_hour(
    tmp_path: Path,
) -> None:
    report = _report()
    duplicate = copy.deepcopy(report["observations"][0])
    duplicate["metric_id"] = "metric-manual-bucket-duplicate"
    duplicate["navigation_id"] = "navigation-manual-bucket-duplicate"
    report["observations"].append(duplicate)

    with pytest.raises(CwvCertificationError, match="sampling bucket"):
        _evaluate(tmp_path, report)


@pytest.mark.parametrize("field", ["session_id", "device_class", "route_group"])
def test_navigation_metadata_must_be_consistent(tmp_path: Path, field: str) -> None:
    report = _report()
    first = report["observations"][0]
    same_navigation = next(
        observation
        for observation in report["observations"][1:]
        if observation["navigation_id"] == first["navigation_id"]
    )
    replacements = {
        "session_id": "session-metadata-mismatch-0001",
        "device_class": "desktop",
        "route_group": "content",
    }
    same_navigation[field] = replacements[field]

    with pytest.raises(CwvCertificationError, match="inconsistent navigation metadata"):
        _evaluate(tmp_path, report)


@pytest.mark.parametrize(
    "mutation", ["short", "stale", "stale_data", "future", "before_deploy"]
)
def test_temporal_evidence_is_current_and_consistent(
    tmp_path: Path, mutation: str
) -> None:
    report = _report()
    now = NOW
    if mutation == "short":
        report["window"]["end"] = _timestamp(WINDOW_START + timedelta(hours=23))
    elif mutation == "stale":
        now = GENERATED_AT + timedelta(hours=73)
    elif mutation == "stale_data":
        report["deployment"]["deployed_at"] = _timestamp(NOW - timedelta(hours=100))
        report["window"]["start"] = _timestamp(NOW - timedelta(hours=97))
        report["window"]["end"] = _timestamp(NOW - timedelta(hours=73))
        report["generated_at"] = _timestamp(NOW - timedelta(hours=1))
        for index, observation in enumerate(report["observations"]):
            observation["observed_at"] = _timestamp(
                NOW - timedelta(hours=97) + timedelta(hours=index % 6)
            )
    elif mutation == "future":
        report["generated_at"] = _timestamp(NOW + timedelta(seconds=1))
    else:
        report["deployment"]["deployed_at"] = _timestamp(
            WINDOW_START + timedelta(seconds=1)
        )

    with pytest.raises(
        CwvCertificationError, match=r"window|stale|times|trusted deployment metadata"
    ):
        _evaluate(tmp_path, report, now=now)


def test_schema_and_json_are_closed_and_finite(tmp_path: Path) -> None:
    report = _report()
    report["unexpected"] = True
    with pytest.raises(CwvCertificationError, match="schema validation"):
        _evaluate(tmp_path, report)

    report = _report()
    report["observations"][0]["value"] = math.nan
    with pytest.raises(CwvCertificationError, match="numeric constant"):
        _evaluate(tmp_path, report)


def test_checksum_must_match_exact_report_bytes_and_filename(tmp_path: Path) -> None:
    report_path, checksum_path = _write_evidence(tmp_path, _report())
    deployment_path, deployment_checksum_path = _write_deployment_evidence(tmp_path)
    checksum_path.write_text(f"{'0' * 64}  {report_path.name}\n", encoding="utf-8")
    with pytest.raises(CwvCertificationError, match="checksum mismatch"):
        evaluate_report(
            report_path=report_path,
            checksum_path=checksum_path,
            schema_path=SCHEMA,
            deployment_metadata_path=deployment_path,
            deployment_checksum_path=deployment_checksum_path,
            deployment_schema_path=DEPLOYMENT_SCHEMA,
            policy_path=POLICY,
            expected_commit_sha=COMMIT_SHA,
            expected_image_digest=IMAGE_DIGEST,
            expected_environment="staging",
            expected_deployment_run_id=123456,
            expected_deployment_run_attempt=2,
            now=NOW,
        )


def test_policy_rejects_unknown_fields(tmp_path: Path) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["advisory"] = True
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(CwvCertificationError, match="closed contract"):
        _evaluate(tmp_path, policy_path=policy_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("minimum_observations_per_metric_and_device", 1),
        ("minimum_observations_per_metric_route_group_and_device", 1),
        ("minimum_distinct_sessions_per_device", 1),
        ("minimum_distinct_collectors_per_device", 1),
        ("minimum_distinct_sessions_per_metric_route_group_and_device", 1),
        ("minimum_distinct_collectors_per_metric_route_group_and_device", 1),
        ("maximum_distinct_collectors", 999),
        ("minimum_collection_window_hours", 1),
        ("minimum_active_hours_per_device", 1),
        ("maximum_report_age_hours", 999),
        ("minimum_navigations_per_route_group_and_device", 1),
    ],
)
def test_policy_cannot_weaken_evidence_requirements(
    tmp_path: Path, field: str, value: int
) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy[field] = value
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(CwvCertificationError, match="canonical field CWV policy"):
        _evaluate(tmp_path, policy_path=policy_path)


@pytest.mark.parametrize(
    ("metric", "maximum"),
    [("LCP", 2501), ("INP", 201), ("CLS", 0.11)],
)
def test_policy_cannot_weaken_metric_thresholds(
    tmp_path: Path, metric: str, maximum: float
) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["thresholds"][metric]["maximum"] = maximum
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(CwvCertificationError, match="canonical field CWV policy"):
        _evaluate(tmp_path, policy_path=policy_path)


def test_cli_removes_stale_verdict_before_failed_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path, checksum_path = _write_evidence(tmp_path, _report())
    deployment_path, deployment_checksum_path = _write_deployment_evidence(tmp_path)
    checksum_path.write_text(f"{'0' * 64}  {report_path.name}\n", encoding="utf-8")
    output_path = tmp_path / "cwv-verdict.json"
    output_path.write_text('{"valid":true}', encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_cwv_field.py",
            "--report",
            str(report_path),
            "--checksum",
            str(checksum_path),
            "--schema",
            str(SCHEMA),
            "--deployment-metadata",
            str(deployment_path),
            "--deployment-checksum",
            str(deployment_checksum_path),
            "--deployment-schema",
            str(DEPLOYMENT_SCHEMA),
            "--policy",
            str(POLICY),
            "--expected-commit-sha",
            COMMIT_SHA,
            "--expected-image-digest",
            IMAGE_DIGEST,
            "--expected-deployment-run-id",
            "123456",
            "--expected-deployment-run-attempt",
            "2",
            "--output",
            str(output_path),
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert not output_path.exists()
