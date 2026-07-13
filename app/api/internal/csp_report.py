"""CSP Violation Reporting endpoint.

Receives Content-Security-Policy violation reports from browsers
and logs them for security monitoring.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status
from fastapi.params import Depends

from app.core.logging import get_logger
from app.core.metrics import record_csp_report
from app.core.ratelimit import sensitive_route_limit

logger = get_logger(__name__)

router = APIRouter(prefix="/csp-report", tags=["security"])

MAX_CSP_REPORT_BYTES = 16 * 1024
MAX_LOG_VALUE_LENGTH = 200
MAX_SCRIPT_SAMPLE_LENGTH = 100


def _truncate(value: Any, limit: int = MAX_LOG_VALUE_LENGTH) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


async def _read_body_with_limit(request: Request, limit: int) -> bytes | None:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                return None
        except ValueError:
            logger.debug("Invalid content-length header for CSP report")
    body = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > limit:
            return None
    return bytes(body)


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(sensitive_route_limit(limit=30, window_sec=60))],
)
async def receive_csp_report(request: Request) -> Response:
    """
    Receive CSP violation reports from browsers.

    Browsers send POST requests with Content-Type: application/csp-report
    when a CSP policy is violated.
    """
    try:
        body = await _read_body_with_limit(request, MAX_CSP_REPORT_BYTES)
        if body is None:
            record_csp_report("too_large")
            logger.warning(
                "CSP report payload too large",
                extra={"event": "csp_report", "status": "payload_too_large"},
            )
            return Response(status_code=status.HTTP_413_CONTENT_TOO_LARGE)
        if not body:
            record_csp_report("empty")
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        # Parse the violation report
        import json

        try:
            report_data: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError:
            record_csp_report("invalid_json")
            logger.warning(
                "Invalid CSP report format",
                extra={"event": "csp_report", "status": "invalid_json"},
            )
            # TD-W5-07: Return 400 so the browser knows the report was malformed
            # (204 would silently succeed, hiding client-side formatting bugs).
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

        # Extract the actual report (browsers wrap it in "csp-report" key)
        csp_report = report_data.get("csp-report", report_data)

        # Log the violation in structured format
        record_csp_report("accepted")
        logger.warning(
            "CSP violation detected",
            extra={
                "event": "csp_violation",
                "document_uri": _truncate(csp_report.get("document-uri")),
                "violated_directive": _truncate(csp_report.get("violated-directive")),
                "effective_directive": _truncate(csp_report.get("effective-directive")),
                "blocked_uri": _truncate(csp_report.get("blocked-uri")),
                "source_file": _truncate(csp_report.get("source-file")),
                "line_number": csp_report.get("line-number"),
                "column_number": csp_report.get("column-number"),
                "status_code": csp_report.get("status-code"),
                "script_sample": _truncate(
                    csp_report.get("script-sample", ""),
                    limit=MAX_SCRIPT_SAMPLE_LENGTH,
                ),
                "user_agent": _truncate(
                    request.headers.get("user-agent", ""),
                    limit=MAX_LOG_VALUE_LENGTH,
                ),
            },
        )

    # LOW-W19: narrowed from bare `except Exception` to the concrete error types
    # that can realistically arise outside the inner json.loads try/except block:
    # UnicodeDecodeError from body decode, TypeError/AttributeError from unexpected
    # dict shapes, and OSError from the underlying stream.  Retains the intent of
    # never propagating errors to the browser while making the guard auditable.
    except UnicodeDecodeError, TypeError, AttributeError, OSError, KeyError:
        record_csp_report("error")
        # Silently ignore errors - don't disrupt user experience
        logger.debug("Failed to process CSP report", exc_info=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
