"""Contracts for the fail-closed pytest shard test-universe manifest."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.quality.pytest_shard_manifest import (
    ManifestError,
    build_manifest,
    main,
    verify_manifests,
    write_manifest,
)
from tests import conftest as project_conftest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
)
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


class _ShardConfig:
    def getoption(self, name: str) -> int:
        return {"--shard-id": 0, "--num-shards": 2}[name]


def test_build_manifest_canonicalizes_node_ids_and_records_hashes() -> None:
    manifest = build_manifest(
        shard_id=1,
        num_shards=4,
        all_nodeids=("tests/test_b.py::test_two", "tests/test_a.py::test_one"),
        selected_nodeids=("tests/test_b.py::test_two",),
    )

    assert manifest["schema_version"] == 1
    assert manifest["shard_id"] == 1
    assert manifest["num_shards"] == 4
    assert manifest["all_nodeids"] == [
        "tests/test_a.py::test_one",
        "tests/test_b.py::test_two",
    ]
    assert manifest["selected_nodeids"] == ["tests/test_b.py::test_two"]
    assert manifest["all_count"] == 2
    assert manifest["selected_count"] == 1
    assert len(manifest["all_sha256"]) == 64
    assert len(manifest["selected_sha256"]) == 64


def test_build_manifest_rejects_empty_test_universe() -> None:
    with pytest.raises(ManifestError, match="all_nodeids must not be empty"):
        build_manifest(
            shard_id=0,
            num_shards=1,
            all_nodeids=(),
            selected_nodeids=(),
        )


def test_verify_manifests_accepts_complete_disjoint_shards(tmp_path: Path) -> None:
    all_nodeids = tuple(f"tests/test_{index}.py::test_case" for index in range(4))
    paths: list[Path] = []
    for shard_id, nodeid in enumerate(all_nodeids):
        path = tmp_path / f"pytest-shard-{shard_id}.json"
        write_manifest(
            path,
            shard_id=shard_id,
            num_shards=4,
            all_nodeids=all_nodeids,
            selected_nodeids=(nodeid,),
        )
        paths.append(path)

    result = verify_manifests(paths, expected_shards=4)

    assert result["all_count"] == 4
    assert result["selected_count"] == 4


@pytest.mark.parametrize(
    ("selected_by_shard", "message"),
    (
        (
            (("tests/test_0.py::test_case",), ("tests/test_0.py::test_case",), (), ()),
            "appears in more than one shard",
        ),
        (
            (("tests/test_0.py::test_case",), ("tests/test_1.py::test_case",), (), ()),
            "union differs",
        ),
    ),
)
def test_verify_manifests_rejects_duplicate_or_missing_nodes(
    tmp_path: Path,
    selected_by_shard: tuple[tuple[str, ...], ...],
    message: str,
) -> None:
    all_nodeids = tuple(f"tests/test_{index}.py::test_case" for index in range(4))
    paths: list[Path] = []
    for shard_id, selected in enumerate(selected_by_shard):
        path = tmp_path / f"pytest-shard-{shard_id}.json"
        write_manifest(
            path,
            shard_id=shard_id,
            num_shards=4,
            all_nodeids=all_nodeids,
            selected_nodeids=selected,
        )
        paths.append(path)

    with pytest.raises(ManifestError, match=message):
        verify_manifests(paths, expected_shards=4)


def test_verify_manifests_rejects_different_collected_universes(tmp_path: Path) -> None:
    paths: list[Path] = []
    for shard_id in range(4):
        path = tmp_path / f"pytest-shard-{shard_id}.json"
        all_nodeids = tuple(f"tests/test_{index}.py::test_case" for index in range(4))
        if shard_id == 3:
            all_nodeids = (*all_nodeids[:-1], "tests/test_new.py::test_case")
        write_manifest(
            path,
            shard_id=shard_id,
            num_shards=4,
            all_nodeids=all_nodeids,
            selected_nodeids=(),
        )
        paths.append(path)

    with pytest.raises(ManifestError, match="collected node-id universe"):
        verify_manifests(paths, expected_shards=4)


def test_verify_manifests_rejects_tampered_hash(tmp_path: Path) -> None:
    path = tmp_path / "pytest-shard-0.json"
    write_manifest(
        path,
        shard_id=0,
        num_shards=1,
        all_nodeids=("tests/test_one.py::test_case",),
        selected_nodeids=("tests/test_one.py::test_case",),
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["selected_sha256"] = "0" * 64
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ManifestError, match="selected_sha256"):
        verify_manifests([path], expected_shards=1)


@pytest.mark.parametrize("schema_version", [True, 1.0, "1"])
def test_verify_manifests_rejects_non_integer_schema_version(
    tmp_path: Path, schema_version: object
) -> None:
    path = tmp_path / "pytest-shard-0.json"
    write_manifest(
        path,
        shard_id=0,
        num_shards=1,
        all_nodeids=("tests/test_one.py::test_case",),
        selected_nodeids=("tests/test_one.py::test_case",),
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = schema_version
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ManifestError, match="unsupported schema"):
        verify_manifests([path], expected_shards=1)


def test_manifest_cli_verifies_a_complete_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "pytest-shard-0.json"
    write_manifest(
        path,
        shard_id=0,
        num_shards=1,
        all_nodeids=("tests/test_one.py::test_case",),
        selected_nodeids=("tests/test_one.py::test_case",),
    )

    assert main(["--expected-shards", "1", "--manifest", str(path)]) == 0
    assert "Verified pytest shard test universe" in capsys.readouterr().out


def test_collection_hook_emits_pre_and_post_filter_node_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests").mkdir()
    items = [
        SimpleNamespace(
            fspath=tmp_path / "tests" / "test_alpha.py",
            nodeid="tests/test_alpha.py::test_alpha",
        ),
        SimpleNamespace(
            fspath=tmp_path / "tests" / "test_beta.py",
            nodeid="tests/test_beta.py::test_beta",
        ),
    ]
    manifest_path = tmp_path / "artifacts" / "pytest-shard-0.json"
    monkeypatch.setattr(project_conftest, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PYTEST_SHARD_MANIFEST", str(manifest_path))

    project_conftest.pytest_collection_modifyitems(_ShardConfig(), items)

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert document["all_nodeids"] == [
        "tests/test_alpha.py::test_alpha",
        "tests/test_beta.py::test_beta",
    ]
    assert document["selected_nodeids"] == ["tests/test_alpha.py::test_alpha"]
    assert [item.nodeid for item in items] == ["tests/test_alpha.py::test_alpha"]


def test_ci_publishes_and_verifies_the_test_universe_before_combine() -> None:
    backend = yaml.safe_load(BACKEND_WORKFLOW.read_text(encoding="utf-8"))
    unit_steps = backend["jobs"]["unit-tests"]["steps"]
    run_step = next(step for step in unit_steps if step.get("name") == "Run pytest")
    assert "PYTEST_SHARD_MANIFEST" in run_step["env"]

    provenance = next(
        step
        for step in unit_steps
        if step.get("name") == "Write backend shard coverage provenance"
    )
    assert "pytest-node-manifest" in provenance["run"]

    upload = next(
        step
        for step in unit_steps
        if step.get("name") == "Upload raw coverage data for aggregation"
    )
    assert "pytest-shard-${{ inputs.shard-id }}.json" in upload["with"]["path"]

    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    aggregate = ci["jobs"]["coverage-policy-gate"]
    names = [step.get("name") for step in aggregate["steps"]]
    verify_index = names.index("Verify backend test-universe manifests")
    combine_index = names.index("Combine Python shard coverage")
    assert verify_index < combine_index
    verify = aggregate["steps"][verify_index]
    assert "pytest_shard_manifest.py" in verify["run"]
