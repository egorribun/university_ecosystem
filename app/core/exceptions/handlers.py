from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.localization import resolve_locale, translate


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle DomainExceptions following RFC 7807 (Problem Details for HTTP APIs).
    """
    locale = resolve_locale(request=request)

    status_code = status.HTTP_400_BAD_REQUEST
    title = "Business Logic Error"
    detail = str(exc)
    error_type = "about:blank"

    if isinstance(exc, EntityNotFound):
        status_code = status.HTTP_404_NOT_FOUND
        title = "Resource Not Found"
        detail = translate("errors.not_found", locale=locale, **exc.details)
        error_type = "https://api.university.edu/probs/not-found"
    elif isinstance(exc, EntityAlreadyExists):
        status_code = status.HTTP_409_CONFLICT
        title = "Resource Already Exists"
        detail = translate("errors.already_exists", locale=locale, **exc.details)
        error_type = "https://api.university.edu/probs/conflict"
    elif isinstance(exc, PermissionDenied):
        status_code = status.HTTP_403_FORBIDDEN
        title = "Permission Denied"
        detail = translate("errors.forbidden", locale=locale)
        error_type = "https://api.university.edu/probs/forbidden"
    elif isinstance(exc, BusinessRuleViolation):
        status_code = status.HTTP_400_BAD_REQUEST
        title = "Business Rule Violation"
        detail = exc.message
        error_type = "https://api.university.edu/probs/business-rule"

    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": error_type,
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": str(request.url),
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle FastAPI HTTPExceptions following RFC 7807.
    """
    titles = {
        status.HTTP_400_BAD_REQUEST: "Bad Request",
        status.HTTP_401_UNAUTHORIZED: "Unauthorized",
        status.HTTP_403_FORBIDDEN: "Forbidden",
        status.HTTP_404_NOT_FOUND: "Resource Not Found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "Method Not Allowed",
        status.HTTP_409_CONFLICT: "Conflict",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "Validation Error",
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
        },
        headers=exc.headers,
    )
