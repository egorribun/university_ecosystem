import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy import exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_user_optional,
    get_news_service,
    get_read_news_service,
)
from app.api.utils import save_upload
from app.api.validation import (
    raise_forbidden,
    raise_not_found,
    raise_validation_error,
    require_admin,
)
from app.core.cache_versioning import news_cache_version
from app.core.container import get_notification_service, get_vector_service
from app.core.database import get_read_db
from app.core.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
)
from app.deps.cache import etag_matches, format_etag, get_cache
from app.models import models
from app.schemas import schemas
from app.services.news_service import NewsService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/news", tags=["news"])

_NEWS_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=120"
_NEWS_LIST_CACHE_PREFIX = news_cache_version.prefix
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
    return await news_cache_version.get_version()


async def _increment_news_list_version() -> None:
    await news_cache_version.increment()


def _news_list_cache_key(
    locale: str | None, limit: int, cursor: str | None, version: str
) -> str:
    normalized = _normalized_cache_locale(locale)
    return news_cache_version.build_cache_key(
        locale=normalized,
        version=version,
        limit=limit,
        cursor=cursor,
    )


def _news_item_cache_key(news_id: uuid.UUID, locale: str | None) -> str:
    normalized = _normalized_cache_locale(locale)
    return f"news:item:{news_id}:{normalized}"


def _legacy_news_item_cache_key(news_id: uuid.UUID) -> str:
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


def _news_cache_keys(news_id: uuid.UUID | None = None) -> list[str]:
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
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
    notifications: NotificationService = Depends(get_notification_service),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    record = await service.create_news(data)
    await _increment_news_list_version()
    serialized = service.serialize_news(record, locale)
    await notifications.dispatch_news_created(record.id, locale, background)
    return serialized


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
    service: NewsService = Depends(get_read_news_service),
    user: models.User | None = Depends(get_current_user_optional),
):
    """
    Get paginated list of news articles.

    - **limit**: Items to return (1-100, default 20)
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
    results = await service.list_news(
        limit=limit,
        cursor=cursor,
        current_user_id=user.id if user else None,
        search=None,
        locale=normalized_locale,
    )

    if cache.enabled and cache_key:
        encoded = jsonable_encoder(results)
        entry = await cache.set(cache_key, encoded)
        etag_header = format_etag(entry.etag)
        response.headers["ETag"] = etag_header
        _set_language_headers(response, normalized_locale)
        return encoded

    return results


@router.get(
    "/{id}",
    response_model=schemas.NewsOut,
    summary="Get News Item",
    description="Get a specific news article by ID.",
)
async def get_news(
    id: uuid.UUID,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    user: models.User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_read_db),
    service: NewsService = Depends(get_read_news_service),
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
    # Subqueries for counts
    likes_sub = (
        select(func.count(models.NewsLike.id))
        .where(models.NewsLike.news_id == id)
        .scalar_subquery()
        .label("likes_count")
    )
    comments_sub = (
        select(func.count(models.NewsComment.id))
        .where(models.NewsComment.news_id == id)
        .scalar_subquery()
        .label("comments_count")
    )

    # Subquery for user like status
    current_user_id = user.id if user else None
    is_liked_sub = literal(False).label("is_liked")
    if current_user_id:
        is_liked_sub = (
            select(
                exists().where(
                    models.NewsLike.news_id == models.News.id,
                    models.NewsLike.user_id == current_user_id,
                )
            )
            .scalar_subquery()
            .label("is_liked")
        )

    stmt = select(
        models.News,
        likes_sub,
        comments_sub,
        is_liked_sub,
    ).where(models.News.id == id)

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise_not_found("news", locale)

    news_obj, l_count, c_count, liked = row
    # Map database row to model object with extra attributes
    news_obj.likes_count = l_count or 0
    news_obj.comments_count = c_count or 0
    news_obj.is_liked = bool(liked)

    serialized = service.serialize_news(news_obj, locale)
    encoded = jsonable_encoder(serialized)
    if cache.enabled:
        entry = await cache.set(cache_key, encoded)
        response.headers["ETag"] = format_etag(entry.etag)
    _set_language_headers(response, normalized_locale)
    return encoded


@router.patch("/{id}", response_model=schemas.NewsOut)
async def update_news(
    id: uuid.UUID,
    request: Request,
    data: schemas.NewsUpdate | None = Body(default=None),
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    try:
        updated = await service.update_news(id, data or schemas.NewsUpdate())
    except ValueError:
        raise_not_found("news", locale)

    await _increment_news_list_version()
    cache = get_cache()
    if cache.enabled:
        await cache.invalidate(
            _news_item_cache_key(id, locale), _legacy_news_item_cache_key(id)
        )
    serialized = service.serialize_news(updated, locale)
    return serialized


@router.delete("/{id}", response_model=dict)
async def delete_news(
    id: uuid.UUID,
    request: Request,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    deleted = await service.delete_news(id)
    if not deleted:
        raise_not_found("news", locale)

    await _increment_news_list_version()
    cache = get_cache()
    if cache.enabled:
        await cache.invalidate(
            _news_item_cache_key(id, locale), _legacy_news_item_cache_key(id)
        )
    return {"ok": True}


@router.post("/{id}/like")
async def like_news(
    id: uuid.UUID,
    request: Request,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    news = await service.get_news_item(id)
    if not news:
        raise_not_found("news", locale)
    is_liked = await service.toggle_like(id, user.id)
    return {"is_liked": is_liked}


@router.post("/{id}/comment", response_model=schemas.NewsCommentOut)
async def comment_on_news(
    id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    content: str = Body(..., embed=True),
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
    notifications: NotificationService = Depends(get_notification_service),
):
    locale = resolve_locale(request=request, user=user)
    news = await service.get_news_item(id)
    if not news:
        raise_not_found("news", locale)
    if not content.strip():
        raise_validation_error("errors.validation.required", locale)

    comment = await service.create_comment(id, user.id, content)

    # Notify admins about new comment
    await notifications.dispatch_comment_created(
        id, comment.id, user.id, locale, background
    )

    return {
        "id": comment.id,
        "content": comment.content,
        "user_id": comment.user_id,
        "user_name": user.full_name,
        "created_at": comment.created_at,
    }


@router.get("/{id}/interactions", response_model=schemas.NewsInteractionsOut)
async def get_news_interact(
    id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: NewsService = Depends(get_read_news_service),
    user: models.User | None = Depends(get_current_user_optional),
):
    locale = resolve_locale(request=request)
    news = await service.get_news_item(id)
    if not news:
        raise_not_found("news", locale)

    data = await service.get_interactions(
        id, user.id if user else None, limit=limit, offset=offset
    )
    return data


@router.patch("/comments/{comment_id}", response_model=schemas.NewsCommentOut)
async def update_comment(
    comment_id: uuid.UUID,
    request: Request,
    data: schemas.NewsCommentUpdate,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    try:
        comment = await service.update_comment(comment_id, user.id, data.content)
        return {
            "id": comment.id,
            "content": comment.content,
            "user_id": comment.user_id,
            "user_name": user.full_name,
            "created_at": comment.created_at,
        }
    except LookupError:
        raise_not_found("news", locale, exact_key="errors.not_found")
    except PermissionError:
        raise_forbidden(locale)


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: uuid.UUID,
    request: Request,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    try:
        await service.delete_comment(
            comment_id, user.id, is_admin=(user.role == "admin")
        )
        return {"ok": True}
    except LookupError:
        raise_not_found("news", locale, exact_key="errors.not_found")
    except PermissionError:
        raise_forbidden(locale)


@router.post("/upload_image")
async def upload_news_image(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    url = await save_upload(file, "news_images", "news", locale=locale)
    return {"url": url}


@router.get("/search/semantic", response_model=list[schemas.NewsOut])
async def semantic_search(
    request: Request,
    response: Response,
    query: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_read_db),
    vector_service: Any = Depends(get_vector_service),
    service: NewsService = Depends(get_read_news_service),
):
    """
    Semantic search for news articles using embeddings.
    """
    locale = resolve_locale(request=request)
    normalized_locale = _normalized_cache_locale(locale)

    # Note: We don't cache semantic search results easily due to query variety,
    # but we can use ETag based on the content version.
    version = await _get_news_list_version()
    etag = format_etag(f"semantic:{version}:{query}:{limit}:{min_score}")
    if etag_matches(etag, if_none_match):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    embedding = await vector_service.get_embedding(query)
    results = await vector_service.search_similar(
        models.News, embedding, limit=limit, min_score=min_score
    )

    items = [service.serialize_news(item, locale) for item in results]
    response.headers["ETag"] = etag
    _set_language_headers(response, normalized_locale)
    return items


__all__ = ["router"]
