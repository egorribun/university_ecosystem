from typing import Any

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
    def __init__(self, message: str = "Resource not found", payload: dict[str, Any] | None = None):
        super().__init__(message, status_code=404, code="resource_not_found", payload=payload)

class PermissionDeniedException(AppException):
    def __init__(self, message: str = "Permission denied", payload: dict[str, Any] | None = None):
        super().__init__(message, status_code=403, code="permission_denied", payload=payload)

class InvalidOperationException(AppException):
    def __init__(self, message: str = "Invalid operation", payload: dict[str, Any] | None = None):
        super().__init__(message, status_code=400, code="invalid_operation", payload=payload)
