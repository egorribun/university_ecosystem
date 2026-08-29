from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quality" / "aggregate_release_image_evidence.py"
VERIFIER = ROOT / "scripts" / "quality" / "verify_release_image_manifest.py"
EXPECTED_IMAGES = {
    "backend",
    "caddy",
    "frontend",
    "ws-hub",
    "gateway",
    "file-processor",
}
SHA = "a" * 40
BUILD_RUN_ID = 101
BUILD_RUN_ATTEMPT = 2
QUALITY_RUN_ID = 99
QUALITY_RUN_ATTEMPT = 1
REPOSITORY = "egorribun/university_ecosystem"
QUALITY_CONTRACT = ROOT / "quality" / "quality-contract.json"
CHECK_POLICY = ROOT / "quality" / "release-required-checks.json"


def _load_script() -> ModuleType:
    assert SCRIPT.is_file(), "release image evidence aggregator is required"
    spec = importlib.util.spec_from_file_location("release_image_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_verifier() -> ModuleType:
    assert VERIFIER.is_file(), "release image manifest verifier is required"
    spec = importlib.util.spec_from_file_location("release_image_verifier", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _aggregate(module: ModuleType, evidence_dir: Path, certification: Path) -> dict:
    certification.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "commit_sha": SHA,
                "contract_sha256": hashlib.sha256(
                    QUALITY_CONTRACT.read_bytes()
                ).hexdigest(),
                "check_policy_sha256": hashlib.sha256(
                    CHECK_POLICY.read_bytes()
                ).hexdigest(),
                "check_event": "push_main",
                "record_sha256": "c" * 64,
                "hmac_sha256": "d" * 64,
            }
        ),
        encoding="utf-8",
    )
    certification_artifact = f"quality-certification-{SHA}-attempt-{BUILD_RUN_ATTEMPT}"
    certification_provenance = certification.with_name("certification-provenance.json")
    certification_provenance.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "certification_sha256": hashlib.sha256(
                    certification.read_bytes()
                ).hexdigest(),
                "producer": _producer(
                    artifact_name=certification_artifact,
                    attempt=BUILD_RUN_ATTEMPT,
                ),
                "quality": {
                    "run_id": QUALITY_RUN_ID,
                    "run_attempt": QUALITY_RUN_ATTEMPT,
                    "evidence_artifact_name": f"quality-evidence-{SHA}",
                    "contract_sha256": hashlib.sha256(
                        QUALITY_CONTRACT.read_bytes()
                    ).hexdigest(),
                    "check_policy_sha256": hashlib.sha256(
                        CHECK_POLICY.read_bytes()
                    ).hexdigest(),
                    "check_event": "push_main",
                },
            }
        ),
        encoding="utf-8",
    )
    images = []
    for index, path in enumerate(sorted(evidence_dir.glob("*.json")), start=1):
        evidence = json.loads(path.read_text(encoding="utf-8"))
        producer = evidence.get("producer")
        if not isinstance(producer, dict):
            continue
        images.append(
            {
                "image_name": evidence.get("image_name"),
                "artifact_id": index,
                "artifact_name": producer.get("artifact_name"),
                "producer_run_attempt": producer.get("run_attempt"),
            }
        )
    cohort = certification.with_name("cohort.json")
    cohort.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repository": REPOSITORY,
                "source_sha": SHA,
                "build_run_id": BUILD_RUN_ID,
                "consumer_run_attempt": BUILD_RUN_ATTEMPT,
                "images": images,
                "certification": {
                    "artifact_id": 7,
                    "artifact_name": certification_artifact,
                    "producer_run_attempt": BUILD_RUN_ATTEMPT,
                },
            }
        ),
        encoding="utf-8",
    )
    return module.aggregate_image_evidence(
        evidence_dir,
        expected_repository=REPOSITORY,
        expected_sha=SHA,
        certification_path=certification,
        certification_provenance_path=certification_provenance,
        cohort_path=cohort,
        quality_contract_path=QUALITY_CONTRACT,
        check_policy_path=CHECK_POLICY,
        build_run_id=BUILD_RUN_ID,
        build_run_attempt=BUILD_RUN_ATTEMPT,
        quality_run_id=QUALITY_RUN_ID,
        quality_run_attempt=QUALITY_RUN_ATTEMPT,
    )


def _producer(*, artifact_name: str, attempt: int) -> dict[str, object]:
    return {
        "repository": REPOSITORY,
        "workflow_path": ".github/workflows/build-release-images.yml",
        "workflow_ref": (
            f"{REPOSITORY}/.github/workflows/build-release-images.yml@refs/heads/main"
        ),
        "workflow_sha": SHA,
        "source_ref": "refs/heads/main",
        "event": "workflow_dispatch",
        "run_id": BUILD_RUN_ID,
        "run_attempt": attempt,
        "artifact_name": artifact_name,
    }


def _write_evidence(
    directory: Path, name: str, digest_char: str, *, attempt: int = BUILD_RUN_ATTEMPT
) -> None:
    digest = f"sha256:{digest_char * 64}"
    artifact_name = f"image-digest-evidence-{name}-{SHA}-attempt-{attempt}"
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "image_name": name,
                "source_sha": SHA,
                "subject_name": f"ghcr.io/{REPOSITORY}/{name}",
                "digest": digest,
                "reference": f"ghcr.io/{REPOSITORY}/{name}@{digest}",
                "signature_verified": True,
                "attestation_verified": True,
                "producer": _producer(artifact_name=artifact_name, attempt=attempt),
                "verification": {
                    "trivy_version": "0.73.0",
                    "sbom_format": "cyclonedx-json",
                    "signature": "cosign-keyless",
                    "attestation": "github-build-provenance",
                },
                "build_contract": {
                    "canonical_frontend": name == "frontend",
                    "release_sha": SHA,
                },
            }
        ),
        encoding="utf-8",
    )


def test_aggregator_requires_exact_unique_six_image_digest_inventory(
    tmp_path: Path,
) -> None:
    module = _load_script()
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for index, name in enumerate(sorted(EXPECTED_IMAGES), start=1):
        _write_evidence(evidence_dir, name, format(index, "x"))
    certification = tmp_path / "certification.json"
    certification.write_text('{"commit_sha":"' + SHA + '"}\n', encoding="utf-8")

    manifest = _aggregate(module, evidence_dir, certification)

    assert {item["image_name"] for item in manifest["images"]} == EXPECTED_IMAGES
    assert manifest["source_sha"] == SHA
    assert (
        manifest["certification_sha256"]
        == hashlib.sha256(certification.read_bytes()).hexdigest()
    )
    assert len({item["digest"] for item in manifest["images"]}) == 6
    assert manifest["schema_version"] == 2
    assert manifest["builder"] == {
        "workflow_path": ".github/workflows/build-release-images.yml",
        "workflow_ref": "egorribun/university_ecosystem/.github/workflows/build-release-images.yml@refs/heads/main",
        "event": "workflow_dispatch",
        "run_id": BUILD_RUN_ID,
        "run_attempt": BUILD_RUN_ATTEMPT,
    }
    assert manifest["quality_run_id"] == QUALITY_RUN_ID

    (evidence_dir / "frontend.json").unlink()
    with pytest.raises(ValueError, match="exact image inventory"):
        _aggregate(module, evidence_dir, certification)


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
        _aggregate(module, evidence_dir, certification)

    payload["signature_verified"] = True
    payload["reference"] = payload["reference"].replace("/backend@", "/other@")
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical digest reference"):
        _aggregate(module, evidence_dir, certification)


def test_consumer_verifier_emits_only_exact_canonical_digests(tmp_path: Path) -> None:
    aggregator = _load_script()
    verifier = _load_verifier()
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for index, name in enumerate(sorted(EXPECTED_IMAGES), start=1):
        _write_evidence(evidence_dir, name, format(index, "x"))
    certification = tmp_path / "certification.json"
    certification.write_text('{"commit_sha":"' + SHA + '"}\n', encoding="utf-8")
    manifest = _aggregate(aggregator, evidence_dir, certification)

    outputs = verifier.verify_manifest(
        manifest,
        expected_repository="egorribun/university_ecosystem",
        expected_sha=SHA,
        expected_build_run_id=BUILD_RUN_ID,
        expected_build_run_attempt=BUILD_RUN_ATTEMPT,
        expected_quality_run_id=QUALITY_RUN_ID,
    )

    assert set(outputs) == {
        "backend-digest",
        "caddy-digest",
        "frontend-digest",
        "ws-hub-digest",
        "gateway-digest",
        "file-processor-digest",
    }
    tampered = dict(manifest)
    tampered["builder"] = {**manifest["builder"], "run_attempt": 3}
    with pytest.raises(ValueError, match="builder provenance"):
        verifier.verify_manifest(
            tampered,
            expected_repository="egorribun/university_ecosystem",
            expected_sha=SHA,
            expected_build_run_id=BUILD_RUN_ID,
            expected_build_run_attempt=BUILD_RUN_ATTEMPT,
            expected_quality_run_id=QUALITY_RUN_ID,
        )
