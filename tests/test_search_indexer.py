"""The indexer that makes ``/api/v1/search`` return real results."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import elasticsearch
import pytest
from elastic_transport import ApiResponseMeta, HttpHeaders, NodeConfig
from typer.testing import CliRunner

import app.models as models
from app.cli import search as search_cli
from app.services import event_handlers, search_indexer


def _fake_service() -> MagicMock:
    service = MagicMock()
    service.index_document = AsyncMock()
    service.delete_document = AsyncMock()
    service.ensure_index = AsyncMock()
    service.bulk_index = AsyncMock(side_effect=lambda index, docs: (len(docs), 0))
    service.close = AsyncMock()
    service.publish_rebuilt_indices = AsyncMock()
    service.delete_index = AsyncMock()
    return service


@pytest.fixture
def service():
    fake = _fake_service()
    with patch.object(search_indexer, "build_search_service", return_value=fake):
        yield fake


@pytest.fixture
def session(db_session):
    @asynccontextmanager
    async def factory():
        yield db_session

    with patch.object(search_indexer, "async_session", factory):
        yield db_session


async def _news(db, user, **overrides) -> models.News:
    news = models.News(
        title="Открытие библиотеки",
        content="Новая библиотека открыта для студентов",
        title_en="Library opening",
        content_en="The new library is open",
        author_id=user.id,
        **overrides,
    )
    db.add(news)
    await db.flush()
    return news


async def _event(
    db, user, *, active: bool = True, title: str = "Хакатон"
) -> models.Event:
    starts = datetime.now(UTC) + timedelta(days=1)
    event = models.Event(
        title=title,
        description="Командное соревнование",
        location="Аудитория 1",
        event_type="hackathon",
        starts_at=starts,
        ends_at=starts + timedelta(hours=2),
        created_by=user.id,
        is_active=active,
    )
    db.add(event)
    await db.flush()
    return event


def test_build_search_service_uses_settings_and_optional_auth():
    with patch.object(search_indexer, "settings") as settings:
        settings.elasticsearch_url = "http://es:9200"
        settings.elasticsearch_user = "elastic"
        settings.elasticsearch_password = "secret"  # pragma: allowlist secret
        authed = search_indexer.build_search_service()
        settings.elasticsearch_password = ""
        anonymous = search_indexer.build_search_service()

    assert authed._hosts == ["http://es:9200"]
    assert authed._http_auth == ("elastic", "secret")
    assert anonymous._http_auth is None


@pytest.mark.asyncio
async def test_documents_expose_every_searchable_field(db_session, user_factory):
    user = await user_factory()
    news = await _news(db_session, user)
    event = await _event(db_session, user)

    news_doc = search_indexer.news_document(news)
    event_doc = search_indexer.event_document(event)

    assert news_doc["id"] == str(news.id)
    assert news_doc["title_en"] == "Library opening"
    assert news_doc["created_at"] is not None
    assert event_doc["category"] == "hackathon"
    assert event_doc["start_time"] < event_doc["end_time"]


@pytest.mark.asyncio
async def test_index_news_writes_document(session, service, user_factory):
    news = await _news(session, await user_factory())

    await search_indexer.index_news(news.id)

    service.index_document.assert_awaited_once()
    index, doc_id, body = service.index_document.await_args.args
    assert (index, doc_id) == ("news", str(news.id))
    assert body["title"] == "Открытие библиотеки"
    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_index_news_ignores_missing_ids(session, service):
    await search_indexer.index_news(None)
    await search_indexer.index_news(uuid.uuid4())
    service.index_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_index_event_writes_active_event(session, service, user_factory):
    event = await _event(session, await user_factory())

    await search_indexer.index_event(event.id)

    assert service.index_document.await_args.args[0] == "events"
    service.delete_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_deactivated_or_missing_event_is_removed_from_index(
    session, service, user_factory
):
    inactive = await _event(session, await user_factory(), active=False)

    await search_indexer.index_event(inactive.id)
    await search_indexer.index_event(uuid.uuid4())
    await search_indexer.index_event(None)

    service.index_document.assert_not_awaited()
    assert service.delete_document.await_count == 2
    assert service.delete_document.await_args_list[0].args == (
        "events",
        str(inactive.id),
    )


def _transport_error() -> Exception:
    return elasticsearch.ConnectionError("es down")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        OSError("socket"),
        ConnectionError("refused"),
        TimeoutError("slow"),
        elasticsearch.ConnectionError("es down"),
        elasticsearch.ApiError(
            "boom",
            ApiResponseMeta(
                status=503,
                http_version="1.1",
                headers=HttpHeaders(),
                duration=0.0,
                node=NodeConfig("http", "es", 9200),
            ),
            body={},
        ),
    ],
)
async def test_search_outage_never_fails_the_caller(session, service, error):
    service.delete_document.side_effect = error

    await search_indexer.remove_document("news", uuid.uuid4())

    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unexpected_errors_are_not_swallowed(session, service):
    service.delete_document.side_effect = ValueError("bug")
    with pytest.raises(ValueError):
        await search_indexer.remove_document("news", "1")
    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_reindex_all_pages_through_active_rows(session, service, user_factory):
    user = await user_factory()
    for _ in range(3):
        await _news(session, user)
    await _event(session, user)
    await _event(session, user, title="Второй")
    await _event(session, user, active=False, title="Скрытый")

    counts = await search_indexer.reindex_all(batch_size=2)

    assert counts == {"news": 3, "events": 2}
    replacements = service.publish_rebuilt_indices.await_args.args[0]
    assert [c.args[0] for c in service.ensure_index.await_args_list] == [
        replacements["news"],
        replacements["events"],
    ]
    assert replacements["news"].startswith("news-rebuild-")
    assert replacements["events"].startswith("events-rebuild-")
    assert service.bulk_index.await_count == 3  # news pages of 2+1, one event page
    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_reindex_closes_client_when_indexing_fails(session, service):
    service.ensure_index.side_effect = elasticsearch.ConnectionError("down")
    with pytest.raises(elasticsearch.ConnectionError):
        await search_indexer.reindex_all()
    service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_handlers_delegate_to_indexer():
    news_id, event_id = uuid.uuid4(), uuid.uuid4()
    with (
        patch.object(search_indexer, "index_news", AsyncMock()) as news,
        patch.object(search_indexer, "index_event", AsyncMock()) as event,
    ):
        await event_handlers.index_news_for_search(MagicMock(news_id=news_id))
        await event_handlers.index_event_for_search(MagicMock(event_id_entity=event_id))
    news.assert_awaited_once_with(news_id)
    event.assert_awaited_once_with(event_id)


def test_handlers_are_registered_for_create_and_update_events():
    from app.core.events import EventBus

    bus = EventBus()
    with patch.object(event_handlers, "event_bus", bus):
        event_handlers.configure_event_handlers()
    for event_type, handler in (
        ("news.created", event_handlers.index_news_for_search),
        ("news.updated", event_handlers.index_news_for_search),
        ("event.created", event_handlers.index_event_for_search),
        ("event.updated", event_handlers.index_event_for_search),
    ):
        assert handler in bus._handlers[event_type]


def test_cli_reindex_reports_counts():
    with patch.object(
        search_cli,
        "reindex_all",
        AsyncMock(return_value={"news": 3, "events": 2}),
    ) as reindex:
        result = CliRunner().invoke(search_cli.app, ["reindex", "--batch-size", "50"])

    assert result.exit_code == 0
    assert "news: 3 documents indexed" in result.output
    assert "events: 2 documents indexed" in result.output
    reindex.assert_awaited_once_with(batch_size=50)
