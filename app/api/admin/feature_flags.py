from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_admin_user
from app.api.validation import raise_not_found, raise_validation_error
from app.core.feature_flags import feature_flags
from app.core.localization import resolve_locale
from app.models import models
from app.schemas import schemas

router = APIRouter(prefix="/feature-flags", tags=["admin-feature-flags"])


@router.get("", response_model=list[schemas.FeatureFlagOut])
async def list_feature_flags(_: models.User = Depends(get_current_admin_user)):
    """List all registered feature flags."""
    return [flag.to_dict() for flag in feature_flags.list_flags()]


@router.patch("/{name}", response_model=schemas.FeatureFlagOut)
async def update_feature_flag(
    name: str,
    data: schemas.FeatureFlagUpdateIn,
    request: Request,
    user: models.User = Depends(get_current_admin_user),
):
    """Update a feature flag's status or percentage."""
    locale = resolve_locale(request=request, user=user)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise_validation_error(locale, "errors.invalid_input")

    success = await feature_flags.update(name, **update_data)
    if not success:
        # Note: Feature flags might not have translation keys for "not found"
        # specifically for flags, so we might need a generic one.
        # Current raise_not_found takes (resource, key, locale).
        # We'll use a generic fallback if specific key isn't available.
        raise_not_found("Feature flag", name, locale)

    # Return updated flag
    all_flags = feature_flags.list_flags()
    updated_flag = next((f for f in all_flags if f.name == name), None)
    if not updated_flag:
        raise_not_found("Feature flag", name, locale)

    return updated_flag.to_dict()
