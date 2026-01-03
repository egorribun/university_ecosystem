from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.core.feature_flags import feature_flags
from app.core.localization import resolve_locale, translate
from app.models import models
from app.schemas import schemas

router = APIRouter(prefix="/feature-flags", tags=["admin-feature-flags"])


def require_admin(user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


@router.get("", response_model=list[schemas.FeatureFlagOut])
async def list_feature_flags(_: models.User = Depends(require_admin)):
    """List all registered feature flags."""
    return [flag.to_dict() for flag in feature_flags.list_flags()]


@router.patch("/{name}", response_model=schemas.FeatureFlagOut)
async def update_feature_flag(
    name: str,
    data: schemas.FeatureFlagUpdateIn,
    request: Request,
    user: models.User = Depends(require_admin),
):
    """Update a feature flag's status or percentage."""
    locale = resolve_locale(request=request, user=user)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.invalid_input", locale=locale),
        )

    success = await feature_flags.update(name, **update_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{name}' not found",
        )

    # Return updated flag
    all_flags = feature_flags.list_flags()
    updated_flag = next((f for f in all_flags if f.name == name), None)
    if not updated_flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{name}' not found after update",
        )

    return updated_flag.to_dict()
