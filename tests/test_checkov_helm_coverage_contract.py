from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml

CANDIDATE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(
    os.environ.get("CHECKOV_HELM_TEST_ROOT", str(CANDIDATE_ROOT))
).resolve()
QUALITY_SCRIPTS = CANDIDATE_ROOT / "scripts" / "quality"
CANONICAL_SCRIPTS = REPOSITORY_ROOT / "scripts" / "quality"
sys.path.insert(0, str(QUALITY_SCRIPTS))
sys.path.insert(1, str(CANONICAL_SCRIPTS))

from scripts.quality.create_checkov_oci_image_evidence import (
    REQUIRED_IMAGES,
    create_evidence,
)
from scripts.quality.prepare_checkov_helm_contexts import (
    _extract_yaml_digest_paths,
    _path_tokens,
    prepare,
    read_pinned_chart_images,
)
from scripts.quality.resolve_oci_platform_digest import render_checkov_values
from scripts.quality.verify_checkov_helm_json import CoverageError, verify_document

WORKFLOW_ROOT = Path(
    os.environ.get("CHECKOV_HELM_WORKFLOW_ROOT", str(CANDIDATE_ROOT))
).resolve()
WORKFLOW = WORKFLOW_ROOT / ".github" / "workflows" / "checkov.yml"
STAGING_TEST = REPOSITORY_ROOT / "tests" / "test_helm_staging_contract.py"


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _descriptor(media_type: str, raw: bytes) -> dict[str, Any]:
    return {"mediaType": media_type, "digest": _digest(raw), "size": len(raw)}


def _oci_archive(
    path: Path,
    marker: bytes,
    config_labels: dict[str, str] | None = None,
    config_raw_override: bytes | None = None,
) -> str:
    if config_raw_override is None:
        config_raw = json.dumps(
            {
                "architecture": "amd64",
                "os": "linux",
                "config": {
                    "Labels": config_labels
                    if config_labels is not None
                    else {
                        "org.opencontainers.image.source": "https://github.com/example/university-ecosystem",
                        "org.opencontainers.image.revision": "f" * 40,
                    }
                },
            },
            separators=(",", ":"),
        ).encode()
    else:
        config_raw = config_raw_override
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": _descriptor("application/vnd.oci.image.config.v1+json", config_raw),
        "layers": [],
        "annotations": {"org.example.fixture": marker.hex()},
    }
    manifest_raw = json.dumps(manifest, separators=(",", ":")).encode()
    descriptor = {
        **_descriptor("application/vnd.oci.image.manifest.v1+json", manifest_raw),
        "platform": {"os": "linux", "architecture": "amd64"},
    }
    index_raw = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [descriptor],
        },
        separators=(",", ":"),
    ).encode()
    entries = {
        "oci-layout": b'{"imageLayoutVersion":"1.0.0"}',
        "index.json": index_raw,
        f"blobs/sha256/{hashlib.sha256(config_raw).hexdigest()}": config_raw,
        f"blobs/sha256/{hashlib.sha256(manifest_raw).hexdigest()}": manifest_raw,
    }
    with tarfile.open(path, mode="w") as archive:
        for name, raw in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = 0o600
            archive.addfile(info, BytesIO(raw))
    return _digest(manifest_raw)


def _fixture_args(function_name: str, *args: Any) -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "_checkov_staging_contract_fixture", STAGING_TEST
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the existing Helm staging contract helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, function_name, None)
    if not callable(function):
        raise RuntimeError(f"missing existing Helm staging helper: {function_name}")
    result = function(*args)
    if not isinstance(result, list) or not all(
        isinstance(item, str) for item in result
    ):
        raise TypeError(
            f"existing Helm helper returned unexpected data: {function_name}"
        )
    return result


def _fixture_values(args: list[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for index in range(0, len(args), 2):
        flag, assignment = args[index : index + 2]
        key, raw = assignment.split("=", 1)
        if flag == "--set":
            value: Any = int(raw)
        else:
            value = raw
        values[key] = value
    return values


def _get_path(profile: dict[str, Any], key: str) -> Any:
    current: Any = profile
    for token in _path_tokens(key):
        current = current[token]
    return current


def _local_evidence(
    tmp_path: Path,
    backend_labels: dict[str, str] | None = None,
    backend_config_raw: bytes | None = None,
) -> tuple[dict[str, str], Path, str, Path]:
    archive_dir = tmp_path / "oci"
    archive_dir.mkdir()
    archive_paths = {}
    expected_digests = {}
    for index, name in enumerate(REQUIRED_IMAGES, start=1):
        path = archive_dir / f"{name}.oci.tar"
        expected_digests[name] = _oci_archive(
            path,
            f"synthetic {name} {index}".encode(),
            config_labels=backend_labels if name == "backend" else None,
            config_raw_override=backend_config_raw if name == "backend" else None,
        )
        archive_paths[name] = path
    evidence_path = tmp_path / "image-evidence.json"
    evidence_sha = create_evidence(
        repository="example/university-ecosystem",
        source_sha="f" * 40,
        archives=[f"{name}={path}" for name, path in archive_paths.items()],
        output=evidence_path,
    )
    assert Path(f"{evidence_path}.sha256").read_text(encoding="ascii") == (
        f"{evidence_sha}  {evidence_path.name}\n"
    )
    backend_values = tmp_path / "backend-values.yaml"
    backend_values.write_text(
        render_checkov_values(expected_digests["backend"]), encoding="utf-8"
    )
    return expected_digests, evidence_path, evidence_sha, backend_values


class CheckovHelmCoverageContracts(unittest.TestCase):
    def test_helm_contexts_match_staging_and_revocation_contract_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            pinned_chart_images = read_pinned_chart_images(REPOSITORY_ROOT)
            digests, evidence, evidence_sha, backend_values = _local_evidence(tmp_path)
            output_dir = tmp_path / "contexts"
            paths = prepare(
                REPOSITORY_ROOT,
                backend_values,
                evidence,
                evidence_sha,
                "example/university-ecosystem",
                "f" * 40,
                123,
                1,
                evidence.parent / "oci",
                output_dir,
            )
            main_profile = json.loads(
                paths["university-ecosystem.json"].read_text(encoding="utf-8")
            )
            staging_values = yaml.safe_load(
                (
                    REPOSITORY_ROOT / "charts/university-ecosystem/values-staging.yaml"
                ).read_text(encoding="utf-8")
            )
            expected_ingress = copy.deepcopy(staging_values["ingress"])
            expected_hosts = [
                "university.staging.example.org",
                "api.university.staging.example.org",
            ]
            for host_entry, host in zip(
                expected_ingress["hosts"], expected_hosts, strict=True
            ):
                host_entry["host"] = host
            expected_ingress["tls"][0]["hosts"] = expected_hosts
            self.assertEqual(
                main_profile["ingress"]["hosts"], expected_ingress["hosts"]
            )
            self.assertEqual(main_profile["ingress"]["tls"], expected_ingress["tls"])
            self.assertEqual(
                main_profile["ingress"]["hosts"][0]["paths"],
                staging_values["ingress"]["hosts"][0]["paths"],
            )
            self.assertEqual(
                main_profile["ingress"]["tls"][0]["secretName"],
                staging_values["ingress"]["tls"][0]["secretName"],
            )
            fixture = _fixture_values(_fixture_args("_resolved_staging_args"))
            expected_replacements = {
                "global.imageTag": "f" * 40,
                "global.backendImageDigest": digests["backend"],
                "backend.image.repository": "ghcr.io/example/university-ecosystem/backend",
                "backend.image.digest": digests["backend"],
                "frontend.image.repository": "ghcr.io/example/university-ecosystem/frontend",
                "frontend.image.digest": digests["frontend"],
                "gateway.image.repository": "ghcr.io/example/university-ecosystem/gateway",
                "gateway.image.digest": digests["gateway"],
                "wsHub.image.repository": "ghcr.io/example/university-ecosystem/ws-hub",
                "wsHub.image.digest": digests["ws-hub"],
                "fileProcessor.image.repository": "ghcr.io/example/university-ecosystem/file-processor",
                "fileProcessor.image.digest": digests["file-processor"],
                "outboxWorker.image.repository": "ghcr.io/example/university-ecosystem/backend",
                "outboxWorker.image.digest": digests["backend"],
                "redis.image.digest": pinned_chart_images["redis.image.digest"],
                "redis.metrics.image.digest": pinned_chart_images[
                    "redis.metrics.image.digest"
                ],
                "redis.metrics.passwordFileInitImage.repository": "ghcr.io/example/university-ecosystem/backend",
                "redis.metrics.passwordFileInitImage.digest": digests["backend"],
                "redis.metrics.passwordFileInitImage.tag": "",
                "nats.image.digest": pinned_chart_images["nats.image.digest"],
                "nats.container.image.digest": pinned_chart_images[
                    "nats.container.image.digest"
                ],
                "cwv.releaseSHA": "f" * 40,
                "cwv.frontendImageDigest": digests["frontend"],
                "cwv.deploymentRunID": 123,
                "cwv.deploymentRunAttempt": 1,
            }
            for key, fixture_value in fixture.items():
                self.assertEqual(
                    _get_path(main_profile, key),
                    expected_replacements.get(key, fixture_value),
                    key,
                )
            self.assertEqual(_get_path(main_profile, "backend.image.tag"), "")
            self.assertEqual(
                _get_path(main_profile, "global.backendImageDigest"), digests["backend"]
            )
            self.assertEqual(
                _get_path(main_profile, "backend.image.digest"), digests["backend"]
            )

            revocation = json.loads(
                paths["revocation-store.json"].read_text(encoding="utf-8")
            )
            revocation_fixture = _fixture_values(
                _fixture_args("_resolved_revocation_store_args", "checkov-revocation")
            )
            for key, fixture_value in revocation_fixture.items():
                if key in (
                    "redis.auth.existingSecret",
                    "redis.auth.existingSecretPasswordKey",
                ):
                    continue
                expected = fixture_value
                if key == "redis.image.digest":
                    expected = pinned_chart_images[key]
                elif key == "redis.metrics.image.digest":
                    expected = pinned_chart_images[key]
                elif key in (
                    "global.backendImageDigest",
                    "redis.metrics.passwordFileInitImage.digest",
                ):
                    expected = digests["backend"]
                self.assertEqual(_get_path(revocation, key), expected, key)
            self.assertEqual(
                _get_path(revocation, "global.backendImageDigest"), digests["backend"]
            )
            self.assertEqual(
                _get_path(revocation, "global.backendImageRepository"),
                "ghcr.io/example/university-ecosystem/backend",
            )
            self.assertEqual(
                _get_path(revocation, "redis.metrics.passwordFileInitImage.repository"),
                "ghcr.io/example/university-ecosystem/backend",
            )
            self.assertEqual(
                _get_path(revocation, "redis.metrics.passwordFileInitImage.digest"),
                digests["backend"],
            )
            self.assertEqual(
                _get_path(revocation, "redis.metrics.passwordFileInitImage.tag"), ""
            )
            self.assertEqual(
                _get_path(revocation, "redis.metrics.passwordFileInitImage.pullPolicy"),
                "Always",
            )
            self.assertNotIn("auth", revocation.get("redis", {}))

            redis_compat = json.loads(
                paths["redis-compat.json"].read_text(encoding="utf-8")
            )
            self.assertEqual(
                _get_path(redis_compat, "global.backendImageDigest"), digests["backend"]
            )
            self.assertEqual(
                set(paths),
                {
                    "university-ecosystem.json",
                    "revocation-store.json",
                    "redis-compat.json",
                },
            )

    def test_image_evidence_rejects_hash_tampering_and_wrong_image_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            _, evidence, evidence_sha, backend_values = _local_evidence(tmp_path)
            raw = evidence.read_bytes()
            evidence.write_bytes(raw + b" ")
            with self.assertRaisesRegex(ValueError, "sealed SHA-256"):
                prepare(
                    REPOSITORY_ROOT,
                    backend_values,
                    evidence,
                    evidence_sha,
                    "example/university-ecosystem",
                    "f" * 40,
                    123,
                    1,
                    evidence.parent / "oci",
                    tmp_path / "contexts",
                )
            evidence.write_bytes(raw)
            Path(f"{evidence}.sha256").write_text(
                "0" * 64 + "  image-evidence.json\n", encoding="ascii"
            )
            with self.assertRaisesRegex(ValueError, "sidecar"):
                prepare(
                    REPOSITORY_ROOT,
                    backend_values,
                    evidence,
                    evidence_sha,
                    "example/university-ecosystem",
                    "f" * 40,
                    123,
                    1,
                    evidence.parent / "oci",
                    tmp_path / "contexts",
                )
            document = json.loads(raw.decode("utf-8"))
            del document["images"]["file-processor"]
            tampered = (
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode("utf-8")
            new_hash = hashlib.sha256(tampered).hexdigest()
            evidence.write_bytes(tampered)
            Path(f"{evidence}.sha256").write_text(
                f"{new_hash}  {evidence.name}\n", encoding="ascii"
            )
            with self.assertRaisesRegex(ValueError, "exact required image set"):
                prepare(
                    REPOSITORY_ROOT,
                    backend_values,
                    evidence,
                    new_hash,
                    "example/university-ecosystem",
                    "f" * 40,
                    123,
                    1,
                    evidence.parent / "oci",
                    tmp_path / "contexts",
                )

    def test_image_evidence_requires_current_oci_source_and_revision_labels(
        self,
    ) -> None:
        valid_source = "https://github.com/example/university-ecosystem"
        valid_revision = "f" * 40
        invalid_labels = (
            {
                "org.opencontainers.image.source": "https://github.com/other/repository",
                "org.opencontainers.image.revision": valid_revision,
            },
            {
                "org.opencontainers.image.source": valid_source,
                "org.opencontainers.image.revision": "e" * 40,
            },
            {"org.opencontainers.image.source": valid_source},
        )
        for labels in invalid_labels:
            with (
                self.subTest(labels=labels),
                tempfile.TemporaryDirectory() as temporary,
            ):
                with self.assertRaises(ValueError):
                    _local_evidence(Path(temporary), backend_labels=labels)

        duplicate_config = json.dumps(
            {
                "architecture": "amd64",
                "os": "linux",
                "config": {
                    "Labels": {
                        "org.opencontainers.image.source": valid_source,
                        "org.opencontainers.image.revision": valid_revision,
                    }
                },
            },
            separators=(",", ":"),
        ).encode()
        duplicate_config = duplicate_config.replace(
            f'"org.opencontainers.image.revision":"{valid_revision}"'.encode(),
            (
                f'"org.opencontainers.image.revision":"{valid_revision}",'
                f'"org.opencontainers.image.revision":"{valid_revision}"'
            ).encode(),
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                _local_evidence(Path(temporary), backend_config_raw=duplicate_config)

    def test_chart_digest_overrides_are_exact_committed_pins(self) -> None:
        pins = read_pinned_chart_images(REPOSITORY_ROOT)
        self.assertEqual(
            set(pins),
            {
                "redis.image.digest",
                "redis.metrics.image.digest",
                "nats.image.digest",
                "nats.container.image.digest",
            },
        )
        sample = "redis:\n  image:\n    digest: sha256:" + "a" * 64 + "\n"
        requested = {"redis.image.digest": ("redis", "image", "digest")}
        self.assertEqual(
            _extract_yaml_digest_paths(sample, "fixture.yaml", requested),
            {"redis.image.digest": "sha256:" + "a" * 64},
        )
        for invalid in (
            sample + "redis:\n  image:\n    digest: sha256:" + "b" * 64 + "\n",
            "redis:\n  image:\n    digest: null\n",
            "redis:\n\timage:\n\t  digest: sha256:" + "a" * 64 + "\n",
        ):
            with self.assertRaises(ValueError):
                _extract_yaml_digest_paths(invalid, "fixture.yaml", requested)

    def test_invalid_or_empty_checkov_helm_reports_fail_closed(self) -> None:
        valid = {
            "check_type": "helm",
            "results": {
                "passed_checks": [{"check_id": "CKV_K8S_1"}],
                "failed_checks": [],
                "skipped_checks": [],
                "parsing_errors": [],
            },
            "summary": {
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "parsing_errors": 0,
                "resource_count": 1,
            },
        }
        self.assertEqual(verify_document(valid)["total_checks"], 1)
        sca_image = {
            "check_type": "sca_image",
            "results": {},
            "summary": {},
        }
        self.assertEqual(verify_document([valid, sca_image])["total_checks"], 1)
        for mutate in (
            lambda report: report.update(check_type="terraform"),
            lambda report: report["results"].update(parsing_errors=["bad.yaml"]),
            lambda report: report["summary"].update(parsing_errors=1),
            lambda report: report["summary"].update(resource_count=0),
            lambda report: report["results"].update(passed_checks=[]),
            lambda report: report["summary"].update(passed=0),
        ):
            report = json.loads(json.dumps(valid))
            mutate(report)
            with self.assertRaises(CoverageError):
                verify_document(report)
        skipped_only = json.loads(json.dumps(valid))
        skipped_only["results"].update(
            passed_checks=[], skipped_checks=[{"check_id": "CKV_K8S_1"}]
        )
        skipped_only["summary"].update(passed=0, skipped=1)
        with self.assertRaisesRegex(CoverageError, "skipped-only"):
            verify_document(skipped_only)
        with self.assertRaises(CoverageError):
            verify_document({"passed": 0, "failed": 0, "resource_count": 0})
        with self.assertRaises(CoverageError):
            verify_document([valid, {"check_type": "terraform"}])

    def test_workflow_keeps_full_scan_and_adds_three_blocking_chart_scans(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 60", workflow)
        self.assertIn("framework: all", workflow)
        self.assertIn("var_file: .checkov-backend-values.yaml", workflow)
        self.assertIn("output_file_path: results.sarif,", workflow)
        self.assertEqual(workflow.count("framework: helm"), 3)
        self.assertEqual(workflow.count("output_format: sarif,json"), 3)
        self.assertIn(
            "charts/university-ecosystem/values-staging.yaml,.checkov-helm-values/university-ecosystem.json",
            workflow,
        )
        self.assertIn(
            "charts/revocation-store/values-staging.yaml,.checkov-helm-values/revocation-store.json",
            workflow,
        )
        self.assertIn("var_file: .checkov-helm-values/redis-compat.json", workflow)
        for name in ("university-ecosystem", "revocation-store", "redis-compat"):
            self.assertIn(f"checkov-helm-{name}", workflow)
            self.assertIn(f"results-helm-{name}.json", workflow)
            self.assertIn(f"filtered-helm-{name}.sarif", workflow)
        self.assertIn("prepare_checkov_helm_contexts.py", workflow)
        self.assertIn("verify_checkov_helm_json.py", workflow)
        self.assertIn(
            '"scripts/quality/create_checkov_oci_image_evidence.py"', workflow
        )
        self.assertIn('"scripts/quality/prepare_checkov_helm_contexts.py"', workflow)
        self.assertIn('"scripts/quality/verify_checkov_helm_json.py"', workflow)
        self.assertIn('"tests/test_checkov_helm_coverage_contract.py"', workflow)
        prepare_start = workflow.index(
            "- name: Prepare finite Checkov Helm values from actual image evidence"
        )
        render_start = workflow.index(
            "- name: Render each chart with the finite Checkov Helm values"
        )
        profile_generator = workflow[prepare_start:render_start]
        self.assertIn("--network none --read-only", profile_generator)
        self.assertIn("--memory 512m --cpus 1 --pids-limit 64", profile_generator)
        self.assertIn('--user "$(id -u):$(id -g)"', profile_generator)
        self.assertIn("--tmpfs /tmp:rw,nosuid,nodev,size=128m", profile_generator)
        self.assertIn('"$GITHUB_WORKSPACE:/workspace:ro"', profile_generator)
        self.assertIn('"$oci_dir:/oci:ro"', profile_generator)
        self.assertIn('"$profile_dir:/profiles:rw"', profile_generator)
        self.assertIn('--entrypoint python "$checkov_image"', profile_generator)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", profile_generator)
        self.assertNotIn("pip install", profile_generator)
        for chart_root in (
            '"charts/university-ecosystem"',
            '"charts/revocation-store"',
            '"charts/redis-compat"',
        ):
            self.assertIn(chart_root, workflow)
        self.assertIn("--network none", workflow)
        self.assertIn("--dependency-update=false", workflow)
        self.assertIn("git rev-parse --verify HEAD", workflow)
        self.assertIn("git status --porcelain=v1 --untracked-files=all", workflow)
        capture_start = workflow.index(
            "- name: Preserve source-bound Checkov evidence before input cleanup"
        )
        cleanup_start = workflow.index("- name: Remove local OCI and Helm scan inputs")
        upload_start = workflow.index("- name: Upload source-bound Checkov evidence")
        final_gate_start = workflow.index(
            "- name: Require all Checkov scans and Helm coverage guards to pass"
        )
        self.assertLess(capture_start, cleanup_start)
        self.assertLess(cleanup_start, upload_start)
        self.assertLess(upload_start, final_gate_start)
        capture = workflow[capture_start:cleanup_start]
        expected_artifacts = {
            "image-evidence.json",
            "image-evidence.json.sha256",
            "university-ecosystem.json",
            "revocation-store.json",
            "redis-compat.json",
            "results.sarif",
            "results-helm-university-ecosystem.sarif",
            "results-helm-revocation-store.sarif",
            "results-helm-redis-compat.sarif",
            "results-helm-university-ecosystem.json",
            "results-helm-revocation-store.json",
            "results-helm-redis-compat.json",
        }
        copied = {
            line.rsplit(" ", 1)[-1]
            for line in capture.splitlines()
            if "copy_required " in line
        }
        self.assertEqual(copied, expected_artifacts)
        self.assertIn("if: always()", capture)
        self.assertNotIn(".oci.tar", capture)
        self.assertNotIn(".yaml", capture)
        self.assertNotIn("render", capture.lower())
        upload = workflow[upload_start:final_gate_start]
        self.assertIn("if: always()", upload)
        self.assertIn(
            "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2",
            upload,
        )
        self.assertIn("path: " + "$" + "{{ runner.temp }}/checkov-evidence", upload)
        self.assertIn("retention-days: 7", upload)


if __name__ == "__main__":
    unittest.main()
