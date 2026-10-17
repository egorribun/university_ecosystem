"""Persisted-query membership must bind to the actual submitted operation."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from graphql import GraphQLError

from app.graphql import extensions


@pytest.mark.asyncio
@pytest.mark.parametrize("submitted_is_allowed", [False, True])
async def test_production_rejects_another_operations_allowlisted_hash(
    submitted_is_allowed: bool,
) -> None:
    approved = "query Approved { me { id } }"
    submitted = "query Different { events { title } }"
    approved_hash = extensions._hash_query(approved)
    manifest = {approved_hash: approved}
    if submitted_is_allowed:
        manifest[extensions._hash_query(submitted)] = submitted
    extension = extensions.PersistedQueryExtension()
    extension.execution_context = SimpleNamespace(
        query=submitted,
        extensions={"persistedQuery": {"sha256Hash": approved_hash}},
    )
    with (
        patch("app.core.config.settings.environment", "production"),
        patch.object(extensions, "_load_manifest", return_value=manifest),
    ):
        with pytest.raises(GraphQLError, match="persisted query allowlist"):
            async for _ in extension.on_validate():
                pass


@pytest.mark.asyncio
async def test_production_accepts_matching_hash_with_normalized_query() -> None:
    approved = "query Approved { me { id } }"
    approved_hash = extensions._hash_query(approved)
    extension = extensions.PersistedQueryExtension()
    extension.execution_context = SimpleNamespace(
        query=f"  {approved}\n",
        extensions={"persistedQuery": {"sha256Hash": approved_hash}},
    )
    with (
        patch("app.core.config.settings.environment", "production"),
        patch.object(
            extensions, "_load_manifest", return_value={approved_hash: approved}
        ),
    ):
        async for _ in extension.on_validate():
            pass
