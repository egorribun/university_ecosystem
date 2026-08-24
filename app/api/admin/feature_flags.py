from fastapi import APIRouter, Depends, HTTPException, status

import app.models as models
from app.api.deps import get_current_admin_user
from app.core.feature_flags import (
    FEATURE_FLAG_CONFIG_PATH,
    FeatureFlagSnapshot,
)
from app.core.feature_flags import (
    list_feature_flags as list_feature_flag_snapshots,
)
from app.schemas import schemas

router = APIRouter(prefix="/feature-flags", tags=["admin-feature-flags"])


@router.get("", response_model=list[schemas.FeatureFlagOut])
async def list_feature_flags(
    _: models.User = Depends(get_current_admin_user),
) -> list[FeatureFlagSnapshot]:
    """List registered flags and their effective read-only evaluations."""
    return list_feature_flag_snapshots()


@router.patch("/{name}", include_in_schema=False)
async def reject_feature_flag_update(
    name: str,
    _: models.User = Depends(get_current_admin_user),
) -> None:
    """Reject legacy writes; flagd configuration is owned by GitOps."""
    del name
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=(
            "Feature flags are read-only in this API. Update "
            f"{FEATURE_FLAG_CONFIG_PATH} through the reviewed GitOps workflow."
        ),
        headers={"Allow": "GET"},
    )
