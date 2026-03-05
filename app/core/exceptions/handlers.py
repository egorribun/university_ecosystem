from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.localization import resolve_locale, translate
from app.core.observability import get_trace_id

if TYPE_CHECKING:
    from starlette.types import Send


async def asgi_json_problem(
    send: Send,
    *,
    status_code: int,
    title_key: str,
    detail_key: str | None = None,
    detail_text: str | None = None,
    locale: str = "en",
    instance: str = "",
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> None:
    """Helper to transmit a localized RFC 7807 response over ASGI."""
    title = translate(title_key, locale=locale)
    detail = detail_text
    if not detail and detail_key:
        detail = translate(detail_key, locale=locale, **kwargs)

    problem = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail or title,
        "instance": instance,
        "trace_id": get_trace_id(),
    }
    body = json.dumps(problem, ensure_ascii=False).encode("utf-8")
    response_headers = [
        (b"content-type", b"application/problem+json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if headers:
        for k, v in headers.items():
            response_headers.append((k.encode("latin-1"), v.encode("latin-1")))

    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": response_headers,
        }
    )
    await send({"type": "http.response.body", "body": body})


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle DomainExceptions following RFC 7807 (Problem Details for HTTP APIs).
    """
    locale = resolve_locale(request=request)

    status_code = status.HTTP_400_BAD_REQUEST
    title_key = "titles.bad_request"
    detail = str(exc)
    error_type = "about:blank"

    if isinstance(exc, EntityNotFound):
        status_code = status.HTTP_404_NOT_FOUND
        title_key = "titles.not_found"
        detail = translate("errors.not_found", locale=locale, **exc.details)
        error_type = "https://api.university.edu/probs/not-found"
    elif isinstance(exc, EntityAlreadyExists):
        status_code = status.HTTP_409_CONFLICT
        title_key = "titles.conflict"
        detail = translate("errors.already_exists", locale=locale, **exc.details)
        error_type = "https://api.university.edu/probs/conflict"
    elif isinstance(exc, PermissionDenied):
        status_code = status.HTTP_403_FORBIDDEN
        title_key = "titles.forbidden"
        detail = translate("errors.forbidden", locale=locale)
        error_type = "https://api.university.edu/probs/forbidden"
    elif isinstance(exc, BusinessRuleViolation):
        status_code = status.HTTP_400_BAD_REQUEST
        title_key = "titles.bad_request"
        detail = exc.message
        error_type = "https://api.university.edu/probs/business-rule"

    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": error_type,
            "title": translate(title_key, locale=locale),
            "status": status_code,
            "detail": detail,
            "instance": str(request.url),
            "trace_id": get_trace_id(),
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle FastAPI HTTPExceptions following RFC 7807.
    """
    titles = {
        status.HTTP_400_BAD_REQUEST: "Bad Request",
        status.HTTP_401_UNAUTHORIZED: "Unauthorized",
        status.HTTP_403_FORBIDDEN: "Permission Denied",
        status.HTTP_404_NOT_FOUND: "Resource Not Found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "Method Not Allowed",
        status.HTTP_409_CONFLICT: "Conflict",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "Validation Error",
        status.HTTP_429_TOO_MANY_REQUESTS: "Rate Limit Exceeded",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal Server Error",
    }
    title = titles.get(exc.status_code, "HTTP Error")

    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": title,
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": str(request.url),
            "trace_id": get_trace_id(),
        },
        headers=exc.headers,
    )
