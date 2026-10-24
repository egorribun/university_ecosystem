"""Fail-closed TDD stub for a read-only React compiler artifact probe.

This file deliberately does not fetch packages or emit artifact evidence.
The companion stdlib tests must first demonstrate assertion RED in hosted CI.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, BinaryIO


class ProbeError(ValueError):
    """Invalid or unavailable public artifact evidence."""


def select_candidates(
    packuments: Mapping[str, Any], cutoff: datetime
) -> list[tuple[str, str]] | None:
    """Pending bounded, maturity-aware candidate selection."""
    return None


def artifact_request(
    package: str,
    version: str,
    metadata: Mapping[str, Any],
    *,
    locked_integrity: str | None = None,
) -> dict[str, Any] | None:
    """Pending exact-origin and integrity validation."""
    return None


def inspect_artifact(
    raw: bytes,
    package: str,
    version: str,
    integrity: str,
    *,
    max_unpacked: int = 64 * 1024 * 1024,
    max_members: int = 512,
) -> dict[str, Any] | None:
    """Pending non-executing, in-memory artifact inspection."""
    return None


def read_bounded(response: BinaryIO, limit: int) -> bytes | None:
    """Pending bounded response reader."""
    return None


def fetch_bounded(
    url: str, limit: int, *, opener: Callable[..., Any] | None = None
) -> bytes | None:
    """Pending approved-origin-only transport."""
    return None


if __name__ == "__main__":
    raise SystemExit("Artifact probe unavailable: implementation pending assertion RED")
