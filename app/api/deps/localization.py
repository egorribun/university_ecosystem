from typing import Annotated

from fastapi import Depends, Request

# MED-W19: get_locale now depends on get_current_user_optional so public
# endpoints (no auth required) can still resolve a locale via Accept-Language.
from app.api.deps.auth import get_current_user_optional
from app.core.localization import resolve_locale
from app.models.models import User


def get_locale(
    request: Request,
    current_user: Annotated[User | None, Depends(get_current_user_optional)],
) -> str:
    """
    Resolve locale from request headers or user preference.
    Falls back to Accept-Language when the caller is unauthenticated.
    """
    header_locale = resolve_locale(request=request)
    user_locale = (
        getattr(current_user, "preferred_locale", None)
        if current_user is not None
        else None
    )  # MED-W19

    if user_locale:
        return str(user_locale)

    return str(header_locale)


__all__ = ["get_locale", "resolve_locale"]
