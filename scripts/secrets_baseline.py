"""Cross-platform canonicalization for detect-secrets baseline documents."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any

DEFAULT_LOCK_TIMEOUT_SECONDS = 900.0
DEFAULT_LOCK_RETRY_SECONDS = 0.1


def canonical_path(value: str) -> str:
    """Return the repository path spelling shared by Windows and POSIX jobs."""
    return "/".join(part for part in value.replace("\\", "/").split("/") if part)


def canonicalize_document(document: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize result keys/findings and merge separator-only duplicates."""
    canonical = deepcopy(document)
    raw_results = canonical.get("results", {})
    if not isinstance(raw_results, dict):
        raise ValueError("detect-secrets baseline results must be an object")

    merged: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[str]] = {}
    for raw_path, raw_findings in raw_results.items():
        if not isinstance(raw_path, str) or not isinstance(raw_findings, list):
            raise ValueError("detect-secrets baseline entries must map paths to lists")
        path = canonical_path(raw_path)
        if not path:
            raise ValueError("detect-secrets baseline contains an empty result path")
        findings = merged.setdefault(path, [])
        fingerprints = seen.setdefault(path, set())
        for raw_finding in raw_findings:
            if not isinstance(raw_finding, dict):
                raise ValueError("detect-secrets findings must be objects")
            finding = deepcopy(raw_finding)
            filename = finding.get("filename")
            if isinstance(filename, str):
                finding["filename"] = canonical_path(filename)
            fingerprint = json.dumps(finding, sort_keys=True, separators=(",", ":"))
            if fingerprint not in fingerprints:
                fingerprints.add(fingerprint)
                findings.append(finding)

    canonical["results"] = {path: merged[path] for path in sorted(merged)}
    return canonical


@contextmanager
def _baseline_lock(
    path: Path,
    *,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    retry_interval_seconds: float = DEFAULT_LOCK_RETRY_SECONDS,
) -> Iterator[None]:
    if timeout_seconds < 0 or retry_interval_seconds <= 0:
        raise ValueError(
            "baseline lock timeout must be non-negative and retry positive"
        )
    lock_id = sha256(str(path.resolve()).encode("utf-8")).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"detect-secrets-{lock_id}.lock"
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()

            def try_acquire() -> None:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)

            _acquire_with_retry(
                try_acquire,
                timeout_seconds=timeout_seconds,
                retry_interval_seconds=retry_interval_seconds,
            )
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def try_acquire() -> None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            _acquire_with_retry(
                try_acquire,
                timeout_seconds=timeout_seconds,
                retry_interval_seconds=retry_interval_seconds,
            )
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _acquire_with_retry(
    try_acquire: Callable[[], None],
    *,
    timeout_seconds: float,
    retry_interval_seconds: float,
    clock: Callable[[], float] = monotonic,
    wait: Callable[[float], object] | None = None,
) -> None:
    deadline = clock() + timeout_seconds
    waiter = wait or Event().wait
    while True:
        try:
            try_acquire()
            return
        except OSError as error:
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"timed out after {timeout_seconds:g}s waiting for baseline lock"
                ) from error
            waiter(min(retry_interval_seconds, remaining))


def _replace_if_unchanged(
    path: Path, temporary_path: Path, expected_content: bytes
) -> bool:
    if path.read_bytes() != expected_content:
        return False
    os.replace(temporary_path, path)
    return True


def _canonicalize_baseline_file_unlocked(path: Path) -> bool:
    for _attempt in range(3):
        original = path.read_bytes()
        document = json.loads(original.decode("utf-8"))
        rendered = (
            json.dumps(canonicalize_document(document), indent=2) + "\n"
        ).encode()
        if original == rendered:
            return False

        mode = stat.S_IMODE(path.stat().st_mode)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(rendered)
            os.chmod(temporary_path, mode)
            if _replace_if_unchanged(path, temporary_path, original):
                return True
        finally:
            temporary_path.unlink(missing_ok=True)
    raise RuntimeError("baseline changed repeatedly while being canonicalized")


def canonicalize_baseline_file(path: Path) -> bool:
    """Atomically rewrite a baseline while holding its interprocess lock."""
    with _baseline_lock(path):
        return _canonicalize_baseline_file_unlocked(path)
