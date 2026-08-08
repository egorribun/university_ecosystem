from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.vector_ring import NodeConfig, VectorStorageEngine
from app.models.vector_shard import VectorChunk
from app.services.vector_sharding_service import VectorShardingService


class _EmbeddingService:
    def __init__(
        self, value: list[float] | None = None, error: Exception | None = None
    ):
        self.value = value
        self.error = error

    async def get_embedding(self, _text: str) -> list[float]:
        if self.error:
            raise self.error
        return self.value or []


class _UpsertClient:
    def __init__(self, error: Exception | None = None):
        self.calls: list[dict[str, object]] = []
        self.error = error

    def upsert(self, **kwargs: object) -> None:
        if self.error:
            raise self.error
        self.calls.append(kwargs)


class _InsertClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def insert(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


class _DbSession:
    def __init__(self, rows: list[VectorChunk] | None = None):
        self.rows = rows or []
        self.added: list[VectorChunk] = []
        self.flushed = False

    def add(self, item: VectorChunk) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed = True

    async def execute(self, _statement: object) -> object:
        rows = self.rows or self.added

        class _Result:
            def scalars(self) -> _Result:
                return self

            def all(self) -> list[VectorChunk]:
                return rows

        return _Result()


class _RedisSetex:
    def __init__(self, value: object = None, error: Exception | None = None):
        self.value = value
        self.error = error
        self.store: dict[str, bytes] = {}

    def setex(self, key: str, _ttl: int, value: bytes) -> None:
        if self.error:
            raise self.error
        self.store[key] = value

    def get(self, _key: str) -> object:
        if self.error:
            raise self.error
        return self.value


class _RedisSet:
    def __init__(self, value: object):
        self.value = value
        self.calls: list[tuple[str, bytes]] = []

    async def set(self, key: str, value: bytes) -> None:
        self.calls.append((key, value))

    async def get(self, _key: str) -> object:
        return self.value


class _RedisAsyncSetex(_RedisSetex):
    async def setex(self, key: str, _ttl: int, value: bytes) -> None:
        self.store[key] = value


class _RedisSyncSet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def set(self, key: str, value: bytes) -> None:
        self.calls.append((key, value))


class _NatsPublish:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.events: list[tuple[str, bytes]] = []

    def publish(self, subject: str, payload: bytes) -> None:
        if self.error:
            raise self.error
        self.events.append((subject, payload))


class _JetStream:
    def __init__(self):
        self.events: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.events.append((subject, payload))


class _NatsJetStream:
    def __init__(self) -> None:
        self.stream = _JetStream()

    def js(self) -> _JetStream:
        return self.stream


@pytest.mark.asyncio
async def test_chunking_and_embedding_fallback_edges() -> None:
    service = VectorShardingService(chunk_size=2, overlap=2, embedding_dim=4)

    assert service.chunk_text("   ") == []
    chunks = service.chunk_text("one two three four five")
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert service.chunk_text("") == []
    assert await service.generate_embeddings_batch([], batch_size=1) == []
    assert service.generate_deterministic_embedding("") == [0.0] * 4

    valid = VectorShardingService(
        vector_service=_EmbeddingService([1.0, 2.0, 3.0, 4.0]),
        embedding_dim=4,
    )
    assert await valid.get_embedding("valid") == [1.0, 2.0, 3.0, 4.0]

    invalid = VectorShardingService(
        vector_service=_EmbeddingService([0.0, 0.0, 0.0, 0.0]),
        embedding_dim=4,
    )
    fallback = await invalid.get_embedding("invalid")
    assert len(fallback) == 4
    assert sum(value * value for value in fallback) > 0

    failing = VectorShardingService(
        vector_service=_EmbeddingService(error=TimeoutError("vector service down")),
        embedding_dim=4,
    )
    assert len(await failing.get_embedding("failing")) == 4
    zero_dim = VectorShardingService(embedding_dim=0)
    assert await zero_dim.get_embedding("zero") == []
    wide = VectorShardingService(embedding_dim=64)
    assert len(wide.generate_deterministic_embedding("wide")) == 64


@pytest.mark.asyncio
async def test_ingestion_empty_and_upsert_failure_paths() -> None:
    engine = VectorStorageEngine()
    node = engine.register_node("node-a", "http://node-a:6333")
    client = _UpsertClient(error=ConnectionError("qdrant unavailable"))
    node._client = client
    service = VectorShardingService(
        storage_engine=engine, embedding_dim=4, chunk_size=10
    )

    assert await service.ingest_document(str(uuid.uuid4()), "empty", "") == []
    chunks = await service.ingest_document(
        str(uuid.uuid4()), "document", "one two", metadata={"kind": "unit"}
    )
    assert len(chunks) == 1
    assert client.calls == []

    success_client = _UpsertClient()
    node._client = success_client
    db = _DbSession()
    chunks = await service.ingest_document(
        uuid.uuid4(),
        "document-2",
        "one two",
        db_session=db,
        collection_name="course_vectors",
    )
    assert len(chunks) == 1
    assert db.flushed is True
    assert len(success_client.calls) == 1
    assert success_client.calls[0]["collection_name"] == "course_vectors"

    no_target = VectorShardingService(embedding_dim=4, chunk_size=10)
    assert await no_target.ingest_document(uuid.uuid4(), "no-target", "one two")

    insert_client = _InsertClient()
    node._client = insert_client
    await service.ingest_document(uuid.uuid4(), "insert", "one two")
    assert len(insert_client.calls) == 1


@pytest.mark.asyncio
async def test_progress_supports_setex_set_bytes_dict_and_local_fallback() -> None:
    setex = _RedisSetex()
    service = VectorShardingService(redis_client=setex)
    data = await service._update_progress(
        "reb-1", 1, 2, "IN_PROGRESS", {"phase": "scan"}
    )
    assert data["percentage"] == 50.0
    assert setex.store
    assert await service.get_rebalance_progress("reb-1") == data

    set_client = _RedisSet(b'{"status":"REMOTE"}')
    service = VectorShardingService(redis_client=set_client)
    await service._update_progress("reb-2", 0, 0, "COMPLETED")
    assert set_client.calls
    assert (await service.get_rebalance_progress("reb-2"))["status"] == "REMOTE"

    dict_client = _RedisSet({"status": "DICT"})
    service = VectorShardingService(redis_client=dict_client)
    assert (await service.get_rebalance_progress("reb-3"))["status"] == "DICT"

    unknown_client = _RedisSet(123)
    service = VectorShardingService(redis_client=unknown_client)
    await service._update_progress("reb-unknown", 0, 0, "LOCAL")
    assert (await service.get_rebalance_progress("reb-unknown"))["status"] == "LOCAL"

    local_only = VectorShardingService(redis_client=SimpleNamespace())
    await local_only._update_progress("reb-4", 0, 0, "LOCAL")
    assert (await local_only.get_rebalance_progress("reb-4"))["status"] == "LOCAL"

    async_setex = _RedisAsyncSetex()
    await VectorShardingService(redis_client=async_setex)._update_progress(
        "reb-async", 1, 1, "COMPLETED"
    )
    sync_set = _RedisSyncSet()
    await VectorShardingService(redis_client=sync_set)._update_progress(
        "reb-sync", 1, 1, "COMPLETED"
    )
    assert sync_set.calls


@pytest.mark.asyncio
async def test_progress_and_publish_network_errors_are_non_fatal() -> None:
    service = VectorShardingService(
        redis_client=_RedisSetex(error=ConnectionError("redis down")),
        nats_client=_NatsPublish(error=OSError("nats down")),
    )
    await service._update_progress("reb", 0, 0, "FAILED")
    await service.publish_jetstream_event("vector.test", {"ok": False})
    assert await service.get_rebalance_progress("reb")

    service = VectorShardingService(nats_client=_NatsJetStream())
    await service.publish_jetstream_event("vector.test", {"ok": True})
    assert service.nats_client.stream.events
    await VectorShardingService().publish_jetstream_event("vector.test", {})


@pytest.mark.asyncio
async def test_rebalance_registers_nodeconfig_and_migrates_upsert_batches() -> None:
    engine = VectorStorageEngine()
    nats = _NatsPublish()
    service = VectorShardingService(storage_engine=engine, nats_client=nats)
    node = NodeConfig("node-new", "http://node-new:6333")
    client = _UpsertClient()
    node._client = client
    rows = [
        VectorChunk(
            tenant_id=uuid.uuid4(),
            document_id=f"doc-{index}",
            content=f"content-{index}",
            embedding=[0.1, 0.2],
            payload=None,
            chunk_index=index,
            is_active=True,
        )
        for index in range(10)
    ]
    db = _DbSession(rows)

    result = await service.rebalance_node_ring(
        [node],
        target_collection="course_vectors",
        db_session=db,
        rebalance_id="reb-batch",
    )

    assert result == {
        "rebalance_id": "reb-batch",
        "migrated_keys": 10,
        "total_keys": 10,
        "percentage": 100.0,
        "status": "COMPLETED",
    }
    assert len(client.calls) == 10
    assert len(nats.events) == 3

    string_engine = VectorStorageEngine()
    string_node = string_engine.register_node("placeholder", "http://placeholder")
    string_node._client = _InsertClient()
    string_service = VectorShardingService(storage_engine=string_engine)
    await string_service.rebalance_node_ring(["node-string"], rebalance_id="reb-string")
    assert "node-string" in string_engine.ring.nodes

    # The public type is stricter, but malformed runtime input must not abort the
    # entire rebalancing operation.
    await string_service.rebalance_node_ring([42], rebalance_id="reb-invalid")  # type: ignore[list-item]


@pytest.mark.asyncio
async def test_rebalance_without_database_and_migration_errors_completes() -> None:
    service = VectorShardingService(nats_client=_NatsJetStream())
    empty = await service.rebalance_node_ring([], rebalance_id="reb-empty")
    assert empty["status"] == "COMPLETED"
    assert empty["total_keys"] == 0

    engine = VectorStorageEngine()
    node = engine.register_node("node-error", "http://node-error:6333")
    node._client = _UpsertClient(error=OSError("write failed"))
    service = VectorShardingService(storage_engine=engine)
    db = _DbSession(
        [
            VectorChunk(
                tenant_id=uuid.uuid4(),
                document_id="doc-error",
                content="content",
                embedding=[0.1, 0.2],
                payload={"kind": "error"},
                chunk_index=0,
                is_active=True,
            )
        ]
    )
    result = await service.rebalance_node_ring(
        [], db_session=db, rebalance_id="reb-error"
    )
    assert result["migrated_keys"] == 1

    insert_engine = VectorStorageEngine()
    insert_node = insert_engine.register_node("node-insert", "http://node-insert:6333")
    insert_client = _InsertClient()
    insert_node._client = insert_client
    insert_service = VectorShardingService(storage_engine=insert_engine)
    insert_db = _DbSession(
        [
            VectorChunk(
                tenant_id=uuid.uuid4(),
                document_id="doc-insert",
                content="content",
                embedding=[0.1, 0.2],
                payload=None,
                chunk_index=0,
                is_active=True,
            )
        ]
    )
    await insert_service.rebalance_node_ring(
        [], db_session=insert_db, rebalance_id="reb-insert"
    )
    assert len(insert_client.calls) == 1
