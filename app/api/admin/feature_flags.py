from typing import Any

from fastapi import APIRouter, Depends, Request

import app.models as models
from app.api.deps import get_current_admin_user
from app.api.validation import raise_not_found, raise_validation_error
from app.core.feature_flags import feature_flags
from app.core.localization import resolve_locale
from app.schemas import schemas

router = APIRouter(prefix="/feature-flags", tags=["admin-feature-flags"])


@router.get("", response_model=list[schemas.FeatureFlagOut])
async def list_feature_flags(
    _: models.User = Depends(get_current_admin_user),
) -> list[dict[str, Any]]:
    """List all registered feature flags."""
    return feature_flags.list_flags()


@router.patch("/{name}", response_model=schemas.FeatureFlagOut)
async def update_feature_flag(
    name: str,
    data: schemas.FeatureFlagUpdateIn,
    request: Request,
    user: models.User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Update a feature flag's status or percentage."""
    locale = resolve_locale(request=request, user=user)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise_validation_error("errors.invalid_input", locale)

    result = await feature_flags.update(name, **update_data)
    if not result:
        raise_not_found("feature_flag", locale, resource_id=name)

    return result
