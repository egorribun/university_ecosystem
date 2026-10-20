"""Owned live acceptance stand running the full or selected Core stack.

By default the stand runs from ``../ue-live`` (a detached git worktree).
Explicit ``--in-place --state-dir`` mode keeps generated configuration under
an owned temporary run root while using the current checkout as its build
context. Every run receives a unique Compose project recorded in an ownership
marker, so its volumes and networks are isolated from other stacks.

Usage::

    python -m scripts.live_stand up [--ref HEAD] [--stack full|core]
    # create/refresh the worktree and start (full is the default)
    python -m scripts.live_stand up --in-place --state-dir <owned-temp-run> --ref HEAD
    python -m scripts.live_stand seed --demo        # load demo users and content
    python -m scripts.live_stand e2e [--mode smoke|full]  # reseed and run live Playwright safely
    python -m scripts.live_stand status             # read-only status
    python -m scripts.live_stand stop               # stop containers; preserve data
    python -m scripts.live_stand quiesce --in-place --state-dir <owned-temp-run>  # stop Core writers; retain stores
    python -m scripts.live_stand teardown           # remove only this run's Compose data

``down`` remains a compatibility alias for ``stop``. ``teardown`` preserves
the worktree, ``.env*`` files, secrets and evidence; it removes volumes only
after validating the run ownership marker.
"""

from __future__ import annotations

import argparse
import base64
import csv
import ctypes
import errno
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import selectors
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from scripts import fast_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKTREE_NAME = "ue-live"
WORKTREE = REPO_ROOT.parent / WORKTREE_NAME
IN_PLACE_MODE = False
SOURCE_SHA: str | None = None
PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION = 7
PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION = 9
IN_PLACE_OWNER_SCHEMA_VERSION = 11
IN_PLACE_STATE_PARENT = "ue-live-acceptance"
IN_PLACE_STATE_PATTERN = re.compile(r"^run-[A-Za-z0-9-]{1,80}$")
IN_PLACE_BUILD_SOURCE_PATHS = (
    "app",
    "alembic",
    "native",
    "frontend",
    "gen",
    "services/pkg",
    "services/gateway",
    "services/ws-hub",
    "services/file-processor",
)
IN_PLACE_DOCKERIGNORE_EXCLUSIONS = (
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.mypy_cache/**",
    "**/.cache/**",
    "**/target/**",
    "frontend/dist/**",
    "frontend/coverage/**",
    "frontend/test-results/**",
    "frontend/playwright-report/**",
    "frontend/.vitest/**",
    "**/.secrets/**",
    "**/artifacts/**",
    "**/.root-*/**",
    "frontend/reports/**",
    "frontend/bundle-report.json",
    "frontend/rust-crypto/pkg/.gitignore",
    "frontend/rust-crypto/pkg/uni_wasm_crypto_bg.wasm.d.ts",
    "frontend/wasm-sanitizer/pkg/.gitignore",
    "frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm.d.ts",
)
IN_PLACE_DOCKERIGNORE_ARTIFACT_RULES = (
    "frontend/dist/",
    "frontend/coverage/",
    "frontend/test-results/",
    "frontend/playwright-report/",
    "frontend/.vitest/",
    "frontend/reports/",
    "frontend/bundle-report.json",
    "frontend/rust-crypto/pkg/.gitignore",
    "frontend/rust-crypto/pkg/uni_wasm_crypto_bg.wasm.d.ts",
    "frontend/wasm-sanitizer/pkg/.gitignore",
    "frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm.d.ts",
)
OVERLAY = "docker-compose.live.yml"
IN_PLACE_OVERLAY = "docker-compose.live-state.yml"
COMPOSE_FILES = ("docker-compose.full.yml", OVERLAY)
MAILPIT_PORT = 18025
LIVE_PORT_SPECS = (
    ("BACKEND", "backend", 8000),
    ("FRONTEND", "frontend", 3000),
    ("POSTGRES", "postgres", 5432),
    ("GATEWAY", "gateway", 8080),
    ("WS_HUB", "ws-hub", 8081),
    ("TEMPORAL_GRPC", "temporal", 7233),
    ("TEMPORAL_WEB", "temporal", 7243),
    ("IMGPROXY", "imgproxy", 8080),
    ("GRAFANA", "grafana", 3000),
    ("PROMETHEUS", "prometheus", 9090),
    ("ALLOY", "alloy", 12345),
    ("PYROSCOPE", "pyroscope", 4040),
    ("CADDY_HTTP", "caddy", 80),
    ("CADDY_HTTPS", "caddy", 443),
    ("MINIO", "minio", 9000),
    ("MAILPIT", "mailpit", 8025),
)
PRE_MINIO_PUBLISHED_PORT_NAMES = (
    "BACKEND",
    "FRONTEND",
    "POSTGRES",
    "GATEWAY",
    "WS_HUB",
    "TEMPORAL_GRPC",
    "TEMPORAL_WEB",
    "IMGPROXY",
    "GRAFANA",
    "PROMETHEUS",
    "ALLOY",
    "PYROSCOPE",
    "CADDY_HTTP",
    "CADDY_HTTPS",
    "MAILPIT",
)
LEGACY_PUBLISHED_PORTS = {
    "BACKEND": 8000,
    "FRONTEND": 8081,
    "POSTGRES": 15433,
    "GATEWAY": 8080,
    "WS_HUB": 8083,
    "TEMPORAL_GRPC": 7233,
    "TEMPORAL_WEB": 7243,
    "IMGPROXY": 8082,
    "GRAFANA": 3000,
    "PROMETHEUS": 9090,
    "ALLOY": 12345,
    "PYROSCOPE": 4040,
    "CADDY_HTTP": 80,
    "CADDY_HTTPS": 443,
    "MAILPIT": MAILPIT_PORT,
}
DEFAULT_PUBLISHED_PORTS = {**LEGACY_PUBLISHED_PORTS, "MINIO": 19000}
PORT_RANGE = (20000, 45000)
PORT_BIND_HOST = "127.0.0.1"
VAPID_FILE = Path(".secrets") / "live-vapid.json"
ADMIN_PASSWORD_FILE = Path(".secrets") / "live-admin-password.json"
STAND_FILE = Path(".secrets") / "live-stand.json"
PROJECT_PREFIX = "ue-live-"
PROJECT_PATTERN = re.compile(r"^ue-live-[0-9a-f]{16}$")
PREVIOUS_STACK_OWNER_SCHEMA_VERSION = 6
PRE_MINIO_OWNER_SCHEMA_VERSION = 8
OWNER_SCHEMA_VERSION = 10
RESOURCE_OWNER_SCHEMA_VERSION = 5
PREVIOUS_OWNER_SCHEMA_VERSION = 4
VOLUME_OWNER_SCHEMA_VERSION = 3
LEGACY_OWNER_SCHEMA_VERSION = 2
LIVE_STACK_FULL = "full"
LIVE_STACK_CORE = "core"
LIVE_STACKS = (LIVE_STACK_FULL, LIVE_STACK_CORE)
LIVE_CORE_SERVICE_ROOTS = (
    "caddy",
    "mailpit",
    "notifications-worker",
    "outbox-worker",
    "spicedb",
)
LIVE_CORE_EXPECTED_SERVICES = (
    "backend",
    "caddy",
    "flagd",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "mailpit",
    "migrations",
    "minio",
    "minio-init",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "postgres-databases-init",
    "redis",
    "revocation-redis",
    "spicedb",
    "spicedb-migrate",
    "tempo",
    "tempo-healthprobe",
    "ws-hub",
)
LIVE_TRUSTED_PROXY_SERVICES = ("backend", "caddy", "gateway", "ws-hub")
LIVE_TRUSTED_PROXY_SETTINGS = (
    "TRUSTED_PROXIES",
    "GATEWAY_TRUSTED_PROXIES",
    "WS_HUB_TRUSTED_PROXIES",
)
LIVE_CORE_QUIESCE_DATA_STORES = frozenset({"minio", "postgres"})
DAEMON_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMPOSE_INSPECTION_PLACEHOLDER = "live-stand-inspection-placeholder"
SEED_SCRIPTS = (
    "scripts/seed_demo_data.py",
    "scripts/seed_admin_data.py",
    "scripts/seed_live_authorization.py",
)
LIVE_E2E_COMMAND = ("npm", "run", "test:e2e:live")
LIVE_CADDY_PROBE_SPEC = "tests/e2e-live/zzz-aud174-prehydration-caddy-log.live.spec.ts"
LIVE_CADDY_PROBE_PROJECTS = ("desktop", "mobile")
LIVE_E2E_SMOKE_FILES = (
    "tests/e2e-live/auth-roles.live.spec.ts",
    "tests/e2e-live/password-reset.live.spec.ts",
    "tests/e2e-live/search-dialog-keyboard.live.spec.ts",
    "tests/e2e-live/settings-radio-focus.live.spec.ts",
    LIVE_CADDY_PROBE_SPEC,
)
LIVE_E2E_WINDOWS_COMMAND = (
    "cmd.exe",
    "/d",
    "/s",
    "/c",
    "npm run test:e2e:live",
)
LIVE_E2E_NPM_CI_COMMAND = ("npm", "ci")
LIVE_E2E_WINDOWS_NPM_CI_COMMAND = ("cmd.exe", "/d", "/s", "/c", "npm ci")
LIVE_E2E_CHROMIUM_PROBE_COMMAND = (
    "node",
    "-e",
    "process.stdout.write(require('playwright').chromium.executablePath())",
)
LIVE_E2E_CI_ENVIRONMENT = ("CI", "GITHUB_ACTIONS")
LIVE_E2E_WINDOWS_ENVIRONMENT = (
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
)
LIVE_E2E_UNIX_ENVIRONMENT = ("HOME", "TMPDIR")
LIVE_PRIMARY_REPOSITORY_ROOT_ENV = "LIVE_PRIMARY_REPOSITORY_ROOT"
LIVE_E2E_REQUIRED_PACKAGES = (
    "@playwright/test",
    "playwright",
    "playwright-core",
)
LIVE_E2E_MANIFEST_FINGERPRINT = ".live-e2e-package-manifest.sha256"
LIVE_E2E_OUTPUT_OWNER_MARKER = ".ue-live-e2e-output-owner"
LIVE_E2E_OUTPUT_OWNER_MARKER_CONTENT = "ue-live-playwright-output-v1\n"
STAND_PATHS_TO_PROTECT = (
    Path(OVERLAY),
    Path(IN_PLACE_OVERLAY),
    Path(".env"),
    Path(".env.docker"),
    Path(".env.docker.workers"),
    Path(".secrets"),
    STAND_FILE,
    VAPID_FILE,
    ADMIN_PASSWORD_FILE,
    Path(".secrets/jwt_rs256.pem"),
    Path(".secrets/jwt_rs256.pub.pem"),
    Path(".secrets/temporal_api_key"),
    Path(".secrets/s3-cutover-attestation.txt"),
)


class StandError(RuntimeError):
    """A precondition for operating the stand does not hold."""


@dataclass(frozen=True)
class StandOwner:
    """Validated identity of one dedicated Compose run."""

    repository: str
    worktree: str
    project_name: str
    published_ports: tuple[tuple[str, int], ...]
    schema_version: int
    daemon_fingerprint: str | None = None
    compose_resource_fingerprint: str | None = None
    resume_compose_resource_fingerprint: str | None = None
    resume_compose_resource_schema_version: int | None = None
    source_sha: str | None = None
    stack: str = LIVE_STACK_FULL
    service_roots: tuple[str, ...] = ()
    selected_services: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComposeResourceEvidence:
    """Canonical project resources in the resolved Compose model."""

    fingerprint: str
    managed_volumes: tuple[tuple[str, str], ...]
    declared_volume_names: tuple[str, ...] = ()
    managed_networks: tuple[tuple[str, str], ...] = ()
    managed_services: tuple[str, ...] = ()
    stack: str = LIVE_STACK_FULL
    service_roots: tuple[str, ...] = ()
    selected_services: tuple[str, ...] = ()
    network_bindings: tuple[tuple[str, str, bool], ...] = ()
    service_networks: tuple[tuple[str, tuple[str, ...]], ...] = ()
    service_mounts: tuple[tuple[str, tuple[tuple[str, str | None, str], ...]], ...] = ()


@dataclass(frozen=True)
class CoreContainerRecord:
    """Verified runtime identity and state for one selected Core container."""

    service: str
    identity: str
    running: bool
    status: str | None
    health: str | None


def _stand_base_url(published_ports: Mapping[str, int]) -> str:
    """Return the loopback URL served by the live stack's development Caddyfile."""
    # The live Compose overlay uses infrastructure/Caddyfile, which disables
    # automatic HTTPS and serves the app on port 80.
    return f"http://localhost:{published_ports['CADDY_HTTP']}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_vapid_keys() -> dict[str, str]:
    """Return a P-256 VAPID key pair in the Web Push base64url encoding."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    raw_private = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_point = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return {"public": _b64url(public_point), "private": _b64url(raw_private)}


def _path_is_reparse_point(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise StandError(f"cannot inspect path safety: {path}") from error

    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (
        stat.S_ISLNK(path_stat.st_mode)
        or getattr(path_stat, "st_file_attributes", 0) & reparse_flag
    ):
        return True

    is_junction = getattr(path, "is_junction", None)
    try:
        return bool(is_junction and is_junction())
    except OSError as error:
        raise StandError(f"cannot inspect path safety: {path}") from error


def _assert_no_reparse_ancestors(path: Path) -> None:
    for candidate in (path, *path.parents):
        if _path_is_reparse_point(candidate):
            raise StandError(f"refusing to use a reparse point: {candidate}")


def _validated_in_place_state_root(raw_path: str | Path, *, create: bool) -> Path:
    """Accept only one direct run directory under the owned system temp root."""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise StandError("in-place state directory must be an absolute owned temp path")
    try:
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        expected_parent = temporary_root / IN_PLACE_STATE_PARENT
        normalized = Path(os.path.abspath(candidate))
        parent = normalized.parent.resolve(strict=False)
        resolved = normalized.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise StandError("cannot validate the in-place state directory") from error
    repository_root = REPO_ROOT.resolve(strict=False)
    if (
        parent != expected_parent.resolve(strict=False)
        or resolved.parent != expected_parent.resolve(strict=False)
        or not IN_PLACE_STATE_PATTERN.fullmatch(normalized.name)
        or normalized == repository_root
        or normalized in repository_root.parents
        or repository_root in normalized.parents
    ):
        raise StandError(
            "in-place state directory must be a direct run child of the owned temporary root"
        )
    _assert_no_reparse_ancestors(expected_parent)
    _assert_no_reparse_ancestors(normalized)
    if normalized.exists() and not normalized.is_dir():
        raise StandError("in-place state path exists and is not a directory")
    if create:
        _ensure_private_state_directory(expected_parent)
        _assert_no_reparse_ancestors(expected_parent)
        if normalized.exists() and not (normalized / STAND_FILE).is_file():
            raise StandError("in-place state directory exists without an owner marker")
    elif not normalized.is_dir():
        raise StandError("owned in-place state directory does not exist")
    return normalized


def _windows_system32_executable(name: str, *, error_message: str) -> str:
    """Resolve a native ACL utility from the absolute Windows system directory."""
    if name not in {"whoami.exe", "icacls.exe"}:
        raise StandError(error_message)
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise StandError(error_message)
    root = Path(system_root)
    executable = root / "System32" / name
    try:
        if (
            not root.is_absolute()
            or not executable.is_absolute()
            or not executable.is_file()
        ):
            raise StandError(error_message)
        resolved = executable.resolve(strict=True)
    except (OSError, RuntimeError):
        raise StandError(error_message) from None
    if not resolved.is_absolute() or not resolved.is_file():
        raise StandError(error_message)
    return str(resolved)


def _windows_user_sid() -> str:
    """Return the current Windows user SID without exposing command output."""
    whoami = _windows_system32_executable(
        "whoami.exe",
        error_message="cannot verify the current Windows user for live state ACLs",
    )
    try:
        result = subprocess.run(  # noqa: S603 - fixed Windows identity query, no shell
            [whoami, "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        row = next(csv.reader(result.stdout.splitlines()))
    except (OSError, subprocess.SubprocessError, StopIteration, csv.Error):
        raise StandError(
            "cannot verify the current Windows user for live state ACLs"
        ) from None
    sid = row[-1].strip() if row else ""
    if not re.fullmatch(r"S-1-\d+(?:-\d+)+", sid):
        raise StandError("cannot verify the current Windows user for live state ACLs")
    return sid


def _restrict_new_windows_state_directory(path: Path) -> None:
    """Protect a newly created run root with only current-user and SYSTEM ACLs."""
    icacls = _windows_system32_executable(
        "icacls.exe",
        error_message="cannot enforce private Windows permissions for live state",
    )
    user_sid = _windows_user_sid()
    try:
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool, path is owned run root
            [icacls, str(path), "/reset"],
            check=True,
            capture_output=True,
            timeout=20,
        )
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool, SID is validated above
            [icacls, str(path), "/setowner", f"*{user_sid}"],
            check=True,
            capture_output=True,
            timeout=20,
        )
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool, SID/path are validated
            [
                icacls,
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{user_sid}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        raise StandError(
            "cannot enforce private Windows permissions for live state"
        ) from None


def _restrict_in_place_windows_state_file(path: Path) -> None:
    """Give a generated in-place state file the protected parent ACL and owner."""
    if not IN_PLACE_MODE or os.name != "nt":
        return
    state_root = Path(os.path.abspath(WORKTREE))
    candidate = Path(os.path.abspath(path))
    try:
        relative_path = candidate.relative_to(state_root)
    except ValueError as error:
        raise StandError(
            "generated live stand file escapes the owned state root"
        ) from error
    _assert_worktree_paths_safe(state_root, (relative_path,))
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise StandError(
            "cannot verify generated live stand file permissions"
        ) from error
    if not stat.S_ISREG(metadata.st_mode):
        raise StandError("generated live stand path is not a regular file")

    icacls = _windows_system32_executable(
        "icacls.exe",
        error_message="cannot enforce private Windows permissions for live state",
    )
    user_sid = _windows_user_sid()
    try:
        subprocess.run(  # noqa: S603 - fixed ACL tool, path is confined to owned state
            [icacls, str(candidate), "/reset"],
            check=True,
            capture_output=True,
            timeout=20,
        )
        subprocess.run(  # noqa: S603 - validated current-user SID and confined path
            [icacls, str(candidate), "/setowner", f"*{user_sid}"],
            check=True,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        raise StandError(
            "cannot enforce private Windows permissions for live state"
        ) from None


def _ensure_private_state_directory(
    path: Path,
    *,
    owner_verified: bool = False,
    protect_new_windows: bool = False,
) -> None:
    """Create an owned state directory with private POSIX permissions."""
    try:
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "nt":
            if protect_new_windows and not existed:
                _restrict_new_windows_state_directory(path)
            return
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise StandError("live stand state directory is not owned by this user")
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            if existed and not owner_verified:
                raise StandError("existing live stand state directory is not private")
            path.chmod(0o700)
    except (OSError, RuntimeError) as error:
        raise StandError("cannot secure live stand state directory") from error


def _assert_private_state_directory(path: Path) -> None:
    """Check POSIX ownership and privacy without changing existing permissions."""
    if os.name == "nt":
        return
    try:
        metadata = path.lstat()
    except OSError as error:
        raise StandError(
            "cannot verify live stand state directory permissions"
        ) from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise StandError("live stand state directory permissions are not private")


def _active_owner_schema_version() -> int:
    return IN_PLACE_OWNER_SCHEMA_VERSION if IN_PLACE_MODE else OWNER_SCHEMA_VERSION


def _is_active_owner_schema(schema_version: int) -> bool:
    return schema_version == _active_owner_schema_version()


def _owner_schema_is_supported(schema_version: int) -> bool:
    return schema_version in {
        LEGACY_OWNER_SCHEMA_VERSION,
        VOLUME_OWNER_SCHEMA_VERSION,
        PREVIOUS_OWNER_SCHEMA_VERSION,
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }


def _write_in_place_compose_override(state_root: Path) -> Path:
    """Redirect state and mount only the secrets each live service reads."""
    resolved_root = state_root.resolve(strict=True)
    repository = REPO_ROOT.resolve(strict=True)
    env_file = json.dumps((resolved_root / ".env.docker").as_posix())
    worker_env_file = json.dumps((resolved_root / ".env.docker.workers").as_posix())

    def readonly_bind(source: Path, target: str) -> str:
        return (
            "      - type: bind\n"
            f"        source: {json.dumps(source.as_posix())}\n"
            f"        target: {target}\n"
            "        read_only: true\n"
            "        bind:\n"
            "          create_host_path: false\n"
        )

    runtime_bind_directory = resolved_root / ".secrets"
    private_key_mount = readonly_bind(
        runtime_bind_directory / "jwt_rs256.pem", "/app/.secrets/jwt_rs256.pem"
    )
    public_key_mount = readonly_bind(
        runtime_bind_directory / "jwt_rs256.pub.pem", "/app/.secrets/jwt_rs256.pub.pem"
    )
    temporal_token_mount = readonly_bind(
        runtime_bind_directory / "temporal_api_key", "/app/.secrets/temporal_api_key"
    )
    temporal_config_mount = readonly_bind(
        repository / "services" / "temporal" / "config.yaml",
        "/etc/temporal/config/docker.yaml",
    )
    temporal_entrypoint_mount = readonly_bind(
        repository / "services" / "temporal" / "entrypoint.sh",
        "/etc/temporal/wave144-entrypoint.sh",
    )
    content = (
        "services:\n"
        "  backend:\n"
        f"    env_file: !override [{env_file}]\n"
        "    volumes: !override\n"
        "      - static-data:/app/app/static\n"
        f"{private_key_mount}"
        "  migrations:\n"
        f"    env_file: !override [{env_file}]\n"
        "  notifications-worker:\n"
        f"    env_file: !override [{worker_env_file}]\n"
        "  outbox-worker:\n"
        f"    env_file: !override [{worker_env_file}]\n"
        "  file-processor:\n"
        "    volumes: !override\n"
        f"{public_key_mount}"
        f"{temporal_token_mount}"
        "  temporal:\n"
        "    volumes: !override\n"
        f"{temporal_config_mount}"
        f"{temporal_entrypoint_mount}"
    )
    override = state_root / IN_PLACE_OVERLAY
    _assert_worktree_paths_safe(state_root, (Path(IN_PLACE_OVERLAY),))
    override.write_text(content, encoding="utf-8")
    if IN_PLACE_MODE and os.name == "nt":
        _restrict_in_place_windows_state_file(override)
    elif os.name != "nt":
        override.chmod(0o600)
    return override


def _assert_worktree_paths_safe(worktree: Path, relative_paths: Sequence[Path]) -> None:
    root = Path(os.path.abspath(worktree))
    _assert_no_reparse_ancestors(root)
    for relative_path in relative_paths:
        if relative_path.is_absolute():
            raise StandError("stand safety paths must remain relative to the worktree")
        candidate = Path(os.path.abspath(root / relative_path))
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise StandError("stand safety path escapes the owned worktree") from error
        _assert_no_reparse_ancestors(candidate)


def _assert_stand_paths_safe(worktree: Path) -> None:
    _assert_worktree_paths_safe(worktree, STAND_PATHS_TO_PROTECT)


def load_or_create_vapid(worktree: Path) -> dict[str, str]:
    path = worktree / VAPID_FILE
    _assert_worktree_paths_safe(worktree, (VAPID_FILE,))
    if path.is_file():
        return load_vapid(worktree)
    keys = generate_vapid_keys()
    if IN_PLACE_MODE:
        _ensure_private_state_directory(path.parent, protect_new_windows=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as key_file:
            key_file.write(json.dumps(keys))
        if IN_PLACE_MODE and os.name == "nt":
            _restrict_in_place_windows_state_file(path)
        elif os.name != "nt":
            path.chmod(0o600)
    except FileExistsError:
        return load_vapid(worktree)
    return keys


def load_vapid(worktree: Path) -> dict[str, str]:
    """Read existing VAPID keys without creating or changing local files."""
    path = worktree / VAPID_FILE
    _assert_worktree_paths_safe(worktree, (VAPID_FILE,))
    if not path.is_file():
        raise StandError(
            f"missing or unsafe VAPID key file: {path}; run `live_stand.py up`"
        )
    try:
        keys = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StandError(f"cannot read VAPID key pair from {path}") from error
    if (
        not isinstance(keys, dict)
        or set(keys) != {"public", "private"}
        or not all(isinstance(value, str) and value for value in keys.values())
    ):
        raise StandError(f"{path} does not hold a VAPID key pair")
    return {"public": keys["public"], "private": keys["private"]}


def _read_stand_admin_password(worktree: Path, path: Path, owner: StandOwner) -> str:
    _assert_worktree_paths_safe(worktree, (ADMIN_PASSWORD_FILE,))
    if not path.is_file():
        raise StandError(
            "owner-scoped live stand admin credential is missing or unsafe"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise StandError(
            "cannot read owner-scoped live stand admin credential"
        ) from None
    if not isinstance(payload, dict):
        raise StandError("admin credential belongs to a different live stand")
    password = payload.get("password")
    if (
        set(payload) != {"version", "project_name", "password"}
        or payload.get("version") != 1
        or payload.get("project_name") != owner.project_name
        or not isinstance(password, str)
        or len(password) < 32
        or len(password) > 128
    ):
        raise StandError("admin credential belongs to a different live stand")
    return password


def load_or_create_stand_admin_password(worktree: Path, owner: StandOwner) -> str:
    """Reuse one protected synthetic admin password for this verified stand."""
    _assert_worktree_paths_safe(worktree, (ADMIN_PASSWORD_FILE,))
    try:
        repository = Path(owner.repository).resolve(strict=True)
        current_repository = REPO_ROOT.resolve(strict=True)
        owned_worktree = Path(owner.worktree).resolve(strict=True)
        current_worktree = _expected_worktree(worktree)
    except (OSError, RuntimeError):
        raise StandError("cannot verify live stand credential ownership") from None
    if repository != current_repository or owned_worktree != current_worktree:
        raise StandError("admin credential owner does not match the live stand")
    _validate_project_name(owner.project_name)

    path = worktree / ADMIN_PASSWORD_FILE
    if path.exists():
        return _read_stand_admin_password(worktree, path, owner)

    if IN_PLACE_MODE:
        _ensure_private_state_directory(path.parent, protect_new_windows=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    _assert_worktree_paths_safe(worktree, (ADMIN_PASSWORD_FILE,))
    password = _new_test_password()
    payload = {
        "version": 1,
        "project_name": owner.project_name,
        "password": password,
    }
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        _assert_worktree_paths_safe(worktree, (ADMIN_PASSWORD_FILE,))
        return _read_stand_admin_password(worktree, path, owner)
    except OSError:
        raise StandError(
            "cannot create owner-scoped live stand admin credential"
        ) from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as password_file:
            json.dump(payload, password_file, sort_keys=True)
            password_file.write("\n")
        if IN_PLACE_MODE and os.name == "nt":
            _restrict_in_place_windows_state_file(path)
        elif os.name != "nt":
            path.chmod(0o600)
    except OSError:
        raise StandError(
            "cannot persist owner-scoped live stand admin credential"
        ) from None
    return password


def _git_common_directory() -> Path:
    """Resolve the repository's common Git metadata directory."""
    git_entry = REPO_ROOT / ".git"
    try:
        if git_entry.is_dir():
            git_directory = git_entry
        elif git_entry.is_file():
            git_file = git_entry.read_text(encoding="utf-8").strip()
            if not git_file.startswith("gitdir:"):
                raise StandError(f"invalid Git metadata pointer: {git_entry}")
            raw_git_directory = Path(git_file.partition(":")[2].strip())
            git_directory = (
                raw_git_directory
                if raw_git_directory.is_absolute()
                else REPO_ROOT / raw_git_directory
            )
            git_directory = git_directory.resolve(strict=True)
            common_directory_file = git_directory / "commondir"
            if common_directory_file.is_file():
                raw_common_directory = Path(
                    common_directory_file.read_text(encoding="utf-8").strip()
                )
                git_directory = (
                    raw_common_directory
                    if raw_common_directory.is_absolute()
                    else git_directory / raw_common_directory
                )
        else:
            raise StandError(f"Git metadata is missing: {git_entry}")
        result = git_directory.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise StandError("cannot resolve the common Git metadata directory") from error
    if not result.is_dir():
        raise StandError("the common Git metadata path is not a directory")
    return result


def _owner_signing_key(*, create: bool) -> bytes:
    """Read or create the owner HMAC key in the mode-specific private root."""
    key_path = (
        WORKTREE / ".secrets" / "live-stand-owner.key"
        if IN_PLACE_MODE
        else _git_common_directory() / "live-stand-owner.key"
    )
    _assert_no_reparse_ancestors(key_path)
    if key_path.is_file():
        key = key_path.read_bytes()
    elif create:
        key = secrets.token_bytes(32)
        try:
            descriptor = os.open(
                key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            _assert_no_reparse_ancestors(key_path)
            if not key_path.is_file():
                raise StandError("unsafe live stand owner key file") from None
            key = key_path.read_bytes()
        else:
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(key)
            if IN_PLACE_MODE and os.name == "nt":
                _restrict_in_place_windows_state_file(key_path)
            elif os.name != "nt":
                key_path.chmod(0o600)
    else:
        raise StandError("missing live stand owner key")
    if len(key) != 32:
        raise StandError("invalid live stand owner key in Git metadata")
    return key


def _owner_signature(payload: dict[str, object], key: bytes) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def docker_daemon_fingerprint(
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> str:
    """Return a stable, non-secret fingerprint for the selected Docker daemon."""
    try:
        if deadline is not None:
            if docker_context is None:
                raise StandError("cannot verify Docker daemon identity")
            command = _live_docker_command(
                ["docker", "info", "--format", "{{.ID}}"], docker_context
            )
            result = _run_live_bounded_read(
                command,
                context=docker_context,
                deadline=deadline,
                maximum_bytes=4096,
                command_timeout_seconds=_LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS,
            )
            if result.returncode != 0 or result.stderr:
                raise StandError("cannot verify Docker daemon identity")
            stdout = (result.stdout or b"").decode("utf-8", errors="strict")
        else:
            stdout = _docker_output(
                ["info", "--format", "{{.ID}}"],
                "cannot verify Docker daemon identity",
                docker_context=docker_context,
            )
    except (
        OSError,
        RuntimeError,
        StandError,
        UnicodeError,
        subprocess.SubprocessError,
    ) as error:
        raise StandError("cannot verify Docker daemon identity") from error
    daemon_id = stdout.strip()
    if not daemon_id:
        raise StandError("cannot verify Docker daemon identity")
    return hashlib.sha256(daemon_id.encode("utf-8")).hexdigest()


def _require_owned_docker_daemon(
    owner: StandOwner,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> None:
    if owner.daemon_fingerprint is None:
        raise StandError(
            "cannot verify Docker daemon ownership for this stand; refusing lifecycle command"
        )
    current_fingerprint = docker_daemon_fingerprint(
        deadline=deadline, docker_context=docker_context
    )
    if not hmac.compare_digest(current_fingerprint, owner.daemon_fingerprint):
        raise StandError("different Docker daemon detected; refusing lifecycle command")


def _validate_port_map(
    ports: Mapping[str, object],
    expected: Sequence[str],
    *,
    allow_privileged: bool,
) -> tuple[tuple[str, int], ...]:
    if set(ports) != set(expected):
        raise StandError("live port map does not match the published service inventory")
    result: list[tuple[str, int]] = []
    for name in expected:
        port = ports[name]
        minimum = 1 if allow_privileged else 1024
        if type(port) is not int or not minimum <= port <= 65535:
            raise StandError(
                f"invalid host port for {name}: expected an unprivileged TCP port"
            )
        result.append((name, port))
    if len({port for _name, port in result}) != len(result):
        raise StandError("live port map contains duplicate host ports")
    return tuple(result)


def _validate_published_ports(
    ports: Mapping[str, object], *, allow_privileged: bool = False
) -> tuple[tuple[str, int], ...]:
    expected = tuple(name for name, _service, _target in LIVE_PORT_SPECS)
    return _validate_port_map(ports, expected, allow_privileged=allow_privileged)


def _validate_pre_minio_published_ports(
    ports: Mapping[str, object], *, allow_privileged: bool = False
) -> tuple[tuple[str, int], ...]:
    return _validate_port_map(
        ports, PRE_MINIO_PUBLISHED_PORT_NAMES, allow_privileged=allow_privileged
    )


def _published_port_names_for_services(
    selected_services: Sequence[str],
) -> tuple[str, ...]:
    selected = set(selected_services)
    if not selected:
        raise StandError("live stack has no selected services for published ports")
    known_services = set(LIVE_CORE_EXPECTED_SERVICES) | {
        service for _name, service, _port in LIVE_PORT_SPECS
    }
    if not selected.issubset(known_services):
        raise StandError("live stack selection contains an unknown published service")
    return tuple(
        name
        for name, service, _container_port in LIVE_PORT_SPECS
        if service in selected
    )


def _selected_published_ports(
    published_ports: Mapping[str, int], selected_services: Sequence[str]
) -> dict[str, int]:
    ports = dict(_validate_published_ports(published_ports, allow_privileged=True))
    names = _published_port_names_for_services(selected_services)
    return {name: ports[name] for name in names}


def choose_published_ports(
    *, active_services: Sequence[str] | None = None
) -> dict[str, int]:
    """Choose free active ports and inert unique values for unused Compose inputs.

    The live overlay must receive every port variable while Compose resolves its
    full model. A bounded Core start only binds the ports for its signed service
    closure; inactive values are interpolation placeholders and are not probed
    or reserved.
    """
    low, high = PORT_RANGE
    chosen: dict[str, int] = {}
    active_names = (
        tuple(name for name, _service, _port in LIVE_PORT_SPECS)
        if active_services is None
        else _published_port_names_for_services(active_services)
    )
    active_set = set(active_names)
    for name in active_names:
        for _attempt in range(1000):
            port = low + secrets.randbelow(high - low + 1)
            if port in chosen.values():
                continue
            if port_is_free(port, host=PORT_BIND_HOST):
                chosen[name] = port
                break
        else:
            raise StandError(f"could not allocate a free loopback port for {name}")
    placeholder = low
    for name, _service, _container_port in LIVE_PORT_SPECS:
        if name in active_set:
            continue
        while placeholder in chosen.values():
            placeholder += 1
        if placeholder > high:
            raise StandError("could not allocate unique Compose interpolation ports")
        chosen[name] = placeholder
        placeholder += 1
    return {name: chosen[name] for name, _service, _container_port in LIVE_PORT_SPECS}


@contextmanager
def stand_lifecycle_lock() -> Iterator[None]:
    """Serialize lifecycle and data operations for this stand worktree."""
    lock_name = WORKTREE.name if IN_PLACE_MODE else WORKTREE_NAME
    lock_path = WORKTREE.parent / f".{lock_name}.lifecycle.lock"
    _assert_no_reparse_ancestors(lock_path)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise StandError(
            f"cannot open the live stand lifecycle lock: {lock_path}"
        ) from error

    with os.fdopen(descriptor, "r+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            if os.fstat(lock_file.fileno()).st_size == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EDEADLK, errno.EAGAIN}:
                        raise StandError(
                            "cannot acquire the live stand lifecycle lock"
                        ) from error
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _validate_project_name(project_name: str) -> None:
    if not PROJECT_PATTERN.fullmatch(project_name):
        raise StandError(f"refusing unexpected Compose project name {project_name!r}")


def _expected_worktree(worktree: Path) -> Path:
    _assert_no_reparse_ancestors(worktree)
    try:
        candidate = worktree.resolve(strict=False)
        expected = WORKTREE.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise StandError("cannot resolve the live stand worktree path") from error
    if worktree.is_symlink() or candidate != expected:
        raise StandError(f"refusing unexpected worktree path {worktree}")
    return candidate


def create_stand_owner(
    worktree: Path,
    *,
    published_ports: Mapping[str, int] | None = None,
    stack: str = LIVE_STACK_FULL,
) -> StandOwner:
    """Create an incomplete signed owner reservation for a new worktree."""
    expected_worktree = _expected_worktree(worktree)
    if not expected_worktree.is_dir():
        raise StandError(f"stand worktree does not exist: {worktree}")
    _assert_worktree_paths_safe(worktree, (Path(".secrets"), STAND_FILE))
    daemon_fingerprint = docker_daemon_fingerprint()
    marker = worktree / STAND_FILE
    if marker.is_symlink() or marker.exists():
        raise StandError(f"ownership metadata already exists or is unsafe: {marker}")
    try:
        repository = str(REPO_ROOT.resolve(strict=True))
    except (OSError, RuntimeError) as error:
        raise StandError(
            "cannot resolve the repository path for the live stand"
        ) from error
    project_name = f"{PROJECT_PREFIX}{secrets.token_hex(8)}"
    _validate_project_name(project_name)
    if stack not in LIVE_STACKS:
        raise StandError("unsupported live stand stack selection")
    default_services = LIVE_CORE_EXPECTED_SERVICES if stack == LIVE_STACK_CORE else None
    if published_ports is None:
        generated_ports = (
            choose_published_ports()
            if default_services is None
            else choose_published_ports(active_services=default_services)
        )
        published_ports = generated_ports
    port_map = _validate_published_ports(published_ports)
    service_roots = LIVE_CORE_SERVICE_ROOTS if stack == LIVE_STACK_CORE else ()
    schema_version = _active_owner_schema_version()
    source_sha = SOURCE_SHA if IN_PLACE_MODE else None
    if IN_PLACE_MODE and (
        source_sha is None or not re.fullmatch(r"[0-9a-f]{40}", source_sha)
    ):
        raise StandError("in-place owner requires the exact checked-out source SHA")
    owner = StandOwner(
        repository=repository,
        worktree=str(expected_worktree),
        project_name=project_name,
        published_ports=port_map,
        schema_version=schema_version,
        daemon_fingerprint=daemon_fingerprint,
        compose_resource_fingerprint=None,
        resume_compose_resource_fingerprint=None,
        source_sha=source_sha,
        stack=stack,
        service_roots=service_roots,
        selected_services=(),
    )
    payload = {
        "version": schema_version,
        "repository": owner.repository,
        "worktree": owner.worktree,
        "project_name": owner.project_name,
        "published_ports": dict(owner.published_ports),
        "daemon_fingerprint": daemon_fingerprint,
        "compose_resource_fingerprint": None,
        "resume_compose_resource_fingerprint": None,
        "resume_compose_resource_schema_version": None,
        "stack": stack,
        "service_roots": list(service_roots),
        "selected_services": [],
    }
    if source_sha is not None:
        payload["source_sha"] = source_sha
    if IN_PLACE_MODE:
        _ensure_private_state_directory(worktree / ".secrets", protect_new_windows=True)
    else:
        (worktree / ".secrets").mkdir(parents=True, exist_ok=True)
    marker_data = {
        **payload,
        "signature": _owner_signature(payload, _owner_signing_key(create=True)),
    }
    try:
        with marker.open("x", encoding="utf-8") as marker_file:
            marker_file.write(json.dumps(marker_data, indent=2) + "\n")
        if IN_PLACE_MODE and os.name == "nt":
            _restrict_in_place_windows_state_file(marker)
        elif os.name != "nt":
            marker.chmod(0o600)
    except FileExistsError as error:
        raise StandError(f"ownership metadata already exists: {marker}") from error
    return owner


def load_stand_owner(worktree: Path) -> StandOwner:
    """Load and validate an existing stand marker without mutating it."""
    expected_worktree = _expected_worktree(worktree)
    _assert_worktree_paths_safe(worktree, (Path(".secrets"), STAND_FILE))
    marker = worktree / STAND_FILE
    if marker.is_symlink() or not marker.is_file():
        raise StandError(
            f"missing or unsafe ownership metadata: {marker}; run `live_stand.py up`"
        )
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StandError(f"cannot read ownership metadata: {marker}") from error
    if not isinstance(data, dict):
        raise StandError(f"invalid ownership metadata: {marker}")
    schema_version = data.get("version")
    legacy_keys = {"version", "repository", "worktree", "project_name", "signature"}
    volume_keys = legacy_keys | {"published_ports"}
    daemon_keys = volume_keys | {"daemon_fingerprint"}
    resource_keys = daemon_keys | {"compose_resource_fingerprint"}
    resumable_resource_keys = resource_keys | {"resume_compose_resource_fingerprint"}
    in_place_resource_keys = resumable_resource_keys | {"source_sha"}
    stack_resource_keys = resumable_resource_keys | {
        "resume_compose_resource_schema_version",
        "stack",
        "service_roots",
        "selected_services",
    }
    in_place_stack_keys = stack_resource_keys | {"source_sha"}
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or (schema_version == LEGACY_OWNER_SCHEMA_VERSION and set(data) != legacy_keys)
        or (schema_version == VOLUME_OWNER_SCHEMA_VERSION and set(data) != volume_keys)
        or (
            schema_version == PREVIOUS_OWNER_SCHEMA_VERSION and set(data) != daemon_keys
        )
        or (
            schema_version == PREVIOUS_STACK_OWNER_SCHEMA_VERSION
            and set(data) not in (resource_keys, resumable_resource_keys)
        )
        or (
            schema_version == RESOURCE_OWNER_SCHEMA_VERSION
            and set(data) not in (resource_keys, resumable_resource_keys)
        )
        or (
            schema_version == PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION
            and (
                not IN_PLACE_MODE
                or set(data) != in_place_resource_keys
                or not isinstance(data.get("source_sha"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", data["source_sha"])
            )
        )
        or (
            schema_version == PRE_MINIO_OWNER_SCHEMA_VERSION
            and (IN_PLACE_MODE or set(data) != stack_resource_keys)
        )
        or (
            schema_version == PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION
            and (
                not IN_PLACE_MODE
                or set(data) != in_place_stack_keys
                or not isinstance(data.get("source_sha"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", data["source_sha"])
            )
        )
        or (
            schema_version == OWNER_SCHEMA_VERSION
            and (IN_PLACE_MODE or set(data) != stack_resource_keys)
        )
        or (
            schema_version == IN_PLACE_OWNER_SCHEMA_VERSION
            and (
                not IN_PLACE_MODE
                or set(data) != in_place_stack_keys
                or not isinstance(data.get("source_sha"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", data["source_sha"])
            )
        )
        or not _owner_schema_is_supported(schema_version)
        or not all(
            isinstance(data.get(key), str)
            for key in ("repository", "worktree", "project_name")
        )
    ):
        raise StandError(f"invalid ownership metadata: {marker}")
    if schema_version in {
        VOLUME_OWNER_SCHEMA_VERSION,
        PREVIOUS_OWNER_SCHEMA_VERSION,
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        raw_ports = data["published_ports"]
        if not isinstance(raw_ports, dict):
            raise StandError(f"invalid ownership metadata: {marker}")
        if schema_version in {
            VOLUME_OWNER_SCHEMA_VERSION,
            PREVIOUS_OWNER_SCHEMA_VERSION,
            RESOURCE_OWNER_SCHEMA_VERSION,
            PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
            PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
            PRE_MINIO_OWNER_SCHEMA_VERSION,
            PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        }:
            try:
                port_map = dict(_validate_pre_minio_published_ports(raw_ports))
            except StandError:
                if schema_version in {
                    PRE_MINIO_OWNER_SCHEMA_VERSION,
                    PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
                }:
                    raise StandError(f"invalid ownership metadata: {marker}") from None
                raise
        else:
            port_map = dict(_validate_published_ports(raw_ports))
    else:
        port_map = LEGACY_PUBLISHED_PORTS.copy()
    daemon_fingerprint: str | None = None
    if schema_version in {
        PREVIOUS_OWNER_SCHEMA_VERSION,
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        raw_fingerprint = data["daemon_fingerprint"]
        if not isinstance(
            raw_fingerprint, str
        ) or not DAEMON_FINGERPRINT_PATTERN.fullmatch(raw_fingerprint):
            raise StandError(
                f"invalid Docker daemon fingerprint in ownership metadata: {marker}"
            )
        daemon_fingerprint = raw_fingerprint
    compose_resource_fingerprint: str | None = None
    resume_compose_resource_fingerprint: str | None = None
    resume_compose_resource_schema_version: int | None = None
    if schema_version in {
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        raw_resource_fingerprint = data["compose_resource_fingerprint"]
        if raw_resource_fingerprint is not None and (
            not isinstance(raw_resource_fingerprint, str)
            or not DAEMON_FINGERPRINT_PATTERN.fullmatch(raw_resource_fingerprint)
        ):
            raise StandError(
                f"invalid Compose resource fingerprint in ownership metadata: {marker}"
            )
        compose_resource_fingerprint = raw_resource_fingerprint
        if "resume_compose_resource_fingerprint" in data:
            raw_resume_fingerprint = data["resume_compose_resource_fingerprint"]
            if raw_resume_fingerprint is not None and (
                not isinstance(raw_resume_fingerprint, str)
                or not DAEMON_FINGERPRINT_PATTERN.fullmatch(raw_resume_fingerprint)
            ):
                raise StandError(
                    "invalid resumable Compose resource fingerprint in ownership metadata"
                )
            resume_compose_resource_fingerprint = raw_resume_fingerprint
            if schema_version in {
                PRE_MINIO_OWNER_SCHEMA_VERSION,
                PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
                OWNER_SCHEMA_VERSION,
                IN_PLACE_OWNER_SCHEMA_VERSION,
            }:
                raw_resume_schema = data.get("resume_compose_resource_schema_version")
                valid_resume_schemas = {
                    RESOURCE_OWNER_SCHEMA_VERSION,
                    PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
                    PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
                    PRE_MINIO_OWNER_SCHEMA_VERSION,
                    PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
                }
                if schema_version in {
                    OWNER_SCHEMA_VERSION,
                    IN_PLACE_OWNER_SCHEMA_VERSION,
                }:
                    valid_resume_schemas.update(
                        {OWNER_SCHEMA_VERSION, IN_PLACE_OWNER_SCHEMA_VERSION}
                    )
                if raw_resume_schema is not None and (
                    not isinstance(raw_resume_schema, int)
                    or isinstance(raw_resume_schema, bool)
                    or raw_resume_schema not in valid_resume_schemas
                ):
                    raise StandError(
                        "invalid resumable Compose resource schema in ownership metadata"
                    )
                resume_compose_resource_schema_version = raw_resume_schema
                if (raw_resume_fingerprint is None) != (raw_resume_schema is None):
                    raise StandError(
                        "resumable Compose fingerprint and schema must be present together"
                    )
            else:
                resume_compose_resource_schema_version = (
                    schema_version if raw_resume_fingerprint is not None else None
                )
            if (
                compose_resource_fingerprint is not None
                and resume_compose_resource_fingerprint is not None
            ):
                raise StandError(
                    "ownership metadata cannot contain active and resumable Compose evidence"
                )
    source_sha = (
        data.get("source_sha")
        if schema_version
        in {
            PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
            PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
            IN_PLACE_OWNER_SCHEMA_VERSION,
        }
        else None
    )
    try:
        marker_repository = Path(data["repository"]).resolve(strict=False)
        expected_repository = REPO_ROOT.resolve(strict=True)
        marker_worktree = Path(data["worktree"]).resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise StandError(f"invalid paths in ownership metadata: {marker}") from error
    if marker_worktree != expected_worktree:
        raise StandError("ownership metadata belongs to another worktree")
    if marker_repository != expected_repository:
        raise StandError("ownership metadata belongs to another repository")
    project_name = data["project_name"]
    _validate_project_name(project_name)
    payload = {
        "version": data["version"],
        "repository": data["repository"],
        "worktree": data["worktree"],
        "project_name": project_name,
    }
    if schema_version in {
        VOLUME_OWNER_SCHEMA_VERSION,
        PREVIOUS_OWNER_SCHEMA_VERSION,
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        payload["published_ports"] = port_map
    if schema_version in {
        PREVIOUS_OWNER_SCHEMA_VERSION,
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        payload["daemon_fingerprint"] = daemon_fingerprint
    if schema_version in {
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        payload["compose_resource_fingerprint"] = compose_resource_fingerprint
        if "resume_compose_resource_fingerprint" in data:
            payload["resume_compose_resource_fingerprint"] = (
                resume_compose_resource_fingerprint
            )
            if schema_version in {
                PRE_MINIO_OWNER_SCHEMA_VERSION,
                PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
                OWNER_SCHEMA_VERSION,
                IN_PLACE_OWNER_SCHEMA_VERSION,
            }:
                payload["resume_compose_resource_schema_version"] = (
                    resume_compose_resource_schema_version
                )
    if schema_version in {
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        stack = data.get("stack")
        raw_roots = data.get("service_roots")
        raw_selected = data.get("selected_services")
        if (
            stack not in LIVE_STACKS
            or not isinstance(raw_roots, list)
            or not isinstance(raw_selected, list)
            or any(
                not isinstance(name, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)
                for name in (*raw_roots, *raw_selected)
            )
            or raw_roots != sorted(set(raw_roots))
            or raw_selected != sorted(set(raw_selected))
        ):
            raise StandError("invalid live stack selection in ownership metadata")
        if stack == LIVE_STACK_CORE and raw_roots != list(LIVE_CORE_SERVICE_ROOTS):
            raise StandError("live Core ownership has unexpected service roots")
        if compose_resource_fingerprint is not None and not raw_selected:
            raise StandError("complete live ownership lacks selected services")
        if compose_resource_fingerprint is None:
            expected_incomplete_roots = (
                list(LIVE_CORE_SERVICE_ROOTS) if stack == LIVE_STACK_CORE else []
            )
            if raw_roots != expected_incomplete_roots or raw_selected:
                raise StandError(
                    "incomplete live ownership contains a service selection"
                )
        if stack == LIVE_STACK_CORE and raw_selected not in (
            [],
            list(LIVE_CORE_EXPECTED_SERVICES),
        ):
            raise StandError("live Core ownership has an unexpected service closure")
        if (
            stack == LIVE_STACK_FULL
            and compose_resource_fingerprint is not None
            and (raw_roots != raw_selected)
        ):
            raise StandError("full-stack service roots and selection do not match")
        service_roots = tuple(raw_roots)
        selected_services = tuple(raw_selected)
        payload["stack"] = stack
        payload["service_roots"] = list(service_roots)
        payload["selected_services"] = list(selected_services)
    else:
        # Historical owner schemas predate stack selection and always describe
        # the original full Compose model.
        stack = LIVE_STACK_FULL
        service_roots = ()
        selected_services = ()
    if schema_version in {
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        payload["source_sha"] = source_sha
    signature = data["signature"]
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, _owner_signature(payload, _owner_signing_key(create=False))
    ):
        if schema_version in {
            PRE_MINIO_OWNER_SCHEMA_VERSION,
            PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
        }:
            raise StandError(f"invalid ownership metadata: {marker}") from None
        raise StandError("ownership metadata signature is invalid")
    if schema_version in {
        PRE_MINIO_OWNER_SCHEMA_VERSION,
        PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        raise StandError(
            f"live stand ownership uses pre-MINIO schema {schema_version}; preserve its data and use the matching previous live_stand.py CLI for stop/teardown before upgrading this stand"
        )
    return StandOwner(
        repository=str(marker_repository),
        worktree=str(marker_worktree),
        project_name=project_name,
        published_ports=tuple(port_map.items()),
        schema_version=schema_version,
        daemon_fingerprint=daemon_fingerprint,
        compose_resource_fingerprint=compose_resource_fingerprint,
        resume_compose_resource_fingerprint=resume_compose_resource_fingerprint,
        resume_compose_resource_schema_version=resume_compose_resource_schema_version,
        source_sha=source_sha,
        stack=stack,
        service_roots=service_roots,
        selected_services=selected_services,
    )


def verify_live_endpoints(base_url: str, mailpit_url: str) -> None:
    """Verify supplied URLs exactly match the signed live-stand port map."""
    try:
        owner = load_stand_owner(WORKTREE)
        if owner.schema_version == LEGACY_OWNER_SCHEMA_VERSION:
            raise StandError("ownership metadata does not sign a current port map")
        if (
            owner.schema_version
            in {
                RESOURCE_OWNER_SCHEMA_VERSION,
                PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
                PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
                OWNER_SCHEMA_VERSION,
                IN_PLACE_OWNER_SCHEMA_VERSION,
            }
            and owner.compose_resource_fingerprint is None
        ):
            raise StandError("live stand startup is incomplete")
        published = dict(owner.published_ports)
        expected_base_url = _stand_base_url(published)
        expected_mailpit_url = f"http://127.0.0.1:{published['MAILPIT']}"
        if base_url != expected_base_url or mailpit_url != expected_mailpit_url:
            raise StandError("endpoint URLs do not match the signed port map")
        if IN_PLACE_MODE:
            _assert_in_place_source_current(owner)
    except StandError:
        # Do not disclose marker paths, ports, project names, or signature
        # details through the Playwright launcher.
        raise StandError("live stand endpoint ownership verification failed") from None


def update_stand_owner_ports(
    worktree: Path,
    owner: StandOwner,
    published_ports: Mapping[str, int],
) -> StandOwner:
    """Sign a new port map and invalidate resource evidence before re-preparing."""
    current = load_stand_owner(worktree)
    if current != owner:
        raise StandError("ownership metadata changed before port map update")
    ports = _validate_published_ports(published_ports)
    if current.daemon_fingerprint is None:
        raise StandError("cannot verify Docker daemon ownership before port map update")
    updated = StandOwner(
        repository=current.repository,
        worktree=current.worktree,
        project_name=current.project_name,
        published_ports=ports,
        schema_version=_active_owner_schema_version(),
        daemon_fingerprint=current.daemon_fingerprint,
        compose_resource_fingerprint=None,
        resume_compose_resource_fingerprint=(
            current.compose_resource_fingerprint
            or current.resume_compose_resource_fingerprint
        ),
        resume_compose_resource_schema_version=(
            current.schema_version
            if current.compose_resource_fingerprint is not None
            else current.resume_compose_resource_schema_version
        ),
        source_sha=SOURCE_SHA if IN_PLACE_MODE else None,
        stack=current.stack,
        service_roots=(
            LIVE_CORE_SERVICE_ROOTS if current.stack == LIVE_STACK_CORE else ()
        ),
        selected_services=(),
    )
    return _write_stand_owner_update(worktree, updated)


def _write_stand_owner_update(worktree: Path, updated: StandOwner) -> StandOwner:
    """Atomically sign a version-five owner update, including incomplete reservations."""
    if updated.schema_version not in {
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        raise StandError("cannot write an unsupported live stand owner version")
    if updated.daemon_fingerprint is None:
        raise StandError("cannot sign live stand ownership without a daemon identity")
    payload: dict[str, object] = {
        "version": updated.schema_version,
        "repository": updated.repository,
        "worktree": updated.worktree,
        "project_name": updated.project_name,
        "published_ports": dict(updated.published_ports),
        "daemon_fingerprint": updated.daemon_fingerprint,
        "compose_resource_fingerprint": updated.compose_resource_fingerprint,
        "resume_compose_resource_fingerprint": (
            updated.resume_compose_resource_fingerprint
        ),
        "resume_compose_resource_schema_version": (
            updated.resume_compose_resource_schema_version
        ),
        "stack": updated.stack,
        "service_roots": list(updated.service_roots),
        "selected_services": list(updated.selected_services),
    }
    if updated.schema_version == IN_PLACE_OWNER_SCHEMA_VERSION:
        if updated.source_sha is None or not re.fullmatch(
            r"[0-9a-f]{40}", updated.source_sha
        ):
            raise StandError("cannot sign in-place ownership without its source SHA")
        payload["source_sha"] = updated.source_sha
    marker_data = {
        **payload,
        "signature": _owner_signature(payload, _owner_signing_key(create=False)),
    }
    marker = worktree / STAND_FILE
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=marker.parent,
            prefix=".live-stand-",
            suffix=".tmp",
            delete=False,
        ) as marker_file:
            temporary_path = Path(marker_file.name)
            marker_file.write(json.dumps(marker_data, indent=2) + "\n")
            marker_file.flush()
            os.fsync(marker_file.fileno())
        _assert_worktree_paths_safe(
            worktree, (STAND_FILE, temporary_path.relative_to(worktree))
        )
        if IN_PLACE_MODE and os.name == "nt":
            _restrict_in_place_windows_state_file(temporary_path)
        elif os.name != "nt":
            temporary_path.chmod(0o600)
        os.replace(temporary_path, marker)
        temporary_path = None
    except OSError as error:
        raise StandError("cannot atomically update live stand ownership") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return updated


def _owner_compose_resource_evidence(
    worktree: Path,
    owner: StandOwner,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> ComposeResourceEvidence:
    if owner.schema_version in {
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        return _compose_resource_evidence(
            worktree,
            owner.project_name,
            dict(owner.published_ports),
            legacy_projection=True,
            deadline=deadline,
            docker_context=docker_context,
        )
    if owner.stack == LIVE_STACK_FULL:
        return _compose_resource_evidence(
            worktree,
            owner.project_name,
            dict(owner.published_ports),
            deadline=deadline,
            docker_context=docker_context,
        )
    return _compose_resource_evidence(
        worktree,
        owner.project_name,
        dict(owner.published_ports),
        stack=owner.stack,
        service_roots=owner.service_roots,
        deadline=deadline,
        docker_context=docker_context,
    )


def _resume_compose_resource_evidence(
    worktree: Path, owner: StandOwner
) -> ComposeResourceEvidence:
    """Resolve the projection version recorded with an incomplete resume hash."""
    schema_version = owner.resume_compose_resource_schema_version
    if schema_version is None or owner.resume_compose_resource_fingerprint is None:
        raise StandError("live stand has no verifiable resume evidence")
    if schema_version in {
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        return _compose_resource_evidence(
            worktree,
            owner.project_name,
            dict(owner.published_ports),
            legacy_projection=True,
        )
    if schema_version not in {OWNER_SCHEMA_VERSION, IN_PLACE_OWNER_SCHEMA_VERSION}:
        raise StandError("unsupported Compose resume evidence schema")
    return _owner_compose_resource_evidence(worktree, owner)


def _bind_stand_owner_compose_resources(
    worktree: Path,
    owner: StandOwner,
    *,
    allow_existing_owned_volumes: bool = False,
) -> StandOwner:
    """Bind resolved Compose resources to an incomplete signed reservation."""
    current = load_stand_owner(worktree)
    if current != owner:
        raise StandError(
            "ownership metadata changed before Compose resource registration"
        )
    if not _is_active_owner_schema(current.schema_version):
        raise StandError(
            "cannot register Compose resources for legacy ownership metadata"
        )
    if current.compose_resource_fingerprint is not None:
        raise StandError("Compose resources are already registered for this stand")
    _require_owned_docker_daemon(current)
    evidence = _owner_compose_resource_evidence(worktree, current)
    if current.resume_compose_resource_fingerprint is not None:
        resume_evidence = _resume_compose_resource_evidence(worktree, current)
        if not hmac.compare_digest(
            resume_evidence.fingerprint,
            current.resume_compose_resource_fingerprint,
        ):
            raise StandError(
                "resolved Compose resource identity differs from signed resume evidence"
            )
    if current.resume_compose_resource_fingerprint is not None and (
        current.resume_compose_resource_schema_version
        in {
            RESOURCE_OWNER_SCHEMA_VERSION,
            PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
            PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
        }
        and current.stack != LIVE_STACK_FULL
    ):
        raise StandError(
            "legacy full-stack resume evidence cannot be reused for a Core stack"
        )
    _assert_compose_volume_ownership(
        current.project_name,
        evidence.managed_volumes,
        declared_volume_names=evidence.declared_volume_names,
        allow_existing_owned=(
            allow_existing_owned_volumes
            or current.resume_compose_resource_fingerprint is not None
        ),
        managed_networks=evidence.managed_networks,
        managed_services=evidence.managed_services,
    )
    _require_owned_docker_daemon(current)
    if load_stand_owner(worktree) != current:
        raise StandError(
            "ownership metadata changed during Compose resource registration"
        )
    updated = StandOwner(
        repository=current.repository,
        worktree=current.worktree,
        project_name=current.project_name,
        published_ports=current.published_ports,
        schema_version=current.schema_version,
        daemon_fingerprint=current.daemon_fingerprint,
        compose_resource_fingerprint=evidence.fingerprint,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha=current.source_sha,
        stack=evidence.stack,
        service_roots=evidence.service_roots,
        selected_services=evidence.selected_services,
    )
    return _write_stand_owner_update(worktree, updated)


def _verify_stand_owner_compose_resources(
    worktree: Path,
    owner: StandOwner,
    *,
    allow_existing_owned_volumes: bool = True,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> ComposeResourceEvidence:
    """Fail closed if the signed owner no longer matches the resolved Compose model."""
    current = load_stand_owner(worktree)
    if current != owner:
        raise StandError("live stand ownership metadata changed")
    legacy_full_owner = current.schema_version in {
        RESOURCE_OWNER_SCHEMA_VERSION,
        PREVIOUS_STACK_OWNER_SCHEMA_VERSION,
        PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION,
    }
    if not _is_active_owner_schema(current.schema_version) and not legacy_full_owner:
        raise StandError(
            "live stand ownership lacks Compose resource evidence for the current schema; re-run up before lifecycle operations"
        )
    if current.compose_resource_fingerprint is None:
        raise StandError(
            "live stand ownership lacks Compose resource evidence; refusing lifecycle operation"
        )
    if deadline is not None:
        _live_probe_remaining(deadline)
    evidence = _owner_compose_resource_evidence(
        worktree,
        current,
        deadline=deadline,
        docker_context=docker_context,
    )
    if not hmac.compare_digest(
        evidence.fingerprint, current.compose_resource_fingerprint
    ):
        raise StandError(
            "resolved Compose resources differ from signed live stand ownership"
        )
    if not legacy_full_owner and (
        evidence.stack != current.stack
        or evidence.service_roots != current.service_roots
        or evidence.selected_services != current.selected_services
    ):
        raise StandError(
            "resolved Compose selection differs from signed live stand ownership"
        )
    _assert_compose_volume_ownership(
        current.project_name,
        evidence.managed_volumes,
        declared_volume_names=evidence.declared_volume_names,
        allow_existing_owned=allow_existing_owned_volumes,
        managed_networks=evidence.managed_networks,
        managed_services=evidence.managed_services,
        deadline=deadline,
        docker_context=docker_context,
    )
    if deadline is not None:
        _live_probe_remaining(deadline)
    return evidence


def _invalidate_stand_owner_compose_resources(
    worktree: Path, owner: StandOwner
) -> StandOwner:
    """Revoke startup evidence after a failed pre-start revalidation."""
    current = load_stand_owner(worktree)
    if current != owner or current.compose_resource_fingerprint is None:
        raise StandError("live stand ownership changed before evidence invalidation")
    updated = StandOwner(
        repository=current.repository,
        worktree=current.worktree,
        project_name=current.project_name,
        published_ports=current.published_ports,
        schema_version=current.schema_version,
        daemon_fingerprint=current.daemon_fingerprint,
        compose_resource_fingerprint=None,
        resume_compose_resource_fingerprint=(
            current.compose_resource_fingerprint
            or current.resume_compose_resource_fingerprint
        ),
        resume_compose_resource_schema_version=(
            current.schema_version
            if current.compose_resource_fingerprint is not None
            else current.resume_compose_resource_schema_version
        ),
        source_sha=current.source_sha,
        stack=current.stack,
        service_roots=(
            current.service_roots if current.stack == LIVE_STACK_CORE else ()
        ),
        selected_services=(),
    )
    return _write_stand_owner_update(worktree, updated)


def stand_environment(
    keys: dict[str, str],
    project_name: str,
    published_ports: Mapping[str, int] = DEFAULT_PUBLISHED_PORTS,
) -> dict[str, str]:
    _validate_project_name(project_name)
    ports = dict(_validate_published_ports(published_ports, allow_privileged=True))
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project_name
    env["LIVE_VAPID_PUBLIC_KEY"] = keys["public"]
    env["LIVE_VAPID_PRIVATE_KEY"] = keys["private"]
    env["LIVE_BASE_URL"] = _stand_base_url(ports)
    # Keep desktop-shell proxy settings out of the initial live Compose model.
    # The owned run derives exact peers from inspected network attachments.
    for name in LIVE_TRUSTED_PROXY_SETTINGS:
        env[name] = ""
    if IN_PLACE_MODE:
        env["LIVE_STAND_STATE_ROOT"] = str(WORKTREE.resolve(strict=True))
        if SOURCE_SHA is not None:
            env["LIVE_STAND_SOURCE_SHA"] = SOURCE_SHA
    for name, port in ports.items():
        if name == "MAILPIT":
            env["LIVE_MAILPIT_PORT"] = str(port)
        else:
            env[f"LIVE_HOST_PORT_{name}"] = str(port)
    return env


def compose_control_environment(
    project_name: str,
    published_ports: Mapping[str, int] = DEFAULT_PUBLISHED_PORTS,
    *,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a secret-free environment for read/stop/remove Compose commands."""
    _validate_project_name(project_name)
    if set(published_ports) == set(PRE_MINIO_PUBLISHED_PORT_NAMES):
        ports = dict(
            _validate_pre_minio_published_ports(published_ports, allow_privileged=True)
        )
    else:
        ports = dict(_validate_published_ports(published_ports, allow_privileged=True))
    env = dict(os.environ if base_environment is None else base_environment)
    env["COMPOSE_PROJECT_NAME"] = project_name
    env["LIVE_BASE_URL"] = _stand_base_url(ports)
    # Compose interpolates these required live-overlay fields while loading
    # the project, even for `ps`, `stop`, or `down`. These commands never
    # recreate containers, so a fixed non-secret placeholder is sufficient.
    env["LIVE_VAPID_PUBLIC_KEY"] = COMPOSE_INSPECTION_PLACEHOLDER
    env["LIVE_VAPID_PRIVATE_KEY"] = COMPOSE_INSPECTION_PLACEHOLDER
    for name in LIVE_TRUSTED_PROXY_SETTINGS:
        env[name] = ""
    if IN_PLACE_MODE:
        env["LIVE_STAND_STATE_ROOT"] = str(WORKTREE.resolve(strict=True))
        if SOURCE_SHA is not None:
            env["LIVE_STAND_SOURCE_SHA"] = SOURCE_SHA
    for name, port in ports.items():
        if name == "MAILPIT":
            env["LIVE_MAILPIT_PORT"] = str(port)
        else:
            env[f"LIVE_HOST_PORT_{name}"] = str(port)
    return env


def compose_command(*args: str, project_name: str) -> list[str]:
    _validate_project_name(project_name)
    if IN_PLACE_MODE:
        command = [
            "docker",
            "compose",
            "--project-directory",
            str(REPO_ROOT.resolve(strict=True)),
            "-p",
            project_name,
            "--env-file",
            str((WORKTREE / ".env.docker").resolve(strict=False)),
        ]
        compose_files = (
            REPO_ROOT / COMPOSE_FILES[0],
            REPO_ROOT / OVERLAY,
            WORKTREE / IN_PLACE_OVERLAY,
        )
    else:
        command = ["docker", "compose", "-p", project_name, "--env-file", ".env.docker"]
        compose_files = tuple(Path(name) for name in COMPOSE_FILES)
    for compose_file in compose_files:
        command += ["-f", str(compose_file)]
    return [*command, *args]


def resolve_live_service_selection(
    compose_project: Mapping[str, object], stack: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve the fixed live roots and their complete Compose dependency closure.

    The Core list is deliberately checked against the reviewed service set so
    a Compose dependency change cannot silently broaden or shrink this stack.
    Full mode selects every service and remains the default live behavior.
    """
    if stack not in LIVE_STACKS:
        raise StandError("unsupported live stand stack selection")
    raw_services = compose_project.get("services")
    if not isinstance(raw_services, Mapping) or not raw_services:
        raise StandError("resolved Compose service inventory is invalid")
    services: dict[str, Mapping[str, object]] = {}
    for name, definition in raw_services.items():
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)
            or not isinstance(definition, Mapping)
        ):
            raise StandError("resolved Compose service inventory is invalid")
        services[name] = definition

    if stack == LIVE_STACK_FULL:
        selected = tuple(sorted(services))
        return selected, selected

    roots = LIVE_CORE_SERVICE_ROOTS
    if any(root not in services for root in roots):
        raise StandError("reviewed live Core service roots are missing from Compose")

    selected_names: set[str] = set()
    pending = list(roots)
    while pending:
        service_name = pending.pop()
        if service_name in selected_names:
            continue
        service = services.get(service_name)
        if service is None:
            raise StandError(
                "resolved Compose dependency references an unknown service"
            )
        selected_names.add(service_name)

        raw_dependencies = service.get("depends_on", {})
        if isinstance(raw_dependencies, Mapping):
            dependencies = list(raw_dependencies)
        elif isinstance(raw_dependencies, list):
            dependencies = raw_dependencies
        elif raw_dependencies in (None, {}):
            dependencies = []
        else:
            raise StandError("resolved Compose dependency inventory is invalid")

        network_mode = service.get("network_mode")
        if isinstance(network_mode, str) and network_mode.startswith("service:"):
            dependencies.append(network_mode.removeprefix("service:"))
        elif network_mode is not None and not isinstance(network_mode, str):
            raise StandError("resolved Compose network mode is invalid")

        raw_links = service.get("links", [])
        if raw_links is not None:
            if not isinstance(raw_links, list):
                raise StandError("resolved Compose link inventory is invalid")
            for link in raw_links:
                if not isinstance(link, str) or not link:
                    raise StandError("resolved Compose link inventory is invalid")
                dependencies.append(link.split(":", 1)[0])

        for dependency in dependencies:
            if not isinstance(dependency, str) or not dependency:
                raise StandError("resolved Compose dependency inventory is invalid")
            if dependency not in services:
                raise StandError(
                    "resolved Compose dependency references an unknown service"
                )
            if dependency not in selected_names:
                pending.append(dependency)

    selected = tuple(sorted(selected_names))
    if selected != LIVE_CORE_EXPECTED_SERVICES:
        raise StandError(
            "resolved live Core dependency closure differs from reviewed services"
        )
    return tuple(sorted(roots)), selected


def _compose_resource_evidence(
    worktree: Path,
    project_name: str,
    published_ports: Mapping[str, int],
    *,
    stack: str = LIVE_STACK_FULL,
    service_roots: Sequence[str] | None = None,
    legacy_projection: bool = False,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> ComposeResourceEvidence:
    """Resolve removable resources and service topology without runtime secrets."""
    _validate_project_name(project_name)
    command = _live_docker_command(
        compose_command("config", "--format", "json", project_name=project_name),
        docker_context,
    )
    compose_environment = compose_control_environment(
        project_name,
        published_ports,
        base_environment=(
            docker_context.environment_dict() if docker_context is not None else None
        ),
    )
    try:
        if deadline is not None:
            if docker_context is None:
                raise StandError("cannot verify resolved Compose resource ownership")
            completed = _run_live_bounded_read(
                command,
                context=docker_context,
                deadline=deadline,
                cwd=worktree,
                environment=compose_environment,
                maximum_bytes=_LIVE_CADDY_PROBE_MAX_BYTES,
                command_timeout_seconds=_LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS,
            )
            if completed.returncode != 0 or completed.stderr:
                raise StandError("cannot verify resolved Compose resource ownership")
            completed_stdout: object = (completed.stdout or b"").decode(
                "utf-8", errors="strict"
            )
        else:
            run_options: dict[str, object] = {
                "cwd": worktree,
                "env": compose_environment,
            }
            completed = subprocess.run(  # noqa: S603 - fixed Compose argv and validated project
                command,
                check=True,
                capture_output=True,
                text=True,
                **run_options,
            )
            if docker_context is not None:
                _assert_live_docker_read_context(docker_context)
            completed_stdout = completed.stdout
    except (
        OSError,
        RuntimeError,
        StandError,
        UnicodeError,
        subprocess.SubprocessError,
    ):
        raise StandError("cannot verify resolved Compose resource ownership") from None
    try:
        project = json.loads(completed_stdout)
    except (json.JSONDecodeError, TypeError):
        raise StandError("cannot parse resolved Compose resource ownership") from None
    return _compose_resource_evidence_from_project(
        project,
        project_name,
        published_ports,
        stack=stack,
        service_roots=service_roots,
        legacy_projection=legacy_projection,
    )


def _compose_resource_evidence_from_project(
    project: object,
    project_name: str,
    published_ports: Mapping[str, int],
    *,
    stack: str = LIVE_STACK_FULL,
    service_roots: Sequence[str] | None = None,
    legacy_projection: bool = False,
) -> ComposeResourceEvidence:
    """Project already parsed Compose data without performing transport I/O."""
    if not isinstance(project, dict) or project.get("name") != project_name:
        raise StandError("resolved Compose project does not match live stand ownership")

    raw_volumes = project.get("volumes", {})
    raw_networks = project.get("networks", {})
    raw_services = project.get("services", {})
    if (
        not isinstance(raw_volumes, dict)
        or not isinstance(raw_networks, dict)
        or not isinstance(raw_services, dict)
    ):
        raise StandError("resolved Compose resource inventory is invalid")
    resolved_roots, selected_services = resolve_live_service_selection(project, stack)
    if service_roots is not None and tuple(service_roots) != resolved_roots:
        raise StandError(
            "resolved Compose service roots differ from live owner selection"
        )
    selected_service_set = set(selected_services)

    volumes: dict[str, object] = {}
    managed_volumes: list[tuple[str, str]] = []
    declared_volume_names: set[str] = set()
    resolved_managed_names: set[str] = set()
    for volume_key, raw_definition in sorted(raw_volumes.items()):
        if not isinstance(volume_key, str) or not isinstance(raw_definition, dict):
            raise StandError("resolved Compose volume inventory is invalid")
        external = raw_definition.get("external", False)
        if not isinstance(external, bool):
            raise StandError("resolved Compose volume ownership is ambiguous")
        resolved_name = raw_definition.get("name")
        if resolved_name is None:
            resolved_name = volume_key if external else f"{project_name}_{volume_key}"
        if not isinstance(resolved_name, str) or not resolved_name:
            raise StandError("resolved Compose volume name is invalid")
        declared_volume_names.add(resolved_name)
        if not external and not resolved_name.startswith(f"{project_name}_"):
            raise StandError(
                "refusing unscoped Compose volume outside the live stand project"
            )
        if not external:
            if resolved_name in resolved_managed_names:
                raise StandError("multiple Compose volumes resolve to one managed name")
            resolved_managed_names.add(resolved_name)
            managed_volumes.append((volume_key, resolved_name))
        # Bind only the identity that Compose down can remove. Hashing the
        # full resolved definition could capture unrelated interpolated values
        # such as driver options or labels in the owner marker's fingerprint.
        volumes[volume_key] = {
            "external": external,
            "resolved_name": resolved_name,
        }

    networks: dict[str, object] = {}
    managed_networks: list[tuple[str, str]] = []
    for network_key, raw_definition in sorted(raw_networks.items()):
        if not isinstance(network_key, str) or (
            raw_definition is not None and not isinstance(raw_definition, dict)
        ):
            raise StandError("resolved Compose network inventory is invalid")
        definition = raw_definition if isinstance(raw_definition, dict) else {}
        external = definition.get("external", False)
        if not isinstance(external, bool):
            raise StandError("resolved Compose network ownership is ambiguous")
        resolved_name = definition.get("name")
        if resolved_name is None:
            resolved_name = network_key if external else f"{project_name}_{network_key}"
        if (
            not isinstance(resolved_name, str)
            or not resolved_name
            or "\n" in resolved_name
            or "\r" in resolved_name
        ):
            raise StandError("resolved Compose network name is invalid")
        if not external and not resolved_name.startswith(f"{project_name}_"):
            raise StandError(
                "refusing unscoped Compose network outside the live stand project"
            )
        if not external:
            managed_networks.append((network_key, resolved_name))
        networks[network_key] = {
            "external": external,
            "resolved_name": resolved_name,
        }

    service_mounts: dict[str, object] = {}
    for service_name, raw_service in sorted(raw_services.items()):
        if service_name not in selected_service_set:
            continue
        if not isinstance(service_name, str) or not isinstance(raw_service, dict):
            raise StandError("resolved Compose service inventory is invalid")
        mounts = raw_service.get("volumes", [])
        volumes_from = raw_service.get("volumes_from", [])
        if not isinstance(mounts, list) or not isinstance(volumes_from, list):
            raise StandError("resolved Compose mount inventory is invalid")
        if volumes_from:
            raise StandError("Compose volumes_from is unsupported for owned teardown")
        network_mode = raw_service.get("network_mode")
        if network_mode is not None and (
            not isinstance(network_mode, str) or not network_mode
        ):
            raise StandError("resolved Compose network mode is invalid")
        raw_service_networks = raw_service.get("networks")
        if network_mode is not None:
            if raw_service_networks not in (None, {}, []):
                raise StandError("Compose service sets both networks and network_mode")
            service_networks: list[str] = []
        elif raw_service_networks is None:
            service_networks = ["default"]
        elif isinstance(raw_service_networks, dict):
            service_networks = list(raw_service_networks)
            if not service_networks:
                service_networks = ["default"]
        elif isinstance(raw_service_networks, list):
            service_networks = raw_service_networks
            if not service_networks:
                service_networks = ["default"]
        else:
            raise StandError("resolved Compose service network inventory is invalid")
        if any(not isinstance(name, str) or not name for name in service_networks):
            raise StandError("resolved Compose service network reference is invalid")
        for network_name in service_networks:
            if network_name not in networks:
                if network_name != "default":
                    raise StandError(
                        "resolved Compose service references an undeclared network"
                    )
                resolved_default = f"{project_name}_default"
                networks["default"] = {
                    "external": False,
                    "resolved_name": resolved_default,
                }
                managed_networks.append(("default", resolved_default))
        mount_identities: list[dict[str, str | None]] = []
        for mount in mounts:
            if not isinstance(mount, dict):
                raise StandError("resolved Compose mount entry is invalid")
            mount_type = mount.get("type")
            target = mount.get("target")
            source = mount.get("source")
            if not isinstance(mount_type, str) or mount_type not in {
                "volume",
                "bind",
                "tmpfs",
            }:
                raise StandError("resolved Compose mount type is unsupported")
            if not isinstance(target, str) or not target:
                raise StandError("resolved Compose mount target is invalid")
            if source is not None and not isinstance(source, str):
                raise StandError("resolved Compose mount source is invalid")
            if mount_type in {"volume", "bind"}:
                if not isinstance(source, str) or not source:
                    if mount_type == "volume":
                        raise StandError(
                            "anonymous Compose volumes are unsupported for owned teardown"
                        )
                    raise StandError("resolved Compose bind source is invalid")
                if mount_type == "volume" and source not in raw_volumes:
                    raise StandError(
                        "resolved Compose mount refers to an undeclared volume"
                    )
            elif source is not None:
                raise StandError("resolved Compose tmpfs source is ambiguous")
            mount_identities.append(
                {
                    "type": mount_type,
                    "source": source,
                    "target": target,
                }
            )
        service_mounts[service_name] = {
            "volumes": mount_identities,
            "volumes_from": volumes_from,
            "networks": sorted(service_networks),
            "network_mode": network_mode,
        }

    used_volume_keys: set[str] = set()
    used_network_keys: set[str] = set()
    for service in service_mounts.values():
        if not isinstance(service, dict):
            raise StandError("resolved Compose service selection is invalid")
        for mount in service["volumes"]:
            if mount["type"] == "volume":
                used_volume_keys.add(mount["source"])
        used_network_keys.update(service["networks"])
    if stack == LIVE_STACK_CORE and not legacy_projection:
        # Core teardown removes only resources used by its signed service
        # closure. Full Compose ``down --volumes`` can remove every declared
        # project volume, including one no selected service currently mounts,
        # so full and historical projections must retain the complete model.
        volumes = {
            key: value for key, value in volumes.items() if key in used_volume_keys
        }
        managed_volumes = [
            (key, name) for key, name in managed_volumes if key in used_volume_keys
        ]
        declared_volume_names = {value["resolved_name"] for value in volumes.values()}
        networks = {
            key: value for key, value in networks.items() if key in used_network_keys
        }
        managed_networks = [
            (key, name) for key, name in managed_networks if key in used_network_keys
        ]

    projection = {
        "project_name": project_name,
        "volumes": volumes,
        "networks": networks,
        "service_mounts": service_mounts,
    }
    if not legacy_projection:
        projection.update(
            {
                "stack": stack,
                "service_roots": list(resolved_roots),
                "selected_services": list(selected_services),
            }
        )
        if stack == LIVE_STACK_CORE:
            selected_ports = _selected_published_ports(
                published_ports, selected_services
            )
            # The signed owner marker binds the actual host-port values. The
            # resource projection binds only which port inputs belong to this
            # service closure, so a safe port reallocation can resume against
            # the same Compose resources.
            projection["published_port_names"] = sorted(selected_ports)
    try:
        canonical = json.dumps(
            projection, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
    except (TypeError, ValueError):
        raise StandError(
            "cannot canonicalize resolved Compose resource ownership"
        ) from None
    if COMPOSE_INSPECTION_PLACEHOLDER in canonical:
        raise StandError(
            "runtime VAPID inputs cannot determine Compose resource identity"
        )
    return ComposeResourceEvidence(
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        managed_volumes=tuple(managed_volumes),
        declared_volume_names=tuple(sorted(declared_volume_names)),
        managed_networks=tuple(sorted(managed_networks)),
        managed_services=tuple(sorted(service_mounts)),
        stack=stack,
        service_roots=resolved_roots,
        selected_services=selected_services,
        network_bindings=tuple(
            sorted(
                (key, str(value["resolved_name"]), bool(value["external"]))
                for key, value in networks.items()
            )
        ),
        service_networks=tuple(
            sorted(
                (service, tuple(details["networks"]))
                for service, details in service_mounts.items()
            )
        ),
        service_mounts=tuple(
            (
                service_name,
                tuple(
                    (
                        mount["type"],
                        (
                            volumes[mount["source"]]["resolved_name"]
                            if mount["type"] == "volume"
                            else mount["source"]
                        ),
                        mount["target"],
                    )
                    for mount in details["volumes"]
                ),
            )
            for service_name, details in sorted(service_mounts.items())
        ),
    )


def _compose_resource_fingerprint(
    worktree: Path,
    project_name: str,
    published_ports: Mapping[str, int],
) -> str:
    """Fingerprint the resolved Compose identity used by destructive cleanup."""
    return _compose_resource_evidence(
        worktree, project_name, published_ports
    ).fingerprint


_DOCKER_INSPECT_MAX_CONTAINER_IDS = 10_000
_DOCKER_INSPECT_BATCH_SIZE = 64
_DOCKER_INSPECT_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_DOCKER_INSPECT_MOUNT_TYPES = frozenset({"volume", "bind", "tmpfs"})
_DOCKER_INSPECT_FORMAT = (
    '{"Id":{{json .Id}},'
    '"ProjectLabel":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"ServiceLabel":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"OneoffLabel":{{json (index .Config.Labels "com.docker.compose.oneoff")}},'
    '"Mounts":[{{range $i, $m := .Mounts}}{{if $i}},{{end}}'
    '{"Type":{{json $m.Type}},'
    '"Name":{{if eq $m.Type "volume"}}{{json $m.Name}}{{else}}null{{end}}'
    "}{{end}}]}"
)


_LIVE_CADDY_CORE_INSPECT_FORMAT = (
    '{"Id":{{json .Id}},'
    '"Name":{{json .Name}},'
    '"Image":{{json .Image}},'
    '"ConfigImage":{{json .Config.Image}},'
    '"Labels":{{json .Config.Labels}},'
    '"State":{"Running":{{json .State.Running}},'
    '"Status":{{json .State.Status}},'
    '"Health":{{if eq (index .State "Health") nil}}null{{else}}'
    '{"Status":{{json (index (index .State "Health") "Status")}}}{{end}}},'
    '"Mounts":{{json .Mounts}}}'
)
_LIVE_CADDY_CORE_MOUNT_FIELDS = (
    "Type",
    "Name",
    "Source",
    "Destination",
    "Driver",
    "Mode",
    "RW",
    "Propagation",
)


class _DockerProjectionError(ValueError):
    """Signal an incomplete or ambiguous batched Docker projection."""


@dataclass(frozen=True, slots=True)
class _DockerMountProjection:
    mount_type: str
    name: str | None


@dataclass(frozen=True, slots=True)
class _DockerContainerProjection:
    container_id: str
    project_label: str | None
    service_label: str | None
    oneoff_label: str | None
    mounts: tuple[_DockerMountProjection, ...]


def _bounded_docker_strings(values: Iterable[str], *, maximum: int) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or maximum < 0:
        raise _DockerProjectionError
    try:
        iterator = iter(values)
    except TypeError:
        raise _DockerProjectionError from None
    result: list[str] = []
    for value in iterator:
        if len(result) >= maximum or not isinstance(value, str):
            raise _DockerProjectionError
        result.append(value)
    return tuple(result)


def _validated_docker_container_ids(
    values: Iterable[str], *, maximum: int
) -> tuple[str, ...]:
    ids = _bounded_docker_strings(values, maximum=maximum)
    if any(not _DOCKER_INSPECT_CONTAINER_ID.fullmatch(item) for item in ids) or len(
        set(ids)
    ) != len(ids):
        raise _DockerProjectionError
    return ids


def _build_docker_inspect_projection_commands(
    container_ids: Iterable[str],
) -> tuple[tuple[str, ...], ...]:
    ids = _validated_docker_container_ids(
        container_ids, maximum=_DOCKER_INSPECT_MAX_CONTAINER_IDS
    )
    return tuple(
        (
            "docker",
            "inspect",
            "--type",
            "container",
            "--format",
            _DOCKER_INSPECT_FORMAT,
            *ids[start : start + _DOCKER_INSPECT_BATCH_SIZE],
        )
        for start in range(0, len(ids), _DOCKER_INSPECT_BATCH_SIZE)
    )


def _reject_duplicate_docker_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DockerProjectionError
        result[key] = value
    return result


def _parse_docker_inspect_projection_batch(
    output: str, expected_ids: Sequence[str]
) -> tuple[_DockerContainerProjection, ...]:
    ids = _validated_docker_container_ids(
        expected_ids, maximum=_DOCKER_INSPECT_BATCH_SIZE
    )
    if not ids or not isinstance(output, str):
        raise _DockerProjectionError
    lines = output.splitlines()
    if len(lines) != len(ids) or any(not line.strip() for line in lines):
        raise _DockerProjectionError

    expected = set(ids)
    parsed: dict[str, _DockerContainerProjection] = {}
    for line in lines:
        try:
            value = json.loads(
                line, object_pairs_hook=_reject_duplicate_docker_json_keys
            )
        except (json.JSONDecodeError, _DockerProjectionError):
            raise _DockerProjectionError from None
        if not isinstance(value, dict) or set(value) != {
            "Id",
            "ProjectLabel",
            "ServiceLabel",
            "OneoffLabel",
            "Mounts",
        }:
            raise _DockerProjectionError

        container_id = value["Id"]
        project_label = value["ProjectLabel"]
        service_label = value["ServiceLabel"]
        oneoff_label = value["OneoffLabel"]
        raw_mounts = value["Mounts"]
        if (
            not isinstance(container_id, str)
            or not _DOCKER_INSPECT_CONTAINER_ID.fullmatch(container_id)
            or container_id not in expected
            or container_id in parsed
            or (project_label is not None and not isinstance(project_label, str))
            or (service_label is not None and not isinstance(service_label, str))
            or (oneoff_label is not None and not isinstance(oneoff_label, str))
            or not isinstance(raw_mounts, list)
        ):
            raise _DockerProjectionError

        mounts: list[_DockerMountProjection] = []
        for raw_mount in raw_mounts:
            if (
                not isinstance(raw_mount, dict)
                or set(raw_mount) != {"Type", "Name"}
                or not isinstance(raw_mount["Type"], str)
                or raw_mount["Type"] not in _DOCKER_INSPECT_MOUNT_TYPES
                or (
                    raw_mount["Name"] is not None
                    and not isinstance(raw_mount["Name"], str)
                )
            ):
                raise _DockerProjectionError
            mounts.append(_DockerMountProjection(raw_mount["Type"], raw_mount["Name"]))
        parsed[container_id] = _DockerContainerProjection(
            container_id=container_id,
            project_label=project_label,
            service_label=service_label,
            oneoff_label=oneoff_label,
            mounts=tuple(mounts),
        )

    if set(parsed) != expected:
        raise _DockerProjectionError
    return tuple(parsed[container_id] for container_id in ids)


def _reject_nonstandard_docker_json_constant(_value: str) -> object:
    raise _DockerProjectionError


def _build_live_core_caddy_inspect_command(
    container_ids: Iterable[str],
) -> tuple[str, ...]:
    ids = _validated_docker_container_ids(
        container_ids, maximum=_LIVE_CADDY_PROBE_MAX_PROJECT_CONTAINERS
    )
    if not ids:
        raise _DockerProjectionError
    return (
        "docker",
        "inspect",
        "--type",
        "container",
        "--format",
        _LIVE_CADDY_CORE_INSPECT_FORMAT,
        *ids,
    )


def _parse_live_core_caddy_inspect_batch(
    output: str, expected_ids: Sequence[str]
) -> tuple[dict[str, object], ...]:
    ids = _validated_docker_container_ids(
        expected_ids, maximum=_LIVE_CADDY_PROBE_MAX_PROJECT_CONTAINERS
    )
    if not ids or not isinstance(output, str):
        raise _DockerProjectionError
    lines = output.splitlines()
    if len(lines) != len(ids) or any(not line.strip() for line in lines):
        raise _DockerProjectionError

    expected = set(ids)
    parsed_by_id: dict[str, dict[str, object]] = {}
    for line in lines:
        try:
            value = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_docker_json_keys,
                parse_constant=_reject_nonstandard_docker_json_constant,
            )
        except (json.JSONDecodeError, _DockerProjectionError):
            raise _DockerProjectionError from None
        if not isinstance(value, dict) or set(value) != {
            "Id",
            "Name",
            "Image",
            "ConfigImage",
            "Labels",
            "State",
            "Mounts",
        }:
            raise _DockerProjectionError
        container_id = value["Id"]
        name = value["Name"]
        image = value["Image"]
        config_image = value["ConfigImage"]
        labels = value["Labels"]
        state = value["State"]
        mounts = value["Mounts"]
        if (
            not isinstance(container_id, str)
            or not _DOCKER_INSPECT_CONTAINER_ID.fullmatch(container_id)
            or container_id not in expected
            or container_id in parsed_by_id
            or not isinstance(name, str)
            or not isinstance(image, str)
            or not isinstance(config_image, str)
            or not isinstance(labels, dict)
            or not all(
                isinstance(key, str) and isinstance(label, str)
                for key, label in labels.items()
            )
            or not isinstance(state, dict)
            or set(state) != {"Running", "Status", "Health"}
            or not isinstance(state["Running"], bool)
            or (state["Status"] is not None and not isinstance(state["Status"], str))
            or not isinstance(mounts, list)
        ):
            raise _DockerProjectionError
        health = state["Health"]
        if health is not None and (
            not isinstance(health, dict)
            or set(health) != {"Status"}
            or not isinstance(health["Status"], str)
        ):
            raise _DockerProjectionError

        normalized_mounts: list[dict[str, object]] = []
        for mount in mounts:
            if (
                not isinstance(mount, dict)
                or "Type" not in mount
                or not isinstance(mount["Type"], str)
            ):
                raise _DockerProjectionError
            normalized_mounts.append(
                {key: mount.get(key) for key in _LIVE_CADDY_CORE_MOUNT_FIELDS}
            )
        parsed_by_id[container_id] = {
            "Id": container_id,
            "Name": name,
            "Image": image,
            "Config": {"Image": config_image, "Labels": labels},
            "State": {
                "Running": state["Running"],
                "Status": state["Status"],
                "Health": health,
            },
            "Mounts": normalized_mounts,
        }

    if set(parsed_by_id) != expected:
        raise _DockerProjectionError
    return tuple(parsed_by_id[container_id] for container_id in ids)


def _parse_docker_inspect_projection_inventory(
    container_ids: Iterable[str], batch_outputs: Iterable[str]
) -> tuple[_DockerContainerProjection, ...]:
    ids = _validated_docker_container_ids(
        container_ids, maximum=_DOCKER_INSPECT_MAX_CONTAINER_IDS
    )
    batches = tuple(
        ids[start : start + _DOCKER_INSPECT_BATCH_SIZE]
        for start in range(0, len(ids), _DOCKER_INSPECT_BATCH_SIZE)
    )
    outputs = _bounded_docker_strings(batch_outputs, maximum=len(batches))
    if len(outputs) != len(batches):
        raise _DockerProjectionError

    parsed_by_id: dict[str, _DockerContainerProjection] = {}
    for expected_batch, output in zip(batches, outputs, strict=True):
        for record in _parse_docker_inspect_projection_batch(output, expected_batch):
            if record.container_id in parsed_by_id:
                raise _DockerProjectionError
            parsed_by_id[record.container_id] = record
    if len(parsed_by_id) != len(ids) or set(parsed_by_id) != set(ids):
        raise _DockerProjectionError
    return tuple(parsed_by_id[container_id] for container_id in ids)


def _assert_compose_volume_ownership(
    project_name: str,
    managed_volumes: Sequence[tuple[str, str]],
    *,
    declared_volume_names: Sequence[str],
    allow_existing_owned: bool,
    managed_networks: Sequence[tuple[str, str]] = (),
    managed_services: Sequence[str] = (),
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> tuple[tuple[str, str], ...]:
    """Check every project resource that Compose teardown could remove."""
    _validate_project_name(project_name)
    existing: list[tuple[str, str]] = []
    if any(not isinstance(name, str) or not name for name in declared_volume_names):
        raise StandError("resolved Compose volume ownership is ambiguous")
    allowed_volume_names = set(declared_volume_names)

    def inventory(command: list[str], error_message: str) -> str:
        try:
            if deadline is not None:
                if docker_context is None:
                    raise StandError(error_message)
                _live_probe_remaining(deadline)
                completed = _run_live_bounded_read(
                    command,
                    context=docker_context,
                    deadline=deadline,
                    maximum_bytes=_LIVE_CADDY_PROBE_MAX_BYTES,
                    command_timeout_seconds=_LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS,
                )
                if completed.returncode != 0 or completed.stderr:
                    raise StandError(error_message)
                output = (completed.stdout or b"").decode("utf-8", errors="replace")
                _live_probe_remaining(deadline)
                return output
            selected_command = _live_docker_command(command, docker_context)
            run_options: dict[str, object] = {}
            if docker_context is not None:
                run_options = {
                    "cwd": docker_context.cwd,
                    "env": docker_context.environment_dict(),
                }
            completed = subprocess.run(  # noqa: S603 - fixed Docker inventory probes with validated resource names
                selected_command,
                check=True,
                capture_output=True,
                text=True,
                **run_options,
            )
            if docker_context is not None:
                _assert_live_docker_read_context(docker_context)
        except (
            OSError,
            RuntimeError,
            StandError,
            UnicodeError,
            subprocess.SubprocessError,
        ):
            raise StandError(error_message) from None
        output = completed.stdout
        if not isinstance(output, str):
            raise StandError(error_message)
        return output

    def inspect_labels(command: list[str], error_message: str) -> dict[str, object]:
        output = inventory(command, error_message)
        try:
            labels = json.loads(output)
        except json.JSONDecodeError:
            raise StandError(error_message) from None
        if not isinstance(labels, dict):
            raise StandError(error_message)
        return labels

    if managed_volumes:
        existing_names = set(
            inventory(
                ["docker", "volume", "ls", "--format", "{{.Name}}"],
                "cannot verify live stand Docker volume ownership",
            ).splitlines()
        )
        for logical_name, resolved_name in managed_volumes:
            if resolved_name not in existing_names:
                continue
            if not allow_existing_owned:
                raise StandError(
                    "a live stand volume already exists before its first Compose startup"
                )
            labels = inspect_labels(
                [
                    "docker",
                    "volume",
                    "inspect",
                    "--format",
                    "{{json .Labels}}",
                    resolved_name,
                ],
                "cannot verify existing live stand volume labels",
            )
            if (
                labels.get("com.docker.compose.project") != project_name
                or labels.get("com.docker.compose.volume") != logical_name
            ):
                raise StandError(
                    "an existing live stand volume is not owned by the expected Compose project"
                )
            existing.append((logical_name, resolved_name))

    if managed_networks:
        existing_networks = set(
            inventory(
                ["docker", "network", "ls", "--format", "{{.Name}}"],
                "cannot verify live stand Docker network ownership",
            ).splitlines()
        )
        for logical_name, resolved_name in managed_networks:
            if resolved_name not in existing_networks:
                continue
            if not allow_existing_owned:
                raise StandError(
                    "a live stand network already exists before its first Compose startup"
                )
            labels = inspect_labels(
                [
                    "docker",
                    "network",
                    "inspect",
                    "--format",
                    "{{json .Labels}}",
                    resolved_name,
                ],
                "cannot verify existing live stand network labels",
            )
            if (
                labels.get("com.docker.compose.project") != project_name
                or labels.get("com.docker.compose.network") != logical_name
            ):
                raise StandError(
                    "an existing live stand network is not owned by the expected Compose project"
                )

    project_filter = f"label=com.docker.compose.project={project_name}"
    container_ids = inventory(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            project_filter,
        ],
        "cannot verify live stand Docker container ownership",
    ).splitlines()
    try:
        validated_ids = _validated_docker_container_ids(
            container_ids, maximum=_DOCKER_INSPECT_MAX_CONTAINER_IDS
        )
    except _DockerProjectionError:
        raise StandError("live stand container inventory is ambiguous") from None

    allowed_services = set(managed_services)
    if validated_ids and not allow_existing_owned:
        raise StandError(
            "a live stand container already exists before its first Compose startup"
        )
    if validated_ids:
        inspect_error = "cannot verify existing live stand Docker container ownership"
        batch_outputs = tuple(
            inventory(list(command), inspect_error)
            for command in _build_docker_inspect_projection_commands(validated_ids)
        )
        try:
            records = _parse_docker_inspect_projection_inventory(
                validated_ids, batch_outputs
            )
        except _DockerProjectionError:
            raise StandError(inspect_error) from None

        for record in records:
            if (
                record.project_label != project_name
                or record.service_label not in allowed_services
            ):
                raise StandError(
                    "an existing live stand container is not owned by the expected Compose project"
                )
            for mount in record.mounts:
                if mount.mount_type == "volume" and (
                    not isinstance(mount.name, str)
                    or mount.name not in allowed_volume_names
                ):
                    raise StandError(
                        "live stand container uses an unregistered Docker volume"
                    )
    return tuple(existing)


def port_is_free(port: int, host: str = PORT_BIND_HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
        return True


def require_free_ports(
    ports: Mapping[str, int] | Sequence[int],
    *,
    active_services: Sequence[str] | None = None,
) -> None:
    if isinstance(ports, Mapping):
        validated_ports = dict(_validate_published_ports(ports, allow_privileged=True))
        active_names = (
            tuple(validated_ports)
            if active_services is None
            else _published_port_names_for_services(active_services)
        )
        values = tuple(validated_ports[name] for name in active_names)
    else:
        if active_services is not None:
            raise StandError("selected services require a named live port map")
        values = tuple(ports)
    busy = [port for port in values if not port_is_free(port, host=PORT_BIND_HOST)]
    if busy:
        raise StandError(
            f"loopback ports {busy} are in use; refusing to stop or build the stand"
        )


def _run(
    command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603 - fixed argv


def _docker_output(
    arguments: Sequence[str],
    error_message: str,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> str:
    try:
        command = ["docker", *arguments]
        if deadline is not None:
            if docker_context is None:
                raise StandError(error_message)
            _live_probe_remaining(deadline)
            completed = _run_live_bounded_read(
                command,
                context=docker_context,
                deadline=deadline,
                maximum_bytes=_LIVE_CADDY_PROBE_MAX_BYTES,
                command_timeout_seconds=_LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS,
            )
            if completed.returncode != 0 or completed.stderr:
                raise StandError(error_message)
            output = (completed.stdout or b"").decode("utf-8", errors="replace")
            _live_probe_remaining(deadline)
            return output
        selected_command = _live_docker_command(command, docker_context)
        run_options: dict[str, object] = {}
        if docker_context is not None:
            run_options = {
                "cwd": docker_context.cwd,
                "env": docker_context.environment_dict(),
            }
        completed = subprocess.run(  # noqa: S603 - fixed Docker inventory/cleanup argv
            selected_command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **run_options,
        )
        if docker_context is not None:
            _assert_live_docker_read_context(docker_context)
    except (
        OSError,
        RuntimeError,
        StandError,
        UnicodeError,
        subprocess.SubprocessError,
    ):
        raise StandError(error_message) from None
    if not isinstance(completed.stdout, str):
        raise StandError(error_message)
    return completed.stdout


def _docker_inspect_object(
    arguments: Sequence[str],
    error_message: str,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> dict[str, object]:
    output = _docker_output(
        arguments,
        error_message,
        deadline=deadline,
        docker_context=docker_context,
    )
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        raise StandError(error_message) from None
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        raise StandError(error_message)
    return value


def _project_container_ids(
    project_name: str,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> tuple[str, ...]:
    output = _docker_output(
        [
            "ps",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={project_name}",
        ],
        "cannot verify live Core container inventory",
        deadline=deadline,
        docker_context=docker_context,
    )
    ids = tuple(line for line in output.splitlines() if line)
    if any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in ids):
        raise StandError("live Core container inventory is ambiguous")
    if len(set(ids)) != len(ids):
        raise StandError("live Core container inventory contains duplicates")
    return ids


def _all_docker_container_ids() -> tuple[str, ...]:
    output = _docker_output(
        ["ps", "--all", "--quiet", "--no-trunc"],
        "cannot verify Docker container network references",
    )
    ids = tuple(line for line in output.splitlines() if line)
    if (
        len(ids) > 10000
        or any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in ids)
        or len(set(ids)) != len(ids)
    ):
        raise StandError("Docker container network reference inventory is ambiguous")
    return ids


def _network_has_container_references(network_id: str) -> bool:
    """Include stopped containers whose inspect data retains a NetworkID."""
    for container_id in _all_docker_container_ids():
        record = _docker_inspect_object(
            ["inspect", container_id],
            "cannot verify Docker container network references",
        )
        settings = record.get("NetworkSettings")
        networks = settings.get("Networks") if isinstance(settings, dict) else None
        if not isinstance(networks, dict):
            raise StandError("Docker container network references are ambiguous")
        for attachment in networks.values():
            if not isinstance(attachment, dict):
                raise StandError("Docker container network references are ambiguous")
            referenced_id = attachment.get("NetworkID")
            if referenced_id in (None, ""):
                continue
            if not isinstance(referenced_id, str) or not re.fullmatch(
                r"[0-9a-f]{64}", referenced_id
            ):
                raise StandError("Docker container network references are ambiguous")
            if referenced_id == network_id:
                return True
    return False


def _core_container_record_from_inspect(
    container_id: str,
    owner: StandOwner,
    evidence: ComposeResourceEvidence,
    record: dict[str, object],
) -> CoreContainerRecord:
    config = record.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    service = (
        labels.get("com.docker.compose.service") if isinstance(labels, dict) else None
    )
    if (
        record.get("Id") != container_id
        or not isinstance(labels, dict)
        or labels.get("com.docker.compose.project") != owner.project_name
        or not isinstance(service, str)
        or service not in evidence.managed_services
    ):
        raise StandError(
            "live Core container is not owned by the signed service closure"
        )
    mounts = record.get("Mounts")
    image = record.get("Image")
    config_image = config.get("Image") if isinstance(config, dict) else None
    name = record.get("Name")
    if (
        not isinstance(mounts, list)
        or not isinstance(image, str)
        or not isinstance(config_image, str)
        or not isinstance(name, str)
        or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in labels.items()
        )
    ):
        raise StandError("live Core container mount inventory is ambiguous")
    allowed_volumes = set(evidence.declared_volume_names)
    mount_identity: list[tuple[object, ...]] = []
    for mount in mounts:
        if not isinstance(mount, dict) or mount.get("Type") not in {
            "volume",
            "bind",
            "tmpfs",
        }:
            raise StandError("live Core container mount inventory is ambiguous")
        if mount.get("Type") == "volume" and mount.get("Name") not in allowed_volumes:
            raise StandError("live Core container uses an unregistered volume")
        mount_identity.append(
            tuple(
                mount.get(key)
                for key in (
                    "Type",
                    "Name",
                    "Source",
                    "Destination",
                    "Driver",
                    "Mode",
                    "RW",
                    "Propagation",
                )
            )
        )
    state = record.get("State")
    running = state.get("Running") if isinstance(state, dict) else None
    status = state.get("Status") if isinstance(state, dict) else None
    raw_health = state.get("Health") if isinstance(state, dict) else None
    if not isinstance(running, bool) or (
        status is not None and not isinstance(status, str)
    ):
        raise StandError("live Core container state is ambiguous")
    if raw_health is None:
        health = None
    elif isinstance(raw_health, dict) and isinstance(raw_health.get("Status"), str):
        health = raw_health["Status"]
    else:
        raise StandError("live Core container health state is ambiguous")
    identity = {
        "id": container_id,
        "name": name,
        "image_id": image,
        "image_name": config_image,
        "labels": labels,
        "mounts": sorted(mount_identity, key=repr),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CoreContainerRecord(
        service=service,
        identity=digest,
        running=running,
        status=status,
        health=health,
    )


def _verify_core_container_record(
    container_id: str, owner: StandOwner, evidence: ComposeResourceEvidence
) -> tuple[str, bool]:
    record = _docker_inspect_object(
        ["inspect", container_id], "cannot verify live Core container identity"
    )
    inspected = _core_container_record_from_inspect(
        container_id, owner, evidence, record
    )
    return inspected.identity, inspected.running


def _trusted_proxy_address(
    value: object,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not isinstance(value, str) or not value or "/" in value or "%" in value:
        raise StandError("live proxy network address is invalid")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise StandError("live proxy network address is invalid") from None
    if address.is_unspecified:
        return None
    if address.version == 4:
        first, second = address.packed[:2]
        private_bridge = (
            first == 10
            or (first == 172 and 16 <= second <= 31)
            or (first == 192 and second == 168)
        )
    else:
        private_bridge = address.packed[0] & 0xFE == 0xFC
    if (
        value != address.compressed.lower()
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_global
        or not private_bridge
    ):
        raise StandError("live proxy network address is outside the owned bridge range")
    return address


def _trusted_proxy_settings_from_inspects(
    owner: StandOwner,
    evidence: ComposeResourceEvidence,
    containers: Mapping[str, dict[str, object]],
    networks: Mapping[str, dict[str, object]],
) -> tuple[dict[str, tuple[str, ...]], dict[str, dict[str, tuple[str, ...]]]]:
    """Derive exact proxy peers from signed Compose names and inspected attachments."""
    required = set(LIVE_TRUSTED_PROXY_SERVICES)
    if (
        owner.stack != evidence.stack
        or owner.selected_services != evidence.selected_services
        or not required <= set(owner.selected_services)
        or not required <= set(evidence.managed_services)
        or set(containers) != required
    ):
        raise StandError("live trusted proxy selection differs from signed ownership")

    binding_rows = evidence.network_bindings
    network_bindings = {key: (name, external) for key, name, external in binding_rows}
    if (
        not binding_rows
        or len(network_bindings) != len(binding_rows)
        or len({name for _, name, _ in binding_rows}) != len(binding_rows)
        or any(
            not isinstance(key, str)
            or not key
            or not isinstance(name, str)
            or not name
            or not isinstance(external, bool)
            for key, name, external in binding_rows
        )
    ):
        raise StandError("signed live network identity evidence is incomplete")
    service_network_rows = evidence.service_networks
    service_networks = {service: names for service, names in service_network_rows}
    if len(service_networks) != len(service_network_rows):
        raise StandError("signed live service network evidence is ambiguous")

    expected_network_names: set[str] = set()
    for service in LIVE_TRUSTED_PROXY_SERVICES:
        logical_names = service_networks.get(service)
        if (
            not isinstance(logical_names, tuple)
            or not logical_names
            or len(set(logical_names)) != len(logical_names)
            or any(name not in network_bindings for name in logical_names)
        ):
            raise StandError("signed live service network evidence is incomplete")
        expected_network_names.update(
            network_bindings[name][0] for name in logical_names
        )
    if set(networks) != expected_network_names:
        raise StandError("inspected live network inventory differs from signed names")

    network_ids: dict[str, str] = {}
    network_subnets: dict[
        str, tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    ] = {}
    resolved_to_logical = {name: key for key, (name, _) in network_bindings.items()}
    for name, record in networks.items():
        if record.get("Name") != name:
            raise StandError("inspected live network name differs from signed evidence")
        network_id = record.get("Id")
        labels = record.get("Labels")
        if not isinstance(network_id, str) or not re.fullmatch(
            r"[0-9a-f]{64}", network_id
        ):
            raise StandError("inspected live network identity is ambiguous")
        logical_name = resolved_to_logical.get(name)
        if logical_name is None:
            raise StandError(
                "inspected live network is not in signed resource evidence"
            )
        _, external = network_bindings[logical_name]
        if not external and (
            not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != owner.project_name
            or labels.get("com.docker.compose.network") != logical_name
        ):
            raise StandError("owned live network labels differ from signed identity")
        ipam = record.get("IPAM")
        raw_subnets = ipam.get("Config") if isinstance(ipam, dict) else None
        if not isinstance(raw_subnets, list) or not raw_subnets:
            raise StandError("inspected live network IPAM evidence is incomplete")
        subnets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for item in raw_subnets:
            subnet = item.get("Subnet") if isinstance(item, dict) else None
            if not isinstance(subnet, str) or not subnet:
                raise StandError("inspected live network IPAM evidence is ambiguous")
            try:
                subnets.append(ipaddress.ip_network(subnet, strict=False))
            except ValueError:
                raise StandError(
                    "inspected live network IPAM evidence is ambiguous"
                ) from None
        network_ids[name] = network_id
        network_subnets[name] = tuple(subnets)

    addresses_by_service: dict[str, dict[str, tuple[str, ...]]] = {}
    for service, record in containers.items():
        container_id = record.get("Id")
        if not isinstance(container_id, str) or not re.fullmatch(
            r"[0-9a-f]{64}", container_id
        ):
            raise StandError("live trusted proxy container identity is ambiguous")
        inspected = _core_container_record_from_inspect(
            container_id, owner, evidence, record
        )
        if (
            inspected.service != service
            or not inspected.running
            or inspected.status != "running"
            or (service == "backend" and inspected.health != "healthy")
        ):
            raise StandError("live trusted proxy target is not healthy and owned")
        settings = record.get("NetworkSettings")
        raw_attachments = (
            settings.get("Networks") if isinstance(settings, dict) else None
        )
        logical_names = service_networks.get(service)
        if not isinstance(raw_attachments, dict) or not isinstance(
            logical_names, tuple
        ):
            raise StandError("live trusted proxy attachment inventory is ambiguous")
        expected_names = {network_bindings[key][0] for key in logical_names}
        if set(raw_attachments) != expected_names:
            raise StandError(
                "live trusted proxy attachments differ from signed network names"
            )
        per_network: dict[str, tuple[str, ...]] = {}
        for logical_name in logical_names:
            network_name, _ = network_bindings[logical_name]
            attachment = raw_attachments.get(network_name)
            if (
                not isinstance(attachment, dict)
                or attachment.get("NetworkID") != network_ids[network_name]
            ):
                raise StandError(
                    "live proxy NetworkID differs from inspected signed network"
                )
            raw_addresses = [
                attachment.get("IPAddress"),
                attachment.get("GlobalIPv6Address"),
            ]
            parsed: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
            for raw_address in raw_addresses:
                if raw_address in (None, ""):
                    continue
                address = _trusted_proxy_address(raw_address)
                if address is None:
                    continue
                if not any(
                    address.version == subnet.version and address in subnet
                    for subnet in network_subnets[network_name]
                ):
                    raise StandError(
                        "live proxy address is outside inspected network IPAM"
                    )
                parsed.append(address)
            if not parsed:
                raise StandError("live proxy network attachment has no usable address")
            per_network[logical_name] = tuple(
                sorted({address.compressed.lower() for address in parsed})
            )
        addresses_by_service[service] = per_network

    def peers(receiver: str, sources: Sequence[str]) -> tuple[str, ...]:
        result: set[str] = set()
        receiver_networks = addresses_by_service[receiver]
        for source in sources:
            source_networks = addresses_by_service[source]
            for logical_name in set(receiver_networks) & set(source_networks):
                result.update(source_networks[logical_name])
        if not result:
            raise StandError("live proxy chain has no inspected shared network peer")
        return tuple(sorted(result))

    settings = {
        "TRUSTED_PROXIES": peers("backend", ("caddy", "gateway")),
        "GATEWAY_TRUSTED_PROXIES": peers("gateway", ("caddy",)),
        "WS_HUB_TRUSTED_PROXIES": peers("ws-hub", ("caddy",)),
    }
    if set(settings) != set(LIVE_TRUSTED_PROXY_SETTINGS):
        raise StandError("live trusted proxy setting inventory is invalid")
    return settings, addresses_by_service


def _capture_live_trusted_proxy_inventory(
    owner: StandOwner, evidence: ComposeResourceEvidence
) -> tuple[
    dict[str, CoreContainerRecord],
    dict[str, tuple[str, ...]],
    dict[str, dict[str, tuple[str, ...]]],
    dict[str, str],
]:
    if (
        owner.stack != evidence.stack
        or owner.selected_services != evidence.selected_services
        or not set(LIVE_TRUSTED_PROXY_SERVICES) <= set(owner.selected_services)
    ):
        raise StandError("live trusted proxy selection differs from signed ownership")
    records: dict[str, CoreContainerRecord] = {}
    containers: dict[str, dict[str, object]] = {}
    service_ids: dict[str, str] = {}
    for container_id in _project_container_ids(owner.project_name):
        raw = _docker_inspect_object(
            ["inspect", container_id],
            "cannot verify live trusted proxy container identity",
        )
        inspected = _core_container_record_from_inspect(
            container_id, owner, evidence, raw
        )
        records[container_id] = inspected
        if inspected.service in LIVE_TRUSTED_PROXY_SERVICES:
            if inspected.service in service_ids:
                raise StandError(
                    "live trusted proxy service has multiple owned containers"
                )
            service_ids[inspected.service] = container_id
            containers[inspected.service] = raw
    if set(containers) != set(LIVE_TRUSTED_PROXY_SERVICES):
        raise StandError("live trusted proxy container inventory is incomplete")

    network_bindings = {key: name for key, name, _ in evidence.network_bindings}
    logical_by_name = {name: key for key, name in network_bindings.items()}
    service_networks = dict(evidence.service_networks)
    names: set[str] = set()
    for service in LIVE_TRUSTED_PROXY_SERVICES:
        logical = service_networks.get(service)
        if (
            not isinstance(logical, tuple)
            or not logical
            or any(key not in network_bindings for key in logical)
        ):
            raise StandError("signed live service network evidence is incomplete")
        names.update(network_bindings[key] for key in logical)
    networks = {
        name: _docker_inspect_object(
            ["network", "inspect", name], "cannot verify signed live network identity"
        )
        for name in sorted(names)
    }
    settings, addresses_by_service = _trusted_proxy_settings_from_inspects(
        owner, evidence, containers, networks
    )
    return (
        records,
        settings,
        addresses_by_service,
        {logical_by_name[name]: str(record["Id"]) for name, record in networks.items()},
    )


def _assert_live_trusted_proxy_source_current(owner: StandOwner) -> None:
    try:
        if load_stand_owner(WORKTREE) != owner:
            raise StandError("live trusted proxy owner or source identity changed")
        expected_source_sha = owner.source_sha if IN_PLACE_MODE else SOURCE_SHA
        if not isinstance(expected_source_sha, str) or not re.fullmatch(
            r"[0-9a-f]{40}", expected_source_sha
        ):
            raise StandError("live trusted proxy owner or source identity changed")
        if IN_PLACE_MODE:
            if (
                SOURCE_SHA != expected_source_sha
                or _git("rev-parse", "HEAD") != expected_source_sha
            ):
                raise StandError("live trusted proxy source identity changed")
            if _git("status", "--porcelain", "--untracked-files=normal"):
                raise StandError("live trusted proxy source tree changed")
        else:
            if _git("-C", str(WORKTREE), "rev-parse", "HEAD") != expected_source_sha:
                raise StandError("live trusted proxy source identity changed")
            _assert_worktree_clean(WORKTREE)
    except subprocess.CalledProcessError:
        raise StandError(
            "live trusted proxy source identity cannot be verified"
        ) from None


def _assert_live_trusted_proxy_container_delta(
    before: Mapping[str, CoreContainerRecord],
    after: Mapping[str, CoreContainerRecord],
    allowed_services: set[str],
) -> None:
    before_stable = {
        container_id: (
            record.service,
            record.identity,
            record.running,
            record.status,
            record.health,
        )
        for container_id, record in before.items()
        if record.service not in allowed_services
    }
    after_stable = {
        container_id: (
            record.service,
            record.identity,
            record.running,
            record.status,
            record.health,
        )
        for container_id, record in after.items()
        if record.service not in allowed_services
    }
    if before_stable != after_stable:
        raise StandError(
            "non-target live containers changed during trusted proxy refresh"
        )


def _assert_live_trusted_proxy_network_ids_unchanged(
    before: Mapping[str, str], after: Mapping[str, str]
) -> None:
    if not before or before != after:
        raise StandError("live trusted proxy network identity changed during refresh")


def _require_live_trusted_proxy_http_health(owner: StandOwner) -> None:
    ports = dict(owner.published_ports)
    probes = (
        ("CADDY_HTTP", "/healthz"),
        ("GATEWAY", "/health"),
        ("WS_HUB", "/health"),
        ("BACKEND", "/health/ready"),
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port_name, path in probes:
        try:
            with opener.open(
                f"http://127.0.0.1:{ports[port_name]}{path}", timeout=5
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise StandError("live trusted proxy health probe failed")
        except (OSError, urllib.error.URLError, KeyError):
            raise StandError("live trusted proxy health probe failed") from None


def _run_live_trusted_proxy_refresh(
    owner: StandOwner,
    base_environment: Mapping[str, str],
    settings: Mapping[str, tuple[str, ...]],
    stage: str,
) -> None:
    if stage not in {"edge", "backend"} or set(settings) != set(
        LIVE_TRUSTED_PROXY_SETTINGS
    ):
        raise StandError("live trusted proxy refresh selection is invalid")
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        raise StandError(
            "PowerShell is required to refresh live trusted proxy settings"
        )
    launcher_path = (
        REPO_ROOT / "start-docker.ps1" if IN_PLACE_MODE else Path("start-docker.ps1")
    )
    command = [
        powershell,
        "-NoProfile",
        "-File",
        str(launcher_path),
        "-RefreshTrustedProxyPeers",
        "-TrustedProxyRefreshStage",
        stage,
        "-TrustedProxyPeersJson",
        json.dumps(settings, sort_keys=True, separators=(",", ":")),
        "-ExtraCompose",
        OVERLAY,
        "-LiveAcceptanceStack",
        owner.stack,
        "-LiveAcceptanceServicesJson",
        json.dumps(owner.selected_services, separators=(",", ":")),
    ]
    if IN_PLACE_MODE:
        command.extend(("-LiveStandStateRoot", str(WORKTREE.resolve(strict=True))))
    environment = dict(base_environment)
    environment.update(
        {
            "TRUSTED_PROXIES": ",".join(settings["TRUSTED_PROXIES"]),
            "GATEWAY_TRUSTED_PROXIES": ",".join(settings["GATEWAY_TRUSTED_PROXIES"]),
            "WS_HUB_TRUSTED_PROXIES": ",".join(settings["WS_HUB_TRUSTED_PROXIES"]),
        }
    )
    try:
        # Fixed launcher plus address data that has already passed the closed
        # inspected-network validator; no untrusted command text reaches a shell.
        result = subprocess.run(  # noqa: S603 - fixed PowerShell launcher and validated arguments
            command,
            cwd=WORKTREE,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        raise StandError("cannot refresh signed live trusted proxy services") from None
    if result.returncode != 0:
        raise StandError("cannot refresh signed live trusted proxy services")


def _assert_live_trusted_proxy_environment(
    records: Mapping[str, CoreContainerRecord],
    settings: Mapping[str, tuple[str, ...]],
) -> None:
    env_names = {
        "backend": ("TRUSTED_PROXIES", "TRUSTED_PROXIES"),
        "gateway": ("GATEWAY_TRUSTED_PROXIES", "GATEWAY_TRUSTED_PROXIES"),
        "ws-hub": ("TRUSTED_PROXIES", "WS_HUB_TRUSTED_PROXIES"),
    }
    found = {service: 0 for service in env_names}
    for container_id, record in records.items():
        service = record.service
        if service not in env_names:
            continue
        inspect = _docker_inspect_object(
            ["inspect", container_id], "cannot verify live trusted proxy environment"
        )
        config = inspect.get("Config")
        env = config.get("Env") if isinstance(config, dict) else None
        if not isinstance(env, list) or any(not isinstance(item, str) for item in env):
            raise StandError("live trusted proxy environment is ambiguous")
        variable, settings_name = env_names[service]
        matches = [
            item[len(variable) + 1 :] for item in env if item.startswith(f"{variable}=")
        ]
        expected = ",".join(settings[settings_name])
        if len(matches) != 1 or matches[0] != expected:
            raise StandError(
                "live trusted proxy environment differs from inspected peers"
            )
        found[service] += 1
    if any(count != 1 for count in found.values()):
        raise StandError("live trusted proxy environment inventory is incomplete")


def _configure_live_trusted_proxy_peers(
    owner: StandOwner,
    base_environment: Mapping[str, str],
    evidence: ComposeResourceEvidence,
) -> None:
    """Bind only this run's proxy settings to current signed network peers."""
    _assert_live_trusted_proxy_source_current(owner)
    _require_owned_docker_daemon(owner)
    current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    if current_evidence.fingerprint != evidence.fingerprint:
        raise StandError("live trusted proxy resource identity changed")
    _require_live_trusted_proxy_http_health(owner)
    before, initial_settings, initial_addresses, initial_network_ids = (
        _capture_live_trusted_proxy_inventory(owner, current_evidence)
    )

    edge_settings = {
        "TRUSTED_PROXIES": (),
        "GATEWAY_TRUSTED_PROXIES": initial_settings["GATEWAY_TRUSTED_PROXIES"],
        "WS_HUB_TRUSTED_PROXIES": initial_settings["WS_HUB_TRUSTED_PROXIES"],
    }
    if (
        edge_settings["GATEWAY_TRUSTED_PROXIES"]
        != edge_settings["WS_HUB_TRUSTED_PROXIES"]
    ):
        raise StandError(
            "live edge proxy peers do not share the signed Caddy attachment"
        )
    _run_live_trusted_proxy_refresh(owner, base_environment, edge_settings, "edge")
    _assert_live_trusted_proxy_source_current(owner)
    _require_owned_docker_daemon(owner)
    edge_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    if edge_evidence.fingerprint != evidence.fingerprint:
        raise StandError("live trusted proxy resource identity changed")
    _require_live_trusted_proxy_http_health(owner)
    after_edge, edge_settings, edge_addresses, edge_network_ids = (
        _capture_live_trusted_proxy_inventory(owner, edge_evidence)
    )
    _assert_live_trusted_proxy_container_delta(
        before, after_edge, {"gateway", "ws-hub"}
    )
    _assert_live_trusted_proxy_network_ids_unchanged(
        initial_network_ids, edge_network_ids
    )
    if initial_addresses["caddy"] != edge_addresses["caddy"]:
        raise StandError("non-target live proxy network attachment changed")
    _run_live_trusted_proxy_refresh(owner, base_environment, edge_settings, "backend")
    _assert_live_trusted_proxy_source_current(owner)
    _require_owned_docker_daemon(owner)
    final_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    if final_evidence.fingerprint != evidence.fingerprint:
        raise StandError("live trusted proxy resource identity changed")
    after_backend, actual_settings, actual_addresses, final_network_ids = (
        _capture_live_trusted_proxy_inventory(owner, final_evidence)
    )
    _assert_live_trusted_proxy_container_delta(after_edge, after_backend, {"backend"})
    _assert_live_trusted_proxy_container_delta(
        before, after_backend, {"backend", "gateway", "ws-hub"}
    )
    _assert_live_trusted_proxy_network_ids_unchanged(
        edge_network_ids, final_network_ids
    )
    if edge_settings != actual_settings or any(
        actual_addresses[service] != edge_addresses[service]
        for service in ("caddy", "gateway", "ws-hub")
    ):
        raise StandError("live trusted proxy topology changed during refresh")
    _require_live_trusted_proxy_http_health(owner)
    _assert_live_trusted_proxy_environment(after_backend, actual_settings)
    _assert_live_trusted_proxy_source_current(owner)
    _require_owned_docker_daemon(owner)
    final_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    if final_evidence.fingerprint != evidence.fingerprint:
        raise StandError("live trusted proxy resource identity changed")


def _core_quiesce_container_inventory(
    owner: StandOwner,
    evidence: ComposeResourceEvidence,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> dict[str, CoreContainerRecord]:
    """Require one verified container for every service in the signed Core projection."""
    selected = owner.selected_services
    selected_set = set(selected)
    if (
        owner.stack != LIVE_STACK_CORE
        or evidence.stack != LIVE_STACK_CORE
        or not selected
        or len(selected_set) != len(selected)
        or evidence.selected_services != selected
        or set(evidence.managed_services) != selected_set
        or not LIVE_CORE_QUIESCE_DATA_STORES <= selected_set
    ):
        raise StandError("signed Core service projection is incomplete for quiesce")

    records: dict[str, CoreContainerRecord] = {}
    service_to_id: dict[str, str] = {}
    if deadline is not None:
        _live_probe_remaining(deadline)
    for container_id in _project_container_ids(
        owner.project_name,
        deadline=deadline,
        docker_context=docker_context,
    ):
        raw_record = _docker_inspect_object(
            ["inspect", container_id],
            "cannot verify live Core container identity",
            deadline=deadline,
            docker_context=docker_context,
        )
        inspected = _core_container_record_from_inspect(
            container_id, owner, evidence, raw_record
        )
        if inspected.service not in selected_set:
            raise StandError(
                "live Core container is outside the signed service selection"
            )
        if inspected.service in service_to_id:
            raise StandError("live Core service has multiple owned containers")
        service_to_id[inspected.service] = container_id
        records[container_id] = inspected
    if set(service_to_id) != selected_set:
        raise StandError("live Core container inventory is incomplete")
    if deadline is not None:
        _live_probe_remaining(deadline)
    return records


def _assert_core_container_identity_unchanged(
    before: dict[str, CoreContainerRecord],
    after: dict[str, CoreContainerRecord],
) -> None:
    before_identity = {
        container_id: (record.service, record.identity)
        for container_id, record in before.items()
    }
    after_identity = {
        container_id: (record.service, record.identity)
        for container_id, record in after.items()
    }
    if before_identity != after_identity:
        raise StandError("live Core container inventory changed during quiesce")


def _require_core_data_stores_healthy(
    records: dict[str, CoreContainerRecord], stage: str
) -> None:
    by_service = {record.service: record for record in records.values()}
    if any(
        not (
            by_service[service].running
            and by_service[service].status == "running"
            and by_service[service].health == "healthy"
        )
        for service in LIVE_CORE_QUIESCE_DATA_STORES
    ):
        raise StandError(f"Core data stores must be running and healthy {stage}")


def _quiesce_locked() -> None:
    """Stop owned Core writers while retaining healthy owned data stores."""
    _require_worktree()
    owner = load_stand_owner(WORKTREE)
    if owner.stack != LIVE_STACK_CORE:
        raise StandError("quiesce is supported only for Core stands")
    _require_owned_docker_daemon(owner)
    evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    before = _core_quiesce_container_inventory(owner, evidence)
    _require_core_data_stores_healthy(before, "before quiesce")
    stop_services = tuple(
        service
        for service in owner.selected_services
        if service not in LIVE_CORE_QUIESCE_DATA_STORES
    )
    if not stop_services:
        raise StandError("signed Core service selection has no writable services")

    # Resolve owner, daemon and Compose evidence again after inspection and
    # immediately before the control operation.
    _require_worktree()
    if load_stand_owner(WORKTREE) != owner:
        raise StandError("live stand ownership metadata changed before quiesce")
    _require_owned_docker_daemon(owner)
    current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    if current_evidence != evidence:
        raise StandError("resolved Compose resources changed before quiesce")
    pre_stop = _core_quiesce_container_inventory(owner, current_evidence)
    _assert_core_container_identity_unchanged(before, pre_stop)
    _require_core_data_stores_healthy(pre_stop, "before quiesce")

    env = compose_control_environment(owner.project_name, dict(owner.published_ports))
    command = compose_command("stop", *stop_services, project_name=owner.project_name)
    try:
        _run(command, cwd=WORKTREE, env=env)
    except (OSError, subprocess.CalledProcessError):
        raise StandError("failed to stop owned Core services") from None

    _require_worktree()
    if load_stand_owner(WORKTREE) != owner:
        raise StandError("live stand ownership metadata changed after quiesce")
    _require_owned_docker_daemon(owner)
    current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    if current_evidence != evidence:
        raise StandError("resolved Compose resources changed after quiesce")
    after = _core_quiesce_container_inventory(owner, current_evidence)
    _assert_core_container_identity_unchanged(before, after)
    _require_core_data_stores_healthy(after, "after quiesce")
    for record in after.values():
        if record.service not in LIVE_CORE_QUIESCE_DATA_STORES and (
            record.running or record.status != "exited"
        ):
            raise StandError("selected Core services remain active after quiesce")
    print(
        "owned Core containers quiesced; postgres and minio remain healthy; "
        "external writers are not verified"
    )


def quiesce() -> None:
    """Stop owned Core services while preserving its healthy Postgres and MinIO stores."""
    if not IN_PLACE_MODE:
        raise StandError("quiesce requires an in-place Core stand")
    with stand_lifecycle_lock():
        _quiesce_locked()


def _assert_core_owner_unchanged(
    owner: StandOwner,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> None:
    if deadline is not None:
        _live_probe_remaining(deadline)
    if load_stand_owner(WORKTREE) != owner:
        raise StandError("live stand ownership metadata changed during Core teardown")
    _require_owned_docker_daemon(
        owner, deadline=deadline, docker_context=docker_context
    )
    if deadline is not None:
        _live_probe_remaining(deadline)


def _remove_core_compose_containers(
    owner: StandOwner,
    evidence: ComposeResourceEvidence,
) -> None:
    container_ids = _project_container_ids(owner.project_name)
    identities = {
        container_id: _verify_core_container_record(container_id, owner, evidence)[0]
        for container_id in container_ids
    }
    for container_id in container_ids:
        _assert_core_owner_unchanged(owner)
        current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
        if current_evidence != evidence:
            raise StandError("live Core Compose selection changed during teardown")
        current_ids = set(_project_container_ids(owner.project_name))
        if current_ids - set(identities):
            raise StandError("live Core project gained an unverified container")
        if container_id not in current_ids:
            continue
        current_identity, running = _verify_core_container_record(
            container_id, owner, evidence
        )
        if current_identity != identities[container_id]:
            raise StandError("live Core container identity changed before removal")
        if running:
            _docker_output(
                ["stop", "--time", "10", container_id],
                "cannot stop verified live Core container",
            )
        current_ids = set(_project_container_ids(owner.project_name))
        if current_ids - set(identities):
            raise StandError("live Core project gained an unverified container")
        if container_id not in current_ids:
            continue
        _assert_core_owner_unchanged(owner)
        current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
        if current_evidence != evidence:
            raise StandError("live Core Compose selection changed during teardown")
        current_identity, still_running = _verify_core_container_record(
            container_id, owner, evidence
        )
        if current_identity != identities[container_id] or still_running:
            raise StandError("live Core container changed before exact-ID removal")
        _docker_output(
            ["rm", container_id], "cannot remove verified live Core container"
        )
    remaining_ids = _project_container_ids(owner.project_name)
    if set(remaining_ids) - set(identities):
        raise StandError("live Core project gained an unverified container")
    if remaining_ids:
        raise StandError("live Core containers remain after service-scoped removal")


def _remove_core_project_networks(
    owner: StandOwner, evidence: ComposeResourceEvidence
) -> None:
    expected = {name: logical for logical, name in evidence.managed_networks}
    if len(expected) != len(evidence.managed_networks):
        raise StandError("live Core network ownership is ambiguous")
    output = _docker_output(
        [
            "network",
            "ls",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={owner.project_name}",
        ],
        "cannot verify live Core network inventory",
    )
    ids = tuple(line for line in output.splitlines() if line)
    if any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in ids) or len(
        set(ids)
    ) != len(ids):
        raise StandError("live Core network inventory is ambiguous")
    observed: set[str] = set()
    for network_id in ids:
        record = _docker_inspect_object(
            ["network", "inspect", network_id],
            "cannot verify live Core network identity",
        )
        name = record.get("Name")
        labels = record.get("Labels")
        attached = record.get("Containers")
        if (
            record.get("Id") != network_id
            or not isinstance(name, str)
            or name not in expected
            or name in observed
            or not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != owner.project_name
            or labels.get("com.docker.compose.network") != expected[name]
            or (attached is not None and attached != {})
        ):
            raise StandError(
                "live Core network is foreign, unexpected, or still attached"
            )
        observed.add(name)
        _assert_core_owner_unchanged(owner)
        current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
        if current_evidence != evidence:
            raise StandError("live Core Compose selection changed during teardown")
        fresh = _docker_inspect_object(
            ["network", "inspect", network_id],
            "cannot reverify live Core network before removal",
        )
        if (
            fresh.get("Id") != network_id
            or fresh.get("Name") != name
            or fresh.get("Labels") != labels
            or (fresh.get("Containers") is not None and fresh.get("Containers") != {})
        ):
            raise StandError("live Core network changed before removal")
        if _network_has_container_references(network_id):
            raise StandError("live Core network is referenced by a container")
        _assert_core_owner_unchanged(owner)
        current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
        if current_evidence != evidence:
            raise StandError("live Core Compose selection changed during teardown")
        _docker_output(
            ["network", "rm", network_id], "cannot remove verified live Core network"
        )
    remaining = _docker_output(
        [
            "network",
            "ls",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={owner.project_name}",
        ],
        "cannot verify live Core network cleanup",
    )
    if any(line for line in remaining.splitlines()):
        raise StandError("live Core project networks remain after cleanup")


def _remove_core_project_volumes(
    owner: StandOwner, evidence: ComposeResourceEvidence
) -> None:
    expected = {name: logical for logical, name in evidence.managed_volumes}
    if len(expected) != len(evidence.managed_volumes):
        raise StandError("live Core volume ownership is ambiguous")
    output = _docker_output(
        [
            "volume",
            "ls",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={owner.project_name}",
        ],
        "cannot verify live Core volume inventory",
    )
    names = tuple(line for line in output.splitlines() if line)
    if len(set(names)) != len(names) or any(name not in expected for name in names):
        raise StandError("live Core volume inventory contains an unexpected resource")
    for name in names:
        record = _docker_inspect_object(
            ["volume", "inspect", name], "cannot verify live Core volume identity"
        )
        labels = record.get("Labels")
        if (
            record.get("Name") != name
            or not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != owner.project_name
            or labels.get("com.docker.compose.volume") != expected[name]
        ):
            raise StandError(
                "live Core volume is not owned by the signed Compose project"
            )
        holders = _docker_output(
            [
                "ps",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"volume={name}",
            ],
            "cannot verify live Core volume attachments",
        )
        if any(line for line in holders.splitlines()):
            raise StandError("live Core volume is still attached to a container")
        _assert_core_owner_unchanged(owner)
        current_evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
        if current_evidence != evidence:
            raise StandError("live Core Compose selection changed during teardown")
        fresh = _docker_inspect_object(
            ["volume", "inspect", name],
            "cannot reverify live Core volume before removal",
        )
        if fresh.get("Name") != name or fresh.get("Labels") != labels:
            raise StandError("live Core volume changed before removal")
        holders = _docker_output(
            [
                "ps",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"volume={name}",
            ],
            "cannot reverify live Core volume attachments",
        )
        if any(line for line in holders.splitlines()):
            raise StandError("live Core volume became attached before removal")
        _docker_output(
            ["volume", "rm", name], "cannot remove verified live Core volume"
        )
    remaining = _docker_output(
        [
            "volume",
            "ls",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={owner.project_name}",
        ],
        "cannot verify live Core volume cleanup",
    )
    if any(line for line in remaining.splitlines()):
        raise StandError("live Core project volumes remain after cleanup")


def _git(*args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git argv
        ["git", *args],  # noqa: S607 - git resolved from PATH like every repo script
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def resolve_stand_ref(ref: str) -> str:
    """Resolve the selected commit and reject refs without the live overlay."""
    try:
        sha = _git("rev-parse", "--verify", f"{ref}^{{commit}}")
        _git("cat-file", "-e", f"{sha}:{OVERLAY}")
    except subprocess.CalledProcessError as error:
        raise StandError(
            f"selected ref {ref!r} is invalid or does not contain {OVERLAY}"
        ) from error
    return sha


def ensure_worktree(ref: str) -> str:
    _assert_no_reparse_ancestors(WORKTREE)
    sha = resolve_stand_ref(ref)
    if WORKTREE.exists():
        _assert_worktree_clean(WORKTREE)
        _git("-C", str(WORKTREE), "checkout", "--detach", sha)
    else:
        _git("worktree", "add", "--detach", str(WORKTREE), sha)
    return sha


def _assert_worktree_clean(worktree: Path) -> None:
    changes = _git("-C", str(worktree), "status", "--porcelain", "--untracked-files=no")
    if changes:
        raise StandError(f"{worktree} has tracked changes; refusing to switch it")


def _require_worktree(*, require_current_source: bool = True) -> None:
    _assert_stand_paths_safe(WORKTREE)
    if IN_PLACE_MODE:
        if (
            not (REPO_ROOT / OVERLAY).is_file()
            or not (WORKTREE / IN_PLACE_OVERLAY).is_file()
        ):
            raise StandError("in-place stand files are incomplete; run `up` first")
    elif not (WORKTREE / OVERLAY).is_file():
        raise StandError(f"no stand at {WORKTREE}; run `live_stand.py up` first")
    owner = load_stand_owner(WORKTREE)
    if (
        owner.schema_version
        in {
            RESOURCE_OWNER_SCHEMA_VERSION,
            OWNER_SCHEMA_VERSION,
            IN_PLACE_OWNER_SCHEMA_VERSION,
        }
        and owner.compose_resource_fingerprint is None
    ):
        raise StandError(
            "live stand startup is incomplete; refusing lifecycle operation"
        )
    if IN_PLACE_MODE:
        if require_current_source:
            _assert_in_place_source_current(owner)
        _assert_private_state_directory(WORKTREE)
        _assert_private_state_directory(WORKTREE / ".secrets")


def _assert_in_place_source_current(owner: StandOwner | None = None) -> str:
    """Reject source drift before operating on an in-place live stand."""
    current_sha = _git("rev-parse", "HEAD")
    expected_sha = owner.source_sha if owner is not None else SOURCE_SHA
    if expected_sha is None or current_sha != expected_sha:
        raise StandError(
            "in-place source checkout changed since the stand was prepared"
        )
    if _git("status", "--porcelain", "--untracked-files=normal"):
        raise StandError("in-place source checkout has modified or untracked files")
    _assert_no_ignored_in_place_build_sources()
    return current_sha


def _assert_no_ignored_in_place_build_sources() -> None:
    """Reject ignored local files that Docker would copy into live images.

    The tracked commit SHA does not cover ignored worktree files. Query only
    directories copied by the live Dockerfiles, and exclude cache/secret paths
    already omitted by the root Docker build context rules. Git reports paths
    internally; do not include potentially sensitive names in an error.
    """
    ignored_sources = _git(
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "--no-empty-directory",
        "--",
        *IN_PLACE_BUILD_SOURCE_PATHS,
        *(f":(exclude,glob){path}" for path in IN_PLACE_DOCKERIGNORE_EXCLUSIONS),
    )
    if ignored_sources:
        raise StandError(
            "in-place source checkout contains ignored untracked files in Docker COPY paths"
        )


def _up_locked(ref: str, stack: str = LIVE_STACK_FULL) -> None:
    global SOURCE_SHA
    if not IN_PLACE_MODE:
        SOURCE_SHA = None
    if stack not in LIVE_STACKS:
        raise StandError("unsupported live stand stack selection")
    _assert_stand_paths_safe(WORKTREE)
    resolved_sha = resolve_stand_ref(ref)
    if IN_PLACE_MODE:
        current_sha = _git("rev-parse", "HEAD")
        if resolved_sha != current_sha:
            raise StandError(
                "in-place mode requires --ref to match current checkout HEAD"
            )
        if _git("status", "--porcelain", "--untracked-files=normal"):
            raise StandError(
                "in-place mode requires a clean source checkout with no untracked files"
            )
        _assert_no_ignored_in_place_build_sources()
        SOURCE_SHA = current_sha
    existing_owner: StandOwner | None = None
    stop_after_resource_binding = False
    allow_existing_owned_volumes = False
    existing_marker = WORKTREE / STAND_FILE
    existing_owned_path = (
        existing_marker.is_file() if IN_PLACE_MODE else (WORKTREE / OVERLAY).is_file()
    )
    if WORKTREE.exists() and existing_owned_path:
        existing_owner = load_stand_owner(WORKTREE)
        if existing_owner.stack != stack:
            raise StandError(
                "existing live stand uses a different stack; teardown it before switching"
            )
        if IN_PLACE_MODE and existing_owner.source_sha != SOURCE_SHA:
            raise StandError("owned in-place stand belongs to a different source SHA")
        if IN_PLACE_MODE:
            _ensure_private_state_directory(WORKTREE, owner_verified=True)
            _ensure_private_state_directory(WORKTREE / ".secrets", owner_verified=True)
    elif IN_PLACE_MODE and WORKTREE.exists():
        raise StandError("in-place state directory exists without an owner marker")
    active_port_services = (
        LIVE_CORE_EXPECTED_SERVICES if stack == LIVE_STACK_CORE else None
    )
    if active_port_services is None:
        published_ports = choose_published_ports()
        require_free_ports(published_ports)
    else:
        published_ports = choose_published_ports(active_services=active_port_services)
        require_free_ports(published_ports, active_services=active_port_services)
    if existing_owner is not None:
        has_previous_resource_evidence = (
            existing_owner.compose_resource_fingerprint is not None
            or existing_owner.resume_compose_resource_fingerprint is not None
        )
        allow_existing_owned_volumes = (
            has_previous_resource_evidence
            or existing_owner.schema_version == PREVIOUS_OWNER_SCHEMA_VERSION
        )
        if not IN_PLACE_MODE:
            _assert_worktree_clean(WORKTREE)
        _require_owned_docker_daemon(existing_owner)
        stop_after_resource_binding = (
            existing_owner.schema_version == PREVIOUS_OWNER_SCHEMA_VERSION
            or existing_owner.schema_version == PREVIOUS_STACK_OWNER_SCHEMA_VERSION
            or existing_owner.schema_version == PREVIOUS_IN_PLACE_OWNER_SCHEMA_VERSION
            or (
                existing_owner.schema_version == RESOURCE_OWNER_SCHEMA_VERSION
                and has_previous_resource_evidence
            )
        )
        should_stop_before_binding = (
            _is_active_owner_schema(existing_owner.schema_version)
            and existing_owner.compose_resource_fingerprint is not None
        )
        if should_stop_before_binding:
            # Only current evidence covers containers and networks as well as
            # volumes. Older signed markers are rebound before the old project
            # is stopped; an incomplete reservation cannot authorize reuse.
            _verify_stand_owner_compose_resources(WORKTREE, existing_owner)
            _require_owned_docker_daemon(existing_owner)
            stop_services = (
                existing_owner.selected_services
                if existing_owner.stack == LIVE_STACK_CORE
                else ()
            )
            _run(
                compose_command(
                    "stop", *stop_services, project_name=existing_owner.project_name
                ),
                cwd=WORKTREE,
                env=compose_control_environment(
                    existing_owner.project_name,
                    dict(existing_owner.published_ports),
                ),
            )
    if IN_PLACE_MODE:
        _ensure_private_state_directory(WORKTREE, protect_new_windows=True)
        sha = resolved_sha
    else:
        sha = ensure_worktree(resolved_sha)
        try:
            worktree_sha = _git("-C", str(WORKTREE), "rev-parse", "HEAD")
        except subprocess.CalledProcessError:
            raise StandError(
                "cannot verify live stand worktree source identity"
            ) from None
        if sha != resolved_sha or worktree_sha != resolved_sha:
            raise StandError(
                "live stand worktree source identity changed during preparation"
            )
        _assert_worktree_clean(WORKTREE)
        # Normal owner schemas do not persist source_sha. Bind this post-start
        # refresh to the exact checkout verified for the current up invocation.
        SOURCE_SHA = worktree_sha
    _assert_stand_paths_safe(WORKTREE)
    if not (WORKTREE / STAND_FILE).is_file():
        owner = create_stand_owner(
            WORKTREE, published_ports=published_ports, stack=stack
        )
    else:
        if existing_owner is None:
            raise StandError("stand ownership metadata appeared during startup")
        owner = update_stand_owner_ports(WORKTREE, existing_owner, published_ports)
    # Catch ports claimed while the old project stopped or the worktree moved.
    # On failure the old stand data remains intact and no new build is started.
    owner_ports = dict(owner.published_ports)
    if active_port_services is None:
        require_free_ports(owner_ports)
    else:
        require_free_ports(owner_ports, active_services=active_port_services)
    env = stand_environment(
        load_or_create_vapid(WORKTREE), owner.project_name, dict(owner.published_ports)
    )
    if IN_PLACE_MODE:
        _write_in_place_compose_override(WORKTREE)
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        raise StandError("PowerShell is required to run start-docker.ps1")
    launcher_path = (
        REPO_ROOT / "start-docker.ps1" if IN_PLACE_MODE else Path("start-docker.ps1")
    )
    prepare_command = [
        powershell,
        "-NoProfile",
        "-File",
        str(launcher_path),
        "-PrepareOnly",
        "-InitializeTrustedProxyBootstrap",
        "-ExtraCompose",
        OVERLAY,
    ]
    if IN_PLACE_MODE:
        prepare_command.extend(
            ("-LiveStandStateRoot", str(WORKTREE.resolve(strict=True)))
        )
    _run(
        prepare_command,
        cwd=WORKTREE,
        env=env,
    )
    owner = _bind_stand_owner_compose_resources(
        WORKTREE,
        owner,
        allow_existing_owned_volumes=allow_existing_owned_volumes,
    )
    if stop_after_resource_binding:
        try:
            _verify_stand_owner_compose_resources(
                WORKTREE,
                owner,
                allow_existing_owned_volumes=allow_existing_owned_volumes,
            )
            _require_owned_docker_daemon(owner)
        except StandError:
            _invalidate_stand_owner_compose_resources(WORKTREE, owner)
            raise
        stop_services = (
            owner.selected_services if owner.stack == LIVE_STACK_CORE else ()
        )
        _run(
            compose_command("stop", *stop_services, project_name=owner.project_name),
            cwd=WORKTREE,
            env=compose_control_environment(
                owner.project_name, dict(owner.published_ports)
            ),
        )
    # Re-resolve immediately before handing control to the normal launcher.
    try:
        _verify_stand_owner_compose_resources(
            WORKTREE,
            owner,
            allow_existing_owned_volumes=allow_existing_owned_volumes,
        )
        _require_owned_docker_daemon(owner)
    except StandError:
        _invalidate_stand_owner_compose_resources(WORKTREE, owner)
        raise
    start_command = [
        powershell,
        "-NoProfile",
        "-File",
        str(launcher_path),
        "-Build",
        "-ExtraCompose",
        OVERLAY,
    ]
    start_command.extend(
        (
            "-LiveAcceptanceStack",
            owner.stack,
            "-LiveAcceptanceServicesJson",
            json.dumps(owner.selected_services, separators=(",", ":")),
        )
    )
    if IN_PLACE_MODE:
        start_command.extend(
            ("-LiveStandStateRoot", str(WORKTREE.resolve(strict=True)))
        )
    if allow_existing_owned_volumes:
        start_command.append("-AllowExistingOwnedVolumes")
    _run(start_command, cwd=WORKTREE, env=env)
    _configure_live_trusted_proxy_peers(
        owner, env, _verify_stand_owner_compose_resources(WORKTREE, owner)
    )
    published = dict(owner.published_ports)
    base_url = _stand_base_url(published)
    mailpit_url = f"http://127.0.0.1:{published['MAILPIT']}"
    print(f"stand {owner.project_name} is up at {base_url} for {sha}")
    print(f"LIVE_BASE_URL={base_url}")
    print(f"LIVE_MAILPIT_URL={mailpit_url}")


def up(ref: str, stack: str = LIVE_STACK_FULL) -> None:
    with stand_lifecycle_lock():
        _up_locked(ref, stack=stack)


def _new_test_password() -> str:
    """Create a policy-valid password for the owned synthetic admin account."""
    return secrets.token_urlsafe(32) + "!Aa0"


def _seed_locked(admin_password: str, *, owner: StandOwner | None = None) -> None:
    _require_worktree()
    current_owner = load_stand_owner(WORKTREE)
    if owner is not None and owner != current_owner:
        raise StandError("live stand ownership metadata changed before seeding")
    owner = current_owner
    _require_owned_docker_daemon(owner)
    env = stand_environment(
        load_vapid(WORKTREE), owner.project_name, dict(owner.published_ports)
    )
    env.pop("TEST_PASSWORD", None)
    source_root = REPO_ROOT if IN_PLACE_MODE else WORKTREE
    scripts_mount = f"{source_root / 'scripts'}:/app/scripts:ro"
    for script in SEED_SCRIPTS:
        run_env = env
        run_options = [
            "run",
            "--rm",
            "--no-deps",
            "-v",
            scripts_mount,
            "--env",
            f"COMPOSE_PROJECT_NAME={owner.project_name}",
            "--env",
            "LIVE_STAND_OWNER_VERIFIED=1",
            "--env",
            f"LIVE_STAND_SEED_PROJECT={owner.project_name}",
        ]
        if script == "scripts/seed_admin_data.py":
            run_env = {**env, "TEST_PASSWORD": admin_password}
            run_options.extend(("-e", "TEST_PASSWORD"))
        if script == "scripts/seed_live_authorization.py":
            run_options.extend(
                ("-v", f"{source_root / 'schema.zed'}:/app/schema.zed:ro")
            )
        run_options.extend(("backend", "python", script))
        try:
            _verify_stand_owner_compose_resources(WORKTREE, owner)
            _require_owned_docker_daemon(owner)
            _run(
                compose_command(
                    *run_options,
                    project_name=owner.project_name,
                ),
                cwd=WORKTREE,
                env=run_env,
            )
        finally:
            if script == "scripts/seed_admin_data.py":
                run_env.pop("TEST_PASSWORD", None)


def seed() -> None:
    admin_password = ""
    try:
        with stand_lifecycle_lock():
            owner = load_stand_owner(WORKTREE)
            admin_password = load_or_create_stand_admin_password(WORKTREE, owner)
            _seed_locked(admin_password, owner=owner)
    finally:
        admin_password = ""


def _live_e2e_environment(
    *,
    output_directory: str,
    npm_config_directory: str,
    source_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the minimal Playwright environment and its isolated npm configs."""
    runtime_source = (
        source_environment if source_environment is not None else os.environ
    )
    env = _live_e2e_runtime_environment(runtime_source)
    browser_cache = _playwright_browser_cache_path(env)
    config_root = Path(npm_config_directory)
    _mark_live_e2e_output_directory(output_directory, config_root)
    npm_user_config = config_root / "npm-userconfig"
    npm_global_config = config_root / "npm-globalconfig"
    for config_path in (npm_user_config, npm_global_config):
        with config_path.open("x", encoding="utf-8"):
            pass
    env.update(
        {
            "LIVE_E2E_OUTPUT_DIR": output_directory,
            "PLAYWRIGHT_TEST_OUTPUT_DIR": output_directory,
            "NPM_CONFIG_USERCONFIG": str(npm_user_config),
            "NPM_CONFIG_GLOBALCONFIG": str(npm_global_config),
            "PLAYWRIGHT_BROWSERS_PATH": str(browser_cache),
        }
    )
    return env


def _mark_live_e2e_output_directory(
    output_directory: str, npm_config_directory: Path
) -> Path:
    """Mark the wrapper's private temporary output root before Playwright loads."""
    raw_output = Path(output_directory)
    try:
        config_root = npm_config_directory.resolve(strict=True)
        output_path = raw_output.resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise StandError(
            "live E2E output must be an existing owned temp directory"
        ) from error

    if (
        raw_output.is_symlink()
        or not raw_output.is_absolute()
        or not output_path.is_dir()
        or output_path.name != "playwright-output"
        or output_path.parent != config_root
        or config_root.parent != temporary_root
        or not config_root.name.startswith("ue-live-playwright-")
    ):
        raise StandError("live E2E output must use its owned temporary directory")

    marker_path = config_root / LIVE_E2E_OUTPUT_OWNER_MARKER
    try:
        with marker_path.open("x", encoding="utf-8", newline="\n") as marker_file:
            marker_file.write(LIVE_E2E_OUTPUT_OWNER_MARKER_CONTENT)
    except OSError as error:
        raise StandError(
            "could not mark the owned live E2E output directory"
        ) from error
    return marker_path


def _live_e2e_runtime_environment(
    source: Mapping[str, str], *, platform: str | None = None
) -> dict[str, str]:
    """Copy only process/runtime metadata needed by npm and Playwright."""
    selected_platform = platform or os.name
    windows = selected_platform == "nt"
    allowed_names = (
        "PATH",
        "PLAYWRIGHT_BROWSERS_PATH",
        *(LIVE_E2E_WINDOWS_ENVIRONMENT if windows else LIVE_E2E_UNIX_ENVIRONMENT),
        *LIVE_E2E_CI_ENVIRONMENT,
    )

    def lookup(name: str) -> str | None:
        if name in source:
            return source[name]
        if windows:
            folded_name = name.casefold()
            for source_name, value in source.items():
                if source_name.casefold() == folded_name:
                    return value
        return None

    environment: dict[str, str] = {}
    for name in allowed_names:
        value = lookup(name)
        if value is not None:
            environment[name] = value
    if not environment.get("PATH"):
        raise StandError("PATH is required to launch live Playwright")
    return environment


def _playwright_browser_cache_path(
    environment: Mapping[str, str], *, platform: str | None = None
) -> Path:
    """Resolve the default cache or validate an existing local cache override."""
    selected_platform = platform or os.name
    windows = selected_platform == "nt"
    if "PLAYWRIGHT_BROWSERS_PATH" in environment:
        raw_override = environment["PLAYWRIGHT_BROWSERS_PATH"]
        if not isinstance(raw_override, str) or not raw_override.strip():
            raise StandError(
                "PLAYWRIGHT_BROWSERS_PATH must be an existing local directory"
            )
        if raw_override == "0" or raw_override.startswith(("\\\\", "//")):
            raise StandError(
                "PLAYWRIGHT_BROWSERS_PATH must be an existing local directory"
            )
        candidate = Path(raw_override)
        if not candidate.is_absolute():
            raise StandError(
                "PLAYWRIGHT_BROWSERS_PATH must be an absolute local directory"
            )
        _assert_no_reparse_ancestors(candidate)
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise StandError(
                "PLAYWRIGHT_BROWSERS_PATH must be an existing local directory"
            ) from error
        if not resolved.is_dir():
            raise StandError(
                "PLAYWRIGHT_BROWSERS_PATH must be an existing local directory"
            )
        _assert_no_reparse_ancestors(resolved)
        if windows:
            if not candidate.drive or candidate.anchor.startswith("\\\\"):
                raise StandError("PLAYWRIGHT_BROWSERS_PATH must be a local directory")
            try:
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(candidate.anchor)
            except (AttributeError, OSError) as error:
                raise StandError(
                    "could not verify the local Playwright browser cache"
                ) from error
            # DRIVE_REMOVABLE, DRIVE_FIXED, and DRIVE_RAMDISK are local stores.
            if drive_type not in {2, 3, 6}:
                raise StandError("PLAYWRIGHT_BROWSERS_PATH must be a local directory")
        return resolved

    profile_root = environment.get("LOCALAPPDATA" if windows else "HOME")
    if not profile_root:
        required_name = "LOCALAPPDATA" if windows else "HOME"
        raise StandError(
            f"{required_name} is required for the Playwright browser cache"
        )
    return (
        Path(profile_root) / "ms-playwright"
        if windows
        else Path(profile_root) / ".cache" / "ms-playwright"
    )


def _validated_live_e2e_specs(
    specs: Sequence[str] | None, *, mode: str
) -> tuple[str, ...]:
    """Return only distinct, canonical full-suite paths from the reviewed list."""
    if mode not in {"smoke", "full"}:
        raise StandError("live E2E mode must be smoke or full")
    if specs is None:
        return ()
    if isinstance(specs, str) or not isinstance(specs, Sequence):
        raise StandError("invalid live E2E focused selection")
    if not specs:
        return ()
    if mode != "full" or len(specs) > len(_PLAYWRIGHT_FAILURE_DECLARATION_SOURCES):
        raise StandError("invalid live E2E focused selection")
    if any(
        type(spec) is not str
        or not spec.isascii()
        or spec not in _PLAYWRIGHT_FAILURE_DECLARATION_SOURCES
        for spec in specs
    ):
        raise StandError("invalid live E2E focused selection")
    if len(set(specs)) != len(specs):
        raise StandError("invalid live E2E focused selection")
    selected = set(specs)
    return tuple(
        source
        for source in _PLAYWRIGHT_FAILURE_DECLARATION_SOURCES
        if source in selected
    )


def _live_e2e_probe_selected(mode: str, selected_specs: Sequence[str]) -> bool:
    """Enable the proof exactly when its fixed spec is in the chosen lane."""
    if mode == "smoke":
        return LIVE_CADDY_PROBE_SPEC in LIVE_E2E_SMOKE_FILES
    return mode == "full" and (
        not selected_specs or LIVE_CADDY_PROBE_SPEC in selected_specs
    )


def _live_e2e_command(
    *,
    mode: str = "full",
    platform: str | None = None,
    specs: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Return a fixed, secret-free launcher for the requested live suite."""
    selected_specs = _validated_live_e2e_specs(specs, mode=mode)
    selected_files = LIVE_E2E_SMOKE_FILES if mode == "smoke" else selected_specs
    if (platform or os.name) == "nt":
        if not selected_files:
            return LIVE_E2E_WINDOWS_COMMAND
        return (
            *LIVE_E2E_WINDOWS_COMMAND[:-1],
            f"{LIVE_E2E_WINDOWS_COMMAND[-1]} -- {' '.join(selected_files)}",
        )
    if not selected_files:
        return LIVE_E2E_COMMAND
    return (*LIVE_E2E_COMMAND, "--", *selected_files)


def _live_e2e_npm_ci_command(*, platform: str | None = None) -> tuple[str, ...]:
    """Return a fixed npm-ci launcher without interpolated arguments."""
    if (platform or os.name) == "nt":
        return LIVE_E2E_WINDOWS_NPM_CI_COMMAND
    return LIVE_E2E_NPM_CI_COMMAND


def _live_e2e_installer_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Keep secrets, endpoints, test output paths, and user npm config out of npm."""
    installer_environment = _live_e2e_runtime_environment(environment)
    for name in (
        "NPM_CONFIG_USERCONFIG",
        "NPM_CONFIG_GLOBALCONFIG",
        "PLAYWRIGHT_BROWSERS_PATH",
    ):
        value = environment.get(name)
        if not value:
            raise StandError(f"{name} is required for the live E2E dependency check")
        installer_environment[name] = value
    installer_environment["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
    return installer_environment


def _live_e2e_package_manifest_fingerprint(
    frontend: Path,
) -> tuple[str, dict[str, str]]:
    """Hash both npm manifests and read exact locked Playwright versions."""
    package_path = frontend / "package.json"
    lock_path = frontend / "package-lock.json"
    try:
        package_bytes = package_path.read_bytes()
        lock_bytes = lock_path.read_bytes()
        package_data = json.loads(package_bytes)
        lock_data = json.loads(lock_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise StandError(
            "live E2E requires readable frontend package manifests"
        ) from error
    if not isinstance(package_data, dict):
        raise StandError("frontend package.json must contain a JSON object")
    packages = lock_data.get("packages") if isinstance(lock_data, dict) else None
    if not isinstance(packages, dict):
        raise StandError("live E2E package lock does not contain a package inventory")

    versions: dict[str, str] = {}
    for package_name in LIVE_E2E_REQUIRED_PACKAGES:
        package = packages.get(f"node_modules/{package_name}")
        version = package.get("version") if isinstance(package, dict) else None
        if not isinstance(version, str) or not version:
            raise StandError(
                "live E2E package lock omits a required Playwright package"
            )
        versions[package_name] = version

    fingerprint = hashlib.sha256()
    for manifest_name, manifest_bytes in (
        (package_path.name, package_bytes),
        (lock_path.name, lock_bytes),
    ):
        name_bytes = manifest_name.encode("utf-8")
        fingerprint.update(len(name_bytes).to_bytes(2, "big"))
        fingerprint.update(name_bytes)
        fingerprint.update(len(manifest_bytes).to_bytes(8, "big"))
        fingerprint.update(manifest_bytes)
    return fingerprint.hexdigest(), versions


def _installed_live_e2e_packages_match(
    frontend: Path, locked_versions: Mapping[str, str]
) -> bool:
    """Check that required Playwright packages match the current lockfile."""
    node_modules = frontend / "node_modules"
    for package_name, locked_version in locked_versions.items():
        package_json = node_modules / package_name / "package.json"
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if (
            not isinstance(package_data, dict)
            or package_data.get("version") != locked_version
        ):
            return False
    return True


def _run_live_e2e_npm_ci(frontend: Path, environment: Mapping[str, str]) -> None:
    """Install the checked-in lockfile with a minimal environment and hidden output."""
    command = _live_e2e_npm_ci_command()
    installer_environment = _live_e2e_installer_environment(environment)
    print("+ npm ci", flush=True)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed platform-specific argv
            command,
            cwd=frontend,
            env=installer_environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise StandError(
            "could not launch the locked live E2E dependency install"
        ) from error

    return_code = completed.returncode
    completed.stdout = ""
    completed.stderr = ""
    del completed
    if return_code != 0:
        raise StandError("locked live E2E dependency installation failed")


def _probe_live_e2e_chromium(frontend: Path, environment: Mapping[str, str]) -> None:
    """Verify the shared Chromium executable is present without launching it."""
    installer_environment = _live_e2e_installer_environment(environment)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed local package probe
            LIVE_E2E_CHROMIUM_PROBE_COMMAND,
            cwd=frontend,
            env=installer_environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise StandError("could not inspect the cached live E2E browser") from error

    return_code = completed.returncode
    executable_path = (completed.stdout or "").strip()
    completed.stdout = ""
    completed.stderr = ""
    del completed
    browser_cache = Path(environment["PLAYWRIGHT_BROWSERS_PATH"])
    try:
        cache_root = browser_cache.resolve(strict=True)
        executable = Path(executable_path).resolve(strict=True)
        executable_is_cached = executable.is_relative_to(cache_root)
        executable_is_file = executable.is_file()
    except (OSError, RuntimeError, ValueError):
        executable_is_cached = False
        executable_is_file = False
    if (
        return_code != 0
        or not executable_path
        or not executable_is_cached
        or not executable_is_file
    ):
        raise StandError("the shared Playwright Chromium executable is unavailable")
    print("live E2E browser=ready name=chromium", flush=True)


def _ensure_live_e2e_dependencies(
    frontend: Path, environment: Mapping[str, str]
) -> None:
    """Install locked Playwright packages when stale, then verify shared Chromium."""
    manifest_fingerprint, locked_versions = _live_e2e_package_manifest_fingerprint(
        frontend
    )
    node_modules = frontend / "node_modules"
    fingerprint_path = node_modules / LIVE_E2E_MANIFEST_FINGERPRINT
    try:
        installed_fingerprint = fingerprint_path.read_text(encoding="ascii").strip()
    except OSError:
        installed_fingerprint = ""
    dependencies_are_ready = (
        installed_fingerprint == manifest_fingerprint
        and _installed_live_e2e_packages_match(frontend, locked_versions)
    )
    if not dependencies_are_ready:
        _run_live_e2e_npm_ci(frontend, environment)
        if not _installed_live_e2e_packages_match(frontend, locked_versions):
            raise StandError("locked Playwright packages are missing after npm ci")
        node_modules.mkdir(parents=True, exist_ok=True)
        temporary_fingerprint = fingerprint_path.with_name(
            f"{fingerprint_path.name}.tmp"
        )
        temporary_fingerprint.write_text(manifest_fingerprint, encoding="ascii")
        temporary_fingerprint.replace(fingerprint_path)
    _probe_live_e2e_chromium(frontend, environment)


_PLAYWRIGHT_COUNT_LINE = re.compile(
    r" *(?P<count>0|[1-9][0-9]{0,4}) "
    r"(?P<kind>passed|failed|skipped|flaky|interrupted|did not run)"
    r"(?: \([0-9]{1,8}(?:\.[0-9])?(?:ms|s|m|h|d)\))? *"
)
_PLAYWRIGHT_FAILURE_HEADER = re.compile(
    r"  [1-9][0-9]{0,3}\) \[(?P<project>desktop|mobile)\] › "
    r"(?P<source>[^ :]{1,160}):(?P<line>[1-9][0-9]{0,4}):"
    r"(?P<column>[1-9][0-9]{0,4}) › "
)
_PLAYWRIGHT_FAILURE_DECLARATION_SOURCES = (
    "tests/e2e-live/activity-dashboard.live.spec.ts",
    "tests/e2e-live/activity-summary.live.spec.ts",
    "tests/e2e-live/admin-audit-rbac.live.spec.ts",
    "tests/e2e-live/admin-feature-flags-rbac.live.spec.ts",
    "tests/e2e-live/admin-notifications-rbac.live.spec.ts",
    "tests/e2e-live/admin-stories-rbac.live.spec.ts",
    "tests/e2e-live/admin-stories-smoke.live.spec.ts",
    "tests/e2e-live/admin-users-rbac.live.spec.ts",
    "tests/e2e-live/auth-login-lockout.live.spec.ts",
    "tests/e2e-live/auth-roles.live.spec.ts",
    "tests/e2e-live/auth-safe-redirect.live.spec.ts",
    "tests/e2e-live/avatar-persistence.live.spec.ts",
    "tests/e2e-live/chat-attachment-isolation.live.spec.ts",
    "tests/e2e-live/core-a11y-live.live.spec.ts",
    "tests/e2e-live/email-otp-mfa-login.live.spec.ts",
    "tests/e2e-live/email-otp-verification.live.spec.ts",
    "tests/e2e-live/events-scroll-restoration.live.spec.ts",
    "tests/e2e-live/events-tab-keyboard.live.spec.ts",
    "tests/e2e-live/footer-bottom-navigation.live.spec.ts",
    "tests/e2e-live/map-gesture-isolation.live.spec.ts",
    "tests/e2e-live/map-zoom-longtask.live.spec.ts",
    "tests/e2e-live/messenger-a11y.live.spec.ts",
    "tests/e2e-live/messenger-focus-trap.live.spec.ts",
    "tests/e2e-live/messenger-group-isolation.live.spec.ts",
    "tests/e2e-live/messenger-keyboard-focus.live.spec.ts",
    "tests/e2e-live/messenger-membership-revocation.live.spec.ts",
    "tests/e2e-live/messenger-realtime.live.spec.ts",
    "tests/e2e-live/messenger-reconnect-ordering.live.spec.ts",
    "tests/e2e-live/messenger-reconnect.live.spec.ts",
    "tests/e2e-live/messenger-unread-read.live.spec.ts",
    "tests/e2e-live/navbar-layout-stability.live.spec.ts",
    "tests/e2e-live/new-chat-hit-targets.live.spec.ts",
    "tests/e2e-live/news-responsive-matrix.live.spec.ts",
    "tests/e2e-live/news-scroll-restoration.live.spec.ts",
    "tests/e2e-live/not-found-i18n.live.spec.ts",
    "tests/e2e-live/notification-in-app.live.spec.ts",
    "tests/e2e-live/notification-preferences.live.spec.ts",
    "tests/e2e-live/notification-topics-delivery.live.spec.ts",
    "tests/e2e-live/password-reset.live.spec.ts",
    "tests/e2e-live/profile-csrf.live.spec.ts",
    "tests/e2e-live/profile-persistence.live.spec.ts",
    "tests/e2e-live/push-delivery.live.spec.ts",
    "tests/e2e-live/push-permission-default.live.spec.ts",
    "tests/e2e-live/push-permission-denied.live.spec.ts",
    "tests/e2e-live/push-subscription.live.spec.ts",
    "tests/e2e-live/pwa-offline-shell-i18n.live.spec.ts",
    "tests/e2e-live/pwa-offline-shell.live.spec.ts",
    "tests/e2e-live/register-double-submit.live.spec.ts",
    "tests/e2e-live/schedule-200-equivalent-reflow.live.spec.ts",
    "tests/e2e-live/schedule-grid-keyboard.live.spec.ts",
    "tests/e2e-live/schedule-hydration-i18n.live.spec.ts",
    "tests/e2e-live/search-dialog-keyboard.live.spec.ts",
    "tests/e2e-live/settings-password-change-rollback.live.spec.ts",
    "tests/e2e-live/settings-radio-focus.live.spec.ts",
    "tests/e2e-live/settings-tabs-keyboard.live.spec.ts",
    "tests/e2e-live/settings-theme-roundtrip.live.spec.ts",
    "tests/e2e-live/ssr-hydration-i18n.live.spec.ts",
    "tests/e2e-live/story-viewer-keyboard.live.spec.ts",
    "tests/e2e-live/story-viewer-memory.live.spec.ts",
    "tests/e2e-live/story-viewer-reduced-motion.live.spec.ts",
    "tests/e2e-live/totp-recovery.live.spec.ts",
    "tests/e2e-live/zzz-aud174-prehydration-caddy-log.live.spec.ts",
)
_PLAYWRIGHT_FAILURE_SOURCES = {
    **{source: source for source in _PLAYWRIGHT_FAILURE_DECLARATION_SOURCES},
    **{
        source.replace("/", "\\"): source
        for source in _PLAYWRIGHT_FAILURE_DECLARATION_SOURCES
    },
}
_PLAYWRIGHT_FAILURE_FRAME_SOURCES = {
    **_PLAYWRIGHT_FAILURE_SOURCES,
    "tests/e2e-live/fixtures.ts": "tests/e2e-live/fixtures.ts",
    r"tests\e2e-live\fixtures.ts": "tests/e2e-live/fixtures.ts",
}
_PLAYWRIGHT_FAILURE_PROJECTS = {project: project for project in ("desktop", "mobile")}
_PLAYWRIGHT_FAILURE_FRAME = re.compile(
    r"        at (?:[^()]{1,256} \((?P<named>.+)\)|(?P<anonymous>.+))"
)
_PLAYWRIGHT_FRAME_LOCATION = re.compile(
    r"(?P<source>.{1,1024}):(?P<line>[1-9][0-9]{0,4}):"
    r"(?P<column>[1-9][0-9]{0,4})"
)
_PLAYWRIGHT_A11Y_CONTRAST_LINE = re.compile(
    r"UE_LIVE_A11Y_CONTRAST_V1 project=(?P<project>desktop|mobile) "
    r"route=(?P<route>dashboard|settings) "
    r"fg=(?P<foreground>#[0-9a-fA-F]{6}) bg=(?P<background>#[0-9a-fA-F]{6}) "
    r"ratio_milli=(?P<ratio>0|[1-9][0-9]{0,4})"
)
_PLAYWRIGHT_A11Y_CONTRAST_LIMIT = 16
_PLAYWRIGHT_A11Y_CONTRAST_PER_ROUTE_LIMIT = 4
_PlaywrightA11yContrast = tuple[str, str, str, str, int]

_PLAYWRIGHT_A11Y_PAINT_LINE = re.compile(
    r"UE_LIVE_A11Y_PAINT_V1 project=(?P<project>desktop|mobile) "
    r"route=(?P<route>dashboard|settings) "
    r"axe_fg=(?P<axe_foreground>#[0-9a-fA-F]{6}) "
    r"axe_bg=(?P<axe_background>#[0-9a-fA-F]{6}) "
    r"ratio_milli=(?P<ratio>0|[1-9][0-9]{0,4}) "
    r"css_fg=(?P<css_foreground>#[0-9a-fA-F]{6}) "
    r"text_color=(?P<text_color>opaque|translucent|transparent) "
    r"css_alpha_milli=(?P<css_alpha>0|[1-9][0-9]{0,2}|1000) "
    r"node_opacity_milli=(?P<node_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"ancestor_opacity_milli=(?P<ancestor_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"opacity_tag=(?P<opacity_tag>none|node|ancestor|fade|layout|fade-pending|multiple) "
    r"page_ready=(?P<page_ready>true|false) "
    r"page_opacity_milli=(?P<page_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"layout_opacity_milli=(?P<layout_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"animation=(?P<animation>none|opacity|transform|color|other|mixed) "
    r"active_animations=(?P<active_animations>0|[1-9][0-9]{0,2})"
)
_PLAYWRIGHT_A11Y_PAINT_LIMIT = 16
_PLAYWRIGHT_A11Y_PAINT_PER_ROUTE_LIMIT = 4
_PlaywrightA11yPaintState = tuple[
    str, str, str, str, int, str, str, int, int, int, str, bool, int, int, str, int
]

_PLAYWRIGHT_A11Y_PHASE_LINE = re.compile(
    r"UE_LIVE_A11Y_PHASE_V1 project=(?P<project>desktop|mobile) "
    r"route=(?P<route>dashboard|settings) "
    r"phase=(?P<phase>before_axe|after_axe) "
    r"page_ready=(?P<page_ready>true|false) "
    r"page_opacity_milli=(?P<page_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"root_opacity_milli=(?P<root_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"layout_opacity_milli=(?P<layout_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"animation=(?P<animation>none|opacity|transform|color|other|mixed) "
    r"active_animations=(?P<active_animations>0|[1-9][0-9]{0,2})"
)
_PLAYWRIGHT_A11Y_PHASE_LIMIT = 16
_PlaywrightA11yPhaseState = tuple[str, str, str, bool, int, int, int, str, int]

_PLAYWRIGHT_FOOTER_GEOMETRY_LINE = re.compile(
    r"UE_LIVE_FOOTER_GEOM_V1 project=(?P<project>desktop|mobile) "
    r"req_w_milli=(?P<requested_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"req_h_milli=(?P<requested_height>-?(?:0|[1-9][0-9]{0,6})) "
    r"inner_w_milli=(?P<inner_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"inner_h_milli=(?P<inner_height>-?(?:0|[1-9][0-9]{0,6})) "
    r"client_w_milli=(?P<client_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"scroll_w_milli=(?P<scroll_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_left_milli=(?P<nav_left>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_right_milli=(?P<nav_right>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_top_milli=(?P<nav_top>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_bottom_milli=(?P<nav_bottom>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_width_milli=(?P<nav_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_transform_present=(?P<nav_transform_present>true|false) "
    r"nav_tx_milli=(?P<nav_tx>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_ty_milli=(?P<nav_ty>-?(?:0|[1-9][0-9]{0,6})) "
    r"fixed_cb_found=(?P<fixed_cb_found>true|false) "
    r"fixed_cb_depth=(?P<fixed_cb_depth>0|[1-9][0-9]{0,1}|32) "
    r"cb_left_milli=(?P<cb_left>-?(?:0|[1-9][0-9]{0,6})) "
    r"cb_right_milli=(?P<cb_right>-?(?:0|[1-9][0-9]{0,6})) "
    r"cb_top_milli=(?P<cb_top>-?(?:0|[1-9][0-9]{0,6})) "
    r"cb_bottom_milli=(?P<cb_bottom>-?(?:0|[1-9][0-9]{0,6}))"
)
_PLAYWRIGHT_FOOTER_GEOMETRY_LIMIT = 16
_PlaywrightFooterGeometry = tuple[
    str,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    bool,
    int,
    int,
    bool,
    int,
    int,
    int,
    int,
    int,
]


_PLAYWRIGHT_NEWS_VIEWPORT_LINE = re.compile(
    r"UE_LIVE_NEWS_VIEWPORT_V1 project=(?P<project>desktop|mobile) "
    r"language=(?P<language>ru|en) "
    r"width=(?P<width>360|390|768|1024|1440) "
    r"viewportHeight=(?P<viewport_height>[1-9][0-9]{0,5}) "
    r"scrollY=(?P<scroll_y>-?(?:0|[1-9][0-9]{0,5})) "
    r"top=(?P<top>-?(?:0|[1-9][0-9]{0,5})) "
    r"bottom=(?P<bottom>-?(?:0|[1-9][0-9]{0,5})) "
    r"left=(?P<left>-?(?:0|[1-9][0-9]{0,5})) "
    r"right=(?P<right>-?(?:0|[1-9][0-9]{0,5}))"
)
_PLAYWRIGHT_NEWS_VIEWPORT_LIMIT = 20
_PlaywrightNewsViewport = tuple[str, str, int, int, int, int, int, int, int]


_PlaywrightPushObservation = tuple[str, str, str, str, bool, bool, int]
_PLAYWRIGHT_PUSH_OBSERVATION_LINE = re.compile(
    r"UE_LIVE_PUSH_OBS_V1 project=(?P<project>desktop|mobile) "
    r"permission=(?P<permission>default|granted|denied|unsupported) "
    r"ready=(?P<ready>resolved|timeout|error) "
    r"state=(?P<state>missing|installing|installed|activating|"
    r"activated|redundant|error) "
    r"controller=(?P<controller>[01]) subscription=(?P<subscription>[01]) "
    r"matches=(?P<matches>[01])"
)
_PLAYWRIGHT_PUSH_OBSERVATION_LIMIT = 4

_PLAYWRIGHT_STORY_MEMORY_PREFIX = "STORY_MEMORY_DIAG "
_PLAYWRIGHT_STORY_MEMORY_LINE_BYTES_LIMIT = 8192
_PLAYWRIGHT_STORY_MEMORY_RECORD_LIMIT = 4
_PLAYWRIGHT_STORY_MEMORY_MAX_COUNT = 9_007_199_254_740_991
_PLAYWRIGHT_STORY_MEMORY_DOM_KEYS = ("documents", "nodes", "jsEventListeners")
_PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS = ("window", "document", "documentTree")
_PLAYWRIGHT_STORY_MEMORY_LISTENER_KEYS = (
    "total",
    "appinstalled",
    "beforeinstallprompt",
    "visibilitychange",
    "focus",
    "blur",
    "focusin",
    "focusout",
    "keydown",
    "keyup",
    "click",
    "ecosystem:push-education-requested",
    "mousedown",
    "mouseup",
    "pointerdown",
    "pointerup",
    "touchstart",
    "touchend",
    "online",
    "offline",
    "pwa:need-refresh",
    "resize",
    "scroll",
    "other",
)
_PLAYWRIGHT_STORY_MEMORY_RECORD_KEYS = (
    "schema",
    "project",
    "phase",
    "diagnosticStatus",
    "warmDOM",
    "cycle0DOM",
    "warmListeners",
    "cycle0Listeners",
)
_PlaywrightStoryMemoryRecord = dict[str, object]

_STORY_MEMORY_CYCLE_TRACE_PREFIX = "STORY_MEMORY_CYCLE_TRACE_DIAG "
_STORY_MEMORY_CYCLE_TRACE_KEYS = (
    "schema",
    "project",
    "diagnosticStatus",
    "samples",
)
_STORY_MEMORY_CYCLE_TRACE_SAMPLE_KEYS = (
    "baseline",
    "dialogOpen",
    "hiddenResumed",
    "afterCloseSettled",
)
_STORY_MEMORY_CYCLE_TRACE_COUNT_KEYS = ("documents", "nodes", "jsEventListeners")
_STORY_MEMORY_CYCLE_TRACE_LINE_BYTES_LIMIT = 2048
_STORY_MEMORY_CYCLE_TRACE_RECORD_LIMIT = 4


def _validated_story_memory_cycle_trace(value: object) -> dict[str, object] | None:
    record = _story_memory_object(value, _STORY_MEMORY_CYCLE_TRACE_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    status = record["diagnosticStatus"]
    if project not in ("desktop", "mobile") or status not in (
        "available",
        "partial",
        "unavailable",
    ):
        return None
    samples = _story_memory_object(
        record["samples"], _STORY_MEMORY_CYCLE_TRACE_SAMPLE_KEYS
    )
    if samples is None:
        return None
    normalized_samples: dict[str, dict[str, int] | None] = {}
    present = 0
    for sample_name in _STORY_MEMORY_CYCLE_TRACE_SAMPLE_KEYS:
        sample = samples[sample_name]
        if sample is None:
            normalized_samples[sample_name] = None
            continue
        counts = _story_memory_object(sample, _STORY_MEMORY_CYCLE_TRACE_COUNT_KEYS)
        if counts is None:
            return None
        normalized: dict[str, int] = {}
        for key in _STORY_MEMORY_CYCLE_TRACE_COUNT_KEYS:
            count = counts[key]
            if (
                type(count) is not int
                or count < 0
                or count > _PLAYWRIGHT_STORY_MEMORY_MAX_COUNT
            ):
                return None
            normalized[key] = count
        present += 1
        normalized_samples[sample_name] = normalized
    if (
        (status == "available" and present != 4)
        or (status == "partial" and not 1 <= present <= 3)
        or (status == "unavailable" and present != 0)
    ):
        return None
    return {
        "schema": 1,
        "project": project,
        "diagnosticStatus": status,
        "samples": normalized_samples,
    }


def _live_playwright_story_memory_cycle_trace_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _STORY_MEMORY_CYCLE_TRACE_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_STORY_MEMORY_CYCLE_TRACE_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_STORY_MEMORY_CYCLE_TRACE_PREFIX) :],
                object_pairs_hook=_story_memory_json_object,
                parse_constant=_reject_story_memory_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_story_memory_cycle_trace(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _STORY_MEMORY_CYCLE_TRACE_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


def _story_memory_object(
    value: object, expected_keys: tuple[str, ...]
) -> Mapping[str, object] | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    if set(value) != set(expected_keys):
        return None
    return value


def _story_memory_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate Story diagnostic key")
        value[key] = item
    return value


def _reject_story_memory_json_constant(value: str) -> None:
    raise ValueError(f"invalid Story diagnostic number: {value}")


def _story_memory_counts(
    value: object, expected_keys: tuple[str, ...], *, unavailable: bool
) -> dict[str, int | None] | None:
    record = _story_memory_object(value, expected_keys)
    if record is None:
        return None
    counts: dict[str, int | None] = {}
    for key in expected_keys:
        count = record[key]
        if unavailable:
            if count is not None:
                return None
            counts[key] = None
            continue
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > _PLAYWRIGHT_STORY_MEMORY_MAX_COUNT
        ):
            return None
        counts[key] = count
    if not unavailable and "total" in counts:
        bucket_total = sum(
            count
            for key, count in counts.items()
            if key != "total" and count is not None
        )
        if bucket_total != counts["total"]:
            return None
    return counts


def _validated_story_memory_record(
    value: object,
) -> _PlaywrightStoryMemoryRecord | None:
    record = _story_memory_object(value, _PLAYWRIGHT_STORY_MEMORY_RECORD_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 2:
        return None
    project = record["project"]
    phase = record["phase"]
    status = record["diagnosticStatus"]
    if project not in ("desktop", "mobile"):
        return None
    if phase != "cycle0-after-settle-before-assertion":
        return None
    if status not in ("available", "unavailable"):
        return None

    unavailable = status == "unavailable"
    warm_dom = _story_memory_counts(
        record["warmDOM"], _PLAYWRIGHT_STORY_MEMORY_DOM_KEYS, unavailable=unavailable
    )
    cycle0_dom = _story_memory_counts(
        record["cycle0DOM"], _PLAYWRIGHT_STORY_MEMORY_DOM_KEYS, unavailable=unavailable
    )
    warm_listeners = _story_memory_object(
        record["warmListeners"], _PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS
    )
    cycle0_listeners = _story_memory_object(
        record["cycle0Listeners"], _PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS
    )
    if (
        warm_dom is None
        or cycle0_dom is None
        or warm_listeners is None
        or cycle0_listeners is None
    ):
        return None

    normalized_warm_listeners: dict[str, dict[str, int | None]] = {}
    normalized_cycle0_listeners: dict[str, dict[str, int | None]] = {}
    for target in _PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS:
        warm_counts = _story_memory_counts(
            warm_listeners[target],
            _PLAYWRIGHT_STORY_MEMORY_LISTENER_KEYS,
            unavailable=unavailable,
        )
        cycle0_counts = _story_memory_counts(
            cycle0_listeners[target],
            _PLAYWRIGHT_STORY_MEMORY_LISTENER_KEYS,
            unavailable=unavailable,
        )
        if warm_counts is None or cycle0_counts is None:
            return None
        normalized_warm_listeners[target] = warm_counts
        normalized_cycle0_listeners[target] = cycle0_counts

    return {
        "schema": 2,
        "project": project,
        "phase": "cycle0-after-settle-before-assertion",
        "diagnosticStatus": status,
        "warmDOM": warm_dom,
        "cycle0DOM": cycle0_dom,
        "warmListeners": normalized_warm_listeners,
        "cycle0Listeners": normalized_cycle0_listeners,
    }


def _live_playwright_story_memory_records(
    output: str,
) -> list[_PlaywrightStoryMemoryRecord]:
    """Accept only the closed, byte-bounded Story memory diagnostic protocol."""
    records: list[_PlaywrightStoryMemoryRecord] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PLAYWRIGHT_STORY_MEMORY_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PLAYWRIGHT_STORY_MEMORY_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PLAYWRIGHT_STORY_MEMORY_PREFIX) :],
                object_pairs_hook=_story_memory_json_object,
                parse_constant=_reject_story_memory_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_story_memory_record(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PLAYWRIGHT_STORY_MEMORY_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PLAYWRIGHT_STORY_SETUP_PREFIX = "STORY_SETUP_DIAG "
_PLAYWRIGHT_STORY_SETUP_LINE_BYTES_LIMIT = 512
_PLAYWRIGHT_STORY_SETUP_RECORD_LIMIT = 4
_PLAYWRIGHT_STORY_SETUP_KEYS = ("schema", "project", "stage", "exceptionKind")
_PLAYWRIGHT_STORY_SETUP_STAGES = (
    "browser-launch",
    "fixture-policy",
    "owner-cdp",
    "command-line",
    "debug-port",
    "cdp-attach",
    "default-context",
    "cookies",
    "main-target",
    "project-options",
    "bootstrap-listener",
    "login",
    "dashboard",
    "bootstrap",
    "story-trigger",
    "warm-up",
    "baseline",
    "cycle0",
    "measured-cycle",
    "acceptance",
    "cleanup",
)
_PLAYWRIGHT_STORY_SETUP_EXCEPTION_KINDS = (
    "error",
    "non-error",
    "cleanup",
    "error-with-cleanup",
    "non-error-with-cleanup",
)


def _validated_story_setup_record(value: object) -> dict[str, object] | None:
    record = _story_memory_object(value, _PLAYWRIGHT_STORY_SETUP_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    stage = record["stage"]
    exception_kind = record["exceptionKind"]
    if not isinstance(project, str) or project not in ("desktop", "mobile"):
        return None
    if not isinstance(stage, str) or stage not in _PLAYWRIGHT_STORY_SETUP_STAGES:
        return None
    if (
        not isinstance(exception_kind, str)
        or exception_kind not in _PLAYWRIGHT_STORY_SETUP_EXCEPTION_KINDS
    ):
        return None
    return {
        "schema": 1,
        "project": project,
        "stage": stage,
        "exceptionKind": exception_kind,
    }


def _live_playwright_story_setup_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    """Accept only closed, byte-bounded Story setup failures from stdout."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PLAYWRIGHT_STORY_SETUP_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PLAYWRIGHT_STORY_SETUP_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PLAYWRIGHT_STORY_SETUP_PREFIX) :],
                object_pairs_hook=_story_memory_json_object,
                parse_constant=_reject_story_memory_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_story_setup_record(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PLAYWRIGHT_STORY_SETUP_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_AUTH_UI_DIAG_PREFIX = "AUTH_UI_DIAG "
_AUTH_HTTP_DIAG_PREFIX = "AUTH_HTTP_DIAG "
_AUTH_DIAG_LINE_BYTES_LIMIT = 1024
_AUTH_DIAG_RECORD_LIMIT = 16
_AUTH_UI_DIAG_KEYS = (
    "schema",
    "project",
    "scenario",
    "status",
    "detailClass",
    "alertCount",
    "alertCountCapped",
    "alertVisible",
    "currentFieldInvalid",
    "loginChallenge",
    "pageError",
)
_AUTH_UI_DIAG_SCENARIOS = ("password_current_invalid", "totp_recovery_replay")
_AUTH_UI_DIAG_DETAIL_CLASSES = ("expected", "other-string", "non-string", "missing")
_AUTH_HTTP_DIAG_KEYS = ("schema", "project", "operation", "expectedStatus", "status")
_AUTH_HTTP_DIAG_EXPECTED_STATUS = {
    operation: (
        403
        if operation == "student_admin_read"
        else 400
        if operation in {"password_change_invalid", "totp_recovery_replay"}
        else 200
    )
    for operation in (
        "profile_read",
        "profile_identity_read",
        "password_settings_register",
        "totp_register",
        "password_change_invalid",
        "password_change_save",
        "totp_recovery_accept",
        "totp_recovery_replay",
        "push_topics_read",
        "push_subscribe",
        "push_topics_initial",
        "push_topics_optout",
        "push_unsubscribe",
        "push_rebind",
        "profile_update_enable",
        "profile_update_start",
        "profile_update_end",
        "profile_update_midnight_start",
        "profile_update_midnight_end",
        "profile_update_disable",
        "student_admin_read",
        "admin_topics_read",
        "admin_account_search",
        "admin_account_delete",
    )
}


def _auth_diag_object(
    value: object, expected_keys: tuple[str, ...]
) -> Mapping[str, object] | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    if set(value) != set(expected_keys):
        return None
    return value


def _auth_diag_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate auth diagnostic key")
        value[key] = item
    return value


def _reject_auth_diag_json_constant(value: str) -> None:
    raise ValueError(f"invalid auth diagnostic number: {value}")


def _validated_auth_ui_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _AUTH_UI_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    scenario = record["scenario"]
    status = record["status"]
    detail_class = record["detailClass"]
    alert_count = record["alertCount"]
    capped = record["alertCountCapped"]
    alert_visible = record["alertVisible"]
    current_invalid = record["currentFieldInvalid"]
    login_challenge = record["loginChallenge"]
    page_error = record["pageError"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    if not isinstance(scenario, str) or scenario not in _AUTH_UI_DIAG_SCENARIOS:
        return None
    if type(status) is not int or not 100 <= status <= 599:
        return None
    if (
        not isinstance(detail_class, str)
        or detail_class not in _AUTH_UI_DIAG_DETAIL_CLASSES
    ):
        return None
    if type(alert_count) is not int or not 0 <= alert_count <= 8:
        return None
    if type(capped) is not bool or (capped and alert_count != 8):
        return None
    if type(alert_visible) is not bool:
        return None
    if type(page_error) is not bool:
        return None
    if scenario == "password_current_invalid":
        if type(current_invalid) is not bool or login_challenge is not None:
            return None
    elif current_invalid is not None or type(login_challenge) is not bool:
        return None
    return {
        "schema": 1,
        "project": project,
        "scenario": scenario,
        "status": status,
        "detailClass": detail_class,
        "alertCount": alert_count,
        "alertCountCapped": capped,
        "alertVisible": alert_visible,
        "currentFieldInvalid": current_invalid,
        "loginChallenge": login_challenge,
        "pageError": page_error,
    }


def _live_playwright_auth_ui_diagnostics(output: str) -> list[dict[str, object]]:
    """Retain only complete bounded Auth UI failure records from stdout."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _AUTH_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_AUTH_UI_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_AUTH_UI_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_auth_ui_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _AUTH_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


def _validated_auth_http_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _AUTH_HTTP_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    operation = record["operation"]
    expected_status = record["expectedStatus"]
    status = record["status"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    if (
        not isinstance(operation, str)
        or operation not in _AUTH_HTTP_DIAG_EXPECTED_STATUS
    ):
        return None
    if (
        type(expected_status) is not int
        or expected_status != _AUTH_HTTP_DIAG_EXPECTED_STATUS[operation]
    ):
        return None
    if type(status) is not int or not 100 <= status <= 599:
        return None
    if status == expected_status:
        return None
    return {
        "schema": 1,
        "project": project,
        "operation": operation,
        "expectedStatus": expected_status,
        "status": status,
    }


_AUTH_REGISTRATION_DIAG_PREFIX = "AUTH_REGISTRATION_DIAG "
_AUTH_REGISTRATION_DIAG_KEYS = (
    "schema",
    "project",
    "scenario",
    "phase",
    "formValid",
    "submitEnabled",
    "requestObserved",
    "status",
)
_AUTH_REGISTRATION_DIAG_SCENARIOS = ("password-settings", "totp", "email-otp")
_AUTH_REGISTRATION_DIAG_PHASES = (
    "before-submit",
    "submit-click",
    "response-wait",
    "response-received",
    "navigation",
)
_AUTH_REGISTRATION_DIAG_LINE_BYTES_LIMIT = 512
_AUTH_REGISTRATION_DIAG_RECORD_LIMIT = 4


def _validated_auth_registration_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _AUTH_REGISTRATION_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    scenario = record["scenario"]
    phase = record["phase"]
    form_valid = record["formValid"]
    submit_enabled = record["submitEnabled"]
    request_observed = record["requestObserved"]
    status = record["status"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    if (
        not isinstance(scenario, str)
        or scenario not in _AUTH_REGISTRATION_DIAG_SCENARIOS
    ):
        return None
    if not isinstance(phase, str) or phase not in _AUTH_REGISTRATION_DIAG_PHASES:
        return None
    if type(form_valid) is not bool or type(submit_enabled) is not bool:
        return None
    if type(request_observed) is not bool:
        return None
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        return None
    if phase == "before-submit" and (request_observed or status is not None):
        return None
    if phase == "submit-click" and status is not None and not request_observed:
        return None
    if phase == "response-wait" and status is not None:
        return None
    if phase in {"response-received", "navigation"} and (
        not request_observed or status is None
    ):
        return None
    return {
        "schema": 1,
        "project": project,
        "scenario": scenario,
        "phase": phase,
        "formValid": form_valid,
        "submitEnabled": submit_enabled,
        "requestObserved": request_observed,
        "status": status,
    }


def _live_playwright_auth_registration_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    """Retain only closed registration-failure rows from complete stdout lines."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _AUTH_REGISTRATION_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_AUTH_REGISTRATION_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_AUTH_REGISTRATION_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_auth_registration_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _AUTH_REGISTRATION_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_REGISTRATION_ADMISSION_DIAG_PREFIX = "REGISTRATION_ADMISSION_DIAG "
_REGISTRATION_ADMISSION_DIAG_KEYS = (
    "schema",
    "project",
    "stage",
    "errorClass",
    "nodeCode",
    "cost",
    "timeoutMs",
    "remainingMs",
    "requestCount",
    "activeRequestCount",
    "deadlineAvailable",
    "ownerPresent",
    "ledgerPresent",
    "requestObserved",
    "responseObserved",
    "actionFailed",
    "status",
)
_REGISTRATION_ADMISSION_DIAG_STAGES = (
    "deadline",
    "origin",
    "state-root",
    "owner-read",
    "ledger-read",
    "quiet-wait",
    "rolling-wait",
    "reserve",
    "submit",
    "request-drain",
    "confirm",
)
_REGISTRATION_ADMISSION_DIAG_ERROR_CLASSES = (
    "Error",
    "TypeError",
    "RangeError",
    "ReferenceError",
    "SyntaxError",
    "URIError",
    "EvalError",
    "AggregateError",
    "AbortError",
    "TimeoutError",
    "PlaywrightError",
    "AssertionError",
    "other",
)
_REGISTRATION_ADMISSION_DIAG_NODE_CODES = (
    "EACCES",
    "EADDRINUSE",
    "EBUSY",
    "ECONNRESET",
    "EEXIST",
    "EINVAL",
    "EISDIR",
    "EMFILE",
    "ENOENT",
    "ENOSPC",
    "EPERM",
    "ETIMEDOUT",
    "ERR_INVALID_ARG_TYPE",
    "ERR_MODULE_NOT_FOUND",
)
_REGISTRATION_ADMISSION_DIAG_LINE_BYTES_LIMIT = 1024
_REGISTRATION_ADMISSION_DIAG_RECORD_LIMIT = 4
_REGISTRATION_ADMISSION_DIAG_MAX_MS = 360_000
_REGISTRATION_ADMISSION_DIAG_MAX_REQUESTS = 256
_REGISTRATION_ADMISSION_DIAG_MAX_COST = 5


def _validated_registration_admission_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _REGISTRATION_ADMISSION_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    if (
        not isinstance(record["project"], str)
        or record["project"] not in _PLAYWRIGHT_FAILURE_PROJECTS
    ):
        return None
    if record["stage"] not in _REGISTRATION_ADMISSION_DIAG_STAGES:
        return None
    if record["errorClass"] not in _REGISTRATION_ADMISSION_DIAG_ERROR_CLASSES:
        return None
    if record["nodeCode"] is not None and record["nodeCode"] not in (
        *_REGISTRATION_ADMISSION_DIAG_NODE_CODES,
        "other",
    ):
        return None
    cost = record["cost"]
    if cost is not None and (
        type(cost) is not int or not 1 <= cost <= _REGISTRATION_ADMISSION_DIAG_MAX_COST
    ):
        return None
    for key in ("timeoutMs", "remainingMs"):
        number = record[key]
        if number is not None and (
            type(number) is not int
            or not 1 <= number <= _REGISTRATION_ADMISSION_DIAG_MAX_MS
        ):
            return None
    for key in ("requestCount", "activeRequestCount"):
        number = record[key]
        if (
            type(number) is not int
            or not 0 <= number <= _REGISTRATION_ADMISSION_DIAG_MAX_REQUESTS
        ):
            return None
    if record["activeRequestCount"] > record["requestCount"]:
        return None
    for key in (
        "deadlineAvailable",
        "ownerPresent",
        "ledgerPresent",
        "requestObserved",
        "responseObserved",
        "actionFailed",
    ):
        if type(record[key]) is not bool:
            return None
    if record["requestObserved"] != (record["requestCount"] > 0):
        return None
    if not record["deadlineAvailable"] and record["remainingMs"] is not None:
        return None
    if record["responseObserved"] and not record["requestObserved"]:
        return None
    status = record["status"]
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        return None
    if not record["responseObserved"] and status is not None:
        return None
    return dict(record)


_PLAYWRIGHT_RESET_REGISTRATION_LINE = re.compile(
    r"UE_LIVE_RESET_REGISTRATION_V1 project=(desktop|mobile) "
    r"step=(arm-response|click|await-response)"
)


def _live_playwright_reset_registration_steps(output: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 128 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_RESET_REGISTRATION_LINE.fullmatch(line)
        if match is None:
            continue
        record = (match.group(1), match.group(2))
        if record not in records:
            records.append(record)
        if len(records) == 6:
            break
    return records


def _live_playwright_registration_admission_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _REGISTRATION_ADMISSION_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_REGISTRATION_ADMISSION_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_REGISTRATION_ADMISSION_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_registration_admission_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _REGISTRATION_ADMISSION_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PWA_BUNDLE_ROUTE_DIAG_PREFIX = "PWA_BUNDLE_ROUTE_DIAG "
_PWA_BUNDLE_ROUTE_DIAG_KEYS = (
    "schema",
    "project",
    "routeEntries",
    "originMatches",
    "bundlePathMatches",
    "serviceWorkerRequestSeen",
)
_PWA_BUNDLE_ROUTE_DIAG_LINE_BYTES_LIMIT = 512
_PWA_BUNDLE_ROUTE_DIAG_RECORD_LIMIT = 4
_PWA_BUNDLE_ROUTE_DIAG_MAX_COUNT = 64


def _validated_pwa_bundle_route_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _PWA_BUNDLE_ROUTE_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    route_entries = record["routeEntries"]
    origin_matches = record["originMatches"]
    bundle_path_matches = record["bundlePathMatches"]
    service_worker_seen = record["serviceWorkerRequestSeen"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    counts = (route_entries, origin_matches, bundle_path_matches)
    if any(
        type(count) is not int or not 0 <= count <= _PWA_BUNDLE_ROUTE_DIAG_MAX_COUNT
        for count in counts
    ):
        return None
    if origin_matches > route_entries or bundle_path_matches > origin_matches:
        return None
    if type(service_worker_seen) is not bool:
        return None
    if service_worker_seen and route_entries == 0:
        return None
    return {
        "schema": 1,
        "project": project,
        "routeEntries": route_entries,
        "originMatches": origin_matches,
        "bundlePathMatches": bundle_path_matches,
        "serviceWorkerRequestSeen": service_worker_seen,
    }


def _live_playwright_pwa_bundle_route_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    """Retain only closed, bounded PWA route observations from complete stdout lines."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PWA_BUNDLE_ROUTE_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PWA_BUNDLE_ROUTE_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PWA_BUNDLE_ROUTE_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_pwa_bundle_route_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PWA_BUNDLE_ROUTE_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PWA_UPDATE_LIFECYCLE_DIAG_PREFIX = "PWA_UPDATE_LIFECYCLE_DIAG "
_PWA_UPDATE_LIFECYCLE_DIAG_KEYS = (
    "schema",
    "project",
    "diagnosticStatus",
    "controllerChangeCount",
    "controllerPresent",
    "controllerState",
    "installingState",
    "waitingState",
    "activeState",
    "controllerIsActive",
    "workerTransformApplied",
    "bundleUpdateResponseSeen",
    "routeEntries",
    "originMatches",
    "bundlePathMatches",
    "serviceWorkerRequestSeen",
)
_PWA_UPDATE_LIFECYCLE_STATES = (
    "none",
    "parsed",
    "installing",
    "installed",
    "activating",
    "activated",
    "redundant",
)
_PWA_UPDATE_LIFECYCLE_DIAG_LINE_BYTES_LIMIT = 1024
_PWA_UPDATE_LIFECYCLE_DIAG_RECORD_LIMIT = 4
_PWA_UPDATE_LIFECYCLE_DIAG_MAX_COUNT = 64


def _validated_pwa_update_lifecycle_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _PWA_UPDATE_LIFECYCLE_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    if (
        not isinstance(record["project"], str)
        or record["project"] not in _PLAYWRIGHT_FAILURE_PROJECTS
    ):
        return None
    if record["diagnosticStatus"] not in ("available", "unavailable"):
        return None
    for key in (
        "controllerState",
        "installingState",
        "waitingState",
        "activeState",
    ):
        if record[key] not in _PWA_UPDATE_LIFECYCLE_STATES:
            return None
    for key in (
        "controllerChangeCount",
        "routeEntries",
        "originMatches",
        "bundlePathMatches",
    ):
        count = record[key]
        if count is not None and (
            type(count) is not int
            or not 0 <= count <= _PWA_UPDATE_LIFECYCLE_DIAG_MAX_COUNT
        ):
            return None
    for key in ("controllerPresent", "controllerIsActive"):
        if record[key] is not None and type(record[key]) is not bool:
            return None
    for key in (
        "workerTransformApplied",
        "bundleUpdateResponseSeen",
        "serviceWorkerRequestSeen",
    ):
        if type(record[key]) is not bool:
            return None
    route_entries = record["routeEntries"]
    origin_matches = record["originMatches"]
    bundle_path_matches = record["bundlePathMatches"]
    if (
        route_entries is not None
        and origin_matches is not None
        and bundle_path_matches is not None
        and not bundle_path_matches <= origin_matches <= route_entries
    ):
        return None
    if record["serviceWorkerRequestSeen"] and (
        route_entries is None or route_entries < 1
    ):
        return None
    if record["diagnosticStatus"] == "unavailable" and (
        record["controllerChangeCount"] is not None
        or record["controllerPresent"] is not None
        or record["controllerIsActive"] is not None
        or any(
            record[key] != "none"
            for key in (
                "controllerState",
                "installingState",
                "waitingState",
                "activeState",
            )
        )
    ):
        return None
    return dict(record)


def _live_playwright_pwa_update_lifecycle_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PWA_UPDATE_LIFECYCLE_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PWA_UPDATE_LIFECYCLE_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PWA_UPDATE_LIFECYCLE_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_pwa_update_lifecycle_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PWA_UPDATE_LIFECYCLE_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


def _live_playwright_auth_http_diagnostics(output: str) -> list[dict[str, object]]:
    """Retain only complete bounded Auth HTTP status mismatches from stdout."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _AUTH_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_AUTH_HTTP_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_AUTH_HTTP_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_auth_http_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _AUTH_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PLAYWRIGHT_LOGIN_FAILURE_LINE = re.compile(
    r"UE_LIVE_LOGIN_FAILURE_V1 project=(?P<project>desktop|mobile) "
    r"stage=(?P<stage>submit|navigation) "
    r"requests=(?P<requests>0|1|many) responses=(?P<responses>0|1|many) "
    r"status=(?P<status>none|[1-5][0-9]{2}) "
    r"route=(?P<route>login|dashboard|register|other|unavailable)"
)
_PLAYWRIGHT_LOGIN_FAILURE_LIMIT = 16
_PlaywrightLoginFailure = tuple[str, str, str, str, str, str]


def _live_playwright_login_failures(output: str) -> list[_PlaywrightLoginFailure]:
    """Accept only complete, closed login observations without raw URLs or errors."""
    records: list[_PlaywrightLoginFailure] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 192 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_LOGIN_FAILURE_LINE.fullmatch(line)
        if match is None:
            continue
        record: _PlaywrightLoginFailure = (
            match["project"],
            match["stage"],
            match["requests"],
            match["responses"],
            match["status"],
            match["route"],
        )
        if record in records:
            continue
        records.append(record)
        if len(records) >= _PLAYWRIGHT_LOGIN_FAILURE_LIMIT:
            break
    return records


_PLAYWRIGHT_HTTP_STATUS_LINE = re.compile(
    r"UE_LIVE_HTTP_STATUS_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>admin-users|admin-feature-flags|admin-feature-flags-ui|password-reset-replay|"
    r"auth-login|auth-session-cap|auth-logout|auth-session-preflight|"
    r"messenger-message-send|chat-attachment-create|email-otp-register|"
    r"email-otp-verification-start|email-otp-verification-wrong-code|"
    r"email-otp-verification-resend|email-otp-verification-stale-code|"
    r"email-otp-verification-accept|email-mfa-register|email-mfa-initial-login|"
    r"email-mfa-sibling-login|email-mfa-verification-start|"
    r"email-mfa-verification-accept|email-mfa-enable-start|email-mfa-enable-accept|"
    r"email-mfa-enabled-login|email-mfa-login-resend-early|email-mfa-login-accept) "
    r"status=(?P<status>[1-5][0-9]{2})"
)
_PLAYWRIGHT_HTTP_STATUS_CHECKS = {
    check: check
    for check in (
        "admin-users",
        "admin-feature-flags",
        "admin-feature-flags-ui",
        "password-reset-replay",
        "auth-login",
        "auth-session-cap",
        "auth-logout",
        "auth-session-preflight",
        "messenger-message-send",
        "chat-attachment-create",
        "email-otp-register",
        "email-otp-verification-start",
        "email-otp-verification-wrong-code",
        "email-otp-verification-resend",
        "email-otp-verification-stale-code",
        "email-otp-verification-accept",
        "email-mfa-register",
        "email-mfa-initial-login",
        "email-mfa-sibling-login",
        "email-mfa-verification-start",
        "email-mfa-verification-accept",
        "email-mfa-enable-start",
        "email-mfa-enable-accept",
        "email-mfa-enabled-login",
        "email-mfa-login-resend-early",
        "email-mfa-login-accept",
    )
}
# 26 closed checks × two projects × two attempts (initial plus one retry).
_PLAYWRIGHT_HTTP_STATUS_LIMIT = 104


_PLAYWRIGHT_RETRY_DECISION_LINE = re.compile(
    r"UE_LIVE_RETRY_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>auth-logout|password-reset-replay|"
    r"email-otp-verification-wrong-code|email-otp-verification-stale-code|"
    r"email-mfa-enabled-login) "
    r"retry_after_seconds=(?P<retry_after>invalid|[1-9][0-9]{0,2}) "
    r"decision=(?P<decision>retry|declined-header|declined-deadline|not-retried) "
    r"remaining_ms=(?P<remaining>0|[1-9][0-9]{0,3}|[1-5][0-9]{4}|60000)"
)
_PLAYWRIGHT_RETRY_DECISION_LIMIT = 32
_PlaywrightRetryDecision = tuple[str, str, int | None, str, int]

_PLAYWRIGHT_RATE_LIMIT_LINE = re.compile(
    r"UE_LIVE_RATE_LIMIT_V1 project=(?P<project>desktop|mobile) "
    r"check=auth-logout "
    r"x_ratelimit_limit=(?P<limit>invalid|[1-9][0-9]{0,5}) "
    r"x_ratelimit_remaining=(?P<remaining>invalid|0|[1-9][0-9]{0,5})"
)
_PLAYWRIGHT_RATE_LIMIT_MAX = 100_000
_PLAYWRIGHT_RATE_LIMIT_RECORD_LIMIT = 32
_PlaywrightRateLimit = tuple[str, int | None, int | None]


def _live_playwright_a11y_contrasts(output: str) -> list[_PlaywrightA11yContrast]:
    """Accept bounded contrast values from the fixed stdout protocol only."""
    records: list[_PlaywrightA11yContrast] = []
    route_counts: dict[tuple[str, str], int] = {}
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_A11Y_CONTRAST_LINE.fullmatch(line)
        if match is None:
            continue
        ratio_milli = int(match["ratio"])
        if ratio_milli > 21_000:
            continue
        project = _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]]
        route = match["route"]
        record: _PlaywrightA11yContrast = (
            project,
            route,
            match["foreground"].lower(),
            match["background"].lower(),
            ratio_milli,
        )
        if record in records:
            continue
        route_key = (project, route)
        if route_counts.get(route_key, 0) >= _PLAYWRIGHT_A11Y_CONTRAST_PER_ROUTE_LIMIT:
            continue
        records.append(record)
        route_counts[route_key] = route_counts.get(route_key, 0) + 1
        if len(records) == _PLAYWRIGHT_A11Y_CONTRAST_LIMIT:
            break
    return records


def _live_playwright_a11y_paint_states(output: str) -> list[_PlaywrightA11yPaintState]:
    """Accept only fixed paint, opacity, text-color and animation tags."""
    records: list[_PlaywrightA11yPaintState] = []
    route_counts: dict[tuple[str, str], int] = {}
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 480 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_A11Y_PAINT_LINE.fullmatch(line)
        if match is None:
            continue
        ratio_milli = int(match["ratio"])
        if ratio_milli > 21_000:
            continue
        record: _PlaywrightA11yPaintState = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["route"],
            match["axe_foreground"].lower(),
            match["axe_background"].lower(),
            ratio_milli,
            match["css_foreground"].lower(),
            match["text_color"],
            int(match["css_alpha"]),
            int(match["node_opacity"]),
            int(match["ancestor_opacity"]),
            match["opacity_tag"],
            match["page_ready"] == "true",
            int(match["page_opacity"]),
            int(match["layout_opacity"]),
            match["animation"],
            int(match["active_animations"]),
        )
        route_key = (record[0], record[1])
        if record in records or route_counts.get(route_key, 0) >= (
            _PLAYWRIGHT_A11Y_PAINT_PER_ROUTE_LIMIT
        ):
            continue
        records.append(record)
        route_counts[route_key] = route_counts.get(route_key, 0) + 1
        if len(records) == _PLAYWRIGHT_A11Y_PAINT_LIMIT:
            break
    return records


def _live_playwright_a11y_phase_states(output: str) -> list[_PlaywrightA11yPhaseState]:
    """Accept only fixed phase, page/root opacity and animation measurements."""
    records: list[_PlaywrightA11yPhaseState] = []
    phases_by_route: dict[tuple[str, str], set[str]] = {}
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 400 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_A11Y_PHASE_LINE.fullmatch(line)
        if match is None:
            continue
        record: _PlaywrightA11yPhaseState = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["route"],
            match["phase"],
            match["page_ready"] == "true",
            int(match["page_opacity"]),
            int(match["root_opacity"]),
            int(match["layout_opacity"]),
            match["animation"],
            int(match["active_animations"]),
        )
        route_key = (record[0], record[1])
        phase_set = phases_by_route.setdefault(route_key, set())
        if record[2] in phase_set:
            continue
        records.append(record)
        phase_set.add(record[2])
        if len(records) == _PLAYWRIGHT_A11Y_PHASE_LIMIT:
            break
    return records


def _live_playwright_footer_geometries(output: str) -> list[_PlaywrightFooterGeometry]:
    """Accept bounded viewport/nav measurements and fixed-block flags only."""
    records: list[_PlaywrightFooterGeometry] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 768 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_FOOTER_GEOMETRY_LINE.fullmatch(line)
        if match is None:
            continue
        number_names = (
            "requested_width",
            "requested_height",
            "inner_width",
            "inner_height",
            "client_width",
            "scroll_width",
            "nav_left",
            "nav_right",
            "nav_top",
            "nav_bottom",
            "nav_width",
            "nav_tx",
            "nav_ty",
            "fixed_cb_depth",
            "cb_left",
            "cb_right",
            "cb_top",
            "cb_bottom",
        )
        values = {name: int(match[name]) for name in number_names}
        if any(abs(value) > 5_000_000 for value in values.values()):
            continue
        if (
            values["requested_width"] <= 0
            or values["requested_height"] <= 0
            or values["inner_width"] <= 0
            or values["inner_height"] <= 0
            or values["client_width"] < 0
            or values["scroll_width"] < 0
            or values["nav_width"] < 0
            or values["fixed_cb_depth"] > 32
        ):
            continue
        fixed_found = match["fixed_cb_found"] == "true"
        depth = values["fixed_cb_depth"]
        cb_rect = tuple(
            values[name] for name in ("cb_left", "cb_right", "cb_top", "cb_bottom")
        )
        if (fixed_found and depth == 0) or (
            not fixed_found and (depth != 0 or any(cb_rect))
        ):
            continue
        record: _PlaywrightFooterGeometry = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            values["requested_width"],
            values["requested_height"],
            values["inner_width"],
            values["inner_height"],
            values["client_width"],
            values["scroll_width"],
            values["nav_left"],
            values["nav_right"],
            values["nav_top"],
            values["nav_bottom"],
            values["nav_width"],
            match["nav_transform_present"] == "true",
            values["nav_tx"],
            values["nav_ty"],
            fixed_found,
            depth,
            values["cb_left"],
            values["cb_right"],
            values["cb_top"],
            values["cb_bottom"],
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_FOOTER_GEOMETRY_LIMIT:
                break
    return records


def _live_playwright_news_viewports(output: str) -> list[_PlaywrightNewsViewport]:
    # Parse only the fixed stdout geometry fields.
    records: list[_PlaywrightNewsViewport] = []
    seen: set[tuple[str, str, int]] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 256 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_NEWS_VIEWPORT_LINE.fullmatch(line)
        if match is None:
            continue
        viewport_height = int(match["viewport_height"])
        scroll_y = int(match["scroll_y"])
        top = int(match["top"])
        bottom = int(match["bottom"])
        left = int(match["left"])
        right = int(match["right"])
        if (
            viewport_height <= 0
            or bottom < top
            or right < left
            or any(
                abs(value) > 999_999 for value in (scroll_y, top, bottom, left, right)
            )
        ):
            continue
        project = _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]]
        language = match["language"]
        width = int(match["width"])
        key = (project, language, width)
        if key in seen:
            continue
        record: _PlaywrightNewsViewport = (
            project,
            language,
            width,
            viewport_height,
            scroll_y,
            top,
            bottom,
            left,
            right,
        )
        records.append(record)
        seen.add(key)
        if len(records) == _PLAYWRIGHT_NEWS_VIEWPORT_LIMIT:
            break
    return records


def _live_playwright_push_observations(
    output: str,
) -> list[_PlaywrightPushObservation]:
    """Accept only closed, bounded browser-only Push observations from stdout."""
    observations: list[_PlaywrightPushObservation] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 240 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PUSH_OBSERVATION_LINE.fullmatch(line)
        if match is None:
            continue
        record: _PlaywrightPushObservation = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["permission"],
            match["ready"],
            match["state"],
            match["controller"] == "1",
            match["subscription"] == "1",
            int(match["matches"]),
        )
        if record in observations:
            continue
        if len(observations) >= _PLAYWRIGHT_PUSH_OBSERVATION_LIMIT:
            break
        observations.append(record)
    return observations


def _live_playwright_http_statuses(output: str) -> list[tuple[str, str, int]]:
    """Accept only complete stdout protocol records; discard all other content."""
    statuses: list[tuple[str, str, int]] = []
    # LF and CRLF terminate records; bare controls and EOF never do.
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 96 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_HTTP_STATUS_LINE.fullmatch(line)
        if match is None:
            continue
        check = _PLAYWRIGHT_HTTP_STATUS_CHECKS[match["check"]]
        status = int(match["status"])
        # The producer emits this row only after the exact API detail check.
        if check == "auth-session-cap" and status != 403:
            continue
        record = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            check,
            status,
        )
        if record not in statuses:
            statuses.append(record)
            if len(statuses) == _PLAYWRIGHT_HTTP_STATUS_LIMIT:
                break
    return statuses


def _live_playwright_retry_decisions(output: str) -> list[_PlaywrightRetryDecision]:
    """Accept only bounded retry-decision records from the live E2E helper."""
    decisions: list[_PlaywrightRetryDecision] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_RETRY_DECISION_LINE.fullmatch(line)
        if match is None:
            continue

        retry_after_text = match["retry_after"]
        retry_after = None if retry_after_text == "invalid" else int(retry_after_text)
        decision = match["decision"]
        check = match["check"]
        if check == "email-otp-verification-stale-code":
            if decision != "not-retried" or (
                retry_after is not None and retry_after > 600
            ):
                continue
        else:
            if decision == "not-retried" or (
                retry_after is not None and retry_after > 60
            ):
                continue
            if (retry_after is None) != (decision == "declined-header"):
                continue
        remaining_ms = int(match["remaining"])
        if decision == "retry" and remaining_ms == 0:
            continue
        record: _PlaywrightRetryDecision = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            check,
            retry_after,
            decision,
            remaining_ms,
        )
        if record not in decisions:
            decisions.append(record)
            if len(decisions) == _PLAYWRIGHT_RETRY_DECISION_LIMIT:
                break
    return decisions


def _live_playwright_rate_limit_headers(output: str) -> list[_PlaywrightRateLimit]:
    """Accept only bounded logout-header records; never retain raw header text."""
    records: list[_PlaywrightRateLimit] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_RATE_LIMIT_LINE.fullmatch(line)
        if match is None:
            continue

        limit_text = match["limit"]
        remaining_text = match["remaining"]
        limit = None if limit_text == "invalid" else int(limit_text)
        remaining = None if remaining_text == "invalid" else int(remaining_text)
        if (
            (limit is not None and not 1 <= limit <= _PLAYWRIGHT_RATE_LIMIT_MAX)
            or (
                remaining is not None
                and not 0 <= remaining <= _PLAYWRIGHT_RATE_LIMIT_MAX
            )
            or (limit is not None and remaining is not None and remaining > limit)
        ):
            continue

        record: _PlaywrightRateLimit = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            limit,
            remaining,
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_RATE_LIMIT_RECORD_LIMIT:
                break
    return records


_PLAYWRIGHT_PAGE_ERROR_LINE = re.compile(
    r"UE_LIVE_PAGE_ERROR_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>password-reset|admin-notifications|auth-roles|map-gesture|"
    r"schedule-grid-keyboard) "
    r"page=(?P<page>register|login|forgot-password|reset-password|dashboard|"
    r"admin-notifications|admin-users|admin-feature-flags|map|schedule|other) "
    r"type=(?P<type>error|type-error|reference-error|syntax-error|range-error|uri-error|"
    r"eval-error|aggregate-error|abort-error|security-error|invalid-state-error|react-418|other) "
    r"count=(?P<count>[1-9][0-9]{0,2})"
)
# One aggregate per allowed project/check/page/type combination across all checks.
_PLAYWRIGHT_PAGE_ERROR_LIMIT = 534

_PLAYWRIGHT_PAGE_ERROR_DETAIL_LINE = re.compile(
    r"UE_LIVE_PAGE_ERROR_DETAIL_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>map-gesture|schedule-grid-keyboard) "
    r"page=(?P<page>login|map|schedule|other) "
    r"type=(?P<type>error|type-error|reference-error|syntax-error|range-error|uri-error|"
    r"eval-error|aggregate-error|abort-error|security-error|invalid-state-error|react-418|other) "
    r"source=(?P<source>map-worker|map-shared|map-bundle|schedule-bundle|remote-script|unknown) "
    r"line=(?P<line>0|[1-9][0-9]{0,5}) "
    r"column=(?P<column>0|[1-9][0-9]{0,5}) "
    r"count=(?P<count>[1-9][0-9]{0,2})"
)
_PLAYWRIGHT_PAGE_ERROR_DETAIL_LIMIT = 156
_PlaywrightPageErrorDetail = tuple[str, str, str, str, str, int, int, int]


_PLAYWRIGHT_PROFILE_SAVE_LINE = re.compile(
    r"UE_LIVE_PROFILE_SAVE_V1 project=(?P<project>desktop|mobile) "
    r"status=(?P<status>[1-5][0-9]{2}) "
    r"detail=(?P<detail>absent|array|object|string|number|boolean|null|unavailable) "
    r"detail_count=(?P<detail_count>unknown|0|[1-9][0-9]{0,2}) "
    r"detail_msg=(?P<detail_msg>true|false|unknown) "
    r"alert_count=(?P<alert_count>unknown|0|[1-9][0-9]{0,2}) "
    r"save_disabled=(?P<save_disabled>true|false|unknown) "
    r"route=(?P<route>profile|login|register|dashboard|other) "
    r"page_error_count=(?P<page_error_count>unknown|0|[1-9][0-9]{0,2}) "
    r"page_error=(?P<page_error>none|error|type-error|reference-error|syntax-error|range-error|"
    r"uri-error|eval-error|aggregate-error|abort-error|security-error|invalid-state-error|other|unknown)"
)
_PLAYWRIGHT_PROFILE_SAVE_LIMIT = 4
_ProfileSaveDiagnostic = tuple[
    str,
    int,
    str,
    int | None,
    bool | None,
    int | None,
    bool | None,
    str,
    int | None,
    str,
]


def _profile_save_diagnostic_count(match: re.Match[str], name: str) -> int | None:
    value = match[name]
    return None if value == "unknown" else int(value)


def _profile_save_diagnostic_flag(match: re.Match[str], name: str) -> bool | None:
    value = match[name]
    return None if value == "unknown" else value == "true"


def _live_playwright_profile_save_diagnostics(
    output: str,
) -> list[_ProfileSaveDiagnostic]:
    """Accept only the fixed profile-save diagnostic protocol and discard all other text."""
    records: list[_ProfileSaveDiagnostic] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 320 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PROFILE_SAVE_LINE.fullmatch(line)
        if match is None:
            continue

        record: _ProfileSaveDiagnostic = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            int(match["status"]),
            match["detail"],
            _profile_save_diagnostic_count(match, "detail_count"),
            _profile_save_diagnostic_flag(match, "detail_msg"),
            _profile_save_diagnostic_count(match, "alert_count"),
            _profile_save_diagnostic_flag(match, "save_disabled"),
            match["route"],
            _profile_save_diagnostic_count(match, "page_error_count"),
            match["page_error"],
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_PROFILE_SAVE_LIMIT:
                break
    return records


def _live_playwright_page_errors(output: str) -> list[tuple[str, str, str, str, int]]:
    """Accept fixed current-page/type counts only, without retaining private text."""
    records: list[tuple[str, str, str, str, int]] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PAGE_ERROR_LINE.fullmatch(line)
        if match is None:
            continue
        if match["check"] == "admin-notifications":
            if match["page"] not in {
                "login",
                "dashboard",
                "admin-notifications",
                "other",
            }:
                continue
        elif match["check"] == "auth-roles":
            if match["page"] not in {
                "login",
                "dashboard",
                "admin-users",
                "admin-feature-flags",
                "other",
            }:
                continue
        elif match["check"] == "map-gesture":
            if match["page"] not in {"login", "map", "other"}:
                continue
        elif match["check"] == "schedule-grid-keyboard":
            if match["project"] != "desktop" or match["page"] not in {
                "login",
                "schedule",
                "other",
            }:
                continue
        elif (
            match["page"]
            not in {
                "register",
                "login",
                "forgot-password",
                "reset-password",
                "dashboard",
                "other",
            }
            or match["type"] == "react-418"
        ):
            continue
        record = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["check"],
            match["page"],
            match["type"],
            int(match["count"]),
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_PAGE_ERROR_LIMIT:
                break
    return records


def _live_playwright_page_error_details(
    output: str,
) -> list[_PlaywrightPageErrorDetail]:
    # Retain only bounded source buckets linked to accepted summaries.
    summaries = set(_live_playwright_page_errors(output))
    records: list[_PlaywrightPageErrorDetail] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 256 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PAGE_ERROR_DETAIL_LINE.fullmatch(line)
        if match is None:
            continue
        check = match["check"]
        page = match["page"]
        source = match["source"]
        if check == "map-gesture":
            if page not in {"login", "map", "other"} or source not in {
                "map-worker",
                "map-shared",
                "map-bundle",
                "remote-script",
                "unknown",
            }:
                continue
        elif (
            match["project"] != "desktop"
            or page not in {"login", "schedule", "other"}
            or source not in {"schedule-bundle", "remote-script", "unknown"}
        ):
            continue
        line_number = int(match["line"])
        column = int(match["column"])
        if (source == "unknown") != (line_number == 0 and column == 0):
            continue
        if source != "unknown" and (line_number == 0 or column == 0):
            continue
        count = int(match["count"])
        record: _PlaywrightPageErrorDetail = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            check,
            page,
            match["type"],
            source,
            line_number,
            column,
            count,
        )
        summary = (record[0], check, page, record[3], count)
        if summary not in summaries or record in records:
            continue
        records.append(record)
        if len(records) == _PLAYWRIGHT_PAGE_ERROR_DETAIL_LIMIT:
            break
    return records


def _live_playwright_counts(output: str) -> dict[str, int]:
    """Extract only numeric aggregate counts from exact Playwright summary lines."""
    counts: dict[str, int] = {}
    for line in output.split("\n"):
        match = _PLAYWRIGHT_COUNT_LINE.fullmatch(line.removesuffix("\r"))
        if match is not None:
            kind = match.group("kind").replace(" ", "_")
            counts[kind] = counts.get(kind, 0) + int(match.group("count"))
    return counts


_PlaywrightSkipIdentity = tuple[str, str, int]
_PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES: tuple[_PlaywrightSkipIdentity, ...] = (
    ("desktop", "tests/e2e-live/auth-roles.live.spec.ts", 144),
    ("mobile", "tests/e2e-live/auth-roles.live.spec.ts", 144),
    ("mobile", "tests/e2e-live/navbar-layout-stability.live.spec.ts", 174),
    ("mobile", "tests/e2e-live/schedule-grid-keyboard.live.spec.ts", 5),
    ("mobile", "tests/e2e-live/schedule-200-equivalent-reflow.live.spec.ts", 5),
    ("mobile", "tests/e2e-live/map-gesture-isolation.live.spec.ts", 178),
    ("mobile", "tests/e2e-live/map-gesture-isolation.live.spec.ts", 209),
    ("desktop", "tests/e2e-live/map-gesture-isolation.live.spec.ts", 248),
)
_PLAYWRIGHT_SKIPPED_ROW_PREFIX = re.compile(r"^  - {2,4}[1-9][0-9]{0,2} ")
_PLAYWRIGHT_SKIPPED_ROW_HEADER = re.compile(
    r"^  - {2,4}(?P<index>[1-9][0-9]{0,2}) "
    r"\[(?P<project>desktop|mobile)\] \u203a "
    r"(?P<source>[^ :\t]{1,160}):(?P<line>[1-9][0-9]{0,4}):"
    r"(?P<column>[1-9][0-9]{0,4}) \u203a (?=.)"
)
_PLAYWRIGHT_FULL_COLLECTION_COUNT = 220
_PLAYWRIGHT_SKIP_IDENTITY_LIMIT = 216
_PLAYWRIGHT_SKIP_SCAN_LINE_LIMIT = 8192
_PLAYWRIGHT_SKIP_LINE_LENGTH_LIMIT = 4096


def _live_playwright_skipped_identities(
    output: str, *, cwd: Path
) -> tuple[list[_PlaywrightSkipIdentity], int, bool]:
    """Extract bounded allowlisted skip identities, never test titles or reasons."""
    identities: list[_PlaywrightSkipIdentity] = []
    rejected_rows = 0
    overflow = False
    seen_indexes: set[int] = set()
    source_cache: dict[str, list[str]] = {}
    try:
        frontend_root = cwd.resolve(strict=True)
    except (OSError, RuntimeError):
        return identities, 0, True

    position = 0
    scanned_lines = 0
    while True:
        line_end = output.find("\n", position)
        if line_end < 0:
            break  # Only complete reporter rows are accepted.
        if scanned_lines >= _PLAYWRIGHT_SKIP_SCAN_LINE_LIMIT:
            overflow = True
            break
        line = output[position:line_end]
        position = line_end + 1
        scanned_lines += 1
        if line.endswith("\r"):
            line = line[:-1]
        if _PLAYWRIGHT_SKIPPED_ROW_PREFIX.match(line) is None:
            continue
        if len(line) > _PLAYWRIGHT_SKIP_LINE_LENGTH_LIMIT or not line.isprintable():
            rejected_rows += 1
            continue
        match = _PLAYWRIGHT_SKIPPED_ROW_HEADER.match(line)
        if match is None:
            rejected_rows += 1
            continue
        index = int(match["index"])
        source = _PLAYWRIGHT_FAILURE_SOURCES.get(match["source"])
        project = _PLAYWRIGHT_FAILURE_PROJECTS.get(match["project"])
        line_number = int(match["line"])
        column = int(match["column"])
        if (
            index > _PLAYWRIGHT_SKIP_IDENTITY_LIMIT
            or index in seen_indexes
            or source is None
            or project is None
        ):
            rejected_rows += 1
            continue
        seen_indexes.add(index)
        if source not in source_cache:
            try:
                source_path = frontend_root / source
                if source_path.is_symlink():
                    raise OSError("skip source is a symlink")
                resolved_source = source_path.resolve(strict=True)
                if (
                    not resolved_source.is_relative_to(frontend_root)
                    or not resolved_source.is_file()
                ):
                    raise OSError("skip source is outside the frontend root")
                source_cache[source] = resolved_source.read_text(
                    encoding="utf-8"
                ).splitlines()
            except (OSError, RuntimeError, UnicodeError):
                rejected_rows += 1
                continue
        source_lines = source_cache[source]
        if line_number > len(source_lines):
            rejected_rows += 1
            continue
        declaration = source_lines[line_number - 1]
        indentation = len(declaration) - len(declaration.lstrip())
        if not declaration.lstrip().startswith("test(") or column != indentation + 1:
            rejected_rows += 1
            continue
        if len(identities) >= _PLAYWRIGHT_SKIP_IDENTITY_LIMIT:
            overflow = True
            break
        identities.append((project, source, line_number))
    return identities, rejected_rows, overflow


def _live_playwright_failure_locations(
    output: str, *, cwd: Path
) -> list[tuple[str, str, int, str]]:
    """Return public declarations/frames, never titles, function names or errors."""
    locations: list[tuple[str, str, int, str]] = []
    source_lines: dict[str, list[str]] = {}
    frame_sources = {
        **_PLAYWRIGHT_FAILURE_FRAME_SOURCES,
        **{
            str(cwd.absolute() / source): source
            for source in _PLAYWRIGHT_FAILURE_FRAME_SOURCES.values()
        },
    }
    project = ""
    # Split only actual reporter newlines, not control characters in a title.
    for reporter_line in output.split("\n"):
        # A new top-level reporter line ends the previous failure, even if its
        # project, path or location cannot be validated. Blank lines are normal
        # between a failure header, error message and its indented stack.
        if reporter_line and not reporter_line.startswith("    "):
            project = ""
        if len(reporter_line) > 4096 or (
            reporter_line and not reporter_line.isprintable()
        ):
            project = ""
            continue
        match = _PLAYWRIGHT_FAILURE_HEADER.match(reporter_line)
        kind = "declaration"
        if match is not None:
            source = _PLAYWRIGHT_FAILURE_SOURCES.get(match["source"])
        elif project:
            frame = _PLAYWRIGHT_FAILURE_FRAME.fullmatch(reporter_line)
            if frame is None:
                continue
            match = _PLAYWRIGHT_FRAME_LOCATION.fullmatch(
                frame["named"] or frame["anonymous"]
            )
            if match is None:
                continue
            source = frame_sources.get(match["source"])
            kind = "frame"
        else:
            continue
        if source is None:
            continue
        if source not in source_lines:
            try:
                source_lines[source] = (
                    (cwd / source).read_text(encoding="utf-8").splitlines()
                )
            except (OSError, UnicodeError):
                # Diagnostics must not expose paths/errors or replace the exit status.
                source_lines[source] = []
        lines = source_lines[source]
        line_number = int(match["line"])
        column = int(match["column"])
        if line_number > len(lines) or column > len(lines[line_number - 1]) + 1:
            continue
        if kind == "declaration":
            project = _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]]
        location = (project, source, line_number, kind)
        if location not in locations:
            locations.append(location)
    return locations


_PLAYWRIGHT_FAILURE_DIAGNOSTIC_LIMIT = 256
_PLAYWRIGHT_FAILURE_EXPECT_LINE = re.compile(r"^ {4}Error: expect\(")
_PLAYWRIGHT_FAILURE_MATCHER_HEADER = re.compile(
    r"^ {4}Error: expect\((?:locator|page|received)\)\."
    r"(?P<negated>not\.)?(?P<matcher>toBe|toEqual|toStrictEqual|toContain|toMatch|"
    r"toBeVisible|toBeHidden|toBeEnabled|toBeDisabled|toBeChecked|"
    r"toBeFocused|toBeEditable|toBeEmpty|toBeAttached|toBeInViewport|toHaveText|"
    r"toContainText|toHaveValue|toHaveAttribute|toHaveClass|toHaveCount|toHaveCSS|"
    r"toHaveJSProperty|toHaveTitle|toHaveURL|toHaveId|toHaveRole|"
    r"toHaveAccessibleName|toHaveAccessibleDescription|toMatchAriaSnapshot|toPass)\s*\("
)
_PLAYWRIGHT_FAILURE_TIMEOUT_LINE = re.compile(
    r"^ {4}(?:"
    r"Error: (?:(?:locator|page)\.[A-Za-z]+: )?"
    r"Timeout [0-9]{1,6}(?:\.[0-9]{1,3})?(?:ms|s) exceeded\."
    r'|Error: page\.waitForResponse: Timeout [0-9]{1,6}ms exceeded while waiting for event "response"'
    r"|Test timeout of [0-9]{1,6}ms exceeded\."
    r"|Test timeout of [0-9]{1,6}ms exceeded while setting up "
    r'"[^"\r\n]{0,256}"\.'
    r'|Tearing down "[^"\r\n]{0,256}" exceeded the test timeout of '
    r"[0-9]{1,6}ms\."
    r'|Test timeout of [0-9]{1,6}ms exceeded while running "(?:beforeEach|afterEach)" hook\.'
    r'|"(?:beforeAll|afterAll)" hook timeout of [0-9]{1,6}ms exceeded\.'
    r"|Worker teardown timeout of [0-9]{1,6}ms exceeded"
    r'(?: while (?:setting up|tearing down) "[^"\r\n]{0,256}")?\.'
    r'|"(?:skip|slow|fixme|fail)" modifier timeout of [0-9]{1,6}ms exceeded\.'
    r'|Fixture "[^"\r\n]{0,256}" timeout of [0-9]{1,6}ms exceeded during (?:setup|teardown)\.'
    r")$"
)
_PLAYWRIGHT_FAILURE_NAVIGATION_LINE = re.compile(
    r"^ {4}Error: page\.(?:goto|waitForURL)\b"
)
_PLAYWRIGHT_FAILURE_LOCATOR_LINE = re.compile(r"^ {4}Error: locator\.[A-Za-z]+\b")
_PLAYWRIGHT_FAILURE_RUNTIME_LINE = re.compile(
    r"^ {4}(?:Error: )?(?:TypeError|ReferenceError|SyntaxError|RangeError|EvalError|"
    r"URIError|AggregateError|AbortError|SecurityError|InvalidStateError):"
)
_PLAYWRIGHT_FAILURE_LOCATOR_CALL = re.compile(
    r"^ {6}- waiting for (?:(?:page|locator)\.)?"
    r"(?P<method>getByRole|getByLabel|getByPlaceholder|getByText|getByTestId|"
    r"getByAltText|getByTitle|locator)\s*\("
)
_PLAYWRIGHT_FAILURE_CALL_LOG_START = re.compile(r"^ {4}Call log:$")
_PLAYWRIGHT_FAILURE_LOCATOR_CATEGORIES = {
    "getByRole": "role",
    "getByLabel": "label",
    "getByPlaceholder": "placeholder",
    "getByText": "text",
    "getByTestId": "test_id",
    "getByAltText": "alt_text",
    "getByTitle": "title",
    "locator": "locator",
}


def _live_playwright_failure_diagnostics(
    output: str, *, cwd: Path
) -> list[tuple[str, str, int, str, str, str]]:
    """Classify validated failure headers using fixed public enums only."""
    diagnostics: list[tuple[str, str, int, str, str, str]] = []
    source_lines: dict[str, list[str]] = {}
    current: dict[str, str | int] | None = None

    def finish() -> None:
        nonlocal current
        if current is None or len(diagnostics) >= _PLAYWRIGHT_FAILURE_DIAGNOSTIC_LIMIT:
            current = None
            return
        diagnostics.append(
            (
                str(current["project"]),
                str(current["source"]),
                int(current["line"]),
                str(current["category"]),
                str(current["matcher"]),
                str(current["locator"]),
            )
        )
        current = None

    for reporter_line in output.split("\n"):
        if reporter_line and not reporter_line.startswith("    "):
            finish()
        if len(reporter_line) > 4096 or (
            reporter_line and not reporter_line.isprintable()
        ):
            current = None
            continue
        if len(diagnostics) >= _PLAYWRIGHT_FAILURE_DIAGNOSTIC_LIMIT:
            break

        header = _PLAYWRIGHT_FAILURE_HEADER.match(reporter_line)
        if header is not None:
            source = _PLAYWRIGHT_FAILURE_SOURCES.get(header["source"])
            project = _PLAYWRIGHT_FAILURE_PROJECTS.get(header["project"])
            if source is None or project is None:
                current = None
                continue
            if source not in source_lines:
                try:
                    source_lines[source] = (
                        (cwd / source).read_text(encoding="utf-8").splitlines()
                    )
                except (OSError, UnicodeError):
                    source_lines[source] = []
            lines = source_lines[source]
            line_number = int(header["line"])
            column = int(header["column"])
            if line_number > len(lines) or column > len(lines[line_number - 1]) + 1:
                current = None
                continue
            current = {
                "project": project,
                "source": source,
                "line": line_number,
                "category": "unknown",
                "matcher": "none",
                "locator": "none",
                "in_call_log": False,
            }
            continue
        if current is None:
            continue

        if _PLAYWRIGHT_FAILURE_CALL_LOG_START.fullmatch(reporter_line):
            current["in_call_log"] = True
            continue
        if current["in_call_log"]:
            locator = _PLAYWRIGHT_FAILURE_LOCATOR_CALL.match(reporter_line)
            if locator is not None and current["locator"] == "none":
                current["locator"] = _PLAYWRIGHT_FAILURE_LOCATOR_CATEGORIES[
                    locator["method"]
                ]
            elif not reporter_line.startswith("      "):
                current["in_call_log"] = False

        if current["category"] != "unknown":
            continue
        if _PLAYWRIGHT_FAILURE_TIMEOUT_LINE.fullmatch(reporter_line):
            current["category"] = "timeout"
        elif _PLAYWRIGHT_FAILURE_EXPECT_LINE.match(reporter_line):
            current["category"] = "assertion"
            matcher = _PLAYWRIGHT_FAILURE_MATCHER_HEADER.match(reporter_line)
            if matcher is None:
                current["matcher"] = "other"
            else:
                matcher_name = matcher["matcher"]
                current["matcher"] = (
                    f"not.{matcher_name}" if matcher["negated"] else matcher_name
                )
        elif _PLAYWRIGHT_FAILURE_NAVIGATION_LINE.match(reporter_line):
            current["category"] = "navigation"
        elif _PLAYWRIGHT_FAILURE_LOCATOR_LINE.match(reporter_line):
            current["category"] = "locator"
        elif _PLAYWRIGHT_FAILURE_RUNTIME_LINE.match(reporter_line):
            current["category"] = "runtime"

    finish()
    return diagnostics


def _run_live_playwright(
    *,
    cwd: Path,
    environment: dict[str, str],
    mode: str = "full",
    specs: Sequence[str] | None = None,
) -> None:
    """Expose bounded public diagnostics and exit status; discard raw output."""
    selected_specs = _validated_live_e2e_specs(specs, mode=mode)
    command = _live_e2e_command(mode=mode, specs=selected_specs)
    if selected_specs:
        print("live E2E scope=focused diagnostic_only=true", flush=True)
    print("+", " ".join(command), flush=True)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed platform-specific argv
            command,
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=False,
        )
    except OSError as error:
        raise StandError("could not launch the live Playwright command") from error

    return_code = completed.returncode
    # Text mode converts bare CR into LF, which could fabricate protocol lines.
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
    output = "\n".join((stdout, stderr))
    counts = _live_playwright_counts(output)
    canonical_full_run = mode == "full" and not selected_specs
    skip_identities: list[_PlaywrightSkipIdentity] = []
    skip_rejected_rows = 0
    skip_overflow = False
    skip_accounting_passed = False
    if canonical_full_run and return_code == 0:
        skip_identities, skip_rejected_rows, skip_overflow = (
            _live_playwright_skipped_identities(stdout, cwd=cwd)
        )
        skip_accounting_passed = (
            _live_playwright_counts(stdout)
            == {"passed": 212, "skipped": len(_PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES)}
            and not skip_rejected_rows
            and not skip_overflow
            and sorted(skip_identities) == sorted(_PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES)
        )
    # Only the reviewed helpers' stdout protocols can emit these diagnostics.
    http_statuses = _live_playwright_http_statuses(stdout)
    push_observations = _live_playwright_push_observations(stdout)
    story_memory_records = _live_playwright_story_memory_records(stdout)
    story_memory_cycle_trace_diagnostics = (
        _live_playwright_story_memory_cycle_trace_diagnostics(stdout)
        if return_code != 0
        else []
    )
    story_setup_diagnostics = (
        _live_playwright_story_setup_diagnostics(stdout) if return_code != 0 else []
    )
    login_failures = _live_playwright_login_failures(stdout) if return_code != 0 else []
    auth_ui_diagnostics = (
        _live_playwright_auth_ui_diagnostics(stdout) if return_code != 0 else []
    )
    auth_http_diagnostics = (
        _live_playwright_auth_http_diagnostics(stdout) if return_code != 0 else []
    )
    auth_registration_diagnostics = (
        _live_playwright_auth_registration_diagnostics(stdout)
        if return_code != 0
        else []
    )
    reset_registration_steps = (
        _live_playwright_reset_registration_steps(stdout) if return_code != 0 else []
    )
    registration_admission_diagnostics = (
        _live_playwright_registration_admission_diagnostics(stdout)
        if return_code != 0
        else []
    )
    pwa_bundle_route_diagnostics = (
        _live_playwright_pwa_bundle_route_diagnostics(stdout)
        if return_code != 0
        else []
    )
    pwa_update_lifecycle_diagnostics = (
        _live_playwright_pwa_update_lifecycle_diagnostics(stdout)
        if return_code != 0
        else []
    )
    a11y_contrast_diagnostics = _live_playwright_a11y_contrasts(stdout)
    a11y_paint_states = _live_playwright_a11y_paint_states(stdout)
    a11y_phase_states = _live_playwright_a11y_phase_states(stdout)
    footer_geometries = _live_playwright_footer_geometries(stdout)
    news_viewports = _live_playwright_news_viewports(stdout)
    retry_decisions = _live_playwright_retry_decisions(stdout)
    rate_limit_headers = _live_playwright_rate_limit_headers(stdout)
    page_errors = _live_playwright_page_errors(stdout)
    page_error_details = _live_playwright_page_error_details(stdout)
    profile_save_diagnostics = _live_playwright_profile_save_diagnostics(stdout)
    # A header from one stream must never authorize frames from the other.
    failure_locations = list(
        dict.fromkeys(
            location
            for stream in (stdout, stderr)
            for location in _live_playwright_failure_locations(
                stream.replace("\r\n", "\n"), cwd=cwd
            )
        )
    )
    failure_diagnostics = [
        diagnostic
        for stream in (stdout, stderr)
        for diagnostic in _live_playwright_failure_diagnostics(
            stream.replace("\r\n", "\n"), cwd=cwd
        )
    ][:_PLAYWRIGHT_FAILURE_DIAGNOSTIC_LIMIT]
    del output, stdout, stderr
    completed.stdout = b""
    completed.stderr = b""
    del completed
    if counts:
        count_summary = " ".join(
            f"{name}={counts[name]}"
            for name in (
                "passed",
                "failed",
                "skipped",
                "flaky",
                "interrupted",
                "did_not_run",
            )
            if name in counts
        )
        print(f"live E2E counts {count_summary}", flush=True)
    for project, source, line_number in skip_identities:
        print(
            f"live E2E skipped project={project} source={source} line={line_number}",
            flush=True,
        )
    if canonical_full_run and return_code == 0:
        if skip_accounting_passed:
            print(
                f"live E2E skip accounting=verified count={len(skip_identities)}",
                flush=True,
            )
        else:
            print(
                f"live E2E skip accounting=failed observed={len(skip_identities)} "
                f"rejected={skip_rejected_rows} overflow={str(skip_overflow).lower()}",
                flush=True,
            )
    for project, source, line_number, kind in failure_locations:
        print(
            f"live E2E failure project={project} source={source} line={line_number} kind={kind}",
            flush=True,
        )
    for project, source, line_number, category, matcher, locator in failure_diagnostics:
        print(
            f"live E2E diagnostic project={project} source={source} line={line_number} "
            f"category={category} matcher={matcher} locator={locator}",
            flush=True,
        )
    for project, check, status in http_statuses:
        print(
            f"live E2E HTTP project={project} check={check} status={status}",
            flush=True,
        )
    for (
        project,
        permission,
        ready,
        state,
        controller,
        subscription,
        matches,
    ) in push_observations:
        print(
            f"live E2E push project={project} permission={permission} ready={ready} "
            f"state={state} controller={str(controller).lower()} "
            f"subscription={str(subscription).lower()} matches={matches}",
            flush=True,
        )
    for record in story_setup_diagnostics:
        print(
            "live E2E story setup " + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for record in story_memory_records:
        print(
            "live E2E story memory " + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for record in story_memory_cycle_trace_diagnostics:
        print(
            "live E2E story memory cycle trace "
            + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for project, stage, requests, responses, status, route in login_failures:
        print(
            f"live E2E login failure project={project} stage={stage} "
            f"requests={requests} responses={responses} status={status} route={route}",
            flush=True,
        )
    for record in auth_ui_diagnostics:
        print(
            "live E2E auth UI " + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for record in auth_registration_diagnostics:
        print(
            "live E2E auth registration " + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for project, step in reset_registration_steps:
        print(
            f"live E2E reset-registration project={project} step={step}",
            flush=True,
        )
    for record in registration_admission_diagnostics:
        print(
            "live E2E registration admission "
            + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for record in pwa_bundle_route_diagnostics:
        print(
            "live E2E PWA bundle route " + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for record in pwa_update_lifecycle_diagnostics:
        print(
            "live E2E PWA update lifecycle "
            + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for record in auth_http_diagnostics:
        print(
            "live E2E auth HTTP " + json.dumps(record, separators=(",", ":")),
            flush=True,
        )
    for (
        project,
        route,
        foreground,
        background,
        ratio_milli,
    ) in a11y_contrast_diagnostics:
        print(
            f"live E2E a11y contrast project={project} route={route} fg={foreground} "
            f"bg={background} ratio_milli={ratio_milli}",
            flush=True,
        )
    for (
        project,
        route,
        phase,
        page_ready,
        page_opacity,
        root_opacity,
        layout_opacity,
        animation,
        active_animations,
    ) in a11y_phase_states:
        print(
            f"live E2E a11y phase project={project} route={route} phase={phase} "
            f"page_ready={str(page_ready).lower()} page_opacity_milli={page_opacity} "
            f"root_opacity_milli={root_opacity} layout_opacity_milli={layout_opacity} "
            f"animation={animation} active_animations={active_animations}",
            flush=True,
        )
    for (
        project,
        route,
        axe_foreground,
        axe_background,
        ratio_milli,
        css_foreground,
        text_color,
        css_alpha,
        node_opacity,
        ancestor_opacity,
        opacity_tag,
        page_ready,
        page_opacity,
        layout_opacity,
        animation,
        active_animations,
    ) in a11y_paint_states:
        print(
            f"live E2E a11y paint project={project} route={route} "
            f"axe_fg={axe_foreground} axe_bg={axe_background} ratio_milli={ratio_milli} "
            f"css_fg={css_foreground} text_color={text_color} css_alpha_milli={css_alpha} "
            f"node_opacity_milli={node_opacity} ancestor_opacity_milli={ancestor_opacity} "
            f"opacity_tag={opacity_tag} page_ready={str(page_ready).lower()} "
            f"page_opacity_milli={page_opacity} layout_opacity_milli={layout_opacity} "
            f"animation={animation} active_animations={active_animations}",
            flush=True,
        )
    for (
        project,
        requested_width,
        requested_height,
        inner_width,
        inner_height,
        client_width,
        scroll_width,
        nav_left,
        nav_right,
        nav_top,
        nav_bottom,
        nav_width,
        nav_transform_present,
        nav_tx,
        nav_ty,
        fixed_cb_found,
        fixed_cb_depth,
        cb_left,
        cb_right,
        cb_top,
        cb_bottom,
    ) in footer_geometries:
        print(
            f"live E2E footer geometry project={project} req_w_milli={requested_width} "
            f"req_h_milli={requested_height} inner_w_milli={inner_width} "
            f"inner_h_milli={inner_height} client_w_milli={client_width} "
            f"scroll_w_milli={scroll_width} nav_left_milli={nav_left} "
            f"nav_right_milli={nav_right} nav_top_milli={nav_top} "
            f"nav_bottom_milli={nav_bottom} nav_width_milli={nav_width} "
            f"nav_transform_present={str(nav_transform_present).lower()} "
            f"nav_tx_milli={nav_tx} nav_ty_milli={nav_ty} "
            f"fixed_cb_found={str(fixed_cb_found).lower()} fixed_cb_depth={fixed_cb_depth} "
            f"cb_left_milli={cb_left} cb_right_milli={cb_right} "
            f"cb_top_milli={cb_top} cb_bottom_milli={cb_bottom}",
            flush=True,
        )
    for (
        project,
        language,
        width,
        viewport_height,
        scroll_y,
        top,
        bottom,
        left,
        right,
    ) in news_viewports:
        print(
            f"live E2E news viewport project={project} language={language} width={width} "
            f"viewportHeight={viewport_height} scrollY={scroll_y} top={top} "
            f"bottom={bottom} left={left} right={right}",
            flush=True,
        )
    for project, check, retry_after, decision, remaining_ms in retry_decisions:
        retry_after_label = "invalid" if retry_after is None else str(retry_after)
        print(
            f"live E2E retry project={project} check={check} "
            f"retry_after_seconds={retry_after_label} decision={decision} "
            f"remaining_ms={remaining_ms}",
            flush=True,
        )
    for project, limit, remaining in rate_limit_headers:
        limit_label = "invalid" if limit is None else str(limit)
        remaining_label = "invalid" if remaining is None else str(remaining)
        print(
            f"live E2E rate-limit project={project} check=auth-logout "
            f"x_ratelimit_limit={limit_label} x_ratelimit_remaining={remaining_label}",
            flush=True,
        )
    for project, check, current_page, error_type, count in page_errors:
        print(
            f"live E2E page error project={project} check={check} "
            f"page={current_page} type={error_type} count={count}",
            flush=True,
        )
    for (
        project,
        check,
        current_page,
        error_type,
        source,
        line_number,
        column,
        count,
    ) in page_error_details:
        print(
            f"live E2E page error detail project={project} check={check} page={current_page} "
            f"type={error_type} source={source} line={line_number} "
            f"column={column} count={count}",
            flush=True,
        )
    if return_code != 0:
        for (
            project,
            status,
            detail,
            detail_count,
            detail_message,
            alert_count,
            save_disabled,
            route,
            page_error_count,
            page_error,
        ) in profile_save_diagnostics:
            detail_count_text = "unknown" if detail_count is None else str(detail_count)
            detail_message_text = (
                "unknown" if detail_message is None else str(detail_message).lower()
            )
            alert_count_text = "unknown" if alert_count is None else str(alert_count)
            save_disabled_text = (
                "unknown" if save_disabled is None else str(save_disabled).lower()
            )
            page_error_count_text = (
                "unknown" if page_error_count is None else str(page_error_count)
            )
            print(
                f"live E2E profile save project={project} status={status} detail={detail} "
                f"detail_count={detail_count_text} detail_msg={detail_message_text} "
                f"alert_count={alert_count_text} save_disabled={save_disabled_text} "
                f"route={route} page_error_count={page_error_count_text} page_error={page_error}",
                flush=True,
            )
    outcome = (
        "passed"
        if return_code == 0 and (not canonical_full_run or skip_accounting_passed)
        else "failed"
    )
    print(f"live E2E outcome={outcome} exit_code={return_code}", flush=True)
    if return_code != 0:
        raise StandError(f"live Playwright E2E failed with exit code {return_code}")
    if canonical_full_run and not skip_accounting_passed:
        raise StandError("live Playwright E2E skip identity accounting failed")


_LIVE_CADDY_PROBE_MAX_BYTES = 1_048_576
_LIVE_CADDY_PROBE_MARKER_MAX_BYTES = 256
_LIVE_CADDY_PROBE_MAX_OUTPUT_DIRECTORY_ENTRIES = 512
_LIVE_CADDY_PROBE_WINDOW_MS = 5_000
_LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS = 10
_LIVE_CADDY_PROBE_ADMISSION_TIMEOUT_SECONDS = 25
_LIVE_CADDY_PROBE_MAX_PROJECT_CONTAINERS = 64
_LIVE_CADDY_PROBE_TOTAL_TIMEOUT_SECONDS = 25
_LIVE_CADDY_PROBE_FAILURE = "Caddy access-log redaction proof failed"
_LIVE_CADDY_PROBE_DIAGNOSTIC_PREFIX = "live_caddy_probe_failure_stage="
_LIVE_CADDY_PROBE_DIAGNOSTIC_CODES = frozenset(
    {
        "input_validation",
        "context_resolution",
        "deadline",
        "marker_observation",
        "pre_pin",
        "log_read",
        "log_exit",
        "log_pipe_io",
        "log_size",
        "nonce_exposure",
        "correlation_row",
        "stderr_validation",
        "project_row",
        "post_pin",
        "internal",
    }
)
_LIVE_CADDY_ACCESS_LOGGER = "http.log.access.log0"
_LIVE_CADDY_PROBE_READ_CHUNK_BYTES = 16_384
_LIVE_CADDY_PROBE_CLEANUP_RESERVE_SECONDS = 0.25
_LIVE_CADDY_PROBE_WINDOWS_POLL_SECONDS = 0.01
_LIVE_CADDY_PROBE_WINDOWS_BROKEN_PIPE = 109
_LIVE_CADDY_PROBE_WINDOWS_PEEK: object | None = None
_LIVE_CADDY_PROBE_WINDOWS_KERNEL32: object | None = None


class _LiveCaddyProbeStageFailure(StandError):
    """Carry only a finite diagnostic code while preserving the generic error."""

    def __init__(self, stage: str) -> None:
        self.stage = (
            stage
            if isinstance(stage, str) and stage in _LIVE_CADDY_PROBE_DIAGNOSTIC_CODES
            else "internal"
        )
        super().__init__(_LIVE_CADDY_PROBE_FAILURE)


class _LiveBoundedReadFailure(StandError):
    """Carry a finite read failure reason without command or output details."""

    def __init__(self, reason: str) -> None:
        self.reason = (
            reason
            if isinstance(reason, str) and reason in {"output_limit", "pipe_io"}
            else "internal"
        )
        super().__init__(_LIVE_CADDY_PROBE_FAILURE)


def _emit_live_caddy_probe_diagnostic(stage: str) -> None:
    code = (
        stage
        if isinstance(stage, str) and stage in _LIVE_CADDY_PROBE_DIAGNOSTIC_CODES
        else "internal"
    )
    try:
        sys.stderr.write(f"{_LIVE_CADDY_PROBE_DIAGNOSTIC_PREFIX}{code}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


@dataclass(frozen=True, slots=True)
class _LiveDockerReadContext:
    executable: str
    executable_identity: tuple[int, int, int, int]
    cwd: str
    environment: tuple[tuple[str, str], ...]

    def environment_dict(self) -> dict[str, str]:
        return dict(self.environment)


def _live_probe_remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
    remaining = float(deadline) - time.monotonic()
    if remaining <= 0:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
    return remaining


def _live_docker_executable_identity(path: str) -> tuple[int, int, int, int]:
    info = os.stat(path, follow_symlinks=True)
    if not stat.S_ISREG(info.st_mode):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _new_live_docker_read_context() -> _LiveDockerReadContext:
    """Snapshot the trusted local Docker selection for one redaction proof."""
    environment = dict(os.environ)
    selected = shutil.which("docker", path=environment.get("PATH"))
    if selected is None:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
    try:
        executable = str(Path(selected).resolve(strict=True))
        identity = _live_docker_executable_identity(executable)
        cwd = str(Path.cwd().resolve(strict=True))
    except (OSError, RuntimeError):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    return _LiveDockerReadContext(
        executable=executable,
        executable_identity=identity,
        cwd=cwd,
        environment=tuple(sorted(environment.items())),
    )


def _assert_live_docker_read_context(context: _LiveDockerReadContext) -> None:
    try:
        current = _live_docker_executable_identity(context.executable)
    except (OSError, RuntimeError):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    if current != context.executable_identity:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)


def _live_docker_command(
    command: Sequence[str], context: _LiveDockerReadContext | None
) -> list[str]:
    result = list(command)
    if result and result[0] == "docker" and context is not None:
        _assert_live_docker_read_context(context)
        result[0] = context.executable
    return result


def _live_windows_peek_named_pipe_api() -> Callable[..., int]:
    """Load the availability-only Windows pipe API used for bounded reads."""
    global _LIVE_CADDY_PROBE_WINDOWS_KERNEL32, _LIVE_CADDY_PROBE_WINDOWS_PEEK
    if _LIVE_CADDY_PROBE_WINDOWS_PEEK is None:
        import ctypes as ctypes_module
        from ctypes import wintypes

        ctypes_api = cast(Any, ctypes_module)
        loader = cast(Callable[..., object], ctypes_api.WinDLL)
        kernel32 = loader("kernel32", use_last_error=True)
        peek = cast(Any, kernel32).PeekNamedPipe
        peek.argtypes = (
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
            ctypes_module.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        )
        peek.restype = wintypes.BOOL
        _LIVE_CADDY_PROBE_WINDOWS_KERNEL32 = kernel32
        _LIVE_CADDY_PROBE_WINDOWS_PEEK = peek
    return cast(Callable[..., int], _LIVE_CADDY_PROBE_WINDOWS_PEEK)


def _live_windows_pipe_available(stream: BinaryIO) -> int | None:
    import ctypes as ctypes_module
    import msvcrt
    from ctypes import wintypes

    available = wintypes.DWORD()
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
    succeeded = _live_windows_peek_named_pipe_api()(
        handle, None, 0, None, ctypes_module.byref(available), None
    )
    if succeeded:
        return int(available.value)
    ctypes_api = cast(Any, ctypes_module)
    error_code = cast(Callable[[], int], ctypes_api.get_last_error)()
    if error_code == _LIVE_CADDY_PROBE_WINDOWS_BROKEN_PIPE:
        return None
    win_error = cast(Callable[[int], OSError], ctypes_api.WinError)
    raise win_error(error_code)


def _live_drain_windows_pipes(
    process: subprocess.Popen[bytes],
    *,
    stdout: bytearray,
    stderr: bytearray,
    work_deadline: float,
    maximum_bytes: int,
) -> bool:
    streams = (process.stdout, process.stderr)
    buffers = (stdout, stderr)
    open_pipes = [stream is not None for stream in streams]
    while any(open_pipes):
        if time.monotonic() >= work_deadline:
            return False
        made_progress = False
        for index, stream in enumerate(streams):
            if not open_pipes[index] or stream is None:
                continue
            available = _live_windows_pipe_available(stream)
            if available is None:
                open_pipes[index] = False
                continue
            if available < 0:
                raise OSError("PeekNamedPipe returned a negative byte count")
            if available == 0:
                continue
            remaining = maximum_bytes - len(stdout) - len(stderr)
            chunk = os.read(
                stream.fileno(),
                min(
                    available,
                    _LIVE_CADDY_PROBE_READ_CHUNK_BYTES,
                    remaining + 1,
                ),
            )
            if not chunk:
                raise OSError(
                    "PeekNamedPipe reported bytes but the pipe read was empty"
                )
            buffers[index].extend(chunk[:remaining])
            if len(chunk) > remaining:
                raise _LiveBoundedReadFailure("output_limit")
            made_progress = True
        if not any(open_pipes):
            return True
        if not made_progress:
            remaining = work_deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(_LIVE_CADDY_PROBE_WINDOWS_POLL_SECONDS, remaining))
    return process.poll() is not None


def _live_drain_posix_pipes(
    process: subprocess.Popen[bytes],
    *,
    stdout: bytearray,
    stderr: bytearray,
    work_deadline: float,
    maximum_bytes: int,
) -> bool:
    streams = (process.stdout, process.stderr)
    buffers = {"stdout": stdout, "stderr": stderr}
    if any(stream is None for stream in streams):
        return False
    selector = selectors.DefaultSelector()
    try:
        for name, stream in zip(("stdout", "stderr"), streams, strict=True):
            if stream is None:
                return False
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = work_deadline - time.monotonic()
            if remaining <= 0:
                return False
            ready = selector.select(min(remaining, 0.05))
            for key, _events in ready:
                if time.monotonic() >= work_deadline:
                    return False
                target = buffers[cast(str, key.data)]
                output_remaining = maximum_bytes - len(stdout) - len(stderr)
                chunk = os.read(
                    key.fd,
                    min(_LIVE_CADDY_PROBE_READ_CHUNK_BYTES, output_remaining + 1),
                )
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                target.extend(chunk[:output_remaining])
                if len(chunk) > output_remaining:
                    raise _LiveBoundedReadFailure("output_limit")
        return True
    finally:
        selector.close()


def _run_live_bounded_read(
    command: Sequence[str],
    *,
    context: _LiveDockerReadContext,
    deadline: float,
    cwd: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
    maximum_bytes: int = _LIVE_CADDY_PROBE_MAX_BYTES,
    command_timeout_seconds: float = _LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    """Capture fixed local read-only command output under one shared deadline."""
    try:
        shared_remaining = _live_probe_remaining(deadline)
        if (
            shared_remaining is None
            or type(maximum_bytes) is not int
            or maximum_bytes < 0
            or type(command_timeout_seconds) not in (int, float)
            or not math.isfinite(command_timeout_seconds)
            or command_timeout_seconds <= 0
        ):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        started = time.monotonic()
        command_deadline = min(
            float(deadline), started + float(command_timeout_seconds)
        )
        command_budget = command_deadline - started
        reserve = min(_LIVE_CADDY_PROBE_CLEANUP_RESERVE_SECONDS, command_budget / 2)
        work_deadline = command_deadline - reserve
        if work_deadline <= started:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _assert_live_docker_read_context(context)
        argv = _live_docker_command(command, context)
        if (
            not argv
            or len(argv) > 128
            or argv[0] != context.executable
            or any(type(argument) is not str or "\x00" in argument for argument in argv)
            or sum(map(len, argv)) > 65_536
        ):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        process_environment = (
            context.environment_dict() if environment is None else dict(environment)
        )
        process = fast_preflight._start_process(
            fast_preflight.CheckSpec("live-caddy-log-read", tuple(argv)),
            repo_root=Path(context.cwd if cwd is None else cwd),
            env=process_environment,
        )
    except (OSError, RuntimeError, StandError, ValueError, TypeError):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None

    stdout = bytearray()
    stderr = bytearray()
    completed = False
    cleanup_ok = True
    return_code: int | None = None
    failure_reason: str | None = None
    try:
        try:
            if process.stdout is None or process.stderr is None:
                raise OSError("Docker read pipes were unavailable")
            if os.name == "nt":
                completed = _live_drain_windows_pipes(
                    process,
                    stdout=stdout,
                    stderr=stderr,
                    work_deadline=work_deadline,
                    maximum_bytes=maximum_bytes,
                )
            else:
                completed = _live_drain_posix_pipes(
                    process,
                    stdout=stdout,
                    stderr=stderr,
                    work_deadline=work_deadline,
                    maximum_bytes=maximum_bytes,
                )
        except OSError:
            raise _LiveBoundedReadFailure("pipe_io") from None

        if completed:
            # Keep the reserved tail for killing and reaping a child that closed
            # both pipes but is still running.
            remaining = work_deadline - time.monotonic()
            if remaining > 0:
                try:
                    return_code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    completed = False
            else:
                completed = False
    except _LiveBoundedReadFailure as error:
        completed = False
        failure_reason = error.reason
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        completed = False
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                if process.poll() is None:
                    cleanup_ok = False
            remaining = command_deadline - time.monotonic()
            if remaining > 0:
                try:
                    process.wait(timeout=remaining)
                except (OSError, subprocess.TimeoutExpired, ValueError):
                    cleanup_ok = False
            elif process.poll() is None:
                cleanup_ok = False
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except (OSError, ValueError):
                    cleanup_ok = False

    if not cleanup_ok:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    if failure_reason is not None:
        raise _LiveBoundedReadFailure(failure_reason) from None
    if not completed or return_code is None:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    try:
        _assert_live_docker_read_context(context)
        _live_probe_remaining(deadline)
    except (OSError, RuntimeError, StandError):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    return subprocess.CompletedProcess(
        argv, return_code, stdout=bytes(stdout), stderr=bytes(stderr)
    )


def _new_live_caddy_probe_values() -> tuple[str, dict[str, str]]:
    """Generate run-only credentials that never enter an observation file or output."""
    nonce = secrets.token_hex(16)
    correlations = {
        project: secrets.token_hex(16) for project in LIVE_CADDY_PROBE_PROJECTS
    }
    values = (nonce, *correlations.values())
    while len(set(values)) != len(values):
        nonce = secrets.token_hex(16)
        correlations = {
            project: secrets.token_hex(16) for project in LIVE_CADDY_PROBE_PROJECTS
        }
        values = (nonce, *correlations.values())
    return nonce, correlations


def _reject_live_caddy_probe_json_constant(_value: str) -> None:
    raise ValueError


def _assert_live_caddy_probe_redaction(
    output: bytes,
    *,
    stderr: bytes = b"",
    password_nonce: str,
    correlation_id: str,
    project: str,
    since_ms: int | None = None,
    until_ms: int | None = None,
) -> None:
    """Require one successful, exactly correlated request with a redacted password."""
    if type(output) is not bytes or type(stderr) is not bytes:
        raise _LiveCaddyProbeStageFailure("input_validation")
    if len(output) + len(stderr) > _LIVE_CADDY_PROBE_MAX_BYTES:
        raise _LiveCaddyProbeStageFailure("log_size")
    if (
        project not in LIVE_CADDY_PROBE_PROJECTS
        or not isinstance(password_nonce, str)
        or re.fullmatch(r"[0-9a-f]{32}", password_nonce) is None
        or not isinstance(correlation_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", correlation_id) is None
        or password_nonce == correlation_id
        or (since_ms is None) != (until_ms is None)
    ):
        raise _LiveCaddyProbeStageFailure("input_validation")

    nonce_bytes = password_nonce.encode("ascii")
    correlation_bytes = correlation_id.encode("ascii")
    if nonce_bytes in output or nonce_bytes in stderr:
        raise _LiveCaddyProbeStageFailure("nonce_exposure")

    matching_rows = [
        line
        for stream in (output, stderr)
        for line in stream.splitlines()
        if correlation_bytes in line
    ]
    if len(matching_rows) != 1:
        raise _LiveCaddyProbeStageFailure("correlation_row")

    # Docker forwards container stderr to this process's stderr. Accept it only
    # as timestamped Caddy JSON records, never as unstructured CLI diagnostics.
    stderr_rows = stderr.splitlines()
    for line in stderr_rows:
        if not line:
            raise _LiveCaddyProbeStageFailure("stderr_validation")
        try:
            timestamp_bytes, payload_bytes = line.split(b" ", 1)
            _parse_live_docker_log_timestamp(timestamp_bytes)
            stderr_payload = json.loads(
                payload_bytes,
                object_pairs_hook=_reject_duplicate_docker_json_keys,
                parse_constant=_reject_live_caddy_probe_json_constant,
            )
        except (
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            RecursionError,
        ):
            raise _LiveCaddyProbeStageFailure("stderr_validation") from None
        level = (
            stderr_payload.get("level") if isinstance(stderr_payload, dict) else None
        )
        if (
            not isinstance(stderr_payload, dict)
            or not isinstance(level, str)
            or level not in {"debug", "info", "warn", "error", "panic", "fatal"}
            or not isinstance(stderr_payload.get("msg"), str)
            or (
                "logger" in stderr_payload
                and not isinstance(stderr_payload.get("logger"), str)
            )
            or level in {"error", "panic", "fatal"}
        ):
            raise _LiveCaddyProbeStageFailure("stderr_validation")

    try:
        timestamp_bytes, payload_bytes = matching_rows[0].split(b" ", 1)
        _parse_live_docker_log_timestamp(timestamp_bytes)
        payload = json.loads(
            payload_bytes,
            object_pairs_hook=_reject_duplicate_docker_json_keys,
            parse_constant=_reject_live_caddy_probe_json_constant,
        )
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise _LiveCaddyProbeStageFailure("project_row") from None

    if since_ms is not None and until_ms is not None:
        try:
            row_timestamp_ns = _parse_live_docker_log_timestamp(timestamp_bytes)
        except (ValueError, OverflowError):
            raise _LiveCaddyProbeStageFailure("project_row") from None
        if (
            type(since_ms) is not int
            or type(until_ms) is not int
            or since_ms <= 0
            or until_ms < since_ms
            or not since_ms * 1_000_000 <= row_timestamp_ns <= until_ms * 1_000_000
        ):
            raise _LiveCaddyProbeStageFailure("project_row")

    if not isinstance(payload, dict):
        raise _LiveCaddyProbeStageFailure("project_row")
    request = payload.get("request")
    expected_uri = f"/login?probe={correlation_id}&password=REDACTED"
    if (
        payload.get("logger") != _LIVE_CADDY_ACCESS_LOGGER
        or not isinstance(request, dict)
        or request.get("method") != "GET"
        or request.get("uri") != expected_uri
        or type(payload.get("status")) is not int
        or payload.get("status") != 200
    ):
        raise _LiveCaddyProbeStageFailure("project_row")


def _parse_live_docker_log_timestamp(value: bytes) -> int:
    """Parse Docker's UTC RFC3339Nano prefix into an exact nanosecond value."""
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError from None
    match = re.fullmatch(
        r"(?P<date>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
        r"(?:\.(?P<fraction>\d{1,9}))?Z",
        text,
    )
    if match is None:
        raise ValueError
    whole_seconds = datetime.strptime(match.group("date"), "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=UTC
    )
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    difference = whole_seconds - epoch
    seconds = difference.days * 86_400 + difference.seconds
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return seconds * 1_000_000_000 + int(fraction or "0")


def _read_live_caddy_probe_observations(
    output_directory: Path,
    *,
    started_at_ms: int,
    finished_at_ms: int,
    deadline: float | None = None,
) -> dict[str, int]:
    """Read and remove the two fixed, bounded, value-free project markers."""
    expected_names = {
        f"aud174-caddy-probe-{project}.json" for project in LIVE_CADDY_PROBE_PROJECTS
    }
    observed: dict[str, int] = {}
    cleanup_failed = False
    try:
        if (
            type(started_at_ms) is not int
            or type(finished_at_ms) is not int
            or started_at_ms <= 0
            or finished_at_ms < started_at_ms
        ):
            raise ValueError
        directory_info = output_directory.lstat()
        if not stat.S_ISDIR(directory_info.st_mode) or _path_is_reparse_point(
            output_directory
        ):
            raise ValueError
        if deadline is not None:
            _live_probe_remaining(deadline)
        marker_names: set[str] = set()
        entry_count = 0
        with os.scandir(output_directory) as iterator:
            while True:
                if deadline is not None:
                    _live_probe_remaining(deadline)
                try:
                    child = next(iterator)
                except StopIteration:
                    break
                entry_count += 1
                if entry_count > _LIVE_CADDY_PROBE_MAX_OUTPUT_DIRECTORY_ENTRIES:
                    raise ValueError
                if deadline is not None:
                    _live_probe_remaining(deadline)
                if child.name.startswith("aud174-caddy-probe-"):
                    marker_names.add(child.name)
        if marker_names != expected_names:
            raise ValueError

        for project in LIVE_CADDY_PROBE_PROJECTS:
            if deadline is not None:
                _live_probe_remaining(deadline)
            marker_path = output_directory / f"aud174-caddy-probe-{project}.json"
            before = marker_path.lstat()
            if (
                not stat.S_ISREG(before.st_mode)
                or _path_is_reparse_point(marker_path)
                or before.st_size > _LIVE_CADDY_PROBE_MARKER_MAX_BYTES
            ):
                raise ValueError
            binary_flag_name = "O_BINARY"
            no_follow_flag_name = "O_NOFOLLOW"
            open_flags = os.O_RDONLY | getattr(os, binary_flag_name, 0)
            open_flags |= getattr(os, no_follow_flag_name, 0)
            descriptor = os.open(marker_path, open_flags)
            raw_buffer = bytearray()
            try:
                opened = os.fstat(descriptor)
                path_at_open = marker_path.lstat()
                if (
                    _live_caddy_marker_identity(before)
                    != _live_caddy_marker_identity(opened)
                    or _live_caddy_marker_identity(opened)
                    != _live_caddy_marker_identity(path_at_open)
                    or not stat.S_ISREG(opened.st_mode)
                ):
                    raise ValueError
                while len(raw_buffer) <= _LIVE_CADDY_PROBE_MARKER_MAX_BYTES:
                    if deadline is not None:
                        _live_probe_remaining(deadline)
                    chunk = os.read(
                        descriptor,
                        min(
                            64,
                            _LIVE_CADDY_PROBE_MARKER_MAX_BYTES + 1 - len(raw_buffer),
                        ),
                    )
                    raw_buffer.extend(chunk)
                    if deadline is not None:
                        _live_probe_remaining(deadline)
                    if not chunk:
                        break
                opened_after = os.fstat(descriptor)
                path_after = marker_path.lstat()
                if (
                    len(raw_buffer) > _LIVE_CADDY_PROBE_MARKER_MAX_BYTES
                    or _live_caddy_marker_identity(opened)
                    != _live_caddy_marker_identity(opened_after)
                    or _live_caddy_marker_identity(opened_after)
                    != _live_caddy_marker_identity(path_after)
                    or len(raw_buffer) != opened_after.st_size
                ):
                    raise ValueError
            finally:
                os.close(descriptor)
            raw = bytes(raw_buffer)
            if len(raw) != before.st_size:
                raise ValueError
            marker = json.loads(raw.decode("utf-8"))
            if (
                not isinstance(marker, dict)
                or set(marker) != {"schema", "project", "completed_at_ms"}
                or marker["schema"] != "aud174-caddy-probe-v1"
                or marker["project"] != project
                or type(marker["completed_at_ms"]) is not int
                or not started_at_ms <= marker["completed_at_ms"] <= finished_at_ms
            ):
                raise ValueError
            observed[project] = marker["completed_at_ms"]
        if set(observed) != set(LIVE_CADDY_PROBE_PROJECTS):
            raise ValueError
        return observed
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    finally:
        for project in LIVE_CADDY_PROBE_PROJECTS:
            marker_path = output_directory / f"aud174-caddy-probe-{project}.json"
            try:
                marker_path.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                cleanup_failed = True
                continue
            try:
                marker_path.unlink()
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None


def _live_caddy_marker_identity(
    info: os.stat_result,
    *,
    windows: bool | None = None,
) -> tuple[int, ...]:
    """Return a stable file identity using the platform's correct timestamp."""
    if windows is None:
        windows = os.name == "nt"
    if type(windows) is not bool:
        raise ValueError

    identity = (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
    )
    if any(type(value) is not int for value in identity):
        raise ValueError
    timestamp_name = "st_birthtime_ns" if windows else "st_ctime_ns"
    timestamp = getattr(info, timestamp_name, None)
    if type(timestamp) is not int:
        raise ValueError
    return (*identity, timestamp)


def _live_core_caddy_container_inventory(
    owner: StandOwner,
    evidence: ComposeResourceEvidence,
    *,
    deadline: float,
    docker_context: _LiveDockerReadContext,
) -> dict[str, CoreContainerRecord]:
    selected = owner.selected_services
    selected_set = set(selected)
    if (
        owner.stack != LIVE_STACK_CORE
        or evidence.stack != LIVE_STACK_CORE
        or not selected
        or len(selected_set) != len(selected)
        or evidence.selected_services != selected
        or set(evidence.managed_services) != selected_set
        or not LIVE_CORE_QUIESCE_DATA_STORES <= selected_set
    ):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)

    _live_probe_remaining(deadline)
    try:
        container_ids = _validated_docker_container_ids(
            _project_container_ids(
                owner.project_name,
                deadline=deadline,
                docker_context=docker_context,
            ),
            maximum=_LIVE_CADDY_PROBE_MAX_PROJECT_CONTAINERS,
        )
    except _DockerProjectionError:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    if not container_ids:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)

    _live_probe_remaining(deadline)
    command = _build_live_core_caddy_inspect_command(container_ids)
    output = _docker_output(
        command[1:],
        _LIVE_CADDY_PROBE_FAILURE,
        deadline=deadline,
        docker_context=docker_context,
    )
    _live_probe_remaining(deadline)
    try:
        raw_records = _parse_live_core_caddy_inspect_batch(output, container_ids)
    except _DockerProjectionError:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None

    records: dict[str, CoreContainerRecord] = {}
    service_to_id: dict[str, str] = {}
    for container_id, raw_record in zip(container_ids, raw_records, strict=True):
        inspected = _core_container_record_from_inspect(
            container_id, owner, evidence, raw_record
        )
        if inspected.service not in selected_set:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        if inspected.service in service_to_id:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        service_to_id[inspected.service] = container_id
        records[container_id] = inspected
    if set(service_to_id) != selected_set:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
    _live_probe_remaining(deadline)
    return records


def _verified_live_core_caddy_container(
    owner: StandOwner,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> tuple[str, str]:
    """Return the sole running Caddy ID and identity in the signed Core projection."""
    try:
        if deadline is None or docker_context is None:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        if owner.stack != LIVE_STACK_CORE:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _assert_core_owner_unchanged(
            owner, deadline=deadline, docker_context=docker_context
        )
        evidence = _verify_stand_owner_compose_resources(
            WORKTREE,
            owner,
            deadline=deadline,
            docker_context=docker_context,
        )
        records = _live_core_caddy_container_inventory(
            owner,
            evidence,
            deadline=deadline,
            docker_context=docker_context,
        )
        caddy_records = [
            (container_id, record)
            for container_id, record in records.items()
            if record.service == "caddy"
        ]
        if (
            len(caddy_records) != 1
            or not caddy_records[0][1].running
            or caddy_records[0][1].status != "running"
        ):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _assert_core_owner_unchanged(
            owner, deadline=deadline, docker_context=docker_context
        )
        container_id, record = caddy_records[0]
        return container_id, record.identity
    except (OSError, RuntimeError, StandError, subprocess.SubprocessError):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None


def _assert_live_full_owner_unchanged(
    owner: StandOwner,
    *,
    deadline: float,
    docker_context: _LiveDockerReadContext,
) -> None:
    _live_probe_remaining(deadline)
    if owner.stack != LIVE_STACK_FULL or load_stand_owner(WORKTREE) != owner:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
    _require_owned_docker_daemon(
        owner, deadline=deadline, docker_context=docker_context
    )
    _live_probe_remaining(deadline)


def _verified_live_full_caddy_container(
    owner: StandOwner,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> tuple[str, str]:
    """Pin Caddy from the complete captured inventory of a signed Full owner."""
    try:
        if deadline is None or docker_context is None:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _live_probe_remaining(deadline)
        _assert_live_full_owner_unchanged(
            owner, deadline=deadline, docker_context=docker_context
        )
        evidence = _verify_stand_owner_compose_resources(
            WORKTREE,
            owner,
            deadline=deadline,
            docker_context=docker_context,
        )
        if (
            evidence.stack != LIVE_STACK_FULL
            or not evidence.managed_services
            or len(set(evidence.managed_services)) != len(evidence.managed_services)
            or "caddy" not in evidence.managed_services
        ):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _live_probe_remaining(deadline)

        container_ids = _project_container_ids(
            owner.project_name,
            deadline=deadline,
            docker_context=docker_context,
        )
        try:
            captured_ids = _validated_docker_container_ids(
                container_ids,
                maximum=_LIVE_CADDY_PROBE_MAX_PROJECT_CONTAINERS,
            )
        except _DockerProjectionError:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
        if not captured_ids:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        commands = _build_docker_inspect_projection_commands(captured_ids)
        if len(commands) != 1:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _live_probe_remaining(deadline)
        inspect_outputs = (
            _docker_output(
                commands[0][1:],
                _LIVE_CADDY_PROBE_FAILURE,
                deadline=deadline,
                docker_context=docker_context,
            ),
        )
        _live_probe_remaining(deadline)
        try:
            projections = _parse_docker_inspect_projection_inventory(
                captured_ids, inspect_outputs
            )
        except _DockerProjectionError:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None

        declared_volumes = set(evidence.declared_volume_names)
        managed_services = set(evidence.managed_services)
        caddy_projections: list[_DockerContainerProjection] = []
        for projection in projections:
            if (
                projection.project_label != owner.project_name
                or projection.service_label not in managed_services
                or projection.oneoff_label != "False"
            ):
                raise StandError(_LIVE_CADDY_PROBE_FAILURE)
            for mount in projection.mounts:
                if mount.mount_type == "volume":
                    if mount.name not in declared_volumes:
                        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
                elif mount.name is not None:
                    raise StandError(_LIVE_CADDY_PROBE_FAILURE)
            if projection.service_label == "caddy":
                caddy_projections.append(projection)
        if len(caddy_projections) != 1:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        caddy_id = caddy_projections[0].container_id

        _live_probe_remaining(deadline)
        caddy_record = _docker_inspect_object(
            ["inspect", "--type", "container", caddy_id],
            _LIVE_CADDY_PROBE_FAILURE,
            deadline=deadline,
            docker_context=docker_context,
        )
        caddy_config = caddy_record.get("Config")
        caddy_labels = (
            caddy_config.get("Labels") if isinstance(caddy_config, dict) else None
        )
        raw_mounts = caddy_record.get("Mounts")
        caddy_mount_contracts = [
            mounts for service, mounts in evidence.service_mounts if service == "caddy"
        ]
        if (
            not isinstance(caddy_labels, dict)
            or caddy_labels.get("com.docker.compose.oneoff") != "False"
            or not isinstance(raw_mounts, list)
            or len(caddy_mount_contracts) != 1
            or not caddy_mount_contracts[0]
        ):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        expected_mounts = caddy_mount_contracts[0]
        if any(
            not isinstance(mount, tuple)
            or len(mount) != 3
            or not isinstance(mount[0], str)
            or mount[0] not in _DOCKER_INSPECT_MOUNT_TYPES
            or not isinstance(mount[2], str)
            or not mount[2]
            or (
                mount[0] in {"volume", "bind"}
                and (not isinstance(mount[1], str) or not mount[1])
            )
            or (mount[0] == "tmpfs" and mount[1] is not None)
            for mount in expected_mounts
        ) or len({mount[2] for mount in expected_mounts}) != len(expected_mounts):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        inspected_mounts: list[_DockerMountProjection] = []
        inspected_mount_contract: list[tuple[str, str | None, str]] = []
        for mount in raw_mounts:
            if not isinstance(mount, dict):
                raise StandError(_LIVE_CADDY_PROBE_FAILURE)
            mount_type = mount.get("Type")
            mount_name = mount.get("Name") if mount_type == "volume" else None
            mount_source = mount.get("Source") if mount_type == "bind" else mount_name
            mount_target = mount.get("Destination")
            if (
                not isinstance(mount_type, str)
                or mount_type not in _DOCKER_INSPECT_MOUNT_TYPES
                or (mount_type == "volume" and not isinstance(mount_name, str))
                or (mount_type != "volume" and mount.get("Name") not in (None, ""))
                or (
                    mount_type == "bind"
                    and (not isinstance(mount_source, str) or not mount_source)
                )
                or (mount_type == "tmpfs" and mount_source is not None)
                or not isinstance(mount_target, str)
                or not mount_target
            ):
                raise StandError(_LIVE_CADDY_PROBE_FAILURE)
            inspected_mounts.append(_DockerMountProjection(mount_type, mount_name))
            inspected_mount_contract.append((mount_type, mount_source, mount_target))
        if tuple(inspected_mounts) != caddy_projections[0].mounts:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        if len({mount[2] for mount in inspected_mount_contract}) != len(
            inspected_mount_contract
        ) or sorted(inspected_mount_contract) != sorted(expected_mounts):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)

        inspected_caddy = _core_container_record_from_inspect(
            caddy_id, owner, evidence, caddy_record
        )
        if (
            inspected_caddy.service != "caddy"
            or not inspected_caddy.running
            or inspected_caddy.status != "running"
        ):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _live_probe_remaining(deadline)

        current_ids = _project_container_ids(
            owner.project_name,
            deadline=deadline,
            docker_context=docker_context,
        )
        try:
            current_ids = _validated_docker_container_ids(
                current_ids,
                maximum=_LIVE_CADDY_PROBE_MAX_PROJECT_CONTAINERS,
            )
        except _DockerProjectionError:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
        if set(current_ids) != set(captured_ids):
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _assert_live_full_owner_unchanged(
            owner, deadline=deadline, docker_context=docker_context
        )
        current_evidence = _verify_stand_owner_compose_resources(
            WORKTREE,
            owner,
            deadline=deadline,
            docker_context=docker_context,
        )
        if current_evidence != evidence:
            raise StandError(_LIVE_CADDY_PROBE_FAILURE)
        _live_probe_remaining(deadline)
        return caddy_id, inspected_caddy.identity
    except (OSError, RuntimeError, StandError, subprocess.SubprocessError):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None


def _verified_live_caddy_container(
    owner: StandOwner,
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> tuple[str, str]:
    """Dispatch the pin check to the exact signed Core or Full owner contract."""
    if owner.stack == LIVE_STACK_CORE:
        return _verified_live_core_caddy_container(
            owner,
            deadline=deadline,
            docker_context=docker_context,
        )
    if owner.stack == LIVE_STACK_FULL:
        return _verified_live_full_caddy_container(
            owner,
            deadline=deadline,
            docker_context=docker_context,
        )
    raise StandError(_LIVE_CADDY_PROBE_FAILURE)


def _assert_live_caddy_container_pin(
    owner: StandOwner,
    expected_pin: tuple[str, str],
    *,
    deadline: float | None = None,
    docker_context: _LiveDockerReadContext | None = None,
) -> None:
    if (
        _verified_live_caddy_container(
            owner,
            deadline=deadline,
            docker_context=docker_context,
        )
        != expected_pin
    ):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)


def _caddy_probe_timestamp_argument(timestamp_ms: int) -> str:
    if type(timestamp_ms) is not int or timestamp_ms <= 0:
        raise StandError(_LIVE_CADDY_PROBE_FAILURE)
    try:
        return (
            datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None


def _read_live_caddy_probe_logs(
    owner: StandOwner,
    *,
    container_pin: tuple[str, str],
    completed_at_ms: Mapping[str, int],
    password_nonce: str,
    correlation_ids: Mapping[str, str],
    deadline: float,
    docker_context: _LiveDockerReadContext | None = None,
) -> None:
    """Verify coalesced probe windows under shared budgets and fresh pins."""
    completed: subprocess.CompletedProcess[bytes] | None = None
    stdout = b""
    stderr = b""
    stage = "input_validation"
    try:
        if (
            not isinstance(completed_at_ms, Mapping)
            or set(completed_at_ms) != set(LIVE_CADDY_PROBE_PROJECTS)
            or not isinstance(correlation_ids, Mapping)
            or set(correlation_ids) != set(LIVE_CADDY_PROBE_PROJECTS)
            or not isinstance(password_nonce, str)
            or re.fullmatch(r"[0-9a-f]{32}", password_nonce) is None
            or any(
                not isinstance(correlation_ids[project], str)
                or re.fullmatch(r"[0-9a-f]{32}", correlation_ids[project]) is None
                for project in LIVE_CADDY_PROBE_PROJECTS
            )
            or len({password_nonce, *correlation_ids.values()}) != 3
        ):
            raise _LiveCaddyProbeStageFailure("input_validation")
        project_windows: dict[str, tuple[int, int]] = {}
        for project in LIVE_CADDY_PROBE_PROJECTS:
            observed_at_ms = completed_at_ms[project]
            if type(observed_at_ms) is not int or observed_at_ms <= 0:
                raise _LiveCaddyProbeStageFailure("input_validation")
            since_ms = max(1, observed_at_ms - _LIVE_CADDY_PROBE_WINDOW_MS)
            until_ms = observed_at_ms + _LIVE_CADDY_PROBE_WINDOW_MS
            project_windows[project] = (since_ms, until_ms)

        capture_windows: list[tuple[int, int]] = []
        for since_ms, until_ms in sorted(project_windows.values()):
            if capture_windows and since_ms <= capture_windows[-1][1]:
                capture_windows[-1] = (
                    capture_windows[-1][0],
                    max(capture_windows[-1][1], until_ms),
                )
            else:
                capture_windows.append((since_ms, until_ms))

        if time.monotonic() >= deadline:
            raise _LiveCaddyProbeStageFailure("deadline")
        if docker_context is None:
            stage = "context_resolution"
            docker_context = _new_live_docker_read_context()
        stage = "pre_pin"
        _assert_live_caddy_container_pin(
            owner,
            container_pin,
            deadline=deadline,
            docker_context=docker_context,
        )
        stage = "deadline"
        remaining = _live_probe_remaining(deadline)
        if remaining is None:
            raise _LiveCaddyProbeStageFailure("deadline")
        capture_deadline = time.monotonic() + min(
            _LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS, remaining
        )
        remaining_bytes = _LIVE_CADDY_PROBE_MAX_BYTES
        for since_ms, until_ms in capture_windows:
            stage = "deadline"
            remaining = _live_probe_remaining(deadline)
            capture_remaining = capture_deadline - time.monotonic()
            if remaining is None or capture_remaining <= 0:
                raise _LiveCaddyProbeStageFailure("deadline")
            stage = "input_validation"
            command = [
                "docker",
                "logs",
                "--timestamps",
                "--since",
                _caddy_probe_timestamp_argument(since_ms),
                "--until",
                _caddy_probe_timestamp_argument(until_ms),
                container_pin[0],
            ]
            stage = "log_read"
            try:
                completed = _run_live_bounded_read(
                    command,
                    context=docker_context,
                    deadline=min(deadline, capture_deadline),
                    maximum_bytes=remaining_bytes,
                    command_timeout_seconds=min(capture_remaining, remaining),
                )
            except _LiveBoundedReadFailure as error:
                failure_stage = {
                    "output_limit": "log_size",
                    "pipe_io": "log_pipe_io",
                }.get(error.reason, "log_read")
                raise _LiveCaddyProbeStageFailure(failure_stage) from None
            if completed.returncode != 0:
                raise _LiveCaddyProbeStageFailure("log_exit")
            received_bytes = len(completed.stdout or b"") + len(completed.stderr or b"")
            if received_bytes > remaining_bytes:
                raise _LiveCaddyProbeStageFailure("log_size")
            remaining_bytes -= received_bytes
            if len(capture_windows) > 1:
                # Do not manufacture a valid row from two truncated captures.
                # Keep the legacy single-capture final-line behavior unchanged.
                if completed.stdout and not completed.stdout.endswith(b"\n"):
                    raise _LiveCaddyProbeStageFailure("project_row")
                if completed.stderr and not completed.stderr.endswith(b"\n"):
                    raise _LiveCaddyProbeStageFailure("stderr_validation")
            stdout += completed.stdout or b""
            stderr += completed.stderr or b""
            completed.stdout = b""
            completed.stderr = b""
            completed = None
            stage = "deadline"
            if time.monotonic() >= capture_deadline:
                raise _LiveCaddyProbeStageFailure("deadline")
            _live_probe_remaining(deadline)

        invalid_stage: str | None = None
        for project in LIVE_CADDY_PROBE_PROJECTS:
            window = project_windows[project]
            try:
                _assert_live_caddy_probe_redaction(
                    stdout,
                    stderr=stderr,
                    password_nonce=password_nonce,
                    correlation_id=correlation_ids[project],
                    project=project,
                    since_ms=window[0],
                    until_ms=window[1],
                )
            except _LiveCaddyProbeStageFailure as error:
                if invalid_stage is None:
                    invalid_stage = error.stage
            except StandError:
                if invalid_stage is None:
                    invalid_stage = "project_row"
        if invalid_stage is not None:
            raise _LiveCaddyProbeStageFailure(invalid_stage)
        stage = "deadline"
        _live_probe_remaining(deadline)
    except _LiveCaddyProbeStageFailure:
        raise
    except (
        OSError,
        RuntimeError,
        StandError,
        subprocess.SubprocessError,
        ValueError,
        TypeError,
    ):
        raise _LiveCaddyProbeStageFailure(stage) from None
    finally:
        if completed is not None:
            completed.stdout = b""
            completed.stderr = b""
        stdout = b""
        stderr = b""
        try:
            if docker_context is None:
                raise _LiveCaddyProbeStageFailure("context_resolution")
            stage = "post_pin"
            _assert_live_caddy_container_pin(
                owner,
                container_pin,
                deadline=deadline,
                docker_context=docker_context,
            )
            stage = "deadline"
            _live_probe_remaining(deadline)
        except _LiveCaddyProbeStageFailure:
            raise
        except (OSError, RuntimeError, StandError, subprocess.SubprocessError):
            raise _LiveCaddyProbeStageFailure(stage) from None


def _verify_live_caddy_probe_log(
    owner: StandOwner,
    output_directory: Path,
    *,
    started_at_ms: int,
    finished_at_ms: int,
    password_nonce: str,
    correlation_ids: Mapping[str, str],
    container_pin: tuple[str, str],
    docker_context: _LiveDockerReadContext | None = None,
) -> None:
    """Require fresh correlated redaction rows for both Playwright projects."""
    stage = "input_validation"
    try:
        if (
            not isinstance(password_nonce, str)
            or re.fullmatch(r"[0-9a-f]{32}", password_nonce) is None
            or not isinstance(correlation_ids, Mapping)
            or set(correlation_ids) != set(LIVE_CADDY_PROBE_PROJECTS)
            or any(
                not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{32}", value) is None
                for value in correlation_ids.values()
            )
            or len({password_nonce, *correlation_ids.values()}) != 3
        ):
            raise _LiveCaddyProbeStageFailure("input_validation")
        if docker_context is None:
            stage = "context_resolution"
            docker_context = _new_live_docker_read_context()
        stage = "deadline"
        deadline = time.monotonic() + _LIVE_CADDY_PROBE_TOTAL_TIMEOUT_SECONDS
        _live_probe_remaining(deadline)
        stage = "marker_observation"
        try:
            observations = _read_live_caddy_probe_observations(
                output_directory,
                started_at_ms=started_at_ms,
                finished_at_ms=finished_at_ms,
                deadline=deadline,
            )
        except (OSError, RuntimeError, StandError, ValueError, TypeError):
            raise _LiveCaddyProbeStageFailure("marker_observation") from None
        stage = "deadline"
        _live_probe_remaining(deadline)
        stage = "log_read"
        _read_live_caddy_probe_logs(
            owner,
            container_pin=container_pin,
            completed_at_ms=observations,
            password_nonce=password_nonce,
            correlation_ids=correlation_ids,
            deadline=deadline,
            docker_context=docker_context,
        )
        stage = "deadline"
        _live_probe_remaining(deadline)
        print("live Caddy access-log redaction=verified projects=2", flush=True)
    except _LiveCaddyProbeStageFailure as error:
        _emit_live_caddy_probe_diagnostic(error.stage)
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    except (OSError, RuntimeError, StandError, subprocess.SubprocessError):
        _emit_live_caddy_probe_diagnostic(stage)
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None
    except Exception:
        _emit_live_caddy_probe_diagnostic("internal")
        raise StandError(_LIVE_CADDY_PROBE_FAILURE) from None


def _e2e_locked(
    admin_password: str,
    *,
    mode: str = "full",
    specs: Sequence[str] | None = None,
) -> None:
    selected_specs = _validated_live_e2e_specs(specs, mode=mode)
    _require_worktree()
    owner = load_stand_owner(WORKTREE)
    _seed_locked(admin_password, owner=owner)

    with tempfile.TemporaryDirectory(prefix="ue-live-playwright-") as temporary_root:
        temporary_path = Path(temporary_root)
        output_path = temporary_path / "playwright-output"
        output_path.mkdir()
        environment = _live_e2e_environment(
            output_directory=str(output_path),
            npm_config_directory=temporary_root,
        )
        frontend = (REPO_ROOT if IN_PLACE_MODE else WORKTREE) / "frontend"
        playwright_environment: dict[str, str] = {}
        probe_nonce = ""
        probe_ids: dict[str, str] = {}
        container_pin: tuple[str, str] | None = None
        try:
            _ensure_live_e2e_dependencies(frontend, environment)
            playwright_environment = dict(environment)
            probe_enabled = _live_e2e_probe_selected(mode, selected_specs)
            probe_started_at_ms = 0
            ports = dict(owner.published_ports)
            try:
                primary_repository_root = str(REPO_ROOT.resolve(strict=True))
            except (OSError, RuntimeError) as error:
                raise StandError(
                    "cannot resolve the primary repository for live endpoint verification"
                ) from error
            playwright_environment.update(
                {
                    "LIVE_BASE_URL": _stand_base_url(ports),
                    "LIVE_MAILPIT_URL": f"http://127.0.0.1:{ports['MAILPIT']}",
                    LIVE_PRIMARY_REPOSITORY_ROOT_ENV: primary_repository_root,
                    "TEST_PASSWORD": admin_password,
                }
            )
            if IN_PLACE_MODE:
                playwright_environment["LIVE_STAND_STATE_ROOT"] = str(
                    WORKTREE.resolve(strict=True)
                )
            if probe_enabled:
                probe_nonce, probe_ids = _new_live_caddy_probe_values()
                playwright_environment["LIVE_CADDY_LOG_PROBE"] = probe_nonce
                playwright_environment["LIVE_CADDY_PROBE_IDS"] = json.dumps(
                    probe_ids, separators=(",", ":")
                )
            if probe_enabled:
                admission_deadline = (
                    time.monotonic() + _LIVE_CADDY_PROBE_ADMISSION_TIMEOUT_SECONDS
                )
                docker_context = _new_live_docker_read_context()
                _live_probe_remaining(admission_deadline)
                _verify_stand_owner_compose_resources(
                    WORKTREE,
                    owner,
                    deadline=admission_deadline,
                    docker_context=docker_context,
                )
                _live_probe_remaining(admission_deadline)
                _require_owned_docker_daemon(
                    owner,
                    deadline=admission_deadline,
                    docker_context=docker_context,
                )
                _live_probe_remaining(admission_deadline)
                container_pin = _verified_live_caddy_container(
                    owner,
                    deadline=admission_deadline,
                    docker_context=docker_context,
                )
                _live_probe_remaining(admission_deadline)
                probe_started_at_ms = time.time_ns() // 1_000_000
            else:
                docker_context = None
                _verify_stand_owner_compose_resources(
                    WORKTREE,
                    owner,
                    docker_context=docker_context,
                )
                _require_owned_docker_daemon(owner, docker_context=docker_context)
            if selected_specs:
                _run_live_playwright(
                    cwd=frontend,
                    environment=playwright_environment,
                    mode=mode,
                    specs=selected_specs,
                )
            else:
                _run_live_playwright(
                    cwd=frontend,
                    environment=playwright_environment,
                    mode=mode,
                )
            if probe_enabled:
                if container_pin is None:
                    raise StandError(_LIVE_CADDY_PROBE_FAILURE)
                _verify_live_caddy_probe_log(
                    owner,
                    output_path,
                    started_at_ms=probe_started_at_ms,
                    finished_at_ms=time.time_ns() // 1_000_000,
                    password_nonce=probe_nonce,
                    correlation_ids=probe_ids,
                    container_pin=container_pin,
                    docker_context=docker_context,
                )
        finally:
            playwright_environment.pop("LIVE_CADDY_LOG_PROBE", None)
            playwright_environment.pop("LIVE_CADDY_PROBE_IDS", None)
            probe_nonce = ""
            probe_ids.clear()
            container_pin = None
            playwright_environment.pop("TEST_PASSWORD", None)
            playwright_environment.pop("LIVE_BASE_URL", None)
            playwright_environment.pop("LIVE_MAILPIT_URL", None)
            playwright_environment.pop(LIVE_PRIMARY_REPOSITORY_ROOT_ENV, None)
            playwright_environment.pop("LIVE_STAND_STATE_ROOT", None)
            playwright_environment.pop("LIVE_E2E_OUTPUT_DIR", None)
            playwright_environment.pop("PLAYWRIGHT_TEST_OUTPUT_DIR", None)
            environment.pop("LIVE_E2E_OUTPUT_DIR", None)
            environment.pop("PLAYWRIGHT_TEST_OUTPUT_DIR", None)


def e2e(mode: str = "full", *, specs: Sequence[str] | None = None) -> None:
    """Seed owned roles and use the same protected account across stand reruns."""
    selected_specs = _validated_live_e2e_specs(specs, mode=mode)
    admin_password = ""
    try:
        with stand_lifecycle_lock():
            owner = load_stand_owner(WORKTREE)
            admin_password = load_or_create_stand_admin_password(WORKTREE, owner)
            if selected_specs:
                _e2e_locked(admin_password, mode=mode, specs=selected_specs)
            else:
                _e2e_locked(admin_password, mode=mode)
    finally:
        admin_password = ""


def _readonly_status_snapshot(worktree: Path) -> tuple[tuple[str, object], ...]:
    """Hash stand inputs/state to detect concurrent changes without a lock write."""
    _assert_stand_paths_safe(worktree)
    snapshot: dict[str, object] = {}
    remaining_entries = 512

    def capture(path: Path, label: str, *, recurse: bool = False) -> None:
        nonlocal remaining_entries
        try:
            info = path.lstat()
        except FileNotFoundError:
            snapshot[label] = ("missing",)
            return
        except OSError:
            raise StandError(
                "cannot snapshot live stand state for read-only status"
            ) from None
        if _path_is_reparse_point(path):
            raise StandError("unsafe reparse point in live stand state")
        identity = (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        if stat.S_ISDIR(info.st_mode):
            if not recurse:
                snapshot[label] = ("directory", identity)
                return
            try:
                children = sorted(path.iterdir(), key=lambda child: child.name)
            except OSError:
                raise StandError(
                    "cannot snapshot live stand state for read-only status"
                ) from None
            for _child in children:
                remaining_entries -= 1
                if remaining_entries < 0:
                    raise StandError(
                        "live stand state exceeds the read-only snapshot limit"
                    )
            snapshot[label] = (
                "directory",
                identity,
                tuple(child.name for child in children),
            )
            for child in children:
                capture(child, f"{label}/{child.name}", recurse=True)
            return
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024 * 1024:
            raise StandError("unsupported file in live stand state snapshot")
        try:
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            after = path.lstat()
        except OSError:
            raise StandError(
                "cannot snapshot live stand state for read-only status"
            ) from None
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity != after_identity or _path_is_reparse_point(path):
            raise StandError(
                "live stand state changed during read-only status snapshot"
            )
        snapshot[label] = ("file", identity, content_hash)

    for relative in (
        Path(OVERLAY),
        Path(IN_PLACE_OVERLAY),
        Path(".env"),
        Path(".env.docker"),
        Path(".env.docker.workers"),
    ):
        capture(worktree / relative, f"stand/{relative.as_posix()}")
    capture(worktree / ".secrets", "stand/.secrets", recurse=True)
    owner_key = (
        worktree / ".secrets" / "live-stand-owner.key"
        if IN_PLACE_MODE
        else _git_common_directory() / "live-stand-owner.key"
    )
    capture(owner_key, "owner-signing-key")
    for relative in (Path("docker-compose.full.yml"), Path(OVERLAY)):
        capture(REPO_ROOT / relative, f"repository/{relative.as_posix()}")
    return tuple(sorted(snapshot.items()))


def _status_compose_output(
    command: Sequence[str], *, cwd: Path, env: dict[str, str]
) -> str:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed read-only Compose ps argv
            command,
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        raise StandError("cannot read live stand status") from None
    if not isinstance(completed.stdout, str):
        raise StandError("cannot read live stand status")
    return completed.stdout


def status() -> None:
    """Read status without creating, extending, or repairing the lifecycle lock."""
    before = _readonly_status_snapshot(WORKTREE)
    try:
        command, output, base_url, mailpit_url = _status_locked()
    except BaseException as error:
        try:
            after = _readonly_status_snapshot(WORKTREE)
        except StandError:
            raise
        if before != after:
            raise StandError(
                "live stand state changed during read-only status"
            ) from error
        raise
    after = _readonly_status_snapshot(WORKTREE)
    if before != after:
        raise StandError("live stand state changed during read-only status")
    print("+", " ".join(command), flush=True)
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    print(f"LIVE_BASE_URL={base_url}")
    print(f"LIVE_MAILPIT_URL={mailpit_url}")


def _status_locked() -> tuple[list[str], str, str, str]:
    _require_worktree(require_current_source=False)
    owner = load_stand_owner(WORKTREE)
    _require_owned_docker_daemon(owner)
    _verify_stand_owner_compose_resources(WORKTREE, owner)
    env = compose_control_environment(owner.project_name, dict(owner.published_ports))
    services = owner.selected_services if owner.stack == LIVE_STACK_CORE else ()
    command = compose_command("ps", *services, project_name=owner.project_name)
    output = _status_compose_output(command, cwd=WORKTREE, env=env)
    published = dict(owner.published_ports)
    return (
        command,
        output,
        _stand_base_url(published),
        f"http://127.0.0.1:{published['MAILPIT']}",
    )


def _stop_locked() -> None:
    """Stop only this owned stand's containers, preserving all data."""
    _require_worktree(require_current_source=False)
    owner = load_stand_owner(WORKTREE)
    _require_owned_docker_daemon(owner)
    _verify_stand_owner_compose_resources(WORKTREE, owner)
    env = compose_control_environment(owner.project_name, dict(owner.published_ports))
    _require_owned_docker_daemon(owner)
    services = owner.selected_services if owner.stack == LIVE_STACK_CORE else ()
    if load_stand_owner(WORKTREE) != owner:
        raise StandError("live stand ownership metadata changed before stop")
    _run(
        compose_command("stop", *services, project_name=owner.project_name),
        cwd=WORKTREE,
        env=env,
    )


def stop() -> None:
    with stand_lifecycle_lock():
        _stop_locked()


def _teardown_locked() -> None:
    """Remove the signed Compose resources and volumes; keep local files."""
    _require_worktree(require_current_source=False)
    owner = load_stand_owner(WORKTREE)
    _require_owned_docker_daemon(owner)
    if owner.compose_resource_fingerprint is None:
        raise StandError(
            "live stand ownership metadata lacks Compose resource evidence; refusing teardown"
        )
    evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
    # Match the secret-free control environment used for the resource projection.
    env = compose_control_environment(owner.project_name, dict(owner.published_ports))
    _require_owned_docker_daemon(owner)
    if owner.stack == LIVE_STACK_CORE:
        if owner.selected_services != LIVE_CORE_EXPECTED_SERVICES:
            raise StandError("signed live Core service closure is incomplete")
        _remove_core_compose_containers(owner, evidence)
        evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
        _remove_core_project_networks(owner, evidence)
        evidence = _verify_stand_owner_compose_resources(WORKTREE, owner)
        _remove_core_project_volumes(owner, evidence)
        return
    _run(
        compose_command("down", "--volumes", project_name=owner.project_name),
        cwd=WORKTREE,
        env=env,
    )


def teardown() -> None:
    with stand_lifecycle_lock():
        _teardown_locked()


def down() -> None:
    """Compatibility alias for the data-preserving stop command."""
    stop()


def _configure_state_mode(args: argparse.Namespace) -> None:
    """Select legacy worktree or strictly confined current-checkout mode."""
    global IN_PLACE_MODE, SOURCE_SHA, WORKTREE
    if bool(args.in_place) != bool(args.state_dir):
        raise StandError("--in-place and --state-dir must be supplied together")
    if not args.in_place:
        if IN_PLACE_MODE:
            WORKTREE = REPO_ROOT.parent / WORKTREE_NAME
        IN_PLACE_MODE = False
        SOURCE_SHA = None
        return
    IN_PLACE_MODE = True
    SOURCE_SHA = None
    WORKTREE = _validated_in_place_state_root(
        args.state_dir, create=args.command == "up"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def add_state_options(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--in-place",
            action="store_true",
            help="use the current checkout with generated state under an owned temp root",
        )
        command_parser.add_argument(
            "--state-dir",
            help="direct run directory under the system temp ue-live-acceptance root",
        )

    up_parser = commands.add_parser("up")
    add_state_options(up_parser)
    up_parser.add_argument("--ref", default="HEAD")
    up_parser.add_argument(
        "--stack",
        choices=LIVE_STACKS,
        default=LIVE_STACK_FULL,
        help="full stack (default) or the reviewed live Core dependency closure",
    )
    verify_parser = commands.add_parser(
        "verify-endpoints", help="verify live URLs against the signed owner marker"
    )
    verify_parser.add_argument("--base-url", required=True)
    verify_parser.add_argument("--mailpit-url", required=True)
    add_state_options(verify_parser)
    seed_parser = commands.add_parser("seed")
    add_state_options(seed_parser)
    seed_parser.add_argument("--demo", action="store_true", required=True)
    e2e_parser = commands.add_parser("e2e")
    add_state_options(e2e_parser)
    e2e_parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    e2e_parser.add_argument(
        "--spec",
        action="append",
        dest="specs",
        metavar="TRACKED_SPEC",
        help="diagnostic-only rerun; serial full-suite specs may depend on earlier cases",
    )
    for command_name in (
        "status",
        "stop",
        "down",
        "quiesce",
        "teardown",
        "nats-outage",
    ):
        command_parser = commands.add_parser(command_name)
        add_state_options(command_parser)
    args = parser.parse_args(argv)
    try:
        selected_specs = (
            _validated_live_e2e_specs(args.specs, mode=args.mode)
            if args.command == "e2e"
            else ()
        )
        if args.command == "nats-outage" and (not args.in_place or not args.state_dir):
            raise StandError("owned NATS outage requires --in-place and --state-dir")
        try:
            _configure_state_mode(args)
        except Exception:
            if args.command == "nats-outage":
                raise StandError("owned NATS acceptance failed") from None
            raise
        if args.command == "nats-outage":
            try:
                from scripts.owned_nats_coordinator import (
                    OutageOutcome,
                    OutageResult,
                    OutageStage,
                )
                from scripts.owned_nats_outage_cli import run_owned_nats_outage

                result = run_owned_nats_outage(
                    args.state_dir,
                    in_place=args.in_place,
                )
            except Exception:
                raise StandError("owned NATS acceptance failed") from None
            if (
                type(result) is not OutageResult
                or result.outcome is not OutageOutcome.ACCEPTED
                or result.stage is not OutageStage.COMPLETE
            ):
                raise StandError("owned NATS acceptance failed")
        elif args.command == "up":
            up(args.ref, stack=args.stack)
        elif args.command == "verify-endpoints":
            verify_live_endpoints(args.base_url, args.mailpit_url)
            print("live stand endpoints verified")
        elif args.command == "seed":
            seed()
        elif args.command == "e2e":
            if selected_specs:
                e2e(args.mode, specs=selected_specs)
            else:
                e2e(args.mode)
        elif args.command == "status":
            status()
        elif args.command in {"stop", "down"}:
            stop()
        elif args.command == "quiesce":
            quiesce()
        elif args.command == "teardown":
            teardown()
        else:
            raise AssertionError(f"unexpected command {args.command}")
    except StandError as error:
        print(f"live_stand: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
