from pathlib import Path


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
