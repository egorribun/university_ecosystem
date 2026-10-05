"""Full rebuild changes live search only after every replacement is complete."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, News
from app.services import search_indexer
from app.services.search import SearchService
from tests.helpers.search_rebuild import RebuildProgress


class SearchCluster:
    def __init__(self):
        self.documents = {
            "news": {"deleted": {"title": "Stale"}},
            "events": {"inactive": {"title": "Stale"}},
        }
        self.mappings = {"news": {"obsolete": True}, "events": {"obsolete": True}}
        self.aliases = {}
        self.failed_bulk = False
        self.switches = 0
        self.indices = self

    def target(self, name):
        return self.aliases.get(name, name)

    async def exists(self, *, index):
        return index in self.documents or index in self.aliases

    async def exists_alias(self, *, name):
        return name in self.aliases

    async def create(self, *, index, body):
        self.documents[index] = {}
        self.mappings[index] = body["mappings"]

    async def get_alias(self, *, name):
        return {self.aliases[name]: {"aliases": {name: {}}}}

    async def refresh(self, *, index):
        assert all(name in self.documents for name in index.split(","))

    async def update_aliases(self, *, actions):
        # Singular transfers are modelled below; names follow the full ES 8.19 API.
        # https://www.elastic.co/guide/en/elasticsearch/reference/8.19/indices-aliases.html
        allowed_fields = {
            "add": {
                "index",
                "indices",
                "alias",
                "aliases",
                "filter",
                "index_routing",
                "is_hidden",
                "is_write_index",
                "routing",
                "search_routing",
            },
            "remove": {"index", "indices", "alias", "aliases", "must_exist"},
            "remove_index": {"index", "indices"},
        }
        for action in actions:
            operation, options = next(iter(action.items()))
            if set(options) - allowed_fields[operation]:
                raise ValueError("Unknown alias action field")
        for action in actions:
            if "remove_index" in action:
                name = action["remove_index"]["index"]
                del self.documents[name]
                del self.mappings[name]
            elif "remove" in action:
                del self.aliases[action["remove"]["alias"]]
            else:
                self.aliases[action["add"]["alias"]] = action["add"]["index"]
        self.switches += 1
        self.actions = actions
        return {"acknowledged": True, "errors": False}

    async def delete(self, *, index, ignore_unavailable=False):
        self.documents.pop(index, None)
        self.mappings.pop(index, None)

    async def index(self, *, index, id, body):
        self.documents[self.target(index)][id] = body

    async def bulk(self, index, docs):
        if self.failed_bulk:
            return 0, len(docs)
        self.documents[index].update({doc["id"]: doc for doc in docs})
        return len(docs), 0

    async def close(self):
        pass


@pytest.fixture
def cluster(db_session, monkeypatch):
    cluster = SearchCluster()
    service = SearchService()
    service._client = cluster
    service.bulk_index = cluster.bulk

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(search_indexer, "async_session", session)
    monkeypatch.setattr(search_indexer, "build_search_service", lambda: service)
    return cluster


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("public_state", "removal_actions"),
    [
        (
            "alias",
            [
                {
                    "remove": {
                        "index": "curated-news-v1",
                        "alias": "news",
                        "must_exist": True,
                    }
                }
            ],
        ),
        ("concrete", [{"remove_index": {"index": "news"}}]),
        ("absent", []),
    ],
    ids=["existing-alias", "legacy-concrete-index", "missing-public-name"],
)
async def test_publish_rebuilt_indices_uses_valid_elasticsearch_requests(
    monkeypatch, public_state, removal_actions
):
    client = AsyncElasticsearch("http://localhost:9200")
    service = SearchService()
    service._client = client
    requests = []
    responses = {
        ("HEAD", "/_alias/news"): public_state == "alias",
        ("GET", "/_alias/news"): {"curated-news-v1": {"aliases": {"news": {}}}},
        ("HEAD", "/news"): public_state == "concrete",
        ("POST", "/news-rebuild-ready/_refresh"): {},
        ("POST", "/_aliases"): {"acknowledged": True, "errors": False},
    }

    async def perform_request(method, path, **kwargs):
        requests.append((method, path, kwargs.get("body")))
        return responses[method, path]

    # Keep the installed endpoint methods and their argument validation real.
    # The request boundary is local; this does not exercise an ES server.
    monkeypatch.setattr(client.indices, "perform_request", perform_request)
    try:
        await service.publish_rebuilt_indices({"news": "news-rebuild-ready"})
    finally:
        await client.close()

    assert requests[-2:] == [
        ("POST", "/news-rebuild-ready/_refresh", None),
        (
            "POST",
            "/_aliases",
            {
                "actions": [
                    *removal_actions,
                    {
                        "add": {
                            "index": "news-rebuild-ready",
                            "alias": "news",
                            "is_write_index": True,
                        }
                    },
                ]
            },
        ),
    ]


@pytest.mark.asyncio
async def test_empty_rebuild_removes_stale_documents_and_old_mappings(cluster):
    assert await search_indexer.reindex_all() == {"news": 0, "events": 0}
    for name, mappings in [
        ("news", search_indexer.NEWS_MAPPINGS),
        ("events", search_indexer.EVENTS_MAPPINGS),
    ]:
        target = cluster.target(name)
        assert cluster.documents[target] == {}
        assert cluster.mappings[target] == mappings
    assert cluster.switches == 1


@pytest.mark.asyncio
async def test_rebuild_excludes_inactive_and_deleted_documents(
    cluster, db_session, user_factory, monkeypatch
):
    user = await user_factory()
    now = datetime.now(UTC)
    news = News(title="Current", content="Body")
    active = Event(
        title="Active",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
    )
    inactive = Event(
        title="Inactive",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_by=user.id,
        is_active=False,
    )
    db_session.add_all([news, active, inactive])
    await db_session.commit()
    progress = RebuildProgress()
    service = search_indexer.build_search_service()
    bulk_index = service.bulk_index

    async def index_page(index, documents):
        await progress.record(index, documents)
        return await bulk_index(index, documents)

    monkeypatch.setattr(service, "bulk_index", index_page)
    assert await progress.complete(search_indexer.reindex_all(batch_size=1)) == {
        "news": 1,
        "events": 1,
    }
    assert set(cluster.documents[cluster.target("news")]) == {str(news.id)}
    assert set(cluster.documents[cluster.target("events")]) == {str(active.id)}


@pytest.mark.asyncio
async def test_bulk_failure_preserves_live_indices_and_is_reported(cluster, db_session):
    db_session.add(News(title="Current", content="Body"))
    await db_session.commit()
    cluster.failed_bulk = True
    with pytest.raises(RuntimeError, match="bulk"):
        await search_indexer.reindex_all()
    assert cluster.documents == {
        "news": {"deleted": {"title": "Stale"}},
        "events": {"inactive": {"title": "Stale"}},
    }
    assert cluster.switches == 0


@pytest.mark.asyncio
async def test_rebuild_replaces_existing_alias_targets(cluster):
    cluster.aliases = {"news": "news-rebuild-old", "events": "events-rebuild-old"}
    for name in ("news", "events"):
        cluster.documents[f"{name}-rebuild-old"] = cluster.documents.pop(name)
        cluster.mappings[f"{name}-rebuild-old"] = cluster.mappings.pop(name)
    await search_indexer.reindex_all()
    assert len(cluster.documents) == 2
    assert all(
        action["remove"].get("must_exist") is True
        for action in cluster.actions
        if "remove" in action
    )
    assert all(
        cluster.documents[cluster.target(name)] == {} for name in ("news", "events")
    )


@pytest.mark.asyncio
async def test_uncertain_alias_switch_never_deletes_potentially_live_indices(cluster):
    switch = cluster.update_aliases

    async def switch_then_timeout(**kwargs):
        await switch(**kwargs)
        raise TimeoutError("response lost after atomic switch")

    cluster.update_aliases = switch_then_timeout
    with pytest.raises(TimeoutError):
        await search_indexer.reindex_all()
    assert cluster.switches == 1
    assert all(cluster.target(name) in cluster.documents for name in ("news", "events"))


@pytest.mark.asyncio
async def test_rebuild_bootstraps_missing_public_names(cluster):
    cluster.documents.clear()
    cluster.mappings.clear()
    await search_indexer.reindex_all()
    assert set(cluster.aliases) == {"news", "events"}
    assert len(cluster.documents) == 2


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_successful_publication(cluster):
    cluster.aliases = {"news": "news-rebuild-old", "events": "events-rebuild-old"}
    for name in ("news", "events"):
        cluster.documents[f"{name}-rebuild-old"] = cluster.documents.pop(name)
        cluster.mappings[f"{name}-rebuild-old"] = cluster.mappings.pop(name)

    async def unavailable(**kwargs):
        raise OSError("cleanup unavailable")

    cluster.delete = unavailable
    assert await search_indexer.reindex_all() == {"news": 0, "events": 0}
    assert cluster.switches == 1
    assert all(
        cluster.documents[cluster.target(name)] == {} for name in ("news", "events")
    )


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_hide_bulk_failure(cluster, db_session):
    db_session.add(News(title="Current", content="Body"))
    await db_session.commit()
    cluster.failed_bulk = True

    async def unavailable(**kwargs):
        raise OSError("cleanup unavailable")

    cluster.delete = unavailable
    with pytest.raises(RuntimeError, match="bulk"):
        await search_indexer.reindex_all()
    assert cluster.switches == 0
    assert cluster.documents["news"] == {"deleted": {"title": "Stale"}}


@pytest.mark.asyncio
async def test_rebuild_rejects_zero_batch_size(cluster):
    with pytest.raises(ValueError, match="batch_size"):
        await search_indexer.reindex_all(batch_size=0)
    assert cluster.switches == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [{"acknowledged": True, "errors": True}, {"acknowledged": False, "errors": False}],
)
async def test_unconfirmed_alias_publication_is_reported(cluster, response):
    async def unconfirmed(**kwargs):
        return response

    cluster.update_aliases = unconfirmed
    with pytest.raises(RuntimeError, match="alias publication"):
        await search_indexer.reindex_all()
    assert cluster.documents["news"] == {"deleted": {"title": "Stale"}}


@pytest.mark.asyncio
async def test_rebuild_preserves_indices_owned_by_other_alias_consumers(cluster):
    for name in ("news", "events"):
        previous = f"curated-{name}-v1"
        cluster.aliases[name] = previous
        cluster.documents[previous] = cluster.documents.pop(name)
        cluster.mappings[previous] = cluster.mappings.pop(name)
    cluster.aliases["archive"] = "curated-news-v1"

    assert await search_indexer.reindex_all() == {"news": 0, "events": 0}

    assert cluster.switches == 1
    assert cluster.documents[cluster.target("archive")] == {
        "deleted": {"title": "Stale"}
    }
    assert cluster.documents["curated-events-v1"] == {"inactive": {"title": "Stale"}}
    for name in ("news", "events"):
        assert cluster.mappings[f"curated-{name}-v1"] == {"obsolete": True}
        assert cluster.target(name).startswith(f"{name}-rebuild-")
        assert cluster.documents[cluster.target(name)] == {}


@pytest.mark.asyncio
async def test_rebuilt_public_names_accept_incremental_content_writes(cluster):
    await search_indexer.reindex_all()
    service = SearchService()
    service._client = cluster
    for name in ("news", "events"):
        document = {"id": f"new-{name}", "title": "Published after rebuild"}
        await service.index_document(name, document["id"], document)
        assert cluster.documents[cluster.target(name)] == {document["id"]: document}


@pytest.mark.asyncio
async def test_reindex_rejects_partial_bulk_counts_without_reported_failures(
    cluster: SearchCluster,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add(News(title="Current", content="Body"))
    await db_session.commit()

    service = search_indexer.build_search_service()

    async def incomplete_success(
        _index: str, documents: list[dict[str, object]]
    ) -> tuple[int, int]:
        assert documents
        return 0, 0

    monkeypatch.setattr(service, "bulk_index", incomplete_success)

    with pytest.raises(RuntimeError, match="bulk"):
        await search_indexer.reindex_all()

    assert cluster.documents == {
        "news": {"deleted": {"title": "Stale"}},
        "events": {"inactive": {"title": "Stale"}},
    }
    assert cluster.mappings == {
        "news": {"obsolete": True},
        "events": {"obsolete": True},
    }
    assert cluster.aliases == {}
    assert cluster.switches == 0
