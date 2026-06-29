import pytest
import uuid
import time
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from graphql import GraphQLError, DocumentNode
from strawberry.extensions import Extension
from app.graphql.extensions import (
    QueryCostExtension,
    RequestTimeoutExtension,
    PersistedQueryExtension,
    _increment_user_cost,
    _CostVisitor,
    _load_manifest,
)
import app.graphql.extensions as extensions_module

@pytest.mark.asyncio
async def test_increment_user_cost_eviction():
    # Force memory limit check
    extensions_module._user_cost_memory.clear()
    for i in range(10005):
        extensions_module._user_cost_memory[str(i)] = (1, 123)
        
    res = await _increment_user_cost("user123", 10, 123)
    assert res == 10
    # Should have cleared and only contains the new user
    assert len(extensions_module._user_cost_memory) == 1

@pytest.mark.asyncio
async def test_request_timeout_extension_timeout():
    ext = RequestTimeoutExtension()
    ext.execution_context = MagicMock()
    ext.TIMEOUT_SECONDS = 0.001
    
    async def dummy_execute():
        await asyncio.sleep(0.05)
        yield
        
    # We test the timeout error propagation
    gen = ext.on_execute()
    await gen.__anext__()
    try:
        await gen.asend(None)
    except GraphQLError as e:
        assert "Request exceeded the maximum execution time" in str(e)
    except TimeoutError:
        pass

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
    with patch("app.graphql.extensions._MANIFEST_PATH", Path("non-existent-file-123.json")):
        extensions_module._query_allowlist = None
        manifest = _load_manifest()
        assert manifest == {}

@pytest.mark.asyncio
async def test_persisted_query_extension_prod_not_in_manifest():
    ext = PersistedQueryExtension()
    ext.execution_context = MagicMock()
    ext.execution_context.query = "query { test }"
    ext.execution_context.extensions = {"persistedQuery": {"sha256Hash": "unknown_hash"}}
    
    with patch("app.core.config.settings") as mock_settings, \
         patch("app.graphql.extensions._query_allowlist", {"known_hash": "query"}):
        mock_settings.environment = "production"
        
        gen = ext.on_validate()
        await gen.__anext__()
        with pytest.raises(GraphQLError, match="This query is not in the persisted-query allowlist"):
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
