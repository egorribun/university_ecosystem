import logging

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
    get_story_service,
)
from app.api.utils import save_upload
from app.api.validation import ensure_exists, require_admin
from app.core.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
)
from app.deps.cache import etag_matches, format_etag, get_cache
from app.models import models
from app.schemas import schemas
from app.services.story_service import StoryService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/stories", tags=["stories"])

_STORIES_LIST_CACHE_KEY = "stories:list"
_CACHE_LOCALES: tuple[str, ...] = tuple(sorted({DEFAULT_LOCALE, *SUPPORTED_LOCALES}))


def _normalized_cache_locale(locale: str | None) -> str:
    candidate = (locale or "").strip().lower()
    if candidate in SUPPORTED_LOCALES:
        return candidate
    return DEFAULT_LOCALE


def _stories_list_cache_key(locale: str | None) -> str:
    normalized = _normalized_cache_locale(locale)
    return f"stories:list:{normalized}"


def _stories_cache_keys() -> list[str]:
    keys: list[str] = [_STORIES_LIST_CACHE_KEY]
    keys.extend(_stories_list_cache_key(locale) for locale in _CACHE_LOCALES)
    return keys


def _set_language_headers(response: Response, locale: str) -> None:
    from app.main import _ensure_vary_header as ensure_vary_header

    response.headers["Content-Language"] = locale
    ensure_vary_header(response, "Accept-Language")


@router.get("", response_model=list[schemas.StoryOut])
async def list_stories(
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    service: StoryService = Depends(get_story_service),
):
    locale = resolve_locale(request=request)
    normalized_locale = _normalized_cache_locale(locale)
    cache = get_cache()
    cache_key = _stories_list_cache_key(locale)
    legacy_key = (
        _STORIES_LIST_CACHE_KEY if normalized_locale == DEFAULT_LOCALE else None
    )

    if cache.enabled:
        cached = await cache.get(cache_key)
        if not cached and legacy_key:
            cached = await cache.get(legacy_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                not_modified = Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
                _set_language_headers(not_modified, normalized_locale)
                return not_modified
            response.headers["ETag"] = etag_header
            _set_language_headers(response, normalized_locale)
            return cached.payload

    # Service returns list[StoryOut] directly
    serialized = await service.list_active_stories(locale)
    # jsonable_encoder needed for caching?
    encoded = jsonable_encoder([item.model_dump() for item in serialized])

    if cache.enabled:
        entry = await cache.set(cache_key, encoded)
        response.headers["ETag"] = format_etag(entry.etag)
    _set_language_headers(response, normalized_locale)
    return encoded


@router.post("", response_model=schemas.StoryOut)
async def create_story(
    data: schemas.StoryCreate,
    request: Request,
    service: StoryService = Depends(get_story_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    record = await service.create_story(data, created_by=user.id)
    cache = get_cache()
    await cache.invalidate(*_stories_cache_keys())
    return service.serialize_story(record, locale)


@router.patch("/{story_id}", response_model=schemas.StoryOut)
async def update_story(
    story_id: int,
    request: Request,
    data: schemas.StoryUpdate | None = Body(default=None),
    service: StoryService = Depends(get_story_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    try:
        updated = await service.update_story(story_id, data or schemas.StoryUpdate())
    except ValueError:
        ensure_exists(None, "stories", locale)

    cache = get_cache()
    await cache.invalidate(*_stories_cache_keys())
    return service.serialize_story(updated, locale)


@router.delete("/{story_id}", response_model=dict)
async def delete_story(
    story_id: int,
    request: Request,
    service: StoryService = Depends(get_story_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    deleted = await service.delete_story(story_id)
    if not deleted:
        ensure_exists(None, "stories", locale)

    cache = get_cache()
    await cache.invalidate(*_stories_cache_keys())
    return {"ok": True}


@router.post("/upload_cover")
async def upload_story_cover(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    url = await save_upload(file, "story_covers", "stories", locale=locale)
    return {"url": url}


__all__ = ["router"]
