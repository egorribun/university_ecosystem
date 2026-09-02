"""Create and validate a reusable mutmut source universe.

The incremental mutation workflow plans a shard by generating mutmut's complete
source copy and metadata.  ``mutmut run`` normally generates that same universe
again, which is needlessly expensive for a shard containing only a few mutants.
This module records a content-addressed manifest during planning and provides a
fail-closed validation path for reusing the already generated files.

The mutmut package is intentionally not imported at module import time.  Local
contract tests run on Windows, while mutmut itself only supports POSIX runners.
Callers pass the lazily imported mutmut module as ``mutmut_cli``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path, PureWindowsPath
from stat import S_ISLNK
from typing import Any, cast

UNIVERSE_MANIFEST_PATH = Path("mutants/mutmut-universe.json")
# Source/metadata-only manifest shared by the stats matrix and central planner.
# The final universe manifest remains separate and always binds merged stats.
GENERATION_MANIFEST_PATH = Path("mutants/mutmut-generation.json")
# Version 2 adds the content-addressed ``also_copy_inventory`` field.  A
# manifest produced before that field is not safe to reuse, so validation must
# reject it instead of silently accepting an incomplete input inventory.
MANIFEST_SCHEMA_VERSION = 2
GENERATION_MANIFEST_SCHEMA_VERSION = 1

# ``mutmut.configuration.Config`` is a dataclass today.  Keep this fallback
# list for contract-test doubles and future compatible config objects that
# expose settings as class attributes rather than instance attributes.
_CONFIG_FIELD_NAMES = (
    "also_copy",
    "only_mutate",
    "do_not_mutate",
    "do_not_mutate_patterns",
    "max_stack_depth",
    "debug",
    "source_paths",
    "resolved_mutated_source_paths",
    "pytest_add_cli_args",
    "pytest_add_cli_args_test_selection",
    "mutate_only_covered_lines",
    "timeout_multiplier",
    "timeout_constant",
    "type_check_command",
    "use_setproctitle",
    "track_dependencies",
    "dependency_tracking_depth",
    "cache_invalidation_files",
    "cache_invalidation_exclude",
    "on_dependency_change",
    "use_git_change_detection",
)

# ``also_copy`` is intentionally broad in this repository: mutmut's test
# process needs configuration, migration, security and infrastructure files in
# addition to the Python source tree.  Source checkouts can also contain
# interpreter/tool caches created while preparing a job.  Those cache files are
# not inputs to mutation execution and are excluded from the content inventory
# so a planner artifact remains reproducible across isolated CI runners.
_EPHEMERAL_COPY_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "target",
    }
)
_EPHEMERAL_COPY_SUFFIXES = frozenset({".pyc", ".pyo"})


class UniverseValidationError(RuntimeError):
    """Raised when a planner-generated universe cannot be trusted for reuse."""


def _normalize_path(path: Path | str) -> str:
    """Use the same slash-separated path representation on every runner."""

    value = str(path).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _json_value(value: Any) -> Any:
    """Convert mutmut's config values into deterministic JSON-compatible data."""

    if isinstance(value, Path):
        return _normalize_path(value)
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_value(item) for item in value), key=repr)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise UniverseValidationError(f"unable to hash universe file {path}") from exc
    return digest.hexdigest()


def _safe_mutant_path(path: Path | str) -> Path:
    """Resolve a repository-relative path below ``mutants`` safely.

    The generated universe is an ephemeral working tree, but its paths still
    come from mutmut/configuration data.  Refuse absolute paths, traversal and
    symlink escapes before reading or deleting any generated file.
    """

    normalized = _normalize_path(path)
    candidate = Path(normalized)
    if (
        not normalized
        or normalized == "."
        or candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise UniverseValidationError(
            f"mutmut path must be repository-relative: {normalized!r}"
        )

    mutants_root_path = Path("mutants")
    if _is_link_or_junction(mutants_root_path):
        raise UniverseValidationError(
            f"mutants root must not be a symlink or junction: {mutants_root_path}"
        )
    current = mutants_root_path
    for component in candidate.parts:
        current /= component
        if _is_link_or_junction(current):
            raise UniverseValidationError(
                f"generated mutmut path traverses a symlink or junction: {current}"
            )
    mutants_root = mutants_root_path.resolve()
    target = mutants_root_path / candidate
    try:
        resolved_target = target.resolve()
    except OSError as exc:
        raise UniverseValidationError(
            f"unable to resolve generated mutmut path: {target}"
        ) from exc
    if not resolved_target.is_relative_to(mutants_root):
        raise UniverseValidationError(
            f"generated mutmut path escapes mutants directory: {target}"
        )
    return target


def _is_link_or_junction(path: Path) -> bool:
    """Return whether ``path`` is a symlink or Windows directory junction.

    ``Path.exists()`` follows links and returns ``False`` for a broken link, so
    the security checks must use link-aware metadata before any existence or
    content operation.  Junctions are the Windows equivalent of a directory
    symlink and are checked when the running Python exposes ``is_junction``.
    """

    try:
        if S_ISLNK(path.lstat().st_mode):
            return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise UniverseValidationError(
            f"unable to inspect mutmut repository path component: {path}"
        ) from exc

    is_junction = getattr(path, "is_junction", None)
    if not callable(is_junction):
        return False
    try:
        return bool(is_junction())
    except OSError as exc:
        raise UniverseValidationError(
            f"unable to inspect mutmut repository path component: {path}"
        ) from exc


def _safe_repository_path(
    path: Path | str,
    *,
    label: str,
    allow_missing: bool,
) -> Path:
    """Validate a configured path before reading or copying it.

    Configured mutmut paths are repository-relative.  Validate every existing
    component (including intermediate parents) without following symlinks or
    junctions, then resolve the complete path and require it to remain below
    the current checkout.  This rejects both direct links and paths such as
    ``link/outside.py`` where only an intermediate parent is a link.
    """

    normalized = _normalize_path(path)
    try:
        candidate = Path(normalized)
        windows_candidate = PureWindowsPath(normalized)
    except (TypeError, ValueError) as exc:
        raise UniverseValidationError(
            f"{label} must be a repository-relative path: {normalized!r}"
        ) from exc

    if (
        not normalized
        or normalized == "."
        or candidate.is_absolute()
        or windows_candidate.is_absolute()
        or bool(windows_candidate.drive)
        or ".." in candidate.parts
    ):
        raise UniverseValidationError(
            f"{label} must be repository-relative: {normalized!r}"
        )

    checkout = Path.cwd()
    try:
        checkout_resolved = checkout.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise UniverseValidationError(
            f"unable to resolve repository root for {label}: {checkout}"
        ) from exc

    current = checkout
    for component in candidate.parts:
        current /= component
        if _is_link_or_junction(current):
            raise UniverseValidationError(
                f"{label} symlink or junction is not allowed: {current}"
            )

    target = checkout / candidate
    try:
        resolved_target = target.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise UniverseValidationError(f"unable to resolve {label}: {target}") from exc
    if not resolved_target.is_relative_to(checkout_resolved):
        raise UniverseValidationError(f"{label} escapes repository: {target}")

    if not allow_missing:
        try:
            exists = target.exists()
        except OSError as exc:
            raise UniverseValidationError(
                f"unable to inspect {label}: {target}"
            ) from exc
        if not exists:
            raise UniverseValidationError(f"{label} is missing: {target}")
    return candidate


def _configured_entries(raw_entries: Any, *, label: str) -> list[Any]:
    """Normalize a mutmut path setting into a list without splitting strings."""

    if raw_entries is None:
        return []
    if isinstance(raw_entries, (Path, str)):
        return [raw_entries]
    try:
        return list(raw_entries)
    except TypeError as exc:
        raise UniverseValidationError(f"{label} must be iterable") from exc


def _validate_repository_tree(path: Path, *, label: str) -> None:
    """Reject link-like descendants before a recursive mutmut copy."""

    if not path.is_dir():
        return
    try:
        children = sorted(path.rglob("*"), key=_normalize_path)
    except OSError as exc:
        raise UniverseValidationError(
            f"unable to inspect {label} directory: {path}"
        ) from exc
    for child in children:
        _safe_repository_path(
            child,
            label=f"{label} child",
            allow_missing=False,
        )


def validate_configured_paths(config: Any) -> None:
    """Validate mutmut source roots and copy inputs before filesystem access."""

    for raw_entry in _configured_entries(
        getattr(config, "source_paths", None), label="mutmut source_paths"
    ):
        source_root = _safe_repository_path(
            raw_entry,
            label="mutmut source root",
            allow_missing=False,
        )
        _validate_repository_tree(source_root, label="mutmut source root")
    for raw_entry in _configured_entries(
        getattr(config, "also_copy", None), label="mutmut also_copy"
    ):
        copy_root = _safe_repository_path(
            raw_entry,
            label="mutmut also_copy path",
            allow_missing=True,
        )
        if copy_root.exists():
            _validate_repository_tree(copy_root, label="mutmut also_copy path")


def _is_ephemeral_copy_file(root: Path, path: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return bool(
        _EPHEMERAL_COPY_DIRECTORIES.intersection(relative_parts)
        or path.suffix.lower() in _EPHEMERAL_COPY_SUFFIXES
    )


def _also_copy_inventory(config: Any) -> dict[str, dict[str, Any]]:
    """Hash every configured ``also_copy`` input deterministically.

    A directory entry records all regular files below it, not just the
    directory mtime.  This catches changes such as the historical omission of
    ``security/audit-allowlist.yaml`` while keeping generated interpreter/tool
    caches out of the cross-runner contract.
    """

    raw_entries = getattr(config, "also_copy", None)
    if raw_entries is None:
        return {}

    inventory: dict[str, dict[str, Any]] = {}
    entries = _configured_entries(raw_entries, label="mutmut also_copy")

    for raw_entry in entries:
        normalized = _normalize_path(raw_entry)
        candidate = _safe_repository_path(
            raw_entry,
            label="mutmut also_copy path",
            allow_missing=True,
        )
        if not candidate.exists():
            # mutmut appends optional compatibility paths (``test/``,
            # ``setup.cfg`` and several lockfiles) to every configuration and
            # silently skips paths that are absent.  Preserve that documented
            # behavior while recording the absence so a newly created file in
            # a later runner still invalidates the manifest.
            inventory[normalized] = {"kind": "missing"}
            continue
        if candidate.is_file():
            inventory[normalized] = {
                "kind": "file",
                "sha256": _sha256_file(candidate),
            }
            continue
        if not candidate.is_dir():
            raise UniverseValidationError(
                f"mutmut also_copy input is not a regular file or directory: {candidate}"
            )

        files: dict[str, str] = {}
        try:
            children = sorted(
                candidate.rglob("*"), key=lambda path: _normalize_path(path)
            )
        except OSError as exc:
            raise UniverseValidationError(
                f"unable to inspect mutmut also_copy directory: {candidate}"
            ) from exc
        for child in children:
            _safe_repository_path(
                child,
                label="mutmut also_copy child",
                allow_missing=False,
            )
            if not child.is_file() or _is_ephemeral_copy_file(candidate, child):
                continue
            relative = _normalize_path(child.relative_to(candidate))
            files[relative] = _sha256_file(child)
        inventory[normalized] = {"kind": "directory", "files": files}

    return inventory


def prepare_mutants_directory(mutmut_cli: Any) -> None:
    """Validate inputs and remove stale files before a fresh mutmut copy.

    mutmut deliberately keeps an existing generated file when its mtime is
    newer than the source.  That optimization is unsafe for an independently
    planned shard: a stale file can silently yield stale metadata and a false
    manifest.  Validate configured source/copy paths before mutmut reads them,
    then delete only paths corresponding to the current source inventory;
    unexpected directories/symlinks fail closed instead of being followed.
    """

    config = mutmut_cli.Config.get()
    validate_configured_paths(config)
    mutants_root = Path("mutants")
    if _is_link_or_junction(mutants_root):
        raise UniverseValidationError(
            f"mutants root must not be a symlink or junction: {mutants_root}"
        )
    mutants_root.mkdir(parents=True, exist_ok=True)
    for source_path in mutmut_cli.walk_source_files():
        _safe_repository_path(
            source_path,
            label="mutmut source file",
            allow_missing=False,
        )
        generated = _safe_mutant_path(source_path)
        for candidate in (
            generated,
            generated.with_name(generated.name + ".meta"),
            generated.with_name(generated.name + ".spans"),
        ):
            if not candidate.exists() and not candidate.is_symlink():
                continue
            if candidate.is_symlink() or candidate.is_dir():
                raise UniverseValidationError(
                    f"unexpected generated mutmut path type: {candidate}"
                )
            try:
                candidate.unlink()
            except OSError as exc:
                raise UniverseValidationError(
                    f"unable to remove stale generated mutmut file: {candidate}"
                ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _source_file_hashes(paths: Iterable[Path]) -> dict[str, str]:
    normalized_paths = sorted({_normalize_path(path) for path in paths})
    return {
        path: _sha256_file(
            _safe_repository_path(
                path,
                label="mutmut source file",
                allow_missing=False,
            )
        )
        for path in normalized_paths
    }


def _mutated_file_hashes(paths: Iterable[Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted({_normalize_path(path) for path in paths}):
        generated = _safe_mutant_path(path)
        if not generated.is_file():
            raise UniverseValidationError(
                f"generated mutmut source is missing: {generated}"
            )
        hashes[path] = _sha256_file(generated)
    return hashes


def _config_snapshot(config: Any) -> dict[str, Any]:
    """Snapshot all user-configurable mutmut fields that affect generated code."""

    if is_dataclass(config):
        values = {
            field.name: getattr(config, field.name)
            for field in fields(config)
            if hasattr(config, field.name)
        }
    else:
        values = dict(vars(config)) if hasattr(config, "__dict__") else {}
        # Some lightweight Config-compatible objects expose settings on the
        # type.  Include those known settings instead of silently recording an
        # empty snapshot and accepting a changed generation contract.
        values.update(
            {
                name: getattr(config, name)
                for name in _CONFIG_FIELD_NAMES
                if hasattr(config, name)
            }
        )
    # This is derived from cwd/source_paths and changes between the source and
    # ``mutants`` trees; the canonical source_paths value is retained instead.
    values = {
        key: value
        for key, value in values.items()
        if key != "resolved_mutated_source_paths"
    }
    return cast(dict[str, Any], _json_value(values))


def _config_fingerprint(config: Any) -> dict[str, Any]:
    method = getattr(config, "config_fingerprint", None)
    if not callable(method):
        return {}
    return cast(dict[str, Any], _json_value(method()))


def _mutmut_version() -> str:
    try:
        return importlib_metadata.version("mutmut")
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


def _load_metadata(mutmut_cli: Any, path: Path, metadata_path: Path) -> Any:
    """Load one mutmut metadata file and normalize malformed input failures."""

    try:
        data = mutmut_cli.SourceFileMutationData(path=path)
        data.load()
    except (AssertionError, KeyError, OSError, TypeError, ValueError) as exc:
        raise UniverseValidationError(
            f"mutmut metadata is invalid: {metadata_path}"
        ) from exc
    return data


def _metadata_inventory(
    mutmut_cli: Any, paths: Iterable[Path]
) -> tuple[dict[str, str], list[str]]:
    metadata_hashes: dict[str, str] = {}
    mutant_names: list[str] = []

    for path in sorted(paths, key=_normalize_path):
        normalized_path = _normalize_path(path)
        metadata_path = _safe_mutant_path(f"{normalized_path}.meta")
        if not metadata_path.is_file():
            raise UniverseValidationError(
                f"mutmut metadata is missing: {metadata_path}"
            )
        data = _load_metadata(mutmut_cli, Path(normalized_path), metadata_path)
        metadata_hashes[normalized_path] = _sha256_file(metadata_path)
        mutant_names.extend(str(name) for name in data.exit_code_by_key)

    if len(mutant_names) != len(set(mutant_names)):
        raise UniverseValidationError("mutmut metadata contains duplicate mutant names")
    return metadata_hashes, sorted(mutant_names)


def _build_generation_manifest(mutmut_cli: Any) -> dict[str, Any]:
    config = mutmut_cli.Config.get()
    validate_configured_paths(config)
    source_paths = list(mutmut_cli.walk_source_files())
    mutatable_paths = list(mutmut_cli.walk_mutatable_files())
    if not source_paths:
        raise UniverseValidationError("mutmut source universe is empty")
    if not mutatable_paths:
        raise UniverseValidationError("mutmut mutation universe is empty")

    source_hashes = _source_file_hashes(source_paths)
    generated_hashes = _mutated_file_hashes(source_paths)
    metadata_hashes, mutant_names = _metadata_inventory(mutmut_cli, mutatable_paths)
    also_copy_inventory = _also_copy_inventory(config)
    return {
        "schema_version": GENERATION_MANIFEST_SCHEMA_VERSION,
        "mutmut_version": _mutmut_version(),
        "source_files": source_hashes,
        "source_fingerprint": _digest(source_hashes),
        "generated_files": generated_hashes,
        "metadata_files": metadata_hashes,
        "mutatable_files": sorted(_normalize_path(path) for path in mutatable_paths),
        "mutant_count": len(mutant_names),
        "mutant_names_sha256": _digest(mutant_names),
        "config": _config_snapshot(config),
        "config_fingerprint": _config_fingerprint(config),
        "also_copy_inventory": also_copy_inventory,
    }


_GENERATION_MANIFEST_FIELDS = (
    "mutmut_version",
    "source_files",
    "source_fingerprint",
    "generated_files",
    "metadata_files",
    "mutatable_files",
    "mutant_count",
    "mutant_names_sha256",
    "config",
    "config_fingerprint",
    "also_copy_inventory",
)


def write_generation_manifest(
    mutmut_cli: Any,
    *,
    manifest_path: Path = GENERATION_MANIFEST_PATH,
) -> dict[str, Any]:
    """Write a source/metadata-only manifest for pre-stats reuse."""

    manifest = _build_generation_manifest(mutmut_cli)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def _read_manifest(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UniverseValidationError(f"{label} is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UniverseValidationError(f"{label} is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise UniverseValidationError(f"{label} must be an object")
    return value


def validate_generation_manifest(
    mutmut_cli: Any,
    *,
    manifest_path: Path = GENERATION_MANIFEST_PATH,
) -> dict[str, Any]:
    """Fail closed if a source/metadata generation tree cannot be trusted."""

    manifest = _read_manifest(manifest_path, label="mutmut generation manifest")
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != GENERATION_MANIFEST_SCHEMA_VERSION
    ):
        raise UniverseValidationError("mutmut generation manifest schema mismatch")
    expected = _build_generation_manifest(mutmut_cli)
    for key in _GENERATION_MANIFEST_FIELDS:
        if manifest.get(key) != expected[key]:
            if key.startswith("source"):
                detail = "source fingerprint"
            elif key.startswith("metadata"):
                detail = "metadata fingerprint"
            elif key in {"config", "config_fingerprint"}:
                detail = "config fingerprint"
            elif key == "also_copy_inventory":
                detail = "also_copy fingerprint"
            else:
                detail = key
            raise UniverseValidationError(
                f"mutmut generation {detail} mismatch; refusing reuse"
            )
    return manifest


def _build_manifest(mutmut_cli: Any, *, stats_path: Path) -> dict[str, Any]:
    if not stats_path.is_file():
        raise UniverseValidationError(f"mutmut stats artifact is missing: {stats_path}")
    return {
        **_build_generation_manifest(mutmut_cli),
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "stats_sha256": _sha256_file(stats_path),
    }


def write_universe_manifest(
    mutmut_cli: Any,
    *,
    stats_path: Path = Path("mutants/mutmut-stats.json"),
    manifest_path: Path = UNIVERSE_MANIFEST_PATH,
) -> dict[str, Any]:
    """Write a deterministic manifest for the freshly generated universe."""

    manifest = _build_manifest(mutmut_cli, stats_path=stats_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def validate_universe_manifest(
    mutmut_cli: Any,
    *,
    stats_path: Path = Path("mutants/mutmut-stats.json"),
    manifest_path: Path = UNIVERSE_MANIFEST_PATH,
) -> dict[str, Any]:
    """Verify every input used by a reused universe before mutation execution."""

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UniverseValidationError(
            f"mutmut universe manifest is missing: {manifest_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise UniverseValidationError(
            f"mutmut universe manifest is invalid JSON: {manifest_path}"
        ) from exc
    if not isinstance(manifest, dict):
        raise UniverseValidationError("mutmut universe manifest must be an object")
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
    ):
        raise UniverseValidationError("mutmut universe manifest schema mismatch")

    expected = _build_manifest(mutmut_cli, stats_path=stats_path)
    for key in (
        "mutmut_version",
        "source_files",
        "source_fingerprint",
        "generated_files",
        "metadata_files",
        "mutatable_files",
        "mutant_count",
        "mutant_names_sha256",
        "stats_sha256",
        "config",
        "config_fingerprint",
        "also_copy_inventory",
    ):
        if manifest.get(key) != expected[key]:
            if key.startswith("source"):
                detail = "source fingerprint"
            elif key.startswith("metadata"):
                detail = "metadata fingerprint"
            elif key == "config" or key == "config_fingerprint":
                detail = "config fingerprint"
            elif key == "stats_sha256":
                detail = "stats fingerprint"
            elif key == "also_copy_inventory":
                detail = "also_copy fingerprint"
            else:
                detail = key
            raise UniverseValidationError(
                f"mutmut universe {detail} mismatch; refusing reuse"
            )
    return manifest


def load_reused_generation_stats(mutmut_cli: Any) -> Any:
    """Populate mutmut's in-memory hash state from validated metadata.

    ``mutmut._run`` normally populates ``state().current_function_hashes`` while
    creating files.  Reuse skips that expensive phase, so we reconstruct the
    exact same map from the metadata generated by the planner.
    """

    config = mutmut_cli.Config.get()
    validate_configured_paths(config)
    state = mutmut_cli.state()
    state.current_function_hashes.clear()
    stats = mutmut_cli.MutantGenerationStats()
    for path in mutmut_cli.walk_source_files():
        normalized_path = _normalize_path(path)
        _safe_repository_path(
            normalized_path,
            label="mutmut source file",
            allow_missing=False,
        )
        generated = _safe_mutant_path(normalized_path)
        if not generated.is_file():
            raise UniverseValidationError(
                f"generated mutmut source is missing: {generated}"
            )
        if config.should_mutate(path):
            metadata_path = _safe_mutant_path(f"{normalized_path}.meta")
            if not metadata_path.is_file():
                raise UniverseValidationError(
                    f"mutmut metadata is missing: {metadata_path}"
                )
            data = _load_metadata(mutmut_cli, Path(normalized_path), metadata_path)
            state.current_function_hashes.update(
                {
                    mutmut_cli.get_mutant_name(Path(normalized_path), function): value
                    for function, value in data.hash_by_function_name.items()
                }
            )
            try:
                source_mtime = Path(normalized_path).stat().st_mtime
                generated_mtime = generated.stat().st_mtime
            except OSError as exc:
                raise UniverseValidationError(
                    f"unable to inspect mutmut source timestamps for {normalized_path}"
                ) from exc
            # Match create_mutants_for_file's source_mtime < mutant_mtime
            # fast-path classification while retaining the already validated
            # generated file instead of re-rendering it.
            if source_mtime < generated_mtime:
                stats.unmodified += 1
            else:
                stats.mutated += 1
        else:
            stats.ignored += 1
    return stats


def prepare_reused_generation(mutmut_cli: Any) -> Any:
    """Validate and initialize an extracted generation tree without copying.

    Callers must invoke this after the repository checkout and artifact
    transport envelope have been validated.  No mutmut source copy or mutant
    generation is performed here; the returned stats object only reconstructs
    the in-memory function-hash state required by downstream collection.
    """

    mutmut_cli.Config.ensure_loaded()
    mutmut_cli.setup_source_paths()
    validate_generation_manifest(mutmut_cli)
    return load_reused_generation_stats(mutmut_cli)
