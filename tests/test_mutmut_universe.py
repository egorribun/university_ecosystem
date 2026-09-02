from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.mutmut_universe import (
    GENERATION_MANIFEST_SCHEMA_VERSION,
    UniverseValidationError,
    _also_copy_inventory,
    load_reused_generation_stats,
    prepare_mutants_directory,
    prepare_reused_generation,
    validate_configured_paths,
    validate_generation_manifest,
    validate_universe_manifest,
    write_generation_manifest,
    write_universe_manifest,
)


@dataclass
class _FakeConfig:
    also_copy: list[Path] = field(default_factory=lambda: [Path("tests")])
    only_mutate: list[str] = field(default_factory=list)
    do_not_mutate: list[str] = field(default_factory=list)
    do_not_mutate_patterns: list[str] = field(default_factory=list)
    max_stack_depth: int = -1
    debug: bool = False
    source_paths: list[Path] = field(default_factory=lambda: [Path("app")])
    resolved_mutated_source_paths: list[Path] = field(
        default_factory=lambda: [Path("mutants/app")]
    )
    pytest_add_cli_args: list[str] = field(default_factory=lambda: ["-q"])
    pytest_add_cli_args_test_selection: list[str] = field(
        default_factory=lambda: ["tests/"]
    )
    mutate_only_covered_lines: bool = False
    timeout_multiplier: float = 15.0
    timeout_constant: float = 6.0
    type_check_command: list[str] = field(default_factory=list)
    use_setproctitle: bool = True
    track_dependencies: bool = True
    dependency_tracking_depth: int = -1
    cache_invalidation_files: list[str] = field(default_factory=list)
    cache_invalidation_exclude: list[str] = field(default_factory=list)
    on_dependency_change: str = "warn"
    use_git_change_detection: bool = True

    def config_fingerprint(self) -> dict[str, str]:
        return {"test_execution": "abc123"}

    def should_mutate(self, _path: Path) -> bool:
        return Path(_path).name != "ignored.py"


class _FakeMutationData:
    def __init__(self, *, path: Path) -> None:
        self.path = path
        self.meta_path = Path("mutants") / (str(path) + ".meta")
        self.exit_code_by_key: dict[str, int | None] = {}
        self.hash_by_function_name: dict[str, str] = {}

    def load(self) -> None:
        payload = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.exit_code_by_key = payload["exit_code_by_key"]
        self.hash_by_function_name = payload["hash_by_function_name"]


@dataclass
class _FakeGenerationStats:
    mutated: int = 0
    unmodified: int = 0
    ignored: int = 0


@dataclass
class _FakeState:
    current_function_hashes: dict[str, str] = field(default_factory=dict)


_FAKE_STATE = _FakeState()


class _FakeCli:
    Config = SimpleNamespace(
        ensure_loaded=lambda: None,
        get=lambda: _FakeConfig(),
    )
    SourceFileMutationData = _FakeMutationData
    MutantGenerationStats = _FakeGenerationStats

    @staticmethod
    def walk_source_files():
        return iter(
            [
                Path("app/example.py"),
                Path("app/noop.py"),
                Path("app/ignored.py"),
            ]
        )

    @staticmethod
    def walk_mutatable_files():
        return iter([Path("app/example.py"), Path("app/noop.py")])

    @staticmethod
    def state():
        return _FAKE_STATE

    @staticmethod
    def get_mutant_name(path: Path, function: str) -> str:
        return f"{path.as_posix().removesuffix('.py').replace('/', '.')}.{function}"

    @staticmethod
    def setup_source_paths() -> None:
        return None


def _write_universe(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app/example.py").write_text(
        "def example() -> bool:\n    return True\n", encoding="utf-8"
    )
    (tmp_path / "app/noop.py").write_text(
        "def noop() -> None:\n    return None\n", encoding="utf-8"
    )
    (tmp_path / "app/ignored.py").write_text(
        "def ignored() -> None:\n    return None\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/fixture.txt").write_text("mutation fixture\n", encoding="utf-8")
    (tmp_path / "mutants/app").mkdir(parents=True)
    (tmp_path / "mutants/app/example.py").write_text(
        "def example() -> bool:\n    return True\n", encoding="utf-8"
    )
    (tmp_path / "mutants/app/noop.py").write_text(
        "def noop() -> None:\n    return None\n", encoding="utf-8"
    )
    (tmp_path / "mutants/app/ignored.py").write_text(
        "def ignored() -> None:\n    return None\n", encoding="utf-8"
    )
    (tmp_path / "mutants/app/example.py.meta").write_text(
        json.dumps(
            {
                "exit_code_by_key": {"app.example.example__mutmut_1": None},
                "hash_by_function_name": {"example": "hash"},
                "type_check_error_by_key": {},
                "durations_by_key": {},
                "estimated_durations_by_key": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "mutants/app/noop.py.meta").write_text(
        json.dumps(
            {
                "exit_code_by_key": {},
                "hash_by_function_name": {},
                "type_check_error_by_key": {},
                "durations_by_key": {},
                "estimated_durations_by_key": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "mutants/mutmut-stats.json").write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": {
                    "app.example.example": ["tests/test_example.py::test_example"]
                },
                "duration_by_test": {"tests/test_example.py::test_example": 1.0},
                "stats_time": 1.0,
            }
        ),
        encoding="utf-8",
    )


def test_generated_universe_manifest_round_trips_and_records_fingerprints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)

    manifest = write_universe_manifest(_FakeCli)
    assert manifest["schema_version"] == 2
    assert manifest["mutant_count"] == 1
    assert len(manifest["source_fingerprint"]) == 64
    assert manifest["config_fingerprint"] == {"test_execution": "abc123"}
    assert manifest["also_copy_inventory"]["tests"]["files"] == {
        "fixture.txt": hashlib.sha256(
            Path("tests/fixture.txt").read_bytes()
        ).hexdigest()
    }
    assert validate_universe_manifest(_FakeCli) == manifest


def test_generation_manifest_round_trips_without_stats_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    (tmp_path / "mutants/mutmut-stats.json").unlink()
    monkeypatch.chdir(tmp_path)

    manifest = write_generation_manifest(_FakeCli)

    assert manifest["schema_version"] == GENERATION_MANIFEST_SCHEMA_VERSION
    assert "stats_sha256" not in manifest
    assert validate_generation_manifest(_FakeCli) == manifest


def test_reused_generation_initialization_does_not_regenerate_mutants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    (tmp_path / "mutants/mutmut-stats.json").unlink()
    monkeypatch.chdir(tmp_path)
    write_generation_manifest(_FakeCli)

    # The fake CLI intentionally has no copy/create methods.  A call to the
    # expensive generation path would therefore fail; successful preparation
    # proves that extraction uses only the validated generation tree.
    _FAKE_STATE.current_function_hashes = {"stale": "hash"}
    stats = prepare_reused_generation(_FakeCli)

    assert stats.mutated == 0
    assert stats.unmodified == 2
    assert stats.ignored == 1
    assert _FAKE_STATE.current_function_hashes == {"app.example.example": "hash"}


def test_generation_manifest_rejects_tampered_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    (tmp_path / "mutants/mutmut-stats.json").unlink()
    monkeypatch.chdir(tmp_path)
    write_generation_manifest(_FakeCli)
    metadata_path = Path("mutants/app/example.py.meta")
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(UniverseValidationError, match="metadata fingerprint"):
        validate_generation_manifest(_FakeCli)


def test_generation_manifest_rejects_boolean_schema_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    (tmp_path / "mutants/mutmut-stats.json").unlink()
    monkeypatch.chdir(tmp_path)
    write_generation_manifest(_FakeCli)

    manifest_path = Path("mutants/mutmut-generation.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(UniverseValidationError, match="schema mismatch"):
        validate_generation_manifest(_FakeCli)


def test_generated_universe_validation_rejects_previous_manifest_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)

    manifest_path = Path("mutants/mutmut-universe.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(UniverseValidationError, match="schema mismatch"):
        validate_universe_manifest(_FakeCli)


def test_generated_universe_validation_rejects_boolean_schema_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)

    manifest_path = Path("mutants/mutmut-universe.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(UniverseValidationError, match="schema mismatch"):
        validate_universe_manifest(_FakeCli)


def test_generated_universe_validation_fails_closed_when_source_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)

    Path("app/example.py").write_text(
        "def example() -> bool:\n    return False\n", encoding="utf-8"
    )

    with pytest.raises(UniverseValidationError, match="source fingerprint"):
        validate_universe_manifest(_FakeCli)


def test_generated_universe_validation_fails_closed_when_also_copy_input_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)

    Path("tests/fixture.txt").write_text("changed fixture\n", encoding="utf-8")

    with pytest.raises(UniverseValidationError, match="also_copy fingerprint"):
        validate_universe_manifest(_FakeCli)


def test_missing_optional_also_copy_path_is_recorded_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    config = _FakeConfig(also_copy=[Path("optional-lockfile.lock")])
    monkeypatch.setattr(_FakeCli, "Config", SimpleNamespace(get=lambda: config))

    manifest = write_universe_manifest(_FakeCli)

    assert manifest["also_copy_inventory"] == {
        "optional-lockfile.lock": {"kind": "missing"}
    }


def test_also_copy_inventory_rejects_intermediate_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("not a repository input", encoding="utf-8")
    link = repo / "linked-directory"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"symlink creation is unavailable: {exc}"
        )

    monkeypatch.chdir(repo)
    config = SimpleNamespace(also_copy=[Path("linked-directory/secret.txt")])

    with pytest.raises(UniverseValidationError, match="symlink or junction"):
        _also_copy_inventory(config)


def test_configured_also_copy_directory_rejects_symlink_descendant_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    copy_root = repo / "config"
    repo.mkdir()
    outside.mkdir()
    copy_root.mkdir()
    link = copy_root / "linked-directory"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"symlink creation is unavailable: {exc}"
        )

    monkeypatch.chdir(repo)
    config = SimpleNamespace(source_paths=[], also_copy=[Path("config")])

    with pytest.raises(UniverseValidationError, match="symlink or junction"):
        validate_configured_paths(config)


def test_also_copy_inventory_accepts_valid_nested_repository_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    nested = repo / "config" / "fixtures"
    nested.mkdir(parents=True)
    fixture = nested / "settings.toml"
    fixture.write_text("enabled = true\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    inventory = _also_copy_inventory(
        SimpleNamespace(also_copy=[Path("config/fixtures")])
    )

    assert inventory["config/fixtures"] == {
        "kind": "directory",
        "files": {"settings.toml": hashlib.sha256(fixture.read_bytes()).hexdigest()},
    }


def test_configured_source_root_rejects_intermediate_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    link = repo / "linked-source"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"symlink creation is unavailable: {exc}"
        )

    monkeypatch.chdir(repo)
    config = SimpleNamespace(
        source_paths=[Path("linked-source/python")],
        also_copy=[],
    )

    with pytest.raises(UniverseValidationError, match="symlink or junction"):
        validate_configured_paths(config)


def test_prepare_mutants_directory_removes_stale_generated_sources_and_sidecars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)

    prepare_mutants_directory(_FakeCli)

    assert not Path("mutants/app/example.py").exists()
    assert not Path("mutants/app/example.py.meta").exists()
    assert not Path("mutants/app/noop.py").exists()
    assert not Path("mutants/app/ignored.py").exists()


def test_prepare_mutants_directory_rejects_symlinked_mutants_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    outside.mkdir()
    for name in ("example.py", "noop.py", "ignored.py"):
        (repo / "app" / name).write_text("# source\n", encoding="utf-8")
    target = outside / "mutants"
    target.mkdir()
    link = repo / "mutants"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"symlink creation is unavailable: {exc}"
        )

    monkeypatch.chdir(repo)
    with pytest.raises(UniverseValidationError, match="mutants root"):
        prepare_mutants_directory(_FakeCli)


def test_generated_universe_validation_fails_closed_when_metadata_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)

    metadata_path = Path("mutants/app/example.py.meta")
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(UniverseValidationError, match="metadata"):
        validate_universe_manifest(_FakeCli)


def test_generated_universe_validation_fails_closed_when_config_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)
    changed_config = _FakeConfig(pytest_add_cli_args=["-q", "--strict-markers"])
    monkeypatch.setattr(
        _FakeCli,
        "Config",
        SimpleNamespace(get=lambda: changed_config),
    )

    with pytest.raises(UniverseValidationError, match="config fingerprint"):
        validate_universe_manifest(_FakeCli)


def test_generated_universe_validation_fails_closed_when_metadata_is_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)
    Path("mutants/app/example.py.meta").write_text("{}", encoding="utf-8")

    with pytest.raises(UniverseValidationError, match="metadata is invalid"):
        validate_universe_manifest(_FakeCli)


def test_reused_generation_stats_match_mutmut_for_unmodified_and_ignored_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_universe_manifest(_FakeCli)
    _FAKE_STATE.current_function_hashes = {"stale": "hash"}

    stats = load_reused_generation_stats(_FakeCli)

    assert stats.mutated == 0
    assert stats.unmodified == 2
    assert stats.ignored == 1
    assert _FAKE_STATE.current_function_hashes == {"app.example.example": "hash"}
