from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.models import PushSubscription, User
from app.services.webpush import send_web_push

router = APIRouter(prefix="/push", tags=["push"])

class SubKeys(BaseModel):
    p256dh: str
    auth: str

class SubPayload(BaseModel):
    endpoint: str
    keys: SubKeys

class NotifyBody(BaseModel):
    title: str
    body: str | None = None
    url: str | None = None
    tag: str | None = None
    type: str | None = None
    ttl: int | None = 43200
    urgency: str | None = "normal"
    topic: str | None = None

@router.get("/public-key")
async def public_key():
    return {"key": settings.vapid_public_key}

@router.post("/subscribe")
async def subscribe(
    payload: SubPayload,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    endpoint = payload.endpoint.strip()
    p256dh = payload.keys.p256dh.strip()
    auth = payload.keys.auth.strip()
    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="invalid subscription")
    res = await session.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    sub = res.scalar_one_or_none()
    if sub:
        await session.execute(
            update(PushSubscription)
            .where(PushSubscription.id == sub.id)
            .values(active=True, p256dh=p256dh, auth=auth, user_id=user.id)
        )
    else:
        session.add(PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth, active=True, user_id=user.id))
    await session.commit()
    return {"ok": True}

@router.post("/unsubscribe")
async def unsubscribe(
    payload: SubPayload,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    endpoint = payload.endpoint.strip()
    await session.execute(
        update(PushSubscription)
        .where(PushSubscription.endpoint == endpoint, PushSubscription.user_id == user.id)
        .values(active=False)
    )
    await session.commit()
    return {"ok": True}

@router.post("/test")
async def send_test(
    data: NotifyBody | None = None,
    bg: BackgroundTasks = None,            # <-- НИ КАКОГО Depends()!
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # FastAPI сам инжектит BackgroundTasks, поэтому подстрахуемся на случай IDE:
    if bg is None:
        bg = BackgroundTasks()

    res = await session.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.active == True,
        )
    )
    subs = res.scalars().all()
    if not subs:
        return {"count": 0}

    payload = (data.model_dump() if data else {}) | {
        "title": (data.title if data and data.title else "Тестовое уведомление"),
        "body": (data.body if data and data.body else "Проверка доставки"),
        "url": (data.url if data and data.url else "/"),
    }
    for s in subs:
        bg.add_task(send_web_push, s, payload)
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
    res = await session.execute(select(PushSubscription).where(PushSubscription.active == True))
    subs = res.scalars().all()
    for s in subs:
        bg.add_task(send_web_push, s, data.model_dump())
    return {"count": len(subs)}