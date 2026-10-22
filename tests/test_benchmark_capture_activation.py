from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "quality"
    / "benchmark_capture_activation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "benchmark_capture_activation", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("activation module spec is unavailable")
activation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = activation
SPEC.loader.exec_module(activation)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed git executable and tokenized fixture args.
        ("git", "-C", str(repo), *args),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def git_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "Benchmark Contract Test")
    _git(repo, "config", "user.email", "benchmark-contract@example.invalid")

    relative = Path(activation.CAPTURE_HELPER_PATH)
    helper_path = repo / relative
    helper_path.parent.mkdir(parents=True)
    base_bytes = b"print('base helper')\n"
    helper_path.write_bytes(base_bytes)
    (repo / "marker.txt").write_text("base\n", encoding="utf-8")
    base_sha = _commit(repo, "base")

    helper_bytes = b"print('trusted helper v1')\n"
    helper_path.write_bytes(helper_bytes)
    helper_commit = _commit(repo, "reviewed helper only")
    helper_parent = _git(repo, "rev-parse", f"{helper_commit}^")
    helper_tree = _git(repo, "rev-parse", f"{helper_commit}^{{tree}}")
    helper_blob = _git(repo, "rev-parse", f"{helper_commit}:{relative.as_posix()}")
    source_head_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "marker.txt").write_text("activation commit\n", encoding="utf-8")
    candidate_sha = _commit(repo, "activation")

    base_worktree = tmp_path / "base-worktree"
    base_file = base_worktree / relative
    base_file.parent.mkdir(parents=True)
    base_file.write_bytes(base_bytes)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()

    monkeypatch.setattr(activation, "PINNED_HELPER_COMMIT", helper_commit)
    monkeypatch.setattr(activation, "PINNED_HELPER_PARENT", helper_parent)
    monkeypatch.setattr(activation, "PINNED_HELPER_TREE", helper_tree)
    monkeypatch.setattr(activation, "PINNED_HELPER_BLOB", helper_blob)
    monkeypatch.setattr(
        activation, "PINNED_HELPER_SHA256", hashlib.sha256(helper_bytes).hexdigest()
    )
    monkeypatch.setattr(activation, "PINNED_HELPER_SIZE", str(len(helper_bytes)))

    return {
        "repo": repo,
        "relative": relative,
        "base_sha": base_sha,
        "helper_commit": helper_commit,
        "helper_parent": helper_parent,
        "helper_tree": helper_tree,
        "helper_blob": helper_blob,
        "helper_bytes": helper_bytes,
        "source_head_sha": source_head_sha,
        "candidate_sha": candidate_sha,
        "base_worktree": base_worktree,
        "base_file": base_file,
        "runner_temp": runner_temp,
    }


def _eligible_context(**overrides: str) -> dict[str, str]:
    context = {
        "event_name": "pull_request",
        "repository": activation.CANONICAL_REPOSITORY,
        "pull_request_number": "1306",
        "head_repository": activation.CANONICAL_REPOSITORY,
        "head_ref": activation.ACTIVATION_HEAD_REF,
        "base_ref": activation.ACTIVATION_BASE_REF,
    }
    context.update(overrides)
    return context


def _main_push_context(**overrides: str) -> dict[str, str]:
    context = {
        "event_name": "push",
        "repository": activation.CANONICAL_REPOSITORY,
        "push_ref": "refs/heads/main",
        "push_base_ref": "main",
    }
    context.update(overrides)
    return context


def _select(fixture: dict[str, object], context: dict[str, str]):
    return activation.select_capture_helper(
        context=context,
        repo=fixture["repo"],
        base_worktree=fixture["base_worktree"],
        base_sha=fixture["base_sha"],
        source_head_sha=fixture["source_head_sha"],
        candidate_sha=fixture["candidate_sha"],
        base_helper=fixture["base_file"],
        runner_temp=fixture["runner_temp"],
    )


def test_exact_approved_context_selects_identical_pinned_blob_outside_checkout(
    git_fixture: dict[str, object],
) -> None:
    selected = _select(git_fixture, _eligible_context())
    assert selected.origin == "reviewed-immutable-candidate"
    assert selected.commit == git_fixture["helper_commit"]
    assert selected.parent == git_fixture["helper_parent"]
    assert selected.tree == git_fixture["helper_tree"]
    assert selected.blob == git_fixture["helper_blob"]
    assert selected.executable_path.read_bytes() == git_fixture["helper_bytes"]
    assert selected.executable_path.stat().st_mode & 0o222 == 0
    assert selected.executable_path.parent.parent == git_fixture["runner_temp"]
    assert selected.size_bytes == len(git_fixture["helper_bytes"])


@pytest.mark.parametrize(
    "context_change",
    [
        {"head_repository": "attacker/university_ecosystem"},
        {"head_ref": "attacker"},
        {"base_ref": "release"},
    ],
)
def test_target_pr_context_mismatch_fails_instead_of_using_base_helper(
    git_fixture: dict[str, object], context_change: dict[str, str]
) -> None:
    with pytest.raises(
        activation.ActivationError, match="approved_pull_request_context_mismatch"
    ):
        _select(git_fixture, _eligible_context(**context_change))


def test_other_pull_requests_keep_the_immutable_base_helper(
    git_fixture: dict[str, object],
) -> None:
    context = _eligible_context(pull_request_number="1307")
    selected = _select(git_fixture, context)
    assert selected.origin == "immutable-base"
    assert selected.commit == git_fixture["base_sha"]
    assert selected.executable_path == git_fixture["base_file"]
    assert selected.executable_path.read_bytes() == b"print('base helper')\n"


def test_unbound_pin_fails_closed_for_the_approved_pull_request(
    git_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(activation, "PINNED_HELPER_COMMIT", "UNBOUND_HELPER_COMMIT")
    with pytest.raises(activation.ActivationError, match="reviewed_helper_pin_unbound"):
        _select(git_fixture, _eligible_context())


def test_content_pin_mismatch_fails_closed_without_base_fallback(
    git_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(activation, "PINNED_HELPER_SHA256", "f" * 64)
    with pytest.raises(
        activation.ActivationError, match="helper_content_sha256_mismatch"
    ):
        _select(git_fixture, _eligible_context())


@pytest.mark.parametrize(
    ("pin_name", "bad_value", "reason"),
    [
        ("PINNED_HELPER_PARENT", "f" * 40, "helper_parent_pin_mismatch"),
        ("PINNED_HELPER_TREE", "f" * 40, "helper_tree_pin_mismatch"),
        ("PINNED_HELPER_BLOB", "f" * 40, "helper_blob_pin_mismatch"),
        ("PINNED_HELPER_SIZE", "1", "helper_blob_size_mismatch"),
    ],
)
def test_each_commit_tree_blob_and_size_pin_is_independently_enforced(
    git_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    pin_name: str,
    bad_value: str,
    reason: str,
) -> None:
    monkeypatch.setattr(activation, pin_name, bad_value)
    with pytest.raises(activation.ActivationError, match=reason):
        _select(git_fixture, _eligible_context())


def test_trusted_helper_must_be_ancestor_of_source_head_and_candidate(
    git_fixture: dict[str, object],
) -> None:
    repo = git_fixture["repo"]
    _git(repo, "checkout", "--orphan", "unrelated")
    _git(repo, "rm", "-rf", ".")
    relative = git_fixture["relative"]
    unrelated_helper = repo / relative
    unrelated_helper.parent.mkdir(parents=True, exist_ok=True)
    unrelated_helper.write_bytes(b"unrelated\n")
    (repo / "marker.txt").write_text("unrelated\n", encoding="utf-8")
    unrelated_sha = _commit(repo, "unrelated history")
    with pytest.raises(
        activation.ActivationError, match="reviewed_helper_not_in_tested_history"
    ):
        activation.select_capture_helper(
            context=_eligible_context(),
            repo=repo,
            base_worktree=git_fixture["base_worktree"],
            base_sha=git_fixture["base_sha"],
            source_head_sha=unrelated_sha,
            candidate_sha=unrelated_sha,
            base_helper=git_fixture["base_file"],
            runner_temp=git_fixture["runner_temp"],
        )


def test_non_main_push_keeps_the_immutable_base_helper(
    git_fixture: dict[str, object],
) -> None:
    context = _main_push_context(push_ref="refs/heads/release")
    selected = _select(git_fixture, context)
    assert selected.origin == "immutable-base"
    assert selected.executable_path == git_fixture["base_file"]


def test_first_canonical_main_push_uses_the_immutable_pinned_helper(
    git_fixture: dict[str, object],
) -> None:
    candidate_sha = git_fixture["candidate_sha"]
    selected = activation.select_capture_helper(
        context=_main_push_context(),
        repo=git_fixture["repo"],
        base_worktree=git_fixture["base_worktree"],
        base_sha=git_fixture["base_sha"],
        source_head_sha=candidate_sha,
        candidate_sha=candidate_sha,
        base_helper=git_fixture["base_file"],
        runner_temp=git_fixture["runner_temp"],
    )
    assert selected.origin == "reviewed-immutable-candidate"
    assert selected.commit == git_fixture["helper_commit"]
    assert selected.executable_path.read_bytes() == git_fixture["helper_bytes"]


def test_noncanonical_main_push_keeps_the_immutable_base_helper(
    git_fixture: dict[str, object],
) -> None:
    selected = _select(
        git_fixture,
        _main_push_context(repository="attacker/university_ecosystem"),
    )
    assert selected.origin == "immutable-base"
    assert selected.executable_path == git_fixture["base_file"]


def test_main_push_requires_source_head_to_equal_candidate(
    git_fixture: dict[str, object],
) -> None:
    with pytest.raises(
        activation.ActivationError, match="main_push_source_candidate_mismatch"
    ):
        activation.select_capture_helper(
            context=_main_push_context(),
            repo=git_fixture["repo"],
            base_worktree=git_fixture["base_worktree"],
            base_sha=git_fixture["base_sha"],
            source_head_sha=git_fixture["source_head_sha"],
            candidate_sha=git_fixture["candidate_sha"],
            base_helper=git_fixture["base_file"],
            runner_temp=git_fixture["runner_temp"],
        )


def test_main_push_requires_the_ref_name_to_match_the_full_main_ref(
    git_fixture: dict[str, object],
) -> None:
    with pytest.raises(
        activation.ActivationError, match="approved_main_push_context_mismatch"
    ):
        _select(git_fixture, _main_push_context(push_base_ref="release"))


def test_main_push_before_helper_merge_uses_immutable_base_helper(
    git_fixture: dict[str, object],
) -> None:
    repo = git_fixture["repo"]
    _git(repo, "checkout", "-b", "main-before-helper", git_fixture["base_sha"])
    (repo / "marker.txt").write_text("main before helper\n", encoding="utf-8")
    before_helper_sha = _commit(repo, "main change before helper merge")

    selected = activation.select_capture_helper(
        context=_main_push_context(),
        repo=repo,
        base_worktree=git_fixture["base_worktree"],
        base_sha=git_fixture["base_sha"],
        source_head_sha=before_helper_sha,
        candidate_sha=before_helper_sha,
        base_helper=git_fixture["base_file"],
        runner_temp=git_fixture["runner_temp"],
    )
    assert selected.origin == "immutable-base"
    assert selected.executable_path == git_fixture["base_file"]


def test_later_main_push_uses_its_pinned_base_helper(
    git_fixture: dict[str, object],
) -> None:
    base_worktree = git_fixture["runner_temp"] / "later-main-base"
    base_helper = base_worktree / git_fixture["relative"]
    base_helper.parent.mkdir(parents=True)
    base_helper.write_bytes(git_fixture["helper_bytes"])
    candidate_sha = git_fixture["candidate_sha"]

    selected = activation.select_capture_helper(
        context=_main_push_context(),
        repo=git_fixture["repo"],
        base_worktree=base_worktree,
        base_sha=git_fixture["helper_commit"],
        source_head_sha=candidate_sha,
        candidate_sha=candidate_sha,
        base_helper=base_helper,
        runner_temp=git_fixture["runner_temp"],
    )
    assert selected.origin == "immutable-base"
    assert selected.commit == git_fixture["helper_commit"]
    assert selected.executable_path.read_bytes() == git_fixture["helper_bytes"]


def test_first_main_transition_pin_mismatch_fails_without_base_fallback(
    git_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(activation, "PINNED_HELPER_SHA256", "f" * 64)
    candidate_sha = git_fixture["candidate_sha"]
    with pytest.raises(
        activation.ActivationError, match="helper_content_sha256_mismatch"
    ):
        activation.select_capture_helper(
            context=_main_push_context(),
            repo=git_fixture["repo"],
            base_worktree=git_fixture["base_worktree"],
            base_sha=git_fixture["base_sha"],
            source_head_sha=candidate_sha,
            candidate_sha=candidate_sha,
            base_helper=git_fixture["base_file"],
            runner_temp=git_fixture["runner_temp"],
        )


def test_cleanup_removes_only_a_direct_child_of_runner_temp(tmp_path: Path) -> None:
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    helper_dir = runner_temp / "quality-pinned-capture-test"
    helper_dir.mkdir()
    (helper_dir / "partial.bin").write_bytes(b"partial")

    activation._cleanup_helper_dir(helper_dir, runner_temp)

    assert not helper_dir.exists()


def test_cleanup_preserves_a_directory_outside_runner_temp(tmp_path: Path) -> None:
    runner_temp = tmp_path / "runner-temp"
    outside = tmp_path / "outside"
    runner_temp.mkdir()
    outside.mkdir()
    marker = outside / "preserve.txt"
    marker.write_text("keep", encoding="utf-8")

    activation._cleanup_helper_dir(outside, runner_temp)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_cleanup_preserves_reparse_helper_path_before_recursive_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    helper_dir = runner_temp / "quality-pinned-capture-test"
    helper_dir.mkdir()
    marker = helper_dir / "preserve.txt"
    marker.write_text("keep", encoding="utf-8")
    original_check = activation._is_reparse_point

    def mark_helper_as_reparse(path: Path) -> bool:
        return path == helper_dir or original_check(path)

    monkeypatch.setattr(activation, "_is_reparse_point", mark_helper_as_reparse)

    activation._cleanup_helper_dir(helper_dir, runner_temp)

    assert marker.read_text(encoding="utf-8") == "keep"
