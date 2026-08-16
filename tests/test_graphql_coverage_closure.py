from __future__ import annotations

import builtins
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphql import parse

import app.graphql.extensions as extensions
from app.graphql.extensions import PersistedQueryExtension, QueryCostExtension
from app.graphql.queries import Query


async def _finish_validation(extension: PersistedQueryExtension) -> None:
    generator = extension.on_validate()
    await generator.__anext__()
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()


@pytest.mark.asyncio
async def test_token_bucket_accepts_valid_result_without_redis_exception_module() -> (
    None
):
    redis = MagicMock()
    redis.eval = AsyncMock(return_value=[1, 17])
    real_import = builtins.__import__

    def import_without_redis_exceptions(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "redis.exceptions":
            raise ImportError("optional redis exceptions unavailable")
        return real_import(name, globals, locals, fromlist, level)

    with (
        patch.object(
            builtins, "__import__", side_effect=import_without_redis_exceptions
        ),
        patch("app.deps.cache.get_cache_client", new=AsyncMock(return_value=redis)),
    ):
        assert await extensions._consume_token_bucket("key", 3) == (True, 17)


@pytest.mark.asyncio
async def test_token_bucket_uses_memory_for_malformed_redis_response() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock(return_value={"unexpected": "shape"})
    memory = AsyncMock(return_value=(False, 2))
    with (
        patch("app.deps.cache.get_cache_client", new=AsyncMock(return_value=redis)),
        patch.object(extensions, "_consume_token_bucket_memory", new=memory),
    ):
        assert await extensions._consume_token_bucket("key", 3) == (False, 2)
    memory.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_cost_anonymous_request_without_usable_ip_uses_loopback() -> None:
    extension = QueryCostExtension()
    context = MagicMock()
    context.current_user = None
    context.request.client = MagicMock(host=None)
    context.request.headers = {}
    execution_context = MagicMock()
    execution_context.pre_execution_errors = []
    execution_context.graphql_document = parse("{ me { id } }")
    execution_context.context = context
    extension.execution_context = execution_context

    consume = AsyncMock(return_value=(True, 99))
    with patch.object(extensions, "_consume_token_bucket", new=consume):
        async for _ in extension.on_validate():
            pass

    assert consume.await_args.kwargs["key"] == "gql:token_bucket:ip:127.0.0.1"


def test_manifest_loader_rejects_non_mapping_json(tmp_path: Path) -> None:
    manifest_path = tmp_path / "persisted_queries.json"
    manifest_path.write_text("[]", encoding="utf-8")
    with (
        patch.object(extensions, "_query_allowlist", None),
        patch.object(extensions, "_MANIFEST_PATH", manifest_path),
    ):
        assert extensions._load_manifest() == {}


@pytest.mark.asyncio
async def test_persisted_query_normalizes_non_string_hash() -> None:
    extension = PersistedQueryExtension()
    extension.execution_context = MagicMock(
        query="query { me }",
        extensions={"persistedQuery": {"sha256Hash": 123}},
    )
    with (
        patch("app.core.config.settings.environment", "testing"),
        patch.object(extensions, "_load_manifest", return_value={}),
    ):
        await _finish_validation(extension)


@pytest.mark.asyncio
async def test_apq_resolution_skips_existing_document_and_contains_parse_errors() -> (
    None
):
    query = "query { me { id } }"
    query_hash = extensions._hash_query(query)

    existing = PersistedQueryExtension()
    existing.execution_context = MagicMock(
        query=None,
        graphql_document=object(),
        extensions={"persistedQuery": {"sha256Hash": query_hash}},
    )
    with (
        patch("app.core.config.settings.environment", "testing"),
        patch.object(extensions, "_load_manifest", return_value={query_hash: query}),
    ):
        await _finish_validation(existing)
    assert existing.execution_context.query == query

    invalid = PersistedQueryExtension()
    invalid.execution_context = MagicMock(
        query=None,
        graphql_document=None,
        extensions={"persistedQuery": {"sha256Hash": query_hash}},
    )
    with (
        patch("app.core.config.settings.environment", "testing"),
        patch.object(extensions, "_load_manifest", return_value={query_hash: query}),
        patch("graphql.parse", side_effect=ValueError("invalid stored query")),
    ):
        await _finish_validation(invalid)
    assert invalid.execution_context.query == query


@pytest.mark.asyncio
async def test_production_validation_normalizes_query_after_yield() -> None:
    extension = PersistedQueryExtension()
    extension.execution_context = MagicMock(query="query { me }", extensions={})
    generator = extension.on_validate()
    manifest_path = MagicMock()
    manifest_path.exists.return_value = True
    with (
        patch("app.core.config.settings.environment", "production"),
        patch.object(extensions, "_load_manifest", return_value={"123": "query"}),
        patch.object(extensions, "_MANIFEST_PATH", manifest_path),
    ):
        await generator.__anext__()
        extension.execution_context.query = 123
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()


@pytest.mark.asyncio
async def test_production_known_hash_can_finish_hash_only_validation() -> None:
    query = "query { me { id } }"
    query_hash = extensions._hash_query(query)
    extension = PersistedQueryExtension()
    extension.execution_context = MagicMock(
        query=None,
        graphql_document=object(),
        extensions={"persistedQuery": {"sha256Hash": query_hash}},
    )
    generator = extension.on_validate()
    manifest_path = MagicMock()
    manifest_path.exists.return_value = True
    with (
        patch("app.core.config.settings.environment", "production"),
        patch.object(extensions, "_load_manifest", return_value={query_hash: query}),
        patch.object(extensions, "_MANIFEST_PATH", manifest_path),
    ):
        await generator.__anext__()
        extension.execution_context.query = None
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()


@pytest.mark.asyncio
@pytest.mark.parametrize("checker_result", [False, OSError("spicedb unavailable")])
async def test_group_schedule_fails_closed_for_denial_and_checker_error(
    checker_result: bool | Exception,
) -> None:
    checker = MagicMock()
    if isinstance(checker_result, Exception):
        checker.check_permission = AsyncMock(side_effect=checker_result)
    else:
        checker.check_permission = AsyncMock(return_value=checker_result)
    context = MagicMock()
    context.checker = checker
    context.current_user = MagicMock(id=uuid.uuid4())
    context.session = AsyncMock()
    info = MagicMock(context=context)

    result = await Query().schedule(info, str(uuid.uuid4()))

    assert result == []
    context.session.execute.assert_not_awaited()
