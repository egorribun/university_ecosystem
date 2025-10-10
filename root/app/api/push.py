from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.models import PushSubscription, User
from app.services.notifications import prepare_push_payload_for_user
from app.services.push_schema import ensure_push_subscription_schema
from app.services.push_topics import normalize_topic, subscription_supports_topic
from app.services.webpush import WebPushResult, send_web_push

router = APIRouter(prefix="/push", tags=["push"])

logger = logging.getLogger(__name__)


class SubKeys(BaseModel):
    p256dh: str
    auth: str


class SubPayload(BaseModel):
    endpoint: str
    keys: SubKeys


class NotificationAction(BaseModel):
    action: str = Field(..., description="Notification action identifier")
    title: str = Field(..., description="Action button title")
    url: str | None = Field(default=None, description="Optional URL to open")
    icon: str | None = Field(default=None, description="Optional icon URL")

    @field_validator("action", "title", mode="before")
    @classmethod
    def _strip(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()


class NotifyBody(BaseModel):
    title: str
    body: str | None = None
    url: str | None = None
    tag: str | None = None
    badge: str | None = None
    type: str | None = None
    ttl: int | None = None
    urgency: str | None = "normal"
    topic: str | None = None
    actions: list[NotificationAction] | None = None
    data: dict[str, Any] | None = None

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic(cls, value):
        return normalize_topic(value)


class DisableUserPushRequest(BaseModel):
    user_id: int = Field(
        ..., ge=1, description="ID пользователя, для которого нужно отключить push"
    )


@router.get("/public-key")
async def public_key():
    return {"key": settings.VAPID_PUBLIC_KEY}


@router.post("/subscribe")
async def subscribe(
    payload: SubPayload,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_push_subscription_schema(session)
    endpoint = payload.endpoint.strip()
    p256dh = payload.keys.p256dh.strip()
    auth = payload.keys.auth.strip()
    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="invalid subscription")
    user_agent = (request.headers.get("user-agent") or "").strip()
    if len(user_agent) > 512:
        user_agent = user_agent[:512]
    res = await session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    sub = res.scalar_one_or_none()
    now = datetime.now(UTC)
    if sub:
        if sub.user_id != user.id:
            raise HTTPException(status_code=409, detail="duplicate endpoint")
        sub.p256dh = p256dh
        sub.auth = auth
        sub.user_id = user.id
        sub.user_agent = user_agent or None
        sub.last_seen_at = now
        sub.topics = sub.topics or []
    else:
        session.add(
            PushSubscription(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_id=user.id,
                user_agent=user_agent or None,
                last_seen_at=now,
                topics=[],
            )
        )
    await session.commit()
    return {"ok": True}


@router.post("/unsubscribe")
async def unsubscribe(
    payload: SubPayload,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_push_subscription_schema(session)
    endpoint = payload.endpoint.strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="invalid subscription")
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == endpoint, PushSubscription.user_id == user.id
        )
    )
    await session.commit()
    return {"ok": True}


class PushSendResponse(BaseModel):
    total: int
    sent: int
    removed: int
    failed: int
    detail: str | None = None


async def _deliver_to_subscription(
    subscription: PushSubscription, payload: dict[str, Any]
) -> WebPushResult:
    return await run_in_threadpool(send_web_push, subscription, payload)


def _aggregate_results(results: list[WebPushResult]) -> PushSendResponse:
    sent = sum(1 for r in results if r.status == "sent")
    removed = sum(1 for r in results if r.status == "gone")
    failed = sum(1 for r in results if r.status == "error")
    detail = None
    if results and sent == 0 and failed:
        detail = "Не удалось отправить уведомления"
    return PushSendResponse(
        total=len(results),
        sent=sent,
        removed=removed,
        failed=failed,
        detail=detail,
    )


@router.post("/admin/disable-user")
async def disable_user_push(
    payload: DisableUserPushRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_push_subscription_schema(session)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    target = await session.get(User, payload.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user_not_found")
    existing = (
        (
            await session.execute(
                select(PushSubscription.id).where(PushSubscription.user_id == target.id)
            )
        )
        .scalars()
        .all()
    )
    if not existing:
        return {"ok": True, "removed": 0}
    await session.execute(
        delete(PushSubscription).where(PushSubscription.user_id == target.id)
    )
    await session.commit()
    logger.info(
        "push.admin.disable_all",
        extra={
            "user_id": user.id,
            "target_user_id": target.id,
            "removed": len(existing),
        },
    )
    return {"ok": True, "removed": len(existing)}


@router.post("/test", response_model=PushSendResponse)
async def send_test(
    data: NotifyBody | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PushSendResponse:
    await ensure_push_subscription_schema(session)
    res = await session.execute(
        select(PushSubscription)
        .options(selectinload(PushSubscription.user))
        .where(PushSubscription.user_id == user.id)
    )
    subs = res.scalars().all()
    if not subs:
        return PushSendResponse(total=0, sent=0, removed=0, failed=0)

    requested_topic = normalize_topic(getattr(data, "topic", None) if data else None)
    payload = (data.model_dump(exclude_none=True) if data else {}) | {
        "title": (data.title if data and data.title else "Тестовое уведомление"),
        "body": (data.body if data and data.body else "Проверка доставки"),
        "url": (data.url if data and data.url else "/"),
    }
    if requested_topic:
        payload["topic"] = requested_topic
    now_time = datetime.now().astimezone().time()
    results: list[WebPushResult] = []
    for s in subs:
        if not subscription_supports_topic(s, requested_topic):
            continue
        prepared = prepare_push_payload_for_user(
            payload, getattr(s, "user", None), now_time=now_time
        )
        result = await _deliver_to_subscription(s, prepared)
        results.append(result)
    response = _aggregate_results(results)
    logger.info(
        "push.test.summary",
        extra={
            "user_id": user.id,
            "total": response.total,
            "sent": response.sent,
            "removed": response.removed,
            "failed": response.failed,
        },
    )
    return response


@router.post("/broadcast", response_model=PushSendResponse)
async def broadcast(
    data: NotifyBody,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PushSendResponse:
    await ensure_push_subscription_schema(session)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    res = await session.execute(
        select(PushSubscription).options(selectinload(PushSubscription.user))
    )
    subs = res.scalars().all()
    topic = normalize_topic(data.topic)
    payload = data.model_dump()
    if topic:
        payload["topic"] = topic
    else:
        payload.pop("topic", None)
    now_time = datetime.now().astimezone().time()
    results: list[WebPushResult] = []
    for s in subs:
        if not subscription_supports_topic(s, topic):
            continue
        prepared = prepare_push_payload_for_user(
            payload, getattr(s, "user", None), now_time=now_time
        )
        results.append(await _deliver_to_subscription(s, prepared))
    response = _aggregate_results(results)
    logger.info(
        "push.broadcast.summary",
        extra={
            "user_id": user.id,
            "total": response.total,
            "sent": response.sent,
            "removed": response.removed,
            "failed": response.failed,
        },
    )
    return response
