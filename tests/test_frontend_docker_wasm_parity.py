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


FROM_STAGE_PATTERN = re.compile(
    r"(?im)^[ \t]*FROM[ \t]+(?:--platform=[^ \t]+[ \t]+)?"
    r"(?P<image>[^ \t]+)(?:[ \t]+AS[ \t]+(?P<alias>[A-Za-z0-9_.-]+))?[ \t]*$"
)


def _stage_body(dockerfile: str, alias: str, stages: list[re.Match]) -> str:
    indexes = [
        index
        for index, stage in enumerate(stages)
        if stage.group("alias") is not None and stage.group("alias").casefold() == alias
    ]
    assert len(indexes) == 1, f"expected exactly one Docker stage named {alias}"
    index = indexes[0]
    start = stages[index].start()
    end = stages[index + 1].start() if index + 1 < len(stages) else len(dockerfile)
    return dockerfile[start:end]


def test_frontend_image_wasm_toolchain_matches_canonical_producer() -> None:
    workflow = yaml.safe_load(PRODUCER.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["build"]["steps"]
    rust_version = str(_step(steps, "Setup Rust toolchain")["with"]["toolchain"])
    wasm_pack = _step(steps, "Install wasm-pack")["with"]["tool"]
    binaryen_install = _step(steps, "Install pinned wasm-opt")["run"]
    binaryen_version = re.search(r'binaryen_version="(version_\d+)"', binaryen_install)
    binaryen_checksum = re.search(r'binaryen_sha256="([0-9a-f]{64})"', binaryen_install)
    assert rust_version == "1.99.0"
    assert wasm_pack == "wasm-pack@0.15.0"
    assert binaryen_version is not None
    assert binaryen_version.group(1) == "version_133"
    assert binaryen_checksum is not None

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"(?m)^ARG WASM_BUILDPLATFORM=linux/amd64$", dockerfile)
    assert re.search(
        rf"(?m)^FROM --platform=\$WASM_BUILDPLATFORM rust:{re.escape(rust_version)}-slim-bookworm"
        r"@sha256:[0-9a-f]{64} AS wasm-builder$",
        dockerfile,
    )
    official_digest = "2c3a22f0a5533ea2dd5a16627bc841228151faa2d4de2644ac9987e4a2f1f2fa"  # public Docker registry digest from verified manifest receipt
    assert f"rust:1.99.0-slim-bookworm@sha256:{official_digest}" in dockerfile
    assert "cargo install wasm-pack --version 0.15.0 --locked" in dockerfile
    binaryen_url = (
        f"https://github.com/WebAssembly/binaryen/releases/download/{binaryen_version.group(1)}/"
        f"binaryen-{binaryen_version.group(1)}-x86_64-linux.tar.gz"
    )
    assert not re.search(r"(?m)^ADD\b", dockerfile)  # Checkov CKV_DOCKER_4.
    assert (
        "apt-get install -y --no-install-recommends curl ca-certificates" in dockerfile
    )
    assert "curl --fail --silent --show-error --location" in dockerfile
    assert "--proto '=https' --tlsv1.2" in dockerfile
    assert f'--output /tmp/binaryen.tar.gz "{binaryen_url}"' in dockerfile
    checksum_check = (
        f"printf '%s  %s\\n' '{binaryen_checksum.group(1)}' /tmp/binaryen.tar.gz"
        " | sha256sum --check --strict"
    )
    assert checksum_check in dockerfile
    assert dockerfile.index(binaryen_url) < dockerfile.index(checksum_check)
    assert dockerfile.index(checksum_check) < dockerfile.index(
        "tar -xzf /tmp/binaryen.tar.gz"
    )
    assert (
        "tar -xzf /tmp/binaryen.tar.gz --strip-components=1 -C /opt/binaryen"
        in dockerfile
    )
    assert '/opt/binaryen/bin/wasm-opt --version | grep -Fq "version 133"' in dockerfile
    assert 'ENV PATH="/opt/binaryen/bin:${PATH}"' in dockerfile
    assert "--remap-path-prefix=/root/.cargo=/usr/local/cargo" in dockerfile
    assert "--remap-path-prefix=/wasm=/work/frontend" in dockerfile
    assert "wasm-pack build rust-crypto --target web --release" in dockerfile
    assert "wasm-pack build wasm-sanitizer --target web --release" in dockerfile


def test_frontend_image_validates_built_wasm_against_checked_in_source_provenance() -> (
    None
):
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    from_stages = list(FROM_STAGE_PATTERN.finditer(dockerfile))
    from_instructions = re.findall(r"(?im)^[ \t]*FROM\b[^\r\n]*$", dockerfile)
    assert len(from_stages) == len(from_instructions)

    stage_indexes = {
        alias: next(
            index
            for index, stage in enumerate(from_stages)
            if stage.group("alias") is not None
            and stage.group("alias").casefold() == alias
        )
        for alias in (
            "base",
            "wasm-builder",
            "wasm-packages",
            "deps",
            "builder",
            "prod-deps",
            "runtime",
        )
    }
    assert len(stage_indexes) == len(from_stages)
    assert list(stage_indexes.values()) == sorted(stage_indexes.values())
    assert (
        from_stages[stage_indexes["base"]].group("image").casefold().startswith("node:")
    )
    assert (
        from_stages[stage_indexes["wasm-packages"]].group("image").casefold() == "base"
    )
    assert from_stages[stage_indexes["deps"]].group("image").casefold() == "base"
    assert from_stages[stage_indexes["builder"]].group("image").casefold() == "deps"
    assert from_stages[stage_indexes["prod-deps"]].group("image").casefold() == "base"

    wasm_builder = _stage_body(dockerfile, "wasm-builder", from_stages)
    assert "WORKDIR /wasm" in wasm_builder
    assert "COPY frontend/rust-crypto ./rust-crypto" in wasm_builder
    assert "COPY frontend/wasm-sanitizer ./wasm-sanitizer" in wasm_builder
    assert "wasm-pack build rust-crypto --target web --release" in wasm_builder
    assert "wasm-pack build wasm-sanitizer --target web --release" in wasm_builder

    wasm_packages = _stage_body(dockerfile, "wasm-packages", from_stages)
    assert (
        "COPY frontend/scripts/finalize-wasm-licenses.mjs ./scripts/finalize-wasm-licenses.mjs"
        in wasm_packages
    )
    for crate in ("rust-crypto", "wasm-sanitizer"):
        for legal_file in (
            "LICENSE",
            "LICENSE-THIRD-PARTY",
            "LICENSE-THIRD-PARTY-SOURCES.md",
            "LICENSE-RUST-STD",
            "LICENSE-RUST-STD-COPYRIGHT.txt",
            "LICENSE-RUST-STD-SOURCES.md",
        ):
            assert f"frontend/{crate}/{legal_file}" in wasm_packages
        assert (
            f"COPY --from=wasm-builder /wasm/{crate}/pkg ./{crate}/pkg" in wasm_packages
        )
    finalizer = "RUN node scripts/finalize-wasm-licenses.mjs"
    assert finalizer in wasm_packages
    assert "wasm-pack build" not in wasm_packages
    assert max(
        wasm_packages.index(f"COPY frontend/{crate}/")
        for crate in ("rust-crypto", "wasm-sanitizer")
    ) < wasm_packages.index(finalizer)

    for consumer in ("deps", "builder", "prod-deps", "runtime"):
        consumer_body = _stage_body(dockerfile, consumer, from_stages)
        assert "--from=wasm-packages" in consumer_body
        for crate in ("rust-crypto", "wasm-sanitizer"):
            assert f"/app/{crate}/pkg ./{crate}/pkg" in consumer_body

    for consumer, next_command in (
        ("deps", "until npm ci"),
        ("builder", "RUN rm -rf dist && npm run build"),
        ("prod-deps", "until npm ci --omit=dev"),
    ):
        consumer_body = _stage_body(dockerfile, consumer, from_stages)
        validation = "RUN node scripts/verify-wasm-artifacts.mjs"
        assert validation in consumer_body
        assert consumer_body.index(validation) < consumer_body.index(next_command)

    builder = _stage_body(dockerfile, "builder", from_stages)
    assert "ENV SKIP_WASM_BUILD=1" in builder
    assert "COPY frontend ./" in builder

    build_wasm = (ROOT / "frontend/scripts/build-wasm.mjs").read_text(encoding="utf-8")
    assert (
        "await validateArtifacts(frontendRoot, { requireSourceProvenance: true })"
        in build_wasm
    )
    verifier = (ROOT / "frontend/scripts/verify-wasm-artifacts.mjs").read_text(
        encoding="utf-8"
    )
    assert (
        "if (requireSourceProvenance) await validateSourceProvenance(root)" in verifier
    )
    assert (
        "validateWasmArtifacts(frontendRoot, { requireSourceProvenance: true })"
        in verifier
    )


@pytest.mark.parametrize("stage", ["deps", "prod-deps"])
def test_frontend_npm_install_validates_source_bound_wasm_before_network_retry(
    stage: str,
) -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    stage_body = dockerfile.split(f"FROM base AS {stage}\n", 1)[1].split("\nFROM ", 1)[
        0
    ]
    assert "COPY frontend/WASM_SOURCE_PROVENANCE.json ./" in stage_body
    for package in ("rust-crypto", "wasm-sanitizer"):
        assert (
            f"COPY frontend/{package}/Cargo.toml frontend/{package}/Cargo.lock ./{package}/"
            in stage_body
        )
        assert (
            f"COPY frontend/{package}/src/lib.rs ./{package}/src/lib.rs" in stage_body
        )
        assert "--from=wasm-packages" in stage_body
        assert f"/app/{package}/pkg ./{package}/pkg" in stage_body
    assert "RUN node scripts/verify-wasm-artifacts.mjs" in stage_body
    assert stage_body.index(
        "RUN node scripts/verify-wasm-artifacts.mjs"
    ) < stage_body.index("until npm ci")


@pytest.mark.parametrize("job", ["rust-lint", "rust-tests"])
def test_ci_rust_quality_jobs_use_the_canonical_producer_toolchain(job: str) -> None:
    """Rust lint/coverage evidence must come from the WASM producer's compiler."""
    producer = yaml.safe_load(PRODUCER.read_text(encoding="utf-8"))
    canonical = str(
        _step(producer["jobs"]["build"]["steps"], "Setup Rust toolchain")["with"][
            "toolchain"
        ]
    )
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    setups = [
        step
        for step in ci["jobs"][job]["steps"]
        if str(step.get("uses", "")).startswith("dtolnay/rust-toolchain@")
    ]

    assert [str(step["with"]["toolchain"]) for step in setups] == [canonical]
