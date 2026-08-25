from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.quality.coverage_provenance import (
    ProvenanceError,
    merge_metadata,
    verify_metadata,
    write_metadata,
)

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


def test_write_metadata_rejects_report_through_symlinked_ancestor(
    provenance_repository: Path,
) -> None:
    outside = provenance_repository.with_name(f"{provenance_repository.name}-outside")
    outside.mkdir()
    alias = provenance_repository / "artifacts"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
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
