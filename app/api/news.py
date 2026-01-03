import logging
from datetime import UTC
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.api.utils import save_upload
from app.core.database import get_db
from app.deps.cache import etag_matches, format_etag, get_cache
from app.core.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
    translate,
)
from app.models import models
from app.schemas import schemas
from app.services import notification_queue
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/news", tags=["news"])

_NEWS_LIST_CACHE_PREFIX = "news:list"
_NEWS_LIST_VERSION_KEY = f"{_NEWS_LIST_CACHE_PREFIX}:version"
_LOCAL_NEWS_LIST_VERSION = 0

_NEWS_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=120"
_LEGACY_NEWS_LIST_CACHE_KEY = "news:list"
_LEGACY_NEWS_ITEM_PREFIX = "news:item"
_CACHE_LOCALES = frozenset(SUPPORTED_LOCALES)


def _normalized_cache_locale(locale: str | None) -> str:
    """Normalize locale string for cache key purposes."""
    if locale is None:
        return DEFAULT_LOCALE
    if locale in SUPPORTED_LOCALES:
        return locale
    return DEFAULT_LOCALE


async def _get_news_list_version() -> str:
    cache = get_cache()
    if not cache.enabled:
        return str(_LOCAL_NEWS_LIST_VERSION)
    from app.deps.cache import RedisCache

    if isinstance(cache, RedisCache):
        try:
            client = await cache._get_client()
            raw = await client.get(_NEWS_LIST_VERSION_KEY)
            return str(int(raw)) if raw is not None else "0"
        except (RedisError, OSError, TypeError, ValueError):
            return "0"
    return "0"


async def _increment_news_list_version() -> None:
    global _LOCAL_NEWS_LIST_VERSION
    cache = get_cache()
    if not cache.enabled:
        _LOCAL_NEWS_LIST_VERSION += 1
        return
    from app.deps.cache import RedisCache

    if isinstance(cache, RedisCache):
        try:
            client = await cache._get_client()
            await client.incr(_NEWS_LIST_VERSION_KEY)
        except (RedisError, OSError):
            logger.warning("Failed to increment news cache version")
        return
    _LOCAL_NEWS_LIST_VERSION += 1


def _news_list_cache_key(
    locale: str | None, limit: int, cursor: str | None, version: str
) -> str:
    normalized = _normalized_cache_locale(locale)
    return f"{_NEWS_LIST_CACHE_PREFIX}:{version}:{normalized}:limit={limit}:cursor={cursor or ''}"


def _news_item_cache_key(news_id: int, locale: str | None) -> str:
    normalized = _normalized_cache_locale(locale)
    return f"news:item:{news_id}:{normalized}"


def _legacy_news_item_cache_key(news_id: int) -> str:
    return f"{_LEGACY_NEWS_ITEM_PREFIX}:{news_id}"


def _non_empty_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value.strip():
        return value
    return None


def _set_language_headers(response: Response, locale: str) -> None:
    from app.main import _ensure_vary_header as ensure_vary_header

    response.headers["Content-Language"] = locale
    response.headers["Cache-Control"] = _NEWS_CACHE_CONTROL
    ensure_vary_header(response, "Accept-Language")


def _localized_text(locale: str, ru_value: Any, en_value: Any) -> str:
    normalized = _normalized_cache_locale(locale)
    candidates: tuple[Any, ...]
    if normalized == "en":
        candidates = (en_value, ru_value)
    else:
        candidates = (ru_value, en_value)
    for candidate in candidates:
        text = _non_empty_text(candidate)
        if text is not None:
            return text
    # Nothing useful, prefer original Russian field as it is required in DB
    return str(ru_value or en_value or "")


def _serialize_news(
    record: models.News | schemas.NewsOut, locale: str
) -> dict[str, Any]:
    model_out = (
        record
        if isinstance(record, schemas.NewsOut)
        else schemas.NewsOut.model_validate(record)
    )
    data = model_out.model_dump()
    data["title"] = _localized_text(locale, data.get("title"), data.get("title_en"))
    data["content"] = _localized_text(
        locale, data.get("content"), data.get("content_en")
    )
    return data


def _news_cache_keys(news_id: int | None = None) -> list[str]:
    keys: list[str] = [_LEGACY_NEWS_LIST_CACHE_KEY]
    keys.extend(f"{_NEWS_LIST_CACHE_PREFIX}:{locale}:*" for locale in _CACHE_LOCALES)
    if news_id is not None:
        keys.append(_legacy_news_item_cache_key(news_id))
        keys.extend(_news_item_cache_key(news_id, locale) for locale in _CACHE_LOCALES)
    return keys


@router.post("", response_model=schemas.NewsOut)
async def create_news(
    data: schemas.NewsCreate,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    record = await crud.create_news(db, data)
    await _increment_news_list_version()
    serialized = _serialize_news(record, locale)
    try:
        background.add_task(
            notification_queue.enqueue_news_notification,
            record.id,
            locale=locale,
        )
    except Exception:
        logger.exception(
            "Failed to enqueue news notification", extra={"news_id": record.id}
        )
    return schemas.NewsOut.model_validate(serialized)


@router.get(
    "",
    response_model=schemas.PaginatedNews,
    summary="List News",
    description="Get a paginated list of news articles.",
)
async def news_list(
    request: Request,
    response: Response,
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated list of news articles.

    - **limit**: Number of items to return (1-100, default 20)
    - **cursor**: Pagination cursor for next page

    Returns news ordered by creation date (newest first).
    """
    locale = resolve_locale(request=request)
    normalized_locale = _normalized_cache_locale(locale)

    cache = get_cache()
    cache_key: str | None = None
    if cache.enabled:
        version = await _get_news_list_version()
        cache_key = _news_list_cache_key(normalized_locale, limit, cursor, version)

    if cache.enabled:
        cached = await cache.get(cache_key)
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

    # Get news with pagination
    rows = await crud.get_news_list(db, limit=limit + 1, cursor=cursor)

    # Check if there are more items
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # Calculate next cursor
    next_cursor = None
    if has_more and rows:
        last_item = rows[-1]
        # Cursor format: timestamp:id
        created_at = last_item.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        ts = int(created_at.timestamp() * 1000)
        next_cursor = f"{ts}:{last_item.id}"

    # Serialize items
    items = [_serialize_news(item, locale) for item in rows]

    payload = {
        "items": items,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }
    encoded = jsonable_encoder(payload)

    if cache.enabled:
        entry = await cache.set(cache_key, encoded)
        response.headers["ETag"] = format_etag(entry.etag)
    _set_language_headers(response, normalized_locale)
    return encoded


@router.get(
    "/{id}",
    response_model=schemas.NewsOut,
    summary="Get News Item",
    description="Get a specific news article by ID.",
)
async def get_news(
    id: int,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific news article by ID.

    - **id**: News item ID

    Returns 404 if not found.
    """
    locale = resolve_locale(request=request)
    cache = get_cache()
    normalized_locale = _normalized_cache_locale(locale)
    cache_key = _news_item_cache_key(id, locale)
    legacy_key = _legacy_news_item_cache_key(id) if locale == DEFAULT_LOCALE else None
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
    q = await db.get(models.News, id)
    if not q:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    serialized = _serialize_news(q, locale)
    encoded = jsonable_encoder(serialized)
    if cache.enabled:
        entry = await cache.set(cache_key, encoded)
        response.headers["ETag"] = format_etag(entry.etag)
    _set_language_headers(response, normalized_locale)
    return encoded


@router.patch("/{id}", response_model=schemas.NewsOut)
async def update_news(
    id: int,
    request: Request,
    data: schemas.NewsUpdate | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    updates = data.model_dump(exclude_unset=True) if data else {}
    if "title_en" in updates:
        updates["title_en"] = crud.sanitize_optional_text(updates.get("title_en"))
    if "content_en" in updates:
        updates["content_en"] = crud.sanitize_optional_text(updates.get("content_en"))

    old_image_url = news.image_url
    for field, value in updates.items():
        setattr(news, field, value)
    await db.commit()
    await db.refresh(news)
    if old_image_url and news.image_url != old_image_url:
        await delete_static_file(old_image_url)
    await _increment_news_list_version()
    cache = get_cache()
    await cache.invalidate(
        _news_item_cache_key(id, locale), _legacy_news_item_cache_key(id)
    )
    serialized = _serialize_news(news, locale)
    return schemas.NewsOut.model_validate(serialized)


@router.delete("/{id}", response_model=dict)
async def delete_news(
    id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    image_url = news.image_url
    await db.delete(news)
    await db.commit()
    if image_url:
        await delete_static_file(image_url)
    await _increment_news_list_version()
    cache = get_cache()
    await cache.invalidate(
        _news_item_cache_key(id, locale), _legacy_news_item_cache_key(id)
    )
    return {"ok": True}


@router.post("/{id}/like")
async def like_news(
    id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    is_liked = await crud.toggle_news_like(db, id, user.id)
    return {"is_liked": is_liked}


@router.post("/{id}/comment", response_model=schemas.NewsCommentOut)
async def comment_on_news(
    id: int,
    request: Request,
    content: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    if not content.strip():
        raise HTTPException(
            status_code=400,
            detail=translate("errors.validation.required", locale=locale),
        )
    comment = await crud.create_news_comment(db, id, user.id, content)
    return {
        "id": comment.id,
        "content": comment.content,
        "user_id": comment.user_id,
        "user_name": user.full_name,
        "created_at": comment.created_at,
    }


@router.get("/{id}/interactions", response_model=schemas.NewsInteractionsOut)
async def get_news_interact(
    id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User | None = Depends(get_current_user),
):
    locale = resolve_locale(request=request)
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    data = await crud.get_news_interactions(db, id, user.id if user else None)
    return data


@router.post("/upload_image")
async def upload_news_image(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    url = await save_upload(file, "news_images", "news", locale=locale)
    return {"url": url}


__all__ = ["router"]
