"""The opt-in persistent-store overlay cannot reuse MinIO on-disk data."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "docker-compose.seaweedfs-cutover.yml"


def test_cutover_overlay_uses_distinct_persistent_volume() -> None:
    content = OVERLAY.read_text(encoding="utf-8")
    assert "!override" in content
    assert "minio_data:/data" not in content
    assert "minio-data:/data" not in content
    assert "seaweedfs_data:/data" in content
    assert "university_ecosystem_seaweedfs_data" in content


def test_cutover_overlay_requires_explicit_acknowledgement_and_private_s3() -> None:
    content = OVERLAY.read_text(encoding="utf-8")
    assert "S3_CUTOVER_ACK" in content
    assert "AWS_ACCESS_KEY_ID" in content
    assert "AWS_SECRET_ACCESS_KEY" in content
    assert "S3_BUCKET" in content
    assert "public-read" not in content.lower()
    assert "mc mb" not in content
    assert "-s3.port=9000" in content
