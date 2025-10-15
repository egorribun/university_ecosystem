import logging
from typing import Any, List

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.api.utils import save_upload
from app.core.database import get_db
from app.deps.cache import etag_matches, format_etag, get_cache
from app.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
    translate,
)
from app.models import models
from app.schemas import schemas
from app.services.notifications import notify_about_news
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/news", tags=["news"])

_LEGACY_NEWS_LIST_CACHE_KEY = "news:list"
_LEGACY_NEWS_ITEM_PREFIX = "news:item"
_CACHE_LOCALES: tuple[str, ...] = tuple(sorted({DEFAULT_LOCALE, *SUPPORTED_LOCALES}))


def _normalized_cache_locale(locale: str | None) -> str:
    candidate = (locale or "").strip().lower()
    if candidate in SUPPORTED_LOCALES:
        return candidate
    return DEFAULT_LOCALE


def _news_list_cache_key(locale: str | None) -> str:
    normalized = _normalized_cache_locale(locale)
    return f"news:list:{normalized}"


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
    keys.extend(_news_list_cache_key(locale) for locale in _CACHE_LOCALES)
    if news_id is not None:
        keys.append(_legacy_news_item_cache_key(news_id))
        keys.extend(_news_item_cache_key(news_id, locale) for locale in _CACHE_LOCALES)
    return keys


@router.post("", response_model=schemas.NewsOut)
async def create_news(
    data: schemas.NewsCreate,
    request: Request,
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
    cache = get_cache()
    await cache.invalidate(*_news_cache_keys(record.id))
    serialized = _serialize_news(record, locale)
    try:
        await notify_about_news(db, record, locale=locale)
    except Exception:
        logger.exception(
            "Failed to dispatch news notification", extra={"news_id": record.id}
        )
    return schemas.NewsOut.model_validate(serialized)


@router.get("", response_model=List[schemas.NewsOut])
async def news_list(
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    cache = get_cache()
    cache_key = _news_list_cache_key(locale)
    legacy_key = _LEGACY_NEWS_LIST_CACHE_KEY if locale == DEFAULT_LOCALE else None

    if cache.enabled:
        cached = await cache.get(cache_key)
        if not cached and legacy_key:
            cached = await cache.get(legacy_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
            return cached.payload

    rows = await crud.get_news_list(db)
    payload = [_serialize_news(item, locale) for item in rows]
    encoded = jsonable_encoder(payload)

    if cache.enabled:
        entry = await cache.set(cache_key, encoded)
        response.headers["ETag"] = format_etag(entry.etag)
    return encoded


@router.get("/{id}", response_model=schemas.NewsOut)
async def get_news(
    id: int,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    cache = get_cache()
    cache_key = _news_item_cache_key(id, locale)
    legacy_key = _legacy_news_item_cache_key(id) if locale == DEFAULT_LOCALE else None
    if cache.enabled:
        cached = await cache.get(cache_key)
        if not cached and legacy_key:
            cached = await cache.get(legacy_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
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
    return encoded


@router.patch("/{id}", response_model=schemas.NewsOut)
async def update_news(
    id: int,
    data: schemas.NewsCreate,
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
    updates = data.model_dump(exclude_unset=True)
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
    cache = get_cache()
    await cache.invalidate(*_news_cache_keys(id))
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
    cache = get_cache()
    await cache.invalidate(*_news_cache_keys(id))
    return {"ok": True}


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
    url = await save_upload(file, "news_images", "news")
    return {"url": url}


__all__ = ["router"]
