from fastapi import APIRouter

from app.api.auth.login import router as login_router
from app.api.auth.mfa import router as mfa_router
from app.api.chat import router as chat_router
from app.api.events import router as events_router
from app.api.images import router as images_router
from app.api.internal.csp_report import router as csp_report_router
from app.api.news import router as news_router
from app.api.notifications import router as notifications_router
from app.api.schedule import router as schedule_api_router
from app.api.search import router as search_router
from app.api.sessions import router as sessions_router
from app.api.spotify import router as spotify_router
from app.api.stats import router as stats_router
from app.api.stories import router as stories_router
from app.api.users import router as users_router
from app.core.versioning import API_V1_PREFIX
from app.routers.notifications import router as push_router
from app.routers.schedule import router as schedule_router

router = APIRouter(prefix=API_V1_PREFIX)

router.include_router(
    login_router, prefix="/auth", responses={401: {"description": "Unauthorized"}}
)
router.include_router(
    mfa_router, prefix="/auth", responses={401: {"description": "Unauthorized"}}
)
router.include_router(spotify_router)
router.include_router(sessions_router)
router.include_router(notifications_router)
router.include_router(push_router)
router.include_router(schedule_router)
router.include_router(users_router)
router.include_router(events_router)
router.include_router(news_router)
router.include_router(stories_router)
router.include_router(schedule_api_router)
router.include_router(stats_router)
router.include_router(chat_router)
router.include_router(images_router)
router.include_router(csp_report_router)
router.include_router(search_router)
