"""Read-only npm artifact evidence for React compiler dependency remediation.

Packages are never installed, imported, executed, or extracted. Static signals
identify candidates for further review; they cannot establish a security fix.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import hmac
import http.client
import io
import json
import os
import re
import signal
import sys
import tarfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

BABEL = "babel-plugin-react-compiler"
ESLINT = "eslint-plugin-react-compiler"
CONTROLS = ((BABEL, "1.0.0"), (ESLINT, "19.1.0-rc.2"))
PACKAGES = frozenset((BABEL, ESLINT))
REGISTRY = "https://registry.npmjs.org"
VERSION = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
MAX_METADATA = 32 * 1024 * 1024
MAX_COMPRESSED = 16 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
MAX_MEMBERS = 512
REQUEST_TIMEOUT = 20
READ_DEADLINE = 60
PROBE_DEADLINE = 7 * 60
EVIDENCE_PATHS = frozenset(
    {
        "package/package.json",
        "package/dist/index.js",
        "package/dist/index.d.ts",
        "package/LICENSE",
        "package/LICENSE.md",
        "package/LICENSE.txt",
    }
)


class ProbeError(ValueError):
    """A sanitized, fail-closed probe error."""


def _identity(package: str, version: str) -> None:
    if (
        package not in PACKAGES
        or not isinstance(version, str)
        or len(version) > 128
        or VERSION.fullmatch(version) is None
    ):
        raise ProbeError("Unsupported package identity")


def _published(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ProbeError("Missing authoritative publication time")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProbeError("Invalid publication time") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ProbeError("Publication time must include a timezone")
    return result.astimezone(UTC)


def select_candidates(
    packuments: Mapping[str, Any], cutoff: datetime
) -> list[tuple[str, str]]:
    """Select exact controls and at most three publication-mature alternatives."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ProbeError("Maturity cutoff must include a timezone")
    mature: dict[str, list[tuple[datetime, str]]] = {}
    for package in (BABEL, ESLINT):
        data = packuments.get(package)
        if not isinstance(data, dict) or data.get("name") != package:
            raise ProbeError("Registry package identity mismatch")
        versions, times = data.get("versions"), data.get("time")
        if not isinstance(versions, dict) or not isinstance(times, dict):
            raise ProbeError("Registry versions or publication times missing")
        mature[package] = []
        for version in versions:
            try:
                _identity(package, version)
                published = _published(times.get(version))
            except ProbeError:
                continue
            if published <= cutoff:
                mature[package].append((published, version))
        mature[package].sort(reverse=True)
    result = list(CONTROLS)
    for package, version in CONTROLS:
        if not any(item[1] == version for item in mature[package]):
            raise ProbeError("Deployed control is missing or not publication-mature")
    for package, prerelease in ((BABEL, False), (BABEL, True), (ESLINT, None)):
        candidate = next(
            (
                version
                for _, version in mature[package]
                if prerelease is None or ("-" in version) == prerelease
            ),
            None,
        )
        if candidate is not None and (package, candidate) not in result:
            result.append((package, candidate))
    return result


def _integrity(value: Any) -> bytes:
    if not isinstance(value, str) or not value.startswith("sha512-"):
        raise ProbeError("Artifact requires SHA-512 integrity")
    encoded = value.removeprefix("sha512-")
    if len(encoded) != 88:
        raise ProbeError("Invalid SHA-512 integrity")
    try:
        digest = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ProbeError("Invalid SHA-512 integrity") from exc
    if len(digest) != 64 or base64.b64encode(digest).decode("ascii") != encoded:
        raise ProbeError("Invalid SHA-512 integrity")
    return digest


def artifact_request(
    package: str,
    version: str,
    metadata: Mapping[str, Any],
    *,
    locked_integrity: str | None = None,
) -> dict[str, Any]:
    _identity(package, version)
    if not isinstance(metadata, dict) or (
        metadata.get("name") != package or metadata.get("version") != version
    ):
        raise ProbeError("Registry artifact identity mismatch")
    dist = metadata.get("dist")
    if not isinstance(dist, dict):
        raise ProbeError("Registry artifact distribution missing")
    integrity = dist.get("integrity")
    digest = _integrity(integrity)
    if locked_integrity is not None and not hmac.compare_digest(
        digest, _integrity(locked_integrity)
    ):
        raise ProbeError("Registry control differs from deployed lock integrity")
    expected = f"{REGISTRY}/{package}/-/{package}-{version}.tgz"
    if dist.get("tarball") != expected:
        raise ProbeError("Artifact URL is not the exact approved registry target")
    return {"url": expected, "integrity": integrity}


def read_bounded(response: BinaryIO, limit: int) -> bytes:
    if not isinstance(limit, int) or not 0 < limit <= MAX_UNPACKED:
        raise ProbeError("Invalid response byte limit")
    read_once = getattr(response, "read1", None)
    if not callable(read_once):
        raise ProbeError("Response requires incremental byte reads")
    output = bytearray()
    # Cooperative body budget; the CLI alarm also bounds headers and framing.
    deadline = time.monotonic() + READ_DEADLINE
    while True:
        if time.monotonic() > deadline:
            raise ProbeError("Response read deadline exceeded")
        chunk = read_once(min(64 * 1024, limit + 1 - len(output)))
        if not isinstance(chunk, bytes):
            raise ProbeError("Response is not a byte stream")
        output.extend(chunk)
        if len(output) > limit:
            raise ProbeError("Response exceeds byte limit")
        if time.monotonic() > deadline:
            raise ProbeError("Response read deadline exceeded")
        if not chunk:
            return bytes(output)


def _approved_url(url: str) -> None:
    if not isinstance(url, str):
        raise ProbeError("Unapproved network target")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ProbeError("Unapproved network target") from exc
    if (
        parsed.scheme != "https"
        or parsed.netloc != "registry.npmjs.org"
        or parsed.query
        or parsed.fragment
    ):
        raise ProbeError("Unapproved network target")
    for package in PACKAGES:
        if url == f"{REGISTRY}/{package}":
            return
        prefix = f"{REGISTRY}/{package}/-/{package}-"
        if url.startswith(prefix) and url.endswith(".tgz"):
            _identity(package, url[len(prefix) : -len(".tgz")])
            return
    raise ProbeError("Unapproved network target")


@contextmanager
def _registry_response(url: str, *, timeout: int) -> Iterator[http.client.HTTPResponse]:
    connection = http.client.HTTPSConnection("registry.npmjs.org", timeout=timeout)
    try:
        connection.request(
            "GET",
            urlsplit(url).path,
            headers={
                "Accept": "application/json" if not url.endswith(".tgz") else "*/*",
                "Accept-Encoding": "identity",
                "User-Agent": "university-ecosystem-artifact-audit",
            },
        )
        with connection.getresponse() as response:
            yield response
    finally:
        connection.close()


def fetch_bounded(
    url: str,
    limit: int,
    *,
    opener: Callable[..., Any] | None = None,
) -> bytes:
    _approved_url(url)
    transport = opener or _registry_response
    try:
        with transport(url, timeout=REQUEST_TIMEOUT) as response:
            if response.status != 200:
                raise ProbeError("Unexpected registry response status")
            if response.headers.get("Content-Encoding", "identity") != "identity":
                raise ProbeError("Unexpected registry content encoding")
            length = response.headers.get("Content-Length")
            if length is not None and (
                not length.isascii()
                or not length.isdigit()
                or len(length) > 12
                or int(length) > limit
            ):
                raise ProbeError("Invalid or oversized registry content length")
            return read_bounded(response, limit)
    except ProbeError:
        raise
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise ProbeError("Registry request failed") from exc


def _member_path(member: tarfile.TarInfo) -> str:
    name = member.name
    if (
        not name
        or len(name) > 512
        or "\\" in name
        or ":" in name
        or any(ord(character) < 32 for character in name)
    ):
        raise ProbeError("Unsafe archive member path")
    if member.isdir() and name.endswith("/"):
        name = name[:-1]
    parts = name.split("/")
    if parts[0] != "package" or any(part in {"", ".", ".."} for part in parts):
        raise ProbeError("Unsafe archive member path")
    if len(parts) == 1 and not member.isdir():
        raise ProbeError("Invalid archive package root")
    return name


def _signals(source: str) -> dict[str, int]:
    signals = {
        name: source.count(name)
        for name in (
            "$ZodArray",
            "capSize",
            "sizeCaps",
            "generateSizeGate",
            "CompileError",
            "InvalidReact",
            "InvalidJS",
            "logger",
            "reportUnusedDirectives",
        )
    }
    for name, module in (
        ("external_zod_root", "zod"),
        ("external_zod_v3", "zod/v3"),
        ("external_zod_v4", "zod/v4"),
    ):
        pattern = (
            r"""(?:\brequire\s*\(\s*|\bfrom\s*|\bimport\s*\(\s*)["']"""
            + re.escape(module)
            + r"""["']"""
        )
        signals[name] = len(re.findall(pattern, source))
    signals["bundled_zod_v3_path"] = source.count("node_modules/zod/v3/")
    signals["bundled_zod_v4_path"] = source.count("node_modules/zod/v4/")
    signals["bundled_zod_legacy_path"] = source.count("node_modules/zod/lib/")
    return signals


def inspect_artifact(
    raw: bytes,
    package: str,
    version: str,
    integrity: str,
    *,
    max_unpacked: int = MAX_UNPACKED,
    max_members: int = MAX_MEMBERS,
) -> dict[str, Any]:
    _identity(package, version)
    if len(raw) > MAX_COMPRESSED:
        raise ProbeError("Compressed artifact exceeds byte limit")
    if not hmac.compare_digest(hashlib.sha512(raw).digest(), _integrity(integrity)):
        raise ProbeError("Artifact integrity mismatch")
    if not 0 < max_members <= MAX_MEMBERS:
        raise ProbeError("Invalid archive member limit")
    evidence: dict[str, bytes] = {}
    seen: set[str] = set()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            unpacked = read_bounded(stream, max_unpacked)
        with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as archive:
            for member in archive:
                if len(seen) >= max_members:
                    raise ProbeError("Archive exceeds member limit")
                path = _member_path(member)
                if path in seen:
                    raise ProbeError("Duplicate archive member")
                seen.add(path)
                if (
                    not (member.isfile() or member.isdir())
                    or member.sparse is not None
                    or any(key.startswith("GNU.sparse") for key in member.pax_headers)
                ):
                    raise ProbeError("Unsupported archive member type")
                if (
                    member.size < 0
                    or member.offset_data + member.size > len(unpacked)
                    or (member.isdir() and member.size != 0)
                ):
                    raise ProbeError("Invalid archive member size")
                if path in EVIDENCE_PATHS:
                    if not member.isfile():
                        raise ProbeError("Evidence entry is not a regular file")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ProbeError("Evidence entry cannot be read")
                    with stream:
                        data = read_bounded(stream, max_unpacked)
                    if len(data) != member.size:
                        raise ProbeError("Truncated evidence entry")
                    evidence[path] = data
    except ProbeError:
        raise
    except (OSError, EOFError, ValueError, tarfile.TarError) as exc:
        raise ProbeError("Invalid compressed tar artifact") from exc
    if not {"package/package.json", "package/dist/index.js"} <= evidence.keys():
        raise ProbeError("Required compiler artifact entries missing")
    try:
        decoded = {path: data.decode("utf-8") for path, data in evidence.items()}
        manifest = json.loads(decoded["package/package.json"])
    except (RecursionError, ValueError) as exc:
        raise ProbeError("Invalid artifact text or manifest") from exc
    if not isinstance(manifest, dict) or (
        manifest.get("name") != package or manifest.get("version") != version
    ):
        raise ProbeError("Artifact manifest identity mismatch")
    scripts = manifest.get("scripts", {})
    dependencies = manifest.get("dependencies", {})
    return {
        "name": package,
        "version": version,
        "tarball_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_size": len(raw),
        "unpacked_size": len(unpacked),
        "member_count": len(seen),
        "files": {
            path: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for path, data in sorted(evidence.items())
        },
        "has_lifecycle_scripts": isinstance(scripts, dict)
        and any(
            key in scripts
            for key in (
                "preinstall",
                "install",
                "postinstall",
                "preprepare",
                "prepare",
                "postprepare",
                "prepublish",
                "prepublishOnly",
                "publish",
                "postpublish",
                "prepack",
                "postpack",
            )
        ),
        "declares_zod_dependency": isinstance(dependencies, dict)
        and "zod" in dependencies,
        "signals": _signals(decoded["package/dist/index.js"]),
        "patched_status": "not_established",
        "artifact_executed": False,
    }


def main() -> None:
    source_sha = os.environ.get("SOURCE_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ProbeError("A full source SHA is required")
    lock_path = Path(__file__).resolve().parents[2] / "frontend" / "package-lock.json"
    with lock_path.open("rb") as stream:
        lock_bytes = read_bounded(stream, MAX_METADATA)
    try:
        lock = json.loads(lock_bytes)
    except (RecursionError, ValueError) as exc:
        raise ProbeError("Invalid deployed lock JSON") from exc
    if not isinstance(lock, dict) or not isinstance(lock.get("packages"), dict):
        raise ProbeError("Deployed lock package inventory missing")
    controls: dict[tuple[str, str], str] = {}
    for package, version in CONTROLS:
        entry = lock["packages"].get(f"node_modules/{package}")
        if not isinstance(entry, dict) or entry.get("version") != version:
            raise ProbeError("Deployed control version changed")
        _integrity(entry.get("integrity"))
        controls[package, version] = entry["integrity"]
    observed = datetime.now(UTC)
    cutoff = observed - timedelta(days=7)
    packuments: dict[str, Any] = {}
    for package in (BABEL, ESLINT):
        raw = fetch_bounded(f"{REGISTRY}/{package}", MAX_METADATA)
        try:
            packuments[package] = json.loads(raw)
        except (RecursionError, ValueError) as exc:
            raise ProbeError("Invalid registry metadata JSON") from exc
    reports = []
    for package, version in select_candidates(packuments, cutoff):
        request = artifact_request(
            package,
            version,
            packuments[package]["versions"][version],
            locked_integrity=controls.get((package, version)),
        )
        raw = fetch_bounded(request["url"], MAX_COMPRESSED)
        report = inspect_artifact(raw, package, version, request["integrity"])
        report["published_at"] = _published(
            packuments[package]["time"][version]
        ).isoformat()
        report["is_deployed_control"] = (package, version) in controls
        report["tarball_url"] = request["url"]
        reports.append(report)
    with lock_path.open("rb") as stream:
        if read_bounded(stream, MAX_METADATA) != lock_bytes:
            raise ProbeError("Deployed lock changed during read-only probe")
    print(
        json.dumps(
            {
                "source_sha": source_sha,
                "observed_at": observed.isoformat(),
                "maturity_cutoff": cutoff.isoformat(),
                "selection_basis": "authoritative_npm_publication_time",
                "artifact_execution": False,
                "fix_verification": "not_established",
                "candidates": reports,
            },
            sort_keys=True,
        )
    )


def _run_with_deadline() -> None:
    """Bound the whole Linux-hosted CLI, including HTTP headers and framing."""

    def expired(_signum: int, _frame: Any) -> None:
        raise ProbeError("Probe wall-clock deadline exceeded")

    previous = signal.signal(signal.SIGALRM, expired)
    try:
        signal.alarm(PROBE_DEADLINE)
        main()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    try:
        _run_with_deadline()
    except (ProbeError, OSError) as exc:
        message = str(exc) if isinstance(exc, ProbeError) else "Local input read failed"
        print(f"React compiler artifact probe failed: {message}", file=sys.stderr)
        raise SystemExit(1) from None
