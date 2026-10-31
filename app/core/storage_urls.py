"""Pure validation for the configured origin of private StaticFS identities."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, TypeAdapter

DEFAULT_STATIC_STORAGE_ORIGIN = "http://localhost:8000"
_INVALID_ORIGIN = "STORAGE_STATIC_ORIGIN must be an HTTP(S) origin without a path"
_AUTHORITY = re.compile(r"(?:\[[0-9A-Fa-f:.]+\]|[^:\[\]]+)(?::[0-9]+)?\Z")
_HTTP_ORIGIN = TypeAdapter(AnyHttpUrl)


def validate_static_storage_origin(value: str) -> str:
    """Validate without DNS or replacing the original configured identity."""
    if (
        not isinstance(value, str)
        or not value
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        or any(char in value for char in "\\?#@%")
    ):
        raise ValueError(_INVALID_ORIGIN)
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not value.startswith(f"{parsed.scheme}://")
            or not parsed.hostname
            or parsed.path
            or parsed.netloc.endswith(":")
            or port == 0
            or _AUTHORITY.fullmatch(parsed.netloc) is None
        ):
            raise ValueError(_INVALID_ORIGIN)
        # The parser validates host syntax; its normalized result is not stored.
        _HTTP_ORIGIN.validate_python(value)
    except ValueError:
        raise ValueError(_INVALID_ORIGIN) from None
    return value
