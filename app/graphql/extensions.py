"""Custom Strawberry schema extensions for the university ecosystem GraphQL API.

D-06 (audit 2026-03-08): Adds query complexity/cost analysis to prevent
resource-exhaustive queries that evade the existing depth and token limits.

MOD-21-02 (audit 2026-03-25 Wave 21): Adds persisted-query allowlist that
rejects unknown queries in production — eliminates arbitrary query execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING

from graphql import GraphQLError
from graphql.language.ast import FieldNode
from graphql.language.visitor import Visitor, visit
from strawberry.extensions import SchemaExtension

from app.core.logging import get_logger

if TYPE_CHECKING:
    from graphql.language.ast import DocumentNode

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Cost table — fields whose resolution is O(N) or triggers nested queries.
# All other fields cost _FIELD_COST (1).  Adjust as resolvers evolve.
# ---------------------------------------------------------------------------
_LIST_FIELD_NAMES: frozenset[str] = frozenset(
    {
        # Chat domain
        "chats",
        "messages",
        "participants",
        "attachments",
        # User/social domain
        "users",
        "followers",
        "following",
        "friends",
        # Generic pagination containers (Relay-style)
        "edges",
        "nodes",
        "items",
        "results",
        # Presence / notification lists
        "presence",
        "notifications",
        "events",
    }
)

_FIELD_COST: int = 1  # scalar / single-object field
_LIST_FIELD_COST: int = 5  # list field — O(N) resolver / DataLoader fan-out
_MAX_QUERY_COST: int = 200  # vetted against current schema; increase as needed

# TD-14-03 (audit 2026-03-23): Per-user cost budget per 60-second tumbling window.
# A single query may cost up to _MAX_QUERY_COST (200), but sustained batching of
# 200-cost queries would exhaust the connection pool. 1 000 cost/min ≈ 5 max-cost
# queries per minute per user — generous for normal usage, blocks abuse.
_MAX_USER_COST_PER_MINUTE: int = 1_000

# In-memory fallback for per-user cost quota when Redis is unavailable.
# {user_id: (accumulated_cost, window_minute)} — window_minute = int(time.time() // 60)
_user_cost_memory: dict[str, tuple[int, int]] = {}
_user_cost_lock = asyncio.Lock()


async def _increment_user_cost(user_id: str, cost: int, window_minute: int) -> int:
    """Increment the user's query-cost counter for the current minute window.

    Uses Redis INCRBY + EXPIRE (pipeline) for multi-instance accuracy.
    Falls back to a process-local dict when Redis is unavailable.

    Returns the new accumulated cost total for this window.
    """
    redis_key = f"gql:cost:{user_id}:{window_minute}"
    try:
        from app.deps.cache import get_cache_client

        redis = await get_cache_client()
        pipe = redis.pipeline(transaction=True)
        pipe.incrby(redis_key, cost)
        # 2-minute TTL: current window + next window so the key is never orphaned
        pipe.expire(redis_key, 120)
        results = await pipe.execute()
        return int(results[0])
    except (ConnectionError, TimeoutError, OSError):  # nosec B110  # RZ-28-01 + PERF-25-01 + RZ-22-01
        # PERF-25-01: Structured log so operators detect degraded cost tracking.
        logger.warning(
            "GraphQL cost tracking falling back to per-process counter",
            extra={"user_id": user_id, "cost": cost},
        )

    async with _user_cost_lock:
        stored_cost, stored_minute = _user_cost_memory.get(user_id, (0, window_minute))
        if stored_minute != window_minute:
            # New window — evict stale entries from previous windows
            _user_cost_memory.clear()
            stored_cost = 0
        elif len(_user_cost_memory) > 10_000:
            _user_cost_memory.clear()
            stored_cost = 0
        new_total = stored_cost + cost
        _user_cost_memory[user_id] = (new_total, window_minute)
    return new_total


class _CostVisitor(Visitor):
    """graphql-core AST visitor that accumulates field-level query cost.

    Traverses the full document including inline fragments and named fragment
    spreads — which ``MaxTokensLimiter`` does not fully expand.
    """

    def __init__(self) -> None:
        super().__init__()
        self.cost: int = 0

    def enter_field(self, node: FieldNode, *_args: object) -> None:
        name = node.name.value
        self.cost += _LIST_FIELD_COST if name in _LIST_FIELD_NAMES else _FIELD_COST


class QueryCostExtension(SchemaExtension):
    """Reject GraphQL operations whose estimated cost exceeds _MAX_QUERY_COST.

    D-06 (audit 2026-03-08): Complements QueryDepthLimiter (structural nesting)
    and MaxTokensLimiter (raw token budget) with a semantic cost model that
    weights list-returning fields (O(N) resolvers / DataLoader fan-outs) more
    heavily than scalar fields.

    Evaluation happens in on_validate() — after parsing, before any DB
    round-trip — so high-cost queries are rejected cheaply.  Errors from
    the existing depth/token limiters are respected: if they already rejected
    the query, cost analysis is skipped.
    """

    async def on_validate(self) -> AsyncGenerator[None]:
        yield  # let QueryDepthLimiter, MaxTokensLimiter, and other rules run first

        # If prior validators already rejected the query, skip cost analysis.
        # Use getattr for compatibility — execution_context.errors is not
        # guaranteed to exist during the validation phase in all Strawberry versions.
        if getattr(self.execution_context, "pre_execution_errors", None):
            return

        document: DocumentNode | None = getattr(
            self.execution_context, "graphql_document", None
        )
        if document is None:
            return

        visitor = _CostVisitor()
        visit(document, visitor)
        cost = visitor.cost

        if cost > _MAX_QUERY_COST:
            logger.warning(
                "GraphQL query rejected: cost=%d exceeds max=%d",
                cost,
                _MAX_QUERY_COST,
            )
            # Raise GraphQLError — Strawberry's extension runner catches it and
            # adds it to the query error list without crashing the server.
            raise GraphQLError(
                f"Query cost {cost} exceeds the maximum allowed cost of "
                f"{_MAX_QUERY_COST}. Reduce the number of requested fields, "
                "especially list fields (chats, messages, users, etc.)."
            )

        # TD-14-03 (audit 2026-03-23): Per-user minute budget.
        # Only applies to authenticated users — anonymous requests are already
        # guarded by per-IP rate limiting at the gateway layer.
        context = getattr(self.execution_context, "context", None)
        current_user = getattr(context, "current_user", None)
        if current_user is not None:
            user_id = str(current_user.id)
            window_minute = int(time.time() // 60)
            new_total = await _increment_user_cost(user_id, cost, window_minute)
            if new_total > _MAX_USER_COST_PER_MINUTE:
                logger.warning(
                    "GraphQL per-user rate limit hit: user=%s cost=%d total_this_minute=%d",
                    user_id,
                    cost,
                    new_total,
                )
                raise GraphQLError(
                    f"GraphQL rate limit exceeded. Budget: {_MAX_USER_COST_PER_MINUTE} "
                    "cost/min. Reduce query frequency or complexity and try again."
                )

        logger.debug("GraphQL query cost=%d (max=%d)", cost, _MAX_QUERY_COST)


class RequestTimeoutExtension(SchemaExtension):
    """Hard deadline for the entire GraphQL execution phase.

    RZ-21-04 (audit 2026-03-25 Wave 21): Individual SQL statements carry a
    15-second ``command_timeout``, but a single GraphQL request can chain
    multiple sequential resolvers (each potentially hitting that 15 s ceiling).
    Without a request-level timeout a crafted query could hold a DB pool slot
    and an ASGI worker for minutes.

    30 seconds is generous for any realistic frontend query while capping the
    worst-case resource hold time.
    """

    TIMEOUT_SECONDS: int = 30

    async def on_execute(self) -> AsyncGenerator[None]:
        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                yield
        except TimeoutError:  # pragma: no mutate
            logger.warning(
                "graphql_request_timeout",
                extra={"timeout_seconds": self.TIMEOUT_SECONDS},
            )
            raise GraphQLError(
                "Request exceeded the maximum execution time of "
                f"{self.TIMEOUT_SECONDS} seconds."
            ) from None


# ---------------------------------------------------------------------------
# MOD-21-02: Persisted Query Allowlist
# ---------------------------------------------------------------------------

# Path to the query manifest generated by the frontend build.
# Format: {"<sha256-hex>": "<original-query-string>", ...}
_MANIFEST_PATH = Path(__file__).resolve().parent / "query-manifest.json"

_query_allowlist: dict[str, str] | None = None
_manifest_lock = threading.Lock()  # RZ-25-05: protect lazy manifest load


def _load_manifest() -> dict[str, str]:
    """Load the persisted-query manifest from disk (lazy, cached)."""
    global _query_allowlist
    if _query_allowlist is not None:
        return _query_allowlist
    with _manifest_lock:  # RZ-25-05: double-checked locking to prevent concurrent loads
        if _query_allowlist is not None:
            return _query_allowlist  # type: ignore[unreachable]  # RZ-25-05: concurrent double-check
        if _MANIFEST_PATH.exists():
            try:
                _query_allowlist = json.loads(_MANIFEST_PATH.read_text("utf-8"))
                logger.info(
                    "Loaded %d persisted queries from %s",
                    len(_query_allowlist),
                    _MANIFEST_PATH,
                )
            except (
                OSError,
                ValueError,
                KeyError,
            ):  # RZ-26-01 + RZ-22-01: narrowed — JSON/file errors
                logger.warning(
                    "Failed to load query manifest — persisted queries disabled"
                )
                _query_allowlist = {}
        else:
            _query_allowlist = {}
        return _query_allowlist


def _hash_query(query: str) -> str:
    """SHA-256 hash of the normalised query string."""
    return hashlib.sha256(query.strip().encode()).hexdigest()


class PersistedQueryExtension(SchemaExtension):
    """Reject unknown queries in production when a manifest is present.

    MOD-21-02 (audit 2026-03-25 Wave 21): In production, only queries whose
    SHA-256 hash appears in ``query-manifest.json`` are accepted.  This
    eliminates arbitrary query execution and reduces the attack surface to
    a known, reviewed set of operations.

    In development/testing the extension is a no-op (all queries accepted).

    Frontend integration:
    1. ``vite build`` extracts all GraphQL operations → ``query-manifest.json``
    2. Deploy the manifest alongside the backend
    3. Clients send ``extensions: { persistedQuery: { sha256Hash: "..." } }``
       OR the full query body (the extension hashes it server-side)
    """

    async def on_validate(self) -> AsyncGenerator[None]:
        yield  # let other validators run first

        from app.core.config import settings

        if settings.environment in {"development", "testing", "local"}:
            return

        manifest = _load_manifest()
        if not manifest:
            return  # no manifest → allow all (graceful degradation)

        query = getattr(self.execution_context, "query", None)
        if not query:
            return

        # Check the extensions block for a client-provided hash first.
        extensions = getattr(self.execution_context, "extensions", None) or {}
        pq = (
            extensions.get("persistedQuery", {}) if isinstance(extensions, dict) else {}
        )
        client_hash = pq.get("sha256Hash", "") if isinstance(pq, dict) else ""

        query_hash = client_hash or _hash_query(query)

        if query_hash not in manifest:
            logger.warning(
                "Rejected unknown query (hash=%s): %s",
                query_hash[:16],
                query[:80],
            )
            raise GraphQLError(
                "This query is not in the persisted-query allowlist. "
                "Use a known operation or update the query manifest."
            )


__all__ = ["PersistedQueryExtension", "QueryCostExtension", "RequestTimeoutExtension"]
