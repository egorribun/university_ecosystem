"""Vector service and shard-management runtime contracts."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.vector_ring import ConsistentHashRing, NodeConfig, VectorStorageEngine
from app.models.vector_shard import VectorChunk
from app.services.vector_sharding_service import VectorShardingService


@pytest.mark.asyncio
async def test_ingestion_tolerates_client_without_supported_write_api() -> None:
    engine = VectorStorageEngine()
    node = engine.register_node("node", "http://node:6333")
    node._client = SimpleNamespace()
    service = VectorShardingService(
        storage_engine=engine,
        embedding_dim=4,
        chunk_size=10,
    )

    chunks = await service.ingest_document(
        uuid.uuid4(),
        "document",
        "one two",
    )

    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_rebalance_progress_reads_local_store_without_redis() -> None:
    service = VectorShardingService()
    service._progress_store["local"] = {"status": "LOCAL"}

    assert await service.get_rebalance_progress("local") == {"status": "LOCAL"}


@pytest.mark.asyncio
async def test_jetstream_publish_handles_absent_stream_and_sync_ack() -> None:
    class NoStream:
        def js(self) -> None:
            return None

    await VectorShardingService(nats_client=NoStream()).publish_jetstream_event(
        "vector.test", {}
    )

    stream = MagicMock()
    stream.publish.return_value = None

    class SyncStream:
        def js(self) -> MagicMock:
            return stream

    await VectorShardingService(nats_client=SyncStream()).publish_jetstream_event(
        "vector.test", {"ok": True}
    )
    stream.publish.assert_called_once()


@pytest.mark.asyncio
async def test_rebalance_tolerates_client_without_supported_write_api() -> None:
    engine = VectorStorageEngine()
    node = engine.register_node("node", "http://node:6333")
    node._client = SimpleNamespace()
    chunk = VectorChunk(
        tenant_id=uuid.uuid4(),
        document_id="document",
        content="content",
        embedding=[0.1, 0.2],
        payload={},
        chunk_index=0,
        is_active=True,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [chunk]
    database = AsyncMock()
    database.execute.return_value = result

    progress = await VectorShardingService(storage_engine=engine).rebalance_node_ring(
        [],
        db_session=database,
        rebalance_id="unsupported-client",
    )

    assert progress["migrated_keys"] == 1


def test_ring_removal_recovers_from_missing_sorted_key() -> None:
    ring = ConsistentHashRing(vnodes_per_node=1)
    node = NodeConfig("node", "http://node:6333")
    ring.add_node(node)
    ring.sorted_keys.clear()

    ring.remove_node("node")

    assert not ring.nodes
    assert not ring.ring
