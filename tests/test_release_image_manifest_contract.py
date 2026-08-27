from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quality" / "aggregate_release_image_evidence.py"
EXPECTED_IMAGES = {"backend", "frontend", "ws-hub", "gateway", "file-processor"}
SHA = "a" * 40


def _load_script() -> ModuleType:
    assert SCRIPT.is_file(), "release image evidence aggregator is required"
    spec = importlib.util.spec_from_file_location("release_image_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_evidence(directory: Path, name: str, digest_char: str) -> None:
    digest = f"sha256:{digest_char * 64}"
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "image_name": name,
                "source_sha": SHA,
                "subject_name": f"ghcr.io/egorribun/university_ecosystem/{name}",
                "digest": digest,
                "reference": f"ghcr.io/egorribun/university_ecosystem/{name}@{digest}",
                "signature_verified": True,
                "attestation_verified": True,
            }
        ),
        encoding="utf-8",
    )


def test_aggregator_requires_exact_unique_five_image_digest_inventory(
    tmp_path: Path,
) -> None:
    module = _load_script()
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for index, name in enumerate(sorted(EXPECTED_IMAGES), start=1):
        _write_evidence(evidence_dir, name, format(index, "x"))
    certification = tmp_path / "certification.json"
    certification.write_text('{"commit_sha":"' + SHA + '"}\n', encoding="utf-8")

    manifest = module.aggregate_image_evidence(
        evidence_dir,
        expected_repository="egorribun/university_ecosystem",
        expected_sha=SHA,
        certification_path=certification,
    )

    assert {item["image_name"] for item in manifest["images"]} == EXPECTED_IMAGES
    assert manifest["source_sha"] == SHA
    assert (
        manifest["certification_sha256"]
        == hashlib.sha256(certification.read_bytes()).hexdigest()
    )
    assert len({item["digest"] for item in manifest["images"]}) == 5

    (evidence_dir / "frontend.json").unlink()
    with pytest.raises(ValueError, match="exact image inventory"):
        module.aggregate_image_evidence(
            evidence_dir,
            expected_repository="egorribun/university_ecosystem",
            expected_sha=SHA,
            certification_path=certification,
        )


def test_aggregator_rejects_foreign_sha_reference_and_unverified_evidence(
    tmp_path: Path,
) -> None:
    module = _load_script()
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for index, name in enumerate(sorted(EXPECTED_IMAGES), start=1):
        _write_evidence(evidence_dir, name, format(index, "x"))
    certification = tmp_path / "certification.json"
    certification.write_text('{"commit_sha":"' + SHA + '"}\n', encoding="utf-8")

    path = evidence_dir / "backend.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["signature_verified"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="verified signature and attestation"):
        module.aggregate_image_evidence(
            evidence_dir,
            expected_repository="egorribun/university_ecosystem",
            expected_sha=SHA,
            certification_path=certification,
        )

    payload["signature_verified"] = True
    payload["reference"] = payload["reference"].replace("/backend@", "/other@")
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical digest reference"):
        module.aggregate_image_evidence(
            evidence_dir,
            expected_repository="egorribun/university_ecosystem",
            expected_sha=SHA,
            certification_path=certification,
        )
