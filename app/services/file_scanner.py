"""File scanning helpers for uploaded payloads."""

from __future__ import annotations

import asyncio
import io
import logging
import time
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Any, cast

from fastapi import UploadFile, status

from app.api.validation import raise_http_error, raise_validation_error
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

# Circuit breaker for ClamAV scanner with conservative settings
_clamav_circuit_breaker = CircuitBreaker(
    "clamav",
    config=CircuitBreakerConfig(
        failure_threshold=3,  # Lower threshold, scanner should be reliable
        recovery_timeout_seconds=60.0,  # Longer recovery time for service restart
        success_threshold=1,  # Single success to close
    ),
)


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


def _create_clamd_client() -> Any:
    """Return a configured clamd client instance."""

    try:  # Import lazily so environments without clamd stay functional.
        import clamd
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
    except Exception as exc:  # pragma: no cover - network failure path  # RZ-22-01-JUSTIFIED: convert-to-domain — wraps clamd errors (reviewed TD-27-04)
        raise FileScannerUnavailableError("unable to connect to clamd") from exc


def _scan_with_clamd_stream(stream: IO[bytes]) -> str | None:
    """Return the detected signature or ``None`` if the payload is clean."""

    try:
        client = _create_clamd_client()
        response: Any = client.instream(stream)
    except FileScannerUnavailableError:
        raise
    except Exception as exc:  # pragma: no cover - network failure path  # RZ-22-01-JUSTIFIED: convert-to-domain — wraps clamd errors (reviewed TD-27-04)
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
    except Exception as exc:  # pragma: no cover - network failure path  # RZ-22-01-JUSTIFIED: convert-to-domain — wraps clamd errors (reviewed TD-27-04)
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
    except (TypeError, ValueError):  # pragma: no cover - invalid config  # RZ-28-01
        return 0
    if configured <= 0:
        return 0
    return int(configured * 1024 * 1024)


def _scanner_duration_limit_seconds() -> float:
    try:
        configured = float(
            getattr(settings, "event_file_scanner_max_duration_sec", 0) or 0
        )
    except (TypeError, ValueError):  # pragma: no cover - invalid config  # RZ-28-01
        return 0.0
    if configured <= 0:
        return 0.0
    return configured


class _UploadStream:
    """File-like adapter that enforces scanner size limits."""

    __slots__ = ("_chunk_size", "_limit", "_wrapped", "bytes_scanned")

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

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._wrapped.seek(offset, whence)

    def tell(self) -> int:
        return self._wrapped.tell()

    def close(self) -> None:
        self._wrapped.close()


async def scan_for_malware(
    payload: bytes | UploadFile,
    *,
    locale: str | None = None,
    size_bytes: int | None = None,
    quarantine_payload: bytes | None = None,
    quarantine_handler: Callable[[bytes, str | None], Awaitable[None]] | None = None,
) -> None:
    """Scan ``payload`` for malware and raise an HTTP error when threats are found."""

    if isinstance(payload, (bytes | bytearray | memoryview)):
        data = bytes(payload)
        if not data:
            return
        stream_upload: UploadFile | None = None
        quarantine_payload = quarantine_payload or data
    elif isinstance(payload, UploadFile):
        stream_upload = payload
        data = b""
        if size_bytes == 0:
            return
    else:  # pragma: no cover
        return  # type: ignore[unreachable]

    if not getattr(settings, "event_file_scanner_enabled", False):
        return

    backend = (
        (getattr(settings, "event_file_scanner_backend", "clamd") or "clamd")
        .strip()
        .lower()
    )
    size_limit = _scanner_size_limit_bytes()
    if size_limit and size_bytes and size_bytes > size_limit:
        raise_http_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "errors.files.too_large",
            locale or "en",
        )

    # Check circuit breaker first for fail-fast behavior
    allow_on_unavailable = getattr(
        settings, "event_file_scanner_allow_on_unavailable", False
    )
    # RZ-13 (audit 2026-03-05): Forbid the allow_on_unavailable escape hatch in
    # production. If EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE=true leaks from staging
    # into production, a brief ClamAV blip would silently accept all file uploads
    # without scanning. Fail hard at startup rather than silently at request time.
    if (
        allow_on_unavailable
        and getattr(settings, "environment", "production") == "production"
    ):
        raise RuntimeError(
            "EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE must not be True in production. "
            "When set, a ClamAV outage silently accepts file uploads without malware "
            "scanning. Unset this flag before deploying to production."
        )
    try:
        async with _clamav_circuit_breaker:
            if backend == "clamd":
                if stream_upload is not None:
                    result = await _scan_upload_with_clamd(
                        stream_upload, size_limit=size_limit
                    )
                else:
                    result = await _scan_bytes_with_clamd(data)
            else:
                raise FileScannerUnavailableError(
                    f"unsupported scanner backend: {backend}"
                )
    except CircuitBreakerOpenError as exc:
        logger.warning(
            "File scanner circuit breaker open, skipping scan",
            extra={
                "event": "file_scan",
                "scan_backend": backend,
                "scan_status": "circuit_breaker_open",
                "remaining_seconds": exc.remaining_seconds,
            },
        )
        if not allow_on_unavailable:
            raise_http_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "errors.files.scanner_unavailable",
                locale or "en",
            )
        # Allow upload without scanning when configured
        return
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
        raise_http_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "errors.files.too_large",
            locale or "en",
        )
    except FileScannerUnavailableError as exc:
        logger.error("File scanner unavailable: %s", exc)
        raise_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "errors.files.scanner_unavailable",
            locale or "en",
        )

    _log_scan_result(result, backend)

    if result.signature:
        if quarantine_handler and quarantine_payload:
            try:
                await quarantine_handler(quarantine_payload, result.signature)
            except (
                OSError,
                ConnectionError,
            ) as exc:  # RZ-22-01: narrowed — storage errors during quarantine
                logger.warning(
                    "Failed to quarantine infected payload: %s", exc, exc_info=True
                )
        raise_validation_error(
            "errors.files.infected",
            locale or "en",
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
    """Scan an uploaded file for malware via streaming (async) ClamAV chunking.

    This avoids loading the entire file into memory concurrently to prevent
    OOM killed scenarios and spike loads on heavy 50MB PDF uploads.
    """
    import struct

    start_time = time.perf_counter()
    timeout = float(getattr(settings, "event_file_scanner_timeout", 30.0) or 30.0)
    socket_path = getattr(settings, "event_file_scanner_socket", "") or ""
    host = getattr(settings, "event_file_scanner_host", "127.0.0.1")
    port = int(getattr(settings, "event_file_scanner_port", 3310) or 3310)

    try:
        async with asyncio.timeout(timeout):
            if socket_path:
                # Use Any cast to avoid platform-specific mypy failures on Windows (open_unix_connection is Unix-only)
                reader, writer = await cast(Any, asyncio).open_unix_connection(
                    socket_path
                )
            else:
                reader, writer = await asyncio.open_connection(host, port)

            try:
                # zINSTREAM expects size+chunk length, terminated with 0 length chunk.
                writer.write(b"zINSTREAM\0")
                await writer.drain()

                bytes_scanned = 0
                await upload.seek(0)

                while True:
                    chunk = await upload.read(128 * 1024)
                    if not chunk:
                        break

                    bytes_scanned += len(chunk)
                    if size_limit and bytes_scanned > size_limit:
                        writer.close()
                        raise FileScannerPayloadTooLarge(
                            bytes_scanned, limit_bytes=size_limit
                        )

                    writer.write(struct.pack("!I", len(chunk)))
                    writer.write(chunk)
                    await writer.drain()

                writer.write(struct.pack("!I", 0))
                await writer.drain()

                response = await reader.read(4096)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (
                    OSError,
                    ConnectionError,
                ):  # RZ-22-01: narrowed — network close errors
                    logger.debug("Failed to close clamd writer cleanly", exc_info=True)
    except FileScannerPayloadTooLarge:
        raise
    except TimeoutError as exc:
        raise FileScannerUnavailableError("clamd scan timed out") from exc
    except Exception as exc:  # RZ-22-01-JUSTIFIED: convert-to-domain — wraps clamd stream errors (reviewed TD-27-04)
        raise FileScannerUnavailableError("clamd scan failed") from exc

    if not response:
        raise FileScannerUnavailableError("empty response from clamd")

    # Response is typically 'stream: OK\0' or 'stream: EICAR-Test-Signature FOUND\0'
    resp_text = response.decode("utf-8", errors="replace").strip("\0 ")

    if resp_text.endswith("OK"):
        signature = None
    elif resp_text.endswith("FOUND"):
        # Extract signature name
        parts = resp_text.split(" ")
        signature = parts[1] if len(parts) >= 2 else "unknown"
    else:
        raise FileScannerUnavailableError(f"clamd error: {resp_text}")

    duration = time.perf_counter() - start_time
    return _ScanResult(
        signature=signature, duration=duration, bytes_scanned=bytes_scanned
    )


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
