from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

SUPPORTED_MODES = frozenset({"set", "count", "atomic"})


class ProfileError(ValueError):
    """Raised when native Go coverage evidence cannot be merged safely."""


def _fail(message: str) -> NoReturn:
    raise ProfileError(message)


def _read_profile(path: Path) -> tuple[str, list[tuple[str, str]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ProfileError(f"unable to read coverage profile {path}") from error
    if not lines:
        _fail(f"coverage profile {path} is empty")

    header = lines[0]
    if (
        not header.startswith("mode: ")
        or header.removeprefix("mode: ") not in SUPPORTED_MODES
    ):
        _fail(f"invalid coverage mode in {path}")
    mode = header.removeprefix("mode: ")
    records: list[tuple[str, str]] = []
    for line_number, record in enumerate(lines[1:], start=2):
        if not record:
            continue
        try:
            block, statement_text, execution_text = record.rsplit(" ", maxsplit=2)
            statement_count = int(statement_text)
            execution_count = int(execution_text)
        except (TypeError, ValueError) as error:
            raise ProfileError(
                f"malformed coverage record in {path}:{line_number}"
            ) from error
        if not block or ":" not in block or "," not in block:
            _fail(f"malformed coverage record in {path}:{line_number}")
        if statement_count < 0:
            _fail(f"negative statement count in {path}:{line_number}")
        if execution_count < 0:
            _fail(f"negative execution count in {path}:{line_number}")
        records.append((f"{block} {statement_count}", str(execution_count)))
    return mode, records


def merge_profiles(inputs: Sequence[Path], output: Path) -> None:
    """Merge disjoint Go profiles without weakening their native counters."""
    if not inputs:
        _fail("at least one input coverage profile is required")

    resolved_output = output.resolve()
    if any(path.resolve() == resolved_output for path in inputs):
        _fail("output path must differ from every input profile")

    expected_mode: str | None = None
    merged: list[str] = []
    seen_blocks: set[str] = set()
    for path in inputs:
        mode, records = _read_profile(path)
        if expected_mode is None:
            expected_mode = mode
        elif mode != expected_mode:
            _fail(
                f"coverage mode mismatch: expected {expected_mode}, "
                f"found {mode} in {path}"
            )
        for block, execution_count in records:
            if block in seen_blocks:
                _fail(f"duplicate coverage block across input profiles: {block}")
            seen_blocks.add(block)
            merged.append(f"{block} {execution_count}")

    if expected_mode is None:
        _fail("at least one readable coverage profile is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(f"mode: {expected_mode}\n")
            for record in merged:
                temporary.write(f"{record}\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(output)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise ProfileError(
            f"unable to write merged coverage profile {output}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge disjoint Go coverprofiles with strict validation.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        merge_profiles(tuple(args.inputs), args.output)
    except ProfileError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
