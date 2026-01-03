from fastapi import APIRouter

from .audit import router as audit_router
from .feature_flags import router as feature_flags_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(feature_flags_router)
router.include_router(audit_router)
