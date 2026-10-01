from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions.domain import BusinessRuleViolation as BusinessRuleViolation
from app.core.exceptions.domain import DomainException as DomainException
from app.core.exceptions.domain import PolicyViolation as PolicyViolation
from app.core.exceptions.handlers import (
    domain_exception_handler as domain_exception_handler,
)
from app.core.observability import get_trace_id


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


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppException):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "trace_id": get_trace_id()},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "payload": exc.payload,
            "trace_id": get_trace_id(),
        },
    )
