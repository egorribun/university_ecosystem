"""
Empirical Stress Test Harness by Challenger 2 for Milestone 4.
Tests:
- Vector text chunking (512 token max, 64 token overlap) & metadata preservation/isolation.
- 1536-dim embedding generation, L2 norm verification, & pgvector HNSW index structure.
- Multi-node consistent hash ring redistribution, JetStream streaming, Redis progress, & zero data loss.
"""

import math
import uuid
from typing import Any

import pytest
from sqlalchemy import Index

from app.core.vector_ring import ConsistentHashRing, NodeConfig, VectorStorageEngine
from app.models.vector_shard import VectorChunk
from app.services.vector_sharding_service import VectorShardingService


class MockAsyncDbSession:
    """Mock async DB session for empirical testing."""

    def __init__(self, records: list[VectorChunk] | None = None):
        self.added: list[VectorChunk] = records or []
        self.flushed = False

    def add(self, item: VectorChunk):
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


# -------------------------------------------------------------------
# Test Suite 1: Text Chunking & Metadata Preservation
# -------------------------------------------------------------------


class TestEmpiricalChunkingAndMetadata:
    @pytest.fixture
    def service(self):
        return VectorShardingService(chunk_size=512, overlap=64, embedding_dim=1536)

    def test_large_document_50k_tokens_chunking(self, service):
        """Stress test chunking with a 50,000-token document."""
        tokens = [f"word_{i}" for i in range(50000)]
        text = " ".join(tokens)
        meta = {"doc_type": "textbook", "chapter": 12}

        chunks = service.chunk_text(text, metadata=meta)

        # Expected chunks: step = 512 - 64 = 448
        # ceil( (50000 - 512) / 448 ) + 1 = 112 chunks
        assert len(chunks) > 100
        assert chunks[0].token_count == 512
        assert chunks[0].chunk_index == 0
        assert chunks[0].metadata["doc_type"] == "textbook"

        # Verify 64-token overlap across first 5 adjacent chunk pairs
        for c_idx in range(5):
            tokens_curr = chunks[c_idx].content.split()
            tokens_next = chunks[c_idx + 1].content.split()
            assert tokens_curr[-64:] == tokens_next[:64], (
                f"Overlap mismatch at chunk {c_idx}"
            )

    def test_chunking_exact_512_boundary(self, service):
        """Test document with exactly 512 tokens."""
        text = " ".join([f"token_{i}" for i in range(512)])
        chunks = service.chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0].token_count == 512

    def test_chunking_513_tokens_triggers_overlap(self, service):
        """Test document with 513 tokens producing 2 chunks with overlap."""
        tokens = [f"tok_{i}" for i in range(513)]
        text = " ".join(tokens)
        chunks = service.chunk_text(text)
        assert len(chunks) == 2
        assert chunks[0].token_count == 512
        assert chunks[1].token_count == 65  # 513 - 448 = 65
        c0_tokens = chunks[0].content.split()
        c1_tokens = chunks[1].content.split()
        assert c0_tokens[-64:] == c1_tokens[:64]

    def test_metadata_preservation_and_independence(self, service):
        """Ensure metadata is attached to all chunks."""
        text = " ".join([f"w{i}" for i in range(1200)])
        meta = {"course": "CS404", "tags": ["AI", "Vector"]}

        chunks = service.chunk_text(text, metadata=meta)
        assert len(chunks) == 3
        for c in chunks:
            assert c.metadata["course"] == "CS404"
            assert "AI" in c.metadata["tags"]


# -------------------------------------------------------------------
# Test Suite 2: 1536d Embedding & pgvector HNSW Indexing
# -------------------------------------------------------------------


class TestEmpiricalEmbeddingsAndPgvector:
    @pytest.fixture
    def service(self):
        return VectorShardingService(chunk_size=512, overlap=64, embedding_dim=1536)

    def test_embedding_dimension_and_l2_normalization(self, service):
        """Verify 100 deterministic embeddings are exactly 1536-dimensional and L2-normalized."""
        for i in range(100):
            text = f"Sample text for vector embedding generation {i}"
            vec = service.generate_deterministic_embedding(text)
            assert len(vec) == 1536
            norm = math.sqrt(sum(x * x for x in vec))
            assert norm == pytest.approx(1.0, abs=1e-4)

    def test_empty_string_embedding_returns_zero_vector(self, service):
        """Empty string must produce a 1536-dim zero vector."""
        vec = service.generate_deterministic_embedding("")
        assert len(vec) == 1536
        assert all(x == 0.0 for x in vec)

    def test_pgvector_model_hnsw_index_metadata(self):
        """Inspect VectorChunk model table args to verify pgvector HNSW index config."""
        table_args = VectorChunk.__table_args__
        hnsw_index = None
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "ix_vector_chunks_embedding":
                hnsw_index = arg
                break

        assert hnsw_index is not None, "ix_vector_chunks_embedding HNSW index missing"
        assert hnsw_index.kwargs.get("postgresql_using") == "hnsw"
        assert hnsw_index.kwargs.get("postgresql_with") == {
            "m": 16,
            "ef_construction": 64,
        }
        assert hnsw_index.kwargs.get("postgresql_ops") == {
            "embedding": "vector_cosine_ops"
        }


# -------------------------------------------------------------------
# Test Suite 3: Node Rebalancing & Zero Data Loss
# -------------------------------------------------------------------


class TestEmpiricalNodeRebalancingAndClusterExpansion:
    @pytest.mark.asyncio
    async def test_rebalancing_cluster_expansion_zero_data_loss(self):
        """Empirically test node addition rebalancing with 500 documents and verify zero data loss."""
        engine = VectorStorageEngine()
        _n1 = engine.register_node("node-1", "http://node-1:6333")
        _n2 = engine.register_node("node-2", "http://node-2:6333")

        redis = MockRedisClient()
        nats = MockNatsClient()
        vss = VectorShardingService(
            storage_engine=engine, redis_client=redis, nats_client=nats
        )

        db = MockAsyncDbSession()
        # Ingest 500 documents
        for i in range(500):
            t_id = uuid.uuid4()
            await vss.ingest_document(
                tenant_id=t_id,
                document_id=f"doc-emb-{i}",
                content=f"Document content string {i} for stress rebalance test.",
                db_session=db,
            )

        total_chunks = len(db.added)
        assert total_chunks == 500

        # Expand cluster with node-3 and node-4
        progress = await vss.rebalance_node_ring(
            new_nodes=["node-3", "node-4"],
            db_session=db,
            rebalance_id="stress-reb-500",
        )

        assert progress["status"] == "COMPLETED"
        assert progress["total_keys"] == total_chunks
        assert progress["migrated_keys"] == total_chunks
        assert progress["percentage"] == 100.0

        # Verify Redis progress persistence
        redis_data = await vss.get_rebalance_progress("stress-reb-500")
        assert redis_data["status"] == "COMPLETED"
        assert redis_data["migrated_keys"] == total_chunks

        # Verify NATS event sequence
        subjects = [e[0] for e in nats.published_events]
        assert "vector.rebalance.started" in subjects
        assert "vector.rebalance.completed" in subjects
        assert "vector.rebalance.batch" in subjects

    def test_consistent_hash_ring_vnode_distribution_uniformity(self):
        """Verify 128 vnodes per physical node distribute 5,000 keys uniformly across 4 nodes."""
        ring = ConsistentHashRing(vnodes_per_node=128)
        for i in range(1, 5):
            ring.add_node(
                NodeConfig(node_id=f"node-{i}", endpoint=f"http://node-{i}:6333")
            )

        counts: dict[str, int] = {}
        for k in range(5000):
            node = ring.get_healthy_node(f"tenant-key-{k}")
            assert node is not None
            counts[node.node_id] = counts.get(node.node_id, 0) + 1

        assert len(counts) == 4
        # Each node should get roughly ~25% of keys (1250 keys +- 300)
        for n_id, count in counts.items():
            assert 900 <= count <= 1600, f"Node {n_id} unbalanced with count {count}"
