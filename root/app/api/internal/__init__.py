from fastapi import APIRouter

from app.api.dlq import router as dlq_router
from app.api.notifications import admin_router as notifications_admin_router
from app.core.versioning import API_V1_PREFIX

router = APIRouter(prefix=API_V1_PREFIX, include_in_schema=False)

router.include_router(notifications_admin_router)
router.include_router(dlq_router)

INTERNAL_ROUTE_PREFIXES = (
    f"{API_V1_PREFIX}{notifications_admin_router.prefix}",
    f"{API_V1_PREFIX}{dlq_router.prefix}",
)
