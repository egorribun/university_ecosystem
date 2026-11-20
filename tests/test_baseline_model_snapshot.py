"""The historical baseline proof uses one verified model tree from its history."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.integration import test_mvp_baseline_schema_equivalence as proof


def _git(root: Path, *arguments: str) -> None:
    executable = shutil.which("git")
    assert executable is not None
    subprocess.run(  # noqa: S603 - fixed Git executable and test-owned arguments
        [executable, "-C", str(root), *arguments], check=True, capture_output=True
    )


@pytest.fixture
def baseline_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Baseline fixture")
    _git(root, "config", "user.email", "baseline@example.invalid")
    (root / "alembic").mkdir()
    (root / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    _git(root, "add", "alembic.ini")
    _git(root, "commit", "-qm", "seed")

    versions = root / "alembic" / "versions"
    versions.mkdir()
    (versions / proof.BASELINE_FILE).write_text(
        "baseline\n", encoding="utf-8", newline="\n"
    )
    models = root / "app" / "models"
    models.mkdir(parents=True)
    (models / "first.py").write_text("baseline first\n", encoding="utf-8")
    (models / "second.py").write_text("baseline second\n", encoding="utf-8")
    _git(root, "add", "alembic", "app")
    _git(root, "commit", "-qm", "baseline")

    (versions / "successor.py").write_text("successor\n", encoding="utf-8")
    (models / "first.py").write_text("current first\n", encoding="utf-8")
    (models / "second.py").write_text("current second\n", encoding="utf-8")
    (models / "current_only.py").write_text("new model\n", encoding="utf-8")
    _git(root, "add", "alembic", "app")
    _git(root, "commit", "-qm", "successor")
    return root


def test_baseline_snapshot_uses_one_historical_model_tree(
    baseline_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(proof, "PROJECT_ROOT", baseline_repository)
    target = tmp_path / "snapshot"
    proof._extract_baseline_tree(target)
    assert (target / "app/models/first.py").read_text(
        encoding="utf-8"
    ) == "baseline first\n"
    assert (target / "app/models/second.py").read_text(
        encoding="utf-8"
    ) == "baseline second\n"
    assert not (target / "app/models/current_only.py").exists()
    assert sorted(path.name for path in (target / "alembic/versions").glob("*.py")) == [
        proof.BASELINE_FILE
    ]


def test_baseline_snapshot_rejects_changed_baseline(
    baseline_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (baseline_repository / "alembic/versions" / proof.BASELINE_FILE).write_text(
        "changed\n", encoding="utf-8"
    )
    monkeypatch.setattr(proof, "PROJECT_ROOT", baseline_repository)
    with pytest.raises(RuntimeError, match="baseline source does not match"):
        proof._extract_baseline_tree(tmp_path / "snapshot")


def test_baseline_snapshot_rejects_shallow_history(
    baseline_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shallow = tmp_path / "shallow"
    executable = shutil.which("git")
    assert executable is not None
    subprocess.run(  # noqa: S603 - fixed Git executable and test-owned arguments
        [executable, "clone", "--depth=1", baseline_repository.as_uri(), str(shallow)],
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(proof, "PROJECT_ROOT", shallow)
    with pytest.raises(RuntimeError, match="complete Git history"):
        proof._extract_baseline_tree(tmp_path / "snapshot")


def test_baseline_snapshot_rejects_ambiguous_revision(
    baseline_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = proof._run_fixed_argv

    async def ambiguous(
        arguments: list[str], cwd: Path, env: dict[str, str] | None = None
    ):
        if "log" in arguments:
            return 0, b"ambiguous\n", b""
        return await run(arguments, cwd, env)

    monkeypatch.setattr(proof, "PROJECT_ROOT", baseline_repository)
    monkeypatch.setattr(proof, "_run_fixed_argv", ambiguous)
    with pytest.raises(RuntimeError, match="ambiguous Git history"):
        proof._extract_baseline_tree(tmp_path / "snapshot")
