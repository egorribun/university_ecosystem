"""Fail-closed target checks shared by the demo seed entry points."""

from __future__ import annotations

import os
import re
from pathlib import Path

from sqlalchemy.engine import make_url

ADMIN_SMOKE_WORKFLOW = "Admin Smoke Monitoring (Linux Periodic)"
ADMIN_SMOKE_TARGET = "admin-smoke"
ADMIN_SMOKE_PROJECT = "ci-admin-smoke"


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


def require_owned_live_stand_target() -> str:
    """Require a verified live stand or the bounded admin-smoke test target."""
    explicit_target = os.environ.get("UE_SEED_TARGET")
    if explicit_target is not None:
        if explicit_target != ADMIN_SMOKE_TARGET:
            raise RuntimeError("unsupported explicit seed target")
        return _require_admin_smoke_target()

    project = os.environ.get("LIVE_STAND_SEED_PROJECT", "")
    if (
        not project
        or os.environ.get("LIVE_STAND_OWNER_VERIFIED") != "1"
        or os.environ.get("COMPOSE_PROJECT_NAME") != project
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project) is None
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

    if target.get_backend_name() != "postgresql" or target.host != "postgres":
        raise RuntimeError(
            "seed database must be the postgres service in the owned live stand project"
        )

    return project
