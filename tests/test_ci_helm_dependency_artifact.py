from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "ci" / "helm_dependency_artifact.py"
SPEC = importlib.util.spec_from_file_location("helm_dependency_artifact", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


COMMIT_SHA = "a" * 40
WORKFLOW = ".github/workflows/nightly-full-gate.yml"


def _stage_archives(root: Path) -> dict[str, str]:
    archive_root = root / "charts"
    archive_root.mkdir(parents=True)
    contents = {
        "redis-20.13.4.tgz": b"redis archive",
        "nats-8.5.4.tgz": b"nats archive",
    }
    for name, content in contents.items():
        (archive_root / name).write_bytes(content)
    return {
        f"charts/{name}": hashlib.sha256(content).hexdigest()
        for name, content in contents.items()
    }


def test_create_and_validate_binds_archive_hashes_and_producer_identity(
    tmp_path: Path,
) -> None:
    expected_files = _stage_archives(tmp_path)
    manifest = tmp_path / "helm-dependencies.json"

    payload = MODULE.create_artifact_manifest(
        root=tmp_path,
        output=Path("helm-dependencies.json"),
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="2",
        workflow=WORKFLOW,
    )

    assert payload["producer"] == {
        "commit_sha": COMMIT_SHA,
        "run_id": "123",
        "run_attempt": "2",
        "workflow": WORKFLOW,
    }
    assert payload["archives"] == expected_files
    assert (
        MODULE.validate_artifact_manifest(
            root=tmp_path,
            manifest_path=manifest,
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="2",
            workflow=WORKFLOW,
        )
        == payload
    )


def test_validate_rejects_archive_hash_tampering(tmp_path: Path) -> None:
    _stage_archives(tmp_path)
    manifest = tmp_path / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    (tmp_path / "charts" / "nats-8.5.4.tgz").write_bytes(b"tampered")

    with pytest.raises(MODULE.ArtifactValidationError, match="hash mismatch"):
        MODULE.validate_artifact_manifest(
            root=tmp_path,
            manifest_path=manifest,
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )


def test_validate_rejects_foreign_producer_identity(tmp_path: Path) -> None:
    _stage_archives(tmp_path)
    manifest = tmp_path / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )

    with pytest.raises(MODULE.ArtifactValidationError, match="identity mismatch"):
        MODULE.validate_artifact_manifest(
            root=tmp_path,
            manifest_path=manifest,
            commit_sha="b" * 40,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )


def test_validate_rejects_malformed_archive_inventory(tmp_path: Path) -> None:
    _stage_archives(tmp_path)
    manifest = tmp_path / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    del payload["archives"]["charts/nats-8.5.4.tgz"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MODULE.ArtifactValidationError, match="required set"):
        MODULE.validate_artifact_manifest(
            root=tmp_path,
            manifest_path=manifest,
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )


def test_manifest_paths_must_stay_below_their_root(tmp_path: Path) -> None:
    _stage_archives(tmp_path)
    with pytest.raises(MODULE.ArtifactValidationError, match="below artifact root"):
        MODULE.create_artifact_manifest(
            root=tmp_path,
            output=Path("..") / "outside.json",
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )

    manifest = tmp_path / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    with pytest.raises(MODULE.ArtifactValidationError, match="below artifact root"):
        MODULE.validate_artifact_manifest(
            root=tmp_path,
            manifest_path=Path("..") / "helm-dependencies.json",
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )


def test_restore_rejects_symlinked_destination_parent(
    tmp_path: Path,
) -> None:
    _stage_archives(tmp_path / "artifact")
    manifest = tmp_path / "artifact" / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path / "artifact",
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    destination_parent = workspace / "charts"
    try:
        destination_parent.symlink_to(tmp_path / "outside", target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"symlinks unavailable: {error}"
        )

    with pytest.raises(MODULE.ArtifactValidationError, match="destination"):
        MODULE.restore_artifact_archives(
            root=tmp_path / "artifact",
            manifest_path=manifest,
            destination_root=workspace,
            destination=Path("charts"),
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )


def test_restore_rejects_destination_traversal(tmp_path: Path) -> None:
    _stage_archives(tmp_path / "artifact")
    artifact_root = tmp_path / "artifact"
    manifest = artifact_root / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=artifact_root,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(MODULE.ArtifactValidationError, match="destination"):
        MODULE.restore_artifact_archives(
            root=artifact_root,
            manifest_path=manifest,
            destination_root=workspace,
            destination=Path("..") / "outside",
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )


def test_restore_copies_only_validated_archives(tmp_path: Path) -> None:
    _stage_archives(tmp_path / "artifact")
    artifact_root = tmp_path / "artifact"
    manifest = artifact_root / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=artifact_root,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    MODULE.restore_artifact_archives(
        root=artifact_root,
        manifest_path=manifest,
        destination_root=workspace,
        destination=Path("charts"),
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    assert sorted(path.name for path in (workspace / "charts").iterdir()) == sorted(
        MODULE.ARCHIVE_NAMES
    )


def test_validate_at_or_before_accepts_earlier_attempt_but_rejects_future(
    tmp_path: Path,
) -> None:
    _stage_archives(tmp_path)
    manifest = tmp_path / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )

    MODULE.validate_artifact_manifest(
        root=tmp_path,
        manifest_path=Path("helm-dependencies.json"),
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="2",
        workflow=WORKFLOW,
        producer_attempt_policy="at-or-before",
    )
    _stage_archives(tmp_path / "future")
    future_manifest = tmp_path / "future" / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path / "future",
        output=future_manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="2",
        workflow=WORKFLOW,
    )
    with pytest.raises(MODULE.ArtifactValidationError, match="future"):
        MODULE.validate_artifact_manifest(
            root=tmp_path / "future",
            manifest_path=future_manifest,
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
            producer_attempt_policy="at-or-before",
        )


def test_validate_rejects_symlinked_archive(tmp_path: Path) -> None:
    _stage_archives(tmp_path)
    manifest = tmp_path / "helm-dependencies.json"
    MODULE.create_artifact_manifest(
        root=tmp_path,
        output=manifest,
        commit_sha=COMMIT_SHA,
        run_id="123",
        run_attempt="1",
        workflow=WORKFLOW,
    )
    target = tmp_path / "charts" / "nats-8.5.4.tgz"
    target.unlink()
    try:
        target.symlink_to(tmp_path / "charts" / "redis-20.13.4.tgz")
    except (OSError, NotImplementedError) as error:
        pytest.skip(  # QUALITY-123 @egorribun — filesystem capability varies by runner
            f"symlinks unavailable: {error}"
        )

    with pytest.raises(MODULE.ArtifactValidationError, match="unsafe"):
        MODULE.validate_artifact_manifest(
            root=tmp_path,
            manifest_path=manifest,
            commit_sha=COMMIT_SHA,
            run_id="123",
            run_attempt="1",
            workflow=WORKFLOW,
        )
