"""
API Validation Helpers

Consolidated validation functions to reduce code duplication across API endpoints.
Each helper raises HTTPException with appropriate status codes and localized messages.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar, overload

from fastapi import HTTPException, status

from app.core.localization import translate
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.schemas.dtos import UserDTO

if TYPE_CHECKING:
    from app.models import User

T = TypeVar("T")


def raise_http_error(
    status_code: int,
    message_key: str,
    locale: str,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> NoReturn:
    """
    Raise an HTTPException with a localized message.

    Args:
        status_code: HTTP status code
        message_key: Translation key
        locale: Current request locale
        headers: Optional HTTP headers
        **kwargs: Additional arguments for translation interpolation
    """
    detail = translate(message_key, locale=locale, **kwargs)
    raise HTTPException(status_code=status_code, detail=detail, headers=headers)


def raise_not_found(
    resource_key: str,
    locale: str,
    *,
    resource_id: uuid.UUID | int | str | None = None,
    exact_key: str | None = None,
) -> NoReturn:
    """
    Raise 404 HTTPException with localized not_found message.

    Args:
        resource_key: Resource identifier (e.g. "news")
        locale: Current request locale
        resource_id: Optional ID for logging (unused in detail)
        exact_key: Optional override for the translation key
    """
    key = exact_key or f"errors.{resource_key}.not_found"
    raise_http_error(status.HTTP_404_NOT_FOUND, key, locale)


def raise_forbidden(locale: str, message_key: str = "errors.forbidden") -> NoReturn:
    """
    Raise 403 HTTPException with localized forbidden message.

    Args:
        locale: Current request locale
        message_key: Optional override for translation key
    """
    raise_http_error(status.HTTP_403_FORBIDDEN, message_key, locale)


def raise_unauthorized(
    locale: str,
    message_key: str = "errors.unauthorized",
    headers: dict[str, str] | None = None,
) -> NoReturn:
    """
    Raise 401 HTTPException with localized unauthorized message.

    Args:
        locale: Current request locale
        message_key: Optional override for translation key
        headers: Optional HTTP headers (e.g. WWW-Authenticate)
    """
    raise_http_error(status.HTTP_401_UNAUTHORIZED, message_key, locale, headers=headers)


def raise_validation_error(message_key: str, locale: str, **kwargs: Any) -> NoReturn:
    """
    Raise 400 HTTPException with localized validation error message.

    Args:
        message_key: Translation key
        locale: Current request locale
    """
    raise_http_error(status.HTTP_400_BAD_REQUEST, message_key, locale, **kwargs)


def raise_conflict(message_key: str, locale: str, **kwargs: Any) -> NoReturn:
    """
    Raise 409 HTTPException for conflict situations.

    Args:
        message_key: Translation key
        locale: Current request locale
        **kwargs: Additional arguments for translation
    """
    raise_http_error(status.HTTP_409_CONFLICT, message_key, locale, **kwargs)


def require_admin(user: User | UserDTO, locale: str) -> None:
    """
    Verify user has admin role, raise 403 if not.
    """
    # TD-W19-02 (audit 2026-03-24 Wave 19): use UserRole enum constants instead
    # of hardcoded string literals for role comparison across all validation helpers.
    if user.role != UserRole.ADMIN:
        raise_forbidden(locale)


def require_teacher_or_admin(user: User, locale: str) -> None:
    """
    Verify user has teacher or admin role, raise 403 if not.
    """
    if user.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise_forbidden(locale)


@overload
def require_owner_or_admin(
    user: User,
    locale: str,
    *,
    owner_id: uuid.UUID | int | str,
) -> None: ...  # pragma: no branch


@overload
def require_owner_or_admin(
    user: User,
    locale: str,
    *,
    owner_id: uuid.UUID | int | str,
    allow_teacher: bool,
) -> None: ...  # pragma: no branch


def require_owner_or_admin(
    user: User,
    locale: str,
    *,
    owner_id: uuid.UUID | int | str,
    allow_teacher: bool = False,
) -> None:
    """
    Verify user is owner of resource or has admin (and optionally teacher) role.
    """
    allowed_roles = (
        (UserRole.ADMIN,) if not allow_teacher else (UserRole.ADMIN, UserRole.TEACHER)
    )

    if user.role in allowed_roles:
        return

    if user.id != owner_id:
        raise_forbidden(locale)


def ensure_exists[T](resource: T | None, resource_key: str, locale: str) -> T:
    """
    Ensure resource exists, return it or raise 404.

    Args:
        resource: Resource from database (may be None)
        resource_key: Resource identifier
        locale: Current request locale

    Returns:
        The resource if it exists
    """
    if resource is None:
        raise_not_found(resource_key, locale)
    return resource


__all__ = [
    "ensure_exists",
    "raise_conflict",
    "raise_forbidden",
    "raise_http_error",
    "raise_not_found",
    "raise_validation_error",
    "require_admin",
    "require_owner_or_admin",
    "require_teacher_or_admin",
]
