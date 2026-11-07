"""Build the deterministic, stage-snapshot-only Helm Semgrep target overlay."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

BoundedRunner = Callable[[Sequence[str], Path, float, int, int], "BoundedProcessResult"]
REGISTRY_RELATIVE = "scripts/quality/helm_semgrep_profile_registry.json"
SOURCE_HEADER = re.compile(r"(?m)^# Source:\s*(.+?)\s*$")
DOC_SEPARATOR = re.compile(r"(?m)^---[ \t]*\r?\n")
HELM_STDOUT_LIMIT = 8 * 1024 * 1024
HELM_STDERR_LIMIT = 256 * 1024
HELM_TIMEOUT_SECONDS = 60
MAX_HELM_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_HELM_BINARY_BYTES = 128 * 1024 * 1024
MAX_TOTAL_RENDERED_VIEW_BYTES = 32 * 1024 * 1024
EXPECTED_PROFILE_REGISTRY_SHA256 = (
    "6536cc971f493f737ef49fad637351b7857c11fff932b313fac2fb87bdb95345"
)
EXPECTED_ROOTS = frozenset(
    {
        "charts/redis-compat/templates",
        "charts/revocation-store/templates",
        "charts/university-ecosystem/templates",
    }
)
PROFILE_NAMES = (
    "university-development",
    "university-staging",
    "university-production",
    "university-feature-enabled-development",
    "revocation-store-development",
    "revocation-store-staging",
    "revocation-store-production",
    "gateway-api-isolated-synthetic-apis",
)
EXPECTED_GUARD_PATHS = frozenset(
    {
        "charts/revocation-store/templates/deployment-contract.yaml",
        "charts/revocation-store/templates/validate-config.yaml",
        "charts/university-ecosystem/templates/deployment-contract.yaml",
        "charts/university-ecosystem/templates/validate-config.yaml",
    }
)
EXPECTED_REQUIRED_COVERAGE = {
    "charts/university-ecosystem/templates/backup-cronjob.yaml": [
        "university-feature-enabled-development"
    ],
    "charts/university-ecosystem/templates/gateway-api.yaml": [
        "gateway-api-isolated-synthetic-apis"
    ],
    "charts/university-ecosystem/templates/keda-scaledobjects.yaml": [
        "university-feature-enabled-development"
    ],
    "charts/university-ecosystem/templates/keda-trigger-auth.yaml": [
        "university-feature-enabled-development"
    ],
    "charts/university-ecosystem/templates/secrets.yaml": ["university-development"],
}


class HelmOverlayError(RuntimeError):
    """The chart source, profile matrix, render, or provenance is incomplete."""


_VERIFIED_TOOL_MARKER = object()


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


@dataclass(frozen=True)
class BoundedProcessResult:
    """Process result whose captured streams are hard-capped by the runner."""

    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    output_limit_exceeded: bool = False


@dataclass(frozen=True)
class VerifiedHelmTool:
    """Helm executable extracted from the checksum-pinned official archive."""

    executable: Path
    extraction_root: Path
    archive_path: Path
    archive_sha256: str
    binary_sha256: str
    version: str
    platform_key: str
    _verification_marker: object


def bounded_process_runner(
    argv: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
    stdout_limit_bytes: int,
    stderr_limit_bytes: int,
) -> BoundedProcessResult:
    """Run Helm without unbounded capture and kill it on timeout or output overflow."""
    if not argv or any(not isinstance(part, str) for part in argv):
        raise HelmOverlayError("Helm command arguments are malformed")
    if timeout_seconds <= 0 or stdout_limit_bytes <= 0 or stderr_limit_bytes <= 0:
        raise HelmOverlayError("Helm process limits must be positive")
    return asyncio.run(
        _bounded_process_async(
            argv, cwd, timeout_seconds, stdout_limit_bytes, stderr_limit_bytes
        )
    )


async def _bounded_process_async(
    argv: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
    stdout_limit_bytes: int,
    stderr_limit_bytes: int,
) -> BoundedProcessResult:
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=(os.name != "nt"),
            creationflags=(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                if os.name == "nt"
                else 0
            ),
        )
    except OSError as exc:
        raise HelmOverlayError("cannot start pinned Helm executable") from exc
    if process.stdout is None or process.stderr is None:
        process.kill()
        await process.wait()
        raise HelmOverlayError("could not create bounded Helm output pipes")

    overflow = asyncio.Event()

    async def drain(stream: asyncio.StreamReader, limit: int) -> bytes:
        captured = bytearray()
        while True:
            chunk = await stream.read(64 * 1024)
            if not chunk:
                return bytes(captured)
            room = limit - len(captured)
            if room > 0:
                captured.extend(chunk[:room])
            if len(chunk) > room:
                overflow.set()

    stdout_task = asyncio.create_task(drain(process.stdout, stdout_limit_bytes))
    stderr_task = asyncio.create_task(drain(process.stderr, stderr_limit_bytes))
    wait_task = asyncio.create_task(process.wait())
    overflow_task = asyncio.create_task(overflow.wait())
    done, _pending = await asyncio.wait(
        {wait_task, overflow_task},
        timeout=timeout_seconds,
        return_when=asyncio.FIRST_COMPLETED,
    )
    timed_out = not done
    limit_exceeded = overflow_task in done and overflow.is_set()
    if timed_out or limit_exceeded:
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
    returncode = await wait_task
    overflow_task.cancel()
    try:
        stdout, stderr = await asyncio.wait_for(
            asyncio.gather(stdout_task, stderr_task), timeout=2.0
        )
    except TimeoutError as exc:
        process.kill()
        raise HelmOverlayError("could not drain bounded Helm output") from exc
    return BoundedProcessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        output_limit_exceeded=limit_exceeded or overflow.is_set(),
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise HelmOverlayError("empty or invalid staged path")
    text = value
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != text:
        raise HelmOverlayError(f"non-canonical staged path: {value!r}")
    return text


def _manifest_map(
    root: Path, manifest: Sequence[Mapping[str, str]]
) -> tuple[dict[str, dict[str, str]], str]:
    records: dict[str, dict[str, str]] = {}
    for row in manifest:
        path = _relative(row.get("path"))
        if path in records or set(row) != {"path", "mode", "oid", "stage", "sha256"}:
            raise HelmOverlayError("duplicate or malformed stage-zero manifest row")
        if row["stage"] != "0" or row["mode"] not in {"100644", "100755"}:
            raise HelmOverlayError(f"unsupported staged entry: {path}")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", row["oid"]):
            raise HelmOverlayError(f"malformed Git blob id: {path}")
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise HelmOverlayError(f"malformed staged SHA-256: {path}")
        records[path] = dict(row)
    payload = (
        json.dumps(
            {"targets": list(manifest)}, indent=2, sort_keys=True, ensure_ascii=False
        )
        + "\n"
    ).encode("utf-8")
    digest = _sha(payload)
    chart_paths = {path for path in records if path.startswith("charts/")}
    charts = root / "charts"
    if _is_link(charts) or not charts.is_dir():
        raise HelmOverlayError("stage snapshot has no regular charts directory")
    actual: set[str] = set()
    for path in charts.rglob("*"):
        if _is_link(path):
            raise HelmOverlayError("stage snapshot chart tree contains a link")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != chart_paths:
        raise HelmOverlayError(
            "stage snapshot chart tree differs from its Git index manifest"
        )
    for relative, row in records.items():
        if not relative.startswith("charts/"):
            continue
        path = root / PurePosixPath(relative)
        if not path.is_file() or _is_link(path) or _sha_file(path) != row["sha256"]:
            raise HelmOverlayError(f"staged chart input hash mismatch: {relative}")
    return records, digest


def _registry(
    root: Path, records: Mapping[str, Mapping[str, str]]
) -> tuple[dict[str, Any], str]:
    row = records.get(REGISTRY_RELATIVE)
    path = root / PurePosixPath(REGISTRY_RELATIVE)
    if (
        row is None
        or not path.is_file()
        or _is_link(path)
        or _sha_file(path) != row["sha256"]
    ):
        raise HelmOverlayError(
            "profile registry is missing or differs from stage-zero bytes"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HelmOverlayError("profile registry is invalid") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise HelmOverlayError("unsupported profile registry schema")
    if row["sha256"] != EXPECTED_PROFILE_REGISTRY_SHA256:
        raise HelmOverlayError(
            "profile registry drifted from the frozen reviewed matrix"
        )
    if (
        value.get("helm_version") != "v4.2.4"
        or value.get("dependency_updates") is not False
    ):
        raise HelmOverlayError("Helm version or offline dependency policy differs")
    if set(value.get("chart_template_roots", [])) != EXPECTED_ROOTS:
        raise HelmOverlayError("chart template roots differ from the reviewed set")
    if value.get("max_render_seconds") != HELM_TIMEOUT_SECONDS:
        raise HelmOverlayError(
            "profile registry process timeout differs from the fixed cap"
        )
    return value, row["sha256"]


def _platform_key() -> str:
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64", "x64"}:
        raise HelmOverlayError(f"unsupported Helm host architecture: {machine}")
    if sys.platform.startswith("linux"):
        return "linux-amd64"
    if sys.platform == "win32":
        return "windows-amd64"
    raise HelmOverlayError(f"unsupported Helm host platform: {sys.platform}")


def helm_archive_pin(
    source_snapshot_root: Path,
    source_manifest: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    """Return the exact host archive pin only after stage and registry validation."""
    root_input = Path(source_snapshot_root)
    if _is_link(root_input):
        raise HelmOverlayError("stage snapshot root may not be linked")
    root = root_input.resolve(strict=True)
    records, _manifest_sha = _manifest_map(root, source_manifest)
    registry, _registry_sha = _registry(root, records)
    platform_key = _platform_key()
    matches = [
        item
        for item in registry.get("helm_toolchains", [])
        if isinstance(item, dict) and item.get("platform_key") == platform_key
    ]
    if len(matches) != 1:
        raise HelmOverlayError(
            "no unique official Helm archive pin exists for this host"
        )
    pin = dict(matches[0])
    if pin.get("version") != registry["helm_version"]:
        raise HelmOverlayError(
            "official Helm archive version differs from the reviewed pin"
        )
    return pin


def verify_helm_archive(
    source_snapshot_root: Path,
    source_manifest: Sequence[Mapping[str, str]],
    archive_path: Path,
    extraction_root: Path,
) -> VerifiedHelmTool:
    """Verify and extract the platform's official, pinned Helm archive."""
    root_input = Path(source_snapshot_root)
    if _is_link(root_input):
        raise HelmOverlayError("stage snapshot root may not be linked")
    root = root_input.resolve(strict=True)
    records, _manifest_sha = _manifest_map(root, source_manifest)
    registry, _registry_sha = _registry(root, records)
    platform_key = _platform_key()
    pins = registry.get("helm_toolchains")
    if not isinstance(pins, list):
        raise HelmOverlayError("pinned Helm archive registry is missing")
    matches = [
        item
        for item in pins
        if isinstance(item, dict) and item.get("platform_key") == platform_key
    ]
    if len(matches) != 1:
        raise HelmOverlayError(
            "no unique official Helm archive pin exists for this host"
        )
    pin = matches[0]
    required = {
        "platform_key",
        "version",
        "archive_url",
        "archive_sha256",
        "archive_type",
        "archive_member",
        "executable_name",
    }
    if set(pin) != required or pin.get("version") != registry["helm_version"]:
        raise HelmOverlayError("official Helm archive pin is malformed")
    url = pin["archive_url"]
    if not isinstance(url, str) or not url.startswith(
        "https://get.helm.sh/helm-v4.2.4-"
    ):
        raise HelmOverlayError("Helm archive URL is outside the official release host")
    expected_archive_sha = pin["archive_sha256"]
    if not isinstance(expected_archive_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_archive_sha
    ):
        raise HelmOverlayError("Helm archive SHA-256 pin is malformed")
    archive_input = Path(archive_path)
    if _is_link(archive_input):
        raise HelmOverlayError("Helm archive may not be linked")
    archive = archive_input.resolve(strict=True)
    if archive.is_relative_to(root) or not archive.is_file():
        raise HelmOverlayError(
            "Helm archive must be a regular file outside the stage snapshot"
        )
    if archive.stat().st_size > MAX_HELM_ARCHIVE_BYTES:
        raise HelmOverlayError(
            "Helm archive does not match the reviewed official checksum"
        )
    try:
        with archive.open("rb") as stream:
            archive_data = stream.read(MAX_HELM_ARCHIVE_BYTES + 1)
    except OSError as exc:
        raise HelmOverlayError("Helm archive cannot be read") from exc
    if (
        len(archive_data) > MAX_HELM_ARCHIVE_BYTES
        or _sha(archive_data) != expected_archive_sha
    ):
        raise HelmOverlayError(
            "Helm archive does not match the reviewed official checksum"
        )
    extraction_input = Path(extraction_root)
    if extraction_input.exists() or _is_link(extraction_input):
        raise HelmOverlayError("Helm extraction root must be a new private path")
    extraction_input.parent.mkdir(parents=True, exist_ok=True)
    extraction_input.mkdir()
    extraction = extraction_input.resolve(strict=True)
    if extraction.is_relative_to(root):
        shutil.rmtree(extraction)
        raise HelmOverlayError(
            "Helm executable must be extracted outside the source snapshot"
        )
    member_name = pin["archive_member"]
    if not isinstance(member_name, str) or _relative(member_name) != member_name:
        shutil.rmtree(extraction)
        raise HelmOverlayError("Helm archive member is not a canonical relative path")
    try:
        if pin["archive_type"] == "tar.gz":
            with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as package:
                candidates = [
                    item for item in package.getmembers() if item.name == member_name
                ]
                if (
                    len(candidates) != 1
                    or not candidates[0].isfile()
                    or candidates[0].size > MAX_HELM_BINARY_BYTES
                ):
                    raise HelmOverlayError(
                        "Helm archive does not contain one bounded regular executable"
                    )
                stream = package.extractfile(candidates[0])
                if stream is None:
                    raise HelmOverlayError("Helm archive executable cannot be read")
                data = stream.read(MAX_HELM_BINARY_BYTES + 1)
        elif pin["archive_type"] == "zip":
            with zipfile.ZipFile(io.BytesIO(archive_data)) as package:
                candidates = [
                    item for item in package.infolist() if item.filename == member_name
                ]
                if len(candidates) != 1:
                    raise HelmOverlayError(
                        "Helm archive does not contain one executable member"
                    )
                item = candidates[0]
                unix_mode = item.external_attr >> 16
                if (
                    item.is_dir()
                    or (unix_mode and (unix_mode & 0o170000) == 0o120000)
                    or item.file_size > MAX_HELM_BINARY_BYTES
                ):
                    raise HelmOverlayError(
                        "Helm archive executable is not a bounded regular file"
                    )
                with package.open(item) as stream:
                    data = stream.read(MAX_HELM_BINARY_BYTES + 1)
        else:
            raise HelmOverlayError("unsupported Helm archive type")
    except HelmOverlayError:
        shutil.rmtree(extraction, ignore_errors=True)
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        shutil.rmtree(extraction, ignore_errors=True)
        raise HelmOverlayError("Helm archive is invalid") from exc
    if not data or len(data) > MAX_HELM_BINARY_BYTES:
        shutil.rmtree(extraction)
        raise HelmOverlayError("Helm executable is empty or exceeds its size cap")
    executable_name = pin["executable_name"]
    if (
        not isinstance(executable_name, str)
        or Path(executable_name).name != executable_name
    ):
        shutil.rmtree(extraction)
        raise HelmOverlayError("Helm executable name is malformed")
    executable = extraction / executable_name
    try:
        with executable.open("xb") as stream:
            stream.write(data)
        if os.name != "nt":
            executable.chmod(0o755)
        resolved_executable = executable.resolve(strict=True)
    except OSError as exc:
        shutil.rmtree(extraction, ignore_errors=True)
        raise HelmOverlayError(
            "verified Helm executable cannot be materialized"
        ) from exc
    if resolved_executable.parent != extraction or _is_link(executable):
        shutil.rmtree(extraction)
        raise HelmOverlayError("extracted Helm executable escaped its private root")
    return VerifiedHelmTool(
        executable=resolved_executable,
        extraction_root=extraction,
        archive_path=archive,
        archive_sha256=expected_archive_sha,
        binary_sha256=_sha(data),
        version=pin["version"],
        platform_key=platform_key,
        _verification_marker=_VERIFIED_TOOL_MARKER,
    )


def _verify_helm_tool(
    tool: VerifiedHelmTool,
    source_root: Path,
    registry: Mapping[str, Any],
) -> None:
    if (
        not isinstance(tool, VerifiedHelmTool)
        or tool._verification_marker is not _VERIFIED_TOOL_MARKER
    ):
        raise HelmOverlayError("Helm tool was not produced by archive verification")
    matches = [
        item
        for item in registry.get("helm_toolchains", [])
        if isinstance(item, dict) and item.get("platform_key") == tool.platform_key
    ]
    if len(matches) != 1:
        raise HelmOverlayError("verified Helm tool has no unique staged archive pin")
    pin = matches[0]
    try:
        extraction = tool.extraction_root.resolve(strict=True)
        executable = tool.executable.resolve(strict=True)
        archive = tool.archive_path.resolve(strict=True)
    except OSError as exc:
        raise HelmOverlayError("verified Helm tool path disappeared") from exc
    if (
        tool.platform_key != _platform_key()
        or _is_link(tool.executable)
        or _is_link(tool.extraction_root)
        or _is_link(tool.archive_path)
        or archive != tool.archive_path
        or extraction.is_relative_to(source_root)
        or not executable.is_relative_to(extraction)
        or executable != tool.executable
        or _is_link(executable)
        or archive.is_relative_to(source_root)
        or not archive.is_file()
        or not executable.is_file()
    ):
        raise HelmOverlayError("verified Helm tool escaped its private source boundary")
    if (
        tool.version != pin["version"]
        or tool.archive_sha256 != pin["archive_sha256"]
        or _sha_file(archive) != pin["archive_sha256"]
        or _sha_file(executable) != tool.binary_sha256
        or tool.archive_sha256 != pin["archive_sha256"]
    ):
        raise HelmOverlayError("verified Helm archive or executable changed")


def _roles(registry: Mapping[str, Any]) -> tuple[dict[str, str], set[str]]:
    rows = registry.get("source_roles")
    if not isinstance(rows, list) or not rows:
        raise HelmOverlayError("source role inventory is empty")
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "role"}:
            raise HelmOverlayError("malformed source role row")
        path = _relative(row["path"])
        if path in result or row["role"] not in {"resource", "guard-only"}:
            raise HelmOverlayError(f"invalid source role: {path}")
        result[path] = row["role"]
    guards = set(registry.get("guard_only_paths", []))
    if (
        guards != EXPECTED_GUARD_PATHS
        or guards != {path for path, role in result.items() if role == "guard-only"}
        or len(result) != 40
        or sum(role == "resource" for role in result.values()) != 36
    ):
        raise HelmOverlayError("guard paths and source roles disagree")
    return result, guards


def _discover_templates(
    records: Mapping[str, Mapping[str, str]], registry: Mapping[str, Any]
) -> set[str]:
    roots = registry["chart_template_roots"]
    found: set[str] = set()
    for path in records:
        if not path.startswith("charts/") or "/templates/" not in path:
            continue
        if PurePosixPath(path).suffix.lower() not in {".yaml", ".yml"}:
            continue
        if not any(path.startswith(root + "/") for root in roots):
            raise HelmOverlayError(f"unreviewed Helm template root: {path}")
        found.add(path)
    declared = {row["path"] for row in registry["source_roles"]}
    if found != declared:
        raise HelmOverlayError(
            f"template inventory drift; added={sorted(found - declared)}; missing={sorted(declared - found)}"
        )
    return found


def _staging_args() -> list[str]:
    digest = "sha256:" + "a" * 64
    values = {
        "global.imageTag": "9d08136558b95d1182f889574f67b1b1d21abc9f",
        "global.jwtIssuer": "https://api.university.staging.example.org",
        "backend.image.repository": "ghcr.io/example/university/backend",
        "backend.image.digest": digest,
        "frontend.image.repository": "ghcr.io/example/university/frontend",
        "frontend.image.digest": digest,
        "gateway.image.repository": "ghcr.io/example/university/gateway",
        "gateway.image.digest": digest,
        "wsHub.image.repository": "ghcr.io/example/university/ws-hub",
        "wsHub.image.digest": digest,
        "fileProcessor.image.repository": "ghcr.io/example/university/file-processor",
        "fileProcessor.image.digest": digest,
        "outboxWorker.image.repository": "ghcr.io/example/university/backend",
        "outboxWorker.image.digest": digest,
        "redis.image.digest": digest,
        "redis.metrics.image.digest": digest,
        "global.backendImageDigest": digest,
        "redis.metrics.passwordFileInitImage.repository": "ghcr.io/example/university/backend",
        "redis.metrics.passwordFileInitImage.digest": digest,
        "nats.image.digest": digest,
        "nats.container.image.digest": digest,
        "backend.config.elasticsearchURL": "https://elasticsearch.staging.internal",
        "backend.config.flagdHost": "flagd.staging.internal",
        "backend.config.storageS3EndpointURL": "https://minio.staging.internal:443",
        "backend.config.mfaTotpActiveEncryptionKeyId": "totp-active-staging-contract",
        "gateway.config.otelEndpoint": "otel-collector.staging.internal:4317",
        "fileProcessor.config.minioEndpoint": "minio.staging.internal:443",
        "fileProcessor.config.temporalHost": "temporal.staging.internal:7233",
        "fileProcessor.config.otlpEndpoint": "otel-collector.staging.internal:4317",
        "ingress.hosts[0].host": "university.staging.example.org",
        "ingress.hosts[1].host": "api.university.staging.example.org",
        "ingress.tls[0].hosts[0]": "university.staging.example.org",
        "ingress.tls[0].hosts[1]": "api.university.staging.example.org",
        "wsHub.config.allowedOrigins[0]": "https://university.staging.example.org",
        "wsHub.config.otelEndpoint": "otel-collector.staging.internal:4317",
        "cwv.releaseSHA": "9d08136558b95d1182f889574f67b1b1d21abc9f",
        "cwv.frontendImageDigest": digest,
        "cwv.deploymentURL": "https://university.staging.example.org",
        "cwv.deployedAt": "2026-08-26T00:00:00Z",
        "cwv.allowedOrigins[0]": "https://university.staging.example.org",
        "cwv.exportOIDC.repository": "example/university-ecosystem",
        "cwv.exportOIDC.workflowRef": "example/university-ecosystem/.github/workflows/cwv-field-certification.yml@refs/heads/main",
        "cwv.exportOIDC.subject": "repo:example/university-ecosystem:environment:staging",
    }
    values["redis.metrics.passwordFileInitImage.tag"] = values["global.imageTag"]
    args: list[str] = []
    for key, value in values.items():
        args.extend(("--set-string", f"{key}={value}"))
    for key, peers in (
        ("gateway.config.trustedProxies", ["192.0.2.11/32", "2001:db8::11"]),
        ("wsHub.config.trustedProxies", ["198.51.100.12/32", "2001:db8::12"]),
        ("backend.config.trustedProxies", ["192.0.2.13/32", "2001:db8::13"]),
    ):
        args.extend(("--set-json", f"{key}={json.dumps(peers, separators=(',', ':'))}"))
    for key in (
        "networkPolicy.gatewayJWKS.egressCIDRs",
        "networkPolicy.fileProcessorHTTPSEgress.egressCIDRs",
        "networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs",
    ):
        args.extend(("--set-json", f"{key}={json.dumps(['192.0.2.0/24'])}"))
    args.extend(
        ("--set", "cwv.deploymentRunID=123", "--set", "cwv.deploymentRunAttempt=1")
    )
    return args


_DEV_OVERRIDES = [
    value
    for pair in (
        ("--set", "global.imageTag=contract-sha"),
        ("--set", "gateway.config.jwtSecret=ci-placeholder"),
        ("--set", "backend.config.jwtPrivateKeyPEM=ci-placeholder"),
        ("--set", "backend.config.internalHMACSecret=ci-placeholder"),
        ("--set", "backend.config.wsHubInternalSecret=ci-placeholder"),
        ("--set", "backend.config.csrfHMACSecret=ci-placeholder"),
        ("--set", "backend.config.spotifyTokenSecret=ci-placeholder"),
        ("--set", "backend.config.elasticsearchPassword=ci-placeholder"),
        ("--set", "backend.config.spicedbPresharedKey=ci-placeholder"),
        ("--set", "backend.config.auditLogSecret=ci-placeholder"),
        ("--set", "backend.config.tokenHMACSecret=ci-placeholder"),
        ("--set", "backend.config.idempotencyHMACSecret=ci-placeholder"),
        (
            "--set-string",
            "backend.config.mfaTotpEncryptionKeys=test-key:ci-placeholder",
        ),
        ("--set-string", "backend.config.mfaTotpActiveEncryptionKeyId=test-key"),
        ("--set-string", "backend.config.mfaEmailOtpHMACKeys=test-key:ci-placeholder"),
        ("--set-string", "backend.config.mfaEmailOtpActiveHMACKeyId=test-key"),
        ("--set-string", "backend.config.mfaEmailDeliveryKEKs=test-key:ci-placeholder"),
        ("--set-string", "backend.config.mfaEmailDeliveryActiveKEKId=test-key"),
        (
            "--set-string",
            "backend.config.mfaTrustedDeviceHMACKeys=test-key:ci-placeholder",
        ),
        ("--set-string", "backend.config.mfaTrustedDeviceActiveHMACKeyId=test-key"),
        ("--set", "fileProcessor.config.rsaPublicKeyPEM=ci-placeholder"),
        ("--set", "fileProcessor.config.minioAccessKey=ci-placeholder"),
        ("--set", "fileProcessor.config.minioSecretKey=ci-placeholder"),
        ("--set", "fileProcessor.config.temporalAPIKey=ci-placeholder"),
    )
    for value in pair
]
API_VERSIONS = (
    "gateway.networking.k8s.io/v1/Gateway",
    "gateway.networking.k8s.io/v1/HTTPRoute",
    "gateway.envoyproxy.io/v1alpha1/ClientTrafficPolicy",
    "gateway.envoyproxy.io/v1alpha1/BackendTrafficPolicy",
    "cert-manager.io/v1/Certificate",
)


def _revocation_args(release: str) -> list[str]:
    digest = "sha256:" + "b" * 64
    backend = "sha256:38d6b346ff695004f8445e2ec92cfb0d80c044a1a0c776ca71a5b24e078c70f2"
    values = {
        "applicationReleaseName": release,
        "redis.fullnameOverride": f"{release}-revocation-redis",
        r"redis.commonLabels.university-ecosystem\.io/revocation-store-for": release,
        r"redis.commonLabels.app\.kubernetes\.io/instance": release,
        "redis.auth.existingSecret": "revocation-redis-credentials",
        "redis.auth.existingSecretPasswordKey": "revocation-redis-password",
        "redis.image.digest": digest,
        "redis.metrics.image.digest": digest,
        "global.backendImageRepository": "ghcr.io/egorribun/university_ecosystem/backend",
        "global.backendImageDigest": backend,
        "redis.metrics.passwordFileInitImage.repository": "ghcr.io/egorribun/university_ecosystem/backend",
        "redis.metrics.passwordFileInitImage.digest": backend,
        "redis.metrics.passwordFileInitImage.pullPolicy": "Always",
    }
    args: list[str] = []
    for key, value in values.items():
        args.extend(("--set-string", f"{key}={value}"))
    return args


def _commands(root: Path, helm: str) -> list[dict[str, Any]]:
    app = root / "charts/university-ecosystem"
    store = root / "charts/revocation-store"
    namespace = "university-ecosystem"
    base_values = app / "values.yaml"
    stage_values = app / "values-staging.yaml"
    store_values = store / "values.yaml"
    store_stage = store / "values-staging.yaml"
    dev = [
        helm,
        "template",
        "development-contract",
        str(app),
        "--dependency-update=false",
        "--namespace",
        namespace,
        "--values",
        str(base_values),
        "--set-string",
        "global.environment=development",
        *_DEV_OVERRIDES,
    ]
    stage = [
        helm,
        "template",
        "staging-contract",
        str(app),
        "--dependency-update=false",
        "--namespace",
        namespace,
        "--values",
        str(stage_values),
        *_staging_args(),
    ]
    production = [
        helm,
        "template",
        "production-contract",
        str(app),
        "--dependency-update=false",
        "--namespace",
        namespace,
        "--values",
        str(stage_values),
        *_staging_args(),
        "--set-string",
        "global.environment=production",
        "--set-string",
        "ingress.issuer.kind=ClusterIssuer",
        "--set-string",
        "ingress.issuer.name=letsencrypt-prod",
        "--set",
        "internalHttpMTLS.enabled=true",
    ]
    feature = [
        helm,
        "template",
        "feature-contract",
        str(app),
        "--dependency-update=false",
        "--namespace",
        namespace,
        "--values",
        str(base_values),
        "--set-string",
        "global.environment=development",
        *_DEV_OVERRIDES,
        "--set",
        "keda.enabled=true",
        "--set",
        "hibernation.enabled=true",
        "--set",
        "backup.enabled=true",
    ]
    profiles = [
        {
            "name": "university-development",
            "command": dev,
            "profile_kind": "development-contract-fixture; not-deployment-evidence",
            "chart_root": "charts/university-ecosystem",
            "environment": "development",
            "deployment_profile": True,
            "deployment_evidence": False,
            "synthetic_overrides": [
                "CI placeholder credentials and contract image digests"
            ],
            "view_path": "charts/rendered-profiles/university-development.yaml",
            "values_sources": ["charts/university-ecosystem/values.yaml"],
            "api_versions": [],
        },
        {
            "name": "university-staging",
            "command": stage,
            "profile_kind": "staging-context-fixture; synthetic-external-egress-CIDRs; not-deployment-evidence",
            "chart_root": "charts/university-ecosystem",
            "environment": "staging",
            "deployment_profile": True,
            "deployment_evidence": False,
            "synthetic_overrides": [
                "CI placeholder credentials and contract image digests",
                "documentation-only 192.0.2.0/24 CIDRs for external HTTPS egress contract rendering",
            ],
            "view_path": "charts/rendered-profiles/university-staging.yaml",
            "values_sources": [
                "charts/university-ecosystem/values.yaml",
                "charts/university-ecosystem/values-staging.yaml",
            ],
            "api_versions": [],
        },
        {
            "name": "university-production",
            "command": production,
            "profile_kind": "production-context-fixture; staging-values-test-issuer-mTLS-and-synthetic-CIDRs; not-deployment-evidence",
            "chart_root": "charts/university-ecosystem",
            "environment": "production",
            "deployment_profile": True,
            "deployment_evidence": False,
            "synthetic_overrides": [
                "staging values with synthetic example.org issuer and host overrides",
                "test ClusterIssuer name and internal HTTP mTLS fixture",
                "documentation-only 192.0.2.0/24 CIDRs for external HTTPS egress contract rendering",
            ],
            "view_path": "charts/rendered-profiles/university-production.yaml",
            "values_sources": [
                "charts/university-ecosystem/values.yaml",
                "charts/university-ecosystem/values-staging.yaml",
            ],
            "api_versions": [],
        },
        {
            "name": "university-feature-enabled-development",
            "command": feature,
            "profile_kind": "feature-enabled-development-ci-fixture; not-deployment-evidence",
            "chart_root": "charts/university-ecosystem",
            "environment": "development",
            "deployment_profile": False,
            "deployment_evidence": False,
            "synthetic_overrides": [
                "CI placeholder credentials and contract image digests",
                "backup, KEDA, and hibernation features enabled for source coverage",
            ],
            "view_path": "charts/rendered-profiles/university-feature-enabled-development.yaml",
            "values_sources": ["charts/university-ecosystem/values.yaml"],
            "api_versions": [],
        },
    ]
    for env, values_path in (
        ("development", store_values),
        ("staging", store_stage),
        ("production", store_stage),
    ):
        release = f"{env}-contract"
        cmd = [
            helm,
            "template",
            release,
            str(store),
            "--dependency-update=false",
            "--namespace",
            namespace,
            "--values",
            str(values_path),
            *_revocation_args(release),
        ]
        profiles.append(
            {
                "name": f"revocation-store-{env}",
                "command": cmd,
                "profile_kind": {
                    "development": "development-contract-fixture; not-deployment-evidence",
                    "staging": "staging-context-fixture; not-deployment-evidence",
                    "production": "production-context-fixture-using-staging-values; not-deployment-evidence",
                }[env],
                "chart_root": "charts/revocation-store",
                "environment": env,
                "deployment_profile": True,
                "deployment_evidence": False,
                "synthetic_overrides": [
                    "staging values with synthetic Redis and backend image digests"
                    if env == "production"
                    else "synthetic Redis and backend image digests"
                ],
                "view_path": f"charts/rendered-profiles/revocation-store-{env}.yaml",
                "values_sources": [values_path.relative_to(root).as_posix()],
                "api_versions": [],
            }
        )
    return profiles


def _gateway_command(helm: str, chart: Path) -> list[str]:
    command = [
        helm,
        "template",
        "gateway-contract",
        str(chart),
        "--dependency-update=false",
        "--namespace",
        "university-ecosystem",
        "--set-string",
        "applicationSecrets.existingSecret=render-contract-existing-secret",
        "--set-string",
        "global.environment=development",
        "--set",
        "gatewayApi.enabled=true",
        "--set",
        "ingress.enabled=false",
        "--set-json",
        'gatewayApi.clientIPDetection={"directSourceIP":{}}',
        "--set-string",
        r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
        "--set-string",
        r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
    ]
    for version in API_VERSIONS:
        command.extend(("--api-versions", version))
    return command


def _source_for_header(header: str) -> tuple[str | None, str | None]:
    if header.startswith("university-ecosystem/templates/"):
        return "charts/university-ecosystem/templates/" + header.removeprefix(
            "university-ecosystem/templates/"
        ), None
    for prefix in (
        "university-ecosystem/charts/redis/templates/",
        "university-ecosystem/charts/redis-compat/templates/",
    ):
        if header.startswith(prefix):
            return "charts/redis-compat/templates/" + header.removeprefix(prefix), None
    if header.startswith("university-ecosystem/charts/nats/templates/"):
        return None, "charts/university-ecosystem/charts/nats-2.15.0.tgz"
    if header.startswith("revocation-store/templates/"):
        return "charts/revocation-store/templates/" + header.removeprefix(
            "revocation-store/templates/"
        ), None
    if header.startswith("revocation-store/"):
        return "charts/revocation-store/" + header.removeprefix(
            "revocation-store/"
        ), None
    if header.startswith("university-ecosystem/"):
        return "charts/university-ecosystem/" + header.removeprefix(
            "university-ecosystem/"
        ), None
    raise HelmOverlayError("Helm emitted an unmapped source header")


def _records(
    rendered: str,
    name: str,
    roles: Mapping[str, str],
    guards: set[str],
    hashes: Mapping[str, str],
) -> tuple[str, list[dict[str, Any]], set[str], int]:
    blocks: list[str] = []
    objects: list[dict[str, Any]] = []
    sources: set[str] = set()
    seen: set[tuple[str, str, str, str]] = set()
    guard_count = 0
    for block in DOC_SEPARATOR.split(rendered):
        if not block.strip():
            continue
        headers = SOURCE_HEADER.findall(block)
        if len(headers) != 1:
            raise HelmOverlayError(
                f"{name} document lacks exactly one Helm source header"
            )
        header = headers[0]
        local, archive = _source_for_header(header)
        source = local or archive
        digest = hashes.get(source or "")
        if source is None or digest is None:
            raise HelmOverlayError(f"{name} source header lacks staged hash provenance")
        try:
            value = yaml.safe_load(block)
        except yaml.YAMLError as exc:
            raise HelmOverlayError(f"{name} emitted invalid YAML") from exc
        if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
            continue
        if local in guards:
            guard_count += 1
            continue
        if local is not None and roles.get(local) != "resource":
            raise HelmOverlayError(
                f"{name} object maps to an unregistered or guard source"
            )
        metadata = value.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise HelmOverlayError(f"{name} resource metadata is not a mapping")
        api, kind, resource_name, namespace = (
            value.get("apiVersion"),
            value.get("kind"),
            metadata.get("name"),
            metadata.get("namespace"),
        )
        if not all(
            isinstance(item, str) and item for item in (api, kind, resource_name)
        ):
            raise HelmOverlayError(f"{name} object lacks a Kubernetes identity")
        api_parts = api.split("/")
        if len(api_parts) not in (1, 2) or any(
            not part or part.strip() != part for part in api_parts
        ):
            raise HelmOverlayError(
                f"{name} object has a malformed Kubernetes apiVersion"
            )
        if namespace is not None and not isinstance(namespace, str):
            raise HelmOverlayError(f"{name} object namespace is malformed")
        api_group = api_parts[0] if len(api_parts) == 2 else ""
        identity = (api_group, kind, namespace or "", resource_name)
        if identity in seen:
            raise HelmOverlayError(f"{name} emitted a duplicate Kubernetes identity")
        seen.add(identity)
        body = block.strip("\r\n")
        blocks.append(body)
        canonical = yaml.safe_dump(value, sort_keys=True, allow_unicode=True).encode(
            "utf-8"
        )
        objects.append(
            {
                "apiVersion": api,
                "kind": kind,
                "namespace": namespace,
                "name": resource_name,
                "source_header": header,
                "source_path": local,
                "source_sha256": digest,
                "dependency_archive": archive,
                "dependency_archive_sha256": digest if archive else None,
                "rendered_yaml_block_sha256": _sha(body.encode("utf-8")),
                "rendered_object_canonical_sha256": _sha(canonical),
            }
        )
        if local is not None:
            sources.add(local)
    if not blocks:
        raise HelmOverlayError(f"{name} rendered no resource documents")
    view = (
        "\n".join(
            ("---\n" if index else "") + body for index, body in enumerate(blocks)
        ).rstrip()
        + "\n"
    )
    try:
        parsed = [item for item in yaml.safe_load_all(view) if item is not None]
    except yaml.YAMLError as exc:
        raise HelmOverlayError(f"{name} rendered invalid scan-view YAML") from exc
    if len(parsed) != len(objects):
        raise HelmOverlayError(f"{name} scan view does not preserve all objects")
    return view, objects, sources, guard_count


def _run(
    command: list[str],
    cwd: Path,
    name: str,
    bounded_runner: BoundedRunner,
    timeout: int,
) -> str:
    if "--dependency-update=false" not in command:
        raise HelmOverlayError(f"{name} allows dependency updates")
    if any(
        argument in {"--enable-dns", "--dry-run=server", "--dry-run", "server"}
        for argument in command
    ):
        raise HelmOverlayError(f"{name} requests a network or server-side render mode")
    try:
        result = bounded_runner(
            command,
            cwd,
            min(float(timeout), HELM_TIMEOUT_SECONDS),
            HELM_STDOUT_LIMIT,
            HELM_STDERR_LIMIT,
        )
    except (OSError, subprocess.TimeoutExpired, HelmOverlayError) as exc:
        raise HelmOverlayError(f"Helm could not render {name}") from exc
    if not isinstance(result, BoundedProcessResult):
        raise HelmOverlayError(f"{name} bounded runner returned an invalid result")
    if result.timed_out:
        raise HelmOverlayError(f"Helm render timed out for {name}")
    if (
        result.output_limit_exceeded
        or len(result.stdout) > HELM_STDOUT_LIMIT
        or len(result.stderr) > HELM_STDERR_LIMIT
    ):
        raise HelmOverlayError(f"Helm output exceeded the fixed size cap for {name}")
    if result.returncode != 0:
        raise HelmOverlayError(f"Helm exited {result.returncode} for {name}")
    if result.stderr:
        raise HelmOverlayError(f"Helm emitted diagnostics for {name}")
    try:
        output = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HelmOverlayError(f"Helm emitted non-UTF-8 output for {name}") from exc
    if not output.strip():
        raise HelmOverlayError(f"Helm emitted no output for {name}")
    return output


def _run_version(
    tool: VerifiedHelmTool, cwd: Path, bounded_runner: BoundedRunner
) -> str:
    try:
        result = bounded_runner(
            [str(tool.executable), "version", "--template", "{{.Version}}"],
            cwd,
            10.0,
            HELM_STDOUT_LIMIT,
            HELM_STDERR_LIMIT,
        )
    except (OSError, subprocess.TimeoutExpired, HelmOverlayError) as exc:
        raise HelmOverlayError("verified Helm version probe failed") from exc
    if not isinstance(result, BoundedProcessResult):
        raise HelmOverlayError("Helm version probe returned an invalid bounded result")
    if (
        result.timed_out
        or result.output_limit_exceeded
        or len(result.stdout) > HELM_STDOUT_LIMIT
        or len(result.stderr) > HELM_STDERR_LIMIT
        or result.returncode != 0
        or result.stderr
    ):
        raise HelmOverlayError("verified Helm version probe failed")
    try:
        version = result.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise HelmOverlayError("verified Helm version is not UTF-8") from exc
    return version


def _command_hash(
    command: Sequence[str],
    root: Path,
    helm_executable: Path,
    temp_root: Path | None = None,
) -> str:
    normalized = []
    for item in command:
        text = str(item).replace(str(helm_executable), "$VERIFIED_HELM")
        text = text.replace(str(root), "$SNAPSHOT")
        if temp_root is not None:
            text = text.replace(str(temp_root), "$GATEWAY_CHART")
        normalized.append(text)
    return _sha(
        json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _validate_profile_matrix(
    commands: Sequence[Mapping[str, Any]], registry_profiles: object
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(registry_profiles, list) or len(registry_profiles) != len(
        PROFILE_NAMES
    ):
        raise HelmOverlayError("rendered profile registry is incomplete")
    profiles: dict[str, Mapping[str, Any]] = {}
    for row in registry_profiles:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise HelmOverlayError("profile registry row is malformed")
        name = row["name"]
        if name in profiles:
            raise HelmOverlayError("profile registry repeats a profile name")
        profiles[name] = row
    if set(profiles) != set(PROFILE_NAMES):
        raise HelmOverlayError("rendered profile names differ from the reviewed matrix")
    command_map = {str(spec["name"]): spec for spec in commands}
    if len(command_map) != len(PROFILE_NAMES) or set(command_map) != set(PROFILE_NAMES):
        raise HelmOverlayError(
            "renderer does not implement the exact reviewed profile matrix"
        )
    required_keys = {
        "name",
        "view_path",
        "chart_root",
        "profile_kind",
        "environment",
        "deployment_profile",
        "deployment_evidence",
        "synthetic_overrides",
        "values_sources",
        "api_versions",
    }
    for name in PROFILE_NAMES:
        row = profiles[name]
        spec = command_map[name]
        if set(row) != required_keys:
            raise HelmOverlayError(f"profile registry fields drifted: {name}")
        expected = {key: spec[key] for key in required_keys}
        if dict(row) != expected:
            raise HelmOverlayError(f"profile registry and renderer differ: {name}")
        if row["view_path"] in {REGISTRY_RELATIVE}:
            raise HelmOverlayError(
                f"rendered profile collides with policy input: {name}"
            )
        view = _relative(row["view_path"])
        if view != f"charts/rendered-profiles/{name}.yaml":
            raise HelmOverlayError(f"profile view path drifted: {name}")
    return profiles


def prepare_overlay(
    source_snapshot_root: Path,
    overlay_root: Path,
    source_manifest: Sequence[Mapping[str, str]],
    *,
    helm_tool: VerifiedHelmTool,
    bounded_runner: BoundedRunner = bounded_process_runner,
) -> tuple[Path, dict[str, Any]]:
    """Render pinned Helm profiles from stage-zero blobs and materialize scan YAML."""
    root_input = Path(source_snapshot_root)
    destination_input = Path(overlay_root)
    if _is_link(root_input) or _is_link(destination_input):
        raise HelmOverlayError("source or overlay path may not be linked")
    root = root_input.resolve(strict=True)
    destination = destination_input.resolve()
    if not root.is_dir() or destination.exists():
        raise HelmOverlayError(
            "source or overlay path is missing, linked, or already exists"
        )
    if destination == root or destination.is_relative_to(root):
        raise HelmOverlayError("overlay may not be nested under the source snapshot")
    records, source_manifest_sha = _manifest_map(root, source_manifest)
    registry, registry_sha = _registry(root, records)
    roles, guards = _roles(registry)
    templates = _discover_templates(records, registry)
    if len(templates) != 40:
        raise HelmOverlayError(
            "template inventory no longer has the reviewed 40 sources"
        )
    hashes = {path: item["sha256"] for path, item in records.items()}
    for path in templates:
        if path not in records:
            raise HelmOverlayError(f"template is not a stage-zero blob: {path}")
    if set(registry.get("required_profile_coverage", {})) != set(
        EXPECTED_REQUIRED_COVERAGE
    ):
        raise HelmOverlayError("required resource profile coverage registry drifted")
    if registry["required_profile_coverage"] != EXPECTED_REQUIRED_COVERAGE:
        raise HelmOverlayError(
            "required source-to-profile coverage differs from the reviewed matrix"
        )

    _verify_helm_tool(helm_tool, root, registry)
    version = _run_version(helm_tool, root, bounded_runner)
    if version != registry["helm_version"] or version != helm_tool.version:
        raise HelmOverlayError("Helm binary does not match the pinned version")
    _verify_helm_tool(helm_tool, root, registry)
    helm = str(helm_tool.executable)
    commands = _commands(root, helm)
    gateway_spec = {
        "name": "gateway-api-isolated-synthetic-apis",
        "profile_kind": "isolated-diagnostic-only; synthetic-APIs; full-chart-guard-remains-active; not-deployment-evidence",
        "chart_root": "charts/university-ecosystem",
        "environment": "development",
        "deployment_profile": False,
        "deployment_evidence": False,
        "synthetic_overrides": [
            "isolated one-template chart fixture",
            "synthetic Gateway API declarations; does not enable full-chart deployment",
        ],
        "view_path": "charts/rendered-profiles/gateway-api-isolated-synthetic-apis.yaml",
        "values_sources": [
            "charts/university-ecosystem/values.yaml",
            "charts/university-ecosystem/values.schema.json",
        ],
        "api_versions": list(API_VERSIONS),
    }
    commands.append(gateway_spec)
    profile_map = _validate_profile_matrix(commands, registry.get("profiles"))

    coverage: dict[str, set[str]] = {path: set() for path in roles}
    profile_rows: list[dict[str, Any]] = []
    outputs: list[tuple[str, str, bytes]] = []
    object_count = 0
    for spec in commands:
        if spec["name"] == "gateway-api-isolated-synthetic-apis":
            continue
        name = spec["name"]
        _verify_helm_tool(helm_tool, root, registry)
        raw = _run(spec["command"], root, name, bounded_runner, HELM_TIMEOUT_SECONDS)
        _verify_helm_tool(helm_tool, root, registry)
        view, objects, sources, guard_count = _records(raw, name, roles, guards, hashes)
        view_path = profile_map[name]["view_path"]
        if view_path in records:
            raise HelmOverlayError(f"invalid or colliding profile view path: {name}")
        for source in sources:
            coverage[source].add(name)
        values = sorted(set(spec["values_sources"]))
        if any(path not in hashes for path in values):
            raise HelmOverlayError(f"{name} values are not stage-zero inputs")
        row = {
            "name": name,
            "profile_kind": profile_map[name]["profile_kind"],
            "environment": profile_map[name]["environment"],
            "deployment_profile": profile_map[name]["deployment_profile"],
            "deployment_evidence": profile_map[name]["deployment_evidence"],
            "synthetic_overrides": profile_map[name]["synthetic_overrides"],
            "chart_root": profile_map[name]["chart_root"],
            "helm_version": registry["helm_version"],
            "dependency_update": False,
            "command_sha256": _command_hash(
                spec["command"], root, helm_tool.executable
            ),
            "helm_binary_sha256": helm_tool.binary_sha256,
            "helm_archive_sha256": helm_tool.archive_sha256,
            "values_sources": [
                {"path": path, "sha256": hashes[path]} for path in values
            ],
            "api_versions": spec["api_versions"],
            "view_path": view_path,
            "view_sha256": _sha(view.encode("utf-8")),
            "raw_helm_output_sha256": _sha(raw.encode("utf-8")),
            "rendered_object_count": len(objects),
            "guard_excluded_document_count": guard_count,
            "source_paths_seen": sorted(sources),
            "objects": objects,
        }
        profile_rows.append(row)
        outputs.append((name, view_path, view.encode("utf-8")))
        object_count += len(objects)
        if sum(len(item[2]) for item in outputs) > MAX_TOTAL_RENDERED_VIEW_BYTES:
            raise HelmOverlayError(
                "combined rendered scan views exceed the fixed size cap"
            )

    app = root / "charts/university-ecosystem"
    with tempfile.TemporaryDirectory(
        prefix="helm-gateway-profile-", dir=destination.parent
    ) as temp:
        isolated = Path(temp)
        (isolated / "templates").mkdir()
        (isolated / "Chart.yaml").write_text(
            "apiVersion: v2\nname: university-ecosystem\nversion: 0.1.0\n",
            encoding="utf-8",
        )
        for source, target in (
            (app / "values.yaml", isolated / "values.yaml"),
            (app / "values.schema.json", isolated / "values.schema.json"),
            (app / "templates/_helpers.tpl", isolated / "templates/_helpers.tpl"),
            (
                app / "templates/gateway-api.yaml",
                isolated / "templates/gateway-api.yaml",
            ),
        ):
            shutil.copyfile(source, target)
        name = "gateway-api-isolated-synthetic-apis"
        command = _gateway_command(helm, isolated)
        _verify_helm_tool(helm_tool, root, registry)
        raw = _run(command, root, name, bounded_runner, HELM_TIMEOUT_SECONDS)
        _verify_helm_tool(helm_tool, root, registry)
        view, objects, sources, guard_count = _records(raw, name, roles, guards, hashes)
        view_path = profile_map[name]["view_path"]
        for source in sources:
            coverage[source].add(name)
        values = sorted(
            {
                "charts/university-ecosystem/values.yaml",
                "charts/university-ecosystem/values.schema.json",
                "charts/university-ecosystem/templates/_helpers.tpl",
                "charts/university-ecosystem/templates/gateway-api.yaml",
            }
        )
        if any(path not in hashes for path in values):
            raise HelmOverlayError(
                "Gateway API diagnostic inputs are not stage-zero blobs"
            )
        profile_rows.append(
            {
                "name": name,
                "profile_kind": profile_map[name]["profile_kind"],
                "environment": profile_map[name]["environment"],
                "deployment_profile": profile_map[name]["deployment_profile"],
                "deployment_evidence": profile_map[name]["deployment_evidence"],
                "synthetic_overrides": profile_map[name]["synthetic_overrides"],
                "chart_root": profile_map[name]["chart_root"],
                "helm_version": registry["helm_version"],
                "dependency_update": False,
                "command_sha256": _command_hash(
                    command, root, helm_tool.executable, isolated
                ),
                "helm_binary_sha256": helm_tool.binary_sha256,
                "helm_archive_sha256": helm_tool.archive_sha256,
                "values_sources": [
                    {"path": path, "sha256": hashes[path]} for path in values
                ],
                "api_versions": list(API_VERSIONS),
                "view_path": view_path,
                "view_sha256": _sha(view.encode("utf-8")),
                "raw_helm_output_sha256": _sha(raw.encode("utf-8")),
                "rendered_object_count": len(objects),
                "guard_excluded_document_count": guard_count,
                "source_paths_seen": sorted(sources),
                "objects": objects,
            }
        )
        outputs.append((name, view_path, view.encode("utf-8")))
        object_count += len(objects)
        if sum(len(item[2]) for item in outputs) > MAX_TOTAL_RENDERED_VIEW_BYTES:
            raise HelmOverlayError(
                "combined rendered scan views exceed the fixed size cap"
            )

    for path, required_profiles in EXPECTED_REQUIRED_COVERAGE.items():
        if path not in roles or not set(required_profiles) <= coverage[path]:
            raise HelmOverlayError(
                f"required profile does not render its source: {path}"
            )
    resources = {path for path, role in roles.items() if role == "resource"}
    missing = sorted(path for path in resources if not coverage[path])
    if missing:
        raise HelmOverlayError(f"resource templates have no rendered object: {missing}")
    if any(coverage[path] for path in guards):
        raise HelmOverlayError("guard-only template entered a resource scan view")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(root, destination, symlinks=False)
        for path in sorted(templates):
            target = destination / PurePosixPath(path)
            if _is_link(target) or not target.is_file():
                raise HelmOverlayError(f"raw template disappeared from overlay: {path}")
            target.unlink()
        for name, relative, content in outputs:
            target = destination / PurePosixPath(relative)
            if target.exists() or _is_link(target):
                raise HelmOverlayError(
                    f"rendered view collides with staged path: {relative}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        target_rows: list[dict[str, str]] = []
        for path, row in sorted(records.items()):
            if path in templates:
                continue
            target_rows.append(
                {
                    "path": path,
                    "mode": row["mode"],
                    "oid": row["oid"],
                    "stage": row["stage"],
                    "sha256": row["sha256"],
                    "origin": "staged-index",
                }
            )
        for name, relative, content in outputs:
            oid = _sha(content)
            target_rows.append(
                {
                    "path": relative,
                    "mode": "100644",
                    "oid": oid,
                    "stage": "rendered",
                    "sha256": _sha(content),
                    "origin": f"helm-profile:{name}",
                }
            )
        for row in target_rows:
            path = destination / PurePosixPath(row["path"])
            if _is_link(path) or not path.is_file() or _sha_file(path) != row["sha256"]:
                raise HelmOverlayError(f"overlay target hash mismatch: {row['path']}")
        for path in templates:
            if (destination / PurePosixPath(path)).exists():
                raise HelmOverlayError(f"raw template remained in overlay: {path}")
    except Exception:
        shutil.rmtree(destination)
        raise

    provenance = {
        "schema_version": 1,
        "target_model": "helm-rendered-v1",
        "report_scope": "renderer-only",
        "helm_version": registry["helm_version"],
        "helm_platform_key": helm_tool.platform_key,
        "helm_archive_sha256": helm_tool.archive_sha256,
        "helm_binary_sha256": helm_tool.binary_sha256,
        "dependency_updates": False,
        "profile_registry_path": REGISTRY_RELATIVE,
        "profile_registry_sha256": registry_sha,
        "source_snapshot_manifest_sha256": source_manifest_sha,
        "template_sources": [
            {
                "path": path,
                "source_sha256": records[path]["sha256"],
                "git_blob_oid": records[path]["oid"],
                "role": roles[path],
                "profiles": sorted(coverage[path]),
            }
            for path in sorted(roles)
        ],
        "guard_only_sources": sorted(guards),
        "chart_inputs": [
            {"path": path, "sha256": row["sha256"], "git_blob_oid": row["oid"]}
            for path, row in sorted(records.items())
            if path.startswith("charts/")
        ],
        "profiles": sorted(profile_rows, key=lambda row: row["name"]),
        "targets": sorted(target_rows, key=lambda row: row["path"]),
        "rendered_object_count": object_count,
        "source_line_mapping_claim": False,
        "scanner_invoked": False,
        "cluster_or_cni_claim": False,
    }
    return destination, provenance
