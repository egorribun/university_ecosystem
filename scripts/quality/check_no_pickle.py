"""AST guard for direct pickle and _pickle imports and API use."""

from __future__ import annotations

import argparse
import ast
import os
import stat
import sys
import tokenize
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

PICKLE_MODULES = frozenset({"pickle", "_pickle"})
PICKLE_API_NAMES = frozenset(
    {"load", "loads", "dump", "dumps", "Pickler", "Unpickler", "_Unpickler"}
)
ALLOWED_PICKLE_FINDING_COUNT = 0


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str


class ScanError(RuntimeError):
    """Raised when source cannot be enumerated, read, or parsed completely."""


def _attribute_root(expression: ast.expr) -> str | None:
    while isinstance(expression, ast.Attribute):
        expression = expression.value
    if isinstance(expression, ast.Name):
        return expression.id
    return None


def scan_source(source: str, *, filename: str = "<memory>") -> tuple[Finding, ...]:
    """Find direct pickle imports and qualified API use without reading comments."""
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError, RecursionError) as exc:
        line = getattr(exc, "lineno", None) or 1
        message = getattr(exc, "msg", str(exc))
        raise ScanError(
            f"cannot parse Python source at {filename}:{line}: {message}"
        ) from exc

    path = Path(filename)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", maxsplit=1)[0]
                if root in PICKLE_MODULES:
                    findings.append(
                        Finding(
                            path, node.lineno, f"pickle module import: {alias.name}"
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", maxsplit=1)[0]
            if node.level == 0 and root in PICKLE_MODULES:
                findings.append(
                    Finding(path, node.lineno, f"pickle symbol import: from {module}")
                )
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in PICKLE_API_NAMES
            and _attribute_root(node) in PICKLE_MODULES
        ):
            findings.append(Finding(path, node.lineno, f"pickle API use: {node.attr}"))
    return tuple(findings)


def _path_is_junction(path: Path) -> bool:
    try:
        return path.is_junction()
    except OSError as exc:
        raise ScanError(f"cannot inspect source path: {path}") from exc


def _walk_python_files(directory: Path) -> list[Path]:
    files: list[Path] = []

    def on_error(error: OSError) -> None:
        raise ScanError(
            f"cannot traverse source directory: {error.filename or directory}"
        ) from error

    try:
        for current, directory_names, file_names in os.walk(
            directory, followlinks=False, onerror=on_error
        ):
            current_path = Path(current)
            for directory_name in directory_names:
                child = current_path / directory_name
                if child.is_symlink():
                    raise ScanError(f"refusing source directory symlink: {child}")
                if _path_is_junction(child):
                    raise ScanError(f"refusing source directory junction: {child}")
            for file_name in file_names:
                child = current_path / file_name
                if Path(file_name).suffix.lower() != ".py":
                    continue
                if child.is_symlink():
                    raise ScanError(f"refusing source file symlink: {child}")
                files.append(child)
    except ScanError:
        raise
    except OSError as exc:
        raise ScanError(
            f"cannot traverse source directory: {exc.filename or directory}"
        ) from exc

    if not files:
        raise ScanError(f"no Python source files found in directory: {directory}")
    return files


def scan_paths(paths: Iterable[str | Path]) -> tuple[int, tuple[Finding, ...]]:
    inputs = [Path(path) for path in paths]
    if not inputs:
        raise ScanError("at least one scan path is required")

    python_files: dict[str, Path] = {}
    for path in inputs:
        if _path_is_junction(path):
            raise ScanError(f"refusing source path junction: {path}")
        try:
            info = path.lstat()
        except OSError as exc:
            raise ScanError(f"cannot inspect source path: {path}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ScanError(f"refusing source path symlink: {path}")
        if stat.S_ISREG(info.st_mode):
            if path.suffix.lower() != ".py":
                raise ScanError(f"scan file is not Python source: {path}")
            candidates = [path]
        elif stat.S_ISDIR(info.st_mode):
            candidates = _walk_python_files(path)
        else:
            raise ScanError(f"scan path is not a regular file or directory: {path}")

        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ScanError(f"cannot inspect source path: {candidate}") from exc
            python_files.setdefault(os.path.normcase(str(resolved)), resolved)

    findings: list[Finding] = []
    ordered_files = sorted(python_files.values(), key=lambda item: str(item))
    for path in ordered_files:
        try:
            with tokenize.open(path) as source_file:
                source = source_file.read()
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise ScanError(f"cannot read Python source: {path}") from exc
        findings.extend(scan_source(source, filename=str(path)))
    return len(ordered_files), tuple(findings)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject pickle use in Python source.")
    parser.add_argument("paths", nargs="+", help="Python files or source directories")
    args = parser.parse_args(argv)
    try:
        file_count, findings = scan_paths(args.paths)
    except ScanError as exc:
        print(f"no_pickle_scan_error: {exc}", file=sys.stderr)
        return 2

    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.message}")
    print(
        "no_pickle_scan "
        f"files={file_count} violations={len(findings)} "
        f"allowed={ALLOWED_PICKLE_FINDING_COUNT}"
    )
    return 1 if len(findings) > ALLOWED_PICKLE_FINDING_COUNT else 0


if __name__ == "__main__":
    raise SystemExit(main())
