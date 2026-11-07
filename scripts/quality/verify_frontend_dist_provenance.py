"""Verify the uploaded frontend-dist archive and its GitHub provenance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OIDC_ISSUER = "https://token.actions.githubusercontent.com"
SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
ARTIFACT_NAME = "frontend-dist"
WORKFLOW_PATH = ".github/workflows/ci.yml"
CHUNK_SIZE = 1024 * 1024
MINIMUM_GH_VERSION = (2, 102, 0)
GH_VERSION_TIMEOUT_SECONDS = 15
GH_VERIFY_TIMEOUT_SECONDS = 180
GH_VERSION_PATTERN = re.compile(r"^gh version (\d+)\.(\d+)\.(\d+)(?:\s|$)")


class ProvenanceError(ValueError):
    """A required artifact, run, or signed identity field did not match."""


@dataclass(frozen=True)
class Binding:
    repository: str
    repository_id: str
    artifact_id: str
    artifact_digest: str
    producer_result: str
    run_id: str
    run_attempt: str
    event: str
    source_sha: str
    source_ref: str
    caller_workflow_ref: str

    @property
    def certificate_identity(self) -> str:
        return f"https://github.com/{self.caller_workflow_ref}"

    @property
    def run_invocation_uri(self) -> str:
        return (
            f"https://github.com/{self.repository}/actions/runs/{self.run_id}"
            f"/attempts/{self.run_attempt}"
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProvenanceError(message)


def _require_text(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value), f"missing or invalid {field}")
    return value


def _require_sha(value: str, field: str, length: int) -> None:
    _require(
        re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None,
        f"invalid {field}",
    )


def binding_from_environment(env: Mapping[str, str]) -> Binding:
    """Read and validate only the explicit GitHub run outputs used by the gate."""
    repository = _require_text(env.get("GITHUB_REPOSITORY"), "repository")
    _require(repository.count("/") == 1, "repository must be owner/name")
    repository_id = _require_text(env.get("EXPECTED_REPOSITORY_ID"), "repository id")
    _require(
        repository_id.isdigit() and int(repository_id) > 0, "invalid repository id"
    )
    artifact_id = _require_text(env.get("FRONTEND_DIST_ARTIFACT_ID"), "artifact id")
    _require(
        re.fullmatch(r"[1-9][0-9]{0,19}", artifact_id) is not None,
        "invalid artifact id",
    )
    artifact_digest = _require_text(
        env.get("FRONTEND_DIST_ARTIFACT_DIGEST"), "artifact digest"
    )
    _require_sha(artifact_digest, "artifact digest", 64)
    run_id = _require_text(env.get("GITHUB_RUN_ID"), "run id")
    run_attempt = _require_text(env.get("GITHUB_RUN_ATTEMPT"), "run attempt")
    _require(run_id.isdigit() and int(run_id) > 0, "invalid run id")
    _require(run_attempt.isdigit() and int(run_attempt) > 0, "invalid run attempt")
    source_sha = _require_text(env.get("GITHUB_SHA"), "source SHA")
    _require_sha(source_sha, "source SHA", 40)
    source_ref = _require_text(env.get("GITHUB_REF"), "source ref")
    _require(source_ref.startswith("refs/heads/"), "push source ref must be a branch")
    caller_workflow_ref = _require_text(
        env.get("GITHUB_WORKFLOW_REF"), "caller workflow ref"
    )
    expected_workflow_ref = f"{repository}/{WORKFLOW_PATH}@{source_ref}"
    _require(
        caller_workflow_ref == expected_workflow_ref,
        "caller workflow ref does not identify the current CI workflow and ref",
    )
    event = _require_text(env.get("GITHUB_EVENT_NAME"), "event")
    _require(event == "push", "application artifact attestation is push-only")
    producer_result = _require_text(
        env.get("FRONTEND_TESTS_RESULT"), "frontend producer result"
    )
    _require(producer_result == "success", "frontend producer job did not succeed")
    attestation_result = _require_text(
        env.get("FRONTEND_ATTESTATION_RESULT"), "attestation job result"
    )
    _require(attestation_result == "success", "attestation job did not succeed")
    return Binding(
        repository=repository,
        repository_id=repository_id,
        artifact_id=artifact_id,
        artifact_digest=artifact_digest,
        producer_result=producer_result,
        run_id=run_id,
        run_attempt=run_attempt,
        event=event,
        source_sha=source_sha,
        source_ref=source_ref,
        caller_workflow_ref=caller_workflow_ref,
    )


def validate_artifact_and_run(
    artifact: dict[str, Any], run: dict[str, Any], binding: Binding
) -> int:
    """Bind the Actions artifact record to this exact CI run and source."""
    _require(str(artifact.get("id")) == binding.artifact_id, "artifact id mismatch")
    _require(artifact.get("name") == ARTIFACT_NAME, "artifact name mismatch")
    _require(artifact.get("expired") is False, "artifact is missing or expired")
    _require(
        artifact.get("digest") == f"sha256:{binding.artifact_digest}",
        "artifact API digest does not match the upload output",
    )
    size = artifact.get("size_in_bytes")
    _require(isinstance(size, int) and size > 0, "invalid artifact archive size")

    artifact_run = artifact.get("workflow_run")
    _require(
        isinstance(artifact_run, dict), "artifact is not attached to a workflow run"
    )
    _require(str(artifact_run.get("id")) == binding.run_id, "artifact run id mismatch")
    _require(
        str(artifact_run.get("repository_id")) == binding.repository_id,
        "artifact repository id mismatch",
    )
    _require(
        str(artifact_run.get("head_repository_id")) == binding.repository_id,
        "artifact was not produced by this repository",
    )
    _require(
        artifact_run.get("head_sha") == binding.source_sha,
        "artifact source SHA mismatch",
    )
    _require(
        artifact_run.get("head_branch")
        == binding.source_ref.removeprefix("refs/heads/"),
        "artifact source branch mismatch",
    )

    _require(str(run.get("id")) == binding.run_id, "workflow run id mismatch")
    _require(
        str(run.get("run_attempt")) == binding.run_attempt, "workflow attempt mismatch"
    )
    _require(run.get("event") == binding.event, "workflow event mismatch")
    _require(run.get("head_sha") == binding.source_sha, "workflow source SHA mismatch")
    _require(
        run.get("head_branch") == binding.source_ref.removeprefix("refs/heads/"),
        "workflow source branch mismatch",
    )
    _require(run.get("path") == WORKFLOW_PATH, "workflow path mismatch")
    repository = run.get("repository")
    _require(isinstance(repository, dict), "workflow repository metadata is missing")
    _require(
        str(repository.get("id")) == binding.repository_id,
        "workflow repository id mismatch",
    )
    return size


def _json_request(
    url: str, token: str, opener: urllib.request.OpenerDirector
) -> dict[str, Any]:
    # Scheme validation is centralized in _api_base and _SafeArtifactRedirect.
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with opener.open(request, timeout=60) as response:
            value = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ProvenanceError("GitHub Actions metadata request failed") from exc
    _require(isinstance(value, dict), "GitHub Actions metadata is not an object")
    return value


class _SafeArtifactRedirect(urllib.request.HTTPRedirectHandler):
    """Follow GitHub's archive redirect without forwarding credentials cross-host."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        fp: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> urllib.request.Request | None:
        target = urllib.parse.urlsplit(new_url)
        _require(
            target.scheme == "https"
            and bool(target.hostname)
            and target.username is None
            and target.password is None,
            "artifact archive redirect must use HTTPS without embedded credentials",
        )
        redirected = super().redirect_request(
            request, fp, code, message, headers, new_url
        )
        if redirected is not None:
            source_host = urllib.parse.urlsplit(request.full_url).netloc.casefold()
            if target.netloc.casefold() != source_host:
                redirected.remove_header("Authorization")
                redirected.remove_header("Accept")
        return redirected


def _api_base(env: Mapping[str, str]) -> str:
    api_url = _require_text(
        env.get("GITHUB_API_URL", "https://api.github.com"), "API URL"
    )
    parsed = urllib.parse.urlsplit(api_url)
    _require(
        parsed.scheme == "https" and bool(parsed.netloc),
        "GitHub API URL must use HTTPS",
    )
    return api_url.rstrip("/")


def fetch_artifact_and_run(
    binding: Binding, env: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, Any], int]:
    token = _require_text(env.get("GH_TOKEN"), "GitHub token")
    owner, repository_name = binding.repository.split("/")
    base = _api_base(env)
    repo_path = "/".join(
        urllib.parse.quote(part, safe="") for part in (owner, repository_name)
    )
    opener = urllib.request.build_opener(_SafeArtifactRedirect())
    artifact_url = f"{base}/repos/{repo_path}/actions/artifacts/{binding.artifact_id}"
    run_url = f"{base}/repos/{repo_path}/actions/runs/{binding.run_id}"
    artifact = _json_request(artifact_url, token, opener)
    run = _json_request(run_url, token, opener)
    size = validate_artifact_and_run(artifact, run, binding)
    return artifact, run, size


def download_raw_archive(
    binding: Binding,
    expected_size: int,
    destination: Path,
    env: Mapping[str, str],
) -> str:
    token = _require_text(env.get("GH_TOKEN"), "GitHub token")
    owner, repository_name = binding.repository.split("/")
    repo_path = "/".join(
        urllib.parse.quote(part, safe="") for part in (owner, repository_name)
    )
    archive_url = (
        f"{_api_base(env)}/repos/{repo_path}/actions/artifacts/"
        f"{binding.artifact_id}/zip"
    )
    # Scheme validation is centralized in _api_base and _SafeArtifactRedirect.
    request = urllib.request.Request(  # noqa: S310
        archive_url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    digest = hashlib.sha256()
    total = 0
    try:
        with (
            urllib.request.build_opener(_SafeArtifactRedirect()).open(
                request, timeout=120
            ) as response,
            destination.open("wb") as archive,
        ):
            while chunk := response.read(CHUNK_SIZE):
                total += len(chunk)
                _require(
                    total <= expected_size, "archive exceeds its API-reported size"
                )
                digest.update(chunk)
                archive.write(chunk)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise ProvenanceError("raw Actions artifact archive download failed") from exc
    _require(total == expected_size, "archive size differs from the API record")
    archive_digest = digest.hexdigest()
    _require(archive_digest == binding.artifact_digest, "raw archive SHA-256 mismatch")
    return archive_digest


def validate_verified_output(document: Any, binding: Binding) -> None:
    """Check every authenticated result and require the exact current invocation.

    ``document`` must come from a successful ``gh attestation verify`` invocation.
    GitHub CLI emits one array entry per verified attestation. Multiple entries
    are accepted only when each binds the same exact artifact, source, workflow,
    repository, event, and hosted-runner claims. Other invocation URIs must still
    be well-formed GitHub Actions run URIs for this repository, and at least one
    entry must match this run ID and attempt exactly. Unit fixtures exercise only
    this policy parser; they are not signatures or proofs.
    """
    _require(
        isinstance(document, list) and bool(document),
        "expected a non-empty list of cryptographically verified attestations",
    )
    current_invocation_verified = False

    # runInvocationURI is allowed to differ across independently verified
    # attestations for the same reproducible artifact. Every other binding is
    # still exact for every record, and acceptance always requires this run's
    # exact invocation URI to appear in the verified result set.
    exact_claims = {
        "issuer": OIDC_ISSUER,
        "subjectAlternativeName": binding.certificate_identity,
        "sourceRepositoryURI": f"https://github.com/{binding.repository}",
        "sourceRepositoryIdentifier": binding.repository_id,
        "sourceRepositoryDigest": binding.source_sha,
        "sourceRepositoryRef": binding.source_ref,
        "buildTrigger": binding.event,
        "runnerEnvironment": "github-hosted",
    }

    for entry in document:
        _require(isinstance(entry, dict), "verified attestation result is missing")
        result = entry.get("verificationResult")
        _require(isinstance(result, dict), "verified result is missing")
        timestamps = result.get("verifiedTimestamps")
        _require(
            isinstance(timestamps, list) and timestamps,
            "attestation has no verified timestamp",
        )
        signature = result.get("signature")
        _require(isinstance(signature, dict), "verified signature is missing")
        certificate = signature.get("certificate")
        _require(isinstance(certificate, dict), "verified certificate is missing")

        for field, expected in exact_claims.items():
            _require(
                certificate.get(field) == expected,
                f"certificate {field} mismatch",
            )

        invocation_uri = certificate.get("runInvocationURI")
        _require(
            _is_actions_run_uri_for_repository(invocation_uri, binding.repository),
            "certificate run invocation URI is invalid",
        )
        current_invocation_verified = (
            current_invocation_verified or invocation_uri == binding.run_invocation_uri
        )

        statement = result.get("statement")
        _require(isinstance(statement, dict), "verified statement is missing")
        _require(
            statement.get("predicateType") == SLSA_PREDICATE,
            "attestation predicate type mismatch",
        )
        subjects = statement.get("subject")
        _require(
            isinstance(subjects, list) and len(subjects) == 1,
            "expected exactly one attestation subject",
        )
        subject = subjects[0]
        _require(
            isinstance(subject, dict) and subject.get("name") == ARTIFACT_NAME,
            "attestation subject name mismatch",
        )
        subject_digest = subject.get("digest")
        _require(
            isinstance(subject_digest, dict), "attestation subject digest is missing"
        )
        _require(
            subject_digest.get("sha256") == binding.artifact_digest,
            "attestation subject digest mismatch",
        )

    _require(
        current_invocation_verified,
        "no cryptographically verified attestation matches the current run and attempt",
    )


def _is_actions_run_uri_for_repository(value: Any, repository: str) -> bool:
    """Accept only a well-formed GitHub Actions run URI for this repository."""
    # Python's urlsplit strips some leading controls and tabs/newlines anywhere.
    # Reject raw ASCII C0 controls and spaces before parsing to avoid normalization.
    if not isinstance(value, str) or any(ord(character) <= 0x20 for character in value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return False

    prefix = f"/{repository}/actions/runs/"
    if not parsed.path.casefold().startswith(prefix.casefold()):
        return False
    run_and_attempt = parsed.path[len(prefix) :].split("/attempts/")
    return (
        len(run_and_attempt) == 2
        and re.fullmatch(r"[1-9][0-9]*", run_and_attempt[0]) is not None
        and re.fullmatch(r"[1-9][0-9]*", run_and_attempt[1]) is not None
    )


def check_gh_version(env: Mapping[str, str]) -> str:
    """Require a patched GitHub CLI version before trusting its verification."""
    try:
        completed = subprocess.run(
            ["gh", "--version"],  # noqa: S607 - runner-installed CLI, version-gated
            check=False,
            capture_output=True,
            text=True,
            env=dict(env),
            timeout=GH_VERSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProvenanceError("GitHub CLI version check timed out") from exc
    except OSError as exc:
        raise ProvenanceError("GitHub CLI could not run version check") from exc

    _require(completed.returncode == 0, "GitHub CLI version check failed")
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    match = GH_VERSION_PATTERN.match(first_line)
    _require(match is not None, "GitHub CLI returned an unrecognized version")
    version_text = ".".join(match.groups())
    version = tuple(int(part) for part in match.groups())
    _require(
        version >= MINIMUM_GH_VERSION,
        f"GitHub CLI >=2.102.0 is required for attestation verification; found {version_text}",
    )
    return version_text


def verify_with_gh(archive_path: Path, binding: Binding, env: Mapping[str, str]) -> str:
    gh_version = check_gh_version(env)
    command = [
        "gh",
        "attestation",
        "verify",
        str(archive_path),
        "--repo",
        binding.repository,
        "--cert-identity",
        binding.certificate_identity,
        "--cert-oidc-issuer",
        OIDC_ISSUER,
        "--source-digest",
        binding.source_sha,
        "--source-ref",
        binding.source_ref,
        "--predicate-type",
        SLSA_PREDICATE,
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]
    try:
        # Fixed executable and argv list; no shell or repository-provided command.
        completed = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
            env=dict(env),
            timeout=GH_VERIFY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProvenanceError("gh attestation verify timed out") from exc
    except OSError as exc:
        raise ProvenanceError(
            "GitHub CLI could not run attestation verification"
        ) from exc
    if completed.returncode != 0:
        raise ProvenanceError(
            f"gh attestation verify failed with exit code {completed.returncode}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProvenanceError("gh attestation verify returned invalid JSON") from exc
    validate_verified_output(result, binding)
    return gh_version


def main() -> int:
    try:
        binding = binding_from_environment(os.environ)
        _, _, archive_size = fetch_artifact_and_run(binding, os.environ)
        with tempfile.TemporaryDirectory(
            prefix="frontend-dist-provenance-"
        ) as temp_dir:
            archive_path = Path(temp_dir) / "frontend-dist.zip"
            digest = download_raw_archive(
                binding, archive_size, archive_path, os.environ
            )
            gh_version = verify_with_gh(archive_path, binding, os.environ)
        print(
            "Frontend artifact provenance verified: "
            f"artifact_id={binding.artifact_id} "
            f"sha256={digest} "
            f"source_sha={binding.source_sha} "
            f"gh_version={gh_version} "
            f"run_id={binding.run_id} attempt={binding.run_attempt}"
        )
        return 0
    except ProvenanceError as exc:
        print(f"::error::Frontend artifact provenance rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
