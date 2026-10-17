#!/usr/bin/env python3
"""Fail CI/pre-commit when obviously weak secrets are committed.

The check targets environment-like files and docker-compose manifests. It flags values
for keys suggesting secrecy (PASSWORD/SECRET/KEY/TOKEN) when they are short or match a
known weak placeholder. Optional fields are skipped if empty to avoid false alarms.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_FILES = [
    ROOT / ".env.example",
    ROOT / ".env",
    ROOT / "docker-compose.yml",
]

SENSITIVE_SUFFIXES = ("PASSWORD", "SECRET", "TOKEN", "KEY")
SECRET_KEY_PATTERN = re.compile(r"^(?P<key>[A-Z0-9_]+)=(?P<value>.*)$")
YAML_ENV_PATTERN = re.compile(r"^[ \t-]*([A-Z0-9_]+)\s*:\s*(.+)$")

BANNED_VALUES = {
    "password",
    "devpassword",
    "changeme",
    "secret",
    "university",
}

MIN_LENGTH = 24


def _is_placeholder(value: str) -> bool:
    v = value.lower()
    return (
        v.startswith("your_")
        or v.startswith("replace_with_")
        or v.startswith("change_me")
    )


def _is_weak(value: str, *, allow_placeholders: bool = False) -> bool:
    normalized = value.strip().strip("\"'").strip().lower()
    if not normalized:
        return False
    # Ignore variable expansion like ${VAR} or $VAR as their real
    # strength is checked where they are defined.
    if normalized.startswith("$"):
        return False
    if normalized in BANNED_VALUES:
        return True
    if _is_placeholder(normalized):
        return not allow_placeholders
    return len(normalized) < MIN_LENGTH


def _path_has_symlink_component(path: Path) -> bool:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        if component in ("", "."):
            continue
        if component == "..":
            current = current.parent
            continue
        current = current / component
        if current.is_symlink():
            return True
    return False


def _is_repository_example(path: Path) -> bool:
    example_path = ROOT / ".env.example"
    try:
        candidate = os.path.normcase(os.path.abspath(path))
        expected = os.path.normcase(os.path.abspath(example_path))
        return (
            candidate == expected
            and not example_path.is_symlink()
            and not _path_has_symlink_component(path)
        )
    except (OSError, RuntimeError):
        return False


def _check_lines(path: Path) -> list[str]:
    weak: list[str] = []
    allow_placeholders = _is_repository_example(path)
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = SECRET_KEY_PATTERN.match(line)
        if match:
            key = match.group("key")
            if key.endswith(SENSITIVE_SUFFIXES):
                value = match.group("value")
                if _is_weak(value, allow_placeholders=allow_placeholders):
                    weak.append(f"{path}:{key} uses a weak value")
            continue

        yaml_match = YAML_ENV_PATTERN.match(raw_line)
        if yaml_match:
            key = yaml_match.group(1)
            if key.endswith(SENSITIVE_SUFFIXES):
                value = yaml_match.group(2)
                if _is_weak(value, allow_placeholders=allow_placeholders):
                    weak.append(f"{path}:{key} uses a weak value")

    return weak


def main() -> int:
    failures: list[str] = []
    targets = [Path(f) for f in sys.argv[1:]] if len(sys.argv) > 1 else TARGET_FILES

    for target in targets:
        if target.exists():
            if target.is_file():
                failures.extend(_check_lines(target))
        else:
            # If explicitly passed but missing, that's an error in pre-commit context
            if len(sys.argv) > 1:
                print(f"Warning: requested file {target} does not exist")

    if failures:
        print("::error::Weak secret values detected:\n- " + "\n- ".join(failures))
        return 1

    print("Secret strength checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
