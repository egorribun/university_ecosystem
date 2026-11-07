"""Stable identities for already verified disposable seed projects, not auth."""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, UUID, uuid5


def owned_seed_tenant_id(project: str) -> UUID:
    """Keep launcher configuration and both seed transactions on one tenant."""
    if (
        project != "ci-admin-smoke"
        and re.fullmatch(r"ue-live-[0-9a-f]{16}", project) is None
    ):
        raise ValueError("unrecognized owned seed project")
    return uuid5(NAMESPACE_URL, f"urn:university-ecosystem:owned-seed:{project}")
