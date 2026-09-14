from fastapi import APIRouter

from app.api.dlq import router as dlq_router
from app.api.internal.chat import router as internal_chat_router
from app.api.internal.csp_report import router as csp_router
from app.api.internal.jwks import router as jwks_router
from app.core.versioning import API_V1_PREFIX

router = APIRouter(prefix=API_V1_PREFIX, include_in_schema=False)

router.include_router(dlq_router)
router.include_router(csp_router)
router.include_router(internal_chat_router)
router.include_router(jwks_router, prefix="")

# Keep the participant callback internal without treating the entire public
# ``/api/v1/chat`` API as an internal surface.  The callback is mounted by this
# router, but its path is intentionally listed explicitly because chat itself
# also has public, user-authenticated routes under the same path segment.
INTERNAL_ROUTE_PREFIXES = (
    f"{API_V1_PREFIX}{dlq_router.prefix}",
    f"{API_V1_PREFIX}{internal_chat_router.prefix}/check-participant",
)
