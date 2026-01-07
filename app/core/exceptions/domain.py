from typing import Any


class DomainException(Exception):
    """Base class for all domain-level exceptions."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class EntityNotFound(DomainException):
    """Raised when a specific entity is not found."""

    def __init__(self, entity_name: str, identifier: Any):
        super().__init__(
            f"{entity_name} with identifier {identifier} not found.",
            details={"entity": entity_name, "identifier": identifier},
        )


class EntityAlreadyExists(DomainException):
    """Raised when attempting to create an entity that already exists."""

    def __init__(self, entity_name: str, identifier: Any):
        super().__init__(
            f"{entity_name} with identifier {identifier} already exists.",
            details={"entity": entity_name, "identifier": identifier},
        )


class PermissionDenied(DomainException):
    """Raised when a user does not have permission to perform an action."""

    def __init__(
        self, message: str = "Permission denied", details: dict[str, Any] | None = None
    ):
        super().__init__(message, details)


class BusinessRuleViolation(DomainException):
    """Raised when a business rule is violated."""

    pass
