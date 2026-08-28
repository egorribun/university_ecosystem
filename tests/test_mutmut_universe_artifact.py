from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.mutmut_universe_artifact import (
    ArtifactValidationError,
    create_artifact_manifest,
    validate_artifact_manifest,
)

COMMIT_SHA = "a" * 40
RUN_ID = "123456"
RUN_ATTEMPT = "2"
WORKFLOW = ".github/workflows/ci.yml"


def _write_mutmut_tree(root: Path) -> Path:
    mutants = root / "mutants"
    (mutants / "app").mkdir(parents=True)
    (mutants / "app/example.py").write_text(
        "def example() -> bool:\n    return True\n", encoding="utf-8"
    )
    (mutants / "app/example.py.meta").write_text(
        json.dumps({"exit_code_by_key": {"example__mutmut_1": None}}),
        encoding="utf-8",
    )
    stats = b'{"duration_by_test": {"test_example": 1.0}}\n'
    (mutants / "mutmut-stats.json").write_bytes(stats)
    (mutants / "mutmut-universe.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "stats_sha256": hashlib.sha256(stats).hexdigest(),
                "mutant_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (mutants / "mutmut-incremental-plan").mkdir()
    (mutants / "mutmut-incremental-plan/plan-manifest.json").write_text(
        "{}\n", encoding="utf-8"
    )
    return mutants / "mutmut-artifact.json"


def _create(root: Path, *, mode: str = "mutmut") -> dict[str, object]:
    output = _write_mutmut_tree(root)
    return create_artifact_manifest(
        root=root,
        output=output,
        commit_sha=COMMIT_SHA,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        workflow=WORKFLOW,
        includes=(
            (
                "mutants/app",
                "mutants/mutmut-universe.json",
                "mutants/mutmut-stats.json",
                "mutants/mutmut-incremental-plan",
            )
            if mode == "mutmut"
            else ()
        ),
        mode=mode,
    )


def test_mutmut_artifact_round_trip_binds_inventory_and_identity(
    tmp_path: Path,
) -> None:
    payload = _create(tmp_path)

    assert payload["schema_version"] == 1
    assert payload["mode"] == "mutmut"
    assert payload["producer"] == {
        "commit_sha": COMMIT_SHA,
        "run_id": RUN_ID,
        "run_attempt": RUN_ATTEMPT,
        "workflow": WORKFLOW,
    }
    assert "mutants/app/example.py" in payload["files"]
    assert (
        validate_artifact_manifest(
            root=tmp_path,
            manifest_path=Path("mutants/mutmut-artifact.json"),
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
            expected_mode="mutmut",
        )
        == payload
    )


def test_mutmut_artifact_rejects_content_tampering(tmp_path: Path) -> None:
    _create(tmp_path)
    (tmp_path / "mutants/app/example.py").write_text(
        "def example() -> bool:\n    return False\n", encoding="utf-8"
    )

    with pytest.raises(ArtifactValidationError, match="hash mismatch"):
        validate_artifact_manifest(
            root=tmp_path,
            manifest_path=Path("mutants/mutmut-artifact.json"),
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commit_sha", "b" * 40),
        ("run_id", "123457"),
        ("run_attempt", "3"),
        ("workflow", ".github/workflows/nightly-full-gate.yml"),
    ],
)
def test_mutmut_artifact_rejects_cross_run_identity(
    tmp_path: Path, field: str, value: str
) -> None:
    _create(tmp_path)
    identity = {
        "commit_sha": COMMIT_SHA,
        "run_id": RUN_ID,
        "run_attempt": RUN_ATTEMPT,
        "workflow": WORKFLOW,
    }
    identity[field] = value

    with pytest.raises(ArtifactValidationError, match="producer identity"):
        validate_artifact_manifest(
            root=tmp_path,
            manifest_path=Path("mutants/mutmut-artifact.json"),
            **identity,
        )


def test_mutmut_artifact_requires_complete_universe_inputs(tmp_path: Path) -> None:
    output = _write_mutmut_tree(tmp_path)
    (tmp_path / "mutants/mutmut-incremental-plan/plan-manifest.json").unlink()

    with pytest.raises(ArtifactValidationError, match="required files"):
        create_artifact_manifest(
            root=tmp_path,
            output=output,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
            includes=(
                "mutants/app",
                "mutants/mutmut-universe.json",
                "mutants/mutmut-stats.json",
            ),
        )


def test_mutmut_artifact_rejects_stats_not_bound_to_universe_manifest(
    tmp_path: Path,
) -> None:
    output = _write_mutmut_tree(tmp_path)
    (tmp_path / "mutants/mutmut-stats.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="bind the artifact stats"):
        create_artifact_manifest(
            root=tmp_path,
            output=output,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
            includes=(
                "mutants/app",
                "mutants/mutmut-universe.json",
                "mutants/mutmut-stats.json",
                "mutants/mutmut-incremental-plan",
            ),
        )


def test_empty_artifact_mode_supports_non_python_pull_requests(tmp_path: Path) -> None:
    output = tmp_path / "mutmut-artifact.json"
    payload = create_artifact_manifest(
        root=tmp_path,
        output=output,
        commit_sha=COMMIT_SHA,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        workflow=WORKFLOW,
        includes=(),
        mode="empty",
    )

    assert payload["files"] == {}
    assert (
        validate_artifact_manifest(
            root=tmp_path,
            manifest_path=output,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
            expected_mode="empty",
        )
        == payload
    )


def test_empty_artifact_mode_rejects_universe_files(tmp_path: Path) -> None:
    _write_mutmut_tree(tmp_path)

    with pytest.raises(ArtifactValidationError, match="must not carry"):
        create_artifact_manifest(
            root=tmp_path,
            output=tmp_path / "mutmut-artifact.json",
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
            includes=("mutants/mutmut-stats.json",),
            mode="empty",
        )


def test_mutmut_artifact_rejects_path_traversal_in_downloaded_manifest(
    tmp_path: Path,
) -> None:
    _create(tmp_path)
    path = tmp_path / "mutants/mutmut-artifact.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["files"]["../outside.txt"] = "0" * 64
    payload["files_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="repository-relative"):
        validate_artifact_manifest(
            root=tmp_path,
            manifest_path=path,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
        )
