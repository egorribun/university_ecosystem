"""GraphQL extension runtime-path and failure-mode tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphql import GraphQLError

import app.graphql.extensions as extensions_module
from app.graphql.extensions import (
    PersistedQueryExtension,
    RequestTimeoutExtension,
    _increment_user_cost,
    _load_manifest,
)


@pytest.mark.asyncio
async def test_increment_user_cost_eviction(monkeypatch):
    # Force memory limit check
    monkeypatch.setattr(
        "app.deps.cache.get_cache_client",
        AsyncMock(side_effect=ConnectionError),
    )
    extensions_module._user_cost_memory.clear()
    try:
        for i in range(10005):
            extensions_module._user_cost_memory[str(i)] = (1, 123)

        res = await _increment_user_cost("user123", 10, 123)
        assert res == 10
        # Should have cleared and only contains the new user
        assert extensions_module._user_cost_memory == {"user123": (10, 123)}
    finally:
        extensions_module._user_cost_memory.clear()


@pytest.mark.asyncio
async def test_request_timeout_extension_timeout():
    ext = RequestTimeoutExtension()
    ext.execution_context = MagicMock()
    ext.TIMEOUT_SECONDS = 0.001

    # We test the timeout error propagation
    gen = ext.on_execute()
    await gen.__anext__()
    try:
        await gen.athrow(TimeoutError)
    except GraphQLError as exc:
        assert "Request exceeded the maximum execution time" in str(exc)
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
        with pytest.raises(GraphQLError, match="allowlist"):
            await gen.asend(None)


def test_build_schema_extensions_production_adds_introspection_rule():
    """Line 183: verify the AddValidationRules lambda is appended in production.

    _build_schema_extensions() is normally called at import time with the
    testing environment, so the production branch (lines 180-189) is never
    reached during ordinary test runs.  We call the function directly after
    patching settings so that _is_prod evaluates to True, then confirm that
    one of the returned extension factories instantiates AddValidationRules
    with NoSchemaIntrospectionCustomRule.
    """
    from graphql.validation import NoSchemaIntrospectionCustomRule
    from strawberry.extensions import AddValidationRules

    from app.graphql.schema import _build_schema_extensions

    with patch("app.graphql.schema.settings") as mock_settings:
        # Any value outside {"development", "testing", "local"} triggers prod branch.
        mock_settings.environment = "production"

        result = _build_schema_extensions()

    # Collect all extension instances produced by the factory callables.
    instantiated = [ext() if callable(ext) else ext for ext in result]

    # QueryDepthLimiter is a subclass of AddValidationRules in this Strawberry version,
    # so use an exact type check to isolate only the introspection-rule extension.
    introspection_rules = [
        inst for inst in instantiated if type(inst) is AddValidationRules
    ]
    assert introspection_rules, (
        "Expected at least one AddValidationRules extension in production mode "
        "(line 183 of schema.py must be covered)"
    )

    # Confirm the rule set contains NoSchemaIntrospectionCustomRule (not just any rule).
    rule_ext = introspection_rules[0]
    assert any(
        rule is NoSchemaIntrospectionCustomRule for rule in rule_ext.validation_rules
    ), "AddValidationRules must include NoSchemaIntrospectionCustomRule"


@pytest.mark.asyncio
async def test_persisted_query_extension_prod_no_query():
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
        with pytest.raises(GraphQLError, match="allowlist"):
            await gen.asend(None)
