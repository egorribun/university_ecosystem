from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core.vector_ring as vector_ring
from app.core.vector_ring import (
    ConsistentHashRing,
    NodeConfig,
    NodeStatus,
    VectorPartitionConfig,
    VectorStorageEngine,
    hash_key,
)


class _FakeQdrantClient:
    def __init__(
        self, hits: list[object] | None = None, error: Exception | None = None
    ):
        self.hits = hits or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> list[object]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.hits


class _FakeResult:
    def __init__(self, rows: list[tuple[object, float]]):
        self.rows = rows

    def all(self) -> list[tuple[object, float]]:
        return self.rows


class _FakeDbSession:
    def __init__(
        self,
        rows: list[tuple[object, float]] | None = None,
        error: Exception | None = None,
    ):
        self.rows = rows or []
        self.error = error
        self.statement: object | None = None

    async def execute(self, statement: object) -> _FakeResult:
        self.statement = statement
        if self.error:
            raise self.error
        return _FakeResult(self.rows)


class _FalseVnode:
    def __bool__(self) -> bool:
        return False

    def startswith(self, _prefix: str) -> bool:
        return True


def _hit(vector_id: str, score: float, tenant_id: str = "tenant-1") -> object:
    return SimpleNamespace(
        id=vector_id,
        score=score,
        payload={"tenant_id": tenant_id, "kind": "test"},
    )


def _row(
    vector_id: str,
    score: float,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[object, float]:
    return (
        SimpleNamespace(
            id=vector_id,
            tenant_id="tenant-1",
            payload=payload,
            content=f"content-{vector_id}",
        ),
        score,
    )


def test_ring_lifecycle_health_and_replication_routing() -> None:
    ring = ConsistentHashRing(vnodes_per_node=2)
    assert hash_key("tenant-1") == hash_key("tenant-1")
    assert ring.get_node_id("tenant-1") is None
    assert ring.get_node("tenant-1") is None
    assert ring.get_healthy_node("tenant-1") is None
    assert ring.get_nodes_for_key("tenant-1", 3) == []

    first = NodeConfig("qdrant-a", "http://a", weight=2)
    second = NodeConfig("qdrant-b", "http://b", status=NodeStatus.DEGRADED)
    assert first.to_dict() == {
        "node_id": "qdrant-a",
        "endpoint": "http://a",
        "weight": 2,
        "status": "healthy",
    }

    ring.add_node(first)
    ring.add_node(second)
    assert ring.get_node("tenant-1") in {first, second}
    assert ring.get_nodes_for_key("tenant-1", 0) == []
    assert ring.get_nodes_for_key("tenant-1", 3) == [first, second]
    assert ring.get_healthy_node("tenant-1") is first

    ring.update_node_status("qdrant-a", NodeStatus.DOWN)
    assert ring.get_healthy_node("tenant-1") is None
    ring.update_node_status("missing", NodeStatus.HEALTHY)
    assert ring.get_all_nodes() == [first, second]

    ring.remove_node("missing")
    ring.remove_node("qdrant-a")
    assert ring.get_node("tenant-1") is second
    ring.remove_node("qdrant-b")
    assert ring.get_all_nodes() == []


def test_ring_removal_handles_missing_virtual_node_entries() -> None:
    ring = ConsistentHashRing(vnodes_per_node=1)
    node = NodeConfig("qdrant-a", "http://a")
    ring.add_node(node)
    hash_value = ring.sorted_keys[0]
    ring.ring[hash_value] = _FalseVnode()  # type: ignore[assignment]
    ring.remove_node("qdrant-a")
    assert ring.get_all_nodes() == []


def test_qdrant_dependency_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def import_without_qdrant(name: str, *args: object, **kwargs: object) -> object:
        if name == "qdrant_client":
            raise ModuleNotFoundError("qdrant-client is optional in this test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_qdrant)
    source_path = Path(vector_ring.__file__)
    spec = importlib.util.spec_from_file_location(
        "vector_ring_without_qdrant", source_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.HAS_QDRANT_CLIENT is False


def test_ring_lookup_wraps_after_the_last_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ring = ConsistentHashRing(vnodes_per_node=1)
    node = NodeConfig("qdrant-a", "http://a")
    ring.add_node(node)
    monkeypatch.setattr(vector_ring, "hash_key", lambda _key: 2**64 - 1)

    assert ring.get_node_id("tenant-1") == "qdrant-a"


def test_partition_config_serializes_all_storage_options() -> None:
    config = VectorPartitionConfig(
        collection_name="course_vectors",
        dimensions=768,
        distance_metric="Dot",
        hnsw_m=32,
        hnsw_ef_construct=128,
        shard_number=8,
        replication_factor=3,
        write_consistency_factor=2,
        on_disk_payload=False,
        pgvector_fallback_enabled=False,
        pgvector_table_name="course_chunks",
    )

    assert config.to_dict() == {
        "collection_name": "course_vectors",
        "dimensions": 768,
        "distance_metric": "Dot",
        "hnsw_m": 32,
        "hnsw_ef_construct": 128,
        "shard_number": 8,
        "replication_factor": 3,
        "write_consistency_factor": 2,
        "on_disk_payload": False,
        "pgvector_fallback_enabled": False,
        "pgvector_table_name": "course_chunks",
    }


def test_engine_registration_and_fallback_state() -> None:
    engine = VectorStorageEngine()
    assert engine.get_target_node("tenant-1") is None
    assert engine.should_fallback_to_pgvector("tenant-1") is True

    node = engine.register_node("qdrant-a", "http://a", status=NodeStatus.HEALTHY)
    assert engine.get_target_node("tenant-1") is node
    assert engine.should_fallback_to_pgvector("tenant-1") is False
    engine.unregister_node("qdrant-a")
    assert engine.get_target_node("tenant-1") is None


@pytest.mark.asyncio
async def test_search_uses_qdrant_and_serializes_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vector_ring, "HAS_QDRANT_CLIENT", True)
    engine = VectorStorageEngine()
    node = engine.register_node("qdrant-a", "http://a")
    client = _FakeQdrantClient([_hit("v-1", 0.91)])
    node._client = client

    results = await engine.search("tenant-1", [0.1, 0.2], top_k=2, score_threshold=0.4)

    assert results[0]._asdict() == {
        "vector_id": "v-1",
        "tenant_id": "tenant-1",
        "score": 0.91,
        "payload": {"tenant_id": "tenant-1", "kind": "test"},
        "source_tier": "qdrant",
        "node_id": "qdrant-a",
    }
    assert client.calls == [
        {
            "collection_name": "learning_materials",
            "query_vector": [0.1, 0.2],
            "limit": 2,
            "score_threshold": 0.4,
        }
    ]


@pytest.mark.asyncio
async def test_search_marks_failed_qdrant_node_and_uses_pgvector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vector_ring, "HAS_QDRANT_CLIENT", True)
    engine = VectorStorageEngine()
    node = engine.register_node("qdrant-a", "http://a")
    node._client = _FakeQdrantClient(error=ConnectionError("offline"))
    db = _FakeDbSession(
        [_row("pg-1", 0.87), _row("pg-2", 0.72, payload={"title": "x"})]
    )

    results = await engine.search("tenant-1", [0.1], db_session=db)

    assert [result.vector_id for result in results] == ["pg-1", "pg-2"]
    assert results[0].payload == {"content": "content-pg-1"}
    assert results[1].payload == {"title": "x"}
    assert all(result.source_tier == "pgvector" for result in results)
    assert node.status is NodeStatus.DEGRADED
    assert db.statement is not None


@pytest.mark.asyncio
async def test_search_returns_empty_when_qdrant_and_fallback_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = VectorStorageEngine()
    node = engine.register_node("qdrant-a", "http://a")

    monkeypatch.setattr(vector_ring, "HAS_QDRANT_CLIENT", True)
    node._client = None
    fallback_results = await engine.search(
        "tenant-1",
        [0.1],
        db_session=_FakeDbSession([_row("pg-1", 0.5)]),
    )
    assert [result.vector_id for result in fallback_results] == ["pg-1"]

    monkeypatch.setattr(vector_ring, "HAS_QDRANT_CLIENT", False)
    assert await engine.search("tenant-1", [0.1]) == []


@pytest.mark.asyncio
async def test_qdrant_query_returns_none_without_client_and_rethrows_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = VectorStorageEngine()
    node = NodeConfig("qdrant-a", "http://a")
    config = VectorPartitionConfig()
    monkeypatch.setattr(vector_ring, "HAS_QDRANT_CLIENT", False)
    assert await engine._query_qdrant(node, config, [0.1], 1, 0.0) is None

    monkeypatch.setattr(vector_ring, "HAS_QDRANT_CLIENT", True)
    assert await engine._query_qdrant(node, config, [0.1], 1, 0.0) is None
    node._client = _FakeQdrantClient(error=TimeoutError("timeout"))
    with pytest.raises(TimeoutError, match="timeout"):
        await engine._query_qdrant(node, config, [0.1], 1, 0.0)


@pytest.mark.asyncio
async def test_pgvector_query_returns_empty_on_database_network_error() -> None:
    engine = VectorStorageEngine()
    db = _FakeDbSession(error=ConnectionError("database down"))

    assert await engine._query_pgvector(db, "tenant-1", [0.1], 5, 0.0) == []


@pytest.mark.asyncio
async def test_scatter_gather_merges_top_k_and_skips_failed_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vector_ring, "HAS_QDRANT_CLIENT", True)
    engine = VectorStorageEngine()
    first = engine.register_node("qdrant-a", "http://a")
    second = engine.register_node("qdrant-b", "http://b")
    failed = engine.register_node("qdrant-c", "http://c")
    empty = engine.register_node("qdrant-d", "http://d")
    first._client = _FakeQdrantClient([_hit("a-high", 0.95), _hit("a-low", 0.40)])
    second._client = _FakeQdrantClient([_hit("b-high", 0.90), _hit("b-low", 0.80)])
    failed._client = _FakeQdrantClient(error=OSError("unreachable"))
    empty._client = _FakeQdrantClient()

    results = await engine.scatter_gather_search([0.1], top_k=2)

    assert [result.vector_id for result in results] == ["a-high", "b-high"]


@pytest.mark.asyncio
async def test_scatter_gather_uses_pgvector_when_all_nodes_are_unhealthy() -> None:
    engine = VectorStorageEngine()
    node = engine.register_node("qdrant-a", "http://a", status=NodeStatus.DOWN)
    assert node.status is NodeStatus.DOWN
    db = _FakeDbSession([_row("pg-1", 0.88)])

    results = await engine.scatter_gather_search([0.1], top_k=3, db_session=db)

    assert [result.vector_id for result in results] == ["pg-1"]
    assert results[0].source_tier == "pgvector"
    assert db.statement is not None


@pytest.mark.asyncio
async def test_scatter_gather_returns_empty_on_pgvector_error_and_empty_ring() -> None:
    engine = VectorStorageEngine()
    db = _FakeDbSession(error=OSError("database down"))

    assert await engine.scatter_gather_search([0.1], db_session=db) == []
    assert await engine.scatter_gather_search([0.1]) == []
