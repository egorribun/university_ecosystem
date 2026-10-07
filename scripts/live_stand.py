"""Owned live acceptance stand running the full stack.

By default the stand runs from ``../ue-live`` (a detached git worktree).
Explicit ``--in-place --state-dir`` mode keeps generated configuration under
an owned temporary run root while using the current checkout as its build
context. Every run receives a unique Compose project recorded in an ownership
marker, so its volumes and networks are isolated from other stacks.

Usage::

    python scripts/live_stand.py up [--ref HEAD]   # create/refresh the worktree and start
    python scripts/live_stand.py up --in-place --state-dir <owned-temp-run> --ref HEAD
    python scripts/live_stand.py seed --demo        # load demo users and content
    python scripts/live_stand.py e2e [--mode smoke|full]  # reseed and run live Playwright safely
    python scripts/live_stand.py status             # read-only status
    python scripts/live_stand.py stop               # stop containers; preserve data
    python scripts/live_stand.py teardown           # remove only this run's Compose data

``down`` remains a compatibility alias for ``stop``. ``teardown`` preserves
the worktree, ``.env*`` files, secrets and evidence; it removes volumes only
after validating the run ownership marker.
"""

from __future__ import annotations

import argparse
import base64
import csv
import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKTREE_NAME = "ue-live"
WORKTREE = REPO_ROOT.parent / WORKTREE_NAME
IN_PLACE_MODE = False
SOURCE_SHA: str | None = None
IN_PLACE_OWNER_SCHEMA_VERSION = 7
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
    ("MAILPIT", "mailpit", 8025),
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
PORT_RANGE = (20000, 45000)
PORT_BIND_HOST = "127.0.0.1"
VAPID_FILE = Path(".secrets") / "live-vapid.json"
ADMIN_PASSWORD_FILE = Path(".secrets") / "live-admin-password.json"
STAND_FILE = Path(".secrets") / "live-stand.json"
PROJECT_PREFIX = "ue-live-"
PROJECT_PATTERN = re.compile(r"^ue-live-[0-9a-f]{16}$")
OWNER_SCHEMA_VERSION = 6
RESOURCE_OWNER_SCHEMA_VERSION = 5
PREVIOUS_OWNER_SCHEMA_VERSION = 4
VOLUME_OWNER_SCHEMA_VERSION = 3
LEGACY_OWNER_SCHEMA_VERSION = 2
DAEMON_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMPOSE_INSPECTION_PLACEHOLDER = "live-stand-inspection-placeholder"
SEED_SCRIPTS = (
    "scripts/seed_demo_data.py",
    "scripts/seed_admin_data.py",
    "scripts/seed_live_authorization.py",
)
LIVE_E2E_COMMAND = ("npm", "run", "test:e2e:live")
LIVE_E2E_SMOKE_FILES = (
    "tests/e2e-live/auth-roles.live.spec.ts",
    "tests/e2e-live/password-reset.live.spec.ts",
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
    source_sha: str | None = None


@dataclass(frozen=True)
class ComposeResourceEvidence:
    """Canonical project resources in the resolved Compose model."""

    fingerprint: str
    managed_volumes: tuple[tuple[str, str], ...]
    declared_volume_names: tuple[str, ...] = ()
    managed_networks: tuple[tuple[str, str], ...] = ()
    managed_services: tuple[str, ...] = ()


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


def _windows_user_sid() -> str:
    """Return the current Windows user SID without exposing command output."""
    whoami = shutil.which("whoami.exe") or shutil.which("whoami")
    if whoami is None:
        raise StandError("cannot verify the current Windows user for live state ACLs")
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
    icacls = shutil.which("icacls.exe") or shutil.which("icacls")
    if icacls is None:
        raise StandError("cannot enforce private Windows permissions for live state")
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

    icacls = shutil.which("icacls.exe") or shutil.which("icacls")
    if icacls is None:
        raise StandError("cannot enforce private Windows permissions for live state")
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


def docker_daemon_fingerprint() -> str:
    """Return a stable, non-secret fingerprint for the selected Docker daemon."""
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ID}}"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise StandError("cannot verify Docker daemon identity") from error
    daemon_id = result.stdout.strip()
    if not daemon_id:
        raise StandError("cannot verify Docker daemon identity")
    return hashlib.sha256(daemon_id.encode("utf-8")).hexdigest()


def _require_owned_docker_daemon(owner: StandOwner) -> None:
    if owner.daemon_fingerprint is None:
        raise StandError(
            "cannot verify Docker daemon ownership for this stand; refusing lifecycle command"
        )
    current_fingerprint = docker_daemon_fingerprint()
    if not hmac.compare_digest(current_fingerprint, owner.daemon_fingerprint):
        raise StandError("different Docker daemon detected; refusing lifecycle command")


def _validate_published_ports(
    ports: Mapping[str, object], *, allow_privileged: bool = False
) -> tuple[tuple[str, int], ...]:
    expected = tuple(name for name, _service, _target in LIVE_PORT_SPECS)
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


def choose_published_ports() -> dict[str, int]:
    """Choose a distinct currently free loopback port for every published service."""
    low, high = PORT_RANGE
    chosen: dict[str, int] = {}
    for name, _service, _container_port in LIVE_PORT_SPECS:
        for _attempt in range(1000):
            port = low + secrets.randbelow(high - low + 1)
            if port in chosen.values():
                continue
            if port_is_free(port, host=PORT_BIND_HOST):
                chosen[name] = port
                break
        else:
            raise StandError(f"could not allocate a free loopback port for {name}")
    return chosen


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
    worktree: Path, *, published_ports: Mapping[str, int] | None = None
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
    port_map = _validate_published_ports(
        published_ports if published_ports is not None else choose_published_ports()
    )
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
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or (schema_version == LEGACY_OWNER_SCHEMA_VERSION and set(data) != legacy_keys)
        or (schema_version == VOLUME_OWNER_SCHEMA_VERSION and set(data) != volume_keys)
        or (
            schema_version == PREVIOUS_OWNER_SCHEMA_VERSION and set(data) != daemon_keys
        )
        or (
            schema_version == RESOURCE_OWNER_SCHEMA_VERSION
            and set(data) not in (resource_keys, resumable_resource_keys)
        )
        or (
            schema_version == OWNER_SCHEMA_VERSION
            and set(data) not in (resource_keys, resumable_resource_keys)
        )
        or (
            schema_version == IN_PLACE_OWNER_SCHEMA_VERSION
            and (
                not IN_PLACE_MODE
                or set(data) != in_place_resource_keys
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
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        raw_ports = data["published_ports"]
        if not isinstance(raw_ports, dict):
            raise StandError(f"invalid port map in ownership metadata: {marker}")
        port_map = dict(_validate_published_ports(raw_ports))
    else:
        port_map = LEGACY_PUBLISHED_PORTS.copy()
    daemon_fingerprint: str | None = None
    if schema_version in {
        PREVIOUS_OWNER_SCHEMA_VERSION,
        RESOURCE_OWNER_SCHEMA_VERSION,
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
    if schema_version in {
        RESOURCE_OWNER_SCHEMA_VERSION,
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
            if (
                compose_resource_fingerprint is not None
                and resume_compose_resource_fingerprint is not None
            ):
                raise StandError(
                    "ownership metadata cannot contain active and resumable Compose evidence"
                )
    source_sha = (
        data.get("source_sha")
        if schema_version == IN_PLACE_OWNER_SCHEMA_VERSION
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
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        payload["published_ports"] = port_map
    if schema_version in {
        PREVIOUS_OWNER_SCHEMA_VERSION,
        RESOURCE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        payload["daemon_fingerprint"] = daemon_fingerprint
    if schema_version in {
        RESOURCE_OWNER_SCHEMA_VERSION,
        OWNER_SCHEMA_VERSION,
        IN_PLACE_OWNER_SCHEMA_VERSION,
    }:
        payload["compose_resource_fingerprint"] = compose_resource_fingerprint
        if "resume_compose_resource_fingerprint" in data:
            payload["resume_compose_resource_fingerprint"] = (
                resume_compose_resource_fingerprint
            )
    if schema_version == IN_PLACE_OWNER_SCHEMA_VERSION:
        payload["source_sha"] = source_sha
    signature = data["signature"]
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, _owner_signature(payload, _owner_signing_key(create=False))
    ):
        raise StandError("ownership metadata signature is invalid")
    return StandOwner(
        repository=str(marker_repository),
        worktree=str(marker_worktree),
        project_name=project_name,
        published_ports=tuple(port_map.items()),
        schema_version=schema_version,
        daemon_fingerprint=daemon_fingerprint,
        compose_resource_fingerprint=compose_resource_fingerprint,
        resume_compose_resource_fingerprint=resume_compose_resource_fingerprint,
        source_sha=source_sha,
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
        source_sha=SOURCE_SHA if IN_PLACE_MODE else None,
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
    evidence = _compose_resource_evidence(
        worktree, current.project_name, dict(current.published_ports)
    )
    if (
        current.resume_compose_resource_fingerprint is not None
        and not hmac.compare_digest(
            evidence.fingerprint, current.resume_compose_resource_fingerprint
        )
    ):
        raise StandError(
            "resolved Compose resource identity differs from signed resume evidence"
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
        source_sha=current.source_sha,
    )
    return _write_stand_owner_update(worktree, updated)


def _verify_stand_owner_compose_resources(
    worktree: Path,
    owner: StandOwner,
    *,
    allow_existing_owned_volumes: bool = True,
) -> ComposeResourceEvidence:
    """Fail closed if the signed owner no longer matches the resolved Compose model."""
    current = load_stand_owner(worktree)
    if current != owner:
        raise StandError("live stand ownership metadata changed")
    if not _is_active_owner_schema(current.schema_version):
        raise StandError(
            "live stand ownership lacks Compose resource evidence for the current schema; re-run up before lifecycle operations"
        )
    if current.compose_resource_fingerprint is None:
        raise StandError(
            "live stand ownership lacks Compose resource evidence; refusing lifecycle operation"
        )
    evidence = _compose_resource_evidence(
        worktree, current.project_name, dict(current.published_ports)
    )
    if not hmac.compare_digest(
        evidence.fingerprint, current.compose_resource_fingerprint
    ):
        raise StandError(
            "resolved Compose resources differ from signed live stand ownership"
        )
    _assert_compose_volume_ownership(
        current.project_name,
        evidence.managed_volumes,
        declared_volume_names=evidence.declared_volume_names,
        allow_existing_owned=allow_existing_owned_volumes,
        managed_networks=evidence.managed_networks,
        managed_services=evidence.managed_services,
    )
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
        source_sha=current.source_sha,
    )
    return _write_stand_owner_update(worktree, updated)


def stand_environment(
    keys: dict[str, str],
    project_name: str,
    published_ports: Mapping[str, int] = LEGACY_PUBLISHED_PORTS,
) -> dict[str, str]:
    _validate_project_name(project_name)
    ports = dict(_validate_published_ports(published_ports, allow_privileged=True))
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project_name
    env["LIVE_VAPID_PUBLIC_KEY"] = keys["public"]
    env["LIVE_VAPID_PRIVATE_KEY"] = keys["private"]
    env["LIVE_BASE_URL"] = _stand_base_url(ports)
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
    published_ports: Mapping[str, int] = LEGACY_PUBLISHED_PORTS,
) -> dict[str, str]:
    """Build a secret-free environment for read/stop/remove Compose commands."""
    _validate_project_name(project_name)
    ports = dict(_validate_published_ports(published_ports, allow_privileged=True))
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project_name
    env["LIVE_BASE_URL"] = _stand_base_url(ports)
    # Compose interpolates these required live-overlay fields while loading
    # the project, even for `ps`, `stop`, or `down`. These commands never
    # recreate containers, so a fixed non-secret placeholder is sufficient.
    env["LIVE_VAPID_PUBLIC_KEY"] = COMPOSE_INSPECTION_PLACEHOLDER
    env["LIVE_VAPID_PRIVATE_KEY"] = COMPOSE_INSPECTION_PLACEHOLDER
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


def _compose_resource_evidence(
    worktree: Path,
    project_name: str,
    published_ports: Mapping[str, int],
) -> ComposeResourceEvidence:
    """Resolve removable resources and service topology without runtime secrets."""
    _validate_project_name(project_name)
    command = compose_command("config", "--format", "json", project_name=project_name)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed Compose argv and validated project
            command,
            cwd=worktree,
            env=compose_control_environment(project_name, published_ports),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise StandError("cannot verify resolved Compose resource ownership") from None
    try:
        project = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        raise StandError("cannot parse resolved Compose resource ownership") from None
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

    projection = {
        "project_name": project_name,
        "volumes": volumes,
        "networks": networks,
        "service_mounts": service_mounts,
    }
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


def _assert_compose_volume_ownership(
    project_name: str,
    managed_volumes: Sequence[tuple[str, str]],
    *,
    declared_volume_names: Sequence[str],
    allow_existing_owned: bool,
    managed_networks: Sequence[tuple[str, str]] = (),
    managed_services: Sequence[str] = (),
) -> tuple[tuple[str, str], ...]:
    """Check every project resource that Compose teardown could remove."""
    _validate_project_name(project_name)
    existing: list[tuple[str, str]] = []
    if any(not isinstance(name, str) or not name for name in declared_volume_names):
        raise StandError("resolved Compose volume ownership is ambiguous")
    allowed_volume_names = set(declared_volume_names)

    def inventory(command: list[str], error_message: str) -> str:
        try:
            completed = subprocess.run(  # noqa: S603 - fixed Docker inventory probes with validated resource names
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
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

    def inspect_mounts(command: list[str], error_message: str) -> list[object]:
        output = inventory(command, error_message)
        try:
            mounts = json.loads(output)
        except json.JSONDecodeError:
            raise StandError(error_message) from None
        if not isinstance(mounts, list):
            raise StandError(error_message)
        return mounts

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
            "--filter",
            project_filter,
        ],
        "cannot verify live stand Docker container ownership",
    ).splitlines()
    allowed_services = set(managed_services)
    for container_id in container_ids:
        if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
            raise StandError("live stand container inventory is ambiguous")
        if not allow_existing_owned:
            raise StandError(
                "a live stand container already exists before its first Compose startup"
            )
        labels = inspect_labels(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .Config.Labels}}",
                container_id,
            ],
            "cannot verify existing live stand container labels",
        )
        if (
            labels.get("com.docker.compose.project") != project_name
            or labels.get("com.docker.compose.service") not in allowed_services
        ):
            raise StandError(
                "an existing live stand container is not owned by the expected Compose project"
            )
        mounts = inspect_mounts(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .Mounts}}",
                container_id,
            ],
            "cannot verify existing live stand container mounts",
        )
        for mount in mounts:
            if not isinstance(mount, dict):
                raise StandError("live stand container mount inventory is ambiguous")
            mount_type = mount.get("Type")
            if mount_type not in {"volume", "bind", "tmpfs"}:
                raise StandError("live stand container mount inventory is ambiguous")
            if mount_type == "volume":
                volume_name = mount.get("Name")
                if (
                    not isinstance(volume_name, str)
                    or volume_name not in allowed_volume_names
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


def require_free_ports(ports: Mapping[str, int] | Sequence[int]) -> None:
    values = (
        tuple(dict(_validate_published_ports(ports, allow_privileged=True)).values())
        if isinstance(ports, Mapping)
        else tuple(ports)
    )
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


def _up_locked(ref: str) -> None:
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
        global SOURCE_SHA
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
        if IN_PLACE_MODE and existing_owner.source_sha != SOURCE_SHA:
            raise StandError("owned in-place stand belongs to a different source SHA")
        if IN_PLACE_MODE:
            _ensure_private_state_directory(WORKTREE, owner_verified=True)
            _ensure_private_state_directory(WORKTREE / ".secrets", owner_verified=True)
    elif IN_PLACE_MODE and WORKTREE.exists():
        raise StandError("in-place state directory exists without an owner marker")
    published_ports = choose_published_ports()
    require_free_ports(published_ports)
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
            _run(
                compose_command("stop", project_name=existing_owner.project_name),
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
    _assert_stand_paths_safe(WORKTREE)
    if not (WORKTREE / STAND_FILE).is_file():
        owner = create_stand_owner(WORKTREE, published_ports=published_ports)
    else:
        if existing_owner is None:
            raise StandError("stand ownership metadata appeared during startup")
        owner = update_stand_owner_ports(WORKTREE, existing_owner, published_ports)
    # Catch ports claimed while the old project stopped or the worktree moved.
    # On failure the old stand data remains intact and no new build is started.
    require_free_ports(dict(owner.published_ports))
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
        _run(
            compose_command("stop", project_name=owner.project_name),
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
    if IN_PLACE_MODE:
        start_command.extend(
            ("-LiveStandStateRoot", str(WORKTREE.resolve(strict=True)))
        )
    if allow_existing_owned_volumes:
        start_command.append("-AllowExistingOwnedVolumes")
    _run(start_command, cwd=WORKTREE, env=env)
    published = dict(owner.published_ports)
    base_url = _stand_base_url(published)
    mailpit_url = f"http://127.0.0.1:{published['MAILPIT']}"
    print(f"stand {owner.project_name} is up at {base_url} for {sha}")
    print(f"LIVE_BASE_URL={base_url}")
    print(f"LIVE_MAILPIT_URL={mailpit_url}")


def up(ref: str) -> None:
    with stand_lifecycle_lock():
        _up_locked(ref)


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
    config_root = Path(npm_config_directory)
    _mark_live_e2e_output_directory(output_directory, config_root)
    npm_user_config = config_root / "npm-userconfig"
    npm_global_config = config_root / "npm-globalconfig"
    for config_path in (npm_user_config, npm_global_config):
        with config_path.open("x", encoding="utf-8"):
            pass
    browser_cache = _playwright_browser_cache_path(env)

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
    """Use Playwright's per-user cache while passing its location explicitly."""
    windows = (platform or os.name) == "nt"
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
    "tests/e2e-live/settings-password-change-rollback.live.spec.ts",
    "tests/e2e-live/settings-tabs-keyboard.live.spec.ts",
    "tests/e2e-live/settings-theme-roundtrip.live.spec.ts",
    "tests/e2e-live/ssr-hydration-i18n.live.spec.ts",
    "tests/e2e-live/story-viewer-keyboard.live.spec.ts",
    "tests/e2e-live/story-viewer-memory.live.spec.ts",
    "tests/e2e-live/story-viewer-reduced-motion.live.spec.ts",
    "tests/e2e-live/totp-recovery.live.spec.ts",
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
_PLAYWRIGHT_HTTP_STATUS_LINE = re.compile(
    r"UE_LIVE_HTTP_STATUS_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>admin-users|admin-feature-flags|admin-feature-flags-ui|password-reset-replay) "
    r"status=(?P<status>[1-5][0-9]{2})"
)
_PLAYWRIGHT_HTTP_STATUS_CHECKS = {
    check: check
    for check in (
        "admin-users",
        "admin-feature-flags",
        "admin-feature-flags-ui",
        "password-reset-replay",
    )
}
# Both projects × four checks × two attempts (CI retries once).
_PLAYWRIGHT_HTTP_STATUS_LIMIT = 16


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
        record = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            _PLAYWRIGHT_HTTP_STATUS_CHECKS[match["check"]],
            int(match["status"]),
        )
        if record not in statuses:
            statuses.append(record)
            if len(statuses) == _PLAYWRIGHT_HTTP_STATUS_LIMIT:
                break
    return statuses


_PLAYWRIGHT_PAGE_ERROR_LINE = re.compile(
    r"UE_LIVE_PAGE_ERROR_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>password-reset|admin-notifications) "
    r"page=(?P<page>register|login|forgot-password|reset-password|dashboard|admin-notifications|other) "
    r"type=(?P<type>error|type-error|reference-error|syntax-error|range-error|uri-error|"
    r"eval-error|aggregate-error|abort-error|security-error|invalid-state-error|react-418|other) "
    r"count=(?P<count>[1-9][0-9]{0,2})"
)
_PLAYWRIGHT_PAGE_ERROR_LIMIT = 248


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
        elif match["page"] == "admin-notifications" or match["type"] == "react-418":
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


def _live_playwright_counts(output: str) -> dict[str, int]:
    """Extract only numeric aggregate counts from exact Playwright summary lines."""
    counts: dict[str, int] = {}
    for line in output.split("\n"):
        match = _PLAYWRIGHT_COUNT_LINE.fullmatch(line.removesuffix("\r"))
        if match is not None:
            kind = match.group("kind").replace(" ", "_")
            counts[kind] = counts.get(kind, 0) + int(match.group("count"))
    return counts


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
    # Only the reviewed helpers' stdout protocols can emit these diagnostics.
    http_statuses = _live_playwright_http_statuses(stdout)
    page_errors = _live_playwright_page_errors(stdout)
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
    for project, check, current_page, error_type, count in page_errors:
        print(
            f"live E2E page error project={project} check={check} "
            f"page={current_page} type={error_type} count={count}",
            flush=True,
        )
    outcome = "passed" if return_code == 0 else "failed"
    print(f"live E2E outcome={outcome} exit_code={return_code}", flush=True)
    if return_code != 0:
        raise StandError(f"live Playwright E2E failed with exit code {return_code}")


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
        try:
            _ensure_live_e2e_dependencies(frontend, environment)
            playwright_environment = dict(environment)
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
            _verify_stand_owner_compose_resources(WORKTREE, owner)
            _require_owned_docker_daemon(owner)
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
        finally:
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


def status() -> None:
    _require_worktree(require_current_source=False)
    owner = load_stand_owner(WORKTREE)
    env = compose_control_environment(owner.project_name, dict(owner.published_ports))
    _run(compose_command("ps", project_name=owner.project_name), cwd=WORKTREE, env=env)
    published = dict(owner.published_ports)
    print(f"LIVE_BASE_URL={_stand_base_url(published)}")
    print(f"LIVE_MAILPIT_URL=http://127.0.0.1:{published['MAILPIT']}")


def _stop_locked() -> None:
    """Stop only this owned stand's containers, preserving all data."""
    _require_worktree(require_current_source=False)
    owner = load_stand_owner(WORKTREE)
    _require_owned_docker_daemon(owner)
    _verify_stand_owner_compose_resources(WORKTREE, owner)
    env = compose_control_environment(owner.project_name, dict(owner.published_ports))
    _require_owned_docker_daemon(owner)
    _run(
        compose_command("stop", project_name=owner.project_name), cwd=WORKTREE, env=env
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
    _verify_stand_owner_compose_resources(WORKTREE, owner)
    # Match the secret-free control environment used for the resource projection.
    env = compose_control_environment(owner.project_name, dict(owner.published_ports))
    _require_owned_docker_daemon(owner)
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
    for command_name in ("status", "stop", "down", "teardown"):
        command_parser = commands.add_parser(command_name)
        add_state_options(command_parser)
    args = parser.parse_args(argv)
    try:
        selected_specs = (
            _validated_live_e2e_specs(args.specs, mode=args.mode)
            if args.command == "e2e"
            else ()
        )
        _configure_state_mode(args)
        if args.command == "up":
            up(args.ref)
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
