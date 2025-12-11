from __future__ import annotations

import re
from typing import Final

# Central API semantic version. Update intentionally following semver.
API_VERSION: Final[str] = "1.0.0"
# Default versioned prefix for HTTP routes.
API_V1_PREFIX: Final[str] = "/api/v1"

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[\w\.-]+)?(?:\+[\w\.-]+)?$")


def assert_semver(version: str) -> str:
    """Validate that the provided version string follows semantic versioning."""
    if not _SEMVER_RE.match(version):
        raise ValueError(
            "API version must follow semantic versioning (MAJOR.MINOR.PATCH, optional pre-release/build)."
        )
    return version


# Validate at import time so misconfigured versions fail fast during startup/tests.
assert_semver(API_VERSION)
