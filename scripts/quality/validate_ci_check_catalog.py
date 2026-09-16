#!/usr/bin/env python3
"""Validate the repository's machine-readable GitHub Actions check catalog.

The catalog is deliberately static and local: it never calls GitHub and never
changes workflow execution.  It is a fail-closed inventory of every workflow
and job, with profile inheritance for ownership, required/advisory policy,
artifact provenance, runbooks, retry policy, and execution budgets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = REPOSITORY_ROOT / "quality" / "ci-check-catalog.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "quality" / "ci-check-catalog.schema.json"
WORKFLOW_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
WORKFLOW_EVENTS = frozenset(
    {
        "push",
        "pull_request",
        "schedule",
        "workflow_dispatch",
        "repository_dispatch",
        "workflow_call",
    }
)
POLICY_EVENTS = frozenset({"pull_request_main", "push_main"})
RETRY_MARKERS = (
    "retry",
    "for attempt",
    "max_attempts",
    "retry-all-errors",
    "retries",
)


class CatalogError(ValueError):
    """Raised when a catalog cannot be trusted as a complete inventory."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise CatalogError(f"non-finite JSON number: {value}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise CatalogError(f"JSON root must be an object: {path}")
    return loaded


def _load_workflow(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogError(f"cannot read workflow {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise CatalogError(f"workflow root must be an object: {path}")
    return loaded


def workflow_triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return the YAML ``on`` mapping, including PyYAML's YAML 1.1 quirk."""

    raw = workflow.get("on", workflow.get(True, {}))
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {str(item): None for item in raw}
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    raise CatalogError("workflow trigger declaration must be a string, list, or object")


def _canonical(value: Any) -> str:
    """Render YAML values deterministically for a source-bound guard string."""

    if value is None:
        return "any"
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise CatalogError(f"workflow guard is not JSON-renderable: {value!r}") from exc


def _workflow_path(path: str, repository_root: Path) -> Path:
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise CatalogError(f"workflow path must be a relative POSIX path: {path!r}")
    if "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise CatalogError(f"workflow path is not canonical: {path!r}")
    candidate = (repository_root / Path(path)).resolve()
    root = repository_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise CatalogError(f"path escapes repository: {path!r}") from exc
    return candidate


def _repo_file(path: str, repository_root: Path, field: str) -> Path:
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise CatalogError(f"{field} must be a relative POSIX path: {path!r}")
    if "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise CatalogError(f"{field} is not canonical: {path!r}")
    candidate = (repository_root / Path(path)).resolve()
    try:
        candidate.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise CatalogError(f"{field} escapes repository: {path!r}") from exc
    if not candidate.is_file():
        raise CatalogError(f"{field} does not exist: {path!r}")
    return candidate


def _as_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{field} must be a non-empty string")
    return value


def _is_retry_candidate(job: dict[str, Any]) -> bool:
    try:
        rendered = json.dumps(
            job, ensure_ascii=False, sort_keys=True, default=str
        ).lower()
    except (TypeError, ValueError):
        rendered = repr(job).lower()
    return any(marker in rendered for marker in RETRY_MARKERS)


def _artifact_inventory(job: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for step in job.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        action = str(step.get("uses", "")).lower()
        if not action.startswith("actions/upload-artifact@"):
            continue
        with_values = step.get("with") or {}
        if not isinstance(with_values, dict):
            raise CatalogError("upload-artifact step has malformed with mapping")
        name = with_values.get("name")
        path = with_values.get("path")
        if not isinstance(name, str) or not name.strip():
            raise CatalogError("upload-artifact step has no non-empty artifact name")
        if not isinstance(path, str) or not path.strip():
            raise CatalogError(f"artifact {name!r} has no non-empty path")
        if "quality-evidence-" in name and "run_attempt" in name:
            provenance = "run_id_attempt"
        elif "github.sha" in name:
            provenance = "sha"
        elif "run_attempt" in name or "run_id" in name:
            provenance = "run_id_attempt"
        elif "inputs." in name:
            provenance = "input"
        else:
            provenance = "none"
        artifacts.append(
            {
                "name_pattern": name,
                "path_pattern": path,
                "required": False,
                "provenance": provenance,
            }
        )
    return artifacts


def _matrix_governance_errors(
    source_job: dict[str, Any], effective: dict[str, Any], location: str
) -> list[str]:
    """Require an explicit, source-bound concurrency contract for matrices."""

    strategy = source_job.get("strategy")
    has_matrix = isinstance(strategy, dict) and "matrix" in strategy
    governance = effective.get("matrix_governance")
    if not has_matrix:
        if governance is not None:
            return [f"{location}: matrix_governance is present for a non-matrix job"]
        return []

    if not isinstance(governance, dict):
        return [f"{location}: matrix_governance is missing"]

    errors: list[str] = []
    has_max_parallel = "max_parallel" in governance
    has_unbounded_justification = "unbounded_justification" in governance
    source_has_max_parallel = "max-parallel" in strategy
    source_max_parallel = strategy.get("max-parallel")

    if source_has_max_parallel:
        if (
            not isinstance(source_max_parallel, int)
            or isinstance(source_max_parallel, bool)
            or source_max_parallel < 1
        ):
            errors.append(f"{location}: source max-parallel is invalid")
        if not has_max_parallel:
            errors.append(
                f"{location}: source declares max-parallel; "
                "matrix_governance.max_parallel is required"
            )
        elif governance.get("max_parallel") != source_max_parallel:
            errors.append(
                f"{location}: matrix max_parallel differs from workflow "
                f"(catalog={governance.get('max_parallel')!r}, "
                f"source={source_max_parallel!r})"
            )
        if has_unbounded_justification:
            errors.append(
                f"{location}: bounded matrix cannot declare unbounded_justification"
            )
    else:
        if has_max_parallel:
            errors.append(
                f"{location}: source has no max-parallel; use unbounded_justification"
            )
        if not has_unbounded_justification:
            errors.append(
                f"{location}: unbounded matrix requires unbounded_justification"
            )

    if has_unbounded_justification:
        justification = governance.get("unbounded_justification")
        if not isinstance(justification, dict):
            errors.append(f"{location}: unbounded_justification must be an object")
        else:
            for field in ("owner", "event_profile", "rationale"):
                value = justification.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"{location}: unbounded_justification.{field} must be non-empty"
                    )
    return errors


def _job_timeout(job: dict[str, Any], *, reusable_timeouts: dict[str, int]) -> int:
    timeout = job.get("timeout-minutes")
    if isinstance(timeout, int) and not isinstance(timeout, bool):
        return timeout
    uses = job.get("uses")
    if isinstance(uses, str) and uses.startswith("./.github/workflows/"):
        return reusable_timeouts.get(uses, 60)
    # External reusable workflow budgets are intentionally explicit in the
    # catalog but cannot be compared to a local timeout declaration.
    if uses:
        return 60
    raise CatalogError("job has neither runs-on timeout-minutes nor uses")


def _reusable_timeout_index(workflow_directory: Path) -> dict[str, int]:
    index: dict[str, int] = {}
    for path in workflow_directory.glob("*.y*ml"):
        workflow = _load_workflow(path)
        try:
            triggers = workflow_triggers(workflow)
        except CatalogError:
            continue
        if "workflow_call" not in triggers:
            continue
        timeouts = [
            job.get("timeout-minutes")
            for job in (workflow.get("jobs") or {}).values()
            if isinstance(job, dict) and isinstance(job.get("timeout-minutes"), int)
        ]
        if timeouts:
            relative = f"./.github/workflows/{path.name}"
            index[relative] = max(timeouts)
    return index


def _schema_errors(catalog: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        f"schema: {error.json_path}: {error.message}"
        for error in sorted(
            validator.iter_errors(catalog), key=lambda item: item.json_path
        )
    ]


def _effective_profile(
    profile_name: str, profiles: dict[str, Any], *, location: str
) -> dict[str, Any]:
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise CatalogError(f"{location} references unknown profile {profile_name!r}")
    effective = dict(profile)
    effective["_profile"] = profile_name
    return effective


def _merge_job(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile)
    merged.update({key: value for key, value in job.items() if key != "profile"})
    return merged


def _validate_artifacts(
    effective: dict[str, Any], expected: list[dict[str, Any]], location: str
) -> list[str]:
    errors: list[str] = []
    actual = effective.get("artifacts")
    if actual != expected:
        errors.append(
            f"{location}: artifact metadata does not match upload-artifact steps "
            f"(catalog={actual!r}, source={expected!r})"
        )
    return errors


def _validate_external_checks(
    entries: object,
    *,
    profiles: dict[str, Any],
    repository_root: Path,
    source_contexts: set[str],
    used_profiles: set[str],
) -> tuple[list[str], set[str]]:
    """Validate checks emitted by a provider outside repository workflows."""

    errors: list[str] = []
    contexts: set[str] = set()
    if not isinstance(entries, list):
        return ["catalog.external_checks must be an array"], contexts
    for index, entry in enumerate(entries):
        location = f"external_checks[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{location} must be an object")
            continue
        provider = entry.get("provider")
        context = entry.get("context")
        integration_id = entry.get("integration_id")
        source_reference = entry.get("source_reference")
        if not isinstance(provider, str) or not provider.strip():
            errors.append(f"{location}.provider must be non-empty")
        if not isinstance(context, str) or not context.strip():
            errors.append(f"{location}.context must be non-empty")
            continue
        if context in contexts:
            errors.append(f"{location}: duplicate provider context {context!r}")
        if context in source_contexts:
            errors.append(
                f"{location}: provider context collides with a source check {context!r}"
            )
        contexts.add(context)
        if (
            not isinstance(integration_id, int)
            or isinstance(integration_id, bool)
            or integration_id < 1
        ):
            errors.append(f"{location}.integration_id is invalid")
        if not isinstance(source_reference, str) or not source_reference.strip():
            errors.append(f"{location}.source_reference must be non-empty")
        if entry.get("externally_owned") is not True:
            errors.append(f"{location}.externally_owned must be true")
        owner = entry.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"{location}.owner must be non-empty")
        profile_name = entry.get("profile")
        if not isinstance(profile_name, str):
            errors.append(f"{location}.profile must be a string")
            continue
        try:
            profile = _effective_profile(profile_name, profiles, location=location)
        except CatalogError as exc:
            errors.append(str(exc))
            continue
        used_profiles.add(profile_name)
        effective = _merge_job(profile, entry)
        if entry.get("classification") != effective.get("classification"):
            errors.append(f"{location}.classification does not match profile")
        classification = effective.get("classification")
        required_events = effective.get("required_events")
        if classification == "required":
            if not required_events:
                errors.append(
                    f"{location}: required provider check has no required_events"
                )
            elif not set(required_events).issubset(POLICY_EVENTS):
                errors.append(f"{location}: unsupported required event alias")
        elif required_events:
            errors.append(
                f"{location}: non-required provider check has required_events"
            )
        try:
            _repo_file(entry.get("runbook"), repository_root, f"{location}.runbook")
        except CatalogError as exc:
            errors.append(str(exc))
    return errors, contexts


def _validate_expansions(
    entries: object,
    *,
    profiles: dict[str, Any],
    repository_root: Path,
    workflow_directory: Path,
    source_paths: set[str],
    source_contexts: set[str],
    external_contexts: set[str],
    used_profiles: set[str],
) -> list[str]:
    """Validate caller-qualified and matrix-expanded protected contexts."""

    errors: list[str] = []
    if not isinstance(entries, list):
        return ["catalog.expansions must be an array"]
    seen_ids: set[str] = set()
    seen_contexts: set[str] = set()
    known_contexts = source_contexts | external_contexts
    for index, entry in enumerate(entries):
        location = f"expansions[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{location} must be an object")
            continue
        expansion_id = entry.get("id")
        if not isinstance(expansion_id, str) or not expansion_id.strip():
            errors.append(f"{location}.id must be non-empty")
        elif expansion_id in seen_ids:
            errors.append(f"{location}: duplicate expansion id {expansion_id!r}")
        else:
            seen_ids.add(expansion_id)
        kind = entry.get("kind")
        if kind not in {"reusable_workflow", "matrix"}:
            errors.append(f"{location}.kind is unsupported")
        caller_path_value = entry.get("caller_workflow_path")
        caller_job_id = entry.get("caller_job_id")
        try:
            caller_path = _workflow_path(caller_path_value, repository_root)
            caller_relative = caller_path.relative_to(repository_root).as_posix()
            if caller_relative not in source_paths:
                errors.append(f"{location}: caller workflow is not in source inventory")
            caller_workflow = _load_workflow(caller_path)
        except CatalogError as exc:
            errors.append(f"{location}: {exc}")
            caller_workflow = None
        source_jobs = (
            caller_workflow.get("jobs") if isinstance(caller_workflow, dict) else None
        )
        if not isinstance(source_jobs, dict):
            source_jobs = {}
        if not isinstance(caller_job_id, str) or not caller_job_id:
            errors.append(f"{location}.caller_job_id must be non-empty")
            caller_job = None
        else:
            caller_job = source_jobs.get(caller_job_id)
            if not isinstance(caller_job, dict):
                errors.append(
                    f"{location}: caller job does not exist: {caller_job_id!r}"
                )
                caller_job = None
        profile_name = entry.get("profile")
        profile: dict[str, Any] | None = None
        if not isinstance(profile_name, str):
            errors.append(f"{location}.profile must be a string")
        else:
            try:
                profile = _effective_profile(profile_name, profiles, location=location)
                used_profiles.add(profile_name)
            except CatalogError as exc:
                errors.append(str(exc))
        owner = entry.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"{location}.owner must be non-empty")
        source_reference = entry.get("source_reference")
        if not isinstance(source_reference, str) or not source_reference.strip():
            errors.append(f"{location}.source_reference must be non-empty")
        try:
            _repo_file(entry.get("runbook"), repository_root, f"{location}.runbook")
        except CatalogError as exc:
            errors.append(str(exc))
        if kind == "reusable_workflow":
            reusable_path_value = entry.get("reusable_workflow_path")
            try:
                reusable_path = _workflow_path(reusable_path_value, repository_root)
                reusable_workflow = _load_workflow(reusable_path)
                reusable_triggers = workflow_triggers(reusable_workflow)
                if "workflow_call" not in reusable_triggers:
                    errors.append(f"{location}: reusable workflow is not workflow_call")
                expected_uses = (
                    f"./{reusable_path.relative_to(repository_root).as_posix()}"
                )
                if (
                    isinstance(caller_job, dict)
                    and caller_job.get("uses") != expected_uses
                ):
                    errors.append(
                        f"{location}: caller uses does not bind to reusable workflow "
                        f"(catalog={expected_uses!r}, source={caller_job.get('uses')!r})"
                    )
                reusable_jobs = reusable_workflow.get("jobs")
                if not isinstance(reusable_jobs, dict):
                    reusable_jobs = {}
                reusable_job_ids = entry.get("reusable_job_ids")
                if isinstance(entry.get("reusable_job_id"), str):
                    reusable_job_ids = [entry["reusable_job_id"]]
                if not isinstance(reusable_job_ids, list) or not reusable_job_ids:
                    errors.append(f"{location}: reusable_job_ids are missing")
                else:
                    for reusable_job_id in reusable_job_ids:
                        if not isinstance(reusable_job_id, str):
                            errors.append(
                                f"{location}: reusable job ID must be a string"
                            )
                            continue
                        if reusable_job_id not in reusable_jobs:
                            errors.append(
                                f"{location}: reusable job does not exist: {reusable_job_id!r}"
                            )
            except CatalogError as exc:
                errors.append(f"{location}: {exc}")
        elif kind == "matrix" and isinstance(caller_job, dict):
            strategy = caller_job.get("strategy")
            matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
            conditional_name = "${{" in str(caller_job.get("name", ""))
            if not isinstance(matrix, dict) and not conditional_name:
                errors.append(
                    f"{location}: matrix caller has no matrix or conditional name"
                )
        if profile is not None:
            if entry.get("classification") != profile.get("classification"):
                errors.append(f"{location}.classification does not match profile")
            classification = profile.get("classification")
            required_events = profile.get("required_events")
            source_events = set()
            if isinstance(caller_workflow, dict):
                try:
                    source_events = set(workflow_triggers(caller_workflow))
                except CatalogError:
                    pass
            if classification == "required":
                if not required_events:
                    errors.append(
                        f"{location}: required expansion has no required_events"
                    )
                elif not set(required_events).issubset(POLICY_EVENTS):
                    errors.append(f"{location}: unsupported required event alias")
                elif (
                    "pull_request_main" in required_events
                    and "pull_request" not in source_events
                ):
                    errors.append(
                        f"{location}: pull_request_main is not a source event"
                    )
                elif "push_main" in required_events and "push" not in source_events:
                    errors.append(f"{location}: push_main is not a source event")
            elif required_events:
                errors.append(f"{location}: non-required expansion has required_events")
        declared_contexts = entry.get("declared_contexts")
        template = entry.get("context_template")
        if isinstance(declared_contexts, list):
            declared_seen: set[str] = set()
            for context in declared_contexts:
                if isinstance(context, str):
                    if context in declared_seen:
                        errors.append(f"{location}: duplicate expanded context")
                    declared_seen.add(context)
            contexts_to_check = declared_contexts
        else:
            contexts_to_check = [template] if isinstance(template, str) else []
        for context in contexts_to_check:
            if not isinstance(context, str) or not context.strip():
                errors.append(f"{location}: expanded context must be non-empty")
                continue
            if context in seen_contexts:
                errors.append(f"{location}: duplicate expanded context {context!r}")
            seen_contexts.add(context)
            if context in known_contexts:
                errors.append(
                    f"{location}: expanded context collides with existing context {context!r}"
                )
    return errors


def validate_catalog(
    catalog: dict[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    workflow_directory: Path | None = None,
    schema: dict[str, Any] | None = None,
) -> list[str]:
    """Return all fail-closed catalog errors; an empty list means valid."""

    errors: list[str] = []
    if schema is not None:
        errors.extend(_schema_errors(catalog, schema))
    workflow_directory = workflow_directory or repository_root / ".github" / "workflows"
    if not workflow_directory.is_dir():
        return [f"workflow directory is missing: {workflow_directory}"]
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict):
        return [*errors, "catalog.profiles must be an object"]
    default_runbook = catalog.get("default_runbook")
    try:
        if isinstance(default_runbook, str):
            _repo_file(default_runbook, repository_root, "default_runbook")
    except CatalogError as exc:
        errors.append(str(exc))

    raw_workflows = catalog.get("workflows")
    if not isinstance(raw_workflows, list):
        return [*errors, "catalog.workflows must be an array"]
    source_paths = {
        path.relative_to(repository_root).as_posix()
        for path in workflow_directory.glob("*.y*ml")
    }
    catalog_paths: list[str] = []
    used_profiles: set[str] = set()
    source_contexts: set[str] = set()
    reusable_timeouts = _reusable_timeout_index(workflow_directory)
    for index, entry in enumerate(raw_workflows):
        location = f"workflows[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{location} must be an object")
            continue
        path_value = entry.get("path")
        if not isinstance(path_value, str):
            errors.append(f"{location}.path must be a string")
            continue
        catalog_paths.append(path_value)
        try:
            workflow_path = _workflow_path(path_value, repository_root)
            workflow = _load_workflow(workflow_path)
            triggers = workflow_triggers(workflow)
        except CatalogError as exc:
            errors.append(f"{location}: {exc}")
            continue
        if path_value not in source_paths:
            errors.append(f"{location}: workflow is not present in .github/workflows")
        if entry.get("name") != workflow.get("name", workflow_path.stem):
            errors.append(f"{location}: workflow name is stale")
        owner = entry.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"{location}.owner must be non-empty")
        event_entries = entry.get("events")
        if not isinstance(event_entries, list):
            errors.append(f"{location}.events must be an array")
            event_entries = []
        source_events = set(triggers)
        catalog_events: set[str] = set()
        for event_index, event_entry in enumerate(event_entries):
            event_location = f"{location}.events[{event_index}]"
            if not isinstance(event_entry, dict):
                errors.append(f"{event_location} must be an object")
                continue
            event_name = event_entry.get("event")
            guard = event_entry.get("guard")
            if event_name not in WORKFLOW_EVENTS:
                errors.append(f"{event_location}.event is unsupported: {event_name!r}")
                continue
            catalog_events.add(event_name)
            expected_guard = _canonical(triggers.get(event_name))
            if guard != expected_guard:
                errors.append(f"{event_location}.guard is stale")
        if catalog_events != source_events:
            errors.append(
                f"{location}: event inventory mismatch "
                f"(catalog={sorted(catalog_events)}, source={sorted(source_events)})"
            )
        jobs = entry.get("jobs")
        source_jobs = workflow.get("jobs")
        if not isinstance(source_jobs, dict):
            errors.append(f"{location}: source jobs must be an object")
            source_jobs = {}
        if not isinstance(jobs, dict):
            errors.append(f"{location}.jobs must be an object")
            jobs = {}
        source_job_ids = {str(job_id) for job_id in source_jobs}
        catalog_job_ids = {str(job_id) for job_id in jobs}
        if source_job_ids != catalog_job_ids:
            errors.append(
                f"{location}: job inventory mismatch "
                f"(catalog={sorted(catalog_job_ids)}, source={sorted(source_job_ids)})"
            )
        for job_id, job_entry in jobs.items():
            job_location = f"{location}.jobs[{job_id!r}]"
            source_job = source_jobs.get(job_id)
            if not isinstance(source_job, dict):
                errors.append(f"{job_location}: source job is not an object")
                continue
            if not isinstance(job_entry, dict):
                errors.append(f"{job_location} must be an object")
                continue
            profile_name = job_entry.get("profile")
            if not isinstance(profile_name, str):
                errors.append(f"{job_location}.profile must be a string")
                continue
            try:
                profile = _effective_profile(
                    profile_name, profiles, location=job_location
                )
            except CatalogError as exc:
                errors.append(str(exc))
                continue
            used_profiles.add(profile_name)
            effective = _merge_job(profile, job_entry)
            try:
                expected_timeout = _job_timeout(
                    source_job, reusable_timeouts=reusable_timeouts
                )
            except CatalogError as exc:
                errors.append(f"{job_location}: {exc}")
                continue
            timeout = effective.get("expected_timeout_minutes")
            if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
                errors.append(f"{job_location}.expected_timeout_minutes is invalid")
            elif "runs-on" in source_job and timeout != expected_timeout:
                errors.append(
                    f"{job_location}: timeout differs from workflow "
                    f"(catalog={timeout}, source={expected_timeout})"
                )
            duration = effective.get("expected_duration_seconds")
            if (
                not isinstance(duration, int)
                or isinstance(duration, bool)
                or duration < 1
            ):
                errors.append(f"{job_location}.expected_duration_seconds is invalid")
            elif isinstance(timeout, int) and duration < timeout * 60:
                errors.append(f"{job_location}: duration must cover timeout budget")
            guard = effective.get("guard")
            expected_job_guard = (
                str(source_job["if"]) if "if" in source_job else "workflow trigger"
            )
            if guard != expected_job_guard:
                errors.append(f"{job_location}.guard is stale")
            expected_name = str(source_job.get("name", job_id))
            if effective.get("check_name_template") != expected_name:
                errors.append(f"{job_location}.check_name_template is stale")
            source_contexts.add(expected_name)
            errors.extend(
                _matrix_governance_errors(source_job, job_entry, job_location)
            )
            try:
                runbook = effective.get("runbook", default_runbook)
                _repo_file(runbook, repository_root, f"{job_location}.runbook")
            except CatalogError as exc:
                errors.append(str(exc))
            retry_policy = effective.get("retry_policy")
            if not isinstance(retry_policy, dict):
                errors.append(f"{job_location}.retry_policy is missing")
            elif _is_retry_candidate(source_job) and retry_policy.get("mode") == "none":
                errors.append(
                    f"{job_location}: retry behavior is present but policy is declared none"
                )
            errors.extend(
                _validate_artifacts(
                    effective, _artifact_inventory(source_job), job_location
                )
            )
            classification = effective.get("classification")
            required_events = effective.get("required_events")
            if classification == "required":
                if not required_events:
                    errors.append(
                        f"{job_location}: required job has no required_events"
                    )
                elif not set(required_events).issubset(POLICY_EVENTS):
                    errors.append(f"{job_location}: unsupported required event alias")
                elif (
                    "pull_request_main" in required_events
                    and "pull_request" not in source_events
                ):
                    errors.append(
                        f"{job_location}: pull_request_main is not a source event"
                    )
                elif "push_main" in required_events and "push" not in source_events:
                    errors.append(f"{job_location}: push_main is not a source event")
            elif required_events:
                errors.append(f"{job_location}: non-required job has required_events")
    if len(catalog_paths) != len(set(catalog_paths)):
        errors.append("catalog contains duplicate workflow paths")
    if set(catalog_paths) != source_paths:
        errors.append(
            "workflow inventory mismatch "
            f"(catalog={sorted(set(catalog_paths))}, source={sorted(source_paths)})"
        )
    external_errors, external_contexts = _validate_external_checks(
        catalog.get("external_checks"),
        profiles=profiles,
        repository_root=repository_root,
        source_contexts=source_contexts,
        used_profiles=used_profiles,
    )
    errors.extend(external_errors)
    errors.extend(
        _validate_expansions(
            catalog.get("expansions"),
            profiles=profiles,
            repository_root=repository_root,
            workflow_directory=workflow_directory,
            source_paths=source_paths,
            source_contexts=source_contexts,
            external_contexts=external_contexts,
            used_profiles=used_profiles,
        )
    )
    unused_profiles = set(profiles) - used_profiles
    if unused_profiles:
        errors.append(f"catalog contains unused profiles: {sorted(unused_profiles)}")
    return errors


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        catalog = _read_json(args.catalog)
        schema = _read_json(args.schema)
        errors = validate_catalog(
            catalog,
            repository_root=args.repository_root.resolve(),
            workflow_directory=args.repository_root.resolve() / ".github" / "workflows",
            schema=schema,
        )
    except CatalogError as exc:
        print(f"CI check catalog: ERROR: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"CI check catalog: ERROR: {error}", file=sys.stderr)
        return 1
    workflow_count = len(catalog["workflows"])
    job_count = sum(len(workflow["jobs"]) for workflow in catalog["workflows"])
    print(f"CI check catalog: OK ({workflow_count} workflows, {job_count} jobs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
