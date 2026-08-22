from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, time
from hashlib import sha256
from threading import Lock
from typing import (  # TD-23-04 (audit 2026-03-25 Wave 23)
    TYPE_CHECKING,
    Any,
    Literal,
    cast,
)
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pywebpush import WebPushException, webpush
from sqlalchemy import create_engine, delete, update
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import async_session
from app.core.localization import resolve_locale, translate
from app.core.logging import get_logger
from app.core.ratelimit import (
    RateLimitExceeded,
    RateLimitInfo,
    enforce_rate_limit,
    get_default_strategy,
)
from app.core.ssrf import validate_public_https_url, validate_url_not_internal
from app.models import PushSubscription, User
from app.services.notification_templates import render_notification_template
from app.services.push_topics import normalize_topic

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)

# HIGH-W19: defer URL computation until first use so that importing this module
# does not immediately read settings or touch the database driver.
_sync_url_cache: URL | None = None


def _get_sync_url() -> URL:
    """Return the synchronous SQLAlchemy URL, computed lazily on first call."""
    global _sync_url_cache
    if _sync_url_cache is None:
        url = make_url(settings.database_url)
        if url.drivername.endswith("+asyncpg"):
            url = url.set(drivername="postgresql+psycopg")
        elif url.drivername.endswith("+aiosqlite"):
            url = url.set(drivername="sqlite")
        _sync_url_cache = url
    return _sync_url_cache


_sync_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None
_sync_init_lock = Lock()
_async_init_lock = asyncio.Lock()

# TD-002 / PERF-001: Cap concurrent outgoing WebPush HTTP connections to prevent
# self-DoS when broadcasting to large subscriber lists (e.g. 500+ recipients).
# Without a semaphore, asyncio.gather fires all connections simultaneously,
# exhausting the connection pool and triggering APNS/GCM rate-limit bans.
# 50 concurrent slots provide high throughput (~50 msg/s) without flooding.
_PUSH_DELIVERY_SEMAPHORE = asyncio.Semaphore(50)


def _initialize_sync_resources() -> None:
    global _sync_engine, _Session
    if _Session is not None:
        return
    # HIGH-W19: _get_sync_url() resolves the URL lazily so that no engine is
    # created at module import time (avoids side-effects during test collection).
    engine = create_engine(str(_get_sync_url()), pool_pre_ping=True, future=True)
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
    with _sync_init_lock:
        if _Session is None and _sync_engine is None:
            return
        engine = _sync_engine
        _sync_engine = None
        _Session = None

    if engine is not None:
        try:
            engine.dispose()
        except (OSError, ConnectionError):
            # RZ-20-04: Narrowed — engine dispose during shutdown.
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

_RATE_LIMIT_WINDOW_SECONDS = 60

# RED-07 (audit 2026-03-14): Cap concurrent push threads to prevent thread-pool
# exhaustion under high notification load.  Python's default ThreadPoolExecutor
# has min(32, os.cpu_count()+4) workers; saturating it with slow push vendors
# blocks all asyncio.to_thread calls across the application.
_PUSH_CONCURRENT_LIMIT = 30
_push_semaphore: asyncio.Semaphore | None = None


def _get_push_semaphore() -> asyncio.Semaphore:
    """Return the shared push semaphore, creating it lazily inside the event loop."""
    global _push_semaphore
    if _push_semaphore is None:
        _push_semaphore = asyncio.Semaphore(_PUSH_CONCURRENT_LIMIT)
    return _push_semaphore


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
    if root_logger is not logger:  # type: ignore[comparison-overlap]
        root_logger.log(level, "webpush.%s", event, extra={**extra})


def _current_local_time(user: User | None = None) -> time:
    tz: Any = UTC
    if user is not None:
        preferences = getattr(user, "preferences", None)
        raw = getattr(preferences, "timezone", None) if preferences else None
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate:
                try:
                    tz = ZoneInfo(candidate)
                except (ZoneInfoNotFoundError, ValueError):  # RZ-28-01
                    tz = UTC
    now = datetime.now(tz)
    return now.timetz().replace(tzinfo=None)


def _is_user_in_quiet_hours(user: User | None, *, now_time: time | None = None) -> bool:
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
    user_id: uuid.UUID | None
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
    raw_meta = raw.get("_meta")
    meta_source = raw_meta if isinstance(raw_meta, Mapping) else {}
    for key in _META_KEYS:
        value = meta_source.get(key)
        if value is None and key in raw and raw.get(key) is not None:
            value = raw.get(key)
        if value is None:
            continue
        if key == "ttl":
            try:
                meta[key] = int(value)
            except (TypeError, ValueError):  # RZ-28-01
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
                except (TypeError, ValueError):  # RZ-28-01
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
        except (TypeError, ValueError):  # RZ-28-01
            payload_options.pop("timestamp", None)
    if "body" not in payload_options:
        payload_options["body"] = ""
    cleaned_options: dict[str, Any] = {}
    for key, value in payload_options.items():
        if key not in _OPTION_KEYS:
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
        except (TypeError, ValueError):  # RZ-28-01
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
    user: User | None,
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
        try:
            options["timestamp"] = int(source["timestamp"])
        except (TypeError, ValueError):
            # Invalid provider metadata must not prevent the notification from
            # being delivered; omit only the malformed optional timestamp.
            pass
    meta: dict[str, Any] = {}
    for key in _META_KEYS:
        value = source.get(key)
        if value is None:
            continue
        if key == "ttl":
            try:
                meta[key] = int(value)
            except (TypeError, ValueError):  # RZ-28-01
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
    endpoint = str(sub.endpoint).strip()
    subscription_info = {
        "endpoint": endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    user_id = getattr(sub, "user_id", None)
    try:
        validate_public_https_url(endpoint)
        try:
            # Re-check immediately before the network call to fail closed on
            # DNS changes between subscription and delivery.  Development
            # fixtures may use non-resolving provider placeholders, but never
            # bypass an actual private-address resolution.
            validate_url_not_internal(endpoint)
        except ValueError as exc:
            try:
                is_development = bool(settings.is_development)
            except AttributeError:
                # Missing development configuration must remain fail-closed.
                is_development = False  # pragma: no mutate
            if not (is_development and "DNS resolution failed" in str(exc)):
                raise
        webpush(
            subscription_info=subscription_info,
            data=json_dumps(normalized_payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.WEBPUSH_SUBJECT},
            headers=headers,
            ttl=ttl,
        )
    except WebPushException as exc:
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
                user_id=uuid.UUID(str(user_id)) if user_id else None,
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
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            status="error",
            status_code=status_code,
            error=message or None,
        )
    except (ConnectionError, TimeoutError, OSError, ValueError) as exc:
        # RZ-20-04: Narrowed — WebPush send errors (HTTP/crypto/network).
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
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            status="error",
            error=str(exc),
        )

    _log_event("send", user_id=user_id, endpoint=sub.endpoint, status="sent")
    return WebPushResult(
        subscription_id=sub.id,
        endpoint=str(sub.endpoint),
        user_id=uuid.UUID(str(user_id)) if user_id else None,
        status="sent",
    )


_PUSH_CALL_TIMEOUT_SECONDS = 15.0


async def _send_push_async(
    sub: PushSubscription, prepared: dict[str, Any]
) -> WebPushResult:
    """Async wrapper for send_web_push with concurrency limit and per-call timeout.

    RED-07 (audit 2026-03-14): Semaphore prevents thread-pool exhaustion;
    asyncio.timeout ensures stuck vendors do not hold threads indefinitely.
    """
    semaphore = _get_push_semaphore()
    async with semaphore:
        try:
            async with asyncio.timeout(_PUSH_CALL_TIMEOUT_SECONDS):
                return await asyncio.to_thread(send_web_push, sub, prepared)
        except TimeoutError:
            import uuid as _uuid

            user_id = getattr(sub, "user_id", None)
            _log_event(
                "send",
                level=logging.WARNING,
                user_id=user_id,
                endpoint=sub.endpoint,
                status="error",
                error="push_timeout",
            )
            return WebPushResult(
                subscription_id=sub.id,
                endpoint=str(sub.endpoint),
                user_id=_uuid.UUID(str(user_id)) if user_id else None,
                status="error",
                error="push delivery timed out",
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
