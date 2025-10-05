from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pywebpush import WebPushException, webpush
from sqlalchemy import create_engine, delete, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.models import PushSubscription

logger = logging.getLogger(__name__)

url = make_url(settings.database_url)
if url.drivername.endswith("+asyncpg"):
    url = url.set(drivername="postgresql+psycopg")
_sync_engine = create_engine(str(url), pool_pre_ping=True, future=True)
_Session = sessionmaker(bind=_sync_engine, autocommit=False, autoflush=False)


def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


@dataclass(slots=True)
class WebPushResult:
    subscription_id: int
    endpoint: str
    user_id: int
    status: Literal["sent", "gone", "error"]
    status_code: int | None = None
    error: str | None = None


def send_web_push(sub: PushSubscription, data: dict) -> WebPushResult:
    payload = {
        "title": data.get("title") or "Уведомление",
        "body": data.get("body") or "",
        "url": data.get("url") or "/",
        "tag": data.get("tag"),
        "type": data.get("type"),
    }
    ttl_val = data.get("ttl")
    ttl = int(ttl_val) if ttl_val is not None else None
    headers = {}
    urgency = data.get("urgency")
    if urgency:
        headers["Urgency"] = urgency
    topic = data.get("topic")
    if topic:
        headers["Topic"] = topic
    subscription_info = {
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    user_id = getattr(sub, "user_id", None) or 0
    try:
        webpush(
            subscription_info=subscription_info,
            data=json_dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.WEBPUSH_SUBJECT},
            headers=headers,
            ttl=ttl if ttl is not None else 43200,
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
            with _Session() as session:
                session.execute(
                    delete(PushSubscription).where(PushSubscription.id == sub.id)
                )
                session.commit()
            logger.info(
                "webpush.send",
                extra={
                    "user_id": user_id,
                    "endpoint": sub.endpoint,
                    "status": "gone",
                    "status_code": status_code,
                },
            )
            return WebPushResult(
                subscription_id=sub.id,
                endpoint=sub.endpoint,
                user_id=user_id,
                status="gone",
                status_code=status_code,
                error=message or None,
            )
        logger.info(
            "webpush.send",
            extra={
                "user_id": user_id,
                "endpoint": sub.endpoint,
                "status": "error",
                "status_code": status_code,
            },
        )
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=user_id,
            status="error",
            status_code=status_code,
            error=message or None,
        )
    except Exception as exc:  # pragma: no cover - unexpected failure
        logger.exception(
            "webpush.send", extra={"user_id": user_id, "endpoint": sub.endpoint}
        )
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=user_id,
            status="error",
            error=str(exc),
        )
    now = datetime.now(UTC)
    with _Session() as session:
        session.execute(
            update(PushSubscription)
            .where(PushSubscription.id == sub.id)
            .values(last_seen_at=now)
        )
        session.commit()
    logger.info(
        "webpush.send",
        extra={"user_id": user_id, "endpoint": sub.endpoint, "status": "sent"},
    )
    return WebPushResult(
        subscription_id=sub.id,
        endpoint=sub.endpoint,
        user_id=user_id,
        status="sent",
    )
