import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Header,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder

from app.api.deps import (
    get_current_user,
    get_read_story_service,
    get_story_service,
)
from app.api.utils import save_upload
from app.api.validation import ensure_exists, require_admin
from app.core.config import settings
from app.core.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
)
from app.core.ratelimit import sensitive_route_limit
from app.deps.cache import etag_matches, format_etag, get_cache
from app.api.deps.etag import cached_endpoint
from app.models import models
from app.schemas import schemas
from app.services.file_scanner import scan_for_malware
from app.services.story_service import StoryService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/stories", tags=["stories"])

_STORIES_LIST_CACHE_KEY = "stories:list"
_CACHE_LOCALES: tuple[str, ...] = tuple(sorted({DEFAULT_LOCALE, *SUPPORTED_LOCALES}))


# Removed obsolete cache key helpers


class MockStoriesVersionResolver:
    async def get_version(self, cache: Any) -> str:
        return "v1"

mock_stories_version = MockStoriesVersionResolver()

@router.get("", response_model=list[schemas.StoryOut])
@cached_endpoint(
    # Mocking a trivial version resolver for the decorator since stories don't use cache_version logic here natively
    version_resolver=mock_stories_version,
    cache_prefix="ue:stories:list",
    cache_control="public, max-age=180",
)
async def list_stories(
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    service: StoryService = Depends(get_read_story_service),
) -> list[schemas.StoryOut] | Response | Any:
    locale = resolve_locale(request=request)

    # Service returns list[StoryOut] directly
    serialized = await service.list_active_stories(locale)
    return serialized


@router.post(
    "",
    response_model=schemas.StoryOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_stories))
    ],
)
async def create_story(
    data: schemas.StoryCreate,
    request: Request,
    service: StoryService = Depends(get_story_service),
    user: models.User = Depends(get_current_user),
) -> schemas.StoryOut:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    record = await service.create_story(data, created_by=user.id)
    # Note: Explicitly invalidating wildcard keys because the inline keys generator was removed
    cache = get_cache()
    await cache.invalidate("ue:stories:list:*", _STORIES_LIST_CACHE_KEY)
    return service.serialize_story(record, locale)


@router.patch(
    "/{story_id}",
    response_model=schemas.StoryOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_stories))
    ],
)
async def update_story(
    story_id: uuid.UUID,
    request: Request,
    data: schemas.StoryUpdate | None = Body(default=None),
    service: StoryService = Depends(get_story_service),
    user: models.User = Depends(get_current_user),
) -> schemas.StoryOut:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    try:
        updated = await service.update_story(story_id, data or schemas.StoryUpdate())
    except ValueError:
        ensure_exists(None, "stories", locale)

    cache = get_cache()
    await cache.invalidate("ue:stories:list:*", _STORIES_LIST_CACHE_KEY)
    return service.serialize_story(updated, locale)


@router.delete(
    "/{story_id}",
    response_model=dict,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_stories))
    ],
)
async def delete_story(
    story_id: uuid.UUID,
    request: Request,
    service: StoryService = Depends(get_story_service),
    user: models.User = Depends(get_current_user),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    deleted = await service.delete_story(story_id)
    if not deleted:
        ensure_exists(None, "stories", locale)

    cache = get_cache()
    await cache.invalidate("ue:stories:list:*", _STORIES_LIST_CACHE_KEY)
    return {"ok": True}


@router.post(
    "/upload_cover",
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_upload))
    ],
)
async def upload_story_cover(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
) -> dict[str, str]:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    await scan_for_malware(file, locale=locale, size_bytes=file.size)
    url = await save_upload(file, "story_covers", "stories", locale=locale)
    return {"url": url}


__all__ = ["router"]
