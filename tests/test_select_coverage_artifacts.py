from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import pytest

import scripts.quality.select_coverage_artifacts as coverage_selector
from scripts.quality.coverage_provenance import MetadataSelection
from scripts.quality.select_coverage_artifacts import (
    CoverageArtifactSlot,
    CoverageReportSpec,
    CoverageSelectionError,
    CoverageSelectionResult,
    select_coverage_artifacts,
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


def _slot(name: str) -> CoverageArtifactSlot:
    return CoverageArtifactSlot(
        logical_artifact=name,
        producer_job="unit-tests",
        metadata_path="coverage-provenance.json",
        reports=(
            CoverageReportSpec(
                component=name,
                report_format="coverage-py-data",
                path="coverage.xml",
            ),
        ),
    )


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
    slot: CoverageArtifactSlot,
    attempt: str,
    run_id: str = "123456789",
) -> Path:
    candidate = parent / f"{slot.logical_artifact}-attempt-{attempt}"
    candidate.mkdir(parents=True)
    reports: list[dict[str, object]] = []
    for specification in slot.reports:
        report = candidate / specification.path
        report.parent.mkdir(parents=True, exist_ok=True)
        payload = f"{slot.logical_artifact}:{attempt}:{specification.path}\n".encode()
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
            "job": slot.producer_job,
            "artifact": slot.logical_artifact,
        },
        "tool_versions": {"coverage.py": "7.10.0", "python": "3.14.0"},
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
            "artifact": slot.logical_artifact,
        },
    }
    metadata_path = candidate / slot.metadata_path
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def _select(
    *,
    repository_root: Path,
    candidate_roots: list[Path],
    slots: tuple[CoverageArtifactSlot, ...],
    destination_root: Path,
) -> CoverageSelectionResult:
    return select_coverage_artifacts(
        repository_root=repository_root,
        candidate_roots=candidate_roots,
        slots=slots,
        destination_root=destination_root,
        expected_sha=_git_head(repository_root),
        expected_repository="example/university-ecosystem",
        expected_run_id="123456789",
        expected_run_attempt="3",
        expected_workflow_ref=WORKFLOW_REF,
        expected_workflow_sha=WORKFLOW_SHA,
        expected_event="pull_request",
        expected_consumer_job="coverage-policy-gate",
        consumer_retry_context=_consumer_retry_context(repository_root),
    )


@pytest.mark.parametrize(
    ("slots", "message"),
    [
        pytest.param((), "at least one logical slot", id="empty"),
        pytest.param(
            (replace(_slot("python"), logical_artifact="bad/name"),),
            "path separator",
            id="logical-path",
        ),
        pytest.param(
            (replace(_slot("python"), logical_artifact="python\n"),),
            "forbidden control",
            id="logical-control",
        ),
        pytest.param(
            (replace(_slot("python"), logical_artifact=""),),
            "non-empty",
            id="logical-empty",
        ),
        pytest.param(
            (replace(_slot("python"), metadata_path="C:/metadata.json"),),
            "safe POSIX",
            id="windows-metadata-path",
        ),
        pytest.param(
            (replace(_slot("python"), metadata_path="../metadata.json"),),
            "safe POSIX",
            id="traversal-metadata-path",
        ),
        pytest.param(
            (replace(_slot("python"), reports=()),),
            "must not be empty",
            id="empty-reports",
        ),
        pytest.param(
            (
                replace(
                    _slot("python"),
                    reports=(_slot("python").reports[0], _slot("python").reports[0]),
                ),
            ),
            "duplicate report identity",
            id="duplicate-reports",
        ),
        pytest.param(
            (replace(_slot("python"), metadata_path="coverage.xml"),),
            "must not overlap",
            id="metadata-overlaps-report",
        ),
        pytest.param(
            (_slot("python"), _slot("python")),
            "duplicate logical slot",
            id="duplicate-slot",
        ),
    ],
)
def test_slot_definitions_reject_unsafe_or_ambiguous_contracts(
    slots: tuple[CoverageArtifactSlot, ...], message: str
) -> None:
    with pytest.raises(CoverageSelectionError, match=message):
        coverage_selector._validate_slots(slots)


@pytest.mark.parametrize("logical_artifact", (".", ".."))
def test_reserved_logical_artifact_is_rejected_before_destination_write(
    repository_root: Path, logical_artifact: str
) -> None:
    destination = repository_root / "artifacts/reserved-logical-artifact"
    slot = replace(_slot("python-shard-0"), logical_artifact=logical_artifact)

    with pytest.raises(CoverageSelectionError, match="reserved logical artifact"):
        _select(
            repository_root=repository_root,
            candidate_roots=[],
            slots=(slot,),
            destination_root=destination,
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    "logical_artifact",
    (
        "lighthouse:reports",
        "con",
        "con.txt",
        "lighthouse.",
        "lighthouse ",
        ".lighthouse",
        "_lighthouse",
        "-lighthouse",
        "lighthouse_",
        "lighthouse-",
        "Lighthouse",
        "université",
    ),
)
def test_logical_artifact_requires_a_portable_safe_slug(
    logical_artifact: str,
) -> None:
    slot = replace(_slot("python-shard-0"), logical_artifact=logical_artifact)

    with pytest.raises(CoverageSelectionError, match="portable safe slug"):
        coverage_selector._validate_slots((slot,))


def test_logical_artifact_casefold_collisions_are_not_allowed() -> None:
    lowercase = _slot("python-shard-0")
    uppercase = _slot("PYTHON-SHARD-0")

    with pytest.raises(
        CoverageSelectionError,
        match=r"portable safe slug|case-insensitive duplicate logical slot",
    ):
        coverage_selector._validate_slots((lowercase, uppercase))


def test_logical_artifact_accepts_a_portable_safe_slug() -> None:
    slot = replace(_slot("python-shard-0"), logical_artifact="a1.b_c-d2")

    assert coverage_selector._validate_slots((slot,)) == (slot,)


def test_candidate_metadata_parser_rejects_noncanonical_json(tmp_path: Path) -> None:
    metadata = tmp_path / "coverage-provenance.json"
    for payload, message in (
        (b'{"reports": [], "reports": []}', "duplicate JSON key"),
        (b'{"reports": NaN}', "invalid JSON constant"),
        (b"[]", "must be a JSON object"),
        (b"\xff", "unable to read candidate metadata"),
    ):
        metadata.write_bytes(payload)
        with pytest.raises(CoverageSelectionError, match=message):
            coverage_selector._load_candidate_metadata(metadata)


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable",
)
def test_candidate_root_and_member_paths_reject_links_and_non_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    root.mkdir()
    with pytest.raises(CoverageSelectionError, match="unavailable"):
        coverage_selector._safe_candidate_root(tmp_path / "missing")
    file_root = tmp_path / "file-root"
    file_root.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(CoverageSelectionError, match="not a directory"):
        coverage_selector._safe_candidate_root(file_root)

    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(root, target_is_directory=True)
    with pytest.raises(CoverageSelectionError, match=r"symlink|junction"):
        coverage_selector._safe_candidate_root(linked_root)
    nested_alias = tmp_path / "nested-alias"
    nested_alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(CoverageSelectionError, match="traverses"):
        coverage_selector._safe_candidate_root(nested_alias / "candidate")

    with pytest.raises(CoverageSelectionError, match="regular file"):
        coverage_selector._safe_file(root, "missing.txt", "test member")
    empty = root / "empty.txt"
    empty.touch()
    with pytest.raises(CoverageSelectionError, match="non-empty"):
        coverage_selector._safe_file(root, "empty.txt", "test member")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "report.txt").write_text("report\n", encoding="utf-8")
    alias = root / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(CoverageSelectionError, match=r"symlink|junction"):
        coverage_selector._safe_file(root, "alias/report.txt", "test member")


def test_candidate_member_rejects_an_absolute_escape(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    root.mkdir()

    with pytest.raises(CoverageSelectionError, match="escapes"):
        coverage_selector._safe_file(root, "/outside.txt", "test member")


def test_candidate_inventory_rejects_regular_file_hardlinks(
    repository_root: Path, tmp_path: Path
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    report = candidate / "coverage.xml"
    outside = tmp_path / "hardlink-source.xml"
    outside.write_bytes(report.read_bytes())
    report.unlink()
    try:
        os.link(outside, report)
    except OSError as error:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"hardlink creation is unavailable: {error}"
        )

    with pytest.raises(CoverageSelectionError, match=r"hard link|link count|nlink"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/hardlink-candidate",
        )


def test_candidate_inventory_rejects_missing_and_uninspectable_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = _slot("python-shard-0")
    root = tmp_path / "python-shard-0-attempt-1"
    root.mkdir()
    (root / slot.metadata_path).write_text("metadata\n", encoding="utf-8")

    with pytest.raises(CoverageSelectionError, match="missing expected members"):
        coverage_selector._candidate_inventory(root, slot)

    def fail_rglob(_path: Path, _pattern: str) -> NoReturn:
        raise OSError("simulated traversal failure")

    monkeypatch.setattr(Path, "rglob", fail_rglob)
    with pytest.raises(CoverageSelectionError, match="unable to inspect"):
        coverage_selector._candidate_inventory(root, slot)


def test_candidate_inventory_rejects_non_regular_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = _slot("python-shard-0")
    root = tmp_path / "python-shard-0-attempt-1"
    root.mkdir()
    for path in (root / slot.metadata_path, root / "coverage.xml"):
        path.write_text("coverage\n", encoding="utf-8")
    original_is_file = Path.is_file

    def non_regular(path: Path) -> bool:
        if path.name == "coverage.xml":
            return False
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", non_regular)
    with pytest.raises(CoverageSelectionError, match="non-regular"):
        coverage_selector._candidate_inventory(root, slot)


@pytest.mark.parametrize(
    ("reports", "message"),
    [
        ({}, "reports must be an array"),
        ([[]], r"reports\[0\] must be an object"),
        ([{}], "is incomplete"),
        (
            [
                {
                    "component": "wrong",
                    "format": "coverage-py-data",
                    "path": "coverage.xml",
                    "sha256": "0" * 64,
                    "byte_size": 1,
                }
            ],
            "does not match slot",
        ),
        (
            [
                {
                    "component": "python-shard-0",
                    "format": "coverage-py-data",
                    "path": "coverage.xml",
                    "sha256": "invalid",
                    "byte_size": 1,
                }
            ],
            "lowercase SHA-256",
        ),
        (
            [
                {
                    "component": "python-shard-0",
                    "format": "coverage-py-data",
                    "path": "coverage.xml",
                    "sha256": "0" * 64,
                    "byte_size": 0,
                }
            ],
            "byte_size must be positive",
        ),
    ],
)
def test_candidate_metadata_rejects_wrong_report_contract(
    repository_root: Path,
    tmp_path: Path,
    reports: object,
    message: str,
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    payload = json.loads((candidate / slot.metadata_path).read_text(encoding="utf-8"))
    payload["reports"] = reports
    (candidate / slot.metadata_path).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CoverageSelectionError, match=message):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/invalid-reports",
        )


def test_rejects_invalid_physical_names_nested_or_duplicate_candidate_roots(
    repository_root: Path, tmp_path: Path
) -> None:
    slot = _slot("python-shard-0")
    invalid_name = tmp_path / "python-shard-0-attempt-invalid"
    invalid_name.mkdir()
    with pytest.raises(CoverageSelectionError, match="bind exactly one"):
        _select(
            repository_root=repository_root,
            candidate_roots=[invalid_name],
            slots=(slot,),
            destination_root=repository_root / "artifacts/invalid-name",
        )

    unknown = tmp_path / "unknown-attempt-1"
    unknown.mkdir()
    with pytest.raises(CoverageSelectionError, match="bind exactly one"):
        _select(
            repository_root=repository_root,
            candidate_roots=[unknown],
            slots=(slot,),
            destination_root=repository_root / "artifacts/unknown-name",
        )

    candidate = _write_candidate(
        parent=tmp_path / "duplicate",
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    with pytest.raises(CoverageSelectionError, match="duplicate root"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate, candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/duplicate-root",
        )

    nested = candidate / "nested"
    nested.mkdir()
    with pytest.raises(CoverageSelectionError, match="must not nest"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate, nested],
            slots=(slot,),
            destination_root=repository_root / "artifacts/nested-root",
        )


def test_supports_nested_report_paths_and_rejects_existing_destination(
    repository_root: Path, tmp_path: Path
) -> None:
    slot = CoverageArtifactSlot(
        logical_artifact="python-shard-0",
        producer_job="unit-tests",
        metadata_path="provenance/coverage.json",
        reports=(
            CoverageReportSpec(
                component="python-shard-0",
                report_format="coverage-py-data",
                path="reports/coverage.xml",
            ),
        ),
    )
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    destination = repository_root / "artifacts/nested-selection"
    _select(
        repository_root=repository_root,
        candidate_roots=[candidate],
        slots=(slot,),
        destination_root=destination,
    )
    assert (destination / "python-shard-0/reports/coverage.xml").is_file()

    with pytest.raises(CoverageSelectionError, match="must not already exist"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=destination,
        )


def test_destination_path_rejects_escape_and_workspace_metadata(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outside = tmp_path / "outside"

    with pytest.raises(CoverageSelectionError, match="stay inside"):
        coverage_selector._safe_destination(repository_root, outside)
    with pytest.raises(CoverageSelectionError, match="unsafe"):
        coverage_selector._safe_destination(repository_root, repository_root)
    with pytest.raises(CoverageSelectionError, match="unsafe"):
        coverage_selector._safe_destination(repository_root, repository_root / ".git/x")


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable",
)
def test_repository_and_destination_path_reject_links(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    (repository_root / "nested").mkdir()
    alias = tmp_path / "repository-alias"
    alias.symlink_to(repository_root, target_is_directory=True)
    with pytest.raises(CoverageSelectionError, match=r"symlink|junction"):
        coverage_selector._validation_root(alias)
    with pytest.raises(CoverageSelectionError, match=r"symlink|junction"):
        coverage_selector._validation_root(alias / "nested")

    linked_destination_parent = repository_root / "artifacts"
    linked_destination_parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(CoverageSelectionError, match=r"symlink|junction"):
        coverage_selector._safe_destination(
            repository_root, linked_destination_parent / "selection"
        )


def test_validation_root_rejects_unavailable_or_non_directory(tmp_path: Path) -> None:
    with pytest.raises(CoverageSelectionError, match="unavailable"):
        coverage_selector._validation_root(tmp_path / "missing")
    not_directory = tmp_path / "not-directory"
    not_directory.write_text("file\n", encoding="utf-8")
    with pytest.raises(CoverageSelectionError, match="not a directory"):
        coverage_selector._validation_root(not_directory)


def test_atomic_json_write_cleans_temporary_file_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "receipt.json"
    output.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        coverage_selector._atomic_write_json(output, {"new": True})

    assert json.loads(output.read_text(encoding="utf-8")) == {"old": True}
    assert not list(tmp_path.glob(".receipt.json.*.tmp"))


def test_atomic_json_write_tolerates_concurrent_temporary_file_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "receipt.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated replace failure")

    original_unlink = Path.unlink

    def unlink_then_report_missing(path: Path, missing_ok: bool = False) -> None:
        original_unlink(path, missing_ok=missing_ok)
        raise FileNotFoundError(path)

    monkeypatch.setattr(os, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", unlink_then_report_missing)

    with pytest.raises(OSError, match="simulated replace failure"):
        coverage_selector._atomic_write_json(output, {"new": True})

    assert not list(tmp_path.glob(".receipt.json.*.tmp"))


def test_projected_metadata_requires_report_objects() -> None:
    with pytest.raises(CoverageSelectionError, match="reports must be an array"):
        coverage_selector._project_metadata({"reports": {}}, "candidate")
    with pytest.raises(CoverageSelectionError, match=r"reports\[0\] must be an object"):
        coverage_selector._project_metadata({"reports": [[]]}, "candidate")


def test_requires_at_least_one_candidate_root(
    repository_root: Path,
) -> None:
    with pytest.raises(CoverageSelectionError, match="at least one root"):
        _select(
            repository_root=repository_root,
            candidate_roots=[],
            slots=(_slot("python-shard-0"),),
            destination_root=repository_root / "artifacts/selection",
        )


def test_rejects_selector_result_outside_the_private_validation_root(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )

    def select_foreign_metadata(**_kwargs: object) -> MetadataSelection:
        return MetadataSelection(
            metadata_path=repository_root / "foreign-coverage-provenance.json",
            manifest={},
            producer_attempt=1,
        )

    monkeypatch.setattr(
        coverage_selector, "select_metadata_candidates", select_foreign_metadata
    )
    with pytest.raises(CoverageSelectionError, match="outside validation root"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/selection",
        )


def test_rejects_metadata_attempt_that_does_not_match_physical_artifact_name(
    repository_root: Path, tmp_path: Path
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    metadata_path = candidate / slot.metadata_path
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["producer"]["run_attempt"] = "2"
    metadata["retry_provenance"]["run_attempt"] = "2"
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(CoverageSelectionError, match="does not bind"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/selection",
        )


def test_rejects_attempt_mismatch_in_nonselected_candidate(
    repository_root: Path, tmp_path: Path
) -> None:
    slot = _slot("python-shard-0")
    highest_valid = _write_candidate(
        parent=tmp_path / "highest-valid",
        repository_root=repository_root,
        slot=slot,
        attempt="3",
    )
    mismatched_lower = _write_candidate(
        parent=tmp_path / "mismatched-lower",
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    metadata_path = mismatched_lower / slot.metadata_path
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["producer"]["run_attempt"] = "2"
    metadata["retry_provenance"]["run_attempt"] = "2"
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
    )
    destination = repository_root / "artifacts/nonselected-attempt-mismatch"

    with pytest.raises(CoverageSelectionError, match="does not bind"):
        _select(
            repository_root=repository_root,
            candidate_roots=[highest_valid, mismatched_lower],
            slots=(slot,),
            destination_root=destination,
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    ("producer", "message"),
    [
        pytest.param([], "producer must be an object", id="non-object"),
        pytest.param(
            {"run_attempt": "invalid"},
            "producer missing fields",
            id="incomplete",
        ),
    ],
)
def test_defers_malformed_producer_to_shared_provenance_validator(
    repository_root: Path,
    tmp_path: Path,
    producer: object,
    message: str,
) -> None:
    """Early suffix binding must not mask the canonical schema diagnostic."""

    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    metadata_path = candidate / slot.metadata_path
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["producer"] = producer
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
    )
    destination = repository_root / "artifacts/malformed-producer"

    with pytest.raises(CoverageSelectionError, match=message):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=destination,
        )

    assert not destination.exists()


def test_selects_complete_slots_deterministically_and_writes_receipt(
    repository_root: Path, tmp_path: Path
) -> None:
    first_slot = _slot("python-shard-0")
    second_slot = _slot("python-shard-1")
    candidates = [
        _write_candidate(
            parent=tmp_path / "first",
            repository_root=repository_root,
            slot=first_slot,
            attempt="1",
        ),
        _write_candidate(
            parent=tmp_path / "second",
            repository_root=repository_root,
            slot=first_slot,
            attempt="2",
        ),
        _write_candidate(
            parent=tmp_path / "third",
            repository_root=repository_root,
            slot=second_slot,
            attempt="1",
        ),
    ]
    first_destination = repository_root / "artifacts/selection-first"
    second_destination = repository_root / "artifacts/selection-second"

    first = _select(
        repository_root=repository_root,
        candidate_roots=candidates,
        slots=(first_slot, second_slot),
        destination_root=first_destination,
    )
    second = _select(
        repository_root=repository_root,
        candidate_roots=list(reversed(candidates)),
        slots=(first_slot, second_slot),
        destination_root=second_destination,
    )

    assert [item.producer_attempt for item in first.selections] == [2, 1]
    assert first.selections == second.selections
    assert (
        first_destination / "python-shard-0/coverage.xml"
    ).read_bytes() == b"python-shard-0:2:coverage.xml\n"
    receipt = json.loads(
        (first_destination / "selection-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["schema_version"] == 1
    assert receipt["consumer"]["job"] == "coverage-policy-gate"
    assert [entry["logical_artifact"] for entry in receipt["selections"]] == [
        "python-shard-0",
        "python-shard-1",
    ]
    assert receipt["selections"][0]["producer_attempt"] == 2
    assert receipt == json.loads(
        (second_destination / "selection-receipt.json").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("replacement", "message"),
    (
        (b"tampered after validation\n", "byte_size"),
        (None, "sha256"),
    ),
)
def test_materialization_rechecks_copied_report_integrity(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bytes | None,
    message: str,
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    original_copy = coverage_selector._copy_regular_file

    def replace_source_before_copy(source: Path, target: Path) -> None:
        if source != candidate / "coverage.xml":
            source.write_bytes(replacement or b"x" * len(source.read_bytes()))
        original_copy(source, target)

    monkeypatch.setattr(
        coverage_selector, "_copy_regular_file", replace_source_before_copy
    )
    destination = repository_root / "artifacts/tampered-materialization"

    with pytest.raises(CoverageSelectionError, match=f"materialized report.*{message}"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=destination,
        )

    assert not destination.exists()


def test_rejects_incomplete_logical_slots_without_materializing(
    repository_root: Path, tmp_path: Path
) -> None:
    first_slot = _slot("python-shard-0")
    second_slot = _slot("python-shard-1")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=first_slot,
        attempt="1",
    )
    destination = repository_root / "artifacts/selection"

    with pytest.raises(CoverageSelectionError, match="missing logical slots"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(first_slot, second_slot),
            destination_root=destination,
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("foreign", "run_id"),
        ("future", "future"),
        ("duplicate", "duplicate producer attempt"),
        ("malformed", "metadata"),
        ("tampered", "sha256"),
    ],
)
def test_rejects_any_invalid_candidate_fail_closed(
    repository_root: Path, tmp_path: Path, fault: str, message: str
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path / "valid",
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    candidates = [candidate]
    if fault == "foreign":
        payload = json.loads(
            (candidate / slot.metadata_path).read_text(encoding="utf-8")
        )
        payload["producer"]["run_id"] = "987654321"
        payload["retry_provenance"]["run_id"] = "987654321"
        (candidate / slot.metadata_path).write_text(
            json.dumps(payload), encoding="utf-8"
        )
    elif fault == "future":
        candidate = _write_candidate(
            parent=tmp_path / "future",
            repository_root=repository_root,
            slot=slot,
            attempt="4",
        )
        candidates = [candidate]
    elif fault == "duplicate":
        candidates.append(
            _write_candidate(
                parent=tmp_path / "duplicate",
                repository_root=repository_root,
                slot=slot,
                attempt="1",
            )
        )
    elif fault == "malformed":
        (candidate / slot.metadata_path).write_text("{", encoding="utf-8")
    else:
        original = (candidate / "coverage.xml").read_bytes()
        (candidate / "coverage.xml").write_bytes(b"X" + original[1:])

    destination = repository_root / "artifacts/selection"
    with pytest.raises(CoverageSelectionError, match=message):
        _select(
            repository_root=repository_root,
            candidate_roots=candidates,
            slots=(slot,),
            destination_root=destination,
        )

    assert not destination.exists()


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable",
)
def test_rejects_unexpected_or_linked_candidate_members(
    repository_root: Path, tmp_path: Path
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    (candidate / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(CoverageSelectionError, match="unexpected"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/selection-extra",
        )

    (candidate / "unexpected.txt").unlink()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "coverage.xml").write_text("coverage\n", encoding="utf-8")
    (candidate / "coverage.xml").unlink()
    (candidate / "coverage.xml").symlink_to(outside / "coverage.xml")

    with pytest.raises(CoverageSelectionError, match=r"symlink|junction"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/selection-linked",
        )


def test_rejects_unexpected_empty_candidate_directory(
    repository_root: Path, tmp_path: Path
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    (candidate / "unexpected").mkdir()

    with pytest.raises(CoverageSelectionError, match="unexpected"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=repository_root / "artifacts/selection-empty-directory",
        )


def test_materialization_is_atomic_when_copy_fails(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = _slot("python-shard-0")
    candidate = _write_candidate(
        parent=tmp_path,
        repository_root=repository_root,
        slot=slot,
        attempt="1",
    )
    destination = repository_root / "artifacts/selection"
    original_copyfile = shutil.copyfile
    calls = 0

    def fail_materialization_copy(
        source: Path, target: Path, *, follow_symlinks: bool = True
    ) -> str:
        nonlocal calls
        calls += 1
        # The first two copies populate the private validation directory;
        # failing the next one exercises the atomic materialization phase.
        if calls == 3:
            raise OSError("simulated copy failure")
        return str(original_copyfile(source, target, follow_symlinks=follow_symlinks))

    monkeypatch.setattr(shutil, "copyfile", fail_materialization_copy)

    with pytest.raises(OSError, match="simulated copy failure"):
        _select(
            repository_root=repository_root,
            candidate_roots=[candidate],
            slots=(slot,),
            destination_root=destination,
        )

    assert not destination.exists()
    assert not list(destination.parent.glob(f".{destination.name}.*"))
