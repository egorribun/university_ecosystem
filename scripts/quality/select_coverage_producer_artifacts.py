"""Select retry-safe coverage producer artifacts from one GitHub Actions run.

Coverage aggregation is a consumer of several independently uploaded producer
artifacts.  A failed-job rerun increments ``github.run_attempt`` without
re-running successful producers, so an exact attempt suffix is not a complete
artifact contract.  This module takes one bounded, same-run REST snapshot and
selects the newest valid artifact for each fixed producer identity.  The
returned server-issued IDs are consumed by the pinned download action; no
cross-run or unverified artifact fallback is possible.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# Keep direct repository-script invocation compatible with the other quality
# CLIs while the workflow itself uses the package-safe ``python -m`` form.
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality import select_same_run_artifact_cli as same_run


class CoverageProducerSelectionError(ValueError):
    """Raised when the same-run producer artifact set is incomplete or unsafe."""


@dataclass(frozen=True)
class CoverageProducerSpec:
    """Identity of one artifact uploaded by the coverage producer matrix."""

    key: str
    prefix: str
    producer_job: str


# These names are intentionally repository-owned constants.  They mirror the
# producer upload contracts and are not accepted from downloaded metadata.
COVERAGE_PRODUCER_SPECS: tuple[CoverageProducerSpec, ...] = (
    CoverageProducerSpec(
        "backend_shard_0",
        "backend-coverage-data-All-Python 3.14-shard-0-attempt-",
        "unit-tests",
    ),
    CoverageProducerSpec(
        "backend_shard_1",
        "backend-coverage-data-All-Python 3.14-shard-1-attempt-",
        "unit-tests",
    ),
    CoverageProducerSpec(
        "backend_shard_2",
        "backend-coverage-data-All-Python 3.14-shard-2-attempt-",
        "unit-tests",
    ),
    CoverageProducerSpec(
        "backend_shard_3",
        "backend-coverage-data-All-Python 3.14-shard-3-attempt-",
        "unit-tests",
    ),
    CoverageProducerSpec("frontend", "frontend-coverage-attempt-", "unit-tests"),
    CoverageProducerSpec("go_gateway", "go-coverage-services-gateway-attempt-", "test"),
    CoverageProducerSpec("go_ws_hub", "go-coverage-services-ws-hub-attempt-", "test"),
    CoverageProducerSpec(
        "go_file_processor",
        "go-coverage-services-file-processor-attempt-",
        "test",
    ),
    CoverageProducerSpec(
        "go_uni_cli", "go-coverage-services-cmd-uni-cli-attempt-", "test"
    ),
    CoverageProducerSpec(
        "go_logging", "go-coverage-services-pkg-logging-attempt-", "test"
    ),
    CoverageProducerSpec(
        "go_spiffe", "go-coverage-services-pkg-spiffe-attempt-", "test"
    ),
    CoverageProducerSpec(
        "go_spicedb", "go-coverage-services-pkg-spicedb-attempt-", "test"
    ),
    CoverageProducerSpec("rust_coverage", "rust-coverage-attempt-", "rust-tests"),
    CoverageProducerSpec("rust_codecov", "rust-codecov-reports-attempt-", "rust-tests"),
)

_KEY = re.compile(r"[a-z][a-z0-9_]*$")
_POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]*$")
_ARTIFACT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]*$")
_MAX_OUTPUT_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CoverageProducerArguments:
    repository: str
    run_id: str
    consumer_run_attempt: str
    commit_sha: str
    run_head_sha: str | None
    event: str
    workflow_path: str


def _selector_arguments(
    arguments: CoverageProducerArguments, prefix: str = "coverage-"
) -> same_run.SelectionArguments:
    return same_run.SelectionArguments(
        repository=arguments.repository,
        run_id=arguments.run_id,
        consumer_run_attempt=arguments.consumer_run_attempt,
        commit_sha=arguments.commit_sha,
        run_head_sha=arguments.run_head_sha,
        event=arguments.event,
        workflow_path=arguments.workflow_path,
        artifact_prefix=prefix,
        artifact_suffix="",
        attempt_policy="current-or-earlier",
        allow_empty=False,
        artifact_name_layout="attempt",
    )


def _validate_arguments(arguments: CoverageProducerArguments) -> None:
    try:
        same_run._validate_arguments(_selector_arguments(arguments))
    except same_run.SameRunArtifactError as error:
        raise CoverageProducerSelectionError(str(error)) from error


def _validate_spec(spec: CoverageProducerSpec) -> None:
    if _KEY.fullmatch(spec.key) is None:
        raise CoverageProducerSelectionError("producer spec key is unsafe")
    if (
        not spec.prefix
        or "\x00" in spec.prefix
        or "\r" in spec.prefix
        or "\n" in spec.prefix
        or _ARTIFACT_NAME.fullmatch(spec.prefix[:-1]) is None
        or not spec.prefix.endswith("-")
    ):
        raise CoverageProducerSelectionError(
            f"producer spec prefix is unsafe: {spec.key}"
        )
    if not spec.producer_job or any(
        ord(character) < 0x20 or ord(character) == 0x7F
        for character in spec.producer_job
    ):
        raise CoverageProducerSelectionError(
            f"producer spec producer job is unsafe: {spec.key}"
        )


def _select_one(
    spec: CoverageProducerSpec,
    artifacts: Sequence[Mapping[str, object]],
    arguments: CoverageProducerArguments,
) -> dict[str, object]:
    _validate_spec(spec)
    selector_arguments = _selector_arguments(arguments, spec.prefix)
    candidates: dict[int, tuple[int, str, str]] = {}
    artifact_ids: set[int] = set()
    for artifact in artifacts:
        try:
            candidate = same_run._candidate_from_artifact(artifact, selector_arguments)
        except same_run.SameRunArtifactError as error:
            raise CoverageProducerSelectionError(str(error)) from error
        if candidate is None:
            continue
        artifact_id, artifact_name, producer_attempt, artifact_digest = candidate
        if producer_attempt in candidates or artifact_id in artifact_ids:
            raise CoverageProducerSelectionError(
                f"producer artifact candidates are duplicated: {spec.key}"
            )
        candidates[producer_attempt] = (artifact_id, artifact_name, artifact_digest)
        artifact_ids.add(artifact_id)
    if not candidates:
        raise CoverageProducerSelectionError(
            f"missing same-run coverage producer artifact: {spec.key}"
        )
    producer_attempt = max(candidates)
    artifact_id, artifact_name, artifact_digest = candidates[producer_attempt]
    return {
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "producer_attempt": producer_attempt,
        "artifact_digest": artifact_digest,
        "producer_job": spec.producer_job,
    }


def select_coverage_producers(
    arguments: CoverageProducerArguments,
    *,
    token: str,
    request: same_run.RequestTransport,
) -> dict[str, dict[str, object]]:
    """Select every required producer from one complete current-run snapshot."""

    _validate_arguments(arguments)
    try:
        same_run._require_token(token)
    except same_run.SameRunArtifactError as error:
        raise CoverageProducerSelectionError(str(error)) from error
    base = _selector_arguments(arguments)
    try:
        bounded_request = same_run._bounded_request_transport(request)
        run_path = f"/repos/{arguments.repository}/actions/runs/{arguments.run_id}"
        metadata = same_run._request_json(run_path, token, bounded_request)
        same_run._validate_current_run(metadata, base)
        artifacts = same_run._list_artifacts(base, token, bounded_request)
    except same_run.SameRunArtifactError as error:
        raise CoverageProducerSelectionError(str(error)) from error

    selected = {
        spec.key: _select_one(spec, artifacts, arguments)
        for spec in COVERAGE_PRODUCER_SPECS
    }
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for key, selection in selected.items():
        artifact_id = selection["artifact_id"]
        artifact_name = selection["artifact_name"]
        if not isinstance(artifact_id, int) or not isinstance(artifact_name, str):
            raise CoverageProducerSelectionError(
                f"selected artifact identity is malformed: {key}"
            )
        if artifact_id in seen_ids or artifact_name in seen_names:
            raise CoverageProducerSelectionError(
                f"selected producer artifacts are duplicated: {key}"
            )
        seen_ids.add(artifact_id)
        seen_names.add(artifact_name)
    if (
        selected["rust_coverage"]["producer_attempt"]
        != selected["rust_codecov"]["producer_attempt"]
    ):
        raise CoverageProducerSelectionError(
            "Rust coverage and Codecov artifacts must come from the same producer attempt"
        )
    return selected


def _write_github_output(
    path: Path, selections: Mapping[str, Mapping[str, object]]
) -> None:
    """Append one compact, newline-free JSON output record atomically."""

    try:
        parent = same_run._safe_output_parent(path)
        parent_before = parent.lstat()
        before = same_run._safe_output_file(path)
        previous = path.read_bytes()
        after_read = same_run._safe_output_file(path)
        if not same_run._same_file_identity(before, after_read):
            raise CoverageProducerSelectionError(
                "GITHUB_OUTPUT changed while it was read"
            )
    except (OSError, same_run.SameRunArtifactError) as error:
        raise CoverageProducerSelectionError(
            "GITHUB_OUTPUT must be an existing regular file"
        ) from error
    if len(previous) > _MAX_OUTPUT_BYTES:
        raise CoverageProducerSelectionError("GITHUB_OUTPUT exceeds its maximum size")
    if previous and not previous.endswith(b"\n"):
        raise CoverageProducerSelectionError(
            "GITHUB_OUTPUT has an incomplete prior record"
        )
    encoded = json.dumps(
        dict(selections), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if b"\r" in encoded or b"\n" in encoded:
        raise CoverageProducerSelectionError("selection output contains a newline")
    record = b"selections=" + encoded + b"\n"
    if len(previous) + len(record) > _MAX_OUTPUT_BYTES:
        raise CoverageProducerSelectionError("GITHUB_OUTPUT exceeds its maximum size")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".coverage-selection-output-", dir=parent, delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(previous + record)
            temporary.flush()
            os.fsync(temporary.fileno())
        if not same_run._same_file_identity(
            after_read, same_run._safe_output_file(path)
        ):
            raise CoverageProducerSelectionError(
                "GITHUB_OUTPUT changed before replacement"
            )
        current_parent = same_run._safe_output_parent(path)
        if current_parent != parent:
            raise CoverageProducerSelectionError(
                "GITHUB_OUTPUT parent changed before replacement"
            )
        parent_after = current_parent.lstat()
        if (parent_before.st_dev, parent_before.st_ino) != (
            parent_after.st_dev,
            parent_after.st_ino,
        ):
            raise CoverageProducerSelectionError(
                "GITHUB_OUTPUT parent changed before replacement"
            )
        os.replace(temporary_name, path)
        temporary_name = None
        after_parent = parent.lstat()
        if (
            stat.S_ISDIR(parent_before.st_mode)
            and after_parent.st_ino != parent_before.st_ino
        ):
            raise CoverageProducerSelectionError("GITHUB_OUTPUT parent changed")
        same_run._safe_output_file(path)
    except CoverageProducerSelectionError:
        raise
    except OSError as error:
        raise CoverageProducerSelectionError(
            "GITHUB_OUTPUT cannot be written atomically"
        ) from error
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _parse_arguments(argv: Sequence[str] | None = None) -> CoverageProducerArguments:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--consumer-run-attempt", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--run-head-sha")
    parser.add_argument("--event", required=True)
    parser.add_argument("--workflow-path", required=True)
    namespace = parser.parse_args(argv)
    return CoverageProducerArguments(
        repository=namespace.repository,
        run_id=namespace.run_id,
        consumer_run_attempt=namespace.consumer_run_attempt,
        commit_sha=namespace.commit_sha,
        run_head_sha=namespace.run_head_sha,
        event=namespace.event,
        workflow_path=namespace.workflow_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parse_arguments(argv)
        output = Path(
            same_run._require_text(os.environ.get("GITHUB_OUTPUT", ""), "GITHUB_OUTPUT")
        )
        selected = select_coverage_producers(
            arguments,
            token=same_run._require_token(os.environ.get("GH_TOKEN", "")),
            request=same_run._default_request,
        )
        _write_github_output(output, selected)
    except (
        CoverageProducerSelectionError,
        same_run.SameRunArtifactError,
        OSError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
