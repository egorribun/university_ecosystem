"""Vector 12 GraphQL Extensions Test Suite.

Comprehensive test suite verifying Vector 12 requirements and acceptance criteria:
1. Strict APQ Verification:
   - In production mode, sending a raw unpersisted query string returns a GraphQLError
     stating query is not in allowlist.
   - Sending a valid sha256Hash present in persisted_queries.json successfully executes
     without requiring raw query body.
   - In development / testing / local modes, raw unpersisted queries remain allowed.
   - Introspection queries (__schema, __type) are rejected in production unless present in persisted_queries.json.

2. DataLoader Costing & Token-Bucket Verification:
   - AST analyzer assigns 5x cost multiplier to fields invoking DataLoaders (users, news, events, etc.).
   - Redis Lua script atomically deducts query cost from user token bucket
     (gql:token_bucket:{user_id} or gql:token_bucket:ip:{ip}) prior to resolver execution.
   - When token balance is less than required query cost, execution is aborted pre-validation
     and returns a 429 GraphQLError without executing DB or DataLoader resolvers.
   - In-memory process-local token bucket fallback operates when Redis raises connection errors
     (tagged # RZ-22-01-JUSTIFIED).
"""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphql import GraphQLError, parse
from graphql.language.visitor import visit

import app.graphql.extensions as ext_module
from app.graphql.extensions import (
    _DATALOADER_COST_MULTIPLIER,
    _DATALOADER_FIELD_COST,
    _DATALOADER_FIELD_NAMES,
    _FIELD_COST,
    _LIST_FIELD_COST,
    _TOKEN_BUCKET_CAPACITY,
    _TOKEN_BUCKET_REFILL_RATE,
    _TOKEN_BUCKET_TTL,
    PersistedQueryExtension,
    QueryCostExtension,
    RequestTimeoutExtension,
    _consume_token_bucket,
    _consume_token_bucket_memory,
    _CostVisitor,
    _hash_query,
    _increment_user_cost,
    _load_manifest,
)

# ===========================================================================
# 1. Strict APQ Verification Tests
# ===========================================================================


class TestStrictAPQVerification:
    """Test suite for Requirement 1: Strict APQ Verification across environments."""

    @pytest.mark.asyncio
    async def test_prod_raw_unpersisted_query_rejected(self) -> None:
        """In production mode, sending a raw unpersisted query string raises GraphQLError."""
        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = "query { unpersistedField }"
        ext.execution_context.extensions = None

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(
                ext_module,
                "_query_allowlist",
                {"known_hash_123": "query { allowedQuery }"},
            ),
        ):
            with pytest.raises(
                GraphQLError, match="Query not found in persisted query allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_prod_valid_sha256_hash_executes_without_raw_body(self) -> None:
        """Sending a valid sha256Hash present in persisted_queries.json executes without raw query body."""
        target_query = "query { users { id name } }"
        target_hash = _hash_query(target_query)

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = None
        ext.execution_context.graphql_document = None
        ext.execution_context.extensions = {
            "persistedQuery": {"sha256Hash": target_hash}
        }

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(ext_module, "_query_allowlist", {target_hash: target_query}),
        ):
            async for _ in ext.on_validate():
                pass

            assert ext.execution_context.query == target_query
            assert ext.execution_context.graphql_document is not None

    @pytest.mark.asyncio
    async def test_prod_raw_query_matching_manifest_hash_allowed(self) -> None:
        """In production, sending raw query string whose hash is in allowlist is accepted."""
        query_str = "query { events { title } }"
        query_hash = _hash_query(query_str)

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = query_str
        ext.execution_context.extensions = None

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(ext_module, "_query_allowlist", {query_hash: query_str}),
        ):
            async for _ in ext.on_validate():
                pass

    @pytest.mark.asyncio
    async def test_prod_raw_query_with_mismatched_hash_rejected(self) -> None:
        """In production, sending raw query string with an unknown/mismatched hash raises GraphQLError."""
        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = "query { unknownField }"
        ext.execution_context.extensions = {
            "persistedQuery": {"sha256Hash": "invalid_hash_value_999"}
        }

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(
                ext_module,
                "_query_allowlist",
                {"valid_hash": "query { validField }"},
            ),
        ):
            with pytest.raises(
                GraphQLError, match="Query not found in persisted query allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    @pytest.mark.parametrize("env_name", ["development", "testing", "local"])
    async def test_dev_testing_local_modes_allow_unpersisted_queries(
        self, env_name: str
    ) -> None:
        """In development, testing, and local modes, raw unpersisted queries remain allowed."""
        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = "query { adhocQuery { customField } }"
        ext.execution_context.extensions = None

        with patch("app.core.config.settings.environment", env_name):
            async for _ in ext.on_validate():
                pass

    @pytest.mark.asyncio
    async def test_dev_mode_unknown_hash_without_raw_body_raises(self) -> None:
        """In development mode, sending sha256Hash without raw body where hash is absent from manifest raises."""
        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = None
        ext.execution_context.extensions = {
            "persistedQuery": {"sha256Hash": "non_existent_hash"}
        }

        with patch("app.core.config.settings.environment", "development"):
            with pytest.raises(
                GraphQLError, match="Persisted query not found in allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_prod_introspection_schema_query_rejected(self) -> None:
        """Introspection queries (__schema) are rejected in production unless present in persisted_queries.json."""
        introspection_query = "query Introspect { __schema { types { name } } }"

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = introspection_query
        ext.execution_context.extensions = None

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(
                ext_module, "_query_allowlist", {"allowed_hash": "query { me { id } }"}
            ),
        ):
            with pytest.raises(
                GraphQLError, match="Query not found in persisted query allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_prod_introspection_type_query_rejected(self) -> None:
        """Introspection queries (__type) are rejected in production unless present in persisted_queries.json."""
        introspection_query = (
            'query IntrospectType { __type(name: "User") { name fields { name } } }'
        )

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = introspection_query
        ext.execution_context.extensions = None

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(
                ext_module, "_query_allowlist", {"allowed_hash": "query { me { id } }"}
            ),
        ):
            with pytest.raises(
                GraphQLError, match="Query not found in persisted query allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_prod_introspection_query_allowed_when_in_manifest(self) -> None:
        """Introspection query is accepted in production if its hash is present in persisted_queries.json."""
        introspection_query = (
            "query AllowedIntrospect { __schema { queryType { name } } }"
        )
        introspection_hash = _hash_query(introspection_query)

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = introspection_query
        ext.execution_context.extensions = None

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(
                ext_module,
                "_query_allowlist",
                {introspection_hash: introspection_query},
            ),
        ):
            async for _ in ext.on_validate():
                pass

    @pytest.mark.asyncio
    async def test_prod_missing_manifest_raises(self) -> None:
        """In production mode, missing or empty manifest raises GraphQLError."""
        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = "query { me { id } }"

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(ext_module, "_query_allowlist", {}),
            patch.object(Path, "exists", return_value=False),
        ):
            with pytest.raises(
                GraphQLError, match="Persisted query manifest missing or unreadable"
            ):
                async for _ in ext.on_validate():
                    pass

    def test_hash_query_deterministic_and_trims_whitespace(self) -> None:
        """_hash_query produces SHA-256 hex digest after stripping whitespace."""
        query = "  query { users { id } }  "
        expected = hashlib.sha256(query.strip().encode()).hexdigest()
        assert _hash_query(query) == expected


# ===========================================================================
# 2. DataLoader Costing Tests
# ===========================================================================


class TestDataLoaderCosting:
    """Test suite for Requirement 2: DataLoader 5x cost multiplier AST analysis."""

    def test_dataloader_field_names_cost_5x(self) -> None:
        """DataLoader fields (users, news, events, author, organizer) each receive 5x cost multiplier."""
        query_doc = parse(
            "{ users { id } news { id } events { id } author { id } organizer { id } }"
        )
        visitor = _CostVisitor()
        visit(query_doc, visitor)
        # Each DataLoader field (5) + each scalar id (1) = 6 * 5 = 30
        expected_cost = 5 * (5 + 1)
        assert visitor.cost == expected_cost

    def test_list_field_names_cost_5x(self) -> None:
        """List fields (chats, messages, participants, attachments, followers, following, friends, etc.) cost 5x."""
        query_doc = parse(
            "{ chats { id } messages { text } participants { id } attachments { url } }"
        )
        visitor = _CostVisitor()
        visit(query_doc, visitor)
        # chats(5)+id(1) + messages(5)+text(1) + participants(5)+id(1) + attachments(5)+url(1) = 24
        assert visitor.cost == 24

    def test_scalar_fields_cost_one(self) -> None:
        """Standard scalar fields cost 1 each."""
        query_doc = parse("{ profile { id name email bio avatarUrl } }")
        visitor = _CostVisitor()
        visit(query_doc, visitor)
        # profile(1) + id(1) + name(1) + email(1) + bio(1) + avatarUrl(1) = 6
        assert visitor.cost == 6

    def test_dataloader_and_scalar_combination_costing(self) -> None:
        """Query combining scalar fields and DataLoader fields accumulates accurate weighted cost."""
        query_doc = parse("""
            query GetDashboard {
                currentUser {
                    id
                    email
                    news {
                        id
                        title
                        author {
                            name
                        }
                    }
                    events {
                        id
                        organizer {
                            name
                        }
                    }
                }
            }
        """)
        visitor = _CostVisitor()
        visit(query_doc, visitor)
        # currentUser(1) + id(1) + email(1) = 3
        # news(5) + id(1) + title(1) + author(5) + name(1) = 13
        # events(5) + id(1) + organizer(5) + name(1) = 12
        # Sum = 3 + 13 + 12 = 28
        assert visitor.cost == 28

    def test_fragment_spread_dataloader_costing(self) -> None:
        """Cost visitor traverses named fragment spreads and inline fragments counting DataLoader fields."""
        query_doc = parse("""
            query {
                ...DataLoaderFrag
                ...InlineFrag
            }
            fragment DataLoaderFrag on Query {
                users { id }
            }
            fragment InlineFrag on Query {
                ... on Query {
                    events { id }
                }
            }
        """)
        visitor = _CostVisitor()
        visit(query_doc, visitor)
        # Fragment 1: users(5) + id(1) = 6
        # Fragment 2: events(5) + id(1) = 6
        # Total = 12
        assert visitor.cost == 12

    def test_dataloader_cost_constants_integrity(self) -> None:
        """Verify cost constant relationships."""
        assert _DATALOADER_COST_MULTIPLIER == 5
        assert _DATALOADER_FIELD_COST == _FIELD_COST * 5
        assert _LIST_FIELD_COST == _DATALOADER_FIELD_COST
        assert "users" in _DATALOADER_FIELD_NAMES
        assert "news" in _DATALOADER_FIELD_NAMES
        assert "events" in _DATALOADER_FIELD_NAMES
        assert "author" in _DATALOADER_FIELD_NAMES
        assert "organizer" in _DATALOADER_FIELD_NAMES


# ===========================================================================
# 3. Token-Bucket Rate Limiting & Pre-validation 429 Abort Tests
# ===========================================================================


class TestTokenBucketRateLimiting:
    """Test suite for Requirement 2: Predictive Redis Token Bucket rate limiting & fallback."""

    @pytest.mark.asyncio
    async def test_authenticated_user_bucket_key_format(self) -> None:
        """Authenticated user uses key pattern `gql:token_bucket:{user_id}`."""
        user_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = user_id

        ext = QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ me { id } }")
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = mock_user

        mock_consume = AsyncMock(return_value=(True, 990))
        mock_increment = AsyncMock(return_value=10)

        with (
            patch.object(ext_module, "_consume_token_bucket", mock_consume),
            patch.object(ext_module, "_increment_user_cost", mock_increment),
        ):
            async for _ in ext.on_validate():
                pass

            mock_consume.assert_called_once()
            key = (
                mock_consume.call_args.kwargs.get("key")
                or mock_consume.call_args.args[0]
            )
            assert key == f"gql:token_bucket:{user_id}"

    @pytest.mark.asyncio
    async def test_anonymous_user_client_ip_bucket_key_format(self) -> None:
        """Anonymous user uses client host key pattern `gql:token_bucket:ip:{ip}`."""
        ext = QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ news { id } }")
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = None

        mock_request = MagicMock()
        mock_request.client.host = "203.0.113.45"
        ext.execution_context.context.request = mock_request

        mock_consume = AsyncMock(return_value=(True, 990))
        with patch.object(ext_module, "_consume_token_bucket", mock_consume):
            async for _ in ext.on_validate():
                pass

            mock_consume.assert_called_once()
            key = (
                mock_consume.call_args.kwargs.get("key")
                or mock_consume.call_args.args[0]
            )
            assert key == "gql:token_bucket:ip:203.0.113.45"

    @pytest.mark.asyncio
    async def test_anonymous_user_x_forwarded_for_bucket_key_format(self) -> None:
        """Anonymous user extracts first IP from X-Forwarded-For header if client host unavailable."""
        ext = QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ events { id } }")
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = None

        mock_request = MagicMock()
        mock_request.client = None
        mock_request.headers = {"x-forwarded-for": "198.51.100.12, 10.0.0.1"}
        ext.execution_context.context.request = mock_request

        mock_consume = AsyncMock(return_value=(True, 990))
        with patch.object(ext_module, "_consume_token_bucket", mock_consume):
            async for _ in ext.on_validate():
                pass

            key = (
                mock_consume.call_args.kwargs.get("key")
                or mock_consume.call_args.args[0]
            )
            assert key == "gql:token_bucket:ip:198.51.100.12"

    @pytest.mark.asyncio
    async def test_anonymous_user_default_ip_fallback(self) -> None:
        """Anonymous user falls back to 127.0.0.1 if no request or host available."""
        ext = QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ events { id } }")
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = None
        ext.execution_context.context.request = None

        mock_consume = AsyncMock(return_value=(True, 990))
        with patch.object(ext_module, "_consume_token_bucket", mock_consume):
            async for _ in ext.on_validate():
                pass

            key = (
                mock_consume.call_args.kwargs.get("key")
                or mock_consume.call_args.args[0]
            )
            assert key == "gql:token_bucket:ip:127.0.0.1"

    @pytest.mark.asyncio
    async def test_redis_lua_script_atomic_deduction(self) -> None:
        """_consume_token_bucket calls Redis eval with Lua script and returns success and balance."""
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=[1, 950])

        with patch(
            "app.deps.cache.get_cache_client", AsyncMock(return_value=mock_redis)
        ):
            allowed, remaining = await _consume_token_bucket(
                key="gql:token_bucket:user_123",
                cost=10,
                capacity=_TOKEN_BUCKET_CAPACITY,
                refill_rate=_TOKEN_BUCKET_REFILL_RATE,
                ttl=_TOKEN_BUCKET_TTL,
            )

            assert allowed is True
            assert remaining == 950
            mock_redis.eval.assert_called_once()
            args = mock_redis.eval.call_args.args
            assert args[0] == ext_module._BUCKET_LUA_SCRIPT
            assert args[1] == 1  # numkeys
            assert args[2] == "gql:token_bucket:user_123"
            assert args[3] == 10  # cost

    @pytest.mark.asyncio
    async def test_insufficient_tokens_aborts_pre_validation_with_429(self) -> None:
        """When token balance is insufficient, execution aborts pre-validation with 429 GraphQLError."""
        ext = QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ users { id name } }")
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = None

        # Simulate token bucket rejection (allowed=False, remaining=2)
        mock_consume = AsyncMock(return_value=(False, 2))

        with patch.object(ext_module, "_consume_token_bucket", mock_consume):
            with pytest.raises(GraphQLError) as exc_info:
                async for _ in ext.on_validate():
                    pass

            err = exc_info.value
            assert "GraphQL rate limit exceeded" in str(err)
            assert "exceeds available token bucket balance" in str(err)
            assert err.extensions.get("status_code") == 429
            assert err.extensions.get("http", {}).get("status_code") == 429
            assert err.extensions.get("code") == "RATE_LIMITED"
            assert (
                err.extensions.get("required_cost") == 7
            )  # users(5) + id(1) + name(1) = 7
            assert err.extensions.get("available_tokens") == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "redis_error",
        [
            ConnectionError("Redis connection failed"),
            TimeoutError("Redis timed out"),
            OSError("Socket closed"),
        ],
    )
    async def test_redis_error_triggers_in_memory_fallback(
        self, redis_error: Exception
    ) -> None:
        """When Redis raises ConnectionError/TimeoutError/OSError, fallback to process-local token bucket."""
        with (
            patch(
                "app.deps.cache.get_cache_client",
                AsyncMock(side_effect=redis_error),
            ),
            patch.object(ext_module.logger, "warning") as mock_log,
        ):
            ext_module._memory_token_buckets.clear()
            key = f"gql:token_bucket:fallback_{uuid.uuid4()}"

            allowed, remaining = await _consume_token_bucket(
                key=key,
                cost=25,
                capacity=100,
                refill_rate=10.0,
            )

            assert allowed is True
            assert remaining == 75
            mock_log.assert_called_once()
            assert (
                "falling back to process-local token bucket" in mock_log.call_args[0][0]
            )

    @pytest.mark.asyncio
    async def test_in_memory_token_bucket_refill_and_exhaustion(self) -> None:
        """Direct unit test of _consume_token_bucket_memory capacity, refill rate, and exhaustion."""
        ext_module._memory_token_buckets.clear()
        key = "gql:token_bucket:mem_test"
        now = time.time()

        # 1. Consume 80 out of 100 tokens
        allowed, remaining = await _consume_token_bucket_memory(
            key, cost=80, capacity=100, refill_rate=10.0, now=now
        )
        assert allowed is True
        assert remaining == 20

        # 2. Try consuming 30 tokens immediately -> fails because balance is 20
        allowed, remaining = await _consume_token_bucket_memory(
            key, cost=30, capacity=100, refill_rate=10.0, now=now
        )
        assert allowed is False
        assert remaining == 20

        # 3. Advance time by 2 seconds (refilling 2 * 10 = 20 tokens -> balance 40)
        future_now = now + 2.0
        allowed, remaining = await _consume_token_bucket_memory(
            key, cost=30, capacity=100, refill_rate=10.0, now=future_now
        )
        assert allowed is True
        assert remaining == 10  # 40 - 30 = 10


# ===========================================================================
# 4. Additional Extension Safeguards & Limits
# ===========================================================================


class TestAdditionalExtensionSafeguards:
    """Test suite for max cost, per-user limits, timeout, and manifest loading."""

    @pytest.mark.asyncio
    async def test_query_cost_exceeds_max_allowed_cost_raises(self) -> None:
        """Query cost exceeding _MAX_QUERY_COST (200) raises GraphQLError."""
        # 45 users aliases * 5 = 225 cost > 200
        aliases = " ".join(f"u{i}: users {{ id }}" for i in range(45))
        doc = parse(f"{{ {aliases} }}")

        ext = QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = doc

        with pytest.raises(
            GraphQLError, match="exceeds the maximum allowed cost of 200"
        ):
            async for _ in ext.on_validate():
                pass

    @pytest.mark.asyncio
    async def test_per_user_minute_budget_exceeded_raises(self) -> None:
        """Authenticated user exceeding per-minute cost budget (1000) raises GraphQLError."""
        user_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = user_id

        ext = QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ me { id } }")
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = mock_user

        mock_increment = AsyncMock(return_value=1050)  # Exceeds 1000 budget

        with patch.object(ext_module, "_increment_user_cost", mock_increment):
            with pytest.raises(
                GraphQLError,
                match=r"GraphQL rate limit exceeded\. Budget: 1000 cost/min",
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_increment_user_cost_redis_fallback_to_memory(self) -> None:
        """_increment_user_cost falls back to memory dict when Redis raises connection error."""
        user_id = f"user_{uuid.uuid4()}"
        window = int(time.time() // 60)

        with (
            patch(
                "app.deps.cache.get_cache_client",
                AsyncMock(side_effect=ConnectionError("Redis down")),
            ),
            patch.object(ext_module.logger, "warning") as mock_log,
        ):
            ext_module._user_cost_memory.clear()
            total = await _increment_user_cost(user_id, 50, window)
            assert total == 50
            mock_log.assert_called_once()
            assert "falling back to per-process counter" in mock_log.call_args[0][0]

    @pytest.mark.asyncio
    async def test_request_timeout_extension_execution_timeout(self) -> None:
        """RequestTimeoutExtension raises GraphQLError when execution exceeds timeout."""
        ext = RequestTimeoutExtension()

        class _DeterministicTimeout:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, _exc_type, _exc, _traceback) -> bool:
                return False

        # Inject the timeout exception without scheduling a wall-clock
        # cancellation. This keeps the test deterministic under mutmut's
        # instrumented stats runner while exercising the production handler.
        with patch.object(
            ext_module.asyncio,
            "timeout",
            return_value=_DeterministicTimeout(),
        ):
            gen = ext.on_execute()
            await gen.__anext__()
            with pytest.raises(
                GraphQLError,
                match=r"Request exceeded the maximum execution time of 30 seconds",
            ):
                await gen.athrow(TimeoutError)

    def test_load_manifest_corrupted_json(self, tmp_path: Path) -> None:
        """_load_manifest handles corrupted JSON files gracefully."""
        corrupt_file = tmp_path / "persisted_queries.json"
        corrupt_file.write_text("{ invalid json ...")

        with patch("app.graphql.extensions._MANIFEST_PATH", corrupt_file):
            ext_module._query_allowlist = None
            manifest = _load_manifest()
            assert manifest == {}

    def test_load_manifest_non_existent_file(self) -> None:
        """_load_manifest returns empty dict when file does not exist."""
        non_existent = Path("/path/does/not/exist/persisted_queries.json")

        with patch("app.graphql.extensions._MANIFEST_PATH", non_existent):
            ext_module._query_allowlist = None
            manifest = _load_manifest()
            assert manifest == {}
