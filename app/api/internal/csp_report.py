"""CSP Violation Reporting endpoint.

Receives Content-Security-Policy violation reports from browsers
and logs them for security monitoring.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/csp-report", tags=["security"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def receive_csp_report(request: Request) -> Response:
    """
    Receive CSP violation reports from browsers.

    Browsers send POST requests with Content-Type: application/csp-report
    when a CSP policy is violated.
    """
    try:
        body = await request.body()
        if not body:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        # Parse the violation report
        import json

        try:
            report_data: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError:
            logger.warning(
                "Invalid CSP report format",
                extra={"event": "csp_report", "status": "invalid_json"},
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        # Extract the actual report (browsers wrap it in "csp-report" key)
        csp_report = report_data.get("csp-report", report_data)

        # Log the violation in structured format
        logger.warning(
            "CSP violation detected",
            extra={
                "event": "csp_violation",
                "document_uri": csp_report.get("document-uri"),
                "violated_directive": csp_report.get("violated-directive"),
                "effective_directive": csp_report.get("effective-directive"),
                "blocked_uri": csp_report.get("blocked-uri"),
                "source_file": csp_report.get("source-file"),
                "line_number": csp_report.get("line-number"),
                "column_number": csp_report.get("column-number"),
                "status_code": csp_report.get("status-code"),
                "script_sample": csp_report.get("script-sample", "")[:100],  # Truncate
                "user_agent": request.headers.get("user-agent", "")[:200],
            },
        )

    except Exception:
        # Silently ignore errors - don't disrupt user experience
        logger.debug("Failed to process CSP report", exc_info=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
