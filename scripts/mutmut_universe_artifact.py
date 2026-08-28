"""Create and validate an attempt-scoped mutmut universe artifact.

The mutmut planner and mutation runners execute in separate GitHub Actions
jobs when a central producer is enabled.  This helper adds a small, explicit
artifact envelope around the generated ``mutants`` files so a consumer cannot
silently reuse a universe from another commit, workflow run or retry attempt.

The envelope is not a replacement for ``mutmut_universe.validate_universe_manifest``:
the latter remains responsible for validating mutmut's source/config/stats
contract.  This module validates transport integrity and provenance before the
runner invokes that existing semantic validator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

ARTIFACT_MANIFEST_SCHEMA_VERSION = 1
MUTMUT_UNIVERSE_MANIFEST_SCHEMA_VERSION = 2
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_POSITIVE_INTEGER_PATTERN = re.compile(r"^[1-9][0-9]*$")
_MUTMUT_MODE = "mutmut"
_EMPTY_MODE = "empty"
_MODES = frozenset({_MUTMUT_MODE, _EMPTY_MODE})
_DEFAULT_UNIVERSE_MANIFEST = "mutants/mutmut-universe.json"
_DEFAULT_STATS_PATH = "mutants/mutmut-stats.json"
_DEFAULT_PLAN_MANIFEST = "mutants/mutmut-incremental-plan/plan-manifest.json"


class ArtifactValidationError(ValueError):
    """Raised when an artifact is missing, tampered with or mis-scoped."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactValidationError(f"unable to hash artifact file {path}") from exc
    return digest.hexdigest()


def _normalize_relative_path(path: Path | str) -> str:
    value = str(path).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    candidate = Path(value)
    # ``Path.is_absolute`` on POSIX does not recognize a Windows drive path;
    # reject both forms because artifact members must stay below ``root``.
    windows_drive = len(value) >= 3 and value[1] == ":" and value[2] == "/"
    if (
        not value
        or value == "."
        or candidate.is_absolute()
        or value.startswith("//")
        or windows_drive
        or ".." in candidate.parts
    ):
        raise ArtifactValidationError(
            f"artifact path must be repository-relative: {value!r}"
        )
    return value


def _safe_target(root: Path, relative_path: Path | str) -> Path:
    normalized = _normalize_relative_path(relative_path)
    root_resolved = root.resolve()
    target = root / Path(normalized)
    try:
        resolved_target = target.resolve()
    except OSError as exc:
        raise ArtifactValidationError(
            f"unable to resolve artifact path: {normalized}"
        ) from exc
    if not resolved_target.is_relative_to(root_resolved):
        raise ArtifactValidationError(
            f"artifact path escapes repository root: {normalized}"
        )
    return target


def _validate_identity(
    *, commit_sha: str, run_id: str, run_attempt: str, workflow: str
) -> dict[str, str]:
    values = {
        "commit_sha": commit_sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "workflow": workflow,
    }
    if not _COMMIT_SHA_PATTERN.fullmatch(commit_sha):
        raise ArtifactValidationError("commit_sha must be a lowercase 40-character SHA")
    if not _POSITIVE_INTEGER_PATTERN.fullmatch(run_id):
        raise ArtifactValidationError("run_id must be a positive decimal integer")
    if not _POSITIVE_INTEGER_PATTERN.fullmatch(run_attempt):
        raise ArtifactValidationError("run_attempt must be a positive decimal integer")
    if not workflow or "\n" in workflow or "\r" in workflow:
        raise ArtifactValidationError("workflow must be a non-empty single-line value")
    return values


def _iter_files(root: Path, includes: Iterable[Path | str]) -> list[str]:
    members: set[str] = set()
    for include in includes:
        normalized = _normalize_relative_path(include)
        target = _safe_target(root, normalized)
        if target.is_symlink():
            raise ArtifactValidationError(
                f"artifact include must not be a symlink: {normalized}"
            )
        if not target.exists():
            raise ArtifactValidationError(f"artifact include is missing: {normalized}")
        if target.is_file():
            members.add(normalized)
            continue
        if not target.is_dir():
            raise ArtifactValidationError(
                f"artifact include is not a regular file or directory: {normalized}"
            )
        try:
            children = sorted(target.rglob("*"), key=lambda path: path.as_posix())
        except OSError as exc:
            raise ArtifactValidationError(
                f"unable to inspect artifact include: {normalized}"
            ) from exc
        for child in children:
            if child.is_symlink():
                raise ArtifactValidationError(
                    f"artifact include contains a symlink: {child}"
                )
            if not child.is_file():
                continue
            relative = _normalize_relative_path(child.relative_to(root))
            members.add(relative)
    return sorted(members)


def _file_inventory(root: Path, members: Iterable[str]) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for member in members:
        target = _safe_target(root, member)
        if target.is_symlink() or not target.is_file():
            raise ArtifactValidationError(
                f"artifact member is not a regular file: {member}"
            )
        inventory[_normalize_relative_path(member)] = _sha256_file(target)
    return inventory


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactValidationError(f"{label} is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"{label} is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise ArtifactValidationError(f"{label} must be a JSON object: {path}")
    return value


def _validate_mutmut_semantics(
    root: Path,
    payload: dict[str, Any],
    files: dict[str, str],
) -> None:
    universe_manifest = payload.get("universe_manifest")
    stats_path = payload.get("stats_path")
    if universe_manifest != _DEFAULT_UNIVERSE_MANIFEST:
        raise ArtifactValidationError("artifact universe_manifest path is unsupported")
    if stats_path != _DEFAULT_STATS_PATH:
        raise ArtifactValidationError("artifact stats_path is unsupported")
    if universe_manifest not in files or stats_path not in files:
        raise ArtifactValidationError(
            "mutmut artifact is missing its universe manifest or merged stats"
        )
    if files[universe_manifest] != _sha256_file(_safe_target(root, universe_manifest)):
        raise ArtifactValidationError("mutmut universe manifest hash is inconsistent")

    manifest = _read_json(
        _safe_target(root, universe_manifest), label="mutmut universe manifest"
    )
    if manifest.get("schema_version") != MUTMUT_UNIVERSE_MANIFEST_SCHEMA_VERSION:
        raise ArtifactValidationError("mutmut universe manifest schema mismatch")
    if manifest.get("stats_sha256") != files[stats_path]:
        raise ArtifactValidationError(
            "mutmut universe manifest does not bind the artifact stats file"
        )
    mutant_count = manifest.get("mutant_count")
    if (
        not isinstance(mutant_count, int)
        or isinstance(mutant_count, bool)
        or mutant_count < 1
    ):
        raise ArtifactValidationError("mutmut universe manifest has no mutants")


def create_artifact_manifest(
    *,
    root: Path,
    output: Path,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    includes: Sequence[Path | str],
    mode: str = _MUTMUT_MODE,
    required_files: Sequence[Path | str] | None = None,
) -> dict[str, Any]:
    """Create a deterministic provenance/integrity envelope for one artifact."""

    if mode not in _MODES:
        raise ArtifactValidationError(f"unsupported artifact mode: {mode!r}")
    identity = _validate_identity(
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
    )
    root = root.resolve()
    output_relative = (
        _normalize_relative_path(output.relative_to(root))
        if output.is_absolute()
        else _normalize_relative_path(output)
    )
    members = _iter_files(root, includes)
    if output_relative in members:
        raise ArtifactValidationError("artifact envelope must not include itself")
    files = _file_inventory(root, members)
    if mode == _EMPTY_MODE and files:
        raise ArtifactValidationError(
            "empty mutmut artifact must not carry universe files"
        )

    if required_files is None:
        required: tuple[str, ...] = (
            (_DEFAULT_UNIVERSE_MANIFEST, _DEFAULT_STATS_PATH, _DEFAULT_PLAN_MANIFEST)
            if mode == _MUTMUT_MODE
            else ()
        )
    else:
        required = tuple(_normalize_relative_path(path) for path in required_files)
    required_sorted = sorted(set(required))
    missing = [path for path in required_sorted if path not in files]
    if missing:
        raise ArtifactValidationError(
            f"artifact is missing required files: {', '.join(missing)}"
        )

    payload: dict[str, Any] = {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "mode": mode,
        "producer": identity,
        "files": files,
        "files_sha256": _digest(files),
        "required_files": required_sorted,
    }
    if mode == _MUTMUT_MODE:
        payload["universe_manifest"] = _DEFAULT_UNIVERSE_MANIFEST
        payload["stats_path"] = _DEFAULT_STATS_PATH
        _validate_mutmut_semantics(root, payload, files)

    output_target = _safe_target(root, output_relative)
    if output_target.is_symlink():
        raise ArtifactValidationError("artifact envelope path must not be a symlink")
    output_target.parent.mkdir(parents=True, exist_ok=True)
    output_target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def validate_artifact_manifest(
    *,
    root: Path,
    manifest_path: Path,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    expected_mode: str | None = None,
) -> dict[str, Any]:
    """Validate provenance, inventory hashes and mutmut semantic binding."""

    if expected_mode is not None and expected_mode not in _MODES:
        raise ArtifactValidationError(
            f"unsupported expected artifact mode: {expected_mode!r}"
        )
    root = root.resolve()
    manifest_relative = (
        _normalize_relative_path(manifest_path.relative_to(root))
        if manifest_path.is_absolute()
        else _normalize_relative_path(manifest_path)
    )
    manifest_target = _safe_target(root, manifest_relative)
    if manifest_target.is_symlink():
        raise ArtifactValidationError("artifact manifest must not be a symlink")
    payload = _read_json(manifest_target, label="artifact manifest")
    if payload.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION:
        raise ArtifactValidationError("artifact manifest schema mismatch")
    mode = payload.get("mode")
    if mode not in _MODES or (expected_mode is not None and mode != expected_mode):
        raise ArtifactValidationError("artifact manifest mode mismatch")

    expected_identity = _validate_identity(
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
    )
    if payload.get("producer") != expected_identity:
        raise ArtifactValidationError("artifact producer identity mismatch")

    raw_files = payload.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        if mode == _EMPTY_MODE and raw_files == {}:
            raw_files = {}
        else:
            raise ArtifactValidationError(
                "artifact files inventory is invalid or empty"
            )
    files: dict[str, str] = {}
    for raw_path, raw_hash in raw_files.items():
        if not isinstance(raw_path, str) or not isinstance(raw_hash, str):
            raise ArtifactValidationError(
                "artifact files inventory has invalid entries"
            )
        normalized = _normalize_relative_path(raw_path)
        if not _SHA256_PATTERN.fullmatch(raw_hash):
            raise ArtifactValidationError(
                f"artifact file hash is invalid: {normalized}"
            )
        if normalized in files:
            raise ArtifactValidationError(
                f"artifact files inventory has duplicate path: {normalized}"
            )
        files[normalized] = raw_hash
    if mode == _EMPTY_MODE and files:
        raise ArtifactValidationError(
            "empty mutmut artifact must not carry universe files"
        )
    if payload.get("files_sha256") != _digest(files):
        raise ArtifactValidationError("artifact files inventory digest mismatch")

    required = payload.get("required_files")
    if not isinstance(required, list) or any(
        not isinstance(path, str) for path in required
    ):
        raise ArtifactValidationError("artifact required_files is invalid")
    required_normalized = sorted(_normalize_relative_path(path) for path in required)
    if required_normalized != sorted(set(required_normalized)):
        raise ArtifactValidationError("artifact required_files contains duplicates")
    missing = [path for path in required_normalized if path not in files]
    if missing:
        raise ArtifactValidationError(
            f"artifact required files are missing from inventory: {', '.join(missing)}"
        )

    for relative, expected_hash in files.items():
        target = _safe_target(root, relative)
        if target.is_symlink() or not target.is_file():
            raise ArtifactValidationError(
                f"artifact member is missing or unsafe: {relative}"
            )
        actual_hash = _sha256_file(target)
        if actual_hash != expected_hash:
            raise ArtifactValidationError(f"artifact member hash mismatch: {relative}")

    if mode == _MUTMUT_MODE:
        _validate_mutmut_semantics(root, payload, files)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "validate"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--root", type=Path, default=Path("."))
        subparser.add_argument("--manifest", type=Path, required=True)
        subparser.add_argument("--commit-sha", required=True)
        subparser.add_argument("--run-id", required=True)
        subparser.add_argument("--run-attempt", required=True)
        subparser.add_argument("--workflow", required=True)
    create = subparsers.choices["create"]
    create.add_argument("--include", type=Path, action="append", default=[])
    create.add_argument("--required-file", type=Path, action="append")
    create.add_argument("--mode", choices=sorted(_MODES), default=_MUTMUT_MODE)
    validate = subparsers.choices["validate"]
    validate.add_argument("--expected-mode", choices=sorted(_MODES))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "create":
            payload = create_artifact_manifest(
                root=args.root,
                output=args.manifest,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
                includes=args.include,
                mode=args.mode,
                required_files=args.required_file,
            )
        else:
            payload = validate_artifact_manifest(
                root=args.root,
                manifest_path=args.manifest,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
                expected_mode=args.expected_mode,
            )
    except (ArtifactValidationError, OSError, ValueError) as exc:
        raise SystemExit(f"ERROR: mutmut artifact contract failed: {exc}") from exc
    print(json.dumps({"mode": payload["mode"], "files": len(payload["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
