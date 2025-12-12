from fastapi import APIRouter

from app.api.notifications import admin_router as notifications_admin_router
from app.core.versioning import API_V1_PREFIX

router = APIRouter(prefix=API_V1_PREFIX, include_in_schema=False)

router.include_router(notifications_admin_router)

INTERNAL_ROUTE_PREFIXES = (f"{API_V1_PREFIX}{notifications_admin_router.prefix}",)
