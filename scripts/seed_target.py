"""Fail-closed target checks shared by the demo seed entry points."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

ADMIN_SMOKE_WORKFLOW = "Admin Smoke Monitoring (Linux Periodic)"
ADMIN_SMOKE_TARGET = "admin-smoke"
ADMIN_SMOKE_PROJECT = "ci-admin-smoke"

# AUD-313: seed authorization never comes from environment variables alone.
# The record is intentionally unsigned. Trust in its origin rests on the operator
# invoking live_stand, which verifies the signed owner marker and bind-mounts the
# generated file read-only here; environment values are only cross-checked.
OWNED_STAND_RECORD_PATH = Path("/run/live-stand/owned-stand.json")
OWNED_STAND_RECORD_SCHEMA_VERSION = 1
OWNED_STAND_RECORD_MAX_BYTES = 4096
OWNED_STAND_RECORD_KEYS = frozenset({"schema_version", "project_name", "database_host"})
OWNED_STAND_DATABASE_HOST = "postgres"


def _read_mountinfo_text() -> str:
    """Read kernel mount evidence; unavailable mount data fails closed."""
    try:
        return Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _unescape_mountinfo_path(value: str) -> str:
    """Decode the four octal escapes used for path fields in mountinfo."""
    return re.sub(
        r"\\(040|011|012|134)",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


def _has_exact_readonly_mount(path: Path) -> bool:
    """Require one exact mountpoint for the record with per-mount ``ro``."""
    matches: list[bool] = []
    for line in _read_mountinfo_text().splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        if separator < 6 or len(fields) < separator + 4:
            continue
        if _unescape_mountinfo_path(fields[4]) == str(path):
            matches.append("ro" in fields[5].split(","))
    # A regular file in a read-only parent directory has no mountpoint at its
    # own path. Requiring exactly one entry also rejects stacked mount overlays.
    return matches == [True]


def _configured_database_url() -> str:
    from app.core.config import settings

    return str(settings.database_url)


def _require_admin_smoke_target() -> str:
    expected_environment = {
        "ENVIRONMENT": "testing",
        "UE_SEED_TARGET": ADMIN_SMOKE_TARGET,
        "GITHUB_ACTIONS": "true",
        "GITHUB_WORKFLOW": ADMIN_SMOKE_WORKFLOW,
        "GITHUB_REF": "refs/heads/main",
    }
    if any(
        os.environ.get(name) != value for name, value in expected_environment.items()
    ):
        raise RuntimeError("admin-smoke seed target is not authorized")

    if os.environ.get("GITHUB_EVENT_NAME") not in {"workflow_dispatch", "schedule"}:
        raise RuntimeError("admin-smoke seed target has an unsupported event")
    if (
        re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
            os.environ.get("GITHUB_REPOSITORY", ""),
        )
        is None
    ):
        raise RuntimeError("admin-smoke seed target has an invalid repository context")
    if any(
        re.fullmatch(r"[1-9][0-9]*", os.environ.get(name, "")) is None
        for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    ):
        raise RuntimeError("admin-smoke seed target has an invalid run identity")

    try:
        workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)
        checkout = Path(__file__).resolve(strict=True).parents[1]
        target = make_url(_configured_database_url())
    except (KeyError, OSError, RuntimeError, ValueError):
        raise RuntimeError("cannot verify the admin-smoke seed target") from None

    if workspace != checkout:
        raise RuntimeError("admin-smoke seed target checkout does not match")
    if (
        target.get_backend_name() != "postgresql"
        or target.host not in {"localhost", "127.0.0.1", "::1"}
        or target.port != 5432
        or target.database != "test_admin_smoke"
        or target.username != "test"
        or target.query
    ):
        raise RuntimeError("admin-smoke seed database target is not the test service")

    return ADMIN_SMOKE_PROJECT


def _load_owned_stand_record(path: Path) -> dict[str, Any]:
    """Read the owner-issued record; only a bounded regular file is accepted."""
    message = "seed requires the owner-issued live stand record"
    try:
        status = os.lstat(path)
        if not stat.S_ISREG(status.st_mode) or status.st_size > (
            OWNED_STAND_RECORD_MAX_BYTES
        ):
            raise RuntimeError(message)
        with path.open("rb") as handle:
            raw = handle.read(OWNED_STAND_RECORD_MAX_BYTES + 1)
        if len(raw) > OWNED_STAND_RECORD_MAX_BYTES:
            raise RuntimeError(message)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        raise RuntimeError(message) from None
    if not isinstance(data, dict) or set(data) != OWNED_STAND_RECORD_KEYS:
        raise RuntimeError(message)
    return data


def require_owned_live_stand_target() -> str:
    """Require a verified live stand or the bounded admin-smoke test target."""
    explicit_target = os.environ.get("UE_SEED_TARGET")
    if explicit_target is not None:
        if explicit_target != ADMIN_SMOKE_TARGET:
            raise RuntimeError("unsupported explicit seed target")
        return _require_admin_smoke_target()

    project = os.environ.get("LIVE_STAND_SEED_PROJECT", "")
    # live_stand creates owned projects as ue-live-<token_hex(8)> only (AUD-313).
    if (
        not project
        or os.environ.get("LIVE_STAND_OWNER_VERIFIED") != "1"
        or os.environ.get("COMPOSE_PROJECT_NAME") != project
        or re.fullmatch(r"ue-live-[0-9a-f]{16}", project) is None
    ):
        raise RuntimeError(
            "seed requires an explicitly verified owned live stand project"
        )

    try:
        target = make_url(_configured_database_url())
    except Exception:
        raise RuntimeError(
            "cannot verify the live stand seed database target"
        ) from None

    if (
        target.get_backend_name() != "postgresql"
        or target.host != OWNED_STAND_DATABASE_HOST
    ):
        raise RuntimeError(
            "seed database must be the postgres service in the owned live stand project"
        )

    record_path = OWNED_STAND_RECORD_PATH
    if not _has_exact_readonly_mount(record_path):
        raise RuntimeError(
            "seed requires the owner-issued live stand record at an "
            "exact read-only mount"
        )
    record = _load_owned_stand_record(record_path)
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != OWNED_STAND_RECORD_SCHEMA_VERSION
        or record["project_name"] != project
        or record["database_host"] != target.host
    ):
        raise RuntimeError("live stand seed record does not match the owned stand")

    # AUD-313 evidence: printed only after the mount check and record match above,
    # so a hosted log line proves the record really was one exact read-only mount.
    print(
        f"AUD-313 seed target verified for {project}: "
        "owner record is one exact read-only mount",
        flush=True,
    )
    return project
