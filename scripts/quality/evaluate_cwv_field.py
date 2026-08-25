"""Fail-closed field Core Web Vitals certification for a staging release."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker

MAX_REPORT_BYTES = 25 * 1024 * 1024
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
CHECKSUM_PATTERN = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)\n?")
CANONICAL_POLICY: dict[str, object] = {
    "schema_version": 1,
    "percentile": 75,
    "percentile_algorithm": "nearest-rank",
    "collector": {
        "kind": "web-vitals-rum",
        "library": "web-vitals",
        "library_version": "6.1.1",
        "exporter_version": "1",
        "eligibility": "operator-curated-manual-testers",
        "sampling": "one-final-metric-per-collector-route-hour",
        "maximum_collectors": 50,
    },
    "thresholds": {
        "LCP": {"unit": "ms", "maximum": 2500},
        "INP": {"unit": "ms", "maximum": 200},
        "CLS": {"unit": "score", "maximum": 0.1},
    },
    "required_device_classes": ["mobile", "desktop"],
    "minimum_observations_per_metric_and_device": 100,
    "minimum_observations_per_metric_route_group_and_device": 20,
    "minimum_distinct_sessions_per_device": 25,
    "minimum_distinct_collectors_per_device": 25,
    "minimum_distinct_sessions_per_metric_route_group_and_device": 5,
    "minimum_distinct_collectors_per_metric_route_group_and_device": 20,
    "maximum_distinct_collectors": 50,
    "minimum_collection_window_hours": 24,
    "minimum_active_hours_per_device": 6,
    "maximum_report_age_hours": 72,
    "minimum_navigations_per_route_group_and_device": 5,
    "required_route_groups": [
        "core",
        "content",
        "map_activity",
        "messenger_profile_settings_admin",
    ],
}


class CwvCertificationError(ValueError):
    """Raised when field evidence is incomplete, stale, or over budget."""


def _reject_constant(value: str) -> NoReturn:
    raise CwvCertificationError(f"invalid JSON numeric constant: {value}")


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CwvCertificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, *, maximum_bytes: int | None = None) -> object:
    try:
        size = path.stat().st_size
        if size <= 0:
            raise CwvCertificationError(f"{path} must be non-empty")
        if maximum_bytes is not None and size > maximum_bytes:
            raise CwvCertificationError(f"{path} exceeds {maximum_bytes} bytes")
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except CwvCertificationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CwvCertificationError(f"unable to read {path}: {error}") from error


def _require_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CwvCertificationError(f"{field} must be an object")
    return value


def _require_int(value: object, field: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CwvCertificationError(f"{field} must be an integer >= {minimum}")
    return value


def _require_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CwvCertificationError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise CwvCertificationError(f"{field} must be finite")
    return number


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CwvCertificationError(f"{field} must be a non-empty string")
    return value


def _timestamp(value: object, field: str) -> datetime:
    text = _require_text(value, field)
    if not text.endswith("Z"):
        raise CwvCertificationError(f"{field} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError as error:
        raise CwvCertificationError(f"{field} is not a valid timestamp") from error
    if parsed.tzinfo != UTC:
        raise CwvCertificationError(f"{field} must be UTC")
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise CwvCertificationError(f"unable to hash {path}: {error}") from error
    return digest.hexdigest()


def _verify_checksum(report_path: Path, checksum_path: Path) -> str:
    try:
        checksum_text = checksum_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CwvCertificationError(f"unable to read checksum: {error}") from error
    match = CHECKSUM_PATTERN.fullmatch(checksum_text)
    if match is None or match.group(2) != report_path.name:
        raise CwvCertificationError("checksum must bind exactly the report filename")
    actual = _sha256(report_path)
    if match.group(1) != actual:
        raise CwvCertificationError("report checksum mismatch")
    return actual


def _validate_schema(document: object, schema: object) -> None:
    validator = Draft202012Validator(
        _require_mapping(schema, "schema"), format_checker=FormatChecker()
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "report"
        raise CwvCertificationError(
            f"schema validation failed at {location}: {error.message}"
        )


def _validate_policy(document: object) -> dict[str, object]:
    policy = _require_mapping(document, "policy")
    expected = {
        "schema_version",
        "percentile",
        "percentile_algorithm",
        "collector",
        "thresholds",
        "required_device_classes",
        "minimum_observations_per_metric_and_device",
        "minimum_observations_per_metric_route_group_and_device",
        "minimum_distinct_sessions_per_device",
        "minimum_distinct_collectors_per_device",
        "minimum_distinct_sessions_per_metric_route_group_and_device",
        "minimum_distinct_collectors_per_metric_route_group_and_device",
        "maximum_distinct_collectors",
        "minimum_collection_window_hours",
        "minimum_active_hours_per_device",
        "maximum_report_age_hours",
        "minimum_navigations_per_route_group_and_device",
        "required_route_groups",
    }
    if set(policy) != expected:
        raise CwvCertificationError("policy fields do not match the v1 closed contract")
    if policy["schema_version"] != 1:
        raise CwvCertificationError("policy.schema_version must equal 1")
    if policy["percentile"] != 75 or policy["percentile_algorithm"] != "nearest-rank":
        raise CwvCertificationError("only nearest-rank p75 is supported")
    for name in expected - {
        "schema_version",
        "percentile",
        "percentile_algorithm",
        "collector",
        "thresholds",
        "required_device_classes",
        "required_route_groups",
    }:
        _require_int(policy[name], f"policy.{name}")
    thresholds = _require_mapping(policy["thresholds"], "policy.thresholds")
    if set(thresholds) != {"LCP", "INP", "CLS"}:
        raise CwvCertificationError("policy.thresholds must define LCP, INP, and CLS")
    expected_units = {"LCP": "ms", "INP": "ms", "CLS": "score"}
    for metric, unit in expected_units.items():
        threshold = _require_mapping(thresholds[metric], f"policy.thresholds.{metric}")
        if set(threshold) != {"unit", "maximum"} or threshold["unit"] != unit:
            raise CwvCertificationError(
                f"policy threshold contract invalid for {metric}"
            )
        _require_number(threshold["maximum"], f"policy.thresholds.{metric}.maximum")
    devices = policy["required_device_classes"]
    if devices != ["mobile", "desktop"]:
        raise CwvCertificationError("policy device classes must be mobile and desktop")
    route_groups = policy["required_route_groups"]
    if (
        not isinstance(route_groups, list)
        or not route_groups
        or not all(isinstance(item, str) and item for item in route_groups)
    ):
        raise CwvCertificationError(
            "policy.required_route_groups must be a non-empty list"
        )
    if len(route_groups) != len(set(route_groups)):
        raise CwvCertificationError("policy.required_route_groups contains duplicates")
    collector = _require_mapping(policy["collector"], "policy.collector")
    if collector != CANONICAL_POLICY["collector"]:
        raise CwvCertificationError("policy collector contract is not canonical")
    if policy != CANONICAL_POLICY:
        raise CwvCertificationError(
            "policy does not match the canonical field CWV policy"
        )
    return policy


def nearest_rank(values: list[float], percentile: int = 75) -> float:
    """Return the nearest-rank percentile without interpolation."""

    if not values:
        raise CwvCertificationError(
            "cannot calculate a percentile for an empty segment"
        )
    if percentile < 1 or percentile > 100:
        raise CwvCertificationError("percentile must be in the range 1..100")
    ordered = sorted(values)
    return ordered[math.ceil((percentile / 100) * len(ordered)) - 1]


def _atomic_write(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = stream.name
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _invalidate_output(output: Path, inputs: tuple[Path, ...]) -> None:
    output_resolved = output.resolve(strict=False)
    if any(output_resolved == path.resolve(strict=False) for path in inputs):
        raise CwvCertificationError("output must be distinct from every input")
    try:
        output.unlink(missing_ok=True)
    except OSError as error:
        raise CwvCertificationError(
            f"unable to invalidate stale output: {error}"
        ) from error


def evaluate_report(
    *,
    report_path: Path,
    checksum_path: Path,
    schema_path: Path,
    deployment_metadata_path: Path,
    deployment_checksum_path: Path,
    deployment_schema_path: Path,
    policy_path: Path,
    expected_commit_sha: str,
    expected_image_digest: str,
    expected_environment: str,
    expected_deployment_run_id: int,
    expected_deployment_run_attempt: int,
    now: datetime | None = None,
) -> dict[str, object]:
    """Validate raw observations and return a deterministic certification verdict."""

    if SHA_PATTERN.fullmatch(expected_commit_sha) is None:
        raise CwvCertificationError("expected commit SHA is invalid")
    if DIGEST_PATTERN.fullmatch(expected_image_digest) is None:
        raise CwvCertificationError("expected frontend image digest is invalid")
    if expected_environment != "staging":
        raise CwvCertificationError("field certification environment must be staging")
    expected_run = _require_int(
        expected_deployment_run_id, "expected deployment run ID"
    )
    expected_attempt = _require_int(
        expected_deployment_run_attempt, "expected deployment run attempt"
    )
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo != UTC:
        raise CwvCertificationError("current time must be timezone-aware UTC")

    report_hash = _verify_checksum(report_path, checksum_path)
    deployment_metadata_hash = _verify_checksum(
        deployment_metadata_path, deployment_checksum_path
    )
    report_object = _load_json(report_path, maximum_bytes=MAX_REPORT_BYTES)
    schema_object = _load_json(schema_path)
    deployment_metadata_object = _load_json(deployment_metadata_path)
    deployment_schema_object = _load_json(deployment_schema_path)
    policy = _validate_policy(_load_json(policy_path))
    _validate_schema(report_object, schema_object)
    _validate_schema(deployment_metadata_object, deployment_schema_object)
    report = _require_mapping(report_object, "report")
    trusted_deployment = _require_mapping(
        deployment_metadata_object, "trusted deployment metadata"
    )

    identity_expectations = {
        "release_sha": expected_commit_sha,
        "frontend_image_digest": expected_image_digest,
        "environment": expected_environment,
    }
    for name, expected in identity_expectations.items():
        if report[name] != expected:
            raise CwvCertificationError(f"report {name} mismatch")
        if trusted_deployment[name] != expected:
            raise CwvCertificationError(f"trusted deployment metadata {name} mismatch")
    deployment = _require_mapping(report["deployment"], "report.deployment")
    if deployment["workflow_run_id"] != expected_run:
        raise CwvCertificationError("deployment workflow run ID mismatch")
    if deployment["workflow_run_attempt"] != expected_attempt:
        raise CwvCertificationError("deployment workflow run attempt mismatch")
    if trusted_deployment["workflow_run_id"] != expected_run:
        raise CwvCertificationError("trusted deployment metadata run ID mismatch")
    if trusted_deployment["workflow_run_attempt"] != expected_attempt:
        raise CwvCertificationError("trusted deployment metadata run attempt mismatch")
    for field in ("deployed_at", "deployment_url"):
        if deployment[field] != trusted_deployment[field]:
            raise CwvCertificationError(
                f"report {field} does not match trusted deployment metadata"
            )
    collector = _require_mapping(report["collector"], "report.collector")
    if collector != policy["collector"]:
        raise CwvCertificationError("collector contract mismatch")

    deployed_at = _timestamp(deployment["deployed_at"], "deployment.deployed_at")
    generated_at = _timestamp(report["generated_at"], "generated_at")
    window = _require_mapping(report["window"], "report.window")
    window_start = _timestamp(window["start"], "window.start")
    window_end = _timestamp(window["end"], "window.end")
    minimum_window = _require_int(
        policy["minimum_collection_window_hours"], "minimum_collection_window_hours"
    )
    maximum_age = _require_int(
        policy["maximum_report_age_hours"], "maximum_report_age_hours"
    )
    if not (deployed_at <= window_start < window_end <= generated_at <= current_time):
        raise CwvCertificationError(
            "deployment, collection window, and report times are inconsistent"
        )
    if (window_end - window_start).total_seconds() < minimum_window * 3600:
        raise CwvCertificationError("collection window is too short")
    if (current_time - generated_at).total_seconds() > maximum_age * 3600:
        raise CwvCertificationError("field report is stale")
    if (current_time - window_end).total_seconds() > maximum_age * 3600:
        raise CwvCertificationError("field data window is stale")

    observations = cast(list[dict[str, object]], report["observations"])
    segments: dict[tuple[str, str], list[float]] = defaultdict(list)
    route_metric_segments: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    sessions: dict[str, set[str]] = defaultdict(set)
    collectors: dict[str, set[str]] = defaultdict(set)
    active_hours: dict[str, set[datetime]] = defaultdict(set)
    route_metric_navigations: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    route_metric_sessions: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    route_metric_collectors: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    collector_hour_samples: set[tuple[str, str, str, datetime]] = set()
    metric_ids: set[str] = set()
    navigation_metrics: set[tuple[str, str]] = set()
    navigation_metadata: dict[str, tuple[str, str, str]] = {}
    for index, observation in enumerate(observations):
        field = f"observations[{index}]"
        if observation["release_sha"] != expected_commit_sha:
            raise CwvCertificationError(f"{field} release SHA mismatch")
        if observation["frontend_image_digest"] != expected_image_digest:
            raise CwvCertificationError(f"{field} image digest mismatch")
        if observation["automated"] is not False or observation["final"] is not True:
            raise CwvCertificationError(f"{field} must be final and non-automated")
        metric = cast(str, observation["metric"])
        metric_id = cast(str, observation["metric_id"])
        if metric_id in metric_ids:
            raise CwvCertificationError(f"duplicate metric identity: {metric_id}")
        metric_ids.add(metric_id)
        observed_at = _timestamp(observation["observed_at"], f"{field}.observed_at")
        if not (window_start <= observed_at <= window_end):
            raise CwvCertificationError(f"{field} falls outside the collection window")
        device = cast(str, observation["device_class"])
        route_group = cast(str, observation["route_group"])
        navigation_id = cast(str, observation["navigation_id"])
        session_id = cast(str, observation["session_id"])
        collector_id = cast(str, observation["collector_id"])
        navigation_metric = (navigation_id, metric)
        if navigation_metric in navigation_metrics:
            raise CwvCertificationError(
                f"duplicate navigation metric: {navigation_id}/{metric}"
            )
        navigation_metrics.add(navigation_metric)
        metadata = (device, session_id, route_group)
        previous_metadata = navigation_metadata.setdefault(navigation_id, metadata)
        if previous_metadata != metadata:
            raise CwvCertificationError(
                f"inconsistent navigation metadata: {navigation_id}"
            )
        value = _require_number(observation["value"], f"{field}.value")
        segments[(device, metric)].append(value)
        route_metric_segments[(device, route_group, metric)].append(value)
        sessions[device].add(session_id)
        collectors[device].add(collector_id)
        active_hours[device].add(observed_at.replace(minute=0, second=0, microsecond=0))
        route_metric_navigations[(device, route_group, metric)].add(navigation_id)
        route_metric_sessions[(device, route_group, metric)].add(session_id)
        route_metric_collectors[(device, route_group, metric)].add(collector_id)
        sample_key = (
            collector_id,
            route_group,
            metric,
            observed_at.replace(minute=0, second=0, microsecond=0),
        )
        if sample_key in collector_hour_samples:
            raise CwvCertificationError(
                f"duplicate manual collector sampling bucket: {collector_id}"
            )
        collector_hour_samples.add(sample_key)

    minimum_observations = _require_int(
        policy["minimum_observations_per_metric_and_device"],
        "minimum_observations_per_metric_and_device",
    )
    minimum_sessions = _require_int(
        policy["minimum_distinct_sessions_per_device"],
        "minimum_distinct_sessions_per_device",
    )
    minimum_collectors = _require_int(
        policy["minimum_distinct_collectors_per_device"],
        "minimum_distinct_collectors_per_device",
    )
    minimum_route_observations = _require_int(
        policy["minimum_observations_per_metric_route_group_and_device"],
        "minimum_observations_per_metric_route_group_and_device",
    )
    minimum_route_sessions = _require_int(
        policy["minimum_distinct_sessions_per_metric_route_group_and_device"],
        "minimum_distinct_sessions_per_metric_route_group_and_device",
    )
    minimum_route_collectors = _require_int(
        policy["minimum_distinct_collectors_per_metric_route_group_and_device"],
        "minimum_distinct_collectors_per_metric_route_group_and_device",
    )
    maximum_collectors = _require_int(
        policy["maximum_distinct_collectors"], "maximum_distinct_collectors"
    )
    minimum_active_hours = _require_int(
        policy["minimum_active_hours_per_device"], "minimum_active_hours_per_device"
    )
    minimum_navigations = _require_int(
        policy["minimum_navigations_per_route_group_and_device"],
        "minimum_navigations_per_route_group_and_device",
    )
    thresholds = cast(dict[str, dict[str, object]], policy["thresholds"])
    device_classes = cast(list[str], policy["required_device_classes"])
    route_groups = cast(list[str], policy["required_route_groups"])
    segment_verdicts: dict[str, dict[str, object]] = {}
    route_segment_verdicts: dict[str, dict[str, object]] = {}
    all_collectors = set().union(*collectors.values())
    if len(all_collectors) > maximum_collectors:
        raise CwvCertificationError("report exceeds the trusted collector cohort")
    for device in device_classes:
        if len(sessions[device]) < minimum_sessions:
            raise CwvCertificationError(f"{device} has insufficient distinct sessions")
        if len(collectors[device]) < minimum_collectors:
            raise CwvCertificationError(
                f"{device} has insufficient distinct collectors"
            )
        if len(active_hours[device]) < minimum_active_hours:
            raise CwvCertificationError(f"{device} has insufficient active hours")
        for route_group in route_groups:
            for metric, threshold in thresholds.items():
                route_key = (device, route_group, metric)
                route_values = route_metric_segments[route_key]
                if len(route_values) < minimum_route_observations:
                    raise CwvCertificationError(
                        f"{device}/{route_group}/{metric} has insufficient route observations"
                    )
                if len(route_metric_navigations[route_key]) < minimum_navigations:
                    raise CwvCertificationError(
                        f"{device}/{route_group}/{metric} has insufficient route coverage"
                    )
                if len(route_metric_sessions[route_key]) < minimum_route_sessions:
                    raise CwvCertificationError(
                        f"{device}/{route_group}/{metric} has insufficient route sessions"
                    )
                if len(route_metric_collectors[route_key]) < minimum_route_collectors:
                    raise CwvCertificationError(
                        f"{device}/{route_group}/{metric} has insufficient route collectors"
                    )
                route_p75 = nearest_rank(route_values)
                route_maximum = _require_number(
                    threshold["maximum"], f"thresholds.{metric}.maximum"
                )
                if route_p75 > route_maximum:
                    raise CwvCertificationError(
                        f"{device}/{route_group}/{metric} p75 {route_p75} "
                        f"exceeds maximum {route_maximum}"
                    )
                route_segment_verdicts[f"{device}/{route_group}/{metric}"] = {
                    "observations": len(route_values),
                    "navigations": len(route_metric_navigations[route_key]),
                    "sessions": len(route_metric_sessions[route_key]),
                    "collectors": len(route_metric_collectors[route_key]),
                    "p75": route_p75,
                    "maximum": route_maximum,
                    "unit": threshold["unit"],
                }
        for metric, threshold in thresholds.items():
            values = segments[(device, metric)]
            if len(values) < minimum_observations:
                raise CwvCertificationError(
                    f"{device}/{metric} has insufficient observations"
                )
            p75 = nearest_rank(values)
            maximum = _require_number(
                threshold["maximum"], f"thresholds.{metric}.maximum"
            )
            if p75 > maximum:
                raise CwvCertificationError(
                    f"{device}/{metric} p75 {p75} exceeds maximum {maximum}"
                )
            segment_verdicts[f"{device}/{metric}"] = {
                "observations": len(values),
                "p75": p75,
                "maximum": maximum,
                "unit": threshold["unit"],
            }

    return {
        "schema_version": 1,
        "valid": True,
        "release_sha": expected_commit_sha,
        "frontend_image_digest": expected_image_digest,
        "environment": expected_environment,
        "deployment_workflow_run_id": expected_run,
        "deployment_workflow_run_attempt": expected_attempt,
        "report_sha256": report_hash,
        "deployment_metadata_sha256": deployment_metadata_hash,
        "policy_sha256": _sha256(policy_path),
        "generated_at": cast(str, report["generated_at"]),
        "window": report["window"],
        "segments": segment_verdicts,
        "route_segments": route_segment_verdicts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--deployment-metadata", type=Path, required=True)
    parser.add_argument("--deployment-checksum", type=Path, required=True)
    parser.add_argument("--deployment-schema", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    parser.add_argument("--expected-image-digest", required=True)
    parser.add_argument("--expected-environment", default="staging")
    parser.add_argument("--expected-deployment-run-id", type=int, required=True)
    parser.add_argument("--expected-deployment-run-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        _invalidate_output(
            args.output,
            (
                args.report,
                args.checksum,
                args.schema,
                args.deployment_metadata,
                args.deployment_checksum,
                args.deployment_schema,
                args.policy,
            ),
        )
        verdict = evaluate_report(
            report_path=args.report,
            checksum_path=args.checksum,
            schema_path=args.schema,
            deployment_metadata_path=args.deployment_metadata,
            deployment_checksum_path=args.deployment_checksum,
            deployment_schema_path=args.deployment_schema,
            policy_path=args.policy,
            expected_commit_sha=args.expected_commit_sha,
            expected_image_digest=args.expected_image_digest,
            expected_environment=args.expected_environment,
            expected_deployment_run_id=args.expected_deployment_run_id,
            expected_deployment_run_attempt=args.expected_deployment_run_attempt,
        )
        _atomic_write(args.output, verdict)
    except CwvCertificationError as error:
        parser.exit(1, f"field CWV certification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
