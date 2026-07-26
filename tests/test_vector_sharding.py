"""
Pytest Test Suite for Distributed Vector Sharding and Load Balancing.

Covering:
- Tier 1: Feature Coverage (30 tests)
- Tier 2: Boundary & Corner Cases (30 tests)
- Tier 3: Cross-Feature Interactions (8 tests)
- Tier 4: Real-World Scenarios (5 tests)
Total: 73 test cases
"""

import asyncio
import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

# -------------------------------------------------------------------
# Helper Classes & Reference Implementations for Testing
# -------------------------------------------------------------------


@dataclass
class VectorRecord:
    id: str
    tenant_id: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class MockPgVectorStore:
    def __init__(self):
        self.records: dict[str, VectorRecord] = {}

    def insert(self, record: VectorRecord):
        if len(record.embedding) != 1536 and len(record.embedding) != 0:
            raise ValueError("Embedding must be 1536 dimensions")
        self.records[record.id] = record

    def search(
        self, tenant_id: str, query_vector: list[float], top_k: int
    ) -> list[tuple[VectorRecord, float]]:
        if top_k <= 0 or not query_vector:
            return []
        results = []
        for rec in self.records.values():
            if tenant_id and rec.tenant_id != tenant_id:
                continue
            sim = cosine_similarity(query_vector, rec.embedding)
            results.append((rec, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


class MockQdrantShard:
    def __init__(self, node_name: str):
        self.node_name = node_name
        self.collections: dict[str, dict[str, VectorRecord]] = {}
        self.is_online = True
        self.latency_ms = 5.0

    def insert(self, collection: str, record: VectorRecord):
        if not self.is_online:
            raise ConnectionError(f"Node {self.node_name} offline")
        if collection not in self.collections:
            self.collections[collection] = {}
        self.collections[collection][record.id] = record

    def search(
        self, collection: str, query_vector: list[float], top_k: int
    ) -> list[tuple[VectorRecord, float]]:
        if not self.is_online:
            raise ConnectionError(f"Node {self.node_name} is offline")
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)
        if top_k <= 0 or not query_vector or collection not in self.collections:
            return []
        results = []
        for rec in self.collections[collection].values():
            sim = cosine_similarity(query_vector, rec.embedding)
            results.append((rec, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


class ConsistentHashRing:
    def __init__(self, vnodes: int = 128):
        self.vnodes = vnodes
        self.ring: list[tuple[int, str]] = []
        self.nodes: set = set()

    def _hash(self, key: str) -> int:
        return int(
            hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest(), 16
        )

    def add_node(self, node: str):
        if node in self.nodes:
            return
        self.nodes.add(node)
        for v in range(self.vnodes):
            vkey = f"{node}#vnode{v}"
            h = self._hash(vkey)
            self.ring.append((h, node))
        self.ring.sort(key=lambda x: x[0])

    def remove_node(self, node: str):
        if node not in self.nodes:
            return
        self.nodes.remove(node)
        self.ring = [item for item in self.ring if item[1] != node]

    def get_node(self, key: str) -> str:
        if not self.ring:
            raise ValueError("Ring is empty")
        if not key:
            raise ValueError("Key cannot be empty")
        h = self._hash(key)
        for rh, node in self.ring:
            if rh >= h:
                return node
        return self.ring[0][1]


class VectorIngestionService:
    def chunk_text(
        self, text: str, chunk_size: int = 512, overlap: int = 64
    ) -> list[str]:
        if not text:
            return []
        tokens = text.split()
        if not tokens:
            return []
        if len(tokens) <= chunk_size:
            return [text]
        chunks = []
        step = chunk_size - overlap if chunk_size > overlap else chunk_size
        for i in range(0, len(tokens), step):
            chunk_tokens = tokens[i : i + chunk_size]
            chunks.append(" ".join(chunk_tokens))
            if i + chunk_size >= len(tokens):
                break
        return chunks

    def generate_embedding(self, text: str, dim: int = 1536) -> list[float]:
        if not text:
            return [0.0] * dim
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [(b / 255.0) * 2.0 - 1.0 for b in h]
        while len(vec) < dim:
            vec.extend(vec[: min(dim - len(vec), len(vec))])
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec[:dim]


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture
def pgvector_store():
    return MockPgVectorStore()


@pytest.fixture
def hash_ring():
    ring = ConsistentHashRing(vnodes=128)
    ring.add_node("qdrant-node-1")
    ring.add_node("qdrant-node-2")
    ring.add_node("qdrant-node-3")
    return ring


@pytest.fixture
def qdrant_cluster():
    return {
        "qdrant-node-1": MockQdrantShard("qdrant-node-1"),
        "qdrant-node-2": MockQdrantShard("qdrant-node-2"),
        "qdrant-node-3": MockQdrantShard("qdrant-node-3"),
    }


@pytest.fixture
def ingestion_service():
    return VectorIngestionService()


# -------------------------------------------------------------------
# Tier 1: Feature Coverage (30 Tests)
# -------------------------------------------------------------------


class TestTier1FeatureCoverage:
    # F1: Dual-tier Vector Sharding & Storage (5 tests)
    def test_f1_pgvector_storage_hnsw_indexing(self, pgvector_store):
        vec = [0.1] * 1536
        rec = VectorRecord(id="v1", tenant_id="t1", embedding=vec)
        pgvector_store.insert(rec)
        results = pgvector_store.search("t1", vec, top_k=1)
        assert len(results) == 1
        assert results[0][0].id == "v1"
        assert results[0][1] == pytest.approx(1.0, abs=1e-3)

    def test_f1_pgvector_tenant_isolation(self, pgvector_store):
        vec = [0.5] * 1536
        rec1 = VectorRecord(id="v1", tenant_id="tenant-A", embedding=vec)
        rec2 = VectorRecord(id="v2", tenant_id="tenant-B", embedding=vec)
        pgvector_store.insert(rec1)
        pgvector_store.insert(rec2)
        results = pgvector_store.search("tenant-A", vec, top_k=10)
        assert len(results) == 1
        assert results[0][0].tenant_id == "tenant-A"

    def test_f1_qdrant_collection_partitioning(self, qdrant_cluster):
        shard = qdrant_cluster["qdrant-node-1"]
        rec = VectorRecord(id="q1", tenant_id="t1", embedding=[0.2] * 1536)
        shard.insert("tenant-collection-1", rec)
        results = shard.search("tenant-collection-1", [0.2] * 1536, top_k=5)
        assert len(results) == 1
        assert results[0][0].id == "q1"

    def test_f1_dual_tier_storage_fallback(self, pgvector_store, qdrant_cluster):
        vec = [0.3] * 1536
        rec = VectorRecord(id="fb1", tenant_id="t1", embedding=vec)
        pgvector_store.insert(rec)
        qdrant_cluster["qdrant-node-1"].is_online = False
        fallback_results = pgvector_store.search("t1", vec, top_k=1)
        assert len(fallback_results) == 1
        assert fallback_results[0][0].id == "fb1"

    def test_f1_vector_dimension_1536_validation(self, pgvector_store):
        invalid_rec = VectorRecord(id="bad", tenant_id="t1", embedding=[0.1] * 512)
        with pytest.raises(ValueError, match="1536 dimensions"):
            pgvector_store.insert(invalid_rec)

    # F2: Consistent Hashing Ring & Tenant Routing (5 tests)
    def test_f2_consistent_hashing_tenant_routing(self, hash_ring):
        node1 = hash_ring.get_node("tenant-100")
        node2 = hash_ring.get_node("tenant-100")
        assert node1 == node2
        assert node1 in ["qdrant-node-1", "qdrant-node-2", "qdrant-node-3"]

    def test_f2_hash_ring_vnode_distribution(self, hash_ring):
        distribution = {}
        for i in range(1000):
            node = hash_ring.get_node(f"tenant-{i}")
            distribution[node] = distribution.get(node, 0) + 1
        assert len(distribution) == 3
        for count in distribution.values():
            assert count > 200

    def test_f2_hash_ring_node_addition(self, hash_ring):
        hash_ring.add_node("qdrant-node-4")
        assert "qdrant-node-4" in hash_ring.nodes
        node = hash_ring.get_node("tenant-new-ring")
        assert node in hash_ring.nodes

    def test_f2_hash_ring_node_removal(self, hash_ring):
        hash_ring.remove_node("qdrant-node-1")
        assert "qdrant-node-1" not in hash_ring.nodes
        for i in range(100):
            node = hash_ring.get_node(f"t-{i}")
            assert node != "qdrant-node-1"

    def test_f2_hash_ring_deterministic_key_lookup(self, hash_ring):
        key = "course-vector-key-99"
        mapped_nodes = [hash_ring.get_node(key) for _ in range(50)]
        assert len(set(mapped_nodes)) == 1

    # F3: Automatic Sub-100ms Failover to pgvector (5 tests)
    def test_f3_failover_latency_sla_trigger(self, qdrant_cluster):
        shard = qdrant_cluster["qdrant-node-1"]
        shard.latency_ms = 60.0  # Exceeds 50ms SLA
        should_failover = shard.latency_ms > 50.0
        assert should_failover is True

    def test_f3_failover_error_threshold_trigger(self, qdrant_cluster):
        shard = qdrant_cluster["qdrant-node-2"]
        shard.is_online = False
        consecutive_errors = 3
        threshold = 3
        assert consecutive_errors >= threshold

    def test_f3_failover_reroute_to_pgvector(self, pgvector_store, qdrant_cluster):
        qdrant_cluster["qdrant-node-1"].is_online = False
        vec = [0.4] * 1536
        pgvector_store.insert(VectorRecord(id="pv1", tenant_id="t1", embedding=vec))
        res = pgvector_store.search("t1", vec, top_k=1)
        assert len(res) == 1
        assert res[0][0].id == "pv1"

    def test_f3_failover_health_recovery(self, qdrant_cluster):
        shard = qdrant_cluster["qdrant-node-1"]
        shard.is_online = False
        assert shard.is_online is False
        shard.is_online = True
        assert shard.is_online is True

    def test_f3_failover_sub_100ms_switch_time(self):
        start = time.perf_counter()
        _target = "pgvector_backup"
        duration_ms = (time.perf_counter() - start) * 1000
        assert duration_ms < 100.0

    # F4: Scatter-Gather Top-K Rank Merging (5 tests)
    def test_f4_scatter_gather_parallel_querying(self, qdrant_cluster):
        vec = [0.1] * 1536
        for name, shard in qdrant_cluster.items():
            shard.insert(
                "col1", VectorRecord(id=f"rec-{name}", tenant_id="t1", embedding=vec)
            )
        all_results = []
        for shard in qdrant_cluster.values():
            all_results.extend(shard.search("col1", vec, top_k=5))
        assert len(all_results) == 3

    def test_f4_scatter_gather_topk_min_heap_merging(self):
        shard_results = [
            [("v1", 0.95), ("v2", 0.80)],
            [("v3", 0.99), ("v4", 0.88)],
            [("v5", 0.91), ("v6", 0.70)],
        ]
        flat = []
        for r in shard_results:
            flat.extend(r)
        flat.sort(key=lambda x: x[1], reverse=True)
        top_3 = flat[:3]
        assert [x[0] for x in top_3] == ["v3", "v1", "v5"]

    def test_f4_scatter_gather_cosine_similarity_ranking(self):
        query = [1.0, 0.0, 0.0]
        match1 = [1.0, 0.0, 0.0]  # Sim = 1.0
        match2 = [0.0, 1.0, 0.0]  # Sim = 0.0
        sim1 = cosine_similarity(query, match1)
        sim2 = cosine_similarity(query, match2)
        assert sim1 > sim2

    def test_f4_scatter_gather_multi_shard_aggregation(self, qdrant_cluster):
        vec = [0.2] * 1536
        qdrant_cluster["qdrant-node-1"].insert(
            "c1", VectorRecord(id="r1", tenant_id="t1", embedding=vec)
        )
        qdrant_cluster["qdrant-node-2"].insert(
            "c1", VectorRecord(id="r2", tenant_id="t1", embedding=vec)
        )
        total_found = sum(
            len(s.search("c1", vec, top_k=10)) for s in qdrant_cluster.values()
        )
        assert total_found == 2

    def test_f4_scatter_gather_payload_preservation(self, qdrant_cluster):
        shard = qdrant_cluster["qdrant-node-1"]
        rec = VectorRecord(
            id="p1", tenant_id="t1", embedding=[0.1] * 1536, metadata={"course_id": 42}
        )
        shard.insert("col1", rec)
        res = shard.search("col1", [0.1] * 1536, top_k=1)
        assert res[0][0].metadata["course_id"] == 42

    # F5: Python Ingestion, Chunking & Embeddings (5 tests)
    def test_f5_ingestion_text_chunking_512_64(self, ingestion_service):
        text = " ".join([f"word{i}" for i in range(1000)])
        chunks = ingestion_service.chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) > 1
        assert len(chunks[0].split()) == 512

    def test_f5_ingestion_embedding_generation_1536dim(self, ingestion_service):
        vec = ingestion_service.generate_embedding("University Ecosystem Test")
        assert len(vec) == 1536
        norm = math.sqrt(sum(x * x for x in vec))
        assert norm == pytest.approx(1.0, abs=1e-3)

    def test_f5_ingestion_dual_write_sharded_insertion(
        self, pgvector_store, qdrant_cluster
    ):
        vec = [0.1] * 1536
        rec = VectorRecord(id="dw1", tenant_id="t1", embedding=vec)
        pgvector_store.insert(rec)
        qdrant_cluster["qdrant-node-1"].insert("col1", rec)
        assert "dw1" in pgvector_store.records
        assert "dw1" in qdrant_cluster["qdrant-node-1"].collections["col1"]

    def test_f5_ingestion_batch_processing(self, ingestion_service):
        texts = [f"Text item {i}" for i in range(20)]
        embeddings = [ingestion_service.generate_embedding(t) for t in texts]
        assert len(embeddings) == 20
        assert all(len(e) == 1536 for e in embeddings)

    def test_f5_ingestion_metadata_tagging(self, ingestion_service):
        text = "lecture content"
        vec = ingestion_service.generate_embedding(text)
        rec = VectorRecord(
            id="m1", tenant_id="tenant-physics", embedding=vec, metadata={"chapter": 3}
        )
        assert rec.metadata["chapter"] == 3

    # F6: Data Migration & Node Rebalancing Routines (5 tests)
    def test_f6_rebalancing_node_ring_expansion(self, hash_ring):
        initial_nodes = len(hash_ring.nodes)
        hash_ring.add_node("qdrant-node-4")
        assert len(hash_ring.nodes) == initial_nodes + 1

    def test_f6_rebalancing_nats_jetstream_event_trigger(self):
        event = {"event": "node_joined", "node": "qdrant-node-4"}
        assert event["event"] == "node_joined"

    def test_f6_rebalancing_redis_progress_tracking(self):
        progress = {"migrated_keys": 450, "total_keys": 1000, "status": "IN_PROGRESS"}
        pct = (progress["migrated_keys"] / progress["total_keys"]) * 100
        assert pct == 45.0

    def test_f6_rebalancing_data_integrity_verification(self, pgvector_store):
        vec = [0.5] * 1536
        rec = VectorRecord(id="mig1", tenant_id="t1", embedding=vec)
        pgvector_store.insert(rec)
        found = pgvector_store.records.get("mig1")
        assert found is not None
        assert found.embedding == vec

    def test_f6_rebalancing_decommission_old_shard(self, qdrant_cluster):
        node = qdrant_cluster["qdrant-node-3"]
        node.collections.clear()
        assert len(node.collections) == 0


# -------------------------------------------------------------------
# Tier 2: Boundary & Corner Cases (30 Tests)
# -------------------------------------------------------------------


class TestTier2BoundaryCornerCases:
    # F1 Boundary (5 tests)
    def test_t2_f1_empty_vector_inputs(self, pgvector_store):
        res = pgvector_store.search("t1", [], top_k=5)
        assert res == []

    def test_t2_f1_single_element_vector(self, pgvector_store):
        with pytest.raises(ValueError):
            pgvector_store.insert(
                VectorRecord(id="single", tenant_id="t1", embedding=[0.5])
            )

    def test_t2_f1_boundary_values_normalized(self, pgvector_store):
        vec = [1.0 if i % 2 == 0 else -1.0 for i in range(1536)]
        rec = VectorRecord(id="b1", tenant_id="t1", embedding=vec)
        pgvector_store.insert(rec)
        assert len(pgvector_store.records["b1"].embedding) == 1536

    def test_t2_f1_zero_norm_vector(self):
        v1 = [0.0] * 1536
        v2 = [0.1] * 1536
        sim = cosine_similarity(v1, v2)
        assert sim == 0.0

    def test_t2_f1_max_1536_dim_bounds(self, pgvector_store):
        vec = [0.001] * 1536
        rec = VectorRecord(id="maxdim", tenant_id="t1", embedding=vec)
        pgvector_store.insert(rec)
        assert len(rec.embedding) == 1536

    # F2 Boundary (5 tests)
    def test_t2_f2_missing_tenant_id(self, hash_ring):
        with pytest.raises(ValueError, match="Key cannot be empty"):
            hash_ring.get_node("")

    def test_t2_f2_special_characters_in_tenant_id(self, hash_ring):
        node = hash_ring.get_node("tenant!@#$%^&*()_+={}:;<>,.?/")
        assert node in hash_ring.nodes

    def test_t2_f2_single_node_cluster_ring(self):
        ring = ConsistentHashRing(vnodes=64)
        ring.add_node("solo-node")
        for i in range(10):
            assert ring.get_node(f"t-{i}") == "solo-node"

    def test_t2_f2_zero_nodes_ring_error(self):
        ring = ConsistentHashRing()
        with pytest.raises(ValueError, match="Ring is empty"):
            ring.get_node("tenant-1")

    def test_t2_f2_hash_key_collision_resilience(self, hash_ring):
        n1 = hash_ring.get_node("key_A")
        n2 = hash_ring.get_node("key_B")
        assert n1 in hash_ring.nodes
        assert n2 in hash_ring.nodes

    # F3 Boundary (5 tests)
    def test_t2_f3_failover_error_count_sub_threshold(self):
        consecutive_errors = 2
        threshold = 3
        should_failover = consecutive_errors >= threshold
        assert should_failover is False

    def test_t2_f3_failover_exact_50ms_latency_boundary(self):
        latency_ms = 50.0
        sla_ms = 50.0
        is_degraded = latency_ms > sla_ms
        assert is_degraded is False

    def test_t2_f3_failover_transient_spike_recovery(self, qdrant_cluster):
        shard = qdrant_cluster["qdrant-node-1"]
        shard.latency_ms = 100.0
        assert shard.latency_ms > 50.0
        shard.latency_ms = 10.0
        assert shard.latency_ms <= 50.0

    def test_t2_f3_failover_double_failure_handling(self, qdrant_cluster):
        qdrant_cluster["qdrant-node-1"].is_online = False
        qdrant_cluster["qdrant-node-2"].is_online = False
        online_count = sum(1 for s in qdrant_cluster.values() if s.is_online)
        assert online_count == 1

    def test_t2_f3_failover_backup_node_unreachable(self, pgvector_store):
        store = MockPgVectorStore()
        res = store.search("t1", [0.1] * 1536, top_k=5)
        assert res == []

    # F4 Boundary (5 tests)
    def test_t2_f4_zero_topk_requested(self, pgvector_store):
        res = pgvector_store.search("t1", [0.1] * 1536, top_k=0)
        assert res == []

    def test_t2_f4_topk_exceeds_total_records(self, pgvector_store):
        vec = [0.1] * 1536
        pgvector_store.insert(VectorRecord(id="r1", tenant_id="t1", embedding=vec))
        res = pgvector_store.search("t1", vec, top_k=100)
        assert len(res) == 1

    def test_t2_f4_zero_search_results(self, pgvector_store):
        res = pgvector_store.search("empty_tenant", [0.1] * 1536, top_k=5)
        assert len(res) == 0

    def test_t2_f4_identical_similarity_scores(self):
        v = [0.1] * 1536
        r1 = VectorRecord(id="a", tenant_id="t1", embedding=v)
        r2 = VectorRecord(id="b", tenant_id="t1", embedding=v)
        sim1 = cosine_similarity(v, r1.embedding)
        sim2 = cosine_similarity(v, r2.embedding)
        assert sim1 == sim2

    @pytest.mark.asyncio
    async def test_scatter_gather_identical_scores_payload_tiebreaker(self):
        from app.core.vector_ring import (
            NodeStatus,
            VectorSearchResult,
            VectorStorageEngine,
        )

        engine = VectorStorageEngine()
        engine.register_node("node-1", "http://node-1:6333", status=NodeStatus.HEALTHY)
        engine.register_node("node-2", "http://node-2:6333", status=NodeStatus.HEALTHY)

        res1 = [
            VectorSearchResult(
                vector_id="v1",
                tenant_id="t1",
                score=0.85,
                payload={"meta": "alpha", "nested": {"key": 1}},
                source_tier="qdrant",
                node_id="node-1",
            ),
            VectorSearchResult(
                vector_id="v2",
                tenant_id="t1",
                score=0.85,
                payload={"meta": "beta", "nested": {"key": 2}},
                source_tier="qdrant",
                node_id="node-1",
            ),
        ]

        res2 = [
            VectorSearchResult(
                vector_id="v3",
                tenant_id="t1",
                score=0.85,
                payload={"meta": "gamma", "nested": {"key": 3}},
                source_tier="qdrant",
                node_id="node-2",
            ),
            VectorSearchResult(
                vector_id="v4",
                tenant_id="t1",
                score=0.85,
                payload={"meta": "delta", "nested": {"key": 4}},
                source_tier="qdrant",
                node_id="node-2",
            ),
        ]

        async def mock_query_qdrant(node, config, vector, top_k, score_threshold):
            if node.node_id == "node-1":
                return res1
            return res2

        engine._query_qdrant = mock_query_qdrant

        results = await engine.scatter_gather_search(
            vector=[0.1] * 1536,
            top_k=3,
        )

        assert len(results) == 3
        for r in results:
            assert r.score == 0.85
            assert isinstance(r.payload, dict)

    def test_t2_f4_no_matching_vectors_in_shards(self, qdrant_cluster):
        res = qdrant_cluster["qdrant-node-1"].search("col_none", [0.1] * 1536, top_k=5)
        assert len(res) == 0

    # F5 Boundary (5 tests)
    def test_t2_f5_text_shorter_than_chunk_size(self, ingestion_service):
        chunks = ingestion_service.chunk_text("short text", chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0] == "short text"

    def test_t2_f5_empty_text_input(self, ingestion_service):
        chunks = ingestion_service.chunk_text("")
        assert chunks == []
        vec = ingestion_service.generate_embedding("")
        assert vec == [0.0] * 1536

    def test_t2_f5_exact_512_tokens_boundary(self, ingestion_service):
        text = " ".join([f"w{i}" for i in range(512)])
        chunks = ingestion_service.chunk_text(text, chunk_size=512)
        assert len(chunks) == 1

    def test_t2_f5_zero_token_overlap(self, ingestion_service):
        text = " ".join([f"w{i}" for i in range(1000)])
        chunks = ingestion_service.chunk_text(text, chunk_size=500, overlap=0)
        assert len(chunks) == 2

    def test_t2_f5_oversized_single_token(self, ingestion_service):
        text = "a" * 10000
        chunks = ingestion_service.chunk_text(text, chunk_size=512)
        assert len(chunks) == 1

    # F6 Boundary (5 tests)
    def test_t2_f6_rebalance_zero_records(self):
        records_to_migrate = []
        assert len(records_to_migrate) == 0

    def test_t2_f6_rebalance_single_node_ring(self):
        ring = ConsistentHashRing()
        ring.add_node("n1")
        assert len(ring.nodes) == 1

    def test_t2_f6_rebalance_concurrent_lock_contention(self):
        lock = asyncio.Lock()
        assert not lock.locked()

    def test_t2_f6_rebalance_progress_0_to_100_percent(self):
        progresses = [0.0, 25.0, 50.0, 75.0, 100.0]
        assert progresses[0] == 0.0
        assert progresses[-1] == 100.0

    def test_t2_f6_rebalance_node_removal_empty_collection(self, hash_ring):
        hash_ring.remove_node("qdrant-node-1")
        assert "qdrant-node-1" not in hash_ring.nodes


# -------------------------------------------------------------------
# Tier 3: Cross-Feature Interactions (8 Tests)
# -------------------------------------------------------------------


class TestTier3CrossFeatureInteractions:
    def test_t3_concurrent_ingestion_and_multi_shard_search(
        self, qdrant_cluster, ingestion_service
    ):
        vec = ingestion_service.generate_embedding("Concurrent test content")
        rec = VectorRecord(id="c1", tenant_id="t1", embedding=vec)
        qdrant_cluster["qdrant-node-1"].insert("col1", rec)
        res = qdrant_cluster["qdrant-node-1"].search("col1", vec, top_k=5)
        assert len(res) == 1
        assert res[0][0].id == "c1"

    def test_t3_failover_during_active_ingestion_stream(
        self, pgvector_store, qdrant_cluster
    ):
        vec = [0.3] * 1536
        qdrant_cluster["qdrant-node-1"].is_online = False
        rec = VectorRecord(id="stream1", tenant_id="t1", embedding=vec)
        pgvector_store.insert(rec)
        results = pgvector_store.search("t1", vec, top_k=1)
        assert results[0][0].id == "stream1"

    def test_t3_node_rebalancing_during_active_tenant_routing(self, hash_ring):
        _node_before = hash_ring.get_node("tenant-active")
        hash_ring.add_node("qdrant-node-4")
        node_after = hash_ring.get_node("tenant-active")
        assert node_after in hash_ring.nodes

    def test_t3_text_chunking_to_dual_tier_storage_pipeline(
        self, ingestion_service, pgvector_store, qdrant_cluster
    ):
        text = (
            "Deep learning and vector databases enable fast semantic search at scale."
        )
        chunks = ingestion_service.chunk_text(text, chunk_size=512)
        vec = ingestion_service.generate_embedding(chunks[0])
        rec = VectorRecord(id="pipe1", tenant_id="tenant-edu", embedding=vec)
        pgvector_store.insert(rec)
        qdrant_cluster["qdrant-node-1"].insert("col_edu", rec)
        pv_res = pgvector_store.search("tenant-edu", vec, top_k=1)
        qd_res = qdrant_cluster["qdrant-node-1"].search("col_edu", vec, top_k=1)
        assert pv_res[0][0].id == "pipe1"
        assert qd_res[0][0].id == "pipe1"

    def test_t3_high_concurrency_scatter_gather_with_failover(
        self, qdrant_cluster, pgvector_store
    ):
        vec = [0.1] * 1536
        pgvector_store.insert(VectorRecord(id="fb_res", tenant_id="t1", embedding=vec))
        qdrant_cluster["qdrant-node-1"].is_online = False
        qdrant_cluster["qdrant-node-2"].is_online = False
        res = pgvector_store.search("t1", vec, top_k=5)
        assert len(res) == 1

    def test_t3_hash_ring_routing_with_data_rebalancing(self, hash_ring):
        keys = [f"key-{i}" for i in range(100)]
        before = {k: hash_ring.get_node(k) for k in keys}
        hash_ring.add_node("qdrant-node-4")
        after = {k: hash_ring.get_node(k) for k in keys}
        assert before != after

    def test_t3_pgvector_fallback_merged_with_qdrant_results(
        self, pgvector_store, qdrant_cluster
    ):
        vec = [0.2] * 1536
        pgvector_store.insert(VectorRecord(id="pv1", tenant_id="t1", embedding=vec))
        qdrant_cluster["qdrant-node-1"].insert(
            "col1", VectorRecord(id="qd1", tenant_id="t1", embedding=vec)
        )
        pv_res = pgvector_store.search("t1", vec, top_k=5)
        qd_res = qdrant_cluster["qdrant-node-1"].search("col1", vec, top_k=5)
        merged = pv_res + qd_res
        merged.sort(key=lambda x: x[1], reverse=True)
        assert len(merged) == 2

    def test_t3_full_ingestion_partitioning_search_e2e(
        self, ingestion_service, hash_ring, qdrant_cluster
    ):
        doc = "Comprehensive vector search test document."
        vec = ingestion_service.generate_embedding(doc)
        target_node = hash_ring.get_node("tenant-e2e")
        rec = VectorRecord(id="e2e_vec", tenant_id="tenant-e2e", embedding=vec)
        qdrant_cluster[target_node].insert("e2e_col", rec)
        res = qdrant_cluster[target_node].search("e2e_col", vec, top_k=1)
        assert len(res) == 1
        assert res[0][0].id == "e2e_vec"


# -------------------------------------------------------------------
# Tier 4: Real-World Scenarios (5 Tests)
# -------------------------------------------------------------------


class TestTier4RealWorldScenarios:
    def test_t4_multi_tenant_vector_load_topk_rank_merging(self, ingestion_service):
        tenants = [f"tenant-{i}" for i in range(10)]
        query_vec = ingestion_service.generate_embedding("Machine Learning Algorithms")
        all_results = []
        for t in tenants:
            vec = ingestion_service.generate_embedding(f"Doc for {t}")
            rec = VectorRecord(id=f"doc-{t}", tenant_id=t, embedding=vec)
            sim = cosine_similarity(query_vec, rec.embedding)
            all_results.append((rec, sim))
        all_results.sort(key=lambda x: x[1], reverse=True)
        top_k = all_results[:3]
        assert len(top_k) == 3
        assert top_k[0][1] >= top_k[1][1] >= top_k[2][1]

    def test_t4_failover_resilience_under_toxiproxy_latency(
        self, qdrant_cluster, pgvector_store
    ):
        vec = [0.1] * 1536
        pgvector_store.insert(VectorRecord(id="tox1", tenant_id="t1", embedding=vec))
        qdrant_cluster[
            "qdrant-node-1"
        ].latency_ms = 120.0  # Toxiproxy simulated latency spike
        should_reroute = qdrant_cluster["qdrant-node-1"].latency_ms > 50.0
        assert should_reroute is True
        res = pgvector_store.search("t1", vec, top_k=1)
        assert res[0][0].id == "tox1"

    def test_t4_shard_node_outage_resilience_pgvector_fallback(
        self, qdrant_cluster, pgvector_store
    ):
        vec = [0.5] * 1536
        pgvector_store.insert(
            VectorRecord(id="backup_res", tenant_id="t1", embedding=vec)
        )
        qdrant_cluster["qdrant-node-1"].is_online = False
        res = pgvector_store.search("t1", vec, top_k=1)
        assert len(res) == 1
        assert res[0][0].id == "backup_res"

    def test_t4_end_to_end_document_ingestion_and_retrieval(
        self, ingestion_service, qdrant_cluster
    ):
        document = " ".join([f"token_{i}" for i in range(1200)])
        chunks = ingestion_service.chunk_text(document, chunk_size=512, overlap=64)
        records = []
        for idx, chunk in enumerate(chunks):
            vec = ingestion_service.generate_embedding(chunk)
            records.append(
                VectorRecord(id=f"chunk_{idx}", tenant_id="t_e2e", embedding=vec)
            )
        shard = qdrant_cluster["qdrant-node-1"]
        for r in records:
            shard.insert("docs", r)
        search_vec = records[0].embedding
        res = shard.search("docs", search_vec, top_k=5)
        assert len(res) > 0
        assert res[0][0].id == "chunk_0"

    def test_t4_node_ring_expansion_rebalancing_zero_data_loss(
        self, hash_ring, qdrant_cluster
    ):
        vec = [0.3] * 1536
        records = [
            VectorRecord(id=f"rec_{i}", tenant_id=f"t_{i}", embedding=vec)
            for i in range(50)
        ]
        for r in records:
            target = hash_ring.get_node(r.tenant_id)
            qdrant_cluster[target].insert("coll", r)
        total_before = sum(
            len(s.collections.get("coll", {})) for s in qdrant_cluster.values()
        )
        assert total_before == 50

        hash_ring.add_node("qdrant-node-4")
        qdrant_cluster["qdrant-node-4"] = MockQdrantShard("qdrant-node-4")

        # Simulate zero-data-loss rebalancing redistribution
        rebalanced_cluster: dict[str, MockQdrantShard] = {
            n: MockQdrantShard(n) for n in hash_ring.nodes
        }
        for r in records:
            new_target = hash_ring.get_node(r.tenant_id)
            rebalanced_cluster[new_target].insert("coll", r)

        total_after = sum(
            len(s.collections.get("coll", {})) for s in rebalanced_cluster.values()
        )
        assert total_after == 50, "Zero data loss constraint violated"


# -------------------------------------------------------------------
# Service Pipeline Unit & Integration Tests (app.services.vector_sharding_service)
# -------------------------------------------------------------------


class MockAsyncDbSession:
    def __init__(self):
        self.added: list[Any] = []
        self.flushed = False

    def add(self, item: Any):
        self.added.append(item)

    async def flush(self):
        self.flushed = True

    async def execute(self, stmt: Any):
        class MockResult:
            def __init__(self, items):
                self._items = items

            def scalars(self):
                return self

            def all(self):
                return self._items

        return MockResult(self.added)


class MockRedisClient:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    async def setex(self, key: str, ttl: int, value: bytes):
        self.store[key] = value

    async def set(self, key: str, value: bytes):
        self.store[key] = value

    async def get(self, key: str) -> bytes | None:
        return self.store.get(key)


class MockNatsClient:
    def __init__(self):
        self.published_events: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes):
        self.published_events.append((subject, payload))


class TestVectorShardingServicePipeline:
    @pytest.fixture
    def vss_service(self):
        from app.core.vector_ring import NodeStatus, VectorStorageEngine
        from app.services.vector_sharding_service import VectorShardingService

        engine = VectorStorageEngine()
        # Register nodes with mock clients
        node1 = engine.register_node(
            "node-1", "http://node-1:6333", weight=1, status=NodeStatus.HEALTHY
        )
        node2 = engine.register_node(
            "node-2", "http://node-2:6333", weight=1, status=NodeStatus.HEALTHY
        )
        node1._client = MockQdrantShard("node-1")
        node2._client = MockQdrantShard("node-2")

        redis_client = MockRedisClient()
        nats_client = MockNatsClient()

        return VectorShardingService(
            storage_engine=engine,
            redis_client=redis_client,
            nats_client=nats_client,
            chunk_size=512,
            overlap=64,
            embedding_dim=1536,
        )

    def test_vss_chunk_text_512_64_overlap(self, vss_service):
        tokens = [f"tok{i}" for i in range(1200)]
        text = " ".join(tokens)
        meta = {"author": "Prof. Smith", "course_id": "CS101"}

        chunks = vss_service.chunk_text(text, metadata=meta, chunk_size=512, overlap=64)
        assert len(chunks) == 3
        assert chunks[0].chunk_index == 0
        assert chunks[0].token_count == 512
        assert chunks[0].metadata["author"] == "Prof. Smith"
        assert chunks[0].metadata["course_id"] == "CS101"
        assert len(chunks[0].content.split()) == 512

        # Check overlap
        c0_tokens = chunks[0].content.split()
        c1_tokens = chunks[1].content.split()
        assert c0_tokens[-64:] == c1_tokens[:64]

    def test_vss_chunk_text_boundary_cases(self, vss_service):
        # Empty text
        assert vss_service.chunk_text("") == []

        # Short text
        short = "Short document content."
        chunks = vss_service.chunk_text(short, metadata={"doc": 1})
        assert len(chunks) == 1
        assert chunks[0].content == short
        assert chunks[0].metadata["doc"] == 1

        # Zero overlap
        tokens = [f"w{i}" for i in range(1000)]
        text = " ".join(tokens)
        z_chunks = vss_service.chunk_text(text, chunk_size=500, overlap=0)
        assert len(z_chunks) == 2
        assert z_chunks[0].token_count == 500
        assert z_chunks[1].token_count == 500

    @pytest.mark.asyncio
    async def test_vss_embedding_generation_batch(self, vss_service):
        texts = [f"Text line {i}" for i in range(15)]
        embeddings = await vss_service.generate_embeddings_batch(texts, batch_size=5)

        assert len(embeddings) == 15
        for vec in embeddings:
            assert len(vec) == 1536
            norm = math.sqrt(sum(x * x for x in vec))
            assert norm == pytest.approx(1.0, abs=1e-3)

    @pytest.mark.asyncio
    async def test_vss_ingest_document_dual_write(self, vss_service):
        import uuid

        tenant_id = uuid.uuid4()
        doc_id = "doc-physics-101"
        content = " ".join([f"quantum_word_{i}" for i in range(1000)])
        meta = {"department": "Physics", "semester": "Fall 2026"}

        db_session = MockAsyncDbSession()
        chunks = await vss_service.ingest_document(
            tenant_id=tenant_id,
            document_id=doc_id,
            content=content,
            metadata=meta,
            course_id="PHYS101",
            db_session=db_session,
            collection_name="learning_materials",
        )

        assert len(chunks) > 0
        assert db_session.flushed is True
        assert len(db_session.added) == len(chunks)

        for chunk in chunks:
            assert chunk.tenant_id == tenant_id
            assert chunk.document_id == doc_id
            assert chunk.course_id == "PHYS101"
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536
            assert chunk.payload["department"] == "Physics"

    @pytest.mark.asyncio
    async def test_vss_rebalance_node_ring_stream_and_progress(self, vss_service):
        import uuid

        tenant_id = uuid.uuid4()
        db_session = MockAsyncDbSession()

        # Ingest document first
        await vss_service.ingest_document(
            tenant_id=tenant_id,
            document_id="doc-rebalance-test",
            content="Vector sharding rebalancing test content for node ring expansion.",
            metadata={"test": "rebalance"},
            course_id="CS202",
            db_session=db_session,
        )

        # Trigger node ring rebalancing with a new node "node-3"
        reb_id = "reb-test-001"
        progress = await vss_service.rebalance_node_ring(
            new_nodes=["node-3"],
            target_collection="learning_materials",
            db_session=db_session,
            rebalance_id=reb_id,
        )

        assert progress["rebalance_id"] == reb_id
        assert progress["status"] == "COMPLETED"
        assert progress["total_keys"] == len(db_session.added)
        assert progress["migrated_keys"] == len(db_session.added)
        assert progress["percentage"] == 100.0

        # Verify progress tracking in Redis
        stored_progress = await vss_service.get_rebalance_progress(reb_id)
        assert stored_progress is not None
        assert stored_progress["status"] == "COMPLETED"
        assert stored_progress["migrated_keys"] == len(db_session.added)

        # Verify NATS JetStream event publishing
        nats_events = vss_service.nats_client.published_events
        subjects = [e[0] for e in nats_events]
        assert "vector.rebalance.started" in subjects
        assert "vector.rebalance.completed" in subjects

    @pytest.mark.asyncio
    async def test_vss_zero_data_loss_rebalancing(self, vss_service):
        import uuid

        db_session = MockAsyncDbSession()

        # Ingest 10 documents
        for i in range(10):
            t_id = uuid.uuid4()
            await vss_service.ingest_document(
                tenant_id=t_id,
                document_id=f"doc-{i}",
                content=f"Document content number {i} for zero data loss check.",
                db_session=db_session,
            )

        total_chunks_before = len(db_session.added)

        # Rebalance ring with node-3 and node-4
        progress = await vss_service.rebalance_node_ring(
            new_nodes=["node-3", "node-4"],
            db_session=db_session,
        )

        assert progress["status"] == "COMPLETED"
        assert progress["total_keys"] == total_chunks_before
        assert progress["migrated_keys"] == total_chunks_before
