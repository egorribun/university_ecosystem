from pathlib import Path


def test_pre_commit_aborts_when_lint_staged_fails() -> None:
    hook = Path(".husky/pre-commit").read_text(encoding="utf-8")
    lines = hook.splitlines()

    assert lines[0] == "#!/usr/bin/env sh"
    assert lines[1] == "set -eu"
    assert hook.index("set -eu") < hook.index("npm --prefix frontend run lint-staged")
