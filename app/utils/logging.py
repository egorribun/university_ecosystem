"""Logging helpers for redacting sensitive data."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

REDACTED_VALUE = "***REDACTED***"


def redact_sensitive_mapping(
    data: Mapping[str, Any] | None, *, allowlist: Iterable[str] = ()
) -> dict[str, Any]:
    """Return a copy of mapping with non-allowlisted values redacted."""
    if not data:
        return {}

    allowed = {key.lower() for key in allowlist}
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in allowed:
            redacted[key] = value
        else:
            redacted[key] = REDACTED_VALUE
    return redacted
