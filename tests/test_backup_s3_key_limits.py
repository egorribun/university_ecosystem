from __future__ import annotations

import pytest

from scripts import backup_db


def test_manifest_key_rejects_artifact_key_over_s3_utf8_byte_limit() -> None:
    artifact_key = "é" * 513 + backup_db.ARTIFACT_SUFFIX
    assert len(artifact_key) < 1024
    assert len(artifact_key.encode("utf-8")) > 1024

    with pytest.raises(backup_db.BackupArtifactError, match="Invalid S3 object key"):
        backup_db.manifest_key(artifact_key)


def test_manifest_key_rejects_derived_key_over_s3_limit() -> None:
    artifact_key = "a" * (1024 - len(backup_db.ARTIFACT_SUFFIX))
    artifact_key += backup_db.ARTIFACT_SUFFIX
    assert len(artifact_key.encode("utf-8")) == 1024

    with pytest.raises(backup_db.BackupArtifactError, match="Invalid S3 object key"):
        backup_db.manifest_key(artifact_key)


def test_generated_artifact_reserves_key_space_for_its_manifest() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="Invalid S3 object key"):
        backup_db.new_artifact_key("p" * 950)
