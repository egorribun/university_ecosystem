"""High-performance JSON utilities using orjson.

orjson is a fast, correct JSON library for Python that provides:
- 10-15x faster serialization than the standard library
- Native support for datetime, UUID, numpy, and dataclass
- Consistent output format across platforms

This module provides centralized utilities for orjson usage throughout
the application to ensure consistent serialization behavior.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

try:
    import orjson

    # Common serialization options optimized for API responses
    ORJSON_OPTIONS = (
        orjson.OPT_SERIALIZE_NUMPY  # Support numpy arrays
        | orjson.OPT_UTC_Z  # Use Z suffix for UTC (e.g., "2024-01-01T00:00:00Z")
        | orjson.OPT_NAIVE_UTC  # Treat naive datetime as UTC
    )
except ImportError:
    import json

    # Mock orjson module and options
    class OrJsonMock:
        OPT_SERIALIZE_NUMPY = 0
        OPT_UTC_Z = 0
        OPT_NAIVE_UTC = 0

        @staticmethod
        def dumps(obj, default=None, option=None):
            # Ignores option
            return json.dumps(obj, default=default).encode("utf-8")

        @staticmethod
        def loads(obj):
            return json.loads(obj)

    orjson = OrJsonMock()
    ORJSON_OPTIONS = 0


def orjson_dumps(obj: Any, *, option: int | None = None) -> bytes:
    """Serialize object to JSON bytes using orjson.

    Args:
        obj: Object to serialize
        option: Additional orjson options (combined with defaults via |)

    Returns:
        JSON bytes
    """
    opts = ORJSON_OPTIONS
    if option is not None:
        opts |= option
    return orjson.dumps(obj, option=opts)


def orjson_dumps_str(obj: Any, *, option: int | None = None) -> str:
    """Serialize object to JSON string using orjson.

    Args:
        obj: Object to serialize
        option: Additional orjson options (combined with defaults via |)

    Returns:
        JSON string
    """
    return orjson_dumps(obj, option=option).decode("utf-8")


def orjson_loads(data: bytes | str) -> Any:
    """Deserialize JSON bytes or string using orjson.

    Args:
        data: JSON bytes or string

    Returns:
        Deserialized Python object
    """
    return orjson.loads(data)


def default_serializer(obj: Any) -> Any:
    """Default serializer for types not natively supported by orjson.

    Args:
        obj: Object to serialize

    Returns:
        Serializable representation

    Raises:
        TypeError: If object cannot be serialized
    """
    if isinstance(obj, datetime | date | time):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


__all__ = [
    "ORJSON_OPTIONS",
    "default_serializer",
    "orjson_dumps",
    "orjson_dumps_str",
    "orjson_loads",
]
