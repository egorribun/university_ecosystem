from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError as RedisResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

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


class _RedisLegacySetAndSetex:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, bytes]] = []
        self.setex_calls: list[tuple[str, int, bytes]] = []

    def set(self, key: str, value: bytes) -> None:
        self.set_calls.append((key, value))

    def setex(self, key: str, ttl: int, value: bytes) -> None:
        self.setex_calls.append((key, ttl, value))


class _RedisSetOnly:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def set(self, key: str, value: bytes) -> None:
        self.calls.append((key, value))


class _RedisAsyncSetOnly:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    async def set(self, key: str, value: bytes) -> None:
        self.calls.append((key, value))


class _RedisVariadicExSetAndSetex:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, bytes, tuple[int, ...]]] = []
        self.setex_calls: list[tuple[str, int, bytes]] = []

    def set(self, key: str, value: bytes, *ex: int) -> None:
        self.set_calls.append((key, value, ex))

    def setex(self, key: str, ttl: int, value: bytes) -> None:
        self.setex_calls.append((key, ttl, value))


class _RedisVariadicExSetOnly:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, tuple[int, ...]]] = []

    def set(self, key: str, value: bytes, *ex: int) -> None:
        self.calls.append((key, value, ex))


class _RedisKwargsSet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, int]]] = []

    def set(self, key: str, value: bytes, **kwargs: int) -> None:
        self.calls.append((key, value, kwargs))


class _RedisPositionalOnlySet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, int]] = []

    def set(self, key: str, value: bytes, ex: int, /) -> None:
        self.calls.append((key, value, ex))


class _RedisAsyncPositionalOnlySet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, int]] = []

    async def set(self, key: str, value: bytes, ex: int, /) -> None:
        self.calls.append((key, value, ex))


class _RedisPositionalOnlySetWithOptionalArgument:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str, int]] = []

    def set(
        self, key: str, value: bytes, mode: str = "default", ex: int = 0, /
    ) -> None:
        self.calls.append((key, value, mode, ex))


class _RedisUninspectableSetCallable:
    def __init__(self, calls: list[tuple[str, bytes, int | None]]) -> None:
        self.calls = calls

    @property
    def __signature__(self) -> object:
        raise ValueError("signature unavailable")

    def __call__(self, key: str, value: bytes, *, ex: int | None = None) -> None:
        self.calls.append((key, value, ex))


class _RedisUninspectableSet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, int | None]] = []
        self.set = _RedisUninspectableSetCallable(self.calls)


class _RedisUninspectableSetAndSetex:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, bytes, int | None]] = []
        self.setex_calls: list[tuple[str, int, bytes]] = []
        self.set = _RedisUninspectableSetCallable(self.set_calls)

    def setex(self, key: str, ttl: int, value: bytes) -> None:
        self.setex_calls.append((key, ttl, value))


class _RedisAsyncUninspectableSetCallable:
    def __init__(self, calls: list[tuple[str, bytes, int | None]]) -> None:
        self.calls = calls

    @property
    def __signature__(self) -> object:
        raise ValueError("signature unavailable")

    async def __call__(self, key: str, value: bytes, *, ex: int | None = None) -> None:
        self.calls.append((key, value, ex))


class _RedisAsyncUninspectableSet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, int | None]] = []
        self.set = _RedisAsyncUninspectableSetCallable(self.calls)


class _RedisUnsupportedPositionalSet:
    def __init__(self) -> None:
        self.calls = 0

    def set(self, key: str, value: bytes, required: object, ex: int, /) -> None:
        self.calls += 1


class _RedisExpiryBeforeValueSet:
    def __init__(self) -> None:
        self.calls = 0

    def set(self, key: str, ex: int, /) -> None:
        self.calls += 1


class _RedisSetFailureWithSetex:
    def __init__(self, error: Exception | None = None) -> None:
        self.setex_calls = 0
        self.error = error or RuntimeError("SET EX failed")

    def set(self, _key: str, _value: bytes, ex: int) -> None:
        raise self.error

    def setex(self, _key: str, _ttl: int, _value: bytes) -> None:
        self.setex_calls += 1


class _RedisSet:
    def __init__(self, value: object):
        self.value = value
        self.calls: list[tuple[str, bytes, int | None]] = []

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.calls.append((key, value, ex))

    async def get(self, _key: str) -> object:
        return self.value


class _RedisAsyncSetex(_RedisSetex):
    async def setex(self, key: str, _ttl: int, value: bytes) -> None:
        self.store[key] = value


class _RedisSyncSet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, int | None]] = []

    def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.calls.append((key, value, ex))


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


class _NatsNoJetStream:
    def js(self) -> None:
        return None


class _SyncJetStream:
    def __init__(self) -> None:
        self.events: list[tuple[str, bytes]] = []

    def publish(self, subject: str, payload: bytes) -> None:
        self.events.append((subject, payload))


class _NatsSyncJetStream:
    def __init__(self) -> None:
        self.stream = _SyncJetStream()

    def js(self) -> _SyncJetStream:
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
async def test_ingestion_skips_unknown_vector_client_without_insert_or_upsert() -> None:
    engine = VectorStorageEngine()
    node = engine.register_node("node-unknown", "http://node-unknown:6333")
    node._client = SimpleNamespace()
    service = VectorShardingService(storage_engine=engine, embedding_dim=4)
    db = _DbSession()

    chunks = await service.ingest_document(
        uuid.uuid4(), "document-unknown-client", "one two", db_session=db
    )

    assert len(chunks) == 1
    assert db.added == chunks
    assert db.flushed is True


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
    assert set_client.calls[0][2] == 3600
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
async def test_progress_reads_local_store_without_redis_client() -> None:
    service = VectorShardingService()

    written = await service._update_progress("reb-local-only", 1, 2, "IN_PROGRESS")

    assert await service.get_rebalance_progress("reb-local-only") == written


@pytest.mark.asyncio
async def test_progress_uses_legacy_setex_when_set_does_not_accept_expiry() -> None:
    redis = _RedisLegacySetAndSetex()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-legacy", 1, 2, "IN_PROGRESS"
    )

    assert redis.set_calls == []
    assert len(redis.setex_calls) == 1
    key, ttl, payload = redis.setex_calls[0]
    assert key == "vector_sharding:rebalance:reb-legacy"
    assert ttl == 3600
    assert b'"status":"IN_PROGRESS"' in payload


@pytest.mark.asyncio
async def test_progress_preserves_legacy_set_only_client() -> None:
    redis = _RedisSetOnly()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-set-only", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    key, payload = redis.calls[0]
    assert key == "vector_sharding:rebalance:reb-set-only"
    assert b'"status":"IN_PROGRESS"' in payload


@pytest.mark.asyncio
async def test_progress_uses_setex_when_set_ex_is_variadic_positional() -> None:
    redis = _RedisVariadicExSetAndSetex()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-variadic-setex", 1, 2, "IN_PROGRESS"
    )

    assert redis.set_calls == []
    assert len(redis.setex_calls) == 1
    key, ttl, payload = redis.setex_calls[0]
    assert key == "vector_sharding:rebalance:reb-variadic-setex"
    assert ttl == 3600
    assert b'"status":"IN_PROGRESS"' in payload


@pytest.mark.asyncio
async def test_progress_uses_safe_set_only_call_for_variadic_ex() -> None:
    redis = _RedisVariadicExSetOnly()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-variadic-set-only", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    key, payload, extra_positional = redis.calls[0]
    assert key == "vector_sharding:rebalance:reb-variadic-set-only"
    assert b'"status":"IN_PROGRESS"' in payload
    assert extra_positional == ()


@pytest.mark.asyncio
async def test_progress_awaits_legacy_set_only_client() -> None:
    redis = _RedisAsyncSetOnly()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-set-only-async", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    assert redis.calls[0][0] == "vector_sharding:rebalance:reb-set-only-async"


@pytest.mark.asyncio
async def test_progress_uses_set_ex_when_set_accepts_extra_keywords() -> None:
    redis = _RedisKwargsSet()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-kwargs", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    key, payload, kwargs = redis.calls[0]
    assert key == "vector_sharding:rebalance:reb-kwargs"
    assert b'"status":"IN_PROGRESS"' in payload
    assert kwargs == {"ex": 3600}


@pytest.mark.asyncio
async def test_progress_uses_positional_only_set_expiry() -> None:
    redis = _RedisPositionalOnlySet()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-positional", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    key, payload, ttl = redis.calls[0]
    assert key == "vector_sharding:rebalance:reb-positional"
    assert b'"status":"IN_PROGRESS"' in payload
    assert ttl == 3600


@pytest.mark.asyncio
async def test_progress_awaits_positional_only_set_expiry() -> None:
    redis = _RedisAsyncPositionalOnlySet()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-positional-async", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    assert redis.calls[0][2] == 3600


@pytest.mark.asyncio
async def test_progress_preserves_defaults_before_positional_only_expiry() -> None:
    redis = _RedisPositionalOnlySetWithOptionalArgument()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-positional-default", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    key, payload, mode, ttl = redis.calls[0]
    assert key == "vector_sharding:rebalance:reb-positional-default"
    assert b'"status":"IN_PROGRESS"' in payload
    assert mode == "default"
    assert ttl == 3600


@pytest.mark.asyncio
async def test_progress_preserves_uninspectable_set_only_two_argument_fallback() -> (
    None
):
    redis = _RedisUninspectableSet()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-uninspectable", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    key, payload, ttl = redis.calls[0]
    assert key == "vector_sharding:rebalance:reb-uninspectable"
    assert b'"status":"IN_PROGRESS"' in payload
    assert ttl is None


@pytest.mark.asyncio
async def test_progress_uses_setex_when_set_signature_is_unavailable() -> None:
    redis = _RedisUninspectableSetAndSetex()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-uninspectable-setex", 1, 2, "IN_PROGRESS"
    )

    assert redis.set_calls == []
    assert len(redis.setex_calls) == 1
    key, ttl, payload = redis.setex_calls[0]
    assert key == "vector_sharding:rebalance:reb-uninspectable-setex"
    assert ttl == 3600
    assert b'"status":"IN_PROGRESS"' in payload


@pytest.mark.asyncio
async def test_progress_awaits_uninspectable_set_only_two_argument_fallback() -> None:
    redis = _RedisAsyncUninspectableSet()

    await VectorShardingService(redis_client=redis)._update_progress(
        "reb-uninspectable-async", 1, 2, "IN_PROGRESS"
    )

    assert len(redis.calls) == 1
    assert redis.calls[0][2] is None


@pytest.mark.asyncio
async def test_progress_rejects_unsupported_positional_expiry_signature() -> None:
    redis = _RedisUnsupportedPositionalSet()

    with pytest.raises(TypeError, match="unsupported positional-only ex"):
        await VectorShardingService(redis_client=redis)._update_progress(
            "reb-positional-invalid", 1, 2, "IN_PROGRESS"
        )

    assert redis.calls == 0


@pytest.mark.asyncio
async def test_progress_rejects_positional_expiry_before_value() -> None:
    redis = _RedisExpiryBeforeValueSet()

    with pytest.raises(TypeError, match="unsupported positional-only ex"):
        await VectorShardingService(redis_client=redis)._update_progress(
            "reb-positional-order", 1, 2, "IN_PROGRESS"
        )

    assert redis.calls == 0


@pytest.mark.asyncio
async def test_progress_does_not_fallback_after_supported_set_fails() -> None:
    redis = _RedisSetFailureWithSetex()

    with pytest.raises(RuntimeError, match="SET EX failed"):
        await VectorShardingService(redis_client=redis)._update_progress(
            "reb-set-failure", 1, 2, "IN_PROGRESS"
        )

    assert redis.setex_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "redis_error", [RedisConnectionError("offline"), RedisTimeoutError("timeout")]
)
async def test_progress_treats_redis_transport_errors_as_non_fatal(
    redis_error: Exception,
) -> None:
    redis = _RedisSetFailureWithSetex(redis_error)

    data = await VectorShardingService(redis_client=redis)._update_progress(
        "reb-redis-transport", 1, 2, "IN_PROGRESS"
    )

    assert data["status"] == "IN_PROGRESS"
    assert redis.setex_calls == 0


@pytest.mark.asyncio
async def test_progress_does_not_swallow_redis_command_errors() -> None:
    redis = _RedisSetFailureWithSetex(RedisResponseError("WRONGTYPE"))

    with pytest.raises(RedisResponseError, match="WRONGTYPE"):
        await VectorShardingService(redis_client=redis)._update_progress(
            "reb-redis-command", 1, 2, "IN_PROGRESS"
        )

    assert redis.setex_calls == 0


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
async def test_publish_skips_when_jetstream_is_unavailable() -> None:
    await VectorShardingService(nats_client=_NatsNoJetStream()).publish_jetstream_event(
        "vector.test", {"ok": True}
    )


@pytest.mark.asyncio
async def test_publish_supports_synchronous_jetstream_client() -> None:
    nats = _NatsSyncJetStream()

    await VectorShardingService(nats_client=nats).publish_jetstream_event(
        "vector.test", {"ok": True}
    )

    assert len(nats.stream.events) == 1
    assert nats.stream.events[0][0] == "vector.test"


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


@pytest.mark.asyncio
async def test_rebalance_skips_unknown_vector_client_methods() -> None:
    engine = VectorStorageEngine()
    node = engine.register_node("node-unknown", "http://node-unknown:6333")
    node._client = SimpleNamespace()
    service = VectorShardingService(storage_engine=engine)
    db = _DbSession(
        [
            VectorChunk(
                tenant_id=uuid.uuid4(),
                document_id="doc-unknown-client",
                content="content",
                embedding=[0.1, 0.2],
                payload=None,
                chunk_index=0,
                is_active=True,
            )
        ]
    )

    result = await service.rebalance_node_ring(
        [], db_session=db, rebalance_id="reb-unknown-client"
    )

    assert result["migrated_keys"] == 1
    assert result["status"] == "COMPLETED"
