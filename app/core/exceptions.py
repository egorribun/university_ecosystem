from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "error",
        payload: dict[str, Any] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.payload = payload
        super().__init__(message)


class ResourceNotFoundException(AppException):
    def __init__(
        self, message: str = "Resource not found", payload: dict[str, Any] | None = None
    ):
        super().__init__(
            message, status_code=404, code="resource_not_found", payload=payload
        )


class PermissionDeniedException(AppException):
    def __init__(
        self, message: str = "Permission denied", payload: dict[str, Any] | None = None
    ):
        super().__init__(
            message, status_code=403, code="permission_denied", payload=payload
        )


class InvalidOperationException(AppException):
    def __init__(
        self, message: str = "Invalid operation", payload: dict[str, Any] | None = None
    ):
        super().__init__(
            message, status_code=400, code="invalid_operation", payload=payload
        )


async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "payload": exc.payload,
        },
    )
