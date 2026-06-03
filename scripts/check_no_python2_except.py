"""
MOD-28-01 cross-platform gate: rejects the obsolete Python 2 comma-style
exception binding (the Python 2 comma syntax replaced by ``as`` in Python 3).

Replaces the bash-based hook entry so this check runs identically on Windows
(Git for Windows + Python) and Linux CI — no WSL or /bin/bash required.

Reads staged content via ``git show :file`` to avoid false positives caused by
pre-commit's stash/restore cycle when ruff-format also modifies staged files.
"""

import re
import shutil
import subprocess
import sys

# Matches the Python 2 comma-style exception binding that was replaced by
# ``except <Type> as <name>:`` in Python 3.
PYTHON2_EXCEPT_PATTERN = re.compile(r"except\s+\w+\s*,\s*\w+\s*:")

# Resolve the full git path once at module load; avoids S607 (partial path).
_GIT = shutil.which("git") or "git"


def list_staged_python_files() -> list[str]:
    result = subprocess.run(  # noqa: S603  # trusted git command, no shell=True
        [_GIT, "diff", "--cached", "--name-only", "--diff-filter=ACM", "--", "*.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def read_staged_content(filepath: str) -> str:
    """Read staged (index) content — not the working tree version."""
    result = subprocess.run(  # noqa: S603  # trusted git command, no shell=True
        [_GIT, "show", f":{filepath}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout if result.returncode == 0 else ""


def check_file(filepath: str) -> list[str]:
    content = read_staged_content(filepath)
    violations = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if PYTHON2_EXCEPT_PATTERN.search(line):
            violations.append(f"{filepath}:{lineno}: {line.rstrip()}")
    return violations


def main() -> None:
    staged_files = list_staged_python_files()
    all_violations: list[str] = []
    for filepath in staged_files:
        all_violations.extend(check_file(filepath))

    if all_violations:
        print("Python 2 except syntax found:")
        for violation in all_violations:
            print(f"  {violation}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
