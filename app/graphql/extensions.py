"""Custom Strawberry schema extensions for the university ecosystem GraphQL API.

D-06 (audit 2026-03-08): Adds query complexity/cost analysis to prevent
resource-exhaustive queries that evade the existing depth and token limits.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
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
    except Exception:  # noqa: S110  # nosec B110
        # Redis unavailable — fall through to per-process in-memory counter.
        # In multi-instance deployments this under-counts, but it still provides
        # meaningful protection against single-client abuse within a process.
        pass

    async with _user_cost_lock:
        stored_cost, stored_minute = _user_cost_memory.get(user_id, (0, window_minute))
        if stored_minute != window_minute:
            stored_cost = 0  # new window — reset counter
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
        if getattr(self.execution_context, "errors", None):
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


__all__ = ["QueryCostExtension"]
