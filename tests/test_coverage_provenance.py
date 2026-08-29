from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import scripts.quality.coverage_provenance as coverage_provenance
from scripts.quality.coverage_provenance import (
    ProvenanceError,
    merge_metadata,
    verify_metadata,
    write_metadata,
)
from tests.symlink_support import DIRECTORY_SYMLINKS_SUPPORTED

COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"  # pragma: allowlist secret
WORKFLOW_SHA = "89abcdef0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
COLLECTED_AT = "2026-08-25T12:34:56Z"
GIT_EXECUTABLE = shutil.which("git")


def _git_head(repository_root: Path) -> str:
    assert GIT_EXECUTABLE is not None
    return subprocess.check_output(  # noqa: S603
        [GIT_EXECUTABLE, "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
    ).strip()


@pytest.fixture
def provenance_repository(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "init", "-q"], cwd=tmp_path, check=True
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
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def _identity(repository_root: Path, **overrides: str) -> dict[str, str]:
    values = {
        "expected_sha": _git_head(repository_root),
        "identity_provider": "github-actions",
        "repository": "example/university-ecosystem",
        "workflow_ref": (
            "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
        "workflow_sha": WORKFLOW_SHA,
        "run_id": "123456789",
        "run_attempt": "2",
        "event": "push",
        "job": "coverage-policy-gate",
        "artifact": "python-coverage-provenance",
        "collected_at": COLLECTED_AT,
    }
    values.update(overrides)
    return values


def _retry_provenance(
    repository_root: Path,
    *,
    run_attempt: str = "2",
    run_id: str = "123456789",
    artifact: str = "python-coverage-provenance",
) -> dict[str, str]:
    return {
        "repository": "example/university-ecosystem",
        "run_id": run_id,
        "source_sha": _git_head(repository_root),
        "source_revision": _git_head(repository_root),
        "workflow_ref": (
            "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
        "workflow_sha": WORKFLOW_SHA,
        "event": "push",
        "config_digest": "a" * 64,
        "policy_digest": "b" * 64,
        "artifact": artifact,
        "run_attempt": run_attempt,
    }


def _consumer_retry_context(repository_root: Path) -> dict[str, str]:
    return {
        name: value
        for name, value in _retry_provenance(repository_root, run_attempt="1").items()
        if name not in {"run_attempt", "artifact"}
    }


def _write_report(repository_root: Path, relative_path: str, payload: bytes) -> Path:
    report_path = repository_root / relative_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(payload)
    return report_path


def _write_one_metadata(
    repository_root: Path,
    *,
    report_path: str = "coverage.xml",
    component: str = "python",
    report_format: str = "cobertura-xml",
    metadata_path: str = "artifacts/coverage/provenance/python.json",
    tool_versions: dict[str, str] | None = None,
    **identity_overrides: str,
) -> Path:
    _write_report(repository_root, report_path, b"coverage-evidence\n")
    output_path = repository_root / metadata_path
    write_metadata(
        repository_root=repository_root,
        output_path=output_path,
        reports=[(component, report_format, report_path, report_path)],
        tool_versions=tool_versions or {"coverage.py": "7.10.0", "python": "3.14.0"},
        **_identity(repository_root, **identity_overrides),
    )
    return output_path


def _write_retry_candidate(
    repository_root: Path,
    *,
    metadata_path: str,
    run_attempt: str,
    run_id: str = "123456789",
    job: str = "coverage-policy-gate",
    artifact: str = "python-coverage-provenance",
) -> Path:
    _write_report(repository_root, "coverage.xml", b"coverage-evidence\n")
    output_path = repository_root / metadata_path
    write_metadata(
        repository_root=repository_root,
        output_path=output_path,
        reports=[("python", "cobertura-xml", "coverage.xml", "coverage.xml")],
        tool_versions={"coverage.py": "7.10.0", "python": "3.14.0"},
        retry_provenance=_retry_provenance(
            repository_root,
            run_attempt=run_attempt,
            run_id=run_id,
            artifact=artifact,
        ),
        **_identity(
            repository_root,
            run_attempt=run_attempt,
            run_id=run_id,
            job=job,
            artifact=artifact,
        ),
    )
    return output_path


def test_write_metadata_records_closed_current_run_evidence(
    provenance_repository: Path,
) -> None:
    metadata_path = _write_one_metadata(provenance_repository)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert set(metadata) == {
        "schema_version",
        "commit_sha",
        "collected_at",
        "producer",
        "tool_versions",
        "reports",
    }
    assert metadata["schema_version"] == 2
    assert metadata["commit_sha"] == _git_head(provenance_repository)
    assert metadata["collected_at"] == COLLECTED_AT
    assert metadata["tool_versions"] == {
        "coverage.py": "7.10.0",
        "python": "3.14.0",
    }
    assert set(metadata["producer"]) == {
        "identity_provider",
        "repository",
        "workflow_ref",
        "workflow_sha",
        "run_id",
        "run_attempt",
        "event",
        "job",
        "artifact",
    }
    assert metadata["producer"]["run_id"] == "123456789"
    assert metadata["reports"] == [
        {
            "component": "python",
            "format": "cobertura-xml",
            "path": "coverage.xml",
            "sha256": hashlib.sha256(b"coverage-evidence\n").hexdigest(),
            "byte_size": len(b"coverage-evidence\n"),
        }
    ]


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("absolute", "relative"),
        ("traversal", "relative"),
        ("empty", "non-empty"),
        ("sha", "HEAD"),
        ("run", "run_id"),
        ("duplicate", "duplicate"),
    ],
)
def test_write_metadata_fails_closed_for_invalid_inputs(
    provenance_repository: Path,
    fault: str,
    message: str,
) -> None:
    report_path = "coverage.xml"
    payload = b"coverage-evidence\n"
    if fault == "absolute":
        report_path = str((provenance_repository / report_path).resolve())
    elif fault == "traversal":
        report_path = "../coverage.xml"
    elif fault == "empty":
        payload = b""
    _write_report(provenance_repository, "coverage.xml", payload)
    reports = [("python", "cobertura-xml", report_path, "coverage.xml")]
    if fault == "duplicate":
        reports *= 2
    identity = _identity(provenance_repository)
    if fault == "sha":
        identity["expected_sha"] = COMMIT_SHA
    elif fault == "run":
        identity["run_id"] = "not-a-run"

    with pytest.raises(ProvenanceError, match=message):
        write_metadata(
            repository_root=provenance_repository,
            output_path=provenance_repository / "metadata.json",
            reports=reports,
            tool_versions={"coverage.py": "7.10.0"},
            **identity,
        )


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable",
)
def test_write_metadata_rejects_report_through_symlinked_ancestor(
    provenance_repository: Path,
) -> None:
    outside = provenance_repository.with_name(f"{provenance_repository.name}-outside")
    outside.mkdir()
    alias = provenance_repository / "artifacts"
    alias.symlink_to(outside, target_is_directory=True)
    (outside / "coverage.xml").write_bytes(b"coverage\n")

    with pytest.raises(ProvenanceError, match="symlink"):
        write_metadata(
            repository_root=provenance_repository,
            output_path=provenance_repository / "metadata.json",
            reports=[
                (
                    "python",
                    "cobertura-xml",
                    "artifacts/coverage.xml",
                    "artifacts/coverage.xml",
                )
            ],
            tool_versions={"coverage.py": "7.10.0"},
            **_identity(provenance_repository),
        )


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("hash", "sha256"),
        ("size", "byte_size"),
        ("empty", "non-empty"),
        ("sha", "commit_sha"),
        ("run", "run_id"),
        ("extra", "unexpected"),
        ("empty_registry", "at least one"),
    ],
)
def test_verify_metadata_recomputes_and_closes_evidence(
    provenance_repository: Path,
    fault: str,
    message: str,
) -> None:
    metadata_path = _write_one_metadata(provenance_repository)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if fault == "hash":
        metadata["reports"][0]["sha256"] = "0" * 64
    elif fault == "size":
        metadata["reports"][0]["byte_size"] += 1
    elif fault == "empty":
        (provenance_repository / "coverage.xml").write_bytes(b"")
    elif fault == "sha":
        metadata["commit_sha"] = COMMIT_SHA
    elif fault == "run":
        metadata["producer"]["run_id"] = "987654321"
    elif fault == "empty_registry":
        metadata["reports"] = []
    else:
        metadata["unexpected"] = True
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=message):
        verify_metadata(
            repository_root=provenance_repository,
            metadata_paths=[metadata_path],
            expected_sha=_git_head(provenance_repository),
            expected_repository="example/university-ecosystem",
            expected_run_id="123456789",
            expected_run_attempt="2",
            expected_job="coverage-policy-gate",
            expected_artifact="python-coverage-provenance",
        )


@pytest.mark.parametrize(
    ("field", "mutated", "message"),
    [
        ("job", "stale-producer-job", "producer.job"),
        ("artifact", "stale-producer-artifact", "producer.artifact"),
    ],
)
def test_verify_metadata_rejects_wrong_producer_identity(
    provenance_repository: Path,
    field: str,
    mutated: str,
    message: str,
) -> None:
    metadata_path = _write_one_metadata(provenance_repository)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["producer"][field] = mutated
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=message):
        verify_metadata(
            repository_root=provenance_repository,
            metadata_paths=[metadata_path],
            expected_sha=_git_head(provenance_repository),
            expected_repository="example/university-ecosystem",
            expected_run_id="123456789",
            expected_run_attempt="2",
            expected_job="coverage-policy-gate",
            expected_artifact="python-coverage-provenance",
        )


def test_merge_metadata_requires_exact_canonical_report_registry_once(
    provenance_repository: Path,
) -> None:
    contract = {
        "coverage_reports": [
            {
                "component": "python",
                "format": "cobertura-xml",
                "path": "coverage.xml",
            },
            {
                "component": "frontend",
                "format": "lcov",
                "path": "frontend/coverage/lcov.info",
            },
        ]
    }
    contract_path = provenance_repository / "quality/quality-contract.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    python_metadata = _write_one_metadata(provenance_repository)
    frontend_metadata = _write_one_metadata(
        provenance_repository,
        report_path="frontend/coverage/lcov.info",
        component="frontend",
        report_format="lcov",
        metadata_path="artifacts/coverage/provenance/frontend.json",
        tool_versions={"node": "24.7.0", "vitest": "4.0.0"},
        job="frontend-tests",
        artifact="frontend-coverage",
    )
    output_path = provenance_repository / "artifacts/coverage/provenance/aggregate.json"

    merge_metadata(
        repository_root=provenance_repository,
        contract_path=contract_path,
        metadata_paths=[python_metadata, frontend_metadata],
        output_path=output_path,
        tool_versions={"quality-provenance": "2.0.0"},
        producer_expectations={
            python_metadata: ("coverage-policy-gate", "python-coverage-provenance"),
            frontend_metadata: ("frontend-tests", "frontend-coverage"),
        },
        **_identity(
            provenance_repository,
            artifact=f"quality-evidence-{_git_head(provenance_repository)}",
        ),
    )

    aggregate = json.loads(output_path.read_text(encoding="utf-8"))
    assert [report["path"] for report in aggregate["reports"]] == [
        "coverage.xml",
        "frontend/coverage/lcov.info",
    ]
    assert aggregate["producer"]["artifact"].startswith("quality-evidence-")
    assert aggregate["tool_versions"] == {
        "coverage.py": "7.10.0",
        "node": "24.7.0",
        "python": "3.14.0",
        "quality-provenance": "2.0.0",
        "vitest": "4.0.0",
    }


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unexpected"])
def test_merge_metadata_rejects_wrong_report_cardinality(
    provenance_repository: Path,
    fault: str,
) -> None:
    contract = {
        "coverage_reports": [
            {
                "component": "python",
                "format": "cobertura-xml",
                "path": "coverage.xml",
            }
        ]
    }
    contract_path = provenance_repository / "quality/quality-contract.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    metadata_path = _write_one_metadata(provenance_repository)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if fault == "missing":
        metadata["reports"] = []
    elif fault == "duplicate":
        metadata["reports"].append(copy.deepcopy(metadata["reports"][0]))
    else:
        extra_path = _write_report(provenance_repository, "extra.xml", b"extra\n")
        metadata["reports"].append(
            {
                "component": "python",
                "format": "cobertura-xml",
                "path": extra_path.relative_to(provenance_repository).as_posix(),
                "sha256": hashlib.sha256(b"extra\n").hexdigest(),
                "byte_size": len(b"extra\n"),
            }
        )
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ProvenanceError, match="report"):
        merge_metadata(
            repository_root=provenance_repository,
            contract_path=contract_path,
            metadata_paths=[metadata_path],
            output_path=provenance_repository / "aggregate.json",
            tool_versions={"quality-provenance": "2.0.0"},
            producer_expectations={
                metadata_path: (
                    "coverage-policy-gate",
                    "python-coverage-provenance",
                )
            },
            **_identity(provenance_repository, artifact="quality-evidence-test"),
        )


def test_merge_metadata_rejects_mutated_producer_expectation(
    provenance_repository: Path,
) -> None:
    contract_path = provenance_repository / "quality/quality-contract.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        json.dumps(
            {
                "coverage_reports": [
                    {
                        "component": "python",
                        "format": "cobertura-xml",
                        "path": "coverage.xml",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    metadata_path = _write_one_metadata(provenance_repository)

    with pytest.raises(ProvenanceError, match=r"producer\.artifact"):
        merge_metadata(
            repository_root=provenance_repository,
            contract_path=contract_path,
            metadata_paths=[metadata_path],
            output_path=provenance_repository / "aggregate.json",
            tool_versions={"quality-provenance": "2.0.0"},
            producer_expectations={
                metadata_path: ("coverage-policy-gate", "wrong-artifact")
            },
            **_identity(provenance_repository, artifact="quality-evidence-test"),
        )


def test_metadata_write_is_atomic_and_does_not_leave_partial_file(
    provenance_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _write_report(provenance_repository, "coverage.xml", b"coverage\n")
    output = provenance_repository / "metadata.json"
    output.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(_source: os.PathLike[str], _target: os.PathLike[str]) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        write_metadata(
            repository_root=provenance_repository,
            output_path=output,
            reports=[
                (
                    "python",
                    "cobertura-xml",
                    report.relative_to(provenance_repository).as_posix(),
                    "coverage.xml",
                )
            ],
            tool_versions={"coverage.py": "7.10.0"},
            **_identity(provenance_repository),
        )

    assert json.loads(output.read_text(encoding="utf-8")) == {"old": True}


def test_coverage_retry_selection_is_explicit_and_surfaces_prior_attempt(
    provenance_repository: Path,
) -> None:
    metadata_path = _write_one_metadata(provenance_repository)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["producer"]["run_attempt"] = "1"
    metadata["retry_provenance"] = _retry_provenance(
        provenance_repository, run_attempt="1"
    )
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=r"producer\.run_attempt"):
        verify_metadata(
            repository_root=provenance_repository,
            metadata_paths=[metadata_path],
            expected_sha=_git_head(provenance_repository),
            expected_repository="example/university-ecosystem",
            expected_run_id="123456789",
            expected_run_attempt="2",
            expected_job="coverage-policy-gate",
            expected_artifact="python-coverage-provenance",
            expected_workflow_ref=(
                "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
            ),
            expected_workflow_sha=WORKFLOW_SHA,
            expected_event="push",
        )

    selections = coverage_provenance.select_metadata(
        repository_root=provenance_repository,
        metadata_paths=[metadata_path],
        expected_sha=_git_head(provenance_repository),
        expected_repository="example/university-ecosystem",
        expected_run_id="123456789",
        expected_run_attempt="2",
        expected_job="coverage-policy-gate",
        expected_artifact="python-coverage-provenance",
        expected_workflow_ref=(
            "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
        expected_workflow_sha=WORKFLOW_SHA,
        expected_event="push",
        producer_attempt_policy="at-or-before",
        expected_retry_provenance=_retry_provenance(
            provenance_repository, run_attempt="1"
        ),
    )

    assert [selection.producer_attempt for selection in selections] == [1]
    assert selections[0].manifest["producer"]["run_attempt"] == "1"


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("future", "future"),
        ("noninteger", "positive decimal"),
        ("missing", "retry provenance"),
        ("source", "source_sha"),
        ("revision", "source_revision"),
        ("config", "config_digest"),
    ],
)
def test_coverage_retry_selection_rejects_unbound_or_tampered_candidates(
    provenance_repository: Path, fault: str, message: str
) -> None:
    metadata_path = _write_one_metadata(provenance_repository)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["producer"]["run_attempt"] = "1"
    metadata["retry_provenance"] = _retry_provenance(
        provenance_repository, run_attempt="1"
    )
    if fault == "future":
        metadata["producer"]["run_attempt"] = "3"
        metadata["retry_provenance"]["run_attempt"] = "3"
    elif fault == "noninteger":
        metadata["producer"]["run_attempt"] = "invalid"
        metadata["retry_provenance"]["run_attempt"] = "invalid"
    elif fault == "missing":
        del metadata["retry_provenance"]
    else:
        field = {
            "source": "source_sha",
            "revision": "source_revision",
            "config": "config_digest",
        }[fault]
        metadata["retry_provenance"][field] = "c" * (64 if fault == "config" else 40)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=message):
        coverage_provenance.select_metadata(
            repository_root=provenance_repository,
            metadata_paths=[metadata_path],
            expected_sha=_git_head(provenance_repository),
            expected_repository="example/university-ecosystem",
            expected_run_id="123456789",
            expected_run_attempt="2",
            expected_job="coverage-policy-gate",
            expected_artifact="python-coverage-provenance",
            expected_workflow_ref=(
                "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
            ),
            expected_workflow_sha=WORKFLOW_SHA,
            expected_event="push",
            producer_attempt_policy="at-or-before",
            expected_retry_provenance=_retry_provenance(
                provenance_repository, run_attempt="1"
            ),
        )


def test_coverage_candidate_collection_selects_highest_valid_attempt_deterministically(
    provenance_repository: Path,
) -> None:
    first = _write_retry_candidate(
        provenance_repository,
        metadata_path="candidates/attempt-1/coverage.json",
        run_attempt="1",
    )
    second = _write_retry_candidate(
        provenance_repository,
        metadata_path="candidates/attempt-2/coverage.json",
        run_attempt="2",
    )
    kwargs = {
        "repository_root": provenance_repository,
        "expected_sha": _git_head(provenance_repository),
        "expected_repository": "example/university-ecosystem",
        "expected_run_id": "123456789",
        "expected_run_attempt": "3",
        "expected_job": "coverage-policy-gate",
        "expected_artifact": "python-coverage-provenance",
        "expected_workflow_ref": (
            "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
        "expected_workflow_sha": WORKFLOW_SHA,
        "expected_event": "push",
        "consumer_retry_context": _consumer_retry_context(provenance_repository),
    }

    selection = coverage_provenance.select_metadata_candidates(
        metadata_paths=[first, second],
        **kwargs,
    )
    reversed_selection = coverage_provenance.select_metadata_candidates(
        metadata_paths=[second, first],
        **kwargs,
    )
    set_selection = coverage_provenance.select_metadata_candidates(
        metadata_paths={first, second},
        **kwargs,
    )

    assert selection.producer_attempt == 2
    assert selection.metadata_path == second.resolve()
    assert reversed_selection == selection
    assert set_selection == selection


def test_coverage_candidate_collection_rejects_consumer_source_revision_mismatch(
    provenance_repository: Path,
) -> None:
    candidate = _write_retry_candidate(
        provenance_repository,
        metadata_path="candidates/attempt-1/coverage.json",
        run_attempt="1",
    )
    forged_revision = "f" * 40
    metadata = json.loads(candidate.read_text(encoding="utf-8"))
    metadata["retry_provenance"]["source_revision"] = forged_revision
    candidate.write_text(json.dumps(metadata), encoding="utf-8")
    context = _consumer_retry_context(provenance_repository)
    context["source_revision"] = forged_revision

    with pytest.raises(ProvenanceError, match="source_revision does not bind"):
        coverage_provenance.select_metadata_candidates(
            repository_root=provenance_repository,
            metadata_paths=[candidate],
            expected_sha=_git_head(provenance_repository),
            expected_repository="example/university-ecosystem",
            expected_run_id="123456789",
            expected_run_attempt="2",
            expected_job="coverage-policy-gate",
            expected_artifact="python-coverage-provenance",
            expected_workflow_ref=(
                "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
            ),
            expected_workflow_sha=WORKFLOW_SHA,
            expected_event="push",
            consumer_retry_context=context,
        )


def _retry_merge_case(
    provenance_repository: Path,
) -> tuple[Path, Path, Path, Path, dict[Path, tuple[str, str]], dict[str, str]]:
    logical_artifact = "coverage-python"
    producer_job = "coverage-producer"
    metadata_path = _write_retry_candidate(
        provenance_repository,
        metadata_path="artifacts/coverage/provenance/python.json",
        run_attempt="1",
        job=producer_job,
        artifact=logical_artifact,
    )
    contract_path = provenance_repository / "quality/quality-contract.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        json.dumps(
            {
                "coverage_reports": [
                    {
                        "component": "python",
                        "format": "cobertura-xml",
                        "path": "coverage.xml",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    selection_root = provenance_repository / "artifacts/coverage/selection"
    selected_metadata = selection_root / logical_artifact / "provenance/python.json"
    selected_report = selection_root / logical_artifact / "coverage.xml"
    selected_metadata.parent.mkdir(parents=True)
    shutil.copyfile(metadata_path, selected_metadata)
    shutil.copyfile(provenance_repository / "coverage.xml", selected_report)
    receipt_path = selection_root / "selection-receipt.json"
    receipt = {
        "schema_version": 1,
        "consumer": {
            "commit_sha": _git_head(provenance_repository),
            "repository": "example/university-ecosystem",
            "run_id": "123456789",
            "run_attempt": "2",
            "workflow_ref": (
                "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
            ),
            "workflow_sha": WORKFLOW_SHA,
            "event": "push",
            "job": "coverage-policy-gate",
            "retry_context": _consumer_retry_context(provenance_repository),
        },
        "selections": [
            {
                "logical_artifact": logical_artifact,
                "producer_job": producer_job,
                "physical_artifact": f"{logical_artifact}-attempt-1",
                "producer_attempt": 1,
                "metadata": {
                    "path": f"{logical_artifact}/provenance/python.json",
                    "sha256": hashlib.sha256(
                        selected_metadata.read_bytes()
                    ).hexdigest(),
                },
                "reports": [
                    {
                        "component": "python",
                        "format": "cobertura-xml",
                        "path": f"{logical_artifact}/coverage.xml",
                        "sha256": hashlib.sha256(
                            selected_report.read_bytes()
                        ).hexdigest(),
                        "byte_size": selected_report.stat().st_size,
                    }
                ],
            }
        ],
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    output_path = provenance_repository / "artifacts/coverage/provenance/aggregate.json"
    identity = _identity(
        provenance_repository,
        run_attempt="2",
        job="coverage-policy-gate",
        artifact="quality-evidence-test",
    )
    return (
        contract_path,
        metadata_path,
        receipt_path,
        output_path,
        {metadata_path: (producer_job, logical_artifact)},
        identity,
    )


def _merge_receipted_retry_case(
    provenance_repository: Path,
    *,
    case: tuple[Path, Path, Path, Path, dict[Path, tuple[str, str]], dict[str, str]],
    retry_selection_receipt: Path | None,
) -> dict[str, object]:
    (
        contract_path,
        metadata_path,
        receipt_path,
        output_path,
        producer_expectations,
        identity,
    ) = case
    return merge_metadata(
        repository_root=provenance_repository,
        contract_path=contract_path,
        metadata_paths=[metadata_path],
        output_path=output_path,
        tool_versions={"quality-provenance": "2.0.0"},
        producer_expectations=producer_expectations,
        retry_selection_receipt=retry_selection_receipt or receipt_path,
        **identity,
    )


def _rewrite_retry_receipt(receipt_path: Path, mutate: object) -> None:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(receipt)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


def test_merge_metadata_accepts_prior_attempt_only_with_selection_receipt(
    provenance_repository: Path,
) -> None:
    (
        contract_path,
        metadata_path,
        receipt_path,
        output_path,
        producer_expectations,
        identity,
    ) = _retry_merge_case(provenance_repository)

    with pytest.raises(ProvenanceError, match=r"producer\.run_attempt"):
        merge_metadata(
            repository_root=provenance_repository,
            contract_path=contract_path,
            metadata_paths=[metadata_path],
            output_path=output_path,
            tool_versions={"quality-provenance": "2.0.0"},
            producer_expectations=producer_expectations,
            **identity,
        )

    aggregate = merge_metadata(
        repository_root=provenance_repository,
        contract_path=contract_path,
        metadata_paths=[metadata_path],
        output_path=output_path,
        tool_versions={"quality-provenance": "2.0.0"},
        producer_expectations=producer_expectations,
        retry_selection_receipt=receipt_path,
        **identity,
    )

    assert aggregate["reports"][0]["path"] == "coverage.xml"


def test_merge_cli_accepts_selection_receipt(
    provenance_repository: Path,
) -> None:
    (
        contract_path,
        metadata_path,
        receipt_path,
        output_path,
        producer_expectations,
        identity,
    ) = _retry_merge_case(provenance_repository)
    producer_job, logical_artifact = producer_expectations[metadata_path]
    arguments = [
        "merge",
        "--repository-root",
        str(provenance_repository),
        "--contract",
        str(contract_path),
        "--metadata",
        str(metadata_path),
        "--output",
        str(output_path),
        "--tool-version",
        "quality-provenance=2.0.0",
        "--producer-expectation",
        f"{metadata_path}|{producer_job}|{logical_artifact}",
        "--retry-selection-receipt",
        str(receipt_path),
        "--expected-sha",
        identity["expected_sha"],
        "--identity-provider",
        identity["identity_provider"],
        "--repository",
        identity["repository"],
        "--workflow-ref",
        identity["workflow_ref"],
        "--workflow-sha",
        identity["workflow_sha"],
        "--run-id",
        identity["run_id"],
        "--run-attempt",
        identity["run_attempt"],
        "--event",
        identity["event"],
        "--job",
        identity["job"],
        "--artifact",
        identity["artifact"],
        "--collected-at",
        identity["collected_at"],
    ]

    assert coverage_provenance.main(arguments) == 0
    assert (
        json.loads(output_path.read_text(encoding="utf-8"))["reports"]
        == json.loads(metadata_path.read_text(encoding="utf-8"))["reports"]
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("job", "lighthouse-gate"),
        ("run_id", "987654321"),
        ("run_attempt", "3"),
        ("event", "pull_request"),
    ],
)
def test_merge_metadata_rejects_receipt_bound_to_another_consumer(
    provenance_repository: Path, field: str, value: str
) -> None:
    case = _retry_merge_case(provenance_repository)
    _, _, receipt_path, _, _, _ = case
    _rewrite_retry_receipt(
        receipt_path,
        lambda receipt: receipt["consumer"].__setitem__(field, value),
    )

    with pytest.raises(ProvenanceError, match=rf"consumer\.{field} mismatch"):
        _merge_receipted_retry_case(
            provenance_repository, case=case, retry_selection_receipt=receipt_path
        )


def test_merge_metadata_rejects_receipt_with_foreign_source_revision(
    provenance_repository: Path,
) -> None:
    case = _retry_merge_case(provenance_repository)
    _, _, receipt_path, _, _, _ = case
    _rewrite_retry_receipt(
        receipt_path,
        lambda receipt: receipt["consumer"]["retry_context"].__setitem__(
            "source_revision", "f" * 40
        ),
    )

    with pytest.raises(ProvenanceError, match="source_revision does not bind"):
        _merge_receipted_retry_case(
            provenance_repository, case=case, retry_selection_receipt=receipt_path
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda receipt: receipt["selections"][0].__setitem__(
                "physical_artifact", "coverage-python-attempt-2"
            ),
            "does not bind producer attempt",
        ),
        (
            lambda receipt: receipt["selections"][0].__setitem__("producer_attempt", 3),
            "does not bind producer attempt",
        ),
        (
            lambda receipt: (
                receipt["selections"][0].__setitem__(
                    "logical_artifact", "unexpected-coverage"
                ),
                receipt["selections"][0].__setitem__(
                    "physical_artifact", "unexpected-coverage-attempt-1"
                ),
                receipt["selections"][0]["metadata"].__setitem__(
                    "path", "unexpected-coverage/provenance/python.json"
                ),
                receipt["selections"][0]["reports"][0].__setitem__(
                    "path", "unexpected-coverage/coverage.xml"
                ),
            ),
            "unknown logical artifact",
        ),
        (
            lambda receipt: receipt["selections"][0]["reports"][0].__setitem__(
                "path", "coverage-python/aux.xml"
            ),
            "portable relative path",
        ),
    ],
)
def test_merge_metadata_rejects_invalid_receipt_selection(
    provenance_repository: Path, mutate: object, message: str
) -> None:
    case = _retry_merge_case(provenance_repository)
    _, _, receipt_path, _, _, _ = case
    _rewrite_retry_receipt(receipt_path, mutate)

    with pytest.raises(ProvenanceError, match=message):
        _merge_receipted_retry_case(
            provenance_repository, case=case, retry_selection_receipt=receipt_path
        )


def test_merge_metadata_rejects_duplicate_receipt_selection(
    provenance_repository: Path,
) -> None:
    case = _retry_merge_case(provenance_repository)
    _, _, receipt_path, _, _, _ = case
    _rewrite_retry_receipt(
        receipt_path,
        lambda receipt: receipt["selections"].append(
            copy.deepcopy(receipt["selections"][0])
        ),
    )

    with pytest.raises(ProvenanceError, match="duplicate logical artifact"):
        _merge_receipted_retry_case(
            provenance_repository, case=case, retry_selection_receipt=receipt_path
        )


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("selected-metadata", "receipt metadata sha256 mismatch"),
        ("selected-report", "receipt report sha256 mismatch"),
        ("canonical-metadata", "canonical metadata sha256"),
        ("canonical-report", "sha256 mismatch"),
    ],
)
def test_merge_metadata_rejects_mutated_receipted_bytes(
    provenance_repository: Path, target: str, message: str
) -> None:
    case = _retry_merge_case(provenance_repository)
    _, metadata_path, receipt_path, _, _, _ = case
    selection_root = receipt_path.parent / "coverage-python"
    if target == "selected-metadata":
        path = selection_root / "provenance/python.json"
    elif target == "selected-report":
        path = selection_root / "coverage.xml"
    elif target == "canonical-metadata":
        path = metadata_path
    else:
        path = provenance_repository / "coverage.xml"
    contents = path.read_bytes()
    if target == "canonical-metadata":
        path.write_bytes(contents + b"\n")
    else:
        path.write_bytes(bytes([contents[0] ^ 1]) + contents[1:])

    with pytest.raises(ProvenanceError, match=message):
        _merge_receipted_retry_case(
            provenance_repository, case=case, retry_selection_receipt=receipt_path
        )


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("foreign", "producer.run_id"),
        ("future", "future"),
        ("duplicate", "duplicate producer attempt"),
        ("malformed", "unable to read metadata"),
    ],
)
def test_coverage_candidate_collection_rejects_every_invalid_candidate(
    provenance_repository: Path, fault: str, message: str
) -> None:
    if fault == "foreign":
        candidates = [
            _write_retry_candidate(
                provenance_repository,
                metadata_path="candidates/foreign/coverage.json",
                run_attempt="1",
                run_id="987654321",
            )
        ]
    elif fault == "future":
        candidates = [
            _write_retry_candidate(
                provenance_repository,
                metadata_path="candidates/future/coverage.json",
                run_attempt="4",
            )
        ]
    elif fault == "duplicate":
        candidates = [
            _write_retry_candidate(
                provenance_repository,
                metadata_path="candidates/duplicate-left/coverage.json",
                run_attempt="2",
            ),
            _write_retry_candidate(
                provenance_repository,
                metadata_path="candidates/duplicate-right/coverage.json",
                run_attempt="2",
            ),
        ]
    else:
        malformed = provenance_repository / "candidates/malformed/coverage.json"
        malformed.parent.mkdir(parents=True)
        malformed.write_text("{", encoding="utf-8")
        candidates = [malformed]

    with pytest.raises(ProvenanceError, match=message):
        coverage_provenance.select_metadata_candidates(
            repository_root=provenance_repository,
            metadata_paths=candidates,
            expected_sha=_git_head(provenance_repository),
            expected_repository="example/university-ecosystem",
            expected_run_id="123456789",
            expected_run_attempt="3",
            expected_job="coverage-policy-gate",
            expected_artifact="python-coverage-provenance",
            expected_workflow_ref=(
                "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
            ),
            expected_workflow_sha=WORKFLOW_SHA,
            expected_event="push",
            consumer_retry_context=_consumer_retry_context(provenance_repository),
        )
