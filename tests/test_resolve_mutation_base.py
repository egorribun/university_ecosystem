from __future__ import annotations

import importlib.util
import shutil
import subprocess  # nosec B404
from pathlib import Path

import pytest

import scripts

# The fixture invokes a resolved git executable without a shell.
ROOT = Path(__file__).resolve().parents[1]
RESOLVER_PATH = ROOT / "scripts" / "resolve_mutation_base.py"


def _load_resolver():
    assert scripts is not None
    assert RESOLVER_PATH.is_file(), "manual mutation-base resolver is missing"
    spec = importlib.util.spec_from_file_location(
        "resolve_mutation_base", RESOLVER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repository: Path, *args: str) -> str:
    git = shutil.which("git")
    assert git is not None
    # The fixture uses a resolved git executable without a shell.
    result = subprocess.run(  # noqa: S603  # nosec B603
        [git, "-C", str(repository), *args],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit(repository: Path, name: str, content: str) -> str:
    (repository / name).write_text(content, encoding="utf-8")
    _git(repository, "add", name)
    _git(repository, "commit", "--quiet", "-m", name)
    return _git(repository, "rev-parse", "HEAD")


@pytest.fixture
def git_repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.email", "quality@example.invalid")
    _git(repository, "config", "user.name", "Quality Gate")
    base = _commit(repository, "base.py", "BASE = 1\n")
    _git(repository, "update-ref", "refs/remotes/origin/main", base)
    head = _commit(repository, "head.py", "HEAD = 1\n")
    return repository, base, head


def test_manual_base_accepts_only_a_strict_ancestor_commit(
    git_repository: tuple[Path, str, str],
) -> None:
    repository, base, _ = git_repository
    resolver = _load_resolver()

    assert (
        resolver.resolve_mutation_base(
            repository=repository,
            event_name="workflow_dispatch",
            pr_base_sha="",
            manual_base_sha=base,
        )
        == base
    )


def test_empty_manual_base_is_rejected(
    git_repository: tuple[Path, str, str],
) -> None:
    repository, _, _ = git_repository
    resolver = _load_resolver()

    with pytest.raises(ValueError, match="requires a full"):
        resolver.resolve_mutation_base(
            repository=repository,
            event_name="workflow_dispatch",
            pr_base_sha="",
            manual_base_sha="",
        )


def test_push_without_manual_base_falls_back_to_origin_main(
    git_repository: tuple[Path, str, str],
) -> None:
    repository, base, _ = git_repository
    resolver = _load_resolver()

    assert (
        resolver.resolve_mutation_base(
            repository=repository,
            event_name="push",
            pr_base_sha="",
            manual_base_sha="",
        )
        == base
    )


def test_pull_request_base_has_priority_without_manual_ancestry_requirement(
    git_repository: tuple[Path, str, str],
) -> None:
    repository, base, _ = git_repository
    _git(repository, "checkout", "--quiet", "-b", "unmerged-pr-base", base)
    pr_base = _commit(repository, "pr-base.py", "PR_BASE = 1\n")
    _git(repository, "checkout", "--quiet", "main")
    resolver = _load_resolver()

    assert (
        resolver.resolve_mutation_base(
            repository=repository,
            event_name="pull_request",
            pr_base_sha=pr_base,
            manual_base_sha="not-a-sha",
        )
        == pr_base
    )


@pytest.mark.parametrize("candidate", ("not-a-sha", "f" * 40))
def test_manual_base_rejects_malformed_or_unknown_sha(
    git_repository: tuple[Path, str, str], candidate: str
) -> None:
    repository, _, _ = git_repository
    resolver = _load_resolver()

    with pytest.raises(ValueError):
        resolver.resolve_mutation_base(
            repository=repository,
            event_name="workflow_dispatch",
            pr_base_sha="",
            manual_base_sha=candidate,
        )


def test_manual_base_rejects_head_tags_blobs_and_non_ancestors(
    git_repository: tuple[Path, str, str],
) -> None:
    repository, base, head = git_repository
    _git(repository, "tag", "-a", "v1", "-m", "release", base)
    tag = _git(repository, "rev-parse", "v1")
    blob = _git(repository, "hash-object", "-w", "base.py")
    _git(repository, "checkout", "--quiet", "-b", "side", base)
    side = _commit(repository, "side.py", "SIDE = 1\n")
    _git(repository, "checkout", "--quiet", "main")
    resolver = _load_resolver()

    for candidate in (head, tag, blob, side):
        with pytest.raises(ValueError):
            resolver.resolve_mutation_base(
                repository=repository,
                event_name="workflow_dispatch",
                pr_base_sha="",
                manual_base_sha=candidate,
            )


def test_manual_base_is_rejected_outside_manual_dispatch(
    git_repository: tuple[Path, str, str],
) -> None:
    repository, base, _ = git_repository
    resolver = _load_resolver()

    with pytest.raises(ValueError):
        resolver.resolve_mutation_base(
            repository=repository,
            event_name="push",
            pr_base_sha="",
            manual_base_sha=base,
        )
