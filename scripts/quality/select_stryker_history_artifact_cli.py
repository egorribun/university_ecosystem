"""Select bounded, provenance-checked Stryker timing *advice* from prior runs.

This does not certify or reuse mutant results. The current mutation/preflight
evidence must still be generated and verified against its exact SHA/run.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
import time
import zipfile
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.quality import download_stryker_cost_artifacts as transport
from scripts.quality.download_stryker_cost_artifacts import RequestTransport

_SHA = re.compile(r"[0-9a-f]{40}$")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH = re.compile(r"[A-Za-z0-9._/-]+$")
_WORKFLOW_PATH = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.(?:yml|yaml)$")
_MAX_RUNS = 50
_MAX_CANDIDATES = 3
_MAX_ARTIFACTS = 400
_MAX_CALLS = 24
_MAX_SECONDS = 30.0
_MAX_AGE = timedelta(days=30)
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_ZIP_BYTES = 64 * 1024 * 1024
_MAX_COST_ENTRIES = 5_000
_MAX_COST_MS = 16_200_000


class InvalidHistory(ValueError):
    """Historical timing advice failed a trust or compatibility boundary."""


@dataclass(frozen=True)
class HistoryArguments:
    repository: str
    current_run_id: int
    current_run_attempt: int
    current_source_sha: str
    event: str
    workflow_path: str
    branch: str


@dataclass(frozen=True)
class HistoricalCandidate:
    run_id: int
    costs: dict[str, float]
    cost_artifact: dict[str, Any]


@dataclass(frozen=True)
class HistorySelection:
    candidate: HistoricalCandidate | None
    diagnostic: str


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _reject_constant(value: str) -> None:
    raise InvalidHistory(f"nonfinite JSON constant {value}")


def _object_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidHistory("duplicate JSON key")
        result[key] = value
    return result


def _json_object(raw: bytes) -> dict[str, Any]:
    if not 0 < len(raw) <= _MAX_JSON_BYTES:
        raise InvalidHistory("JSON payload size is invalid")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_object_no_duplicates,
        )
    except InvalidHistory:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise InvalidHistory("malformed JSON payload") from error
    if not isinstance(parsed, dict):
        raise InvalidHistory("JSON payload must be an object")
    return parsed


def _verified_wrapper(raw: bytes) -> dict[str, Any]:
    artifact = _json_object(raw)
    if tuple(artifact) != ("schemaVersion", "payload", "payloadSha256"):
        raise InvalidHistory("Stryker artifact wrapper shape is invalid")
    payload = artifact["payload"]
    digest = artifact["payloadSha256"]
    if artifact["schemaVersion"] != "1.0" or not isinstance(payload, dict):
        raise InvalidHistory("Stryker artifact schema is unsupported")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise InvalidHistory("Stryker artifact payload digest is malformed")
    # JS signs JSON.stringify(payload, null, 2) + "\n". Python re-encoding is not
    # equivalent for every finite IEEE-754 number (for example, 1e-6), so take
    # the exact payload bytes from the canonical JS wrapper instead.
    prefix = b'{\n  "schemaVersion": "1.0",\n  "payload": '
    suffix = f',\n  "payloadSha256": "{digest}"\n}}\n'.encode("ascii")
    if not raw.startswith(prefix) or not raw.endswith(suffix):
        raise InvalidHistory("Stryker artifact JSON layout is not canonical")
    nested_payload = raw[len(prefix) : -len(suffix)]
    if not nested_payload.startswith(b"{") or not nested_payload.endswith(b"}"):
        raise InvalidHistory("Stryker artifact payload layout is invalid")
    lines = nested_payload.split(b"\n")
    if b"\r" in nested_payload or any(not line.startswith(b"  ") for line in lines[1:]):
        raise InvalidHistory("Stryker artifact payload indentation is invalid")
    signed_payload = b"\n".join([lines[0], *(line[2:] for line in lines[1:])]) + b"\n"
    if hashlib.sha256(signed_payload).hexdigest() != digest:
        raise InvalidHistory("Stryker artifact payload digest mismatch")
    return artifact


def _bounded_request(request: RequestTransport) -> RequestTransport:
    remaining = _MAX_CALLS
    deadline = time.monotonic() + _MAX_SECONDS

    def bounded(item: transport.Request, limit: int) -> transport.HttpResponse:
        nonlocal remaining
        if remaining <= 0 or time.monotonic() >= deadline:
            raise InvalidHistory("historical search budget exhausted")
        remaining -= 1
        try:
            response = request(item, limit)
        except (OSError, ConnectionError, TimeoutError) as error:
            raise InvalidHistory("historical API network request failed") from error
        if time.monotonic() > deadline or not isinstance(response.body, bytes):
            raise InvalidHistory(
                "historical search deadline or transport type violated"
            )
        if len(response.body) > limit:
            raise InvalidHistory("historical response exceeds byte bound")
        return response

    return bounded


def _api_json(url: str, token: str, request: RequestTransport) -> dict[str, Any]:
    response = request(transport._api_request(url, token), 2 * 1024 * 1024)
    if response.status != 200:
        raise InvalidHistory("GitHub API returned a non-success status")
    return _json_object(response.body)


def _identity(run: dict[str, Any], arguments: HistoryArguments, run_id: int) -> None:
    if (
        type(run.get("id")) is not int
        or run["id"] != run_id
        or run.get("event") != arguments.event
        or run.get("path") != arguments.workflow_path
        or run.get("head_branch") != arguments.branch
        or not isinstance(run.get("repository"), dict)
        or run["repository"].get("full_name") != arguments.repository
        or not isinstance(run.get("head_sha"), str)
        or _SHA.fullmatch(run["head_sha"]) is None
        or type(run.get("run_attempt")) is not int
        or run["run_attempt"] < 1
    ):
        raise InvalidHistory("workflow run identity mismatch")


def _age_is_valid(run: dict[str, Any], now: datetime) -> bool:
    created = run.get("created_at")
    if not isinstance(created, str):
        return False
    try:
        parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and now - _MAX_AGE <= parsed <= now


def _artifact_pair(
    records: list[Any], run: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], str]:
    matches: dict[str, dict[str, Any]] = {}
    tested_sha: str | None = None
    for item in records:
        if not isinstance(item, dict):
            raise InvalidHistory("artifact inventory entry is malformed")
        name = item.get("name")
        if not isinstance(name, str):
            raise InvalidHistory("artifact name is malformed")
        if name.startswith("frontend-mutation-historical-costs-"):
            kind = "cost"
        elif name.startswith("frontend-mutation-preflight-"):
            kind = "preflight"
        else:
            continue
        prefix = (
            f"frontend-mutation-{'historical-costs' if kind == 'cost' else 'preflight'}-"
            f"{run['id']}-{run['run_attempt']}-"
        )
        if not name.startswith(prefix):
            # GitHub's run-wide artifact catalog also contains prior attempts.
            continue
        pattern = rf"{re.escape(prefix)}([0-9a-f]{{40}})$"
        name_match = re.fullmatch(pattern, name)
        if name_match is None or kind in matches:
            raise InvalidHistory("duplicate or malformed historical artifact identity")
        sha = name_match.group(1)
        if tested_sha is not None and tested_sha != sha:
            raise InvalidHistory("historical artifact pair has different tested SHAs")
        tested_sha = sha
        if (
            type(item.get("id")) is not int
            or item["id"] <= 0
            or type(item.get("size_in_bytes")) is not int
            or not 0 < item["size_in_bytes"] <= _MAX_ZIP_BYTES
            or item.get("expired") is not False
            or not isinstance(item.get("digest"), str)
            or _DIGEST.fullmatch(item["digest"]) is None
            or not isinstance(item.get("workflow_run"), dict)
            or item["workflow_run"].get("id") != run["id"]
            or item["workflow_run"].get("head_sha") != run["head_sha"]
        ):
            raise InvalidHistory("historical artifact provenance is invalid")
        matches[kind] = item
    if set(matches) != {"cost", "preflight"} or tested_sha is None:
        raise InvalidHistory("historical cost/preflight artifact pair is incomplete")
    return matches["cost"], matches["preflight"], tested_sha


def _one_zip_member(archive_bytes: bytes, expected_name: str) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].filename != expected_name:
                raise InvalidHistory("archive has unexpected members")
            member = members[0]
            member_type = stat.S_IFMT(member.external_attr >> 16)
            if (
                member.is_dir()
                or member.flag_bits & 0x1
                or member_type not in {0, stat.S_IFREG}
                or not 0 < member.file_size <= _MAX_JSON_BYTES
                or member.compress_size <= 0
                or member.file_size > member.compress_size * 100
            ):
                raise InvalidHistory("archive member is unsafe")
            contents = archive.read(member)
    except (
        OSError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        zlib.error,
    ) as error:
        raise InvalidHistory("archive cannot be read safely") from error
    if len(contents) != member.file_size:
        raise InvalidHistory("archive member size mismatch")
    return contents


def _download(
    artifact: dict[str, Any],
    arguments: HistoryArguments,
    token: str,
    request: RequestTransport,
    expected_name: str,
) -> bytes:
    endpoint = f"https://api.github.com/repos/{arguments.repository}/actions/artifacts/{artifact['id']}/zip"
    redirect = request(transport._api_request(endpoint, token), 64 * 1024)
    if redirect.status != 302:
        raise InvalidHistory("artifact API did not return one redirect")
    location = transport._validate_cdn_location(
        transport._header(redirect.headers, "Location")
    )
    response = request(transport._cdn_request(location), _MAX_ZIP_BYTES)
    if response.status != 200:
        raise InvalidHistory("artifact CDN returned non-success")
    if hashlib.sha256(response.body).hexdigest() != artifact["digest"].removeprefix(
        "sha256:"
    ):
        raise InvalidHistory("artifact ZIP digest mismatch")
    return _one_zip_member(response.body, expected_name)


def _compatible_costs(
    current: dict[str, Any],
    historic: dict[str, Any],
    historic_preflight: dict[str, Any],
    run: dict[str, Any],
    tested_sha: str,
) -> dict[str, float]:
    current_payload = current["payload"]
    cost = historic["payload"]
    old_payload = historic_preflight["payload"]
    revision = cost.get("sourceRevision")
    current_revision = current_payload.get("sourceRevision")
    if not isinstance(revision, dict) or not isinstance(current_revision, dict):
        raise InvalidHistory("Stryker source revision is malformed")
    preflight = current_payload.get("preflight")
    if not isinstance(preflight, dict) or not isinstance(preflight.get("files"), dict):
        raise InvalidHistory("current viable source inventory is invalid")
    if (
        revision.get("headSha") != tested_sha
        or revision.get("sourceHeadSha") != run["head_sha"]
        or revision.get("repositoryDirty") is not False
        or current_revision.get("repositoryDirty") is not False
        or revision.get("inputHashes") != current_revision.get("inputHashes")
        or cost.get("config") != current_payload.get("config")
        or cost.get("preflightDigest") != preflight.get("digest")
        or old_payload.get("sourceRevision") != revision
        or old_payload.get("config") != cost.get("config")
        or old_payload.get("toolchain") != current_payload.get("toolchain")
        or old_payload.get("preflight") != current_payload.get("preflight")
    ):
        raise InvalidHistory(
            "historical timing fingerprints differ from current inputs"
        )
    workflow = old_payload.get("workflow")
    if (
        not isinstance(workflow, dict)
        or workflow.get("runId") != str(run["id"])
        or workflow.get("runAttempt") != str(run["run_attempt"])
        or workflow.get("sha") != tested_sha
        or workflow.get("sourceHeadSha") != run["head_sha"]
    ):
        raise InvalidHistory("historical preflight producer identity mismatch")
    if not 0 < len(preflight["files"]) <= _MAX_COST_ENTRIES:
        raise InvalidHistory("current viable source inventory exceeds entry bound")
    for file, entry in preflight["files"].items():
        if (
            not isinstance(file, str)
            or not file.startswith("src/")
            or "\\" in file
            or any(segment in {"", ".", ".."} for segment in file.split("/"))
            or not isinstance(entry, dict)
            or set(entry) != {"sourceSha256", "mutantSignatures"}
            or not isinstance(entry["sourceSha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sourceSha256"]) is None
            or not isinstance(entry["mutantSignatures"], list)
            or any(
                not isinstance(signature, str) or not signature
                for signature in entry["mutantSignatures"]
            )
            or len(set(entry["mutantSignatures"])) != len(entry["mutantSignatures"])
        ):
            raise InvalidHistory("current viable source inventory entry is malformed")
    expected: dict[str, dict[str, Any]] = {
        file: entry
        for file, entry in preflight["files"].items()
        if len(entry["mutantSignatures"]) > 0
    }
    entries = cost.get("costs")
    if not expected or not isinstance(entries, list) or len(entries) != len(expected):
        raise InvalidHistory("historical timing is incomplete")
    costs: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "file",
            "sourceSha256",
            "mutantCount",
            "estimatedDurationMs",
        }:
            raise InvalidHistory("historical cost entry is malformed")
        file = entry["file"]
        source = expected.get(file) if isinstance(file, str) else None
        duration = entry["estimatedDurationMs"]
        if (
            source is None
            or file in costs
            or entry["sourceSha256"] != source.get("sourceSha256")
            or type(entry["mutantCount"]) is not int
            or entry["mutantCount"] != len(source["mutantSignatures"])
            or type(duration) not in {int, float}
            or not math.isfinite(duration)
            or not 0 < duration <= _MAX_COST_MS
        ):
            raise InvalidHistory("historical timing has stale or nonfinite source cost")
        costs[file] = float(duration)
    if set(costs) != set(expected):
        raise InvalidHistory("historical timing omitted a viable source")
    return costs


def select_historical_costs(
    arguments: HistoryArguments,
    current_preflight: bytes | dict[str, Any],
    *,
    token: str,
    request: RequestTransport,
) -> HistorySelection:
    if (
        _REPOSITORY.fullmatch(arguments.repository) is None
        or any(part in {".", ".."} for part in arguments.repository.split("/"))
        or _BRANCH.fullmatch(arguments.branch) is None
        or _WORKFLOW_PATH.fullmatch(arguments.workflow_path) is None
        or _SHA.fullmatch(arguments.current_source_sha) is None
        or type(arguments.current_run_id) is not int
        or arguments.current_run_id < 1
        or type(arguments.current_run_attempt) is not int
        or arguments.current_run_attempt < 1
        or arguments.event != "pull_request"
        or not token
    ):
        raise InvalidHistory("current workflow arguments are invalid")
    current = _validated_current_preflight(arguments, current_preflight)
    bounded = _bounded_request(request)
    api = f"https://api.github.com/repos/{arguments.repository}"
    try:
        current_run = _api_json(
            f"{api}/actions/runs/{arguments.current_run_id}", token, bounded
        )
        _identity(current_run, arguments, arguments.current_run_id)
        if (
            current_run["run_attempt"] != arguments.current_run_attempt
            or current_run["head_sha"] != arguments.current_source_sha
        ):
            raise InvalidHistory("current run metadata does not match preflight")
        listing = _api_json(
            f"{api}/actions/workflows/{arguments.workflow_path.rsplit('/', 1)[-1]}/runs"
            f"?event={arguments.event}&status=completed&per_page={_MAX_RUNS}&page=1",
            token,
            bounded,
        )
    except (InvalidHistory, transport.ArtifactDownloadError) as error:
        return HistorySelection(None, f"baseline planner retained: {error}")
    runs = listing.get("workflow_runs")
    total = listing.get("total_count")
    if (
        not isinstance(runs, list)
        or len(runs) > _MAX_RUNS
        or type(total) is not int
        or total < len(runs)
    ):
        raise InvalidHistory("historical run catalog is malformed")
    now = datetime.now(UTC)
    eligible = [
        run
        for run in runs
        if isinstance(run, dict)
        and run.get("id") != arguments.current_run_id
        and run.get("conclusion") == "success"
        and run.get("head_branch") == arguments.branch
        and _age_is_valid(run, now)
    ][:_MAX_CANDIDATES]
    last_error = "no compatible recent successful Stryker run"
    for run_summary in eligible:
        try:
            run_id = run_summary.get("id")
            if type(run_id) is not int or run_id < 1:
                raise InvalidHistory("historical run id is invalid")
            run = _api_json(f"{api}/actions/runs/{run_id}", token, bounded)
            _identity(run, arguments, run_id)
            stable_fields = (
                "id",
                "head_sha",
                "event",
                "path",
                "head_branch",
                "conclusion",
                "run_attempt",
                "created_at",
                "repository",
            )
            if (
                any(run.get(field) != run_summary.get(field) for field in stable_fields)
                or run.get("conclusion") != "success"
                or not _age_is_valid(run, now)
            ):
                raise InvalidHistory("historical run metadata changed or is stale")
            artifacts: list[Any] = []
            expected_total: int | None = None
            for page in range(1, 6):
                catalog = _api_json(
                    f"{api}/actions/runs/{run_id}/artifacts?per_page=100&page={page}",
                    token,
                    bounded,
                )
                count = catalog.get("total_count")
                records = catalog.get("artifacts")
                if (
                    type(count) is not int
                    or not 0 <= count <= _MAX_ARTIFACTS
                    or not isinstance(records, list)
                    or len(records) > 100
                    or (expected_total is not None and count != expected_total)
                ):
                    raise InvalidHistory("historical artifact catalog is malformed")
                expected_total = count
                artifacts.extend(records)
                if len(artifacts) == count:
                    break
                if not records or len(artifacts) > count:
                    raise InvalidHistory("historical artifact catalog is partial")
            else:
                raise InvalidHistory("historical artifact catalog exceeded page bound")
            cost_record, preflight_record, tested_sha = _artifact_pair(artifacts, run)
            cost = _verified_wrapper(
                _download(
                    cost_record, arguments, token, bounded, "HISTORICAL_COSTS.json"
                )
            )
            preflight = _verified_wrapper(
                _download(
                    preflight_record,
                    arguments,
                    token,
                    bounded,
                    "PREFLIGHT_ARTIFACT.json",
                )
            )
            costs = _compatible_costs(current, cost, preflight, run, tested_sha)
            return HistorySelection(
                HistoricalCandidate(run_id=run_id, costs=costs, cost_artifact=cost),
                "compatible historical Stryker timing advice",
            )
        except (InvalidHistory, transport.ArtifactDownloadError) as error:
            last_error = str(error)
            continue
    return HistorySelection(None, f"baseline planner retained: {last_error}")


def _validated_current_preflight(
    arguments: HistoryArguments, current_preflight: bytes | dict[str, Any]
) -> dict[str, Any]:
    current = _verified_wrapper(
        current_preflight
        if isinstance(current_preflight, bytes)
        else _canonical_json(current_preflight)
    )
    current_workflow = current["payload"].get("workflow")
    current_revision = current["payload"].get("sourceRevision")
    if (
        not isinstance(current_workflow, dict)
        or not isinstance(current_revision, dict)
        or current_workflow.get("runId") != str(arguments.current_run_id)
        or current_workflow.get("runAttempt") != str(arguments.current_run_attempt)
        or current_workflow.get("sourceHeadSha") != arguments.current_source_sha
        or current_revision.get("headSha") != current_workflow.get("sha")
        or current_revision.get("sourceHeadSha") != arguments.current_source_sha
    ):
        raise InvalidHistory("current preflight provenance is invalid")
    return current


def _snapshot_file(
    root: Path, name: str, maximum_bytes: int, expected_digest: str | None = None
) -> bytes:
    target = root / name
    try:
        metadata = target.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 0 < metadata.st_size <= maximum_bytes
        ):
            raise InvalidHistory("historical snapshot member is unsafe")
        raw = target.read_bytes()
    except OSError as error:
        raise InvalidHistory("historical snapshot member cannot be read") from error
    if len(raw) != metadata.st_size:
        raise InvalidHistory("historical snapshot member changed while reading")
    if (
        expected_digest is not None
        and hashlib.sha256(raw).hexdigest() != expected_digest
    ):
        raise InvalidHistory("historical snapshot member differs from trusted download")
    return raw


def select_offline_historical_costs(
    arguments: HistoryArguments,
    current_preflight: bytes | dict[str, Any],
    snapshot_root: Path,
    expected_digests: dict[str, str] | None = None,
) -> HistorySelection:
    """Verify a bounded artifact snapshot fetched by a separate token-bearing step."""

    if (
        _REPOSITORY.fullmatch(arguments.repository) is None
        or any(part in {".", ".."} for part in arguments.repository.split("/"))
        or _BRANCH.fullmatch(arguments.branch) is None
        or _WORKFLOW_PATH.fullmatch(arguments.workflow_path) is None
        or _SHA.fullmatch(arguments.current_source_sha) is None
        or type(arguments.current_run_id) is not int
        or arguments.current_run_id < 1
        or type(arguments.current_run_attempt) is not int
        or arguments.current_run_attempt < 1
        or arguments.event != "pull_request"
    ):
        raise InvalidHistory("current workflow arguments are invalid")
    current = _validated_current_preflight(arguments, current_preflight)
    try:
        root_metadata = snapshot_root.lstat()
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise InvalidHistory("historical snapshot root is unsafe")
        snapshot = _json_object(
            _snapshot_file(
                snapshot_root,
                "metadata.json",
                2 * 1024 * 1024,
                expected_digests["metadata.json"] if expected_digests else None,
            )
        )
        if set(snapshot) != {"run", "artifacts"}:
            raise InvalidHistory("historical snapshot metadata is malformed")
        run = snapshot["run"]
        records = snapshot["artifacts"]
        if not isinstance(run, dict) or not isinstance(records, list):
            raise InvalidHistory("historical snapshot metadata is malformed")
        run_id = run.get("id")
        if type(run_id) is not int or run_id == arguments.current_run_id:
            raise InvalidHistory("historical snapshot run id is invalid")
        _identity(run, arguments, run_id)
        if run.get("conclusion") != "success" or not _age_is_valid(
            run, datetime.now(UTC)
        ):
            raise InvalidHistory("historical snapshot run is not a recent success")
        cost_record, preflight_record, tested_sha = _artifact_pair(records, run)
        cost_zip = _snapshot_file(
            snapshot_root,
            "historical-costs.zip",
            _MAX_ZIP_BYTES,
            expected_digests["historical-costs.zip"] if expected_digests else None,
        )
        preflight_zip = _snapshot_file(
            snapshot_root,
            "preflight.zip",
            _MAX_ZIP_BYTES,
            expected_digests["preflight.zip"] if expected_digests else None,
        )
        if hashlib.sha256(cost_zip).hexdigest() != cost_record["digest"].removeprefix(
            "sha256:"
        ) or hashlib.sha256(preflight_zip).hexdigest() != preflight_record[
            "digest"
        ].removeprefix("sha256:"):
            raise InvalidHistory("historical snapshot archive digest mismatch")
        cost = _verified_wrapper(_one_zip_member(cost_zip, "HISTORICAL_COSTS.json"))
        preflight = _verified_wrapper(
            _one_zip_member(preflight_zip, "PREFLIGHT_ARTIFACT.json")
        )
        costs = _compatible_costs(current, cost, preflight, run, tested_sha)
        return HistorySelection(
            HistoricalCandidate(run_id=run_id, costs=costs, cost_artifact=cost),
            "compatible historical Stryker timing advice",
        )
    except (InvalidHistory, OSError) as error:
        return HistorySelection(None, f"baseline planner retained: {error}")


def select_offline_historical_candidates(
    arguments: HistoryArguments,
    current_preflight: bytes | dict[str, Any],
    snapshot_root: Path,
    manifest_digest: str,
) -> HistorySelection:
    """Try at most three immutable snapshots bound by a pre-checkout digest."""

    try:
        if re.fullmatch(r"[0-9a-f]{64}", manifest_digest) is None:
            raise InvalidHistory("trusted historical candidate digest is required")
        root_metadata = snapshot_root.lstat()
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise InvalidHistory("historical candidate root is unsafe")
        manifest = _json_object(
            _snapshot_file(
                snapshot_root,
                "candidates.json",
                2 * 1024 * 1024,
                manifest_digest,
            )
        )
        if (
            set(manifest) != {"schemaVersion", "candidates"}
            or manifest["schemaVersion"] != "1.0"
        ):
            raise InvalidHistory("historical candidate manifest is malformed")
        entries = manifest["candidates"]
        if not isinstance(entries, list) or not 0 < len(entries) <= _MAX_CANDIDATES:
            raise InvalidHistory("historical candidate count is invalid")
        required_names = {"metadata.json", "historical-costs.zip", "preflight.zip"}
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or set(entry) != {"directory", "digests"}:
                raise InvalidHistory("historical candidate entry is malformed")
            digests = entry["digests"]
            if (
                entry["directory"] != f"candidate-{index}"
                or not isinstance(digests, dict)
                or set(digests) != required_names
                or any(
                    not isinstance(value, str)
                    or re.fullmatch(r"[0-9a-f]{64}", value) is None
                    for value in digests.values()
                )
            ):
                raise InvalidHistory("historical candidate digest entry is malformed")
        last_error = "no compatible recent successful Stryker run"
        for entry in entries:
            candidate_root = snapshot_root / entry["directory"]
            candidate_metadata = candidate_root.lstat()
            if not stat.S_ISDIR(candidate_metadata.st_mode):
                raise InvalidHistory("historical candidate directory is unsafe")
            # Every considered candidate is bound to the pre-checkout manifest.
            # A changed local file is not an incompatible sample to skip.
            for name, digest in entry["digests"].items():
                _snapshot_file(
                    candidate_root,
                    name,
                    _MAX_ZIP_BYTES if name.endswith(".zip") else 2 * 1024 * 1024,
                    digest,
                )
            selection = select_offline_historical_costs(
                arguments,
                current_preflight,
                candidate_root,
                entry["digests"],
            )
            if selection.candidate is not None:
                return selection
            last_error = selection.diagnostic.removeprefix(
                "baseline planner retained: "
            )
        return HistorySelection(None, f"baseline planner retained: {last_error}")
    except (InvalidHistory, OSError) as error:
        return HistorySelection(None, f"baseline planner retained: {error}")


def _read_current_preflight(path: Path) -> bytes:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise InvalidHistory("current preflight must be an unlinked regular file")
        with path.open("rb") as stream:
            raw = stream.read(_MAX_JSON_BYTES + 1)
    except OSError as error:
        raise InvalidHistory("current preflight cannot be read") from error
    _verified_wrapper(raw)
    return raw


def main(
    argv: list[str] | None = None,
    *,
    token: str | None = None,
    request: RequestTransport = transport._default_request,
) -> int:
    """Print advisory selection; no mutation or preflight evidence is imported."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--current-run-id", type=int, required=True)
    parser.add_argument("--current-run-attempt", type=int, required=True)
    parser.add_argument("--current-source-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--current-preflight", type=Path, required=True)
    parser.add_argument("--offline-snapshot", type=Path)
    parser.add_argument("--snapshot-metadata-sha256")
    parser.add_argument("--snapshot-cost-sha256")
    parser.add_argument("--snapshot-preflight-sha256")
    parser.add_argument("--snapshot-candidates-sha256")
    parser.add_argument("--output-receipt", type=Path)
    parser.add_argument("--github-output", type=Path)
    options = parser.parse_args(argv)
    arguments = HistoryArguments(
        repository=options.repository,
        current_run_id=options.current_run_id,
        current_run_attempt=options.current_run_attempt,
        current_source_sha=options.current_source_sha,
        event=options.event,
        workflow_path=options.workflow_path,
        branch=options.branch,
    )
    try:
        current = _read_current_preflight(options.current_preflight)
        if options.offline_snapshot is not None:
            if options.snapshot_candidates_sha256 is not None:
                selection = select_offline_historical_candidates(
                    arguments,
                    current,
                    options.offline_snapshot,
                    options.snapshot_candidates_sha256,
                )
            else:
                digests = {
                    "metadata.json": options.snapshot_metadata_sha256,
                    "historical-costs.zip": options.snapshot_cost_sha256,
                    "preflight.zip": options.snapshot_preflight_sha256,
                }
                if any(
                    not isinstance(value, str)
                    or re.fullmatch(r"[0-9a-f]{64}", value) is None
                    for value in digests.values()
                ):
                    raise InvalidHistory(
                        "trusted historical snapshot digests are required"
                    )
                selection = select_offline_historical_costs(
                    arguments, current, options.offline_snapshot, digests
                )
        else:
            selection = select_historical_costs(
                arguments,
                current,
                token=token or os.environ.get("GH_TOKEN", ""),
                request=request,
            )
    except (InvalidHistory, transport.ArtifactDownloadError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    candidate = selection.candidate
    receipt = {
        "has_candidate": candidate is not None,
        "candidate_run_id": candidate.run_id if candidate is not None else None,
        "costs": candidate.costs if candidate is not None else None,
        "diagnostic": selection.diagnostic,
    }
    rendered = json.dumps(receipt, sort_keys=True)
    if options.output_receipt is not None and candidate is not None:
        try:
            with options.output_receipt.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
        except OSError as error:
            print(
                f"error: cannot write verified timing receipt: {error}", file=sys.stderr
            )
            return 1
    if options.github_output is not None:
        try:
            with options.github_output.open("a", encoding="utf-8") as stream:
                stream.write(
                    f"has_candidate={'true' if candidate is not None else 'false'}\n"
                )
        except OSError as error:
            print(f"error: cannot write workflow output: {error}", file=sys.stderr)
            return 1
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
