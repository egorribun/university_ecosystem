"""Inactive, pure contract for one historical Squawk diagnostic inventory.

A match is not scanner success, migration permission, greenfield admission or
deployment acceptance. This module has no file, process, database or CI adapter.
The tests-first scaffold deliberately rejects every candidate until its exact
historical positive control has produced a hosted assertion failure.
"""

from __future__ import annotations

from datetime import UTC, datetime


def match_inventory(policy_bytes: bytes, capture_bytes: bytes) -> str | None:
    """Return only a bounded diagnostic match; never authorize execution."""
    # The clock import is the future real UTC boundary, not a caller override.
    # Keeping the function importable makes the first failure semantic, not an
    # import/setup error. No inventory is accepted by this scaffold.
    _ = UTC, datetime, policy_bytes, capture_bytes
    return None
