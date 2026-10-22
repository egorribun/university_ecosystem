from __future__ import annotations

from pathlib import Path

import pytest

from scripts.mutmut_universe import (
    UniverseValidationError,
    prepare_reused_generation_with_manifest,
    validate_universe_manifest,
    write_generation_manifest,
    write_universe_manifest,
)
from tests.test_mutmut_universe import _FakeCli, _write_universe


def test_primary_manifest_validates_pristine_inputs_and_rejects_full_stats_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)

    primary_manifest = write_universe_manifest(_FakeCli)
    assert validate_universe_manifest(_FakeCli) == primary_manifest

    stats_path = Path("mutants/mutmut-stats.json")
    stats_path.write_text(
        stats_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(UniverseValidationError, match="stats fingerprint"):
        validate_universe_manifest(_FakeCli)


def test_reused_planner_manifest_reuses_only_validated_generation_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_generation_manifest(_FakeCli)

    import scripts.mutmut_universe as universe

    build_count = 0
    original_build = universe._build_generation_manifest

    def count_generation_build(mutmut_cli):
        nonlocal build_count
        build_count += 1
        return original_build(mutmut_cli)

    monkeypatch.setattr(universe, "_build_generation_manifest", count_generation_build)
    _stats, validated_snapshot = prepare_reused_generation_with_manifest(_FakeCli)

    assert build_count == 1
    written = write_universe_manifest(_FakeCli, validated_generation=validated_snapshot)
    assert build_count == 1
    assert validate_universe_manifest(_FakeCli) == written
    assert build_count == 2


def test_universe_writer_rejects_unvalidated_generation_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(TypeError, match="must come from reused-generation validation"):
        write_universe_manifest(_FakeCli, validated_generation={})  # type: ignore[arg-type]


def test_validated_generation_snapshot_does_not_retain_mutable_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)

    import scripts.mutmut_universe as universe

    validated_payload = universe._build_generation_manifest(_FakeCli)
    expected_fingerprint = validated_payload["source_fingerprint"]
    monkeypatch.setattr(
        universe,
        "validate_generation_manifest",
        lambda _mutmut_cli: validated_payload,
    )
    monkeypatch.setattr(
        universe, "load_reused_generation_stats", lambda _mutmut_cli: object()
    )

    _stats, snapshot = universe._prepare_reused_generation(_FakeCli)
    validated_payload["source_fingerprint"] = "0" * 64

    written = write_universe_manifest(_FakeCli, validated_generation=snapshot)

    assert written["source_fingerprint"] == expected_fingerprint


def test_runner_revalidation_rejects_source_drift_after_cached_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_generation_manifest(_FakeCli)
    _stats, validated_snapshot = prepare_reused_generation_with_manifest(_FakeCli)

    source_path = Path("app/example.py")
    source_path.write_text(
        source_path.read_text(encoding="utf-8") + "# changed after validation\n",
        encoding="utf-8",
    )
    write_universe_manifest(_FakeCli, validated_generation=validated_snapshot)

    with pytest.raises(UniverseValidationError, match="source fingerprint"):
        validate_universe_manifest(_FakeCli)


def test_runner_revalidation_rejects_stats_drift_after_cached_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_generation_manifest(_FakeCli)
    _stats, validated_snapshot = prepare_reused_generation_with_manifest(_FakeCli)
    write_universe_manifest(_FakeCli, validated_generation=validated_snapshot)

    stats_path = Path("mutants/mutmut-stats.json")
    stats_path.write_text(
        stats_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(UniverseValidationError, match="stats fingerprint"):
        validate_universe_manifest(_FakeCli)
