"""File scanning helpers for uploaded payloads."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings
from app.localization import translate

logger = logging.getLogger(__name__)


class FileScannerUnavailableError(RuntimeError):
    """Raised when the configured malware scanner cannot be reached."""


def _create_clamd_client():
    """Return a configured clamd client instance."""

    try:  # Import lazily so environments without clamd stay functional.
        import clamd  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - depends on optional dependency
        raise FileScannerUnavailableError("python-clamd is not installed") from exc

    timeout = float(getattr(settings, "event_file_scanner_timeout", 30.0) or 30.0)
    socket_path = getattr(settings, "event_file_scanner_socket", "") or ""
    host = getattr(settings, "event_file_scanner_host", "127.0.0.1")
    port = int(getattr(settings, "event_file_scanner_port", 3310) or 3310)

    try:
        if socket_path:
            return clamd.ClamdUnixSocket(path=socket_path, timeout=timeout)
        return clamd.ClamdNetworkSocket(host=host, port=port, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network failure path
        raise FileScannerUnavailableError("unable to connect to clamd") from exc


def _scan_with_clamd(data: bytes) -> str | None:
    """Return the detected signature or ``None`` if the payload is clean."""

    try:
        client = _create_clamd_client()
        response: Any = client.instream(io.BytesIO(data))
    except FileScannerUnavailableError:
        raise
    except Exception as exc:  # pragma: no cover - network failure path
        raise FileScannerUnavailableError("clamd scan failed") from exc

    if not isinstance(response, dict) or "stream" not in response:
        raise FileScannerUnavailableError("unexpected clamd response format")

    result = response["stream"]
    if isinstance(result, tuple) and len(result) >= 1:
        status_value = (result[0] or "").upper()
        signature = result[1] if len(result) > 1 else None
    else:
        raise FileScannerUnavailableError("malformed clamd response")

    if status_value == "OK":
        return None
    if status_value == "FOUND":
        return str(signature or "unknown")
    if status_value == "ERROR":
        raise FileScannerUnavailableError(str(signature or "clamd error"))
    raise FileScannerUnavailableError(f"unsupported clamd status: {status_value}")


def _check_clamd_health() -> None:
    """Ensure the clamd service responds to control commands."""

    try:
        client = _create_clamd_client()
        pong = client.ping()
    except FileScannerUnavailableError:
        raise
    except Exception as exc:  # pragma: no cover - network failure path
        raise FileScannerUnavailableError("clamd health check failed") from exc

    if isinstance(pong, str) and pong.upper() == "PONG":
        return

    raise FileScannerUnavailableError("unexpected clamd health response")


async def scan_for_malware(data: bytes, *, locale: str | None = None) -> None:
    """Scan ``data`` for malware and raise an HTTP error when a threat is found."""

    if not data:
        return

    if not getattr(settings, "event_file_scanner_enabled", False):
        return

    backend = (
        (getattr(settings, "event_file_scanner_backend", "clamd") or "clamd")
        .strip()
        .lower()
    )

    try:
        if backend == "clamd":
            signature = await asyncio.to_thread(_scan_with_clamd, data)
        else:
            raise FileScannerUnavailableError(f"unsupported scanner backend: {backend}")
    except FileScannerUnavailableError as exc:
        logger.error("File scanner unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=translate("errors.files.scanner_unavailable", locale=locale),
        ) from exc

    if signature:
        logger.warning("File scanner detected malware: %s", signature)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=translate("errors.files.infected", locale=locale),
        )


async def check_file_scanner_health() -> None:
    """Verify that the configured scanner responds without uploading data."""

    if not getattr(settings, "event_file_scanner_enabled", False):
        return

    backend = (
        (getattr(settings, "event_file_scanner_backend", "clamd") or "clamd")
        .strip()
        .lower()
    )

    if backend == "clamd":
        await asyncio.to_thread(_check_clamd_health)
        return

    raise FileScannerUnavailableError(f"unsupported scanner backend: {backend}")
