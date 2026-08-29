"""Fail-closed retry selection for primary-CI mutmut artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import scripts.mutmut_retry_artifacts as retry_artifacts

GIT = shutil.which("git")
WORKFLOW_SHA = "89abcdef0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
RUN_ID = "123456789"
WORKFLOW = ".github/workflows/ci.yml"
REPOSITORY = "example/university-ecosystem"

pytestmark = pytest.mark.skipif(GIT is None, reason="git is required for provenance")


def _git(root: Path, *arguments: str) -> str:
    assert GIT is not None
    result = subprocess.run(  # noqa: S603 -- test fixture invokes discovered git.
        [GIT, *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _prepare_inputs(root: Path) -> None:
    (root / "mutation-config.toml").write_text(
        "[mutation]\nworkers = 2\n", encoding="utf-8"
    )
    (root / "mutation-policy.json").write_text('{"floor": 100}\n', encoding="utf-8")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _prepare_inputs(root)
    (root / "README.md").write_text("test repository\n", encoding="utf-8")
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "Retry artifact tests")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "fixture")
    return root


def _head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD")


def _retry_context(root: Path, *, run_attempt: str, artifact: str) -> dict[str, str]:
    commit_sha = _head(root)
    return retry_artifacts.build_retry_provenance(
        root=root,
        repository=REPOSITORY,
        run_id=RUN_ID,
        run_attempt=run_attempt,
        source_sha=commit_sha,
        source_revision=commit_sha,
        workflow_ref=f"{REPOSITORY}/{WORKFLOW}@refs/heads/main",
        workflow_sha=WORKFLOW_SHA,
        event="pull_request",
        artifact=artifact,
        config_inputs=("mutation-config.toml",),
        policy_inputs=("mutation-policy.json",),
    )


def _write_stats_candidate(
    root: Path,
    *,
    shard: int,
    run_attempt: str,
    candidate_parent: Path = Path(retry_artifacts.STATS_CANDIDATE_DIRECTORY),
) -> Path:
    source = root / retry_artifacts.STATS_SOURCE_PATH
    source.parent.mkdir(parents=True, exist_ok=True)
    stats = {
        "duration_by_test": {f"test_{shard}": float(shard + 1)},
        "stats_time": float(shard + 1),
        "tests_by_mangled_function_name": {f"app.module_{shard}": [f"test_{shard}"]},
    }
    source.write_text(json.dumps(stats, sort_keys=True) + "\n", encoding="utf-8")
    logical_artifact = f"mutmut-stats-shard-{shard}"
    retry_artifacts.create_stats_sidecar(
        root=root,
        output=Path(retry_artifacts.STATS_SIDECAR_NAME),
        stats_path=Path(retry_artifacts.STATS_SOURCE_PATH),
        logical_shard=shard,
        commit_sha=_head(root),
        run_id=RUN_ID,
        run_attempt=run_attempt,
        workflow=WORKFLOW,
        retry_provenance=_retry_context(
            root, run_attempt=run_attempt, artifact=logical_artifact
        ),
        candidate_parent=candidate_parent,
    )
    physical_artifact = f"{logical_artifact}-attempt-{run_attempt}"
    candidate = root / candidate_parent / physical_artifact
    candidate.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, candidate / retry_artifacts.STATS_PATH)
    shutil.copyfile(
        root / retry_artifacts.STATS_SIDECAR_NAME,
        candidate / retry_artifacts.STATS_SIDECAR_NAME,
    )
    return candidate


def _complete_stats_candidates(
    root: Path,
    *,
    run_attempt: str = "1",
    candidate_parent: Path = Path(retry_artifacts.STATS_CANDIDATE_DIRECTORY),
) -> list[Path]:
    return [
        _write_stats_candidate(
            root,
            shard=shard,
            run_attempt=run_attempt,
            candidate_parent=candidate_parent,
        )
        for shard in range(8)
    ]


def test_stats_sidecar_uses_generic_provenance_integrity_envelope(
    repository: Path,
) -> None:
    candidate = _write_stats_candidate(repository, shard=0, run_attempt="1")

    sidecar = json.loads(
        (candidate / retry_artifacts.STATS_SIDECAR_NAME).read_text(encoding="utf-8")
    )

    assert sidecar["schema_version"] == 2
    assert sidecar["producer"]["identity_provider"] == "github-actions"
    assert sidecar["producer"]["artifact"] == "mutmut-stats-shard-0"
    assert sidecar["reports"] == [
        {
            "component": "mutmut",
            "format": "mutmut-stats-json",
            "path": (
                "mutmut-stats-candidates/"
                "mutmut-stats-shard-0-attempt-1/mutmut-stats.json"
            ),
            "sha256": sidecar["reports"][0]["sha256"],
            "byte_size": sidecar["reports"][0]["byte_size"],
        }
    ]


def test_retry_provenance_rejects_a_root_with_a_linked_ancestor(
    repository: Path,
) -> None:
    outside = repository / "outside/nested"
    outside.mkdir(parents=True)
    _prepare_inputs(outside)
    linked_parent = repository / "linked"
    try:
        linked_parent.symlink_to(outside.parent, target_is_directory=True)
    except OSError as error:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"directory symlinks are unavailable: {error}"
        )

    with pytest.raises(retry_artifacts.RetryArtifactError):
        retry_artifacts.build_retry_provenance(
            root=linked_parent / "nested",
            repository=REPOSITORY,
            run_id=RUN_ID,
            run_attempt="1",
            source_sha=_head(repository),
            source_revision=_head(repository),
            workflow_ref=f"{REPOSITORY}/{WORKFLOW}@refs/heads/main",
            workflow_sha=WORKFLOW_SHA,
            event="pull_request",
            artifact=retry_artifacts.STATS_ARTIFACT,
            config_inputs=("mutation-config.toml",),
            policy_inputs=("mutation-policy.json",),
        )


def test_stats_selector_chooses_highest_valid_attempt_per_logical_shard(
    repository: Path,
) -> None:
    candidates = _complete_stats_candidates(repository)
    newest = _write_stats_candidate(repository, shard=0, run_attempt="2")

    selected = retry_artifacts.select_stats_candidates(
        root=repository,
        candidate_roots=[*reversed(candidates), newest],
        output_root=repository / "selected-stats",
        commit_sha=_head(repository),
        run_id=RUN_ID,
        run_attempt="3",
        workflow=WORKFLOW,
        consumer_retry_context=_retry_context(
            repository, run_attempt="3", artifact=retry_artifacts.STATS_ARTIFACT
        ),
    )

    assert {shard: item.producer_attempt for shard, item in selected.items()} == {
        0: 2,
        **{shard: 1 for shard in range(1, 8)},
    }
    assert (repository / "selected-stats/shard-00/mutmut-stats.json").is_file()
    evidence = json.loads(
        (repository / "selected-stats/mutmut-stats-selection.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["consumer"]["run_attempt"] == "3"
    assert {
        item["logical_shard"]: item["producer_attempt"] for item in evidence["selected"]
    } == {0: 2, **{shard: 1 for shard in range(1, 8)}}
    assert (
        evidence["selected"][0]["physical_artifact"] == "mutmut-stats-shard-0-attempt-2"
    )


@pytest.mark.parametrize(
    "fault",
    (
        "foreign",
        "future",
        "duplicate",
        "tampered",
        "malformed",
        "incomplete",
        "unexpected-member",
        "invalid-physical-name",
        "physical-attempt-mismatch",
    ),
)
def test_stats_selector_fails_closed_for_every_untrusted_candidate(
    repository: Path, fault: str
) -> None:
    candidates = _complete_stats_candidates(repository)
    if fault == "foreign":
        sidecar_path = candidates[0] / retry_artifacts.STATS_SIDECAR_NAME
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["producer"]["run_id"] = "987654321"
        sidecar["retry_provenance"]["run_id"] = "987654321"
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    elif fault == "future":
        candidates[0] = _write_stats_candidate(repository, shard=0, run_attempt="4")
    elif fault == "duplicate":
        candidates.extend(
            (
                _write_stats_candidate(
                    repository,
                    shard=0,
                    run_attempt="2",
                    candidate_parent=Path("duplicate-left"),
                ),
                _write_stats_candidate(
                    repository,
                    shard=0,
                    run_attempt="2",
                    candidate_parent=Path("duplicate-right"),
                ),
            )
        )
    elif fault == "tampered":
        (candidates[0] / retry_artifacts.STATS_PATH).write_text(
            "tampered\n", encoding="utf-8"
        )
    elif fault == "malformed":
        (candidates[0] / retry_artifacts.STATS_SIDECAR_NAME).write_text(
            "{", encoding="utf-8"
        )
    elif fault == "incomplete":
        candidates.pop()
    elif fault == "unexpected-member":
        (candidates[0] / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    elif fault == "invalid-physical-name":
        renamed = candidates[0].with_name("unexpected-mutmut-stats-candidate")
        candidates[0].rename(renamed)
        candidates[0] = renamed
    else:
        renamed = candidates[0].with_name("mutmut-stats-shard-0-attempt-2")
        candidates[0].rename(renamed)
        candidates[0] = renamed
        sidecar_path = renamed / retry_artifacts.STATS_SIDECAR_NAME
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["reports"][0]["path"] = (
            "mutmut-stats-candidates/mutmut-stats-shard-0-attempt-2/mutmut-stats.json"
        )
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

    with pytest.raises(retry_artifacts.RetryArtifactError):
        retry_artifacts.select_stats_candidates(
            root=repository,
            candidate_roots=candidates,
            output_root=repository / "selected-stats",
            commit_sha=_head(repository),
            run_id=RUN_ID,
            run_attempt="3",
            workflow=WORKFLOW,
            consumer_retry_context=_retry_context(
                repository, run_attempt="3", artifact=retry_artifacts.STATS_ARTIFACT
            ),
        )


def _write_universe_candidate(root: Path, *, candidate: Path, run_attempt: str) -> None:
    stats_parent = Path(f"stats-candidates-{run_attempt}")
    stats_candidates = _complete_stats_candidates(
        root, run_attempt=run_attempt, candidate_parent=stats_parent
    )
    selected_stats = root / f"selected-stats-{run_attempt}"
    retry_artifacts.select_stats_candidates(
        root=root,
        candidate_roots=stats_candidates,
        output_root=selected_stats,
        commit_sha=_head(root),
        run_id=RUN_ID,
        run_attempt=run_attempt,
        workflow=WORKFLOW,
        consumer_retry_context=_retry_context(
            root, run_attempt=run_attempt, artifact=retry_artifacts.STATS_ARTIFACT
        ),
    )

    mutants = root / "mutants"
    shutil.rmtree(mutants)
    (mutants / "app").mkdir(parents=True)
    (mutants / "app/example.py").write_text(
        "def example() -> bool:\n    return True\n", encoding="utf-8"
    )
    (mutants / "app/example.py.meta").write_text(
        '{"exit_code_by_key": {"example__mutmut_1": null}}\n', encoding="utf-8"
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
        )
        + "\n",
        encoding="utf-8",
    )
    (mutants / "mutmut-incremental-plan").mkdir()
    (mutants / "mutmut-incremental-plan/plan-manifest.json").write_text(
        "{}\n", encoding="utf-8"
    )
    shutil.copyfile(
        selected_stats / retry_artifacts.STATS_SELECTION_NAME,
        mutants / retry_artifacts.STATS_SELECTION_NAME,
    )
    retry_artifacts.create_universe_artifact(
        root=root,
        output=Path("mutmut-universe-artifact.json"),
        mode="mutmut",
        commit_sha=_head(root),
        run_id=RUN_ID,
        run_attempt=run_attempt,
        workflow=WORKFLOW,
        retry_provenance=_retry_context(
            root, run_attempt=run_attempt, artifact=retry_artifacts.UNIVERSE_ARTIFACT
        ),
    )
    candidate.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(
        root / "mutmut-universe-artifact.json",
        candidate / "mutmut-universe-artifact.json",
    )
    shutil.copytree(mutants, candidate / "mutants")


def test_universe_selector_reuses_the_highest_verified_prior_attempt(
    repository: Path,
) -> None:
    first = repository / "universe-candidates/attempt-1"
    second = repository / "universe-candidates/attempt-2"
    _write_universe_candidate(repository, candidate=first, run_attempt="1")
    _write_universe_candidate(repository, candidate=second, run_attempt="2")

    consumer = repository / "universe-consumer"
    consumer.mkdir()
    selection = retry_artifacts.select_universe_candidate(
        candidate_roots=[first, second],
        output_root=consumer,
        selection_evidence=Path("mutmut-universe-selection.json"),
        commit_sha=_head(repository),
        run_id=RUN_ID,
        run_attempt="3",
        workflow=WORKFLOW,
        expected_mode="mutmut",
        consumer_retry_context=_retry_context(
            repository,
            run_attempt="3",
            artifact=retry_artifacts.UNIVERSE_ARTIFACT,
        ),
    )

    assert selection.producer_attempt == 2
    assert (consumer / "mutants/mutmut-universe.json").is_file()
    evidence = json.loads(
        (consumer / "mutmut-universe-selection.json").read_text(encoding="utf-8")
    )
    assert evidence["consumer"]["run_attempt"] == "3"
    assert evidence["producer_attempt"] == 2
