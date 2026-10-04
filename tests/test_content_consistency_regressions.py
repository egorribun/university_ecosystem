"""Exercise content writes and retained/legacy rows through real repositories."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.events import (
    EventBus,
    EventCreated,
    NewsCreated,
    register_event_listeners,
)
from app.models import Event, EventAttendance, News, User
from app.models.domain_events import StoredEvent
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services import attendance_tokens, event_handlers, search_indexer
from app.services.event_service import EventService
from app.services.news_service import NewsService
from app.workers import outbox


@pytest.fixture
async def projection_io(db_session, monkeypatch):
    """Real sessions and HTTP client; replace only remote transports/SQLite vector binding."""
    state = SimpleNamespace(
        documents={},
        clients=[],
        provider_error=False,
        status=200,
        embedding=[0.5] * 1536,
    )
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(search_indexer, "async_session", sessions)
    monkeypatch.setattr(event_handlers, "async_session", sessions)
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_key", "test-provider-key")
    monkeypatch.setattr(settings, "embedding_api_base", "https://93.184.216.34")
    if db_session.bind.dialect.name == "sqlite":
        # PostgreSQL binds lists through pgvector; SQLite's TEXT stand-in needs JSON.
        monkeypatch.setitem(
            sqlite3.adapters, (list, sqlite3.PrepareProtocol), json.dumps
        )
    real_client = httpx.AsyncClient

    def provider(request):
        if state.provider_error:
            raise RuntimeError("provider boundary failed")
        return httpx.Response(
            state.status,
            content=json.dumps({"data": [{"embedding": state.embedding}]}),
            headers={"Content-Type": "application/json"},
        )

    def client_factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(provider), **kwargs)
        state.clients.append(client)
        return client

    monkeypatch.setattr("app.services.vector_service.httpx.AsyncClient", client_factory)

    class Projection:
        async def index_document(self, index, document_id, document):
            state.documents[(index, document_id)] = document

        async def close(self):
            pass

    monkeypatch.setattr(search_indexer, "build_search_service", Projection)
    bus = EventBus()
    monkeypatch.setattr(event_handlers, "event_bus", bus)
    monkeypatch.setattr(outbox, "event_bus", bus)
    event_handlers.configure_event_handlers()
    try:
        yield state
    finally:
        for client in state.clients:
            await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
async def test_content_service_writes_reach_outbox_and_search(
    db_session, user_factory, projection_io, kind
):
    await register_event_listeners()
    user = await user_factory()
    uow = uow_from_session(db_session)
    vector = AsyncMock()
    if kind == "event":
        service = EventService(uow, vector)
        now = datetime.now(UTC)
        record = await service.create_event(
            schemas.EventCreate(
                title="Original",
                title_en="Open research seminar",
                starts_at=now,
                ends_at=now + timedelta(hours=1),
            ),
            user.id,
        )
        await service.update_event(record.id, schemas.EventUpdate(title="Updated"))
    else:
        service = NewsService(uow, vector)
        record = await service.create_news(
            schemas.NewsCreate(title="Original", content="Body")
        )
        await service.update_news(record.id, schemas.NewsUpdate(title="Updated"))
    rows = (
        (
            await db_session.execute(
                select(StoredEvent)
                .where(StoredEvent.aggregate_id == str(record.id))
                .order_by(StoredEvent.created_at, StoredEvent.id)
            )
        )
        .scalars()
        .all()
    )
    assert [row.event_type for row in rows] == [f"{kind}.created", f"{kind}.updated"]
    assert all(row.status == "pending" for row in rows)

    created = rows[0]
    assert created.payload["title"] == "Original"
    entity_key = "event_id_entity" if kind == "event" else "news_id"
    assert created.payload[entity_key] == str(record.id)
    if kind == "event":
        assert created.payload["organizer_id"] == str(user.id)
    index = "events" if kind == "event" else "news"
    await outbox.OutboxWorker()._dispatch_event(created)
    assert (index, str(record.id)) in projection_io.documents
    if kind == "event":
        assert (
            projection_io.documents[(index, str(record.id))]["title_en"]
            == "Open research seminar"
        )
    await outbox.OutboxWorker()._dispatch_event(rows[1])
    assert projection_io.documents[(index, str(record.id))]["title"] == "Updated"
    model = Event if kind == "event" else News
    embedding = await db_session.scalar(
        select(model.embedding).where(model.id == record.id)
    )
    if isinstance(embedding, str):
        embedding = json.loads(embedding)
    assert list(embedding) == [0.5] * 1536
    assert len(projection_io.clients) == 2
    assert all(client.is_closed for client in projection_io.clients)


@pytest.mark.asyncio
async def test_retained_event_serializes_after_creator_deleted(
    db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    row = Event(
        title="Retained",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add(row)
    await db_session.commit()
    event_id = row.id
    await db_session.execute(delete(User).where(User.id == user.id))
    await db_session.commit()
    db_session.expire_all()
    service = EventService(uow_from_session(db_session), AsyncMock())
    detail = await service.get_event_detail(event_id, None)
    assert detail is not None
    assert detail.created_by is None


@pytest.mark.asyncio
@pytest.mark.parametrize("secret,mac", [("", ""), ("legacy-secret", "old-signing-key")])
async def test_detail_repairs_frozen_attendance_and_persists_values(
    db_session, user_factory, secret, mac
):
    user = await user_factory()
    now = datetime.now(UTC)
    row = Event(
        title="Legacy",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add(row)
    await db_session.flush()
    attendance = EventAttendance(
        event_id=row.id, user_id=user.id, qr_secret=secret, qr_hmac=mac
    )
    db_session.add(attendance)
    await db_session.commit()
    service = EventService(uow_from_session(db_session), AsyncMock())
    detail = await service.get_event_detail(row.id, user.id)
    assert detail is not None
    persisted = await service.repo.get_attendance(row.id, user.id)
    assert persisted is not None
    assert persisted.qr_secret
    assert persisted.qr_hmac == attendance_tokens.compute_secret_hmac(
        persisted.qr_secret
    )
    if secret:
        assert persisted.qr_secret == secret
    assert (
        attendance_tokens.verify_token(detail.my_qr_token, persisted).user_id == user.id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["redis", "memory", "tiered"])
async def test_attendance_mutations_refresh_cached_membership_and_etags(
    async_client, db_session, user_factory, fake_cache, backend
):
    from app.auth.security import get_password_hash
    from app.deps.cache import MemoryCache, TieredCache, set_cache_backend
    from tests.test_event_attendance_api import _login

    if backend == "memory":
        set_cache_backend(MemoryCache())
    elif backend == "tiered":
        set_cache_backend(TieredCache(MemoryCache(), MemoryCache()))

    password = f"Aa1!{uuid4()}"
    user = await user_factory(hashed_password=await get_password_hash(password))
    now = datetime.now(UTC)
    row = Event(
        title="Cached membership",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=user.id,
    )
    db_session.add(row)
    await db_session.commit()
    headers = await _login(async_client, user.email, password)
    paths = ["/events", f"/events/{row.id}", "/events/my"]
    initial = [await async_client.get(path, headers=headers) for path in paths]
    assert all(response.status_code == 200 for response in initial)
    assert all(response.headers.get("etag") for response in initial)
    response = await async_client.post(
        "/events/attendance", headers=headers, json={"event_id": str(row.id)}
    )
    assert response.status_code == 200
    registered = [
        await async_client.get(
            path, headers={**headers, "If-None-Match": old.headers["etag"]}
        )
        for path, old in zip(paths, initial, strict=True)
    ]
    assert all(response.status_code == 200 for response in registered)
    assert registered[0].json()["items"][0]["is_registered"] is True
    assert registered[1].json()["is_registered"] is True
    assert registered[1].json()["participant_count"] == 1
    assert registered[2].json()[0]["id"] == str(row.id)
    response = await async_client.request(
        "DELETE", "/events/attendance", headers=headers, json={"event_id": str(row.id)}
    )
    assert response.status_code == 200
    unregistered = [
        await async_client.get(
            path, headers={**headers, "If-None-Match": old.headers["etag"]}
        )
        for path, old in zip(paths, registered, strict=True)
    ]
    assert all(response.status_code == 200 for response in unregistered)
    assert unregistered[0].json()["items"][0]["is_registered"] is False
    assert unregistered[1].json()["participant_count"] == 0
    assert unregistered[2].json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
async def test_rolled_back_content_emits_no_outbox_on_next_commit(
    db_session, user_factory, kind
):
    await register_event_listeners()
    user = await user_factory()
    uow = uow_from_session(db_session)
    repo = uow.events if kind == "event" else uow.news
    now = datetime.now(UTC)
    payload = (
        {
            "title": "Rolled back",
            "starts_at": now,
            "ends_at": now + timedelta(hours=1),
            "created_by": user.id,
        }
        if kind == "event"
        else {"title": "Rolled back", "content": "Body"}
    )
    record = await repo.create(payload)
    await db_session.rollback()
    await db_session.commit()
    assert await repo.get(record.id) is None
    rows = (
        (
            await db_session.execute(
                select(StoredEvent).where(StoredEvent.aggregate_id == str(record.id))
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
async def test_rolled_back_update_restores_content_without_update_event(
    db_session, user_factory, kind
):
    await register_event_listeners()
    user = await user_factory()
    uow = uow_from_session(db_session)
    repo = uow.events if kind == "event" else uow.news
    now = datetime.now(UTC)
    payload = (
        {
            "title": "Original",
            "starts_at": now,
            "ends_at": now + timedelta(hours=1),
            "created_by": user.id,
        }
        if kind == "event"
        else {"title": "Original", "content": "Body"}
    )
    original = await repo.create(payload)
    await db_session.commit()
    await repo.update(original.id, {"title": "Rolled back"})
    await db_session.rollback()
    await db_session.commit()
    persisted = await repo.get(original.id)
    assert persisted.title == "Original"
    rows = (
        (
            await db_session.execute(
                select(StoredEvent).where(StoredEvent.aggregate_id == str(original.id))
            )
        )
        .scalars()
        .all()
    )
    assert [row.event_type for row in rows] == [f"{kind}.created"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
async def test_updating_missing_content_does_not_emit_an_event(db_session, kind):
    from uuid import uuid4

    uow = uow_from_session(db_session)
    repo = uow.events if kind == "event" else uow.news
    missing = uuid4()
    assert await repo.update(missing, {"title": "Missing"}) is None
    await db_session.commit()
    assert (
        await db_session.execute(
            select(StoredEvent).where(StoredEvent.aggregate_id == str(missing))
        )
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_disappearing_attendance_during_repair_is_not_serialized(
    db_session, user_factory, monkeypatch
):
    from app.core.exceptions.domain import EntityNotFound

    user = await user_factory()
    now = datetime.now(UTC)
    row = Event(
        title="Legacy race",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add(row)
    await db_session.flush()
    attendance = EventAttendance(
        event_id=row.id, user_id=user.id, qr_secret="", qr_hmac=""
    )
    db_session.add(attendance)
    await db_session.commit()
    service = EventService(uow_from_session(db_session), AsyncMock())
    monkeypatch.setattr(service.repo, "update_attendance", AsyncMock(return_value=None))
    with pytest.raises(EntityNotFound):
        await service.get_event_detail(row.id, user.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
@pytest.mark.parametrize("outcome", ["normal", "missing", "error"])
async def test_embedding_consumers_close_client_on_every_path(
    db_session, user_factory, projection_io, kind, outcome
):
    user = await user_factory()
    now = datetime.now(UTC)
    if kind == "event":
        row = Event(
            title="Consumer lifecycle",
            starts_at=now,
            ends_at=now + timedelta(hours=1),
            created_by=user.id,
        )
        handler = event_handlers.generate_event_embedding
    else:
        row = News(title="Consumer lifecycle", content="Body")
        handler = event_handlers.generate_news_embedding
    db_session.add(row)
    await db_session.commit()
    record_id = uuid4() if outcome == "missing" else row.id
    event = (
        EventCreated(event_id_entity=str(record_id))
        if kind == "event"
        else NewsCreated(news_id=str(record_id))
    )
    projection_io.provider_error = outcome == "error"
    if outcome == "error":
        with pytest.raises(RuntimeError, match="provider boundary"):
            await handler(event)
    else:
        await handler(event)
    assert len(projection_io.clients) == 1
    assert projection_io.clients[0].is_closed


@pytest.mark.asyncio
async def test_event_detail_repairs_via_primary_with_readonly_replica(
    async_client, db_session, user_factory, monkeypatch
):
    from sqlalchemy import event as sa_event
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.auth.security import get_password_hash
    from app.core.database import get_read_db
    from app.main import app
    from tests.test_event_attendance_api import _login

    password = f"Aa1!{uuid4()}"
    user = await user_factory(hashed_password=await get_password_hash(password))
    now = datetime.now(UTC)
    row = Event(
        title="Primary repair",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add(row)
    await db_session.flush()
    attendance = EventAttendance(
        event_id=row.id, user_id=user.id, qr_secret="", qr_hmac=""
    )
    db_session.add(attendance)
    await db_session.commit()
    read_engine = create_async_engine(db_session.bind.url)

    @sa_event.listens_for(read_engine.sync_engine, "connect")
    def readonly(connection, _record):
        cursor = connection.cursor()
        cursor.execute(
            "PRAGMA query_only=ON"
            if read_engine.dialect.name == "sqlite"
            else "SET default_transaction_read_only = on"
        )
        cursor.close()

    read_sessions = async_sessionmaker(read_engine, expire_on_commit=False)

    async def read_db():
        async with read_sessions() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_read_db, read_db)
    try:
        headers = await _login(async_client, user.email, password)
        response = await async_client.get(f"/events/{row.id}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["my_qr_token"]
        assert await db_session.scalar(
            select(EventAttendance.qr_secret).where(EventAttendance.id == attendance.id)
        )
    finally:
        await read_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
@pytest.mark.parametrize(
    "mode", ["disabled", "no_key", "failure", "zero", "nan", "empty"]
)
async def test_embedding_fallback_is_never_persisted(
    db_session, user_factory, projection_io, monkeypatch, kind, mode
):
    user = await user_factory()
    now = datetime.now(UTC)
    if kind == "event":
        row = Event(
            title="Fallback",
            starts_at=now,
            ends_at=now + timedelta(hours=1),
            created_by=user.id,
        )
        handler = event_handlers.generate_event_embedding
    else:
        row = News(title="Fallback", content="Body")
        handler = event_handlers.generate_news_embedding
    db_session.add(row)
    await db_session.commit()
    event = (
        EventCreated(event_id_entity=str(row.id))
        if kind == "event"
        else NewsCreated(news_id=str(row.id))
    )
    if mode == "disabled":
        monkeypatch.setattr(settings, "semantic_search_enabled", False)
    elif mode == "no_key":
        monkeypatch.setattr(settings, "embedding_api_key", "")
    elif mode == "failure":
        projection_io.status = 503
    elif mode == "nan":
        projection_io.embedding = [float("nan")] * 1536
    elif mode == "empty":
        projection_io.embedding = []
    else:
        projection_io.embedding = [0.0] * 1536
    if mode in {"failure", "zero", "nan", "empty"}:
        with pytest.raises(RuntimeError, match="Embedding"):
            await handler(event)
    else:
        await handler(event)
    model = Event if kind == "event" else News
    assert (
        await db_session.scalar(select(model.embedding).where(model.id == row.id))
        is None
    )
    assert all(client.is_closed for client in projection_io.clients)
