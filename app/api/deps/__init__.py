from __future__ import annotations

from app.api.deps.auth import (
    _enforce_fresh_mfa,
    get_current_admin_user,
    get_current_admin_user_from_dishka,
    get_current_user,
    get_current_user_auth_dto,
    get_current_user_dto,
    get_current_user_from_dishka,
    get_current_user_full,
    get_current_user_optional,
    get_current_user_optional_from_dishka,
    get_redis_session_service,
    require_fresh_mfa,
)
from app.api.deps.localization import get_locale, resolve_locale
from app.core.database import get_db, get_read_db

# BE-04: app/api/deps/services.py and app/core/container.py are gone. Between
# them they held the 39 legacy ``Depends(get_*_service)`` factories and the
# four private constructors behind them; every route now resolves its services
# from the Dishka container, and the two remaining non-route callers construct
# their service over the session they already own.

__all__ = [
    "_enforce_fresh_mfa",
    "get_current_admin_user",
    "get_current_admin_user_from_dishka",
    "get_current_user",
    "get_current_user_auth_dto",
    "get_current_user_dto",
    "get_current_user_from_dishka",
    "get_current_user_full",
    "get_current_user_optional",
    "get_current_user_optional_from_dishka",
    "get_db",
    "get_locale",
    "get_read_db",
    "get_redis_session_service",
    "require_fresh_mfa",
    "resolve_locale",
]
