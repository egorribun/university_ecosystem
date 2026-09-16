#!/usr/bin/env python3
"""Create and validate a provenance-bound Helm dependency artifact.

The nightly mutation matrix uses one producer to fetch the lock-bound chart
archives. Consumers validate this envelope before copying the archives into
their checkout and invoking Helm with ``--skip-refresh``. The validation is
fail-closed: producer identity, archive membership, regular-file status, and
SHA-256 bytes must all match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ARTIFACT_KIND = "helm-dependency-archives"
ARCHIVE_NAMES = ("redis-20.13.4.tgz", "nats-8.5.4.tgz")
ARCHIVE_PATHS = tuple(f"charts/{name}" for name in ARCHIVE_NAMES)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")


class ArtifactValidationError(ValueError):
    """Raised when the dependency artifact is missing, unsafe, or mismatched."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ArtifactValidationError(
            f"unable to hash artifact member: {path}"
        ) from error
    return digest.hexdigest()


def _identity(
    *, commit_sha: str, run_id: str, run_attempt: str, workflow: str
) -> dict[str, str]:
    if _COMMIT_SHA.fullmatch(commit_sha) is None:
        raise ArtifactValidationError("commit_sha must be a lowercase 40-character SHA")
    if _POSITIVE_INTEGER.fullmatch(run_id) is None:
        raise ArtifactValidationError("run_id must be a positive decimal integer")
    if _POSITIVE_INTEGER.fullmatch(run_attempt) is None:
        raise ArtifactValidationError("run_attempt must be a positive decimal integer")
    if not workflow or "\n" in workflow or "\r" in workflow:
        raise ArtifactValidationError("workflow must be a non-empty single-line value")
    return {
        "commit_sha": commit_sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "workflow": workflow,
    }


def _rooted_path(root: Path, relative: str) -> Path:
    if relative not in ARCHIVE_PATHS:
        raise ArtifactValidationError(f"unsupported Helm archive path: {relative!r}")
    root = root.resolve(strict=True)
    target = root / Path(relative)
    current = root
    for component in Path(relative).parts:
        current /= component
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ArtifactValidationError(f"artifact member is unsafe: {relative}")
    try:
        if not target.resolve(strict=False).is_relative_to(root):
            raise ArtifactValidationError(f"artifact member escapes root: {relative}")
    except OSError as error:
        raise ArtifactValidationError(
            f"unable to resolve artifact member: {relative}"
        ) from error
    return target


def _require_archive(root: Path, relative: str) -> Path:
    target = _rooted_path(root, relative)
    if target.is_symlink() or not target.is_file() or target.stat().st_size == 0:
        raise ArtifactValidationError(
            f"artifact member is missing or unsafe: {relative}"
        )
    return target


def create_artifact_manifest(
    *,
    root: Path,
    output: Path,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
) -> dict[str, Any]:
    """Create the deterministic archive inventory and producer envelope."""

    identity = _identity(
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
    )
    root = root.resolve(strict=True)
    archives = {
        relative: _sha256_file(_require_archive(root, relative))
        for relative in ARCHIVE_PATHS
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": ARTIFACT_KIND,
        "producer": identity,
        "archives": archives,
        "archives_sha256": _digest(archives),
    }
    output = output if output.is_absolute() else root / output
    try:
        output.relative_to(root)
    except ValueError as error:
        raise ArtifactValidationError("manifest must be below artifact root") from error
    if output.is_symlink():
        raise ArtifactValidationError("manifest must not be a symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _read_manifest(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ArtifactValidationError("manifest is missing or unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArtifactValidationError("manifest is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ArtifactValidationError("manifest must be a JSON object")
    return payload


def validate_artifact_manifest(
    *,
    root: Path,
    manifest_path: Path,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    producer_attempt_policy: str = "exact",
) -> dict[str, Any]:
    """Validate identity, exact archive inventory, safety, and bytes."""

    if producer_attempt_policy not in {"exact", "at-or-before"}:
        raise ArtifactValidationError("invalid producer attempt policy")
    expected_identity = _identity(
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
    )
    root = root.resolve(strict=True)
    manifest_path = (
        manifest_path if manifest_path.is_absolute() else root / manifest_path
    )
    try:
        manifest_path.relative_to(root)
    except ValueError as error:
        raise ArtifactValidationError("manifest must be below artifact root") from error
    payload = _read_manifest(manifest_path)
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != ARTIFACT_KIND
    ):
        raise ArtifactValidationError("manifest schema or kind mismatch")
    producer = payload.get("producer")
    if not isinstance(producer, dict) or set(producer) != set(expected_identity):
        raise ArtifactValidationError("producer identity is invalid")
    if any(
        producer[field] != expected_identity[field]
        for field in ("commit_sha", "run_id", "workflow")
    ):
        raise ArtifactValidationError("producer identity mismatch")
    producer_attempt = producer.get("run_attempt")
    if (
        not isinstance(producer_attempt, str)
        or _POSITIVE_INTEGER.fullmatch(producer_attempt) is None
    ):
        raise ArtifactValidationError("producer run_attempt is invalid")
    if producer_attempt_policy == "exact" and producer_attempt != run_attempt:
        raise ArtifactValidationError("producer attempt mismatch")
    if producer_attempt_policy == "at-or-before" and int(producer_attempt) > int(
        run_attempt
    ):
        raise ArtifactValidationError("producer attempt is from the future")
    archives = payload.get("archives")
    if not isinstance(archives, dict) or set(archives) != set(ARCHIVE_PATHS):
        raise ArtifactValidationError(
            "archive inventory does not match the required set"
        )
    if any(
        not isinstance(value, str) or _SHA256.fullmatch(value) is None
        for value in archives.values()
    ):
        raise ArtifactValidationError("archive inventory contains an invalid SHA-256")
    if payload.get("archives_sha256") != _digest(archives):
        raise ArtifactValidationError("archive inventory digest mismatch")
    for relative, expected_hash in archives.items():
        actual_hash = _sha256_file(_require_archive(root, relative))
        if actual_hash != expected_hash:
            raise ArtifactValidationError(f"archive hash mismatch: {relative}")
    return dict(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("root", type=Path)
    create.add_argument("output", type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("root", type=Path)
    validate.add_argument("manifest", type=Path)
    for command in (create, validate):
        command.add_argument("--commit-sha", required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--run-attempt", required=True)
        command.add_argument("--workflow", required=True)
    validate.add_argument(
        "--producer-attempt-policy", choices=("exact", "at-or-before"), default="exact"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            create_artifact_manifest(
                root=args.root,
                output=args.output,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
            )
        else:
            validate_artifact_manifest(
                root=args.root,
                manifest_path=args.manifest,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
                producer_attempt_policy=args.producer_attempt_policy,
            )
    except ArtifactValidationError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
