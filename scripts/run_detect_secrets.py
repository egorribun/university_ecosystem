#!/usr/bin/env python3
"""Run one cross-platform detect-secrets scan and normalize its baseline."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from scripts.secrets_baseline import (
        _baseline_lock,
        _canonicalize_baseline_file_unlocked,
    )
else:
    from secrets_baseline import _baseline_lock, _canonicalize_baseline_file_unlocked

_VALUE_OPTIONS = frozenset(
    {
        "-C",
        "-c",
        "--baseline",
        "-p",
        "--plugin",
        "--base64-limit",
        "--hex-limit",
        "--disable-plugin",
        "--exclude-lines",
        "--exclude-files",
        "--exclude-secrets",
        "-f",
        "--filter",
        "--disable-filter",
    }
)
_PATH_VALUE_OPTIONS = frozenset(
    {"-C", "--baseline", "-p", "--plugin", "-f", "--filter"}
)


def normalize_detect_secrets_arguments(arguments: list[str]) -> list[str]:
    """Normalize only filenames and path-valued options, never regex values."""
    normalized: list[str] = []
    value_for: str | None = None
    for argument in arguments:
        if value_for is not None:
            normalized.append(
                argument.replace("\\", "/")
                if value_for in _PATH_VALUE_OPTIONS
                else argument
            )
            value_for = None
            continue
        if argument.startswith("-"):
            if argument.startswith("-C") and len(argument) > 2:
                prefix = "-C=" if argument.startswith("-C=") else "-C"
                value = argument[len(prefix) :].replace("\\", "/")
                normalized.append(f"{prefix}{value}")
                continue
            option, separator, value = argument.partition("=")
            if separator:
                normalized_value = (
                    value.replace("\\", "/") if option in _PATH_VALUE_OPTIONS else value
                )
                normalized.append(f"{option}={normalized_value}")
            else:
                normalized.append(argument)
                if option in _VALUE_OPTIONS:
                    value_for = option
            continue
        normalized.append(argument.replace("\\", "/"))
    return normalized


def _detect_context_values(arguments: list[str]) -> tuple[str | None, str | None]:
    custom_root: str | None = None
    baseline: str | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            break
        if argument in {"-C", "--baseline"}:
            if index + 1 < len(arguments):
                value = arguments[index + 1]
                if argument == "-C":
                    custom_root = value
                else:
                    baseline = value
            index += 2
            continue
        if argument.startswith("-C="):
            custom_root = argument[3:]
        elif argument.startswith("-C") and len(argument) > 2:
            custom_root = argument[2:]
        elif argument.startswith("--baseline="):
            baseline = argument.partition("=")[2]
        elif argument in _VALUE_OPTIONS:
            index += 2
            continue
        index += 1
    return custom_root, baseline


def _runner_arguments(arguments: list[str]) -> list[str]:
    """Remove wrapper-only custom-root options before invoking detect-secrets."""
    runner_arguments: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            runner_arguments.extend(arguments[index:])
            break
        if argument == "-C":
            index += 2
            continue
        if argument.startswith("-C") and len(argument) > 2:
            index += 1
            continue
        runner_arguments.append(argument)
        index += 1
    return runner_arguments


def _effective_root(arguments: list[str], invocation_root: Path) -> Path:
    custom_root, _baseline = _detect_context_values(arguments)
    if not custom_root:
        return invocation_root.resolve()
    root = Path(custom_root)
    if not root.is_absolute():
        root = invocation_root / root
    return root.resolve()


def _baseline_path(
    arguments: list[str], invocation_root: Path | None = None
) -> Path | None:
    invocation = (invocation_root or Path.cwd()).resolve()
    _custom_root, baseline_value = _detect_context_values(arguments)
    if not baseline_value:
        return None
    baseline = Path(baseline_value)
    if not baseline.is_absolute():
        baseline = _effective_root(arguments, invocation) / baseline
    return baseline.resolve()


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run_detect_secrets_hook(
    arguments: list[str], runner: Callable[[list[str]], int]
) -> int:
    """Serialize the hook's complete baseline read/modify/write transaction."""
    normalized = normalize_detect_secrets_arguments(arguments)
    invocation_root = Path.cwd().resolve()
    effective_root = _effective_root(normalized, invocation_root)
    baseline = _baseline_path(normalized, invocation_root)
    runner_arguments = _runner_arguments(normalized)
    if baseline is None or not baseline.is_file():
        with _working_directory(effective_root):
            return runner(runner_arguments)
    with _baseline_lock(baseline):
        with _working_directory(effective_root):
            try:
                return runner(runner_arguments)
            finally:
                _canonicalize_baseline_file_unlocked(baseline)


def main(arguments: list[str] | None = None) -> int:
    # Call the hook API in-process so normalized positional filenames are
    # preserved without another platform-dependent command-line roundtrip.
    from detect_secrets.pre_commit_hook import main as detect_secrets_main

    return run_detect_secrets_hook(list(arguments or sys.argv[1:]), detect_secrets_main)


if __name__ == "__main__":
    raise SystemExit(main())
