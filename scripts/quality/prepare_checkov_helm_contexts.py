"""Generate finite Checkov Helm values from sealed local OCI evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from create_checkov_oci_image_evidence import (
    REQUIRED_IMAGES,
    _verified_image_config_labels,
)

DIGEST_PATTERN = re.compile(
    r"^global:\n  backendImageDigest: \"(sha256:[0-9a-f]{64})\"\n?$", re.ASCII
)
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", re.ASCII)
SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$", re.ASCII)
EXPECTED_CHARTS = {
    "university-ecosystem": "charts/university-ecosystem",
    "revocation-store": "charts/revocation-store",
    "redis": "charts/redis-compat",
}

# Read the existing immutable third-party pins from each chart's committed
# values instead of copying their public digests into another policy file.
PINNED_IMAGE_VALUE_PATHS = {
    "charts/university-ecosystem/values.yaml": {
        "redis.image.digest": ("redis", "image", "digest"),
        "redis.metrics.image.digest": ("redis", "metrics", "image", "digest"),
        "nats.image.digest": ("nats", "image", "digest"),
        "nats.container.image.digest": ("nats", "container", "image", "digest"),
    },
    "charts/revocation-store/values.yaml": {
        "redis.image.digest": ("redis", "image", "digest"),
        "redis.metrics.image.digest": ("redis", "metrics", "image", "digest"),
    },
    "charts/revocation-store/values-staging.yaml": {
        "redis.image.digest": ("redis", "image", "digest"),
        "redis.metrics.image.digest": ("redis", "metrics", "image", "digest"),
    },
    "charts/redis-compat/values.yaml": {
        "redis.image.digest": ("image", "digest"),
        "redis.metrics.image.digest": ("metrics", "image", "digest"),
    },
}

# Finite synthetic staging inputs mirror tests/test_helm_staging_contract.py.
# Image repositories and digests, release SHA, and run identity are filled from
# current-source local OCI evidence and GitHub's immutable run metadata below.
STAGING_OVERRIDES: dict[str, Any] = {
    "global.imageTag": "",
    "global.jwtIssuer": "https://api.university.staging.example.org",
    "backend.image.repository": "",
    "backend.image.digest": "",
    "backend.image.tag": "",
    "frontend.image.repository": "",
    "frontend.image.digest": "",
    "gateway.image.repository": "",
    "gateway.image.digest": "",
    "wsHub.image.repository": "",
    "wsHub.image.digest": "",
    "fileProcessor.image.repository": "",
    "fileProcessor.image.digest": "",
    "outboxWorker.image.repository": "",
    "outboxWorker.image.digest": "",
    "backend.config.elasticsearchURL": "https://elasticsearch.staging.internal",
    "backend.config.flagdHost": "flagd.staging.internal",
    "backend.config.mfaTotpActiveEncryptionKeyId": "totp-active-staging-contract",
    "backend.config.storageS3EndpointURL": "https://minio.staging.internal:443",
    "gateway.config.otelEndpoint": "otel-collector.staging.internal:4317",
    "fileProcessor.config.minioEndpoint": "minio.staging.internal:443",
    "fileProcessor.config.temporalHost": "temporal.staging.internal:7233",
    "fileProcessor.config.otlpEndpoint": "otel-collector.staging.internal:4317",
    # TEST-NET/IPv6 documentation peers exist only in the generated scanner profile.
    "backend.config.trustedProxies": ["192.0.2.13/32", "2001:db8::13"],
    "gateway.config.trustedProxies": ["192.0.2.11/32", "2001:db8::11"],
    "wsHub.config.trustedProxies": ["198.51.100.12/32", "2001:db8::12"],
    "ingress.hosts[0].host": "university.staging.example.org",
    "ingress.hosts[1].host": "api.university.staging.example.org",
    "ingress.tls[0].hosts[0]": "university.staging.example.org",
    "ingress.tls[0].hosts[1]": "api.university.staging.example.org",
    "wsHub.config.allowedOrigins[0]": "https://university.staging.example.org",
    "wsHub.config.otelEndpoint": "otel-collector.staging.internal:4317",
    "cwv.releaseSHA": "",
    "cwv.frontendImageDigest": "",
    "cwv.deploymentURL": "https://university.staging.example.org",
    "cwv.deployedAt": "2026-08-26T00:00:00Z",
    "cwv.allowedOrigins[0]": "https://university.staging.example.org",
    "cwv.exportOIDC.repository": "example/university-ecosystem",
    "cwv.exportOIDC.workflowRef": "example/university-ecosystem/.github/workflows/cwv-field-certification.yml@refs/heads/main",
    "cwv.exportOIDC.subject": "repo:example/university-ecosystem:environment:staging",
    "networkPolicy.gatewayJWKS.egressCIDRs[0]": "192.0.2.0/24",
    "cwv.deploymentRunID": 0,
    "cwv.deploymentRunAttempt": 0,
}

REVOCATION_RELEASE = "checkov-revocation"
REVOCATION_OVERRIDES: dict[str, str] = {
    "applicationReleaseName": REVOCATION_RELEASE,
    "redis.fullnameOverride": f"{REVOCATION_RELEASE}-revocation-redis",
    "redis.commonLabels.university-ecosystem\\.io/revocation-store-for": REVOCATION_RELEASE,
    "redis.commonLabels.app\\.kubernetes\\.io/instance": REVOCATION_RELEASE,
}


def _path_tokens(path: str) -> list[str | int]:
    """Decode Helm dotted keys, escaped dots, and list indexes."""
    tokens: list[str | int] = []
    current: list[str] = []
    index = 0
    while index < len(path):
        char = path[index]
        if char == "\\":
            index += 1
            if index >= len(path):
                raise ValueError("Helm path ends with an escape")
            current.append(path[index])
        elif char == ".":
            if current:
                tokens.append("".join(current))
                current = []
            elif not tokens or not isinstance(tokens[-1], int):
                raise ValueError("Helm path has an empty map key")
        elif char == "[":
            if current:
                tokens.append("".join(current))
                current = []
            close = path.find("]", index + 1)
            if close < 0 or not path[index + 1 : close].isdigit():
                raise ValueError("Helm path has an invalid list index")
            tokens.append(int(path[index + 1 : close]))
            index = close
        else:
            current.append(char)
        index += 1
    if current:
        tokens.append("".join(current))
    if not tokens:
        raise ValueError("Helm path is empty")
    return tokens


def _set_path(root: dict[str, Any], path: str, value: Any) -> None:
    tokens = _path_tokens(path)
    current: Any = root
    for position, token in enumerate(tokens):
        is_last = position == len(tokens) - 1
        next_token = None if is_last else tokens[position + 1]
        if isinstance(token, str):
            if not isinstance(current, dict):
                raise ValueError(f"Helm path conflicts at {path!r}")
            if is_last:
                current[token] = value
            else:
                expected_type = list if isinstance(next_token, int) else dict
                child = current.setdefault(token, expected_type())
                if not isinstance(child, expected_type):
                    raise ValueError(f"Helm path conflicts at {path!r}")
                current = child
        else:
            if not isinstance(current, list):
                raise ValueError(f"Helm list index conflicts at {path!r}")
            while len(current) <= token:
                current.append(None)
            if is_last:
                current[token] = value
            else:
                expected_type = list if isinstance(next_token, int) else dict
                if current[token] is None:
                    current[token] = expected_type()
                if not isinstance(current[token], expected_type):
                    raise ValueError(f"Helm list index conflicts at {path!r}")
                current = current[token]


def _read_staging_ingress_arrays(repository_root: Path) -> dict[str, Any]:
    """Copy the staging hosts and TLS arrays before finite host overrides."""
    root = repository_root.resolve()
    source = repository_root / "charts/university-ecosystem/values-staging.yaml"
    resolved = source.resolve()
    if (
        source.is_symlink()
        or not resolved.is_relative_to(root)
        or not resolved.is_file()
    ):
        raise ValueError("staging values file is missing or unsafe")
    try:
        document = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError("cannot safely parse canonical staging values") from error
    if not isinstance(document, dict):
        raise ValueError("canonical staging values must be a mapping")
    ingress = document.get("ingress")
    if not isinstance(ingress, dict):
        raise ValueError("canonical staging values are missing ingress settings")
    hosts = ingress.get("hosts")
    tls = ingress.get("tls")
    if not isinstance(hosts, list) or len(hosts) != 2:
        raise ValueError("staging ingress must define the two finite host entries")
    for host in hosts:
        if (
            not isinstance(host, dict)
            or not isinstance(host.get("host"), str)
            or not host["host"]
            or not isinstance(host.get("paths"), list)
            or not host["paths"]
            or any(
                not isinstance(path, dict)
                or not isinstance(path.get("path"), str)
                or not path["path"]
                or not isinstance(path.get("pathType"), str)
                or not path["pathType"]
                for path in host["paths"]
            )
        ):
            raise ValueError("staging ingress host entries must include complete paths")
    if not isinstance(tls, list) or len(tls) != 1 or not isinstance(tls[0], dict):
        raise ValueError("staging ingress must define the finite TLS entry")
    if (
        not isinstance(tls[0].get("secretName"), str)
        or not tls[0]["secretName"]
        or not isinstance(tls[0].get("hosts"), list)
        or len(tls[0]["hosts"]) != 2
        or any(not isinstance(host, str) or not host for host in tls[0]["hosts"])
    ):
        raise ValueError("staging ingress TLS entry must include its secret and hosts")
    arrays = {"hosts": hosts, "tls": tls}
    try:
        json.dumps(arrays, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("staging ingress arrays are not JSON serializable") from error
    return copy.deepcopy(arrays)


def _profile(
    overrides: dict[str, Any], initial: dict[str, Any] | None = None
) -> dict[str, Any]:
    result = copy.deepcopy(initial) if initial is not None else {}
    for key, value in overrides.items():
        _set_path(result, key, value)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_yaml_digest_paths(
    text: str, source_name: str, requested_paths: dict[str, tuple[str, ...]]
) -> dict[str, str]:
    """Extract a finite set of plain nested YAML digest scalars fail-closed."""
    requested = {tuple(path): name for name, path in requested_paths.items()}
    relevant_prefixes = {
        path[:depth] for path in requested for depth in range(1, len(path) + 1)
    }
    found: dict[tuple[str, ...], str] = {}
    seen: set[tuple[str, ...]] = set()
    stack: list[tuple[int, str]] = []
    mapping_line = re.compile(
        r"^( *)([A-Za-z0-9][A-Za-z0-9_.-]*):(?:[ ]+(.*))?[ ]*$", re.ASCII
    )

    for line_number, line in enumerate(text.splitlines(), start=1):
        indent_text = line[: len(line) - len(line.lstrip(" \t"))]
        if "\t" in indent_text:
            raise ValueError(f"{source_name}:{line_number} has tab-indented YAML")
        stripped = line.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in {"---", "..."}:
            stack.clear()
            continue
        if stripped.startswith("-"):
            continue

        match = mapping_line.fullmatch(line)
        if match is None:
            continue
        indent = len(match.group(1))
        key = match.group(2)
        raw_value = match.group(3)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        current_path = (*tuple(parent for _, parent in stack), key)
        if current_path in relevant_prefixes:
            if current_path in seen:
                raise ValueError(
                    f"{source_name}:{line_number} duplicates a pinned image value path"
                )
            seen.add(current_path)

        if current_path in requested:
            scalar = (
                ""
                if raw_value is None
                else re.split(r"\s+#", raw_value, maxsplit=1)[0].strip()
            )
            if not IMAGE_DIGEST_PATTERN.fullmatch(scalar):
                raise ValueError(
                    f"{source_name}:{line_number} pinned image value is missing or malformed"
                )
            found[current_path] = scalar

        if (
            raw_value is None
            or not raw_value.strip()
            or raw_value.lstrip().startswith("#")
        ):
            stack.append((indent, key))

    missing = set(requested) - set(found)
    if missing:
        labels = ", ".join(requested[path] for path in sorted(missing))
        raise ValueError(f"{source_name} is missing pinned image value paths: {labels}")
    return {requested[path]: value for path, value in found.items()}


def read_pinned_chart_images(repository_root: Path) -> dict[str, str]:
    """Read and cross-check existing digest pins from every chart values source."""
    root = repository_root.resolve()
    pins: dict[str, str] = {}
    for relative_path, requested_paths in PINNED_IMAGE_VALUE_PATHS.items():
        source = repository_root / relative_path
        resolved = source.resolve()
        if (
            source.is_symlink()
            or not resolved.is_relative_to(root)
            or not resolved.is_file()
        ):
            raise ValueError(
                f"pinned chart values file is missing or unsafe: {relative_path}"
            )
        try:
            text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError(
                f"cannot read pinned chart values file: {relative_path}"
            ) from error
        extracted = _extract_yaml_digest_paths(text, relative_path, requested_paths)
        for key, digest in extracted.items():
            previous = pins.setdefault(key, digest)
            if previous != digest:
                raise ValueError(
                    f"committed chart values disagree for pinned image path: {key}"
                )

    if pins.get("nats.image.digest") != pins.get("nats.container.image.digest"):
        raise ValueError(
            "committed NATS chart image aliases do not share the same pinned digest"
        )
    expected = {
        "redis.image.digest",
        "redis.metrics.image.digest",
        "nats.image.digest",
        "nats.container.image.digest",
    }
    if set(pins) != expected:
        raise ValueError(
            "committed chart values did not provide the exact pinned image set"
        )
    return pins


def _verify_chart_roots(repository_root: Path) -> None:
    for expected_name, relative_root in EXPECTED_CHARTS.items():
        chart_root = (repository_root / relative_root).resolve()
        if not chart_root.is_dir() or not chart_root.is_relative_to(
            repository_root.resolve()
        ):
            raise ValueError(
                f"expected chart directory is missing or outside repository: {relative_root}"
            )
        chart_files = sorted(
            path.relative_to(chart_root).as_posix()
            for path in chart_root.rglob("Chart.yaml")
            if path.is_file()
        )
        if chart_files != ["Chart.yaml"]:
            raise ValueError(
                f"{relative_root} must contain exactly one unpacked Chart.yaml root"
            )
        chart_text = (chart_root / "Chart.yaml").read_text(encoding="utf-8")
        name_match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", chart_text)
        if name_match is None or name_match.group(1) != expected_name:
            raise ValueError(f"unexpected chart name at {relative_root}")


def _read_digest_output(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"cannot read resolver output: {path}") from error
    normalized = raw.replace("\r\n", "\n")
    match = DIGEST_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(
            "resolver output is not the exact bounded backend digest document"
        )
    return match.group(1)


def _read_evidence(
    path: Path,
    expected_sha256: str,
    repository: str,
    source_sha: str,
    archive_dir: Path,
) -> dict[str, dict[str, str]]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256, re.ASCII):
        raise ValueError(
            "expected image evidence hash must be 64 lowercase hex characters"
        )
    if path.is_symlink() or not path.is_file():
        raise ValueError("local OCI image evidence must be a regular file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("local OCI image evidence does not match its sealed SHA-256")
    sidecar = Path(f"{path}.sha256")
    try:
        sidecar_text = sidecar.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise ValueError(
            "local OCI image evidence SHA-256 sidecar is missing"
        ) from error
    if sidecar_text != f"{expected_sha256}  {path.name}\n":
        raise ValueError("local OCI image evidence SHA-256 sidecar does not match")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("local OCI image evidence is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "source_sha",
        "repository",
        "images",
    }:
        raise ValueError("local OCI image evidence has an unexpected shape")
    if document["schema"] != "checkov-local-oci-image-evidence/v2":
        raise ValueError("local OCI image evidence schema is not recognized")
    if document["source_sha"] != source_sha or not SOURCE_SHA_PATTERN.fullmatch(
        source_sha
    ):
        raise ValueError(
            "local OCI image evidence is not bound to the current source SHA"
        )
    if document["repository"] != repository or not REPOSITORY_PATTERN.fullmatch(
        repository
    ):
        raise ValueError("local OCI image evidence repository does not match this run")
    image_records = document["images"]
    if not isinstance(image_records, dict) or set(image_records) != set(
        REQUIRED_IMAGES
    ):
        raise ValueError(
            "local OCI image evidence does not contain the exact required image set"
        )

    verified: dict[str, dict[str, str]] = {}
    for image_name in REQUIRED_IMAGES:
        record = image_records[image_name]
        if not isinstance(record, dict) or set(record) != {
            "repository",
            "manifest_digest",
            "archive_sha256",
            "source_label",
            "revision_label",
        }:
            raise ValueError(
                f"local OCI evidence for {image_name} has an unexpected shape"
            )
        expected_repository = f"ghcr.io/{repository}/{image_name}"
        if record["repository"] != expected_repository:
            raise ValueError(f"local OCI evidence repository mismatch for {image_name}")
        if not isinstance(
            record["manifest_digest"], str
        ) or not IMAGE_DIGEST_PATTERN.fullmatch(record["manifest_digest"]):
            raise ValueError(f"invalid manifest digest for {image_name}")
        if not isinstance(record["archive_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", record["archive_sha256"]
        ):
            raise ValueError(f"invalid OCI archive hash for {image_name}")
        archive = archive_dir / f"{image_name}.oci.tar"
        if (
            archive.is_symlink()
            or not archive.is_file()
            or _sha256(archive) != record["archive_sha256"]
        ):
            raise ValueError(f"OCI archive hash mismatch for {image_name}")
        manifest_digest, source_label, revision_label = _verified_image_config_labels(
            archive
        )
        if manifest_digest != record["manifest_digest"]:
            raise ValueError(f"OCI archive manifest digest mismatch for {image_name}")
        if (
            source_label != f"https://github.com/{repository}"
            or revision_label != source_sha
            or record["source_label"] != source_label
            or record["revision_label"] != revision_label
        ):
            raise ValueError(f"OCI source/revision labels mismatch for {image_name}")
        verified[image_name] = {
            "repository": record["repository"],
            "digest": record["manifest_digest"],
        }
    return verified


def _write_profile(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def prepare(
    repository_root: Path,
    backend_values_file: Path,
    evidence_file: Path,
    evidence_sha256: str,
    repository: str,
    source_sha: str,
    run_id: int,
    run_attempt: int,
    archive_dir: Path,
    output_dir: Path,
) -> dict[str, Path]:
    _verify_chart_roots(repository_root)
    pinned_chart_images = read_pinned_chart_images(repository_root)
    images = _read_evidence(
        evidence_file, evidence_sha256, repository, source_sha, archive_dir
    )
    backend_digest = _read_digest_output(backend_values_file)
    if backend_digest != images["backend"]["digest"]:
        raise ValueError(
            "backend resolver output does not match sealed local OCI evidence"
        )
    if run_id <= 0 or run_attempt <= 0:
        raise ValueError("GitHub run ID and attempt must be positive integers")

    staging_ingress = _read_staging_ingress_arrays(repository_root)
    staging = dict(STAGING_OVERRIDES)
    staging.update(pinned_chart_images)
    staging.update(
        {
            "global.imageTag": source_sha,
            "global.backendImageDigest": backend_digest,
            "backend.image.repository": images["backend"]["repository"],
            "backend.image.digest": backend_digest,
            "backend.image.tag": "",
            "frontend.image.repository": images["frontend"]["repository"],
            "frontend.image.digest": images["frontend"]["digest"],
            "gateway.image.repository": images["gateway"]["repository"],
            "gateway.image.digest": images["gateway"]["digest"],
            "wsHub.image.repository": images["ws-hub"]["repository"],
            "wsHub.image.digest": images["ws-hub"]["digest"],
            "fileProcessor.image.repository": images["file-processor"]["repository"],
            "fileProcessor.image.digest": images["file-processor"]["digest"],
            "outboxWorker.image.repository": images["backend"]["repository"],
            "outboxWorker.image.digest": backend_digest,
            "redis.metrics.passwordFileInitImage.repository": images["backend"][
                "repository"
            ],
            "redis.metrics.passwordFileInitImage.digest": backend_digest,
            "redis.metrics.passwordFileInitImage.tag": "",
            "cwv.releaseSHA": source_sha,
            "cwv.frontendImageDigest": images["frontend"]["digest"],
            "cwv.deploymentRunID": run_id,
            "cwv.deploymentRunAttempt": run_attempt,
        }
    )
    revocation = {
        **REVOCATION_OVERRIDES,
        "redis.image.digest": pinned_chart_images["redis.image.digest"],
        "redis.metrics.image.digest": pinned_chart_images["redis.metrics.image.digest"],
        "global.backendImageRepository": images["backend"]["repository"],
        "global.backendImageDigest": backend_digest,
        "redis.metrics.passwordFileInitImage.repository": images["backend"][
            "repository"
        ],
        "redis.metrics.passwordFileInitImage.digest": backend_digest,
        "redis.metrics.passwordFileInitImage.tag": "",
        "redis.metrics.passwordFileInitImage.pullPolicy": "Always",
    }
    redis_compat = {"global.backendImageDigest": backend_digest}
    profiles = {
        "university-ecosystem.json": _profile(staging, {"ingress": staging_ingress}),
        "revocation-store.json": _profile(revocation),
        "redis-compat.json": _profile(redis_compat),
    }
    paths: dict[str, Path] = {}
    for filename, value in profiles.items():
        path = output_dir / filename
        _write_profile(path, value)
        paths[filename] = path
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--backend-values-file", type=Path, required=True)
    parser.add_argument("--image-evidence-file", type=Path, required=True)
    parser.add_argument("--image-evidence-sha256", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = prepare(
            args.repository_root,
            args.backend_values_file,
            args.image_evidence_file,
            args.image_evidence_sha256,
            args.repository,
            args.source_sha,
            args.run_id,
            args.run_attempt,
            args.archive_dir,
            args.output_dir,
        )
    except (OSError, UnicodeError, ValueError, KeyError) as error:
        print(
            f"error: Checkov Helm context generation failed: {error}", file=sys.stderr
        )
        return 2
    for path in paths.values():
        print(f"Wrote bounded Checkov Helm context: {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
