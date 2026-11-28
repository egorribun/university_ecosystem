from pathlib import Path

from scripts.check_no_python2_except import _run_git


def test_pre_commit_aborts_when_lint_staged_fails() -> None:
    hook = Path(".husky/pre-commit").read_text(encoding="utf-8")
    lines = hook.splitlines()

    assert lines[0] == "#!/usr/bin/env sh"
    assert lines[1] == "set -eu"
    assert hook.index("set -eu") < hook.index("npm --prefix frontend run lint-staged")


def test_pre_commit_finds_locked_windows_virtualenv_executable() -> None:
    hook = Path(".husky/pre-commit").read_text(encoding="utf-8")

    assert "elif [ -x .venv/Scripts/pre-commit.exe ]; then" in hook
    assert "  ./.venv/Scripts/pre-commit.exe run --hook-stage pre-commit" in hook


def test_pre_commit_is_executable_in_git_index() -> None:
    hook = ".husky/pre-commit"
    staged = _run_git(["ls-files", "--stage", "--", hook], output_limit=4096)
    assert staged.startswith(b"100755 "), f"{hook} must be executable in Git"
