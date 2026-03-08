from typing import Annotated

from fastapi import Depends, Request

from app.api.deps.auth import get_current_user
from app.core.localization import resolve_locale
from app.models.models import User


def get_locale(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> str:
    """
    Resolve locale from request headers or user preference.
    """
    header_locale = resolve_locale(request=request)
    user_locale = getattr(current_user, "preferred_locale", None)

    if user_locale:
        return str(user_locale)

    return str(header_locale)


__all__ = ["get_locale", "resolve_locale"]
