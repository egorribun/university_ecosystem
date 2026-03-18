from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
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


def _loc_to_pointer(loc: tuple[int | str, ...]) -> str:
    """Convert a Pydantic v2 error location tuple to an RFC 6901 JSON Pointer.

    Example: ("body", "user", "email") → "/body/user/email"
    Tilde and slash characters in segment names are escaped per RFC 6901:
      '~' → '~0', '/' → '~1'
    """
    if not loc:
        return ""
    segments = [str(part).replace("~", "~0").replace("/", "~1") for part in loc]
    return "/" + "/".join(segments)


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


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle FastAPI HTTPExceptions following RFC 7807.
    """
    assert isinstance(exc, HTTPException)
    locale = resolve_locale(request=request)

    status_titles = {
        status.HTTP_400_BAD_REQUEST: "titles.bad_request",
        status.HTTP_401_UNAUTHORIZED: "titles.unauthorized",
        status.HTTP_403_FORBIDDEN: "titles.forbidden",
        status.HTTP_404_NOT_FOUND: "titles.not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "titles.method_not_allowed",
        status.HTTP_409_CONFLICT: "titles.conflict",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "titles.validation_error",
        status.HTTP_429_TOO_MANY_REQUESTS: "titles.rate_limit_exceeded",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "titles.internal_server_error",
    }
    title_key = status_titles.get(exc.status_code, "titles.http_error")
    title = translate(title_key, locale=locale)

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
