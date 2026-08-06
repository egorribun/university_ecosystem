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

# R2: DataLoader fields from app/graphql/dataloaders.py and resolvers resolving via DataLoaders
_DATALOADER_FIELD_NAMES: frozenset[str] = (
    frozenset(
        {
            "users",
            "news",
            "events",
            "author",
            "organizer",
        }
    )
    | _LIST_FIELD_NAMES
)

_FIELD_COST: int = 1  # scalar / single-object field standard cost
_DATALOADER_COST_MULTIPLIER: int = 5  # 5x cost multiplier for DataLoader fields
_DATALOADER_FIELD_COST: int = _FIELD_COST * _DATALOADER_COST_MULTIPLIER  # 5
_LIST_FIELD_COST: int = _DATALOADER_FIELD_COST  # backward-compatibility alias
_MAX_QUERY_COST: int = 200  # vetted against current schema; increase as needed

# TD-14-03 (audit 2026-03-23): Per-user cost budget per 60-second tumbling window.
_MAX_USER_COST_PER_MINUTE: int = 1_000

# R3: Token Bucket Rate Limiting configuration
_TOKEN_BUCKET_CAPACITY: int = 1000
_TOKEN_BUCKET_REFILL_RATE: float = 50.0  # tokens per second
_TOKEN_BUCKET_TTL: int = 3600  # 1 hour key TTL in Redis

_BUCKET_LUA_SCRIPT: str = """
local key = KEYS[1]
local cost = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local data = redis.call("HMGET", key, "tokens", "last_updated")
local tokens = tonumber(data[1])
local last_updated = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_updated = now
else
    local delta = math.max(0, now - last_updated)
    tokens = math.min(capacity, tokens + delta * refill_rate)
    last_updated = now
end

if tokens >= cost then
    tokens = tokens - cost
    redis.call("HMSET", key, "tokens", tokens, "last_updated", last_updated)
    redis.call("EXPIRE", key, ttl)
    return {1, math.floor(tokens)}
else
    redis.call("HMSET", key, "tokens", tokens, "last_updated", last_updated)
    redis.call("EXPIRE", key, ttl)
    return {0, math.floor(tokens)}
end
"""

# In-memory fallback for per-user cost quota when Redis is unavailable.
_user_cost_memory: dict[str, tuple[int, int]] = {}
_user_cost_lock = asyncio.Lock()

# R3: In-memory fallback for token bucket
_memory_token_buckets: dict[str, tuple[float, float]] = {}
_memory_token_bucket_lock = asyncio.Lock()


async def _consume_token_bucket_memory(
    key: str, cost: int, capacity: int, refill_rate: float, now: float
) -> tuple[bool, int]:
    """Process-local token bucket consumption fallback."""
    async with _memory_token_bucket_lock:
        tokens, last_updated = _memory_token_buckets.get(key, (float(capacity), now))
        delta = max(0.0, now - last_updated)
        tokens = min(float(capacity), tokens + delta * refill_rate)
        last_updated = now

        if tokens >= cost:
            tokens -= cost
            _memory_token_buckets[key] = (tokens, last_updated)
            return True, int(tokens)
        else:
            _memory_token_buckets[key] = (tokens, last_updated)
            return False, int(tokens)


async def _consume_token_bucket(
    key: str,
    cost: int,
    capacity: int = _TOKEN_BUCKET_CAPACITY,
    refill_rate: float = _TOKEN_BUCKET_REFILL_RATE,
    ttl: int = _TOKEN_BUCKET_TTL,
) -> tuple[bool, int]:
    """Deduct cost from Redis token bucket atomically via Lua script.

    Key patterns:
    - Authenticated users: `gql:token_bucket:{user_id}`
    - Anonymous users: `gql:token_bucket:ip:{ip}`

    Falls back to process-local token bucket on Redis connection/timeout/scripting error.
    Returns (success: bool, remaining_tokens: int).
    """
    try:
        from redis.exceptions import ResponseError
    except ImportError:
        ResponseError = OSError  # type: ignore[misc, assignment]

    now = time.time()
    try:
        from app.deps.cache import get_cache_client

        redis = await get_cache_client()
        res = await redis.eval(  # type: ignore[no-untyped-call]
            _BUCKET_LUA_SCRIPT,
            1,
            key,
            cost,
            capacity,
            refill_rate,
            now,
            ttl,
        )
        if isinstance(res, (list, tuple)) and len(res) >= 2:
            return bool(int(res[0])), int(res[1])
        return await _consume_token_bucket_memory(key, cost, capacity, refill_rate, now)
    except (
        ConnectionError,
        TimeoutError,
        OSError,
        ResponseError,
    ):  # RZ-22-01-JUSTIFIED: Fall back to process-local token bucket on Redis error
        logger.warning(
            "GraphQL token bucket falling back to process-local token bucket",
            extra={"key": key, "cost": cost},
        )
        return await _consume_token_bucket_memory(key, cost, capacity, refill_rate, now)


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
    Applies a 5x cost multiplier for fields invoking DataLoaders from
    app/graphql/dataloaders.py or fields resolving via DataLoaders.
    """

    def __init__(self) -> None:
        super().__init__()
        self.cost: int = 0

    def enter_field(self, node: FieldNode, *_args: object) -> None:
        name = node.name.value
        if name in _DATALOADER_FIELD_NAMES or name in _LIST_FIELD_NAMES:
            self.cost += _DATALOADER_FIELD_COST
        else:
            self.cost += _FIELD_COST


class QueryCostExtension(SchemaExtension):
    """Reject GraphQL operations whose estimated cost exceeds _MAX_QUERY_COST or token bucket balance.

    Evaluation happens in on_validate() — after parsing, before any DB
    round-trip or resolver / DataLoader execution — so high-cost or rate-limited
    queries are rejected pre-validation.
    """

    async def on_validate(self) -> AsyncGenerator[None]:
        yield  # let QueryDepthLimiter, MaxTokensLimiter, and other rules run first

        # If prior validators already rejected the query, skip cost analysis.
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

        context = getattr(self.execution_context, "context", None)
        current_user = getattr(context, "current_user", None)
        request = getattr(context, "request", None)

        if current_user is not None and getattr(current_user, "id", None) is not None:
            user_id = str(current_user.id)
            bucket_key = f"gql:token_bucket:{user_id}"
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
        else:
            ip = None
            if request is not None:
                client = getattr(request, "client", None)
                if client is not None and getattr(client, "host", None):
                    ip = client.host
                if not ip:
                    headers = getattr(request, "headers", {})
                    forwarded = headers.get("x-forwarded-for") or headers.get(
                        "X-Forwarded-For"
                    )
                    if forwarded:
                        ip = forwarded.split(",")[0].strip()
            if not ip:
                ip = "127.0.0.1"
            bucket_key = f"gql:token_bucket:ip:{ip}"

        allowed, remaining_tokens = await _consume_token_bucket(
            key=bucket_key,
            cost=cost,
            capacity=_TOKEN_BUCKET_CAPACITY,
            refill_rate=_TOKEN_BUCKET_REFILL_RATE,
        )

        if not allowed:
            logger.warning(
                "GraphQL quota exceeded for key=%s query_cost=%d remaining_balance=%d max_capacity=%d",  # pragma: allowlist secret
                bucket_key,
                cost,
                remaining_tokens,
                _TOKEN_BUCKET_CAPACITY,
            )
            raise GraphQLError(
                f"GraphQL rate limit exceeded: required query cost {cost} exceeds available token bucket balance ({remaining_tokens} tokens).",
                extensions={
                    "http": {"status_code": 429},
                    "code": "RATE_LIMITED",
                    "status_code": 429,
                    "required_cost": cost,
                    "available_tokens": remaining_tokens,
                },
            )

        logger.debug(
            "GraphQL query cost=%d (max=%d, remaining=%d)",
            cost,
            _MAX_QUERY_COST,
            remaining_tokens,
        )


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
_MANIFEST_PATH = Path(__file__).resolve().parent / "persisted_queries.json"

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
                data = json.loads(_MANIFEST_PATH.read_text("utf-8"))
                if isinstance(data, dict):
                    _query_allowlist = {str(k): str(v) for k, v in data.items()}
                else:
                    _query_allowlist = {}
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
    SHA-256 hash appears in ``persisted_queries.json`` are accepted.  This
    eliminates arbitrary query execution and reduces the attack surface to
    a known, reviewed set of operations.

    In development/testing the extension allows unpersisted queries, but
    resolves persisted query hashes if present in ``persisted_queries.json``.
    """

    async def on_validate(self) -> AsyncGenerator[None]:
        from graphql import parse

        from app.core.config import settings

        # Determine environment
        env = str(getattr(settings, "environment", "production")).lower()
        is_dev = env in {"development", "testing", "local"}

        raw_query = getattr(self.execution_context, "query", None)
        if raw_query is not None and not isinstance(raw_query, str):
            raw_query = str(raw_query) if raw_query else ""

        extensions = getattr(self.execution_context, "extensions", None) or {}
        pq = (
            extensions.get("persistedQuery", {}) if isinstance(extensions, dict) else {}
        )
        client_hash = pq.get("sha256Hash", "") if isinstance(pq, dict) else ""
        if not isinstance(client_hash, str):
            client_hash = str(client_hash) if client_hash else ""

        manifest = _load_manifest()

        # Before yield: resolve APQ hash-only query if present in manifest
        if not raw_query and client_hash and client_hash in manifest:
            resolved_query = manifest[client_hash]
            self.execution_context.query = resolved_query
            if getattr(self.execution_context, "graphql_document", None) is None:
                try:
                    self.execution_context.graphql_document = parse(resolved_query)
                except (
                    Exception
                ) as exc:  # RZ-22-01-JUSTIFIED: invalid query syntax fallback
                    logger.debug("APQ query AST parse failed: %s", exc)
            raw_query = resolved_query

        yield

        # After yield: perform allowlist validation
        if is_dev:
            # Development / testing / local environment:
            # - Raw unpersisted queries remain allowed.
            # - If sha256Hash was passed without raw query body and not found in manifest:
            if (
                not getattr(self.execution_context, "query", None)
                and client_hash
                and client_hash not in manifest
            ):
                raise GraphQLError("Persisted query not found in allowlist")
            return

        # Production environment:
        # Require persisted_queries.json manifest to exist and be readable/non-empty.
        if (
            not _MANIFEST_PATH.exists()
            or not manifest
            or not isinstance(manifest, dict)
        ):
            raise GraphQLError("Persisted query manifest missing or unreadable")

        current_query = getattr(self.execution_context, "query", None)
        if current_query is not None and not isinstance(current_query, str):
            current_query = str(current_query) if current_query else ""

        # 1. APQ Hash-only Query (request contains sha256Hash without raw query body)
        if not current_query and client_hash:
            if client_hash not in manifest:
                raise GraphQLError("Persisted query not found in allowlist")

        # 2. Raw query string provided
        elif current_query:
            computed_hash = _hash_query(current_query)
            query_stripped = current_query.strip()

            is_in_allowlist = (
                (client_hash and client_hash in manifest)
                or (computed_hash in manifest)
                or (current_query in manifest)
                or (query_stripped in manifest)
            )

            if not is_in_allowlist:
                raise GraphQLError("Query not found in persisted query allowlist")

        # 3. Neither raw query nor client_hash provided
        else:
            raise GraphQLError("Persisted query not found in allowlist")


__all__ = ["PersistedQueryExtension", "QueryCostExtension", "RequestTimeoutExtension"]
