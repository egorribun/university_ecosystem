from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, time
from hashlib import sha256
from threading import Lock
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pywebpush import WebPushException, webpush
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import selectinload, sessionmaker

from app.core.config import settings
from app.core.database import async_session
from app.core.localization import resolve_locale, translate
from app.core.ratelimit import (
    RateLimitExceeded,
    RateLimitInfo,
    enforce_rate_limit,
    get_default_strategy,
)
from app.models.models import PushSubscription, User
from app.services import push_schema
from app.services.notification_templates import render_notification_template
from app.services.push_topics import normalize_topic, subscription_supports_topic

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
logger.setLevel(logging.NOTSET)

_sync_url = make_url(settings.database_url)
if _sync_url.drivername.endswith("+asyncpg"):
    _sync_url = _sync_url.set(drivername="postgresql+psycopg")
elif _sync_url.drivername.endswith("+aiosqlite"):
    _sync_url = _sync_url.set(drivername="sqlite")

_sync_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None
_sync_init_lock = Lock()
_async_init_lock = asyncio.Lock()


def _initialize_sync_resources() -> None:
    global _sync_engine, _Session
    if _Session is not None:
        return
    engine = create_engine(str(_sync_url), pool_pre_ping=True, future=True)
    push_schema.ensure_push_subscription_schema_sync(engine)
    _sync_engine = engine
    _Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _ensure_sync_sessionmaker() -> sessionmaker[Session]:
    if _Session is None:
        with _sync_init_lock:
            if _Session is None:
                _initialize_sync_resources()
    return cast("sessionmaker[Session]", _Session)


async def _ensure_async_sessionmaker() -> sessionmaker[Session]:
    if _Session is None:
        async with _async_init_lock:
            if _Session is None:
                await asyncio.to_thread(_ensure_sync_sessionmaker)
    return cast("sessionmaker[Session]", _Session)


def cleanup() -> None:
    """Dispose of cached synchronous engine resources."""

    global _sync_engine, _Session

    engine: Engine | None = None
    session_factory: sessionmaker[Session] | None = None

    with _sync_init_lock:
        if _Session is None and _sync_engine is None:
            return
        engine = _sync_engine
        session_factory = _Session
        _sync_engine = None
        _Session = None

    if session_factory is not None:
        try:
            # Use the class method instead of deprecated instance method
            from sqlalchemy.orm import Session

            # close_all_sessions is removed in SQLAlchemy 2.0
            Session.close_all_sessions()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to close webpush session factory")

    if engine is not None:
        try:
            engine.dispose()
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to dispose webpush engine")


_OPTION_KEYS: set[str] = {
    "actions",
    "badge",
    "body",
    "dir",
    "icon",
    "image",
    "lang",
    "renotify",
    "requireInteraction",
    "silent",
    "tag",
    "timestamp",
    "vibrate",
}
_META_KEYS: set[str] = {"ttl", "topic", "urgency"}

_DEFAULT_TTL_SECONDS = 60 * 60  # 1 hour
_TTL_BY_URGENCY: dict[str, int] = {
    "high": 5 * 60,
    "normal": 60 * 60,
    "low": 12 * 60 * 60,
    "very-low": 24 * 60 * 60,
}

_USER_RATE_LIMIT = 60
_TOPIC_RATE_LIMIT = 300
_RATE_LIMIT_WINDOW_SECONDS = 60


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _mask_endpoint(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    value = endpoint.strip()
    if not value:
        return None
    digest = sha256(value.encode("utf-8")).hexdigest()[:10]
    try:
        parsed = urlparse(value)
    except ValueError:
        parsed = None
    if parsed and parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/…#{digest}"
    return f"…#{digest}"


def _log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    extra = {key: value for key, value in fields.items() if value is not None}
    if "endpoint" in extra:
        extra["endpoint"] = _mask_endpoint(str(extra["endpoint"]))
    extra["event"] = event
    logger.log(level, "webpush.%s", event, extra=extra)
    root_logger = logging.getLogger()
    if root_logger is not logger:
        root_logger.log(level, "webpush.%s", event, extra={**extra})


def _current_local_time(user: Any | None = None) -> time:
    tz: Any = UTC
    if user is not None:
        preferences = getattr(user, "preferences", None)
        raw = getattr(preferences, "timezone", None) if preferences else None
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate:
                try:
                    tz = ZoneInfo(candidate)
                except (ZoneInfoNotFoundError, ValueError):
                    tz = UTC
    now = datetime.now(tz)
    current = now.timetz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    return current


def _is_user_in_quiet_hours(user: Any | None, *, now_time: time | None = None) -> bool:
    preferences = getattr(user, "preferences", None) if user else None
    if not preferences or not getattr(preferences, "dnd_enabled", False):
        return False
    start = getattr(preferences, "dnd_start", None)
    end = getattr(preferences, "dnd_end", None)
    if now_time is None:
        now_time = _current_local_time(user)
    if start is None or end is None:
        return True
    if start == end:
        return True
    if start < end:
        return bool(start <= now_time < end)
    return bool(now_time >= start or now_time < end)


def _sanitize_vibrate(raw: Any) -> list[int]:
    if not isinstance(raw, list | tuple):
        return []
    cleaned: list[int] = []
    for item in raw:
        if isinstance(item, int | float):
            cleaned.append(int(item))
    return cleaned


@dataclass(slots=True)
class WebPushResult:
    subscription_id: uuid.UUID
    endpoint: str
    user_id: uuid.UUID
    status: Literal["sent", "gone", "error"]
    status_code: int | None = None
    error: str | None = None


def _prepare_actions(raw_actions: Any) -> tuple[list[dict[str, str]], dict[str, str]]:
    actions: list[dict[str, str]] = []
    action_urls: dict[str, str] = {}
    if not isinstance(raw_actions, list):
        return actions, action_urls
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip()
        title = str(item.get("title") or "").strip()
        if not action or not title:
            continue
        prepared: dict[str, str] = {"action": action, "title": title}
        icon = item.get("icon")
        if isinstance(icon, str) and icon.strip():
            prepared["icon"] = icon.strip()
        actions.append(prepared)
        url = item.get("url")
        if isinstance(url, str) and url.strip():
            action_urls[action] = url.strip()
    return actions, action_urls


def _normalize_payload(
    raw: Mapping[str, Any] | None,
    *,
    locale: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(raw, Mapping):
        raw = {}
    payload_options: dict[str, Any]
    payload_data: dict[str, Any]
    if isinstance(raw.get("options"), Mapping):
        payload_options = {
            key: deepcopy(value)
            for key, value in raw["options"].items()
            if value is not None
        }
    else:
        payload_options = {}
    if isinstance(raw.get("data"), Mapping):
        payload_data = {key: deepcopy(value) for key, value in raw["data"].items()}
    else:
        payload_data = {}
    meta: dict[str, Any] = {}
    meta_source = raw.get("_meta") if isinstance(raw.get("_meta"), Mapping) else {}
    for key in _META_KEYS:
        value = None
        if isinstance(meta_source, Mapping):
            value = meta_source.get(key)
        if value is None and key in raw and raw.get(key) is not None:
            value = raw.get(key)
        if value is None:
            continue
        if key == "ttl":
            try:
                meta[key] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            meta[key] = value
    if not payload_options:
        actions, action_urls = _prepare_actions(raw.get("actions"))
        if actions:
            payload_options["actions"] = actions
            if action_urls:
                payload_data.setdefault("actionUrls", action_urls)
        for key in _OPTION_KEYS - {"actions", "vibrate", "body"}:
            if key not in raw:
                continue
            value = raw.get(key)
            if value is None:
                continue
            payload_options[key] = value
        vibrate = _sanitize_vibrate(raw.get("vibrate"))
        if vibrate:
            payload_options["vibrate"] = vibrate
        body_value = raw.get("body")
        payload_options.setdefault("body", str(body_value or ""))
    else:
        meta_from_options = {
            key: payload_options.pop(key)
            for key in list(payload_options)
            if key in _META_KEYS
        }
        for key, value in meta_from_options.items():
            if value is None or key in meta:
                continue
            if key == "ttl":
                try:
                    meta[key] = int(value)
                except (TypeError, ValueError):
                    continue
            else:
                meta[key] = value
        actions, action_urls = _prepare_actions(payload_options.get("actions"))
        if actions:
            payload_options["actions"] = actions
            if action_urls:
                payload_data.setdefault("actionUrls", action_urls)
        else:
            payload_options.pop("actions", None)
        if "vibrate" in payload_options:
            vibrate = _sanitize_vibrate(payload_options.get("vibrate"))
            if vibrate:
                payload_options["vibrate"] = vibrate
            else:
                payload_options.pop("vibrate", None)
        if "body" in payload_options:
            payload_options["body"] = str(payload_options["body"] or "")
    for flag in ("renotify", "requireInteraction", "silent"):
        if flag in payload_options:
            payload_options[flag] = bool(payload_options[flag])
    if "timestamp" in payload_options:
        try:
            payload_options["timestamp"] = int(payload_options["timestamp"])
        except (TypeError, ValueError):
            payload_options.pop("timestamp", None)
    if "body" not in payload_options:
        payload_options["body"] = ""
    cleaned_options: dict[str, Any] = {}
    for key, value in payload_options.items():
        if key not in _OPTION_KEYS:
            continue
        if key == "actions" and not value:
            continue
        cleaned_options[key] = value
    payload_options = cleaned_options
    for string_key in ("badge", "icon", "image", "tag", "dir", "lang"):
        if string_key in payload_options:
            payload_options[string_key] = str(payload_options[string_key])
    url = raw.get("url")
    if isinstance(url, str) and url.strip():
        payload_data.setdefault("url", url.strip())
    if "type" in raw and raw.get("type") is not None:
        payload_data.setdefault("type", str(raw.get("type")))
    topic = meta.get("topic")
    if topic and isinstance(topic, str):
        payload_data.setdefault("topic", topic)
    title_value = raw.get("title")
    title = (
        str(title_value)
        if title_value not in (None, "")
        else translate("notifications.default_title", locale=locale)
    )
    payload = {
        "title": title,
        "options": payload_options,
        "data": payload_data,
    }
    return payload, meta


def _resolve_ttl(meta: Mapping[str, Any]) -> int:
    raw_ttl = meta.get("ttl")
    ttl_value: int | None = None
    if isinstance(raw_ttl, int):
        ttl_value = raw_ttl
    elif raw_ttl is not None:
        try:
            ttl_value = int(raw_ttl)
        except (TypeError, ValueError):
            ttl_value = None
    if ttl_value is not None and ttl_value > 0:
        return ttl_value
    urgency = str(meta.get("urgency") or "").strip().lower()
    mapped_ttl = _TTL_BY_URGENCY.get(urgency)
    if mapped_ttl is not None and mapped_ttl > 0:
        return mapped_ttl
    return _DEFAULT_TTL_SECONDS


def _compose_payload(
    payload: Mapping[str, Any],
    meta: Mapping[str, Any] | None,
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    result = {
        "title": str(
            payload.get("title")
            or translate("notifications.default_title", locale=locale)
        ),
        "options": deepcopy(payload.get("options", {})),
        "data": deepcopy(payload.get("data", {})),
    }
    clean_meta = (
        {key: value for key, value in (meta or {}).items() if value is not None}
        if meta
        else {}
    )
    if clean_meta:
        result["_meta"] = clean_meta
    return result


def _apply_quiet_mode(payload: dict[str, Any]) -> None:
    options = payload.setdefault("options", {})
    options["silent"] = True
    options["renotify"] = False
    options["requireInteraction"] = False
    options["vibrate"] = []
    data_payload = payload.setdefault("data", {})
    data_payload["dnd_suppressed"] = True


def _prepare_delivery_payload(
    payload: Mapping[str, Any] | None,
    *,
    topic: str | None,
    user: Any | None,
) -> dict[str, Any]:
    resolved_locale = resolve_locale(user=user)
    normalized, meta = _normalize_payload(payload, locale=resolved_locale)
    normalized_topic = normalize_topic(topic) or normalize_topic(meta.get("topic"))
    if normalized_topic:
        meta["topic"] = normalized_topic
        normalized.setdefault("data", {})
        normalized["data"].setdefault("topic", normalized_topic)
    if user and _is_user_in_quiet_hours(user):
        _apply_quiet_mode(normalized)
    return _compose_payload(normalized, meta, locale=resolved_locale)


async def _check_rate_limit(
    identifier: str,
    *,
    namespace: str,
    limit: int,
) -> RateLimitInfo:
    if limit <= 0 or not settings.rate_limit_enabled:
        return RateLimitInfo(True, max(limit, 0), 0)
    try:
        return await enforce_rate_limit(
            identifier=identifier,
            limit=limit,
            window_seconds=_RATE_LIMIT_WINDOW_SECONDS,
            strategy=get_default_strategy(namespace),
        )
    except RateLimitExceeded as exc:
        return exc.info


def build_payload(
    notification_type: str,
    data: Mapping[str, Any] | None,
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    if isinstance(data, Mapping):
        raw_source = {key: deepcopy(value) for key, value in data.items()}
    else:
        raw_source = {}

    template_defaults = render_notification_template(
        notification_type, raw_source, locale=locale
    )
    if template_defaults:
        source: dict[str, Any] = {
            key: deepcopy(value) for key, value in template_defaults.items()
        }
        template_data = (
            template_defaults.get("data")
            if isinstance(template_defaults.get("data"), Mapping)
            else None
        )
        input_data = (
            raw_source.get("data")
            if isinstance(raw_source.get("data"), Mapping)
            else None
        )
        if template_data or input_data:
            merged_data: dict[str, Any] = {}
            if template_data:
                merged_data.update(
                    {key: deepcopy(value) for key, value in template_data.items()}
                )
            if input_data:
                for key, value in input_data.items():
                    merged_data[key] = deepcopy(value)
            source["data"] = merged_data
        for key, value in raw_source.items():
            if key == "data":
                continue
            if value is None:
                continue
            source[key] = value
    else:
        source = raw_source

    title = str(
        source.get("title") or translate("notifications.default_title", locale=locale)
    )
    payload_data: dict[str, Any] = {}
    if isinstance(source.get("data"), Mapping):
        payload_data.update(
            {key: deepcopy(value) for key, value in source["data"].items()}
        )
    url = source.get("url")
    if isinstance(url, str) and url.strip():
        payload_data.setdefault("url", url.strip())
    if notification_type is not None:
        payload_data.setdefault("type", str(notification_type))
    options: dict[str, Any] = {}
    for key in ("badge", "icon", "image", "tag", "dir", "lang"):
        value = source.get(key)
        if value is not None:
            options[key] = str(value)
    if locale and "lang" not in options:
        options["lang"] = locale
    actions, action_urls = _prepare_actions(source.get("actions"))
    if actions:
        options["actions"] = actions
    if action_urls:
        payload_data.setdefault("actionUrls", action_urls)
    vibrate = _sanitize_vibrate(source.get("vibrate"))
    if vibrate:
        options["vibrate"] = vibrate
    options["body"] = str(source.get("body") or "")
    if "renotify" in source:
        options["renotify"] = bool(source.get("renotify"))
    if "requireInteraction" in source:
        options["requireInteraction"] = bool(source.get("requireInteraction"))
    if "silent" in source:
        options["silent"] = bool(source.get("silent"))
        if "timestamp" in source and source.get("timestamp") is not None:
            with contextlib.suppress(TypeError, ValueError):
                options["timestamp"] = int(source.get("timestamp"))  # type: ignore[arg-type]
    meta: dict[str, Any] = {}
    for key in _META_KEYS:
        value = source.get(key)
        if value is None:
            continue
        if key == "ttl":
            try:
                meta[key] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            meta[key] = value
    payload = {"title": title, "options": options, "data": payload_data}
    if meta:
        payload["_meta"] = meta
    return payload


def send_web_push(sub: PushSubscription, data: dict[str, Any]) -> WebPushResult:
    user = getattr(sub, "user", None)
    locale = resolve_locale(user=user)
    normalized_payload, meta = _normalize_payload(data, locale=locale)
    ttl = _resolve_ttl(meta)
    headers = {"TTL": str(ttl)}
    urgency = meta.get("urgency")
    if urgency:
        headers["Urgency"] = str(urgency)
    topic = meta.get("topic")
    if topic:
        headers["Topic"] = str(topic)
    subscription_info = {
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    user_id = getattr(sub, "user_id", None)
    try:
        webpush(
            subscription_info=subscription_info,
            data=json_dumps(normalized_payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.WEBPUSH_SUBJECT},
            headers=headers,
            ttl=ttl,
        )
    except (
        WebPushException
    ) as exc:  # pragma: no cover - network errors hard to simulate
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        message = str(exc)
        gone = False
        if status_code in (404, 410):
            gone = True
        elif message:
            gone = "404" in message or "410" in message
        if gone:
            _log_event(
                "send",
                user_id=user_id,
                endpoint=sub.endpoint,
                status="gone",
                status_code=status_code,
            )
            return WebPushResult(
                subscription_id=sub.id,
                endpoint=str(sub.endpoint),
                user_id=uuid.UUID(str(user_id)) if user_id else None,  # type: ignore[arg-type]
                status="gone",
                status_code=status_code,
                error=message or None,
            )
        _log_event(
            "send",
            user_id=user_id,
            endpoint=sub.endpoint,
            status="error",
            status_code=status_code,
        )
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=str(sub.endpoint),
            user_id=uuid.UUID(str(user_id)) if user_id else None,  # type: ignore[arg-type]
            status="error",
            status_code=status_code,
            error=message or None,
        )
    except Exception as exc:  # pragma: no cover - unexpected failure
        _log_event(
            "send",
            level=logging.ERROR,
            user_id=user_id,
            endpoint=sub.endpoint,
            status="error",
        )
        logger.exception(
            "webpush.send",
            extra={"user_id": user_id, "endpoint": _mask_endpoint(str(sub.endpoint))},
        )
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=str(sub.endpoint),
            user_id=uuid.UUID(str(user_id)) if user_id else None,  # type: ignore[arg-type]
            status="error",
            error=str(exc),
        )

    _log_event("send", user_id=user_id, endpoint=sub.endpoint, status="sent")
    return WebPushResult(
        subscription_id=sub.id,
        endpoint=str(sub.endpoint),
        user_id=uuid.UUID(str(user_id)) if user_id else None,  # type: ignore[arg-type]
        status="sent",
    )


async def process_push_results(results: list[WebPushResult]) -> None:
    gone_ids = [r.subscription_id for r in results if r.status == "gone"]
    sent_ids = [r.subscription_id for r in results if r.status == "sent"]

    if not gone_ids and not sent_ids:
        return

    await _ensure_async_sessionmaker()
    async with async_session() as session:
        if gone_ids:
            await session.execute(
                delete(PushSubscription).where(PushSubscription.id.in_(gone_ids))
            )
        if sent_ids:
            await session.execute(
                update(PushSubscription)
                .where(PushSubscription.id.in_(sent_ids))
                .values(last_seen_at=datetime.now(UTC))
            )
        await session.commit()


async def send_to_user(
    user_id: uuid.UUID,
    payload: Mapping[str, Any] | None,
    topic: str | None = None,
) -> list[WebPushResult]:
    normalized_topic = normalize_topic(topic) if topic is not None else None
    if topic and normalized_topic is None:
        _log_event(
            "dispatch",
            level=logging.WARNING,
            user_id=user_id,
            topic=topic,
            status="invalid_topic",
        )
    _, payload_meta = _normalize_payload(payload)
    payload_topic = normalize_topic(payload_meta.get("topic"))
    effective_topic = normalized_topic or payload_topic
    rate_info = await _check_rate_limit(
        f"user:{user_id}", namespace="webpush:user", limit=_USER_RATE_LIMIT
    )
    if not rate_info.allowed:
        _log_event(
            "dispatch",
            level=logging.WARNING,
            user_id=user_id,
            topic=effective_topic or normalized_topic or topic,
            status="rate_limited",
            retry_after=rate_info.retry_after,
        )
        return []
    await _ensure_async_sessionmaker()
    async with async_session() as session:
        result = await session.execute(
            select(PushSubscription)
            .options(
                selectinload(PushSubscription.user).selectinload(
                    User.push_topic_preferences
                )
            )
            .where(PushSubscription.user_id == user_id)
        )
        subscriptions = result.scalars().all()
    if not subscriptions:
        _log_event(
            "dispatch",
            user_id=user_id,
            topic=effective_topic or normalized_topic or topic,
            status="no_subscriptions",
        )
        return []
    tasks = []
    for sub in subscriptions:
        if not subscription_supports_topic(sub, effective_topic):
            continue
        prepared = _prepare_delivery_payload(
            payload,
            topic=normalized_topic or payload_topic,
            user=getattr(sub, "user", None),
        )
        tasks.append(asyncio.to_thread(send_web_push, sub, prepared))
    if not tasks:
        _log_event(
            "dispatch",
            user_id=user_id,
            topic=effective_topic or normalized_topic or topic,
            status="no_matching_topics",
        )
        return []
    results = await asyncio.gather(*tasks)
    await process_push_results(list(results))

    _log_event(
        "dispatch",
        user_id=user_id,
        topic=effective_topic or normalized_topic or topic,
        status="sent",
        delivered=len(results),
    )
    return list(results)


async def broadcast_to_topic(
    topic: str,
    payload: Mapping[str, Any] | None,
) -> list[WebPushResult]:
    normalized_topic = normalize_topic(topic)
    if not normalized_topic:
        _log_event(
            "broadcast",
            level=logging.WARNING,
            topic=topic,
            status="invalid_topic",
        )
        return []
    rate_info = await _check_rate_limit(
        f"topic:{normalized_topic}",
        namespace="webpush:topic",
        limit=_TOPIC_RATE_LIMIT,
    )
    if not rate_info.allowed:
        _log_event(
            "broadcast",
            level=logging.WARNING,
            topic=normalized_topic,
            status="rate_limited",
            retry_after=rate_info.retry_after,
        )
        return []
    await _ensure_async_sessionmaker()
    async with async_session() as session:
        result = await session.execute(
            select(PushSubscription)
            .options(selectinload(PushSubscription.user))
            .where(PushSubscription.topics.contains([normalized_topic]))
        )
        subscriptions = result.scalars().all()
    if not subscriptions:
        _log_event(
            "broadcast",
            topic=normalized_topic,
            status="no_subscribers",
        )
        return []
    tasks = []
    for sub in subscriptions:
        prepared = _prepare_delivery_payload(
            payload,
            topic=normalized_topic,
            user=getattr(sub, "user", None),
        )
        tasks.append(asyncio.to_thread(send_web_push, sub, prepared))
    results = await asyncio.gather(*tasks)
    await process_push_results(list(results))

    _log_event(
        "broadcast",
        topic=normalized_topic,
        status="sent",
        delivered=len(results),
    )
    return list(results)
