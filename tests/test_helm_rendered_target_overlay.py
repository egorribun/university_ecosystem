"""Behavioral tests for the isolated Helm rendered-target helper."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tarfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPOSITORY_ROOT / "scripts/quality/helm_rendered_target_overlay.py"
REGISTRY_PATH = REPOSITORY_ROOT / "scripts/quality/helm_semgrep_profile_registry.json"

_spec = importlib.util.spec_from_file_location(
    "helm_rendered_target_overlay_candidate", HELPER_PATH
)
assert _spec is not None and _spec.loader is not None
helm_overlay = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = helm_overlay
_spec.loader.exec_module(helm_overlay)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_oid(data: bytes) -> str:
    return _sha(data)[:40]


def _make_synthetic_archive(
    pin: Mapping[str, Any], *, symlink_member: bool = False
) -> bytes:
    executable = b"test-only Helm placeholder; never executed"
    buffer = io.BytesIO()
    if pin["archive_type"] == "zip":
        with zipfile.ZipFile(
            buffer, mode="w", compression=zipfile.ZIP_STORED
        ) as package:
            package.writestr(pin["archive_member"], executable)
    elif pin["archive_type"] == "tar.gz":
        with tarfile.open(fileobj=buffer, mode="w:gz") as package:
            member = tarfile.TarInfo(pin["archive_member"])
            if symlink_member:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../../../outside"
                package.addfile(member)
            else:
                member.size = len(executable)
                member.mode = 0o755
                package.addfile(member, io.BytesIO(executable))
    else:
        raise AssertionError("unexpected pinned Helm archive type")
    return buffer.getvalue()


def _synthetic_tool_fixture(
    platform_key: str | None = None, *, symlink_member: bool = False
) -> tuple[bytes, bytes]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    platform_key = platform_key or helm_overlay._platform_key()
    pins = [
        pin
        for pin in registry["helm_toolchains"]
        if pin["platform_key"] == platform_key
    ]
    assert len(pins) == 1
    archive = _make_synthetic_archive(pins[0], symlink_member=symlink_member)
    pins[0]["archive_sha256"] = _sha(archive)
    registry_bytes = (json.dumps(registry, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return registry_bytes, archive


TEST_REGISTRY_BYTES, TEST_HELM_ARCHIVE = _synthetic_tool_fixture()
assert _sha(REGISTRY_PATH.read_bytes()) == (
    "6536cc971f493f737ef49fad637351b7857c11fff932b313fac2fb87bdb95345"
)
helm_overlay.EXPECTED_PROFILE_REGISTRY_SHA256 = _sha(TEST_REGISTRY_BYTES)


def _copy_stage_snapshot(
    destination: Path, registry_bytes: bytes = TEST_REGISTRY_BYTES
) -> list[dict[str, str]]:
    charts = destination / "charts"
    shutil.copytree(REPOSITORY_ROOT / "charts", charts)
    registry_path = destination / "scripts/quality/helm_semgrep_profile_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_bytes(registry_bytes)

    paths = [path for path in charts.rglob("*") if path.is_file()]
    paths.append(registry_path)
    manifest = []
    for path in sorted(
        paths, key=lambda item: item.relative_to(destination).as_posix()
    ):
        content = path.read_bytes()
        relative = path.relative_to(destination).as_posix()
        manifest.append(
            {
                "path": relative,
                "mode": "100644",
                "oid": _git_oid(content),
                "stage": "0",
                "sha256": _sha(content),
            }
        )
    return manifest


def _source_header(path: str) -> str:
    if path.startswith("charts/university-ecosystem/templates/"):
        return "university-ecosystem/templates/" + path.rsplit("/", 1)[1]
    if path.startswith("charts/revocation-store/templates/"):
        return "revocation-store/templates/" + path.rsplit("/", 1)[1]
    if path == "charts/redis-compat/templates/redis.yaml":
        return "university-ecosystem/charts/redis-compat/templates/redis.yaml"
    raise AssertionError(f"unexpected test source path: {path}")


def _profile_sources(registry: Mapping[str, Any]) -> dict[str, list[str]]:
    sources = {name: [] for name in helm_overlay.PROFILE_NAMES}
    roles = {row["path"]: row["role"] for row in registry["source_roles"]}
    for path, role in roles.items():
        if role != "resource":
            continue
        if path.endswith("gateway-api.yaml"):
            profile = "gateway-api-isolated-synthetic-apis"
        elif path.endswith("backup-cronjob.yaml") or path.endswith(
            ("keda-scaledobjects.yaml", "keda-trigger-auth.yaml")
        ):
            profile = "university-feature-enabled-development"
        elif path.endswith("secrets.yaml"):
            profile = "university-development"
        elif path.startswith("charts/revocation-store/"):
            profile = {
                "redis-configmap.yaml": "revocation-store-development",
                "redis-networkpolicy.yaml": "revocation-store-staging",
            }.get(path.rsplit("/", 1)[1], "revocation-store-production")
        else:
            profile = "university-development"
        sources[profile].append(path)

    app_control = "charts/university-ecosystem/templates/backend-service.yaml"
    sources["university-staging"].append(app_control)
    sources["university-production"].append(app_control)
    sources["university-feature-enabled-development"].append(app_control)
    return sources


class FakeBoundedRunner:
    def __init__(
        self,
        registry: Mapping[str, Any],
        *,
        omit_source: str | None = None,
        duplicate: bool = False,
        duplicate_api_version: str | None = None,
    ):
        self.sources = _profile_sources(registry)
        self.omit_source = omit_source
        self.duplicate = duplicate
        self.duplicate_api_version = duplicate_api_version
        self.calls: list[tuple[list[str], Path, float, int, int]] = []

    def __call__(
        self,
        argv: Sequence[str],
        cwd: Path,
        timeout: float,
        stdout_limit: int,
        stderr_limit: int,
    ) -> Any:
        self.calls.append((list(argv), cwd, timeout, stdout_limit, stderr_limit))
        assert timeout <= helm_overlay.HELM_TIMEOUT_SECONDS
        assert stdout_limit == helm_overlay.HELM_STDOUT_LIMIT
        assert stderr_limit == helm_overlay.HELM_STDERR_LIMIT
        if len(argv) > 1 and argv[1] == "version":
            return helm_overlay.BoundedProcessResult(0, b"v4.2.4", b"")
        assert "--dependency-update=false" in argv
        assert "--enable-dns" not in argv
        if "gateway-contract" in argv:
            profile = "gateway-api-isolated-synthetic-apis"
        else:
            release = argv[2]
            profile = {
                "development-contract": "university-development",
                "staging-contract": "university-staging",
                "production-contract": "university-production",
                "feature-contract": "university-feature-enabled-development",
            }.get(release)
            if (
                release.endswith("-contract")
                and release.split("-", 1)[0]
                in {
                    "development",
                    "staging",
                    "production",
                }
                and "revocation-store" in argv[3]
            ):
                profile = f"revocation-store-{release.removesuffix('-contract')}"
        assert profile is not None
        documents: list[str] = []
        render_sources = list(self.sources[profile])
        if (
            profile == "gateway-api-isolated-synthetic-apis"
            and self.omit_source
            == "charts/university-ecosystem/templates/gateway-api.yaml"
        ):
            render_sources.append(
                "charts/university-ecosystem/templates/backend-service.yaml"
            )
        for index, path in enumerate(render_sources):
            if path == self.omit_source:
                continue
            api_version = "apps/v1" if self.duplicate_api_version else "v1"
            kind = "Deployment" if self.duplicate_api_version else "ConfigMap"
            body = (
                f"# Source: {_source_header(path)}\n"
                f"apiVersion: {api_version}\n"
                f"kind: {kind}\n"
                "metadata:\n"
                f"  name: {profile}-{index}\n"
            )
            documents.append(body)
            if self.duplicate and index == 0:
                documents.append(body)
            if self.duplicate_api_version and index == 0:
                documents.append(
                    body.replace(api_version, self.duplicate_api_version, 1)
                )
        if profile == "university-development":
            documents.append(
                "# Source: revocation-store/templates/deployment-contract.yaml\n"
                "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: guard-only-test\n"
            )
        output = ("---\n".join(documents) + "\n").encode("utf-8")
        return helm_overlay.BoundedProcessResult(0, output, b"")


@pytest.fixture(scope="module")
def helm_tool(
    tmp_path_factory: pytest.TempPathFactory,
) -> helm_overlay.VerifiedHelmTool:
    stage = tmp_path_factory.mktemp("stage-tool") / "source"
    stage.mkdir()
    manifest = _copy_stage_snapshot(stage)
    extraction_root = tmp_path_factory.mktemp("verified-tool") / "helm"
    archive = tmp_path_factory.mktemp("helm-archive") / "synthetic-helm.archive"
    archive.write_bytes(TEST_HELM_ARCHIVE)
    return helm_overlay.verify_helm_archive(
        stage,
        manifest,
        archive,
        extraction_root,
    )


@pytest.fixture
def staged_source(tmp_path: Path) -> tuple[Path, list[dict[str, str]], dict[str, Any]]:
    root = tmp_path / "stage"
    root.mkdir()
    manifest = _copy_stage_snapshot(root)
    registry = json.loads(TEST_REGISTRY_BYTES)
    return root, manifest, registry


def _manifest_sha(manifest: Sequence[Mapping[str, str]]) -> str:
    payload = (
        json.dumps(
            {"targets": list(manifest)}, indent=2, sort_keys=True, ensure_ascii=False
        )
        + "\n"
    ).encode("utf-8")
    return _sha(payload)


def test_prepare_overlay_keeps_stage_bytes_and_excludes_guard_templates(
    staged_source: tuple[Path, list[dict[str, str]], dict[str, Any]],
    helm_tool: helm_overlay.VerifiedHelmTool,
    tmp_path: Path,
) -> None:
    root, manifest, registry = staged_source
    worktree_copy = tmp_path / "worktree"
    shutil.copytree(root, worktree_copy)
    mutable = (
        worktree_copy / "charts/university-ecosystem/templates/backend-deployment.yaml"
    )
    mutable.write_text("# unrelated worktree bytes\n", encoding="utf-8")
    runner = FakeBoundedRunner(registry)
    overlay, proof = helm_overlay.prepare_overlay(
        root,
        tmp_path / "scan-overlay",
        manifest,
        helm_tool=helm_tool,
        bounded_runner=runner,
    )

    assert proof["source_snapshot_manifest_sha256"] == _manifest_sha(manifest)
    assert proof["profile_registry_sha256"] == _sha(TEST_REGISTRY_BYTES)
    assert proof["target_model"] == "helm-rendered-v1"
    assert proof["report_scope"] == "renderer-only"
    assert proof["scanner_invoked"] is False
    assert proof["cluster_or_cni_claim"] is False
    assert len(proof["template_sources"]) == 40
    assert len(proof["guard_only_sources"]) == 4
    assert proof["rendered_object_count"] > 0
    assert {row["name"] for row in proof["profiles"]} == set(helm_overlay.PROFILE_NAMES)
    assert all(len(row["view_sha256"]) == 64 for row in proof["profiles"])
    assert all(row["deployment_evidence"] is False for row in proof["profiles"])
    production_profile = next(
        row for row in proof["profiles"] if row["name"] == "university-production"
    )
    assert "not-deployment-evidence" in production_profile["profile_kind"]
    assert any(
        "staging values" in label for label in production_profile["synthetic_overrides"]
    )
    gateway_profile = next(
        row
        for row in proof["profiles"]
        if row["name"] == "gateway-api-isolated-synthetic-apis"
    )
    assert "isolated-diagnostic-only" in gateway_profile["profile_kind"]
    assert all(
        row["role"] in {"resource", "guard-only"} for row in proof["template_sources"]
    )
    assert all(
        row["origin"] in {"staged-index"} or row["origin"].startswith("helm-profile:")
        for row in proof["targets"]
    )
    assert all(
        not (overlay / path).exists() for path in helm_overlay._roles(registry)[1]
    )
    assert "guard-only-test" not in (
        overlay / "charts/rendered-profiles/university-development.yaml"
    ).read_text(encoding="utf-8")
    for profile in proof["profiles"]:
        view = overlay / profile["view_path"]
        assert _sha(view.read_bytes()) == profile["view_sha256"]
    non_template = "charts/university-ecosystem/values.yaml"
    assert (overlay / non_template).read_bytes() == (root / non_template).read_bytes()
    assert runner.calls[0][0][1] == "version"
    assert (
        len(
            [
                call
                for call in runner.calls
                if len(call[0]) > 1 and call[0][1] == "template"
            ]
        )
        == 8
    )


def test_stage_snapshot_hash_mismatch_fails_before_helm(
    staged_source: tuple[Path, list[dict[str, str]], dict[str, Any]],
    helm_tool: helm_overlay.VerifiedHelmTool,
    tmp_path: Path,
) -> None:
    root, manifest, registry = staged_source
    target = root / "charts/university-ecosystem/templates/backend-deployment.yaml"
    target.write_text("# changed after stage snapshot\n", encoding="utf-8")
    runner = FakeBoundedRunner(registry)
    with pytest.raises(
        helm_overlay.HelmOverlayError,
        match=r"stage snapshot chart tree|staged chart input hash",
    ):
        helm_overlay.prepare_overlay(
            root,
            tmp_path / "bad-overlay",
            manifest,
            helm_tool=helm_tool,
            bounded_runner=runner,
        )
    assert runner.calls == []


def test_missing_required_source_profile_fails_closed(
    staged_source: tuple[Path, list[dict[str, str]], dict[str, Any]],
    helm_tool: helm_overlay.VerifiedHelmTool,
    tmp_path: Path,
) -> None:
    root, manifest, registry = staged_source
    runner = FakeBoundedRunner(
        registry,
        omit_source="charts/university-ecosystem/templates/gateway-api.yaml",
    )
    with pytest.raises(
        helm_overlay.HelmOverlayError, match="required profile does not render"
    ):
        helm_overlay.prepare_overlay(
            root,
            tmp_path / "missing-source-overlay",
            manifest,
            helm_tool=helm_tool,
            bounded_runner=runner,
        )
    assert not (tmp_path / "missing-source-overlay").exists()


def test_duplicate_kubernetes_identity_fails_closed(
    staged_source: tuple[Path, list[dict[str, str]], dict[str, Any]],
    helm_tool: helm_overlay.VerifiedHelmTool,
    tmp_path: Path,
) -> None:
    root, manifest, registry = staged_source
    runner = FakeBoundedRunner(registry, duplicate=True)
    with pytest.raises(
        helm_overlay.HelmOverlayError, match="duplicate Kubernetes identity"
    ):
        helm_overlay.prepare_overlay(
            root,
            tmp_path / "duplicate-overlay",
            manifest,
            helm_tool=helm_tool,
            bounded_runner=runner,
        )
    assert not (tmp_path / "duplicate-overlay").exists()


def test_duplicate_kubernetes_identity_across_api_versions_fails_closed(
    staged_source: tuple[Path, list[dict[str, str]], dict[str, Any]],
    helm_tool: helm_overlay.VerifiedHelmTool,
    tmp_path: Path,
) -> None:
    root, manifest, registry = staged_source
    runner = FakeBoundedRunner(registry, duplicate_api_version="apps/v1beta1")
    with pytest.raises(
        helm_overlay.HelmOverlayError, match="duplicate Kubernetes identity"
    ):
        helm_overlay.prepare_overlay(
            root,
            tmp_path / "duplicate-version-overlay",
            manifest,
            helm_tool=helm_tool,
            bounded_runner=runner,
        )
    assert not (tmp_path / "duplicate-version-overlay").exists()


def test_unknown_template_and_registry_drift_fail_closed(
    staged_source: tuple[Path, list[dict[str, str]], dict[str, Any]],
) -> None:
    root, manifest, _registry = staged_source
    unknown = root / "charts/university-ecosystem/templates/unknown.yaml"
    unknown.write_text("# unexpected template\n", encoding="utf-8")
    with pytest.raises(helm_overlay.HelmOverlayError, match="chart tree differs"):
        helm_overlay.helm_archive_pin(root, manifest)

    unknown.unlink()
    changed = root / "scripts/quality/helm_semgrep_profile_registry.json"
    content = json.loads(changed.read_text(encoding="utf-8"))
    content["profiles"][0]["view_path"] = "charts/rendered-profiles/changed.yaml"
    changed.write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    row = next(
        item
        for item in manifest
        if item["path"] == "scripts/quality/helm_semgrep_profile_registry.json"
    )
    raw = changed.read_bytes()
    row["sha256"] = _sha(raw)
    row["oid"] = _git_oid(raw)
    with pytest.raises(helm_overlay.HelmOverlayError, match="profile registry drifted"):
        helm_overlay.helm_archive_pin(root, manifest)


def test_archive_checksum_and_bounded_runner_fail_closed(
    staged_source: tuple[Path, list[dict[str, str]], dict[str, Any]],
    tmp_path: Path,
) -> None:
    root, manifest, _registry = staged_source
    incorrect = tmp_path / "wrong-helm.zip"
    incorrect.write_bytes(b"not the pinned archive")
    with pytest.raises(helm_overlay.HelmOverlayError, match="official checksum"):
        helm_overlay.verify_helm_archive(
            root, manifest, incorrect, tmp_path / "bad-helm"
        )

    oversize = helm_overlay.bounded_process_runner(
        [sys.executable, "-c", "print('x' * 1000000)"],
        tmp_path,
        5.0,
        1024,
        1024,
    )
    assert oversize.output_limit_exceeded is True
    assert len(oversize.stdout) <= 1024
    assert len(oversize.stderr) <= 1024

    timeout = helm_overlay.bounded_process_runner(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        tmp_path,
        0.1,
        1024,
        1024,
    )
    assert timeout.timed_out is True


def test_linux_tar_archive_verification_and_symlink_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_bytes, archive_bytes = _synthetic_tool_fixture("linux-amd64")
    monkeypatch.setattr(helm_overlay, "_platform_key", lambda: "linux-amd64")
    monkeypatch.setattr(
        helm_overlay, "EXPECTED_PROFILE_REGISTRY_SHA256", _sha(registry_bytes)
    )

    stage = tmp_path / "linux-stage"
    stage.mkdir()
    manifest = _copy_stage_snapshot(stage, registry_bytes)
    archive = tmp_path / "synthetic-linux-helm.tar.gz"
    archive.write_bytes(archive_bytes)
    tool = helm_overlay.verify_helm_archive(
        stage, manifest, archive, tmp_path / "linux-helm"
    )
    assert tool.platform_key == "linux-amd64"
    assert tool.executable.name == "helm"
    assert tool.executable.read_bytes() == b"test-only Helm placeholder; never executed"

    malicious_registry, malicious_archive = _synthetic_tool_fixture(
        "linux-amd64", symlink_member=True
    )
    monkeypatch.setattr(
        helm_overlay,
        "EXPECTED_PROFILE_REGISTRY_SHA256",
        _sha(malicious_registry),
    )
    malicious_stage = tmp_path / "linux-malicious-stage"
    malicious_stage.mkdir()
    malicious_manifest = _copy_stage_snapshot(malicious_stage, malicious_registry)
    malicious_archive_path = tmp_path / "malicious-linux-helm.tar.gz"
    malicious_archive_path.write_bytes(malicious_archive)
    rejected_extraction = tmp_path / "rejected-linux-helm"
    with pytest.raises(
        helm_overlay.HelmOverlayError, match="bounded regular executable"
    ):
        helm_overlay.verify_helm_archive(
            malicious_stage,
            malicious_manifest,
            malicious_archive_path,
            rejected_extraction,
        )
    assert not rejected_extraction.exists()
