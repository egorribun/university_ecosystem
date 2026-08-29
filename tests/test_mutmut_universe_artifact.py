from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.mutmut_universe_artifact as mutmut_artifact
from scripts.mutmut_universe_artifact import (
    ArtifactValidationError,
    create_artifact_manifest,
    validate_artifact_manifest,
)

COMMIT_SHA = "a" * 40
RUN_ID = "123456"
RUN_ATTEMPT = "2"
WORKFLOW = ".github/workflows/ci.yml"


def _retry_provenance(
    *, run_attempt: str = RUN_ATTEMPT, run_id: str = RUN_ID
) -> dict[str, str]:
    return {
        "repository": "example/university-ecosystem",
        "run_id": run_id,
        "source_sha": COMMIT_SHA,
        "source_revision": COMMIT_SHA,
        "workflow_ref": (
            "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
        "workflow_sha": "b" * 40,
        "event": "pull_request",
        "config_digest": "c" * 64,
        "policy_digest": "d" * 64,
        "artifact": "mutmut-universe",
        "run_attempt": run_attempt,
    }


def _consumer_retry_context() -> dict[str, str]:
    return {
        name: value
        for name, value in _retry_provenance(run_attempt="1").items()
        if name not in {"run_attempt", "artifact"}
    }


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


def _create(
    root: Path,
    *,
    mode: str = "mutmut",
    run_id: str = RUN_ID,
    run_attempt: str = RUN_ATTEMPT,
    retry_provenance: dict[str, str] | None = None,
) -> dict[str, object]:
    output = _write_mutmut_tree(root)
    return create_artifact_manifest(
        root=root,
        output=output,
        commit_sha=COMMIT_SHA,
        run_id=run_id,
        run_attempt=run_attempt,
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
        retry_provenance=retry_provenance,
    )


def _create_retry_candidate(
    root: Path, *, run_attempt: str, run_id: str = RUN_ID
) -> dict[str, object]:
    _write_mutmut_tree(root)
    return create_artifact_manifest(
        root=root,
        output=Path("mutmut-universe-artifact.json"),
        commit_sha=COMMIT_SHA,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=WORKFLOW,
        includes=(
            "mutants/app",
            "mutants/mutmut-universe.json",
            "mutants/mutmut-stats.json",
            "mutants/mutmut-incremental-plan",
        ),
        mode="mutmut",
        retry_provenance=_retry_provenance(
            run_id=run_id,
            run_attempt=run_attempt,
        ),
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


def test_mutmut_artifact_retry_selection_is_explicit_and_surfaces_prior_attempt(
    tmp_path: Path,
) -> None:
    _create(tmp_path)
    path = tmp_path / "mutants/mutmut-artifact.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["producer"]["run_attempt"] = "1"
    payload["retry_provenance"] = _retry_provenance(run_attempt="1")
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="producer identity"):
        validate_artifact_manifest(
            root=tmp_path,
            manifest_path=path,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
        )

    selection = mutmut_artifact.select_artifact_manifest(
        root=tmp_path,
        manifest_path=path,
        commit_sha=COMMIT_SHA,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        workflow=WORKFLOW,
        producer_attempt_policy="at-or-before",
        expected_retry_provenance=_retry_provenance(run_attempt="1"),
    )

    assert selection.producer_attempt == 1
    assert selection.manifest["producer"]["run_attempt"] == "1"


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
def test_mutmut_artifact_retry_selection_rejects_unbound_or_tampered_candidates(
    tmp_path: Path, fault: str, message: str
) -> None:
    _create(tmp_path)
    path = tmp_path / "mutants/mutmut-artifact.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["producer"]["run_attempt"] = "1"
    payload["retry_provenance"] = _retry_provenance(run_attempt="1")
    if fault == "future":
        payload["producer"]["run_attempt"] = "3"
        payload["retry_provenance"]["run_attempt"] = "3"
    elif fault == "noninteger":
        payload["producer"]["run_attempt"] = "invalid"
        payload["retry_provenance"]["run_attempt"] = "invalid"
    elif fault == "missing":
        del payload["retry_provenance"]
    else:
        field = {
            "source": "source_sha",
            "revision": "source_revision",
            "config": "config_digest",
        }[fault]
        payload["retry_provenance"][field] = "e" * (64 if fault == "config" else 40)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match=message):
        mutmut_artifact.select_artifact_manifest(
            root=tmp_path,
            manifest_path=path,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt=RUN_ATTEMPT,
            workflow=WORKFLOW,
            producer_attempt_policy="at-or-before",
            expected_retry_provenance=_retry_provenance(run_attempt="1"),
        )


def test_mutmut_candidate_collection_selects_highest_valid_attempt_deterministically(
    tmp_path: Path,
) -> None:
    first = tmp_path / "attempt-1"
    second = tmp_path / "attempt-2"
    _create_retry_candidate(first, run_attempt="1")
    _create_retry_candidate(second, run_attempt="2")

    selection = mutmut_artifact.select_artifact_manifest_candidates(
        candidate_roots=[first, second],
        commit_sha=COMMIT_SHA,
        run_id=RUN_ID,
        run_attempt="3",
        workflow=WORKFLOW,
        expected_artifact="mutmut-universe",
        consumer_retry_context=_consumer_retry_context(),
    )
    reversed_selection = mutmut_artifact.select_artifact_manifest_candidates(
        candidate_roots=[second, first],
        commit_sha=COMMIT_SHA,
        run_id=RUN_ID,
        run_attempt="3",
        workflow=WORKFLOW,
        expected_artifact="mutmut-universe",
        consumer_retry_context=_consumer_retry_context(),
    )
    set_selection = mutmut_artifact.select_artifact_manifest_candidates(
        candidate_roots={first, second},
        commit_sha=COMMIT_SHA,
        run_id=RUN_ID,
        run_attempt="3",
        workflow=WORKFLOW,
        expected_artifact="mutmut-universe",
        consumer_retry_context=_consumer_retry_context(),
    )

    assert selection.producer_attempt == 2
    assert selection.candidate_root == second.resolve()
    assert reversed_selection == selection
    assert set_selection == selection


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("foreign", "producer identity"),
        ("future", "future"),
        ("duplicate", "duplicate producer attempt"),
        ("malformed", "invalid"),
    ],
)
def test_mutmut_candidate_collection_rejects_every_invalid_candidate(
    tmp_path: Path, fault: str, message: str
) -> None:
    candidates: list[Path]
    if fault == "foreign":
        foreign = tmp_path / "foreign"
        _create_retry_candidate(foreign, run_attempt="1", run_id="987654")
        candidates = [foreign]
    elif fault == "future":
        future = tmp_path / "future"
        _create_retry_candidate(future, run_attempt="4")
        candidates = [future]
    elif fault == "duplicate":
        left = tmp_path / "duplicate-left"
        right = tmp_path / "duplicate-right"
        _create_retry_candidate(left, run_attempt="2")
        _create_retry_candidate(right, run_attempt="2")
        candidates = [left, right]
    else:
        malformed = tmp_path / "malformed"
        malformed.mkdir()
        (malformed / "mutmut-universe-artifact.json").write_text("{", encoding="utf-8")
        candidates = [malformed]

    with pytest.raises(ArtifactValidationError, match=message):
        mutmut_artifact.select_artifact_manifest_candidates(
            candidate_roots=candidates,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt="3",
            workflow=WORKFLOW,
            expected_artifact="mutmut-universe",
            consumer_retry_context=_consumer_retry_context(),
        )


def test_mutmut_artifact_rejects_duplicate_retry_provenance_json_keys(
    tmp_path: Path,
) -> None:
    _create_retry_candidate(tmp_path, run_attempt="1")
    path = tmp_path / "mutmut-universe-artifact.json"
    serialized = path.read_text(encoding="utf-8").rstrip()
    path.write_text(
        f'{serialized[:-1]},"retry_provenance":{json.dumps(_retry_provenance(run_attempt="1"))}}}',
        encoding="utf-8",
    )

    with pytest.raises(ArtifactValidationError, match="duplicate JSON key"):
        mutmut_artifact.select_artifact_manifest(
            root=tmp_path,
            manifest_path=path,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt="2",
            workflow=WORKFLOW,
            producer_attempt_policy="at-or-before",
            expected_retry_provenance=_retry_provenance(run_attempt="1"),
        )


def test_mutmut_artifact_rejects_nonstandard_json_constants(tmp_path: Path) -> None:
    _create_retry_candidate(tmp_path, run_attempt="1")
    path = tmp_path / "mutmut-universe-artifact.json"
    serialized = path.read_text(encoding="utf-8")
    tampered = serialized.replace('"schema_version": 1', '"schema_version": NaN')
    assert tampered != serialized
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="invalid JSON constant: NaN"):
        validate_artifact_manifest(
            root=tmp_path,
            manifest_path=path,
            commit_sha=COMMIT_SHA,
            run_id=RUN_ID,
            run_attempt="1",
            workflow=WORKFLOW,
        )
