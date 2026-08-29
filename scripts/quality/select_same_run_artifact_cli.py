"""Select one provenance-bound same-run GitHub Actions artifact.

The command intentionally queries only GitHub's current-run metadata and that
run's artifact catalog.  It never downloads or extracts an artifact archive;
the caller can pass the selected server-issued artifact id to a pinned action.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from typing import TypeIs, cast

_ARTIFACT_PAGE_SIZE = 100
_MAX_ARTIFACTS = 10_000
_MAX_CATALOG_SNAPSHOT_ATTEMPTS = 3
_MAX_METADATA_BYTES = 2 * 1024 * 1024
_DECIMAL = re.compile(r"[1-9][0-9]*$")
_SHA = re.compile(r"[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PREFIX = re.compile(r"[a-z0-9][a-z0-9._-]*-$")
_SUFFIX = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*$")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}$")
_API_TARGET = re.compile(
    r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[1-9][0-9]*"
    r"(?:/artifacts\?per_page=100&page=[1-9][0-9]*)?$"
)


class SameRunArtifactError(ValueError):
    """Raised when current-run artifact selection cannot be trusted."""


class _CatalogChanged(RuntimeError):
    """Signals a concurrent catalog update that requires a bounded retry."""


@dataclass(frozen=True)
class SelectionArguments:
    """Trusted identity fields and the artifact naming contract."""

    repository: str
    run_id: str
    consumer_run_attempt: str
    commit_sha: str
    event: str
    workflow_path: str
    artifact_prefix: str
    artifact_suffix: str
    attempt_policy: str
    allow_empty: bool
    artifact_name_layout: str = "run-id-attempt"


@dataclass(frozen=True)
class HttpResponse:
    """A bounded REST response supplied by the injectable transport."""

    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class Request:
    """One GitHub REST request; the path is always relative to api.github.com."""

    path: str
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionResult:
    """The compact, server-issued artifact identity exported to Actions."""

    has_candidate: bool
    artifact_id: int | None
    artifact_name: str | None
    producer_attempt: int | None


RequestTransport = Callable[[Request, int], HttpResponse]


def _is_int(value: object) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise SameRunArtifactError(f"{field} must be a non-empty string")
    if any(character in value for character in "\x00\r\n"):
        raise SameRunArtifactError(f"{field} contains a forbidden control character")
    return value


def _require_decimal(value: object, field: str) -> int:
    text = _require_text(value, field)
    if _DECIMAL.fullmatch(text) is None:
        raise SameRunArtifactError(f"{field} must be a positive decimal")
    return int(text)


def _read_limited(stream: object, maximum_bytes: int) -> bytes:
    if not _is_int(maximum_bytes) or maximum_bytes < 1:
        raise SameRunArtifactError("response limit is invalid")
    read = getattr(stream, "read", None)
    if not callable(read):
        raise SameRunArtifactError("GitHub REST response is malformed")
    body = read(maximum_bytes + 1)
    if not isinstance(body, bytes) or len(body) > maximum_bytes:
        raise SameRunArtifactError("GitHub REST response exceeds its maximum size")
    return body


def _default_request(request: Request, maximum_bytes: int) -> HttpResponse:
    """Perform one bounded request to the fixed GitHub REST API origin."""

    if _API_TARGET.fullmatch(request.path) is None:
        raise SameRunArtifactError("GitHub REST path is not an allowed current-run endpoint")
    connection = HTTPSConnection("api.github.com", port=443, timeout=20)
    try:
        connection.request("GET", request.path, headers=dict(request.headers))
        response = connection.getresponse()
        status = response.status
        if not _is_int(status):
            raise SameRunArtifactError("GitHub REST response has an invalid status")
        headers = dict(response.getheaders())
        return HttpResponse(status, headers, _read_limited(response, maximum_bytes))
    except SameRunArtifactError:
        raise
    except (OSError, HTTPException) as error:
        raise SameRunArtifactError("GitHub REST request failed") from error
    finally:
        connection.close()


def _validate_arguments(arguments: SelectionArguments) -> None:
    if _REPOSITORY.fullmatch(_require_text(arguments.repository, "repository")) is None:
        raise SameRunArtifactError("repository must be an owner/name identifier")
    _require_decimal(arguments.run_id, "run_id")
    _require_decimal(arguments.consumer_run_attempt, "consumer_run_attempt")
    if _SHA.fullmatch(_require_text(arguments.commit_sha, "commit_sha")) is None:
        raise SameRunArtifactError("commit_sha must be a lowercase full SHA")
    _require_text(arguments.event, "event")
    workflow_path = _require_text(arguments.workflow_path, "workflow_path")
    if not workflow_path.startswith(".github/workflows/"):
        raise SameRunArtifactError("workflow_path must identify a repository workflow")
    if _PREFIX.fullmatch(_require_text(arguments.artifact_prefix, "artifact_prefix")) is None:
        raise SameRunArtifactError("artifact_prefix must be a safe portable prefix")
    suffix = arguments.artifact_suffix
    if not isinstance(suffix, str) or any(character in suffix for character in "\x00\r\n"):
        raise SameRunArtifactError("artifact_suffix contains a forbidden control character")
    if suffix and _SUFFIX.fullmatch(suffix) is None:
        raise SameRunArtifactError("artifact_suffix must be a safe portable suffix")
    if arguments.artifact_name_layout not in {"run-id-attempt", "attempt"}:
        raise SameRunArtifactError("artifact_name_layout is invalid")
    if arguments.attempt_policy not in {"earlier", "current-or-earlier"}:
        raise SameRunArtifactError("attempt_policy is invalid")
    if not isinstance(arguments.allow_empty, bool):
        raise SameRunArtifactError("allow_empty must be a boolean")


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SameRunArtifactError("GitHub API JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise SameRunArtifactError(f"GitHub API JSON contains invalid constant {value}")


def _request_json(
    path: str, token: str, request: RequestTransport
) -> Mapping[str, object]:
    response = request(
        Request(
            path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        ),
        _MAX_METADATA_BYTES,
    )
    if response.status != 200:
        raise SameRunArtifactError("GitHub API returned an unexpected status")
    try:
        value = json.loads(
            response.body.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except SameRunArtifactError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SameRunArtifactError("GitHub API returned malformed JSON") from error
    if not isinstance(value, Mapping):
        raise SameRunArtifactError("GitHub API JSON must be an object")
    return cast(Mapping[str, object], value)


def _required(mapping: Mapping[str, object], field: str) -> object:
    try:
        return mapping[field]
    except KeyError as error:
        raise SameRunArtifactError(f"GitHub API JSON is missing {field}") from error


def _validate_current_run(
    metadata: Mapping[str, object], arguments: SelectionArguments
) -> None:
    if (
        not _is_int(_required(metadata, "id"))
        or _required(metadata, "id") != _require_decimal(arguments.run_id, "run_id")
    ):
        raise SameRunArtifactError("workflow run id does not match the current run")
    if _required(metadata, "head_sha") != arguments.commit_sha:
        raise SameRunArtifactError("workflow run SHA does not match the current commit")
    if _required(metadata, "event") != arguments.event:
        raise SameRunArtifactError("workflow run event does not match the current event")
    if _required(metadata, "path") != arguments.workflow_path:
        raise SameRunArtifactError("workflow run path does not match the trusted workflow")
    if (
        not _is_int(_required(metadata, "run_attempt"))
        or _required(metadata, "run_attempt")
        != _require_decimal(arguments.consumer_run_attempt, "consumer_run_attempt")
    ):
        raise SameRunArtifactError("workflow run attempt does not match the current attempt")
    repository = _required(metadata, "repository")
    if not isinstance(repository, Mapping) or repository.get("full_name") != arguments.repository:
        raise SameRunArtifactError("workflow run repository does not match the current repository")


def _candidate_from_artifact(
    artifact: Mapping[str, object], arguments: SelectionArguments
) -> tuple[int, str, int] | None:
    name = _require_text(_required(artifact, "name"), "artifact.name")
    if not name.startswith(arguments.artifact_prefix):
        return None
    suffix = (
        rf"-{re.escape(arguments.artifact_suffix)}"
        if arguments.artifact_suffix
        else ""
    )
    if arguments.artifact_name_layout == "run-id-attempt":
        pattern = re.compile(
            rf"{re.escape(arguments.artifact_prefix)}{re.escape(arguments.run_id)}-"
            rf"([1-9][0-9]*){suffix}$"
        )
    else:
        pattern = re.compile(
            rf"{re.escape(arguments.artifact_prefix)}([1-9][0-9]*){suffix}$"
        )
    match = pattern.fullmatch(name)
    if match is None:
        raise SameRunArtifactError("artifact has foreign or malformed provenance")
    artifact_id = _required(artifact, "id")
    if not _is_int(artifact_id) or artifact_id <= 0:
        raise SameRunArtifactError("artifact id is invalid")
    if not _is_int(_required(artifact, "size_in_bytes")) or _required(
        artifact, "size_in_bytes"
    ) <= 0:
        raise SameRunArtifactError("artifact size is invalid")
    expired = _required(artifact, "expired")
    if not isinstance(expired, bool) or expired:
        raise SameRunArtifactError("artifact is expired or malformed")
    if _DIGEST.fullmatch(_require_text(_required(artifact, "digest"), "artifact.digest")) is None:
        raise SameRunArtifactError("artifact digest is invalid")
    workflow_run = _required(artifact, "workflow_run")
    if not isinstance(workflow_run, Mapping):
        raise SameRunArtifactError("artifact workflow_run is malformed")
    workflow_run_id = workflow_run.get("id")
    if (
        not _is_int(workflow_run_id)
        or workflow_run_id != _require_decimal(arguments.run_id, "run_id")
    ):
        raise SameRunArtifactError("artifact belongs to a foreign workflow run")
    if workflow_run.get("head_sha") != arguments.commit_sha:
        raise SameRunArtifactError("artifact belongs to a foreign commit")
    attempt = int(match.group(1))
    consumer_attempt = _require_decimal(
        arguments.consumer_run_attempt, "consumer_run_attempt"
    )
    if attempt > consumer_attempt:
        raise SameRunArtifactError("artifact producer attempt is from the future")
    if arguments.attempt_policy == "earlier" and attempt == consumer_attempt:
        return None
    return artifact_id, name, attempt


def _select_candidate(
    artifacts: Sequence[Mapping[str, object]], arguments: SelectionArguments
) -> SelectionResult | None:
    candidates: dict[int, tuple[int, str]] = {}
    artifact_ids: set[int] = set()
    for artifact in artifacts:
        candidate = _candidate_from_artifact(artifact, arguments)
        if candidate is None:
            continue
        artifact_id, artifact_name, producer_attempt = candidate
        if producer_attempt in candidates or artifact_id in artifact_ids:
            raise SameRunArtifactError("artifact candidates are duplicated")
        candidates[producer_attempt] = (artifact_id, artifact_name)
        artifact_ids.add(artifact_id)
    if not candidates:
        return None
    producer_attempt = max(candidates)
    artifact_id, artifact_name = candidates[producer_attempt]
    return SelectionResult(True, artifact_id, artifact_name, producer_attempt)


def _list_artifact_snapshot(
    arguments: SelectionArguments, token: str, request: RequestTransport
) -> list[Mapping[str, object]]:
    run_path = f"/repos/{arguments.repository}/actions/runs/{arguments.run_id}"
    expected_total: int | None = None
    artifacts: list[Mapping[str, object]] = []
    for page in range(1, (_MAX_ARTIFACTS // _ARTIFACT_PAGE_SIZE) + 2):
        data = _request_json(
            f"{run_path}/artifacts?per_page={_ARTIFACT_PAGE_SIZE}&page={page}",
            token,
            request,
        )
        total = _required(data, "total_count")
        page_artifacts = _required(data, "artifacts")
        if (
            not _is_int(total)
            or total < 0
            or total > _MAX_ARTIFACTS
            or not isinstance(page_artifacts, list)
        ):
            raise SameRunArtifactError("artifact listing is malformed")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise _CatalogChanged
        if len(artifacts) + len(page_artifacts) > total:
            raise _CatalogChanged
        for artifact in page_artifacts:
            if not isinstance(artifact, Mapping):
                raise SameRunArtifactError(
                    "artifact listing contains a malformed artifact"
                )
            artifacts.append(cast(Mapping[str, object], artifact))
        if len(artifacts) == total:
            return artifacts
        if not page_artifacts:
            raise _CatalogChanged
    raise _CatalogChanged


def _list_artifacts(
    arguments: SelectionArguments, token: str, request: RequestTransport
) -> list[Mapping[str, object]]:
    """Read a complete same-run catalog, retrying only a detected concurrent race."""

    for _ in range(_MAX_CATALOG_SNAPSHOT_ATTEMPTS):
        try:
            return _list_artifact_snapshot(arguments, token, request)
        except _CatalogChanged:
            continue
    raise SameRunArtifactError("artifact catalog did not converge to a complete snapshot")


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _normal_path_text(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _safe_output_parent(path: Path) -> Path:
    lexical_parent = Path(os.path.abspath(path.parent))
    if _is_link_or_junction(lexical_parent):
        raise SameRunArtifactError("GITHUB_OUTPUT parent must not be a link")
    try:
        resolved_parent = lexical_parent.resolve(strict=True)
    except OSError as error:
        raise SameRunArtifactError(
            "GITHUB_OUTPUT parent must be an available regular directory"
        ) from error
    if _normal_path_text(lexical_parent) != _normal_path_text(resolved_parent):
        raise SameRunArtifactError("GITHUB_OUTPUT parent must not traverse a link")
    if not resolved_parent.is_dir():
        raise SameRunArtifactError("GITHUB_OUTPUT parent must be a regular directory")
    return lexical_parent


def _safe_output_file(path: Path) -> os.stat_result:
    if _is_link_or_junction(path):
        raise SameRunArtifactError("GITHUB_OUTPUT must not be a link")
    try:
        metadata = path.lstat()
    except OSError as error:
        raise SameRunArtifactError("GITHUB_OUTPUT must be an existing regular file") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise SameRunArtifactError("GITHUB_OUTPUT must be a regular file")
    if metadata.st_nlink != 1:
        raise SameRunArtifactError("GITHUB_OUTPUT must not be a hard link")
    return metadata


def _same_file_identity(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
    )


def _append_output(path: Path, result: SelectionResult) -> None:
    parent = _safe_output_parent(path)
    before = _safe_output_file(path)
    try:
        previous = path.read_bytes()
    except OSError as error:
        raise SameRunArtifactError("GITHUB_OUTPUT cannot be read") from error
    after = _safe_output_file(path)
    if not _same_file_identity(before, after):
        raise SameRunArtifactError("GITHUB_OUTPUT changed while it was read")
    if previous and not previous.endswith(b"\n"):
        raise SameRunArtifactError("GITHUB_OUTPUT has an incomplete prior record")
    values = (
        f"has_candidate={'true' if result.has_candidate else 'false'}\n"
        f"artifact_id={result.artifact_id if result.artifact_id is not None else ''}\n"
        f"artifact_name={result.artifact_name or ''}\n"
        f"producer_attempt={result.producer_attempt if result.producer_attempt is not None else ''}\n"
    ).encode("utf-8")
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".same-run-output-", dir=parent
        )
    except OSError as error:
        raise SameRunArtifactError("GITHUB_OUTPUT cannot be prepared atomically") from error
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(previous + values)
            stream.flush()
            os.fsync(stream.fileno())
        if not _same_file_identity(after, _safe_output_file(path)):
            raise SameRunArtifactError("GITHUB_OUTPUT changed before replacement")
        os.replace(temporary, path)
    except OSError as error:
        raise SameRunArtifactError("GITHUB_OUTPUT cannot be written atomically") from error
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError as error:
                raise SameRunArtifactError("GITHUB_OUTPUT temporary cleanup failed") from error


def select_same_run_artifact(
    arguments: SelectionArguments,
    *,
    token: str,
    github_output: Path,
    request: RequestTransport,
) -> SelectionResult:
    """Validate current-run metadata, select one artifact, and emit outputs."""

    _validate_arguments(arguments)
    _require_text(token, "GH_TOKEN")
    run_path = f"/repos/{arguments.repository}/actions/runs/{arguments.run_id}"
    _validate_current_run(_request_json(run_path, token, request), arguments)
    candidate = _select_candidate(_list_artifacts(arguments, token, request), arguments)
    if candidate is None:
        if not arguments.allow_empty:
            raise SameRunArtifactError("no valid same-run artifact candidate exists")
        candidate = SelectionResult(False, None, None, None)
    _append_output(github_output, candidate)
    return candidate


def parse_arguments(argv: Sequence[str] | None = None) -> SelectionArguments:
    """Parse trusted workflow identity; credentials remain environment-only."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--consumer-run-attempt", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument("--artifact-suffix", required=True)
    parser.add_argument(
        "--artifact-name-layout",
        choices=("run-id-attempt", "attempt"),
        default="run-id-attempt",
    )
    parser.add_argument(
        "--attempt-policy", choices=("earlier", "current-or-earlier"), required=True
    )
    parser.add_argument("--allow-empty", action="store_true")
    namespace = parser.parse_args(argv)
    return SelectionArguments(
        repository=namespace.repository,
        run_id=namespace.run_id,
        consumer_run_attempt=namespace.consumer_run_attempt,
        commit_sha=namespace.commit_sha,
        event=namespace.event,
        workflow_path=namespace.workflow_path,
        artifact_prefix=namespace.artifact_prefix,
        artifact_suffix=namespace.artifact_suffix,
        attempt_policy=namespace.attempt_policy,
        allow_empty=namespace.allow_empty,
        artifact_name_layout=namespace.artifact_name_layout,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selector with credentials and output location from GitHub Actions."""

    try:
        arguments = parse_arguments(argv)
        github_output = Path(_require_text(os.environ.get("GITHUB_OUTPUT", ""), "GITHUB_OUTPUT"))
        select_same_run_artifact(
            arguments,
            token=_require_text(os.environ.get("GH_TOKEN", ""), "GH_TOKEN"),
            github_output=github_output,
            request=_default_request,
        )
    except SameRunArtifactError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
