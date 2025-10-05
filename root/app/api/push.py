from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.models import PushSubscription, User
from app.services.notifications import prepare_push_payload_for_user
from app.services.webpush import send_web_push

router = APIRouter(prefix="/push", tags=["push"])


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
    ttl: int | None = 43200
    urgency: str | None = "normal"
    topic: str | None = None
    actions: list[NotificationAction] | None = None
    data: dict[str, Any] | None = None


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


@router.post("/test")
async def send_test(
    data: NotifyBody | None = None,
    bg: BackgroundTasks = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if bg is None:
        bg = BackgroundTasks()

    res = await session.execute(
        select(PushSubscription)
        .options(selectinload(PushSubscription.user))
        .where(PushSubscription.user_id == user.id)
    )
    subs = res.scalars().all()
    if not subs:
        return {"count": 0}

    payload = (data.model_dump(exclude_none=True) if data else {}) | {
        "title": (data.title if data and data.title else "Тестовое уведомление"),
        "body": (data.body if data and data.body else "Проверка доставки"),
        "url": (data.url if data and data.url else "/"),
    }
    now_time = datetime.now().astimezone().time()
    for s in subs:
        prepared = prepare_push_payload_for_user(
            payload, getattr(s, "user", None), now_time=now_time
        )
        bg.add_task(send_web_push, s, prepared)
    return {"count": len(subs)}


@router.post("/broadcast")
async def broadcast(
    data: NotifyBody,
    bg: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    res = await session.execute(
        select(PushSubscription).options(selectinload(PushSubscription.user))
    )
    subs = res.scalars().all()
    payload = data.model_dump()
    now_time = datetime.now().astimezone().time()
    for s in subs:
        prepared = prepare_push_payload_for_user(
            payload, getattr(s, "user", None), now_time=now_time
        )
        bg.add_task(send_web_push, s, prepared)
    return {"count": len(subs)}
