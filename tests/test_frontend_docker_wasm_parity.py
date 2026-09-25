"""Keep the release image's WASM builder aligned with the canonical producer."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "frontend.Dockerfile"
PRODUCER = ROOT / ".github/workflows/reusable-e2e-wasm-build.yml"
if not DOCKERFILE.is_file() or not PRODUCER.is_file():
    pytest.skip(  # QUALITY-123 @egorribun
        "Docker build assets are absent from this isolated test checkout",
        allow_module_level=True,
    )


def _step(steps: list[dict], name: str) -> dict:
    return next(step for step in steps if step.get("name") == name)


def test_frontend_image_wasm_toolchain_matches_canonical_producer() -> None:
    workflow = yaml.safe_load(PRODUCER.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["build"]["steps"]
    rust_version = str(_step(steps, "Setup Rust toolchain")["with"]["toolchain"])
    wasm_pack = _step(steps, "Install wasm-pack")["with"]["tool"]
    binaryen_install = _step(steps, "Install pinned wasm-opt")["run"]
    binaryen_version = re.search(r'binaryen_version="(version_\d+)"', binaryen_install)
    binaryen_checksum = re.search(r'binaryen_sha256="([0-9a-f]{64})"', binaryen_install)
    assert rust_version == "1.97.1"
    assert wasm_pack == "wasm-pack@0.13.1"
    assert binaryen_version is not None
    assert binaryen_version.group(1) == "version_117"
    assert binaryen_checksum is not None

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"(?m)^ARG WASM_BUILDPLATFORM=linux/amd64$", dockerfile)
    assert re.search(
        rf"(?m)^FROM --platform=\$WASM_BUILDPLATFORM rust:{re.escape(rust_version)}-slim-bookworm"
        r"@sha256:[0-9a-f]{64} AS wasm-builder$",
        dockerfile,
    )
    official_digest = "2775a09d208ff0d7c1f50490c45b62db929e87ba1dcbc3f2132ac71a704bcdd3"  # pragma: allowlist secret - public Docker image digest
    assert f"rust:1.97.1-slim-bookworm@sha256:{official_digest}" in dockerfile
    assert "cargo install wasm-pack --version 0.13.1 --locked" in dockerfile
    assert (
        f"ADD --checksum=sha256:{binaryen_checksum.group(1)} "
        f"https://github.com/WebAssembly/binaryen/releases/download/{binaryen_version.group(1)}/"
        f"binaryen-{binaryen_version.group(1)}-x86_64-linux.tar.gz" in dockerfile
    )
    assert (
        "tar -xzf /tmp/binaryen.tar.gz --strip-components=1 -C /opt/binaryen"
        in dockerfile
    )
    assert '/opt/binaryen/bin/wasm-opt --version | grep -Fq "version 117"' in dockerfile
    assert 'ENV PATH="/opt/binaryen/bin:${PATH}"' in dockerfile
    assert "--remap-path-prefix=/root/.cargo=/usr/local/cargo" in dockerfile
    assert "--remap-path-prefix=/wasm=/work/frontend" in dockerfile
    assert "wasm-pack build rust-crypto --target web --release" in dockerfile
    assert "wasm-pack build wasm-sanitizer --target web --release" in dockerfile


def test_frontend_image_validates_built_wasm_against_checked_in_source_provenance() -> (
    None
):
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    builder = dockerfile[dockerfile.index("FROM base AS builder") :]
    assert "ENV SKIP_WASM_BUILD=1" in builder
    assert "COPY frontend ./" in builder
    assert "COPY --from=wasm-builder /wasm/rust-crypto/pkg ./rust-crypto/pkg" in builder
    assert (
        "COPY --from=wasm-builder /wasm/wasm-sanitizer/pkg ./wasm-sanitizer/pkg"
        in builder
    )
    assert "RUN node scripts/verify-wasm-artifacts.mjs" in builder
    assert "RUN rm -rf dist && npm run build" in builder
    assert builder.index("RUN node scripts/verify-wasm-artifacts.mjs") < builder.index(
        "RUN rm -rf dist && npm run build"
    )

    build_wasm = (ROOT / "frontend/scripts/build-wasm.mjs").read_text(encoding="utf-8")
    assert (
        "await validateArtifacts(frontendRoot, { requireSourceProvenance: true })"
        in build_wasm
    )
