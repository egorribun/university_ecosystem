from __future__ import annotations

import bisect
import enum
import hashlib
import heapq
from typing import Any, NamedTuple

from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    import qdrant_client  # noqa: F401
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qdrant_models

    HAS_QDRANT_CLIENT = True
except (ImportError, ModuleNotFoundError):  # RZ-20-04
    HAS_QDRANT_CLIENT = False
    QdrantClient = Any
    qdrant_models = Any


class NodeStatus(str, enum.Enum):
    """Health status of a Qdrant cluster node."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class NodeConfig:
    """Physical Qdrant cluster node configuration."""

    def __init__(
        self,
        node_id: str,
        endpoint: str,
        weight: int = 1,
        status: NodeStatus = NodeStatus.HEALTHY,
    ) -> None:
        self.node_id = node_id
        self.endpoint = endpoint
        self.weight = weight
        self.status = status
        self._client: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "endpoint": self.endpoint,
            "weight": self.weight,
            "status": self.status.value,
        }


def hash_key(key: str) -> int:
    """Compute deterministic 64-bit uint hash for consistent ring placement."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


class ConsistentHashRing:
    """
    Consistent hash ring data structure mapping tenant/vector keys across physical nodes
    using 128 virtual nodes (vnodes) per physical instance.
    """

    def __init__(self, vnodes_per_node: int = 128) -> None:
        self.vnodes_per_node = vnodes_per_node
        self.ring: dict[int, str] = {}  # hash_val -> vnode_name
        self.sorted_keys: list[int] = []  # sorted hash values
        self.vnode_to_node: dict[str, str] = {}  # vnode_name -> node_id
        self.nodes: dict[str, NodeConfig] = {}  # node_id -> NodeConfig

    def add_node(self, node: NodeConfig) -> None:
        """Add a physical node to the hash ring with virtual nodes."""
        self.nodes[node.node_id] = node
        num_vnodes = self.vnodes_per_node * node.weight
        for i in range(num_vnodes):
            vnode_name = f"{node.node_id}#vnode-{i}"
            h = hash_key(vnode_name)
            self.ring[h] = vnode_name
            self.vnode_to_node[vnode_name] = node.node_id
            bisect.insort(self.sorted_keys, h)
        logger.info(
            "Added physical node %s (%d vnodes) to hash ring", node.node_id, num_vnodes
        )

    def remove_node(self, node_id: str) -> None:
        """Remove a physical node and all associated vnodes from the hash ring."""
        if node_id not in self.nodes:
            return
        self.nodes.pop(node_id)
        keys_to_remove = [
            h for h, vn in self.ring.items() if vn.startswith(f"{node_id}#")
        ]
        for h in keys_to_remove:
            vn = self.ring.pop(h, None)
            if vn:
                self.vnode_to_node.pop(vn, None)
            if h in self.sorted_keys:
                self.sorted_keys.remove(h)
        logger.info("Removed physical node %s from hash ring", node_id)

    def get_node_id(self, key: str) -> str | None:
        """Find the target physical node_id for a given string key."""
        if not self.sorted_keys:
            return None
        h = hash_key(key)
        idx = bisect.bisect_right(self.sorted_keys, h)
        if idx == len(self.sorted_keys):
            idx = 0
        target_hash = self.sorted_keys[idx]
        vnode_name = self.ring[target_hash]
        return self.vnode_to_node[vnode_name]

    def get_node(self, key: str) -> NodeConfig | None:
        """Get target physical NodeConfig for a key."""
        node_id = self.get_node_id(key)
        if node_id:
            return self.nodes.get(node_id)
        return None

    def get_healthy_node(self, key: str) -> NodeConfig | None:
        """
        Find the first HEALTHY physical node starting from key's hash ring location.
        If all Qdrant nodes are degraded or down, returns None to trigger pgvector fallback.
        """
        if not self.sorted_keys:
            return None
        h = hash_key(key)
        start_idx = bisect.bisect_right(self.sorted_keys, h)
        n_keys = len(self.sorted_keys)

        visited_nodes: set[str] = set()
        for i in range(n_keys):
            idx = (start_idx + i) % n_keys
            h_val = self.sorted_keys[idx]
            vnode = self.ring[h_val]
            node_id = self.vnode_to_node[vnode]
            if node_id in visited_nodes:
                continue
            visited_nodes.add(node_id)
            node = self.nodes.get(node_id)
            if node and node.status == NodeStatus.HEALTHY:
                return node
        return None

    def get_nodes_for_key(self, key: str, count: int) -> list[NodeConfig]:
        """Get count distinct physical nodes for scatter-gather or replication."""
        if not self.sorted_keys:
            return []
        h = hash_key(key)
        start_idx = bisect.bisect_right(self.sorted_keys, h)
        n_keys = len(self.sorted_keys)

        result: list[NodeConfig] = []
        seen: set[str] = set()

        for i in range(n_keys):
            if len(result) >= count:
                break
            idx = (start_idx + i) % n_keys
            h_val = self.sorted_keys[idx]
            vnode = self.ring[h_val]
            node_id = self.vnode_to_node[vnode]
            if node_id not in seen and node_id in self.nodes:
                seen.add(node_id)
                result.append(self.nodes[node_id])
        return result

    def update_node_status(self, node_id: str, status: NodeStatus) -> None:
        """Update physical node health status."""
        if node_id in self.nodes:
            self.nodes[node_id].status = status
            logger.warning("Node %s status updated to %s", node_id, status.value)

    def get_all_nodes(self) -> list[NodeConfig]:
        """Return all physical nodes registered on ring."""
        return list(self.nodes.values())


class VectorPartitionConfig:
    """Collection partition and sharding configuration for Qdrant cluster & pgvector fallback."""

    def __init__(
        self,
        collection_name: str = "learning_materials",
        dimensions: int = 1536,
        distance_metric: str = "Cosine",
        hnsw_m: int = 16,
        hnsw_ef_construct: int = 64,
        shard_number: int = 4,
        replication_factor: int = 1,
        write_consistency_factor: int = 1,
        on_disk_payload: bool = True,
        pgvector_fallback_enabled: bool = True,
        pgvector_table_name: str = "vector_chunks",
    ) -> None:
        self.collection_name = collection_name
        self.dimensions = dimensions
        self.distance_metric = distance_metric
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct
        self.shard_number = shard_number
        self.replication_factor = replication_factor
        self.write_consistency_factor = write_consistency_factor
        self.on_disk_payload = on_disk_payload
        self.pgvector_fallback_enabled = pgvector_fallback_enabled
        self.pgvector_table_name = pgvector_table_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection_name": self.collection_name,
            "dimensions": self.dimensions,
            "distance_metric": self.distance_metric,
            "hnsw_m": self.hnsw_m,
            "hnsw_ef_construct": self.hnsw_ef_construct,
            "shard_number": self.shard_number,
            "replication_factor": self.replication_factor,
            "write_consistency_factor": self.write_consistency_factor,
            "on_disk_payload": self.on_disk_payload,
            "pgvector_fallback_enabled": self.pgvector_fallback_enabled,
            "pgvector_table_name": self.pgvector_table_name,
        }


class VectorSearchResult(NamedTuple):
    vector_id: str
    tenant_id: str
    score: float
    payload: dict[str, Any]
    source_tier: str  # "qdrant" or "pgvector"
    node_id: str | None


class VectorStorageEngine:
    """
    Dual-tier vector sharding and storage engine.
    Tier 1: PostgreSQL 17 pgvector (1536-dim HNSW cosine indexing)
    Tier 2: Multi-node Qdrant cluster partitioned via consistent hash ring.
    """

    def __init__(
        self,
        ring: ConsistentHashRing | None = None,
        partition_configs: dict[str, VectorPartitionConfig] | None = None,
    ) -> None:
        self.ring = ring or ConsistentHashRing(vnodes_per_node=128)
        self.partition_configs = partition_configs or {
            "learning_materials": VectorPartitionConfig(
                collection_name="learning_materials",
                dimensions=1536,
                distance_metric="Cosine",
            ),
            "vector_chunks": VectorPartitionConfig(
                collection_name="vector_chunks",
                dimensions=1536,
                distance_metric="Cosine",
            ),
        }

    def register_node(
        self,
        node_id: str,
        endpoint: str,
        weight: int = 1,
        status: NodeStatus = NodeStatus.HEALTHY,
    ) -> NodeConfig:
        node = NodeConfig(
            node_id=node_id, endpoint=endpoint, weight=weight, status=status
        )
        self.ring.add_node(node)
        return node

    def unregister_node(self, node_id: str) -> None:
        self.ring.remove_node(node_id)

    def get_target_node(self, tenant_id: str) -> NodeConfig | None:
        return self.ring.get_healthy_node(tenant_id)

    def should_fallback_to_pgvector(self, tenant_id: str) -> bool:
        """Determine if a query should failover to pgvector based on ring status."""
        healthy_node = self.ring.get_healthy_node(tenant_id)
        return healthy_node is None

    async def search(
        self,
        tenant_id: str,
        vector: list[float],
        collection_name: str = "learning_materials",
        top_k: int = 5,
        score_threshold: float = 0.0,
        db_session: Any | None = None,
    ) -> list[VectorSearchResult]:
        """
        Search vector storage with dynamic routing and pgvector failover.
        Attempts primary Qdrant target on hash ring. If node is degraded/down or
        fails, seamlessly switches to pgvector fallback.
        """
        config = self.partition_configs.get(
            collection_name, VectorPartitionConfig(collection_name=collection_name)
        )

        healthy_node = self.ring.get_healthy_node(tenant_id)

        if healthy_node and HAS_QDRANT_CLIENT:
            try:
                results = await self._query_qdrant(
                    healthy_node, config, vector, top_k, score_threshold
                )
                if results is not None:
                    return results
            except (ConnectionError, TimeoutError, OSError, Exception) as e:
                # RZ-20-04 / RZ-22-01: Log and trip to pgvector fallback
                logger.warning(
                    "Qdrant node %s failed (%s), failing over to pgvector",
                    healthy_node.node_id,
                    e,
                )
                self.ring.update_node_status(healthy_node.node_id, NodeStatus.DEGRADED)

        # Fallback to Tier 1 pgvector if enabled
        if config.pgvector_fallback_enabled and db_session is not None:
            return await self._query_pgvector(
                db_session, tenant_id, vector, top_k, score_threshold
            )

        return []

    async def _query_qdrant(
        self,
        node: NodeConfig,
        config: VectorPartitionConfig,
        vector: list[float],
        top_k: int,
        score_threshold: float,
    ) -> list[VectorSearchResult] | None:
        """Execute vector search query against a Qdrant node."""
        if not HAS_QDRANT_CLIENT:
            return None

        try:
            if node._client:
                q_res = node._client.search(
                    collection_name=config.collection_name,
                    query_vector=vector,
                    limit=top_k,
                    score_threshold=score_threshold,
                )
                return [
                    VectorSearchResult(
                        vector_id=str(hit.id),
                        tenant_id=str(hit.payload.get("tenant_id", "")),
                        score=float(hit.score),
                        payload=dict(hit.payload or {}),
                        source_tier="qdrant",
                        node_id=node.node_id,
                    )
                    for hit in q_res
                ]
        except (ConnectionError, TimeoutError, OSError, Exception) as e:
            # RZ-20-04
            logger.error("Qdrant query error on %s: %s", node.node_id, e)
            raise

        return None

    async def _query_pgvector(
        self,
        db_session: Any,
        tenant_id: str,
        vector: list[float],
        top_k: int,
        score_threshold: float,
    ) -> list[VectorSearchResult]:
        """Execute fallback vector query against PostgreSQL pgvector model."""
        from sqlalchemy import select

        from app.models.vector_shard import VectorChunk

        try:
            distance = VectorChunk.embedding.cosine_distance(vector)
            score = (1.0 - distance).label("similarity_score")

            stmt = (
                select(VectorChunk, score)
                .where(
                    VectorChunk.tenant_id == tenant_id,
                    VectorChunk.is_active == True,  # noqa: E712
                    score >= score_threshold,
                )
                .order_by(score.desc())
                .limit(top_k)
            )

            res = await db_session.execute(stmt)
            rows = res.all()

            return [
                VectorSearchResult(
                    vector_id=str(row[0].id),
                    tenant_id=str(row[0].tenant_id),
                    score=float(row[1]),
                    payload=row[0].payload or {"content": row[0].content},
                    source_tier="pgvector",
                    node_id=None,
                )
                for row in rows
            ]
        except (ConnectionError, TimeoutError, OSError, Exception) as e:
            # RZ-20-04
            logger.exception("pgvector fallback query error: %s", e)
            return []

    async def scatter_gather_search(
        self,
        vector: list[float],
        collection_name: str = "learning_materials",
        top_k: int = 5,
        score_threshold: float = 0.0,
        db_session: Any | None = None,
    ) -> list[VectorSearchResult]:
        """
        Scatter-gather search query across all healthy Qdrant nodes in parallel,
        merging top-K results using min-heap bounded by cosine similarity score.
        """
        healthy_nodes = [
            n for n in self.ring.get_all_nodes() if n.status == NodeStatus.HEALTHY
        ]

        if not healthy_nodes and db_session:
            from sqlalchemy import select

            from app.models.vector_shard import VectorChunk

            try:
                distance = VectorChunk.embedding.cosine_distance(vector)
                score = (1.0 - distance).label("similarity_score")
                stmt = (
                    select(VectorChunk, score)
                    .where(
                        VectorChunk.is_active == True,  # noqa: E712
                        score >= score_threshold,
                    )
                    .order_by(score.desc())
                    .limit(top_k)
                )
                res = await db_session.execute(stmt)
                rows = res.all()
                return [
                    VectorSearchResult(
                        vector_id=str(r[0].id),
                        tenant_id=str(r[0].tenant_id),
                        score=float(r[1]),
                        payload=r[0].payload or {"content": r[0].content},
                        source_tier="pgvector",
                        node_id=None,
                    )
                    for r in rows
                ]
            except (ConnectionError, TimeoutError, OSError, Exception) as e:
                # RZ-20-04
                logger.exception("Scatter-gather pgvector error: %s", e)
                return []

        heap: list[tuple[float, int, VectorSearchResult]] = []
        config = self.partition_configs.get(
            collection_name, VectorPartitionConfig(collection_name=collection_name)
        )

        idx = 0
        for node in healthy_nodes:
            try:
                node_results = await self._query_qdrant(
                    node, config, vector, top_k, score_threshold
                )
                if node_results:
                    for item in node_results:
                        idx += 1
                        if len(heap) < top_k:
                            heapq.heappush(heap, (item.score, idx, item))
                        elif item.score > heap[0][0]:
                            heapq.heapreplace(heap, (item.score, idx, item))
            except (ConnectionError, TimeoutError, OSError, Exception) as e:
                # RZ-20-04
                logger.warning("Scatter-gather failed for node %s: %s", node.node_id, e)

        merged = [item for _, _, item in sorted(heap, key=lambda x: x[0], reverse=True)]
        return merged
