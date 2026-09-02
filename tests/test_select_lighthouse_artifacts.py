from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import scripts.quality.select_coverage_artifacts as coverage_selector
import scripts.quality.select_lighthouse_artifacts as lighthouse_selector
from scripts.quality.select_coverage_artifacts import (
    CoverageArtifactSelection,
    CoverageSelectionResult,
)
from scripts.quality.select_lighthouse_artifacts import (
    LIGHTHOUSE_LOGICAL_ARTIFACT,
    LIGHTHOUSE_METADATA_PATH,
    LighthouseSelectionError,
    LighthouseSelectionResult,
    expected_lighthouse_report_specs,
    lighthouse_artifact_slot,
    select_lighthouse_artifacts,
)
from tests.symlink_support import DIRECTORY_SYMLINKS_SUPPORTED

WORKFLOW_SHA = "b" * 40
WORKFLOW_REF = "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
GIT_EXECUTABLE = shutil.which("git")


def _git_head(repository_root: Path) -> str:
    assert GIT_EXECUTABLE is not None
    return subprocess.check_output(  # noqa: S603
        [GIT_EXECUTABLE, "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
    ).strip()


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "init", "-q"], cwd=root, check=True
    )
    subprocess.run(  # noqa: S603
        [
            GIT_EXECUTABLE,
            "-c",
            "user.name=Quality Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    return root


def _consumer_retry_context(repository_root: Path) -> dict[str, str]:
    commit_sha = _git_head(repository_root)
    return {
        "repository": "example/university-ecosystem",
        "run_id": "123456789",
        "source_sha": commit_sha,
        "source_revision": commit_sha,
        "workflow_ref": WORKFLOW_REF,
        "workflow_sha": WORKFLOW_SHA,
        "event": "pull_request",
        "config_digest": "c" * 64,
        "policy_digest": "d" * 64,
    }


def _write_candidate(
    *,
    parent: Path,
    repository_root: Path,
    attempt: str,
    run_id: str = "123456789",
) -> Path:
    candidate = parent / f"{LIGHTHOUSE_LOGICAL_ARTIFACT}-attempt-{attempt}"
    candidate.mkdir(parents=True)
    reports: list[dict[str, object]] = []
    for report_index, specification in enumerate(expected_lighthouse_report_specs()):
        report = candidate / specification.path
        report.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                {
                    "finalUrl": f"https://example.test/{report_index}",
                    "requestedUrl": f"https://example.test/{report_index}",
                },
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        report.write_bytes(payload)
        reports.append(
            {
                "component": specification.component,
                "format": specification.report_format,
                "path": specification.path,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "byte_size": len(payload),
            }
        )
    metadata = {
        "schema_version": 2,
        "commit_sha": _git_head(repository_root),
        "collected_at": "2026-08-29T12:34:56Z",
        "producer": {
            "identity_provider": "github-actions",
            "repository": "example/university-ecosystem",
            "workflow_ref": WORKFLOW_REF,
            "workflow_sha": WORKFLOW_SHA,
            "run_id": run_id,
            "run_attempt": attempt,
            "event": "pull_request",
            "job": "lighthouse",
            "artifact": LIGHTHOUSE_LOGICAL_ARTIFACT,
        },
        "tool_versions": {"@lhci/cli": "0.15.1", "node": "24.0.0"},
        "reports": reports,
        "retry_provenance": {
            "repository": "example/university-ecosystem",
            "run_id": run_id,
            "run_attempt": attempt,
            "source_sha": _git_head(repository_root),
            "source_revision": _git_head(repository_root),
            "workflow_ref": WORKFLOW_REF,
            "workflow_sha": WORKFLOW_SHA,
            "event": "pull_request",
            "config_digest": "c" * 64,
            "policy_digest": "d" * 64,
            "artifact": LIGHTHOUSE_LOGICAL_ARTIFACT,
        },
    }
    metadata_path = candidate / LIGHTHOUSE_METADATA_PATH
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def _select(
    *,
    repository_root: Path,
    candidate_roots: list[Path],
    destination_root: Path,
) -> LighthouseSelectionResult:
    return select_lighthouse_artifacts(
        repository_root=repository_root,
        candidate_roots=candidate_roots,
        destination_root=destination_root,
        expected_sha=_git_head(repository_root),
        expected_repository="example/university-ecosystem",
        expected_run_id="123456789",
        expected_run_attempt="3",
        expected_workflow_ref=WORKFLOW_REF,
        expected_workflow_sha=WORKFLOW_SHA,
        expected_event="pull_request",
        expected_consumer_job="performance-gate",
        consumer_retry_context=_consumer_retry_context(repository_root),
    )


def test_expected_lighthouse_inventory_is_exact_and_immutable() -> None:
    reports = expected_lighthouse_report_specs()

    assert len(reports) == 30
    assert len({report.path for report in reports}) == 30
    assert [
        report.component for report in reports if report.component == "lighthouse-core"
    ] == ["lighthouse-core"] * 9
    assert [
        report.component
        for report in reports
        if report.component == "lighthouse-content"
    ] == ["lighthouse-content"] * 9
    assert [
        report.component
        for report in reports
        if report.component == "lighthouse-realtime"
    ] == ["lighthouse-realtime"] * 9
    assert [
        report.component
        for report in reports
        if report.component == "lighthouse-fallback"
    ] == ["lighthouse-fallback"] * 3
    assert [report.path for report in reports] == sorted(
        report.path for report in reports
    )
    assert all(report.report_format == "lighthouse-lhr-json" for report in reports)

    slot = lighthouse_artifact_slot()
    assert slot.logical_artifact == LIGHTHOUSE_LOGICAL_ARTIFACT
    assert slot.producer_job == "lighthouse"
    assert slot.metadata_path == LIGHTHOUSE_METADATA_PATH
    assert slot.reports == reports


def test_selects_highest_complete_attempt_and_writes_atomic_receipt(
    repository_root: Path, tmp_path: Path
) -> None:
    first = _write_candidate(
        parent=tmp_path / "first", repository_root=repository_root, attempt="1"
    )
    second = _write_candidate(
        parent=tmp_path / "second", repository_root=repository_root, attempt="2"
    )
    destination = repository_root / "artifacts/lighthouse-selection"

    result = _select(
        repository_root=repository_root,
        candidate_roots=[second, first],
        destination_root=destination,
    )

    assert result.selection.physical_artifact == "lighthouse-reports-attempt-2"
    assert result.selection.producer_attempt == 2
    assert result.reports_root == destination / LIGHTHOUSE_LOGICAL_ARTIFACT
    assert result.receipt_path == destination / "selection-receipt.json"
    assert len(list(result.reports_root.rglob("lhr-*.json"))) == 30
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 1
    assert receipt["selections"][0]["producer_attempt"] == 2
    assert receipt["selections"][0]["logical_artifact"] == LIGHTHOUSE_LOGICAL_ARTIFACT


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        pytest.param("foreign", "run_id", id="foreign"),
        pytest.param("future", "future", id="future"),
        pytest.param("duplicate", "duplicate producer attempt", id="duplicate"),
        pytest.param("malformed", "metadata", id="malformed"),
        pytest.param("malformed_lhr", "finalUrl", id="malformed-lhr"),
        pytest.param("incomplete", "missing expected members", id="incomplete"),
        pytest.param("tampered", "sha256", id="tampered"),
    ],
)
def test_rejects_every_invalid_candidate_fail_closed(
    repository_root: Path, tmp_path: Path, fault: str, message: str
) -> None:
    candidate = _write_candidate(
        parent=tmp_path / "valid", repository_root=repository_root, attempt="1"
    )
    candidates = [candidate]
    metadata_path = candidate / LIGHTHOUSE_METADATA_PATH
    if fault == "foreign":
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["producer"]["run_id"] = "987654321"
        metadata["retry_provenance"]["run_id"] = "987654321"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    elif fault == "future":
        candidate = _write_candidate(
            parent=tmp_path / "future", repository_root=repository_root, attempt="4"
        )
        candidates = [candidate]
    elif fault == "duplicate":
        candidates.append(
            _write_candidate(
                parent=tmp_path / "duplicate",
                repository_root=repository_root,
                attempt="1",
            )
        )
    elif fault == "malformed":
        metadata_path.write_text("{", encoding="utf-8")
    elif fault == "malformed_lhr":
        report = candidate / expected_lighthouse_report_specs()[0].path
        payload = b'{"finalUrl": ""}\n'
        report.write_bytes(payload)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for record in metadata["reports"]:
            if record["path"] == expected_lighthouse_report_specs()[0].path:
                record["sha256"] = hashlib.sha256(payload).hexdigest()
                record["byte_size"] = len(payload)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    elif fault == "incomplete":
        (candidate / expected_lighthouse_report_specs()[0].path).unlink()
    else:
        report = candidate / expected_lighthouse_report_specs()[0].path
        original = report.read_bytes()
        report.write_bytes(b"X" + original[1:])

    destination = repository_root / "artifacts/lighthouse-selection"
    with pytest.raises(LighthouseSelectionError, match=message):
        _select(
            repository_root=repository_root,
            candidate_roots=candidates,
            destination_root=destination,
        )

    assert not destination.exists()


def test_rejects_duplicate_and_nested_candidate_roots(
    repository_root: Path, tmp_path: Path
) -> None:
    candidate = _write_candidate(
        parent=tmp_path, repository_root=repository_root, attempt="1"
    )

    with pytest.raises(LighthouseSelectionError, match="duplicate root"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate, candidate],
            destination_root=repository_root / "artifacts/duplicate",
        )

    nested = candidate / "nested"
    nested.mkdir()
    with pytest.raises(LighthouseSelectionError, match="must not nest"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate, nested],
            destination_root=repository_root / "artifacts/nested",
        )


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable",
)
def test_rejects_candidate_and_repository_links_before_materialization(
    repository_root: Path, tmp_path: Path
) -> None:
    candidate = _write_candidate(
        parent=tmp_path, repository_root=repository_root, attempt="1"
    )
    candidate_alias = tmp_path / "candidate-alias"
    candidate_alias.symlink_to(candidate, target_is_directory=True)

    with pytest.raises(LighthouseSelectionError, match=r"symlink|junction"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate_alias],
            destination_root=repository_root / "artifacts/candidate-link",
        )

    repository_alias = tmp_path / "repository-alias"
    repository_alias.symlink_to(repository_root, target_is_directory=True)
    with pytest.raises(LighthouseSelectionError, match=r"symlink|junction"):
        _select(
            repository_root=repository_alias,
            candidate_roots=[candidate],
            destination_root=repository_root / "artifacts/repository-link",
        )
    (repository_root / "nested").mkdir()
    with pytest.raises(LighthouseSelectionError, match=r"traverses a symlink|junction"):
        lighthouse_selector._safe_repository_root(repository_alias / "nested")


def test_rejects_unexpected_members_and_preserves_atomic_destination(
    repository_root: Path, tmp_path: Path
) -> None:
    candidate = _write_candidate(
        parent=tmp_path, repository_root=repository_root, attempt="1"
    )
    (candidate / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    destination = repository_root / "artifacts/selection"

    with pytest.raises(LighthouseSelectionError, match="unexpected"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            destination_root=destination,
        )

    assert not destination.exists()


def test_rejects_unsafe_or_existing_destinations_before_selection(
    repository_root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    with pytest.raises(LighthouseSelectionError, match="stay inside"):
        _select(
            repository_root=repository_root,
            candidate_roots=[],
            destination_root=outside,
        )
    with pytest.raises(LighthouseSelectionError, match="unsafe"):
        _select(
            repository_root=repository_root,
            candidate_roots=[],
            destination_root=repository_root,
        )

    existing = repository_root / "artifacts/existing"
    existing.mkdir(parents=True)
    with pytest.raises(LighthouseSelectionError, match="must not already exist"):
        _select(
            repository_root=repository_root,
            candidate_roots=[],
            destination_root=existing,
        )

    parent_file = repository_root / "not-a-directory"
    parent_file.write_text("file\n", encoding="utf-8")
    with pytest.raises(LighthouseSelectionError, match="parent is not a directory"):
        _select(
            repository_root=repository_root,
            candidate_roots=[],
            destination_root=parent_file / "selection",
        )


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable",
)
def test_rejects_linked_destination_parent(
    repository_root: Path, tmp_path: Path
) -> None:
    linked_parent = repository_root / "artifacts"
    linked_parent.symlink_to(tmp_path, target_is_directory=True)

    with pytest.raises(LighthouseSelectionError, match=r"symlink|junction"):
        _select(
            repository_root=repository_root,
            candidate_roots=[],
            destination_root=linked_parent / "selection",
        )


def test_rejects_unavailable_or_non_directory_repository_root(tmp_path: Path) -> None:
    with pytest.raises(LighthouseSelectionError, match="unavailable"):
        lighthouse_selector._safe_repository_root(tmp_path / "missing")

    non_directory = tmp_path / "not-a-directory"
    non_directory.write_text("file\n", encoding="utf-8")
    with pytest.raises(LighthouseSelectionError, match="not a directory"):
        lighthouse_selector._safe_repository_root(non_directory)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        pytest.param("{", "unable to parse", id="invalid-json"),
        pytest.param("[]", "JSON object", id="array"),
        pytest.param('{"finalUrl": NaN}', "invalid JSON constant", id="constant"),
        pytest.param(
            '{"finalUrl": "https://example.test", "finalUrl": "https://other.test"}',
            "duplicate JSON key",
            id="duplicate-key",
        ),
    ],
)
def test_lhr_parser_rejects_malformed_json(
    payload: str, message: str, tmp_path: Path
) -> None:
    report = tmp_path / "lhr.json"
    report.write_text(payload, encoding="utf-8")

    with pytest.raises(LighthouseSelectionError, match=message):
        lighthouse_selector._validate_lhr(report)


def test_rejects_missing_materialized_lhr_root(tmp_path: Path) -> None:
    with pytest.raises(LighthouseSelectionError, match="reports root is unavailable"):
        lighthouse_selector._validate_materialized_lhrs(tmp_path / "missing")

    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    with pytest.raises(LighthouseSelectionError, match="LHR is unavailable"):
        lighthouse_selector._validate_materialized_lhrs(reports_root)


def test_removes_staged_materialization_when_copy_fails(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _write_candidate(
        parent=tmp_path, repository_root=repository_root, attempt="1"
    )
    destination = repository_root / "artifacts/lighthouse-selection"
    original_copyfile = shutil.copyfile
    calls = 0

    def fail_materialization_copy(
        source: Path, target: Path, *, follow_symlinks: bool = True
    ) -> str:
        nonlocal calls
        calls += 1
        if calls == len(expected_lighthouse_report_specs()) + 2:
            raise OSError("simulated copy failure")
        return str(original_copyfile(source, target, follow_symlinks=follow_symlinks))

    monkeypatch.setattr(shutil, "copyfile", fail_materialization_copy)

    with pytest.raises(OSError, match="simulated copy failure"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            destination_root=destination,
        )

    assert not destination.exists()
    assert not list(destination.parent.glob(f".{destination.name}.*"))


def test_wraps_generic_selector_failures_without_hiding_cause(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _write_candidate(
        parent=tmp_path, repository_root=repository_root, attempt="1"
    )

    def reject_selection(**_kwargs: object) -> None:
        raise coverage_selector.CoverageSelectionError("synthetic provenance fault")

    monkeypatch.setattr(
        lighthouse_selector, "select_coverage_artifacts", reject_selection
    )
    with pytest.raises(LighthouseSelectionError, match="synthetic provenance fault"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            destination_root=repository_root / "artifacts/selection",
        )


@pytest.mark.parametrize(
    ("result", "message"),
    [
        pytest.param(
            CoverageSelectionResult(selections=(), receipt_path=Path("receipt.json")),
            "exactly one Lighthouse artifact",
            id="empty-selection",
        ),
        pytest.param(
            CoverageSelectionResult(
                selections=(
                    CoverageArtifactSelection(
                        logical_artifact="unexpected-artifact",
                        physical_artifact="unexpected-artifact-attempt-1",
                        producer_attempt=1,
                        candidate_root=Path("candidate"),
                    ),
                ),
                receipt_path=Path("receipt.json"),
            ),
            "unexpected Lighthouse logical artifact",
            id="unexpected-logical-artifact",
        ),
    ],
)
def test_rejects_inconsistent_generic_selector_results(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: CoverageSelectionResult,
    message: str,
) -> None:
    candidate = _write_candidate(
        parent=tmp_path, repository_root=repository_root, attempt="1"
    )

    def return_inconsistent_result(**_kwargs: object) -> CoverageSelectionResult:
        return result

    monkeypatch.setattr(
        lighthouse_selector, "select_coverage_artifacts", return_inconsistent_result
    )
    with pytest.raises(LighthouseSelectionError, match=message):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            destination_root=repository_root / "artifacts/selection",
        )
