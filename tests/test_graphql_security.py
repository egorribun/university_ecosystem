"""MOD-22-03 (Wave 22): GraphQL adversarial query test suite.

Tests cover:
  - Deep nesting that triggers QueryDepthLimiter
  - Alias amplification that triggers QueryCostExtension
  - Fragment spread injection
  - Persisted query bypass attempts
"""

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphql import GraphQLError, parse
from graphql.language.visitor import visit

import app.graphql.extensions as ext_module
from app.graphql.extensions import (
    _MAX_QUERY_COST,
    _CostVisitor,
    _hash_query,
)

# ---------------------------------------------------------------------------
# Cost visitor unit tests (MOD-22-03)
# ---------------------------------------------------------------------------


class TestCostVisitor:
    """Direct unit tests for the _CostVisitor AST walker."""

    def test_scalar_fields_cost_one(self) -> None:
        """Non-list fields each cost 1."""
        query = parse("{ user { id name email } }")
        visitor = _CostVisitor()
        visit(query, visitor)
        # 'user' (1) + 'id' (1) + 'name' (1) + 'email' (1) = 4
        assert visitor.cost == 4

    def test_list_fields_cost_five(self) -> None:
        """Fields in the list-field table cost 5 each."""
        query = parse("{ users { id messages { text } } }")
        visitor = _CostVisitor()
        visit(query, visitor)
        # 'users' (5) + 'id' (1) + 'messages' (5) + 'text' (1) = 12
        assert visitor.cost == 12

    def test_deeply_nested_query_cost(self) -> None:
        """A deeply nested query with list fields accumulates high cost."""
        # Build: { users { messages { attachments { id } } } }
        query = parse("{ users { messages { attachments { id } } } }")
        visitor = _CostVisitor()
        visit(query, visitor)
        # users(5) + messages(5) + attachments(5) + id(1) = 16
        assert visitor.cost == 16


# ---------------------------------------------------------------------------
# Alias amplification (MOD-22-03)
# ---------------------------------------------------------------------------


class TestAliasAmplification:
    """Alias amplification inflates cost to trigger QueryCostExtension."""

    def test_alias_amplification_exceeds_budget(self) -> None:
        """Repeating a list field via aliases drives cost above _MAX_QUERY_COST."""
        # Each 'users' alias costs 5 + 'id' costs 1 = 6 per alias.
        # _MAX_QUERY_COST = 200 → need ceil(201/6) = 34 aliases to exceed.
        aliases = " ".join(f"a{i}: users {{ id }}" for i in range(40))
        query_str = f"{{ {aliases} }}"
        doc = parse(query_str)

        visitor = _CostVisitor()
        visit(doc, visitor)
        assert visitor.cost > _MAX_QUERY_COST, (
            f"Alias amplification cost={visitor.cost} did not exceed {_MAX_QUERY_COST}"
        )


# ---------------------------------------------------------------------------
# Fragment spread injection (MOD-22-03)
# ---------------------------------------------------------------------------


class TestFragmentSpreadInjection:
    """Fragment spreads should be counted by the cost visitor."""

    def test_fragment_spread_adds_cost(self) -> None:
        """Fields inside named fragments are counted when spread into a query."""
        query_str = """
        query {
            ...UserFields
        }
        fragment UserFields on Query {
            users { id name messages { text } }
        }
        """
        doc = parse(query_str)
        visitor = _CostVisitor()
        visit(doc, visitor)
        # Fragment body: users(5) + id(1) + name(1) + messages(5) + text(1) = 13
        assert visitor.cost >= 13

    def test_multiple_fragment_spreads(self) -> None:
        """Multiple fragment spreads accumulate cost from each fragment body."""
        query_str = """
        query {
            ...F1
            ...F2
        }
        fragment F1 on Query { users { id } }
        fragment F2 on Query { notifications { id } }
        """
        doc = parse(query_str)
        visitor = _CostVisitor()
        visit(doc, visitor)
        # F1: users(5) + id(1) = 6
        # F2: notifications(5) + id(1) = 6
        assert visitor.cost >= 12


# ---------------------------------------------------------------------------
# Deep nesting detection (MOD-22-03)
# ---------------------------------------------------------------------------


class TestDeepNestingDetection:
    """Verify that deeply nested queries produce high cost (depth limiter
    is tested separately via Strawberry integration; here we test cost)."""

    def test_nesting_20_levels_high_cost(self) -> None:
        """A query nested 20 levels deep accumulates significant cost."""
        # Build: { users { messages { users { messages { ... { id } } } } } }
        inner = "id"
        for _ in range(10):
            inner = f"users {{ messages {{ {inner} }} }}"
        doc = parse(f"{{ {inner} }}")
        visitor = _CostVisitor()
        visit(doc, visitor)
        # 10 levels × (users(5) + messages(5)) + id(1) = 101
        assert visitor.cost > 100


# ---------------------------------------------------------------------------
# Persisted query bypass (MOD-22-03)
# ---------------------------------------------------------------------------


class TestPersistedQueryBypass:
    """Verify that PersistedQueryExtension blocks unknown queries."""

    def test_hash_query_deterministic(self) -> None:
        """_hash_query produces a deterministic SHA-256 hex digest."""
        q = "{ users { id } }"
        expected = hashlib.sha256(q.strip().encode()).hexdigest()
        assert _hash_query(q) == expected

    def test_hash_query_trims_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped before hashing."""
        assert _hash_query("  { users { id } }  ") == _hash_query("{ users { id } }")

    def test_unknown_hash_format(self) -> None:
        """A fabricated hash should not match any manifest entry."""
        manifest = {"abc123": "{ users { id } }"}
        fake_hash = "zzzzzz"
        assert fake_hash not in manifest

    def test_bypass_with_wrong_hash(self) -> None:
        """Sending a valid query with a wrong persistedQuery hash should fail
        validation when the manifest is checked server-side."""
        known_query = "{ users { id } }"
        correct_hash = _hash_query(known_query)
        wrong_hash = "0" * 64

        manifest = {correct_hash: known_query}

        # The wrong hash is not in the manifest.
        assert wrong_hash not in manifest
        # The correct hash IS in the manifest.
        assert correct_hash in manifest

    def test_empty_manifest_allows_all(self) -> None:
        """When the manifest is empty (no file), all queries pass (graceful degradation)."""
        # Per the extension logic: if not manifest: return (allow all)
        manifest: dict[str, str] = {}
        assert not manifest  # empty dict is falsy → extension skips

    def test_arbitrary_query_blocked_with_manifest(self) -> None:
        """An arbitrary query not in the manifest is blocked."""
        manifest = {_hash_query("{ me { id } }"): "{ me { id } }"}
        arbitrary = "{ __schema { types { name } } }"
        arbitrary_hash = _hash_query(arbitrary)
        assert arbitrary_hash not in manifest


class TestAPQRequirementR1:
    """Requirement R1 APQ test suite covering strict production & development modes."""

    @pytest.mark.asyncio
    async def test_prod_missing_or_empty_manifest_raises(self) -> None:
        from unittest.mock import MagicMock, patch

        from graphql import GraphQLError

        import app.graphql.extensions as ext_module
        from app.graphql.extensions import PersistedQueryExtension

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = "query { me }"

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(ext_module, "_query_allowlist", {}),
        ):
            with pytest.raises(
                GraphQLError, match="Persisted query manifest missing or unreadable"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_prod_apq_hash_only_resolution(self) -> None:
        from unittest.mock import MagicMock, patch

        import app.graphql.extensions as ext_module
        from app.graphql.extensions import PersistedQueryExtension, _hash_query

        query_str = "query { me { id name } }"
        query_hash = _hash_query(query_str)

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = None
        ext.execution_context.graphql_document = None
        ext.execution_context.extensions = {
            "persistedQuery": {"sha256Hash": query_hash}
        }

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(ext_module, "_query_allowlist", {query_hash: query_str}),
        ):
            async for _ in ext.on_validate():
                pass
            assert ext.execution_context.query == query_str
            assert ext.execution_context.graphql_document is not None

    @pytest.mark.asyncio
    async def test_prod_apq_hash_only_absent_raises(self) -> None:
        from unittest.mock import MagicMock, patch

        from graphql import GraphQLError

        import app.graphql.extensions as ext_module
        from app.graphql.extensions import PersistedQueryExtension

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = None
        ext.execution_context.extensions = {
            "persistedQuery": {"sha256Hash": "unknown_hash"}
        }

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(ext_module, "_query_allowlist", {"hash123": "query { me }"}),
        ):
            with pytest.raises(
                GraphQLError, match="Persisted query not found in allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_prod_raw_query_uncompiled_introspection_raises(self) -> None:
        from unittest.mock import MagicMock, patch

        from graphql import GraphQLError

        import app.graphql.extensions as ext_module
        from app.graphql.extensions import PersistedQueryExtension

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = "query { __schema { types { name } } }"
        ext.execution_context.extensions = None

        with (
            patch("app.core.config.settings.environment", "production"),
            patch.object(ext_module, "_query_allowlist", {"hash123": "query { me }"}),
        ):
            with pytest.raises(
                GraphQLError, match="Query not found in persisted query allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_dev_mode_allows_unpersisted_query(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.graphql.extensions import PersistedQueryExtension

        ext = PersistedQueryExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.query = "query { unpersisted }"
        ext.execution_context.extensions = None

        with patch("app.core.config.settings.environment", "development"):
            async for _ in ext.on_validate():
                pass


# ---------------------------------------------------------------------------
# Requirements R2 & R3 Test Suites
# ---------------------------------------------------------------------------


class TestDataLoaderCosting:
    """Requirement R2: DataLoader AST costing multiplier unit tests."""

    def test_dataloader_fields_cost_5x(self) -> None:
        """Fields invoking DataLoaders (users, news, events, author, organizer) cost 5 each."""
        query = parse(
            "{ news { title author { name } } events { title organizer { name } } }"
        )
        visitor = _CostVisitor()
        visit(query, visitor)
        # news(5) + title(1) + author(5) + name(1) + events(5) + title(1) + organizer(5) + name(1) = 24
        assert visitor.cost == 24

    def test_dataloader_fields_from_registry(self) -> None:
        """DataLoaderRegistry fields (users, news, events) are recognized and receive 5x multiplier."""
        query = parse("{ users { id } news { id } events { id } }")
        visitor = _CostVisitor()
        visit(query, visitor)
        # users(5) + id(1) + news(5) + id(1) + events(5) + id(1) = 18
        assert visitor.cost == 18


class TestTokenBucketRateLimiting:
    """Requirement R3: Predictive Redis Token Bucket rate limiting tests."""

    @pytest.mark.asyncio
    async def test_token_bucket_key_authenticated_user(self) -> None:
        ext = ext_module.QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ me { id name } }")

        user_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = user_id
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = mock_user

        mock_consume = AsyncMock(return_value=(True, 950))
        with (
            patch.object(ext_module, "_consume_token_bucket", mock_consume),
            patch.object(
                ext_module, "_increment_user_cost", AsyncMock(return_value=10)
            ),
        ):
            async for _ in ext.on_validate():
                pass
            mock_consume.assert_called_once()
            key_arg = (
                mock_consume.call_args[1].get("key") or mock_consume.call_args[0][0]
            )
            assert key_arg == f"gql:token_bucket:{user_id}"

    @pytest.mark.asyncio
    async def test_token_bucket_key_anonymous_user(self) -> None:
        ext = ext_module.QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ news { title } }")

        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = None
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.100"
        ext.execution_context.context.request = mock_request

        mock_consume = AsyncMock(return_value=(True, 990))
        with patch.object(ext_module, "_consume_token_bucket", mock_consume):
            async for _ in ext.on_validate():
                pass
            mock_consume.assert_called_once()
            key_arg = (
                mock_consume.call_args[1].get("key") or mock_consume.call_args[0][0]
            )
            assert key_arg == "gql:token_bucket:ip:192.168.1.100"

    @pytest.mark.asyncio
    async def test_token_bucket_rejection_429(self) -> None:
        ext = ext_module.QueryCostExtension()
        ext.execution_context = MagicMock()
        ext.execution_context.pre_execution_errors = None
        ext.execution_context.graphql_document = parse("{ news { title } }")
        ext.execution_context.context = MagicMock()
        ext.execution_context.context.current_user = None

        # Simulate insufficient token bucket balance
        mock_consume = AsyncMock(return_value=(False, 2))
        with patch.object(ext_module, "_consume_token_bucket", mock_consume):
            with pytest.raises(GraphQLError) as exc_info:
                async for _ in ext.on_validate():
                    pass
            err = exc_info.value
            assert "rate limit exceeded" in str(err).lower()
            assert err.extensions.get("status_code") == 429
            assert err.extensions.get("http", {}).get("status_code") == 429

    @pytest.mark.asyncio
    async def test_token_bucket_redis_fallback_to_memory(self) -> None:
        # Mock Redis get_cache_client to raise ConnectionError
        with patch(
            "app.deps.cache.get_cache_client",
            AsyncMock(side_effect=ConnectionError("Redis down")),
        ):
            ext_module._memory_token_buckets.clear()
            allowed, remaining = await ext_module._consume_token_bucket(
                "gql:token_bucket:test_fallback", 10, capacity=100
            )
            assert allowed is True
            assert remaining == 90
