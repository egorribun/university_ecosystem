"""Download one provenance-bound historical Stryker cost artifact safely.

The GitHub artifact action cannot express all of the trust-boundary checks this
repository needs: it may select a similarly named artifact from a different
attempt and it follows the signed CDN redirect implicitly.  This helper lists
only the current workflow run through the GitHub REST API, validates immutable
run metadata, then materialises exactly one earlier-attempt cost file.

It is deliberately self-contained and uses only the standard library so the
workflow can run it before any project dependencies are installed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import ssl
import stat
import sys
import tempfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from typing import Any, TypeIs, cast
from urllib.parse import urlsplit

_API_ROOT = "https://api.github.com"
_ARTIFACT_PAGE_SIZE = 100
_MAX_ARTIFACTS = 10_000
_MAX_METADATA_BYTES = 2 * 1024 * 1024
_MAX_REDIRECT_BYTES = 64 * 1024
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_MEMBER_BYTES = 16 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_HISTORICAL_COSTS_NAME = "HISTORICAL_COSTS.json"
_DECIMAL = re.compile(r"[1-9][0-9]*$")
_SHA = re.compile(r"[0-9a-f]{40}$")
_DIGEST = re.compile(r"sha256:([0-9a-f]{64})$")
_PREFIX = re.compile(r"[a-z0-9][a-z0-9._-]*-$")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TRUSTED_CDN_SUFFIXES = (
    ".actions.githubusercontent.com",
    ".blob.core.windows.net",
)


class ArtifactDownloadError(ValueError):
    """Raised when a cost artifact or its provenance is unsafe."""


@dataclass(frozen=True)
class DownloadArguments:
    """Immutable identity and output locations supplied by the workflow."""

    repository: str
    run_id: str
    consumer_run_attempt: str
    commit_sha: str
    event: str
    workflow_path: str
    artifact_prefix: str
    output_root: Path
    github_output: Path


@dataclass(frozen=True)
class HttpResponse:
    """A bounded HTTP response returned by the injectable transport."""

    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class Request:
    """One validated HTTPS GET request for the injectable transport boundary."""

    full_url: str
    headers: Mapping[str, str] = field(default_factory=dict)

    def header_items(self) -> list[tuple[str, str]]:
        return list(self.headers.items())


@dataclass(frozen=True)
class DownloadResult:
    """The optional materialised artifact path reported to GitHub Actions."""

    has_candidate: bool
    artifact: str | None


@dataclass(frozen=True)
class _Candidate:
    artifact_id: int
    artifact_name: str
    producer_attempt: int
    digest: str
    size_in_bytes: int


RequestTransport = Callable[[Request, int], HttpResponse]


def _is_int(value: object) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ArtifactDownloadError(f"{field} must be a non-empty string")
    if any(character in value for character in "\x00\r\n"):
        raise ArtifactDownloadError(f"{field} contains a forbidden control character")
    return value


def _require_decimal(value: object, field: str) -> int:
    text = _require_text(value, field)
    if _DECIMAL.fullmatch(text) is None:
        raise ArtifactDownloadError(f"{field} must be a positive decimal")
    return int(text)


def _validate_arguments(arguments: DownloadArguments) -> None:
    repository = _require_text(arguments.repository, "repository")
    if _REPOSITORY.fullmatch(repository) is None:
        raise ArtifactDownloadError("repository must be an owner/name identifier")
    _require_decimal(arguments.run_id, "run_id")
    _require_decimal(arguments.consumer_run_attempt, "consumer_run_attempt")
    commit_sha = _require_text(arguments.commit_sha, "commit_sha")
    if _SHA.fullmatch(commit_sha) is None:
        raise ArtifactDownloadError("commit_sha must be a lowercase full SHA")
    _require_text(arguments.event, "event")
    workflow_path = _require_text(arguments.workflow_path, "workflow_path")
    if not workflow_path.startswith(".github/workflows/"):
        raise ArtifactDownloadError("workflow_path must identify a repository workflow")
    prefix = _require_text(arguments.artifact_prefix, "artifact_prefix")
    if _PREFIX.fullmatch(prefix) is None:
        raise ArtifactDownloadError("artifact_prefix must be a safe portable prefix")
    _safe_relative_directory(arguments.output_root)


def _safe_relative_directory(path: Path) -> tuple[str, ...]:
    if not str(path) or path.is_absolute() or path.drive:
        raise ArtifactDownloadError(
            "output_root must be a non-empty relative directory"
        )
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArtifactDownloadError(
            "output_root must be a non-empty relative directory"
        )
    if any("\x00" in part for part in parts):
        raise ArtifactDownloadError(
            "output_root contains a forbidden control character"
        )
    return parts


def _read_limited(stream: Any, maximum_bytes: int) -> bytes:
    body = stream.read(maximum_bytes + 1)
    if not isinstance(body, bytes) or len(body) > maximum_bytes:
        raise ArtifactDownloadError("remote response exceeds its maximum size")
    return body


def _default_request(request: Request, maximum_bytes: int) -> HttpResponse:
    """Perform exactly one request and surface redirects without following them."""

    try:
        parsed = urlsplit(request.full_url)
        port = parsed.port
    except ValueError as error:
        raise ArtifactDownloadError("request URL is malformed") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise ArtifactDownloadError("request URL must be direct HTTPS")
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    # Build an explicit system-trust context instead of relying on the
    # constructor's implicit defaults.  This keeps certificate and hostname
    # verification fail-closed at the transport boundary and makes the
    # security contract visible to static analysis and reviewers.  The
    # redirect policy is separately restricted to trusted HTTPS CDN hosts and
    # covered by the transport tests below.
    tls_context = ssl.create_default_context()
    # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected -- explicit verified TLS context; redirect policy is host allowlisted and covered by tests
    connection = HTTPSConnection(
        parsed.hostname,
        port=port or 443,
        timeout=20,
        context=tls_context,
    )
    try:
        connection.request("GET", target, headers=dict(request.headers))
        response = connection.getresponse()
        return HttpResponse(
            status=response.status,
            headers=dict(response.getheaders()),
            body=_read_limited(response, maximum_bytes),
        )
    except (OSError, HTTPException) as error:
        raise ArtifactDownloadError("network request failed") from error
    finally:
        connection.close()


def _api_request(url: str, token: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _cdn_request(url: str) -> Request:
    return Request(url, headers={"Accept": "application/zip"})


def _request_json(
    url: str, token: str, request: RequestTransport
) -> Mapping[str, object]:
    response = request(_api_request(url, token), _MAX_METADATA_BYTES)
    if response.status != 200:
        raise ArtifactDownloadError("GitHub API returned an unexpected status")
    try:
        value = json.loads(
            response.body.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactDownloadError("GitHub API returned malformed JSON") from error
    if not isinstance(value, Mapping):
        raise ArtifactDownloadError("GitHub API JSON must be an object")
    return cast(Mapping[str, object], value)


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactDownloadError("GitHub API JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ArtifactDownloadError(f"GitHub API JSON contains invalid constant {value}")


def _required(mapping: Mapping[str, object], field: str) -> object:
    try:
        return mapping[field]
    except KeyError as error:
        raise ArtifactDownloadError(f"GitHub API JSON is missing {field}") from error


def _validate_current_run(
    metadata: Mapping[str, object], arguments: DownloadArguments
) -> None:
    expected_run_id = _require_decimal(arguments.run_id, "run_id")
    expected_attempt = _require_decimal(
        arguments.consumer_run_attempt, "consumer_run_attempt"
    )
    actual_run_id = _required(metadata, "id")
    if not _is_int(actual_run_id) or actual_run_id != expected_run_id:
        raise ArtifactDownloadError("workflow run id does not match the current run")
    if _required(metadata, "head_sha") != arguments.commit_sha:
        raise ArtifactDownloadError(
            "workflow run SHA does not match the current commit"
        )
    if _required(metadata, "event") != arguments.event:
        raise ArtifactDownloadError(
            "workflow run event does not match the current event"
        )
    if _required(metadata, "path") != arguments.workflow_path:
        raise ArtifactDownloadError(
            "workflow run path does not match the trusted workflow"
        )
    actual_attempt = _required(metadata, "run_attempt")
    if not _is_int(actual_attempt) or actual_attempt != expected_attempt:
        raise ArtifactDownloadError(
            "workflow run attempt does not match the current attempt"
        )
    repository = _required(metadata, "repository")
    if (
        not isinstance(repository, Mapping)
        or repository.get("full_name") != arguments.repository
    ):
        raise ArtifactDownloadError(
            "workflow run repository does not match the current repository"
        )


def _list_artifacts(
    arguments: DownloadArguments, token: str, request: RequestTransport
) -> list[Mapping[str, object]]:
    run_url = (
        f"{_API_ROOT}/repos/{arguments.repository}/actions/runs/{arguments.run_id}"
    )
    expected_total: int | None = None
    artifacts: list[Mapping[str, object]] = []
    for page in range(1, (_MAX_ARTIFACTS // _ARTIFACT_PAGE_SIZE) + 2):
        page_data = _request_json(
            f"{run_url}/artifacts?per_page={_ARTIFACT_PAGE_SIZE}&page={page}",
            token,
            request,
        )
        total = _required(page_data, "total_count")
        page_artifacts = _required(page_data, "artifacts")
        if not _is_int(total) or total < 0 or total > _MAX_ARTIFACTS:
            raise ArtifactDownloadError("artifact total_count is invalid")
        if not isinstance(page_artifacts, list):
            raise ArtifactDownloadError(
                "artifact listing must contain an artifact list"
            )
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise ArtifactDownloadError(
                "artifact listing total_count changed during pagination"
            )
        if len(artifacts) + len(page_artifacts) > total:
            raise ArtifactDownloadError(
                "artifact listing exceeds its reported total_count"
            )
        for artifact in page_artifacts:
            if not isinstance(artifact, Mapping):
                raise ArtifactDownloadError(
                    "artifact listing contains a malformed artifact"
                )
            artifacts.append(cast(Mapping[str, object], artifact))
        if len(artifacts) == total:
            return artifacts
        if not page_artifacts:
            raise ArtifactDownloadError(
                "artifact listing ended before its reported total_count"
            )
    raise ArtifactDownloadError("artifact listing exceeds its maximum page count")


def _candidate_from_artifact(
    artifact: Mapping[str, object], arguments: DownloadArguments
) -> _Candidate | None:
    name = _require_text(_required(artifact, "name"), "artifact.name")
    if not name.startswith(arguments.artifact_prefix):
        return None
    pattern = re.compile(
        rf"{re.escape(arguments.artifact_prefix)}{re.escape(arguments.run_id)}-"
        rf"([1-9][0-9]*)-{re.escape(arguments.commit_sha)}$"
    )
    match = pattern.fullmatch(name)
    if match is None:
        raise ArtifactDownloadError("cost artifact has foreign or malformed provenance")
    artifact_id = _required(artifact, "id")
    size_in_bytes = _required(artifact, "size_in_bytes")
    if not _is_int(artifact_id) or artifact_id <= 0:
        raise ArtifactDownloadError("cost artifact id is invalid")
    if not _is_int(size_in_bytes) or not 0 < size_in_bytes <= _MAX_ARCHIVE_BYTES:
        raise ArtifactDownloadError("cost artifact size is invalid")
    expired = _required(artifact, "expired")
    if not isinstance(expired, bool) or expired:
        raise ArtifactDownloadError("cost artifact is expired or malformed")
    digest = _require_text(_required(artifact, "digest"), "artifact.digest")
    if _DIGEST.fullmatch(digest) is None:
        raise ArtifactDownloadError("cost artifact digest is invalid")
    workflow_run = _required(artifact, "workflow_run")
    if not isinstance(workflow_run, Mapping):
        raise ArtifactDownloadError("cost artifact workflow_run is malformed")
    workflow_run_id = workflow_run.get("id")
    if not _is_int(workflow_run_id) or workflow_run_id != _require_decimal(
        arguments.run_id, "run_id"
    ):
        raise ArtifactDownloadError("cost artifact belongs to a foreign workflow run")
    if workflow_run.get("head_sha") != arguments.commit_sha:
        raise ArtifactDownloadError("cost artifact belongs to a foreign commit")
    producer_attempt = int(match.group(1))
    if producer_attempt >= _require_decimal(
        arguments.consumer_run_attempt, "consumer_run_attempt"
    ):
        raise ArtifactDownloadError("cost artifact is not from an earlier attempt")
    return _Candidate(
        artifact_id=artifact_id,
        artifact_name=name,
        producer_attempt=producer_attempt,
        digest=digest,
        size_in_bytes=size_in_bytes,
    )


def _select_candidate(
    artifacts: Sequence[Mapping[str, object]], arguments: DownloadArguments
) -> _Candidate | None:
    by_attempt: dict[int, _Candidate] = {}
    artifact_ids: set[int] = set()
    for artifact in artifacts:
        candidate = _candidate_from_artifact(artifact, arguments)
        if candidate is None:
            continue
        if (
            candidate.producer_attempt in by_attempt
            or candidate.artifact_id in artifact_ids
        ):
            raise ArtifactDownloadError("cost artifact candidates are duplicated")
        by_attempt[candidate.producer_attempt] = candidate
        artifact_ids.add(candidate.artifact_id)
    if not by_attempt:
        return None
    return by_attempt[max(by_attempt)]


def _header(headers: Mapping[str, str], name: str) -> str:
    matches = [value for key, value in headers.items() if key.lower() == name.lower()]
    if len(matches) != 1:
        raise ArtifactDownloadError("artifact redirect has an invalid Location header")
    return _require_text(matches[0], "artifact redirect Location")


def _validate_cdn_location(location: str) -> str:
    try:
        parsed = urlsplit(location)
        port = parsed.port
    except ValueError as error:
        raise ArtifactDownloadError(
            "artifact redirect location is malformed"
        ) from error
    hostname = parsed.hostname.lower() if parsed.hostname is not None else ""
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
        or not parsed.path.startswith("/")
        or not hostname.endswith(_TRUSTED_CDN_SUFFIXES)
    ):
        raise ArtifactDownloadError(
            "artifact redirect location is not a trusted HTTPS CDN"
        )
    return location


def _download_archive(
    candidate: _Candidate,
    arguments: DownloadArguments,
    token: str,
    request: RequestTransport,
) -> bytes:
    endpoint = (
        f"{_API_ROOT}/repos/{arguments.repository}/actions/artifacts/"
        f"{candidate.artifact_id}/zip"
    )
    redirect = request(_api_request(endpoint, token), _MAX_REDIRECT_BYTES)
    if redirect.status != 302:
        raise ArtifactDownloadError("artifact API did not return a single redirect")
    location = _validate_cdn_location(_header(redirect.headers, "Location"))
    archive = request(_cdn_request(location), _MAX_ARCHIVE_BYTES)
    if archive.status != 200:
        raise ArtifactDownloadError("artifact CDN returned an unexpected status")
    # ``size_in_bytes`` is GitHub's logical artifact inventory value, not a
    # contract for the byte length of the ZIP served by the signed CDN URL.
    # The transport is bounded independently by ``_MAX_ARCHIVE_BYTES`` and
    # authenticated by the metadata digest below.
    if hashlib.sha256(archive.body).hexdigest() != candidate.digest.removeprefix(
        "sha256:"
    ):
        raise ArtifactDownloadError(
            "artifact archive digest does not match its metadata"
        )
    return archive.body


def _extract_historical_costs(archive_bytes: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].filename != _HISTORICAL_COSTS_NAME:
                raise ArtifactDownloadError(
                    "artifact archive must contain exactly HISTORICAL_COSTS.json"
                )
            member = members[0]
            mode = member.external_attr >> 16
            member_type = stat.S_IFMT(mode)
            if (
                member.is_dir()
                or member.flag_bits & 0x1
                or member_type not in {0, stat.S_IFREG}
                or not 0 < member.file_size <= _MAX_MEMBER_BYTES
                or member.compress_size <= 0
                or member.file_size > member.compress_size * _MAX_COMPRESSION_RATIO
            ):
                raise ArtifactDownloadError("artifact archive member is unsafe")
            contents = archive.read(member)
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as error:
        raise ArtifactDownloadError("artifact archive cannot be read safely") from error
    if len(contents) != member.file_size:
        raise ArtifactDownloadError("artifact archive member size is inconsistent")
    return contents


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _safe_output_root(output_root: Path) -> Path:
    parts = _safe_relative_directory(output_root)
    root = Path.cwd()
    if _is_link_or_junction(root):
        raise ArtifactDownloadError("current working directory must not be a link")
    for part in parts:
        root /= part
        if root.exists():
            if _is_link_or_junction(root) or not root.is_dir():
                raise ArtifactDownloadError("output_root traverses an unsafe directory")
        else:
            root.mkdir()
    return root


def _assert_safe_output_file(path: Path) -> None:
    if path.exists() or _is_link_or_junction(path):
        if not path.is_file() or _is_link_or_junction(path):
            raise ArtifactDownloadError("GITHUB_OUTPUT must be a regular file")
        if path.stat().st_nlink != 1:
            raise ArtifactDownloadError("GITHUB_OUTPUT must not be a hard link")


def _atomic_append_github_output(path: Path, lines: str) -> None:
    parent = path.parent
    if not parent.is_dir() or _is_link_or_junction(parent):
        raise ArtifactDownloadError("GITHUB_OUTPUT parent must be a regular directory")
    _assert_safe_output_file(path)
    previous = path.read_bytes() if path.exists() else b""
    if previous and not previous.endswith(b"\n"):
        raise ArtifactDownloadError("GITHUB_OUTPUT has an incomplete prior record")
    try:
        encoded = lines.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ArtifactDownloadError("GITHUB_OUTPUT record is not UTF-8") from error
    descriptor, temporary_name = tempfile.mkstemp(prefix=".stryker-output-", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(previous + encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _remove_materialized_candidate(destination: Path) -> None:
    if destination.exists() and not _is_link_or_junction(destination):
        shutil.rmtree(destination)


def _materialize_candidate(
    candidate: _Candidate, contents: bytes, arguments: DownloadArguments
) -> str:
    root = _safe_output_root(arguments.output_root)
    destination = root / candidate.artifact_name
    if destination.exists() or _is_link_or_junction(destination):
        raise ArtifactDownloadError("candidate destination already exists")
    stage = Path(tempfile.mkdtemp(prefix=".stryker-cost-", dir=root))
    staged_candidate = stage / candidate.artifact_name
    moved = False
    try:
        staged_candidate.mkdir()
        output = staged_candidate / _HISTORICAL_COSTS_NAME
        with output.open("xb") as cost_file:
            cost_file.write(contents)
            cost_file.flush()
            os.fsync(cost_file.fileno())
        os.replace(staged_candidate, destination)
        moved = True
        artifact = f"{candidate.artifact_name}/{_HISTORICAL_COSTS_NAME}"
        _atomic_append_github_output(
            arguments.github_output,
            f"artifact={artifact}\nhas_candidate=true\n",
        )
        return artifact
    except BaseException:
        if moved:
            _remove_materialized_candidate(destination)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def download_stryker_cost_artifacts(
    arguments: DownloadArguments,
    *,
    token: str,
    request: RequestTransport = _default_request,
) -> DownloadResult:
    """Select, verify, and atomically materialise an earlier Stryker cost file."""

    _validate_arguments(arguments)
    _require_text(token, "GitHub token")
    run_url = (
        f"{_API_ROOT}/repos/{arguments.repository}/actions/runs/{arguments.run_id}"
    )
    _validate_current_run(_request_json(run_url, token, request), arguments)
    candidate = _select_candidate(_list_artifacts(arguments, token, request), arguments)
    if candidate is None:
        _atomic_append_github_output(arguments.github_output, "has_candidate=false\n")
        return DownloadResult(has_candidate=False, artifact=None)
    contents = _extract_historical_costs(
        _download_archive(candidate, arguments, token, request)
    )
    artifact = _materialize_candidate(candidate, contents, arguments)
    return DownloadResult(has_candidate=True, artifact=artifact)


def parse_arguments(argv: Sequence[str] | None = None) -> DownloadArguments:
    """Parse workflow identity values; credentials intentionally have no flag."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--consumer-run-attempt", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--github-output", required=True, type=Path)
    namespace = parser.parse_args(argv)
    return DownloadArguments(
        repository=namespace.repository,
        run_id=namespace.run_id,
        consumer_run_attempt=namespace.consumer_run_attempt,
        commit_sha=namespace.commit_sha,
        event=namespace.event,
        workflow_path=namespace.workflow_path,
        artifact_prefix=namespace.artifact_prefix,
        output_root=namespace.output_root,
        github_output=namespace.github_output,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the downloader without ever accepting or printing a token."""

    try:
        arguments = parse_arguments(argv)
        token = _require_text(os.environ.get("GH_TOKEN", ""), "GH_TOKEN")
        download_stryker_cost_artifacts(arguments, token=token)
    except ArtifactDownloadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
