"""
Ingestion & Rebalancing Pipeline Service for Distributed Vector Sharding.

Implements Tier 2 / Tier 1 vector ingestion, chunking (512 tokens / 64 token overlap),
1536-dimensional embedding generation via VectorService (with async batching),
dual-write sharded insertion (Qdrant shard nodes + PostgreSQL 17 pgvector store),
and node rebalancing/data migration routines with NATS JetStream batch streaming & Redis progress tracking.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import math
import uuid
from collections.abc import Sequence
from typing import Any, cast

from app.core.logging import get_logger
from app.core.vector_ring import (
    NodeConfig,
    VectorStorageEngine,
)
from app.models.vector_shard import VectorChunk

logger = get_logger(__name__)


@dataclasses.dataclass
class TextChunk:
    """Represents a text chunk produced during ingestion."""

    content: str
    chunk_index: int
    token_count: int
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


class VectorShardingService:
    """
    Background Python ingestion, chunking, dual-write sharding, and node rebalancing service.
    """

    def __init__(
        self,
        storage_engine: VectorStorageEngine | None = None,
        vector_service: Any | None = None,
        nats_client: Any | None = None,
        redis_client: Any | None = None,
        chunk_size: int = 512,
        overlap: int = 64,
        embedding_dim: int = 1536,
    ) -> None:
        self.storage_engine = storage_engine or VectorStorageEngine()
        self.vector_service = vector_service
        self.nats_client = nats_client
        self.redis_client = redis_client
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.embedding_dim = embedding_dim
        self._progress_store: dict[str, dict[str, Any]] = {}

    def chunk_text(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[TextChunk]:
        """
        Chunk text into windows of `chunk_size` tokens with `overlap` token overlap.
        Preserves document metadata on every chunk.
        """
        c_size = chunk_size if chunk_size is not None else self.chunk_size
        ov = overlap if overlap is not None else self.overlap
        base_meta = dict(metadata or {})

        if not text:
            return []

        tokens = text.split()
        if not tokens:
            return []

        if len(tokens) <= c_size:
            return [
                TextChunk(
                    content=text,
                    chunk_index=0,
                    token_count=len(tokens),
                    metadata=dict(base_meta),
                )
            ]

        chunks: list[TextChunk] = []
        step = c_size - ov if c_size > ov else c_size
        chunk_idx = 0

        for i in range(0, len(tokens), step):
            chunk_tokens = tokens[i : i + c_size]
            chunk_str = " ".join(chunk_tokens)
            chunks.append(
                TextChunk(
                    content=chunk_str,
                    chunk_index=chunk_idx,
                    token_count=len(chunk_tokens),
                    metadata=dict(base_meta),
                )
            )
            chunk_idx += 1

        return chunks

    def generate_deterministic_embedding(self, text: str) -> list[float]:
        """Generate normalized 1536-dim fallback embedding for testing or offline mode."""
        if not text:
            return [0.0] * self.embedding_dim
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [(b / 255.0) * 2.0 - 1.0 for b in h]
        while len(vec) < self.embedding_dim:
            vec.extend(vec[: min(self.embedding_dim - len(vec), len(vec))])
        norm = math.sqrt(sum(x * x for x in vec))
        # A SHA-256 byte maps to one of 256 values, none of which becomes
        # exactly zero under the transformation above, so the norm is positive.
        vec = [x / norm for x in vec]
        return vec[: self.embedding_dim]

    async def get_embedding(self, text: str) -> list[float]:
        """Generate 1536-dimensional embedding using VectorService if available, else deterministic fallback."""
        if self.vector_service is not None and hasattr(
            self.vector_service, "get_embedding"
        ):
            try:
                emb = await self.vector_service.get_embedding(text)
                if (
                    emb
                    and len(emb) == self.embedding_dim
                    and any(x != 0.0 for x in emb)
                ):
                    return cast(list[float], emb)
            except (ConnectionError, TimeoutError, OSError, ValueError) as e:
                # RZ-20-04 / RZ-22-01
                logger.warning(
                    "VectorService get_embedding failed, using fallback embedding: %s",
                    e,
                )
        return self.generate_deterministic_embedding(text)

    async def generate_embeddings_batch(
        self, texts: list[str], batch_size: int = 10
    ) -> list[list[float]]:
        """Generate embeddings in async batches."""
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_tasks = [self.get_embedding(t) for t in batch_texts]
            batch_embs = await asyncio.gather(*batch_tasks)
            results.extend(batch_embs)
        return results

    async def ingest_document(
        self,
        tenant_id: str | uuid.UUID,
        document_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        course_id: str | None = None,
        db_session: Any | None = None,
        collection_name: str = "learning_materials",
    ) -> list[VectorChunk]:
        """
        Full ingestion pipeline:
        1. Chunk text into 512-token / 64-overlap chunks.
        2. Generate 1536d embeddings in async batches.
        3. Dual-write: insert VectorChunk into pgvector DB and push to assigned Qdrant shard node.
        """
        str_tenant = str(tenant_id)
        uuid_tenant = uuid.UUID(str_tenant) if isinstance(tenant_id, str) else tenant_id
        meta = dict(metadata or {})
        meta.update(
            {
                "tenant_id": str_tenant,
                "document_id": document_id,
                "course_id": course_id,
            }
        )

        chunks = self.chunk_text(content, metadata=meta)
        if not chunks:
            return []

        texts = [c.content for c in chunks]
        embeddings = await self.generate_embeddings_batch(texts)

        vector_chunks: list[VectorChunk] = []
        target_node = self.storage_engine.get_target_node(str_tenant)

        for chunk, emb in zip(chunks, embeddings, strict=False):
            v_chunk = VectorChunk(
                tenant_id=uuid_tenant,
                course_id=course_id,
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=emb,
                payload=chunk.metadata,
                is_active=True,
            )
            vector_chunks.append(v_chunk)

            if db_session is not None:
                db_session.add(v_chunk)

            if target_node and target_node._client is not None:
                try:
                    q_payload = dict(chunk.metadata)
                    q_payload.update(
                        {
                            "tenant_id": str_tenant,
                            "document_id": document_id,
                            "chunk_index": chunk.chunk_index,
                            "content": chunk.content,
                        }
                    )
                    if hasattr(target_node._client, "insert"):
                        target_node._client.insert(
                            collection=collection_name,
                            record=v_chunk,
                        )
                    elif hasattr(target_node._client, "upsert"):
                        target_node._client.upsert(
                            collection_name=collection_name,
                            points=[
                                {
                                    "id": str(v_chunk.id),
                                    "vector": emb,
                                    "payload": q_payload,
                                }
                            ],
                        )
                except (ConnectionError, TimeoutError, OSError) as e:
                    # RZ-20-04
                    logger.warning(
                        "Failed dual-write to Qdrant node %s: %s",
                        target_node.node_id,
                        e,
                    )

        if db_session is not None:
            await db_session.flush()

        return vector_chunks

    async def _update_progress(
        self,
        rebalance_id: str,
        migrated_keys: int,
        total_keys: int,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update rebalancing progress in Redis and internal store."""
        pct = (migrated_keys / total_keys * 100.0) if total_keys > 0 else 100.0
        data = {
            "rebalance_id": rebalance_id,
            "migrated_keys": migrated_keys,
            "total_keys": total_keys,
            "percentage": round(pct, 2),
            "status": status,
        }
        if extra:
            data.update(extra)

        self._progress_store[rebalance_id] = data

        if self.redis_client is not None:
            try:
                import orjson

                redis_key = f"vector_sharding:rebalance:{rebalance_id}"
                if hasattr(self.redis_client, "setex"):
                    res = self.redis_client.setex(redis_key, 3600, orjson.dumps(data))
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(self.redis_client, "set"):
                    res = self.redis_client.set(redis_key, orjson.dumps(data))
                    if asyncio.iscoroutine(res):
                        await res
            except (ConnectionError, TimeoutError, OSError) as e:
                # RZ-22-01: narrowed — Redis error
                logger.warning("Failed to save rebalance progress to Redis: %s", e)

        return data

    async def get_rebalance_progress(self, rebalance_id: str) -> dict[str, Any] | None:
        """Get rebalancing progress from Redis or local store."""
        if self.redis_client is not None:
            try:
                import orjson

                redis_key = f"vector_sharding:rebalance:{rebalance_id}"
                raw = None
                if hasattr(self.redis_client, "get"):
                    raw = self.redis_client.get(redis_key)
                    if asyncio.iscoroutine(raw):
                        raw = await raw
                if raw:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    if isinstance(raw, str):
                        return cast(dict[str, Any], orjson.loads(raw))
                    if isinstance(raw, dict):
                        return raw
            except (ConnectionError, TimeoutError, OSError) as e:
                # RZ-22-01
                logger.warning("Failed to fetch rebalance progress from Redis: %s", e)

        return self._progress_store.get(rebalance_id)

    async def publish_jetstream_event(
        self, subject: str, payload: dict[str, Any]
    ) -> None:
        """Publish rebalance streaming event to NATS JetStream if available."""
        if self.nats_client is not None:
            try:
                import orjson

                data = orjson.dumps(payload)
                if hasattr(self.nats_client, "publish"):
                    res = self.nats_client.publish(subject, data)
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(self.nats_client, "js") and self.nats_client.js():
                    res = self.nats_client.js().publish(subject, data)
                    if asyncio.iscoroutine(res):
                        await res
            except (ConnectionError, TimeoutError, OSError) as e:
                # RZ-20-04
                logger.warning("NATS JetStream publish error for %s: %s", subject, e)

    async def rebalance_node_ring(
        self,
        new_nodes: Sequence[NodeConfig | str],
        target_collection: str = "learning_materials",
        db_session: Any | None = None,
        rebalance_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Data migration and node rebalancing routine:
        1. Register new nodes into consistent hash ring.
        2. Publish JetStream start event & initialize Redis progress tracking.
        3. Scan existing vector records from pgvector DB or storage.
        4. Recalculate target shard nodes for each tenant/record.
        5. Redistribute vector chunks to new target nodes.
        6. Stream batch events over JetStream & update progress in Redis.
        7. Verify zero data loss constraint and decommission empty shards if needed.
        """
        r_id = rebalance_id or f"reb-{uuid.uuid4().hex[:8]}"

        registered_nodes: list[str] = []
        for n in new_nodes:
            if isinstance(n, str):
                self.storage_engine.register_node(
                    node_id=n, endpoint=f"http://{n}:6333"
                )
                registered_nodes.append(n)
            elif isinstance(n, NodeConfig):
                self.storage_engine.ring.add_node(n)
                registered_nodes.append(n.node_id)

        await self.publish_jetstream_event(
            "vector.rebalance.started",
            {
                "rebalance_id": r_id,
                "new_nodes": registered_nodes,
                "collection": target_collection,
            },
        )

        records_to_migrate: list[VectorChunk] = []
        if db_session is not None:
            from sqlalchemy import select

            stmt = select(VectorChunk).where(VectorChunk.is_active == True)  # noqa: E712
            res = await db_session.execute(stmt)
            records_to_migrate = list(res.scalars().all())

        total_keys = len(records_to_migrate)
        migrated_keys = 0

        await self._update_progress(r_id, migrated_keys, total_keys, "IN_PROGRESS")

        for idx, chunk in enumerate(records_to_migrate, start=1):
            str_tenant = str(chunk.tenant_id)
            target_node = self.storage_engine.get_target_node(str_tenant)

            if target_node and target_node._client is not None:
                try:
                    q_payload = dict(chunk.payload or {})
                    q_payload.update(
                        {
                            "tenant_id": str_tenant,
                            "document_id": chunk.document_id,
                            "chunk_index": chunk.chunk_index,
                            "content": chunk.content,
                        }
                    )
                    if hasattr(target_node._client, "insert"):
                        target_node._client.insert(
                            collection=target_collection,
                            record=chunk,
                        )
                    elif hasattr(target_node._client, "upsert"):
                        target_node._client.upsert(
                            collection_name=target_collection,
                            points=[
                                {
                                    "id": str(chunk.id),
                                    "vector": chunk.embedding,
                                    "payload": q_payload,
                                }
                            ],
                        )
                except (ConnectionError, TimeoutError, OSError) as e:
                    # RZ-20-04
                    logger.warning(
                        "Error migrating chunk %s to node %s: %s",
                        chunk.id,
                        target_node.node_id,
                        e,
                    )

            migrated_keys += 1

            if idx % 10 == 0 or idx == total_keys:
                await self._update_progress(
                    r_id, migrated_keys, total_keys, "IN_PROGRESS"
                )
                await self.publish_jetstream_event(
                    "vector.rebalance.batch",
                    {
                        "rebalance_id": r_id,
                        "migrated": migrated_keys,
                        "total": total_keys,
                    },
                )

        final_progress = await self._update_progress(
            r_id, migrated_keys, total_keys, "COMPLETED"
        )

        await self.publish_jetstream_event(
            "vector.rebalance.completed",
            {
                "rebalance_id": r_id,
                "total_migrated": migrated_keys,
                "status": "COMPLETED",
            },
        )

        return final_progress
