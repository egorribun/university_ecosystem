#!/usr/bin/env python3
"""Fail CI/pre-commit when obviously weak secrets are committed.

The check targets environment-like files and docker-compose manifests. It flags values
for keys suggesting secrecy (PASSWORD/SECRET/KEY/TOKEN) when they are short or match a
known weak placeholder. Optional fields are skipped if empty to avoid false alarms.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_FILES = [
    ROOT / "root/.env.example",
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
    return value.startswith("your_") or value.startswith("replace_with_")


def _is_weak(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    if not normalized:
        return False
    # Ignore variable expansion like ${VAR} or $VAR as their real
    # strength is checked where they are defined.
    if normalized.startswith("$"):
        return False
    if normalized in BANNED_VALUES:
        return True
    if len(normalized) < MIN_LENGTH and not _is_placeholder(normalized):
        return True
    return False


def _check_lines(path: Path) -> list[str]:
    weak: list[str] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = SECRET_KEY_PATTERN.match(line)
        if match:
            key = match.group("key")
            if key.endswith(SENSITIVE_SUFFIXES):
                value = match.group("value")
                if _is_weak(value):
                    weak.append(f"{path}:{key} uses a weak value")
            continue

        yaml_match = YAML_ENV_PATTERN.match(raw_line)
        if yaml_match:
            key = yaml_match.group(1)
            if key.endswith(SENSITIVE_SUFFIXES):
                value = yaml_match.group(2)
                if _is_weak(value):
                    weak.append(f"{path}:{key} uses a weak value")

    return weak


def main() -> int:
    failures: list[str] = []
    for target in TARGET_FILES:
        if target.exists():
            failures.extend(_check_lines(target))

    if failures:
        print("::error::Weak secret values detected:\n- " + "\n- ".join(failures))
        return 1

    print("Secret strength checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
