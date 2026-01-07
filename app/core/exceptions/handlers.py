from fastapi import Request, status
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
    Handle DomainExceptions and map them to appropriate HTTP status codes.
    Translates error messages using the request's locale.
    """
    locale = resolve_locale(request=request)

    if isinstance(exc, EntityNotFound):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": translate("errors.not_found", locale=locale, **exc.details)
            },
        )

    if isinstance(exc, EntityAlreadyExists):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": translate(
                    "errors.already_exists", locale=locale, **exc.details
                )
            },
        )

    if isinstance(exc, PermissionDenied):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": translate("errors.forbidden", locale=locale)},
        )

    if isinstance(exc, BusinessRuleViolation):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": exc.message
            },  # Logic might need specific translation keys in the future
        )

    # Fallback for generic DomainException
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message},
    )
