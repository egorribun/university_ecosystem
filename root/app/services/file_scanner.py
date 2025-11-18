"""File scanning helpers for uploaded payloads."""

from __future__ import annotations

import asyncio
import io
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, Any

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.localization import translate

logger = logging.getLogger(__name__)


class FileScannerUnavailableError(RuntimeError):
    """Raised when the configured malware scanner cannot be reached."""


class FileScannerPayloadTooLarge(RuntimeError):
    """Raised when a payload exceeds the configured scanner size limit."""

    def __init__(self, size_bytes: int, *, limit_bytes: int) -> None:
        super().__init__(
            f"payload exceeds scanner limit ({size_bytes} > {limit_bytes} bytes)"
        )
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes


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


def _scan_with_clamd_stream(stream: IO[bytes]) -> str | None:
    """Return the detected signature or ``None`` if the payload is clean."""

    try:
        client = _create_clamd_client()
        response: Any = client.instream(stream)
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


@dataclass(slots=True)
class _ScanResult:
    signature: str | None
    duration: float
    bytes_scanned: int


def _scanner_size_limit_bytes() -> int:
    try:
        configured = float(getattr(settings, "event_file_scanner_max_size_mb", 0) or 0)
    except (TypeError, ValueError):  # pragma: no cover - invalid config
        return 0
    if configured <= 0:
        return 0
    return int(configured * 1024 * 1024)


def _scanner_duration_limit_seconds() -> float:
    try:
        configured = float(
            getattr(settings, "event_file_scanner_max_duration_sec", 0) or 0
        )
    except (TypeError, ValueError):  # pragma: no cover - invalid config
        return 0.0
    if configured <= 0:
        return 0.0
    return configured


class _UploadStream:
    """File-like adapter that enforces scanner size limits."""

    __slots__ = ("_wrapped", "_limit", "_chunk_size", "bytes_scanned")

    def __init__(
        self,
        wrapped: IO[bytes],
        *,
        limit: int,
        chunk_size: int = 128 * 1024,
    ) -> None:
        self._wrapped = wrapped
        self._limit = max(0, int(limit))
        self._chunk_size = max(1, int(chunk_size))
        self.bytes_scanned = 0

    def read(self, size: int | None = None) -> bytes:
        requested = size if isinstance(size, int) and size > 0 else self._chunk_size
        data = self._wrapped.read(requested)
        if not data:
            return data
        self.bytes_scanned += len(data)
        if self._limit and self.bytes_scanned > self._limit:
            raise FileScannerPayloadTooLarge(
                self.bytes_scanned, limit_bytes=self._limit
            )
        return data


async def scan_for_malware(
    payload: bytes | UploadFile,
    *,
    locale: str | None = None,
    size_bytes: int | None = None,
) -> None:
    """Scan ``payload`` for malware and raise an HTTP error when threats are found."""

    if isinstance(payload, (bytes | bytearray | memoryview)):
        data = bytes(payload)
        if not data:
            return
        stream_upload: UploadFile | None = None
    elif isinstance(payload, UploadFile):
        stream_upload = payload
        data = b""
        if size_bytes == 0:
            return
    else:  # pragma: no cover - defensive guard for unexpected inputs
        return

    if not getattr(settings, "event_file_scanner_enabled", False):
        return

    backend = (
        (getattr(settings, "event_file_scanner_backend", "clamd") or "clamd")
        .strip()
        .lower()
    )
    size_limit = _scanner_size_limit_bytes()
    if size_limit and size_bytes and size_bytes > size_limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=translate("errors.files.too_large", locale=locale),
        )

    try:
        if backend == "clamd":
            if stream_upload is not None:
                result = await _scan_upload_with_clamd(
                    stream_upload, size_limit=size_limit
                )
            else:
                result = await _scan_bytes_with_clamd(data)
        else:
            raise FileScannerUnavailableError(f"unsupported scanner backend: {backend}")
    except FileScannerPayloadTooLarge as exc:
        logger.warning(
            "File scan aborted: payload exceeded scanner limit",
            extra={
                "event": "file_scan",
                "scan_backend": backend,
                "scan_status": "payload_too_large",
                "scan_bytes": exc.size_bytes,
                "scan_limit": exc.limit_bytes,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=translate("errors.files.too_large", locale=locale),
        ) from exc
    except FileScannerUnavailableError as exc:
        logger.error("File scanner unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=translate("errors.files.scanner_unavailable", locale=locale),
        ) from exc

    _log_scan_result(result, backend)

    if result.signature:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=translate("errors.files.infected", locale=locale),
        )


def _log_scan_result(result: _ScanResult, backend: str) -> None:
    status_label = "malware_detected" if result.signature else "clean"
    duration_limit = _scanner_duration_limit_seconds()
    log_level = logging.INFO
    message = "File scan completed"
    if duration_limit and result.duration > duration_limit:
        log_level = logging.WARNING
        message = "File scan exceeded duration threshold"
    logger.log(
        log_level,
        message,
        extra={
            "event": "file_scan",
            "scan_backend": backend,
            "scan_status": status_label,
            "scan_bytes": result.bytes_scanned,
            "scan_duration_sec": round(result.duration, 6),
            "scan_signature": result.signature,
            "scan_duration_limit_sec": duration_limit,
        },
    )


async def _scan_bytes_with_clamd(data: bytes) -> _ScanResult:
    def _runner() -> tuple[str | None, int]:
        signature = _scan_with_clamd_stream(io.BytesIO(data))
        return signature, len(data)

    return await _run_scan(_runner)


async def _scan_upload_with_clamd(
    upload: UploadFile, *, size_limit: int
) -> _ScanResult:
    await upload.seek(0)

    def _runner() -> tuple[str | None, int]:
        stream = _UploadStream(upload.file, limit=size_limit)
        signature = _scan_with_clamd_stream(stream)
        return signature, stream.bytes_scanned

    return await _run_scan(_runner)


async def _run_scan(
    runner: Callable[[], tuple[str | None, int]],
) -> _ScanResult:
    start = time.perf_counter()
    signature, bytes_scanned = await asyncio.to_thread(runner)
    duration = time.perf_counter() - start
    return _ScanResult(
        signature=signature, duration=duration, bytes_scanned=bytes_scanned
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
