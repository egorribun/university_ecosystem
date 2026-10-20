"""
MOD-28-01 cross-platform gate for obsolete Python 2 comma-style exception bindings.

This lexical check detects the legacy ``except expression, name:`` form without
matching example text in comments or strings. It is not a Python parser; normal
syntax validation remains the responsibility of the repository's lint/test gates.

When Python files are staged, their index bytes take precedence. With no staged
Python paths, the check scans bounded tracked Python worktree files so clean-index
CI runs do not become no-ops.
"""

import io
import os
import shutil
import stat
import subprocess
import sys
import tokenize
from pathlib import Path
from tokenize import TokenInfo

# Keep Git calls and the tracked-source fallback finite; exceeding any limit fails
# closed instead of silently skipping files.
GIT_TIMEOUT_SECONDS = 15
MAX_GIT_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_TRACKED_PYTHON_FILES = 10_000
MAX_PYTHON_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_PYTHON_BYTES = 64 * 1024 * 1024

# Resolve the full git path once at module load; avoids S607 (partial path).
_GIT = shutil.which("git")


class ScanError(RuntimeError):
    """Raised when the input set cannot be checked completely."""


def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    output_limit: int = MAX_GIT_OUTPUT_BYTES,
) -> bytes:
    if _GIT is None:
        raise ScanError("Git executable is unavailable; refusing to skip the check.")
    try:
        result = subprocess.run(  # noqa: S603  # trusted git command, no shell=True
            [_GIT, *args],
            cwd=cwd,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanError("Unable to complete the Git source query.") from exc

    if result.returncode != 0:
        raise ScanError("Git source query failed; refusing to skip the check.")
    if len(result.stdout) > output_limit:
        raise ScanError("Git source query exceeded the configured output limit.")
    return result.stdout


def _repository_root() -> Path:
    output = _run_git(["rev-parse", "--show-toplevel"], output_limit=4096)
    try:
        return Path(os.fsdecode(output.rstrip(b"\r\n"))).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise ScanError("Git returned an invalid repository root.") from exc


def _decode_path_list(output: bytes) -> list[str]:
    paths = [os.fsdecode(item) for item in output.split(b"\0") if item]
    if len(paths) > MAX_TRACKED_PYTHON_FILES:
        raise ScanError("Python file count exceeded the configured scan limit.")
    return paths


def list_staged_python_files(repo_root: Path) -> list[str]:
    """Return staged regular-file Python paths, rejecting unresolved/type changes."""
    unmerged = _run_git(
        ["ls-files", "--unmerged", "--full-name", "-z", "--", "*.py"],
        cwd=repo_root,
    )
    if unmerged:
        raise ScanError("A Python index path has unresolved merge stages.")

    output = _run_git(
        ["diff", "--cached", "--raw", "-z", "--", "*.py"],
        cwd=repo_root,
    )
    if not output:
        return []
    if not output.endswith(b"\0"):
        raise ScanError("Git returned an incomplete staged Python path list.")

    fields = output[:-1].split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        header = fields[index]
        index += 1
        if not header.startswith(b":"):
            raise ScanError("Git returned an invalid staged Python metadata record.")
        metadata = header[1:].split()
        if len(metadata) != 5:
            raise ScanError("Git returned an invalid staged Python metadata record.")
        old_mode, new_mode, _old_object, _new_object, raw_status = metadata
        status = os.fsdecode(raw_status)
        if status in {"A", "M", "D", "T", "U", "X", "B"}:
            path_count = 1
        elif status.startswith(("R", "C")) and status[1:].isdigit():
            path_count = 2
        else:
            raise ScanError("Git returned an unsupported staged Python change status.")
        if index + path_count > len(fields) or any(
            not fields[path_index] for path_index in range(index, index + path_count)
        ):
            raise ScanError("Git returned an incomplete staged Python path list.")

        changed_paths = fields[index : index + path_count]
        index += path_count
        if status == "D":
            continue
        if status in {"T", "U", "X", "B"}:
            raise ScanError(
                "A staged Python path has an unsupported type or index state."
            )
        if old_mode not in {b"000000", b"100644", b"100755", b"120000", b"160000"}:
            raise ScanError("Git returned an unsupported staged Python file mode.")
        if new_mode not in {b"100644", b"100755"}:
            raise ScanError("A staged Python path is not a regular file.")

        # Rename/copy status carries old and new paths; only the destination is
        # the content present in the index and must be checked.
        destination = changed_paths[-1]
        paths.append(os.fsdecode(destination))
        if len(paths) > MAX_TRACKED_PYTHON_FILES:
            raise ScanError("Python file count exceeded the configured scan limit.")
    return paths


def list_tracked_python_files(repo_root: Path) -> list[str]:
    """Return the bounded index path list used by clean-index CI fallback."""
    output = _run_git(["ls-files", "--full-name", "-z", "--", "*.py"], cwd=repo_root)
    return _decode_path_list(output)


def read_staged_content(repo_root: Path, filepath: str) -> bytes:
    """Read staged (index) bytes — not the working tree version."""
    return _run_git(
        ["show", f":{filepath}"], cwd=repo_root, output_limit=MAX_PYTHON_FILE_BYTES
    )


def _stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Fields used to detect path/descriptor replacement or mutation during read."""
    if os.name == "nt":
        change_time = getattr(metadata, "st_birthtime_ns", metadata.st_ctime_ns)
    else:
        change_time = metadata.st_ctime_ns
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        change_time,
    )


def _is_reparse_point(path: Path, metadata: os.stat_result) -> bool:
    if stat.S_ISLNK(metadata.st_mode):
        return True
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if getattr(metadata, "st_file_attributes", 0) & reparse_attribute:
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is None:
        return False
    try:
        return bool(is_junction(path))
    except OSError as exc:
        raise ScanError("Unable to inspect a tracked Python path component.") from exc


def _inspect_worktree_path(
    repo_root: Path, filepath: str
) -> tuple[Path, os.stat_result]:
    relative_path = Path(filepath)
    if (
        not filepath
        or "\\" in filepath
        or relative_path.is_absolute()
        or relative_path.drive
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise ScanError("Tracked Python path is not a safe repository-relative path.")

    try:
        root = repo_root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ScanError("Unable to validate the repository root.") from exc
    path = root.joinpath(*relative_path.parts)
    current = root
    metadata: os.stat_result | None = None
    for index, part in enumerate(relative_path.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError as exc:
            raise ScanError("A tracked Python worktree file is missing.") from exc
        except OSError as exc:
            raise ScanError(
                "Unable to inspect a tracked Python worktree path."
            ) from exc

        if _is_reparse_point(current, metadata):
            raise ScanError(
                "Tracked Python paths cannot traverse symbolic links or junctions."
            )
        is_final = index == len(relative_path.parts) - 1
        if is_final and not stat.S_ISREG(metadata.st_mode):
            raise ScanError("Tracked Python worktree paths must be regular files.")
        if not is_final and not stat.S_ISDIR(metadata.st_mode):
            raise ScanError("Tracked Python path ancestors must be directories.")

    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ScanError("Tracked Python path resolves outside the repository.")
    except (OSError, RuntimeError, ValueError) as exc:
        raise ScanError("Unable to validate a tracked Python worktree path.") from exc

    if metadata is None:
        raise ScanError("Tracked Python path is empty.")
    return path, metadata


def read_worktree_content(repo_root: Path, filepath: str) -> bytes:
    """Read one bounded regular file and detect replacement or mutation mid-read."""
    path, path_before = _inspect_worktree_path(repo_root, filepath)
    if path_before.st_size > MAX_PYTHON_FILE_BYTES:
        raise ScanError("Tracked Python file exceeded the configured size limit.")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScanError(
            "Unable to open a tracked Python worktree file safely."
        ) from exc
    try:
        descriptor_before = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_before.st_mode) or _stat_identity(
            descriptor_before
        ) != _stat_identity(path_before):
            raise ScanError("Tracked Python path changed before it could be read.")

        chunks: list[bytes] = []
        total = 0
        while total <= MAX_PYTHON_FILE_BYTES:
            chunk = os.read(
                descriptor, min(64 * 1024, MAX_PYTHON_FILE_BYTES + 1 - total)
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > MAX_PYTHON_FILE_BYTES:
            raise ScanError("Tracked Python file exceeded the configured size limit.")

        descriptor_after = os.fstat(descriptor)
        _, path_after = _inspect_worktree_path(repo_root, filepath)
        if _stat_identity(descriptor_after) != _stat_identity(
            descriptor_before
        ) or _stat_identity(path_after) != _stat_identity(descriptor_before):
            raise ScanError("Tracked Python file changed while it was being read.")
        content = b"".join(chunks)
    except OSError as exc:
        raise ScanError("Unable to read a tracked Python worktree file.") from exc
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            raise ScanError(
                "Unable to close a tracked Python worktree file safely."
            ) from exc
    return content


def _has_legacy_except_binding(tokens: list[TokenInfo], start: int) -> bool:
    """Find a top-level comma binding after ``except`` and before its colon."""
    depth = 0
    for index in range(start + 1, len(tokens)):
        token = tokens[index]
        if token.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            return False
        if token.type == tokenize.OP:
            if token.string in "([{":
                depth += 1
            elif token.string in ")]}":
                depth -= 1
            elif depth == 0 and token.string == ":":
                return False
            elif depth == 0 and token.string == ",":
                if index + 2 >= len(tokens):
                    return False
                target, colon = tokens[index + 1 : index + 3]
                return (
                    target.type == tokenize.NAME
                    and colon.type == tokenize.OP
                    and colon.string == ":"
                )
    return False


def check_content(filepath: str, content: bytes) -> list[str]:
    """Check Python tokens, excluding comment/string contents by construction."""
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(content).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, UnicodeError) as exc:
        raise ScanError(f"Unable to tokenize tracked Python file: {filepath}.") from exc

    encoding = next(token.string for token in tokens if token.type == tokenize.ENCODING)
    try:
        lines = content.decode(encoding).splitlines()
    except (LookupError, UnicodeError) as exc:
        raise ScanError(f"Unable to decode tracked Python file: {filepath}.") from exc
    violations: list[str] = []
    for index, token in enumerate(tokens):
        if token.type == tokenize.NAME and token.string == "except":
            if _has_legacy_except_binding(tokens, index):
                line = (
                    lines[token.start[0] - 1].rstrip()
                    if token.start[0] <= len(lines)
                    else ""
                )
                violations.append(f"{filepath}:{token.start[0]}: {line}")
    return violations


def _scan_files(
    repo_root: Path,
    paths: list[str],
    *,
    staged: bool,
) -> list[str]:
    total_bytes = 0
    all_violations: list[str] = []
    for filepath in paths:
        content = (
            read_staged_content(repo_root, filepath)
            if staged
            else read_worktree_content(repo_root, filepath)
        )
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_PYTHON_BYTES:
            raise ScanError("Python source total exceeded the configured scan limit.")
        all_violations.extend(check_content(filepath, content))
    return all_violations


def main() -> None:
    try:
        repo_root = _repository_root()
        staged_files = list_staged_python_files(repo_root)
        if staged_files:
            all_violations = _scan_files(repo_root, staged_files, staged=True)
        else:
            tracked_files = list_tracked_python_files(repo_root)
            all_violations = _scan_files(repo_root, tracked_files, staged=False)
    except ScanError as exc:
        print(f"Python 2 except check could not complete: {exc}", file=sys.stderr)
        sys.exit(1)

    if all_violations:
        print("Python 2 except syntax found:")
        for violation in all_violations:
            print(f"  {violation}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
