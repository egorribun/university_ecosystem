import json
from sqlalchemy import delete, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import make_url
from pywebpush import webpush, WebPushException
from app.core.config import settings
from app.models.models import PushSubscription

url = make_url(settings.database_url)
if url.drivername.endswith("+asyncpg"):
    url = url.set(drivername="postgresql+psycopg")
_sync_engine = create_engine(str(url), pool_pre_ping=True, future=True)
_Session = sessionmaker(bind=_sync_engine, autocommit=False, autoflush=False)

def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)

def send_web_push(sub: PushSubscription, data: dict):
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
    try:
        webpush(
            subscription_info=subscription_info,
            data=json_dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject or "mailto:no-reply@example.com"},
            headers=headers,
            ttl=ttl if ttl is not None else 43200,
        )
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        txt = str(e)
        gone = status in (404, 410) or ("404" in txt or "410" in txt)
        if gone:
            with _Session() as s:
                s.execute(delete(PushSubscription).where(PushSubscription.id == sub.id))
                s.commit()