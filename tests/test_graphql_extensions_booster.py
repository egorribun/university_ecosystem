import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphql import GraphQLError

import app.graphql.extensions as extensions_module
from app.graphql.extensions import (
    PersistedQueryExtension,
    QueryCostExtension,
    RequestTimeoutExtension,
    _increment_user_cost,
    _load_manifest,
)


@pytest.mark.asyncio
async def test_increment_user_cost_eviction():
    # Force memory limit check
    extensions_module._user_cost_memory.clear()
    for i in range(10005):
        extensions_module._user_cost_memory[str(i)] = (1, 123)

    with patch("app.deps.cache.get_cache_client", side_effect=ConnectionError):
        res = await _increment_user_cost("user123", 10, 123)
        assert res == 10
        # Should have cleared and only contains the new user
        assert len(extensions_module._user_cost_memory) == 1


@pytest.mark.asyncio
async def test_request_timeout_extension_timeout():
    ext = RequestTimeoutExtension()
    ext.execution_context = MagicMock()
    ext.TIMEOUT_SECONDS = 0.001

    # We test the timeout error propagation
    gen = ext.on_execute()
    await gen.__anext__()
    try:
        await asyncio.sleep(0.01)
        await gen.asend(None)
    except asyncio.CancelledError as e:
        with pytest.raises(
            GraphQLError, match="Request exceeded the maximum execution time"
        ):
            await gen.athrow(e)


def test_load_manifest_double_lock_and_exists(tmp_path):
    # Set manifest path to a temp file
    temp_manifest = tmp_path / "query-manifest.json"
    temp_manifest.write_text(json.dumps({"hash1": "query1"}))

    with patch("app.graphql.extensions._MANIFEST_PATH", temp_manifest):
        extensions_module._query_allowlist = None
        manifest = _load_manifest()
        assert manifest == {"hash1": "query1"}

        # Test double checked lock return
        manifest2 = _load_manifest()
        assert manifest2 == {"hash1": "query1"}


def test_load_manifest_corrupted_json(tmp_path):
    temp_manifest = tmp_path / "query-manifest.json"
    temp_manifest.write_text("{corrupt")

    with patch("app.graphql.extensions._MANIFEST_PATH", temp_manifest):
        extensions_module._query_allowlist = None
        manifest = _load_manifest()
        assert manifest == {}


def test_load_manifest_not_exists():
    with patch(
        "app.graphql.extensions._MANIFEST_PATH", Path("non-existent-file-123.json")
    ):
        extensions_module._query_allowlist = None
        manifest = _load_manifest()
        assert manifest == {}


@pytest.mark.asyncio
async def test_persisted_query_extension_prod_not_in_manifest():
    ext = PersistedQueryExtension()
    ext.execution_context = MagicMock()
    ext.execution_context.query = "query { test }"
    ext.execution_context.extensions = {
        "persistedQuery": {"sha256Hash": "unknown_hash"}
    }

    with (
        patch("app.core.config.settings") as mock_settings,
        patch("app.graphql.extensions._query_allowlist", {"known_hash": "query"}),
    ):
        mock_settings.environment = "production"

        gen = ext.on_validate()
        await gen.__anext__()
        with pytest.raises(
            GraphQLError, match="This query is not in the persisted-query allowlist"
        ):
            await gen.asend(None)


@pytest.mark.asyncio
async def test_persisted_query_extension_prod_no_query():
    ext = PersistedQueryExtension()
    ext.execution_context = MagicMock()
    ext.execution_context.query = None

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.environment = "production"

        gen = ext.on_validate()
        await gen.__anext__()
        # Should return without error
        try:
            await gen.asend(None)
        except StopAsyncIteration:
            pass


def test_load_manifest_concurrent_double_check():
    extensions_module._query_allowlist = None

    class MockLock:
        def __enter__(self):
            extensions_module._query_allowlist = {"concurrent": "check"}
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("app.graphql.extensions._manifest_lock", MockLock()):
        manifest = _load_manifest()
        assert manifest == {"concurrent": "check"}


@pytest.mark.asyncio
async def test_persisted_query_extension_dev_testing():
    ext = PersistedQueryExtension()
    ext.execution_context = MagicMock()
    # Runs in default testing environment, should return early
    gen = ext.on_validate()
    await gen.__anext__()
    try:
        await gen.asend(None)
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_persisted_query_extension_prod_no_query_with_manifest():
    ext = PersistedQueryExtension()
    ext.execution_context = MagicMock()
    ext.execution_context.query = None

    with (
        patch("app.core.config.settings") as mock_settings,
        patch("app.graphql.extensions._query_allowlist", {"known_hash": "query"}),
    ):
        mock_settings.environment = "production"

        gen = ext.on_validate()
        await gen.__anext__()
        try:
            await gen.asend(None)
        except StopAsyncIteration:
            pass


@pytest.mark.asyncio
async def test_query_cost_extension_user_rate_limit():
    ext = QueryCostExtension()
    ext.execution_context = MagicMock()
    ext.execution_context.pre_execution_errors = None
    document = MagicMock()
    ext.execution_context.graphql_document = document

    def mock_visit_fn(doc, vis):
        vis.cost = 50

    with (
        patch("app.graphql.extensions.visit", side_effect=mock_visit_fn),
        patch(
            "app.graphql.extensions._increment_user_cost", new_callable=AsyncMock
        ) as mock_incr,
    ):
        mock_incr.return_value = 1005

        current_user = MagicMock()
        current_user.id = 42
        ext.execution_context.context.current_user = current_user

        gen = ext.on_validate()
        await gen.__anext__()
        with pytest.raises(GraphQLError, match="GraphQL rate limit exceeded"):
            await gen.asend(None)
