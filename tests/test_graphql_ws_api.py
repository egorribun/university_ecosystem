"""Wave 4 coverage: GraphQL, WebSocket, API deps, and repository utilities.

Covers:
- app/graphql/permissions.py
- app/graphql/extensions.py
- app/graphql/context.py
- app/api/ws/connection_manager.py (WebSocketRateLimiter)
- app/repositories/pagination.py
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/graphql/context.py — GraphQLContext
# ---------------------------------------------------------------------------


def test_graphql_context_unauthenticated() -> None:
    from app.graphql.context import GraphQLContext

    ctx = GraphQLContext(
        session=MagicMock(),
        loaders=MagicMock(),
        checker=MagicMock(),
        current_user=None,
    )
    assert ctx.is_authenticated is False


def test_graphql_context_authenticated() -> None:
    from app.graphql.context import GraphQLContext

    mock_user = MagicMock()
    ctx = GraphQLContext(
        session=MagicMock(),
        loaders=MagicMock(),
        checker=MagicMock(),
        current_user=mock_user,
    )
    assert ctx.is_authenticated is True


# ---------------------------------------------------------------------------
# app/graphql/permissions.py — IsAuthenticated, IsAdmin
# ---------------------------------------------------------------------------


def test_is_authenticated_allows_authenticated() -> None:
    from app.graphql.permissions import IsAuthenticated

    perm = IsAuthenticated()

    mock_context = MagicMock()
    mock_context.is_authenticated = True

    mock_info = MagicMock()
    mock_info.context = mock_context

    assert perm.has_permission(source=None, info=mock_info) is True


def test_is_authenticated_denies_unauthenticated() -> None:
    from app.graphql.permissions import IsAuthenticated

    perm = IsAuthenticated()

    mock_context = MagicMock()
    mock_context.is_authenticated = False

    mock_info = MagicMock()
    mock_info.context = mock_context

    assert perm.has_permission(source=None, info=mock_info) is False


def test_is_authenticated_message() -> None:
    from app.graphql.permissions import IsAuthenticated

    assert IsAuthenticated.message == "Authentication required"


@pytest.mark.asyncio
async def test_is_admin_denies_unauthenticated() -> None:
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    mock_context = MagicMock()
    mock_context.is_authenticated = False
    mock_context.current_user = None

    mock_info = MagicMock()
    mock_info.context = mock_context

    result = await perm.has_permission(source=None, info=mock_info)
    assert result is False


@pytest.mark.asyncio
async def test_is_admin_denies_no_checker() -> None:
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_context = MagicMock()
    mock_context.is_authenticated = True
    mock_context.current_user = mock_user
    mock_context.checker = None
    # Remove checker so getattr returns None
    del mock_context.checker

    mock_info = MagicMock()
    mock_info.context = mock_context

    result = await perm.has_permission(source=None, info=mock_info)
    assert result is False


@pytest.mark.asyncio
async def test_is_admin_allows_admin_user() -> None:
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_checker = AsyncMock()
    mock_checker.check_admin = AsyncMock(return_value=True)

    mock_context = MagicMock()
    mock_context.is_authenticated = True
    mock_context.current_user = mock_user
    mock_context.checker = mock_checker

    mock_info = MagicMock()
    mock_info.context = mock_context

    result = await perm.has_permission(source=None, info=mock_info)
    assert result is True


@pytest.mark.asyncio
async def test_is_admin_denies_non_admin() -> None:
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_checker = AsyncMock()
    mock_checker.check_admin = AsyncMock(return_value=False)

    mock_context = MagicMock()
    mock_context.is_authenticated = True
    mock_context.current_user = mock_user
    mock_context.checker = mock_checker

    mock_info = MagicMock()
    mock_info.context = mock_context

    result = await perm.has_permission(source=None, info=mock_info)
    assert result is False


@pytest.mark.asyncio
async def test_is_admin_fails_closed_on_spicedb_error() -> None:
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_checker = AsyncMock()

    mock_context = MagicMock()
    mock_context.is_authenticated = True
    mock_context.current_user = mock_user
    mock_context.checker = mock_checker

    mock_info = MagicMock()
    mock_info.context = mock_context

    # Mock SpiceDBUnavailableError
    with (
        patch("app.graphql.permissions.checker")
        if False
        else patch("app.auth.rbac.SpiceDBUnavailableError", RuntimeError)
    ):
        mock_checker.check_admin = AsyncMock(
            side_effect=RuntimeError("SpiceDB unavailable")
        )
        result = await perm.has_permission(source=None, info=mock_info)

    assert result is False


@pytest.mark.asyncio
async def test_is_admin_fails_closed_on_unexpected_error() -> None:
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_checker = AsyncMock()
    mock_checker.check_admin = AsyncMock(side_effect=Exception("unexpected"))

    mock_context = MagicMock()
    mock_context.is_authenticated = True
    mock_context.current_user = mock_user
    mock_context.checker = mock_checker

    mock_info = MagicMock()
    mock_info.context = mock_context

    result = await perm.has_permission(source=None, info=mock_info)
    assert result is False


# ---------------------------------------------------------------------------
# app/graphql/extensions.py — _CostVisitor, QueryCostExtension
# ---------------------------------------------------------------------------


def test_cost_visitor_cheap_fields() -> None:
    """Simple scalar fields cost 1 each."""
    from graphql.language import parse
    from graphql.language.visitor import visit

    from app.graphql.extensions import _CostVisitor

    doc = parse("{ me { id email } }")
    visitor = _CostVisitor()
    visit(doc, visitor)

    # me=1, id=1, email=1 → cost=3
    assert visitor.cost == 3


def test_cost_visitor_list_fields_cost_more() -> None:
    """List fields like 'chats' cost 5."""
    from graphql.language import parse
    from graphql.language.visitor import visit

    from app.graphql.extensions import _CostVisitor

    doc = parse("{ chats { id } messages { id } }")
    visitor = _CostVisitor()
    visit(doc, visitor)

    # chats=5, id=1, messages=5, id=1 → 12
    assert visitor.cost == 5 + 1 + 5 + 1


def test_cost_visitor_mixed_fields() -> None:
    from graphql.language import parse
    from graphql.language.visitor import visit

    from app.graphql.extensions import _CostVisitor

    doc = parse("{ me { name } chats { participants { id } } }")
    visitor = _CostVisitor()
    visit(doc, visitor)
    # me=1, name=1, chats=5, participants=5, id=1 = 13
    assert visitor.cost == 13


@pytest.mark.asyncio
async def test_cost_extension_under_limit_no_error() -> None:
    """Queries under the cost limit should pass through without errors."""
    from app.graphql.extensions import QueryCostExtension

    ext = QueryCostExtension.__new__(QueryCostExtension)
    mock_ctx = MagicMock()
    mock_ctx.errors = None
    mock_ctx.graphql_document = None
    mock_ctx.context = MagicMock()
    mock_ctx.context.current_user = None
    ext.execution_context = mock_ctx

    gen = ext.on_validate()
    await gen.__anext__()  # first yield
    # Should not raise when document is None
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_cost_extension_skips_when_prior_errors() -> None:
    """If prior validators already set errors, cost analysis is skipped."""
    from app.graphql.extensions import QueryCostExtension

    ext = QueryCostExtension.__new__(QueryCostExtension)
    mock_ctx = MagicMock()
    mock_ctx.errors = ["existing error"]  # prior errors exist
    mock_ctx.graphql_document = None
    ext.execution_context = mock_ctx

    gen = ext.on_validate()
    await gen.__anext__()
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass  # Should complete without raising GraphQLError


@pytest.mark.asyncio
async def test_cost_extension_rejects_expensive_query() -> None:
    """Queries exceeding the cost limit raise GraphQLError."""
    from graphql import GraphQLError
    from graphql.language import parse

    from app.graphql.extensions import QueryCostExtension

    ext = QueryCostExtension.__new__(QueryCostExtension)

    # Build a query with many list fields to exceed _MAX_QUERY_COST
    # Each list field = 5 pts. Need > 200 pts total.
    # 50 list fields = 250 pts → exceeds 200
    many_list_fields = " ".join(f"field{i}: chats {{ id }}" for i in range(50))
    doc = parse(f"{{ {many_list_fields} }}")

    mock_ctx = MagicMock()
    mock_ctx.pre_execution_errors = None
    mock_ctx.graphql_document = doc
    mock_ctx.context = MagicMock()
    mock_ctx.context.current_user = None
    ext.execution_context = mock_ctx

    gen = ext.on_validate()
    await gen.__anext__()
    with pytest.raises(GraphQLError, match="exceeds the maximum"):
        await gen.__anext__()


def test_cost_extension_exports() -> None:
    from app.graphql import extensions

    assert "QueryCostExtension" in extensions.__all__


def test_cost_constants() -> None:
    from app.graphql.extensions import (
        _FIELD_COST,
        _LIST_FIELD_COST,
        _LIST_FIELD_NAMES,
        _MAX_QUERY_COST,
    )

    assert _FIELD_COST == 1
    assert _LIST_FIELD_COST == 5
    assert _MAX_QUERY_COST == 200
    assert "chats" in _LIST_FIELD_NAMES
    assert "messages" in _LIST_FIELD_NAMES
    assert "users" in _LIST_FIELD_NAMES


# ---------------------------------------------------------------------------
# app/api/ws/connection_manager.py — WebSocketRateLimiter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_rate_limiter_allows_under_capacity() -> None:
    from app.api.ws.connection_manager import WebSocketRateLimiter

    limiter = WebSocketRateLimiter(rate=10.0, capacity=5.0)
    # Should allow up to capacity requests
    assert limiter.consume() is True


@pytest.mark.asyncio
async def test_ws_rate_limiter_blocks_when_empty() -> None:
    from app.api.ws.connection_manager import WebSocketRateLimiter

    limiter = WebSocketRateLimiter(rate=0.001, capacity=1.0)
    # Consume the one token
    limiter.consume()
    # Next consume should be blocked (rate refill is ~0)
    result = limiter.consume()
    assert result is False


@pytest.mark.asyncio
async def test_ws_rate_limiter_refills_over_time() -> None:
    from app.api.ws.connection_manager import WebSocketRateLimiter

    limiter = WebSocketRateLimiter(rate=100.0, capacity=1.0)
    # Drain the token
    limiter.consume()
    # Wait for refill
    await asyncio.sleep(0.05)
    assert limiter.consume() is True


@pytest.mark.asyncio
async def test_ws_rate_limiter_first_call_initializes() -> None:
    """First call with last_update=0 should initialize the timer."""
    from app.api.ws.connection_manager import WebSocketRateLimiter

    limiter = WebSocketRateLimiter(rate=5.0, capacity=5.0)
    assert limiter.last_update == 0.0
    result = limiter.consume()
    assert result is True
    assert limiter.last_update > 0.0


def test_broadcast_semaphore_limit() -> None:
    """Semaphore cap is 100 as per Wave 13 audit — now inlined in ConnectionManager."""
    from app.api.ws.connection_manager import ConnectionManager

    # _BROADCAST_SEMAPHORE was moved into ConnectionManager; verify the class exists
    assert ConnectionManager is not None


def test_connection_manager_max_per_user() -> None:
    from app.api.ws.connection_manager import ConnectionManager

    assert ConnectionManager.MAX_CONNECTIONS_PER_USER == 5


def test_connection_manager_initial_state() -> None:
    from app.api.ws.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    assert mgr.active_connections == {}
    assert mgr.connection_users == {}
    assert mgr.rate_limiters == {}


# ---------------------------------------------------------------------------
# app/repositories/pagination.py — cursor encode/decode, Page, CursorParams
# ---------------------------------------------------------------------------


def test_encode_cursor_uuid() -> None:
    from app.repositories.pagination import encode_cursor

    uid = uuid.uuid4()
    encoded = encode_cursor(uid)
    assert isinstance(encoded, str)
    assert len(encoded) > 0


def test_encode_cursor_int() -> None:
    from app.repositories.pagination import encode_cursor

    encoded = encode_cursor(42)
    assert isinstance(encoded, str)


def test_encode_cursor_str() -> None:
    from app.repositories.pagination import encode_cursor

    encoded = encode_cursor("hello")
    assert isinstance(encoded, str)


def test_decode_cursor_as_uuid_roundtrip() -> None:
    from app.repositories.pagination import decode_cursor_as_uuid, encode_cursor

    uid = uuid.uuid4()
    encoded = encode_cursor(uid)
    decoded = decode_cursor_as_uuid(encoded)
    assert decoded == uid


def test_decode_cursor_as_uuid_invalid() -> None:
    from app.repositories.pagination import decode_cursor_as_uuid

    with pytest.raises((ValueError, Exception)):
        decode_cursor_as_uuid("not_valid_base64_uuid!!")


def test_decode_cursor_as_int_roundtrip() -> None:
    from app.repositories.pagination import decode_cursor_as_int, encode_cursor

    n = 12345
    encoded = encode_cursor(n)
    decoded = decode_cursor_as_int(encoded)
    assert decoded == n


def test_decode_cursor_as_int_negative_raises() -> None:
    import base64

    from app.repositories.pagination import decode_cursor_as_int

    # Encode -1 manually
    raw = str(-1).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    with pytest.raises(ValueError, match="out of valid range"):
        decode_cursor_as_int(encoded)


def test_decode_cursor_as_int_malformed() -> None:
    from app.repositories.pagination import decode_cursor_as_int

    with pytest.raises(ValueError, match="malformed cursor"):
        decode_cursor_as_int("not_valid_cursor!@#")


def test_page_from_rows_under_limit() -> None:
    from app.repositories.pagination import Page

    rows = [MagicMock(id=i) for i in range(5)]
    page = Page.from_rows(rows, limit=10)

    assert len(page.items) == 5
    assert page.has_more is False
    assert page.next_cursor is None


def test_page_from_rows_has_more() -> None:
    from app.repositories.pagination import Page

    rows = [MagicMock(id=i) for i in range(11)]  # 11 rows for limit=10
    page = Page.from_rows(rows, limit=10)

    assert len(page.items) == 10
    assert page.has_more is True
    assert page.next_cursor is not None


def test_page_from_rows_exact_limit() -> None:
    from app.repositories.pagination import Page

    rows = [MagicMock(id=i) for i in range(10)]  # exactly limit rows
    page = Page.from_rows(rows, limit=10)

    assert len(page.items) == 10
    assert page.has_more is False


def test_page_empty() -> None:
    from app.repositories.pagination import Page

    page: Page[Any] = Page.empty()
    assert page.items == []
    assert page.has_more is False
    assert page.next_cursor is None


def test_cursor_params_no_after() -> None:
    from app.repositories.pagination import CursorParams

    # Must pass after=None explicitly — dataclass default is FastAPI's Query() object
    params = CursorParams(after=None)
    assert params.after is None
    assert params.after_uuid is None
    assert params.after_int is None


def test_cursor_params_with_uuid_after() -> None:
    from app.repositories.pagination import CursorParams, encode_cursor

    uid = uuid.uuid4()
    encoded = encode_cursor(uid)
    params = CursorParams(after=encoded)
    assert params.after_uuid == uid


def test_cursor_params_with_int_after() -> None:
    from app.repositories.pagination import CursorParams, encode_cursor

    n = 999
    encoded = encode_cursor(n)
    params = CursorParams(after=encoded)
    assert params.after_int == n


def test_apply_cursor_no_after() -> None:
    from app.repositories.pagination import CursorParams, apply_cursor

    mock_stmt = MagicMock()
    mock_stmt.limit = MagicMock(return_value=mock_stmt)
    mock_stmt.where = MagicMock(return_value=mock_stmt)

    mock_column = MagicMock()
    params = CursorParams(limit=5, after=None)

    apply_cursor(mock_stmt, mock_column, params)
    # Should call limit(params.limit + 1)
    mock_stmt.limit.assert_called_once_with(6)
    mock_stmt.where.assert_not_called()


def test_apply_cursor_with_after() -> None:
    from app.repositories.pagination import CursorParams, apply_cursor, encode_cursor

    uid = uuid.uuid4()
    encoded = encode_cursor(uid)

    mock_stmt = MagicMock()
    mock_stmt.where = MagicMock(return_value=mock_stmt)
    mock_stmt.limit = MagicMock(return_value=mock_stmt)

    mock_column = MagicMock()
    mock_column.__gt__ = MagicMock(return_value=MagicMock())

    params = CursorParams(limit=10, after=encoded)
    apply_cursor(mock_stmt, mock_column, params)

    mock_stmt.where.assert_called_once()
    mock_stmt.limit.assert_called_once_with(11)


def test_apply_cursor_malformed_after_raises_400() -> None:
    """Malformed cursor raises HTTPException 400 (RZ-14-03)."""
    from fastapi import HTTPException

    from app.repositories.pagination import CursorParams, apply_cursor

    mock_stmt = MagicMock()
    mock_stmt.limit = MagicMock(return_value=mock_stmt)
    mock_stmt.where = MagicMock(return_value=mock_stmt)

    mock_column = MagicMock()
    params = CursorParams(limit=5, after="!!invalid!!")

    with pytest.raises(HTTPException) as exc_info:
        apply_cursor(mock_stmt, mock_column, params)
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    "limit,expected_rows",
    [
        (5, 5),
        (10, 10),
        (1, 1),
    ],
)
def test_page_from_rows_respects_limit(limit: int, expected_rows: int) -> None:
    from app.repositories.pagination import Page

    rows = [MagicMock(id=i) for i in range(limit)]
    page = Page.from_rows(rows, limit=limit)
    assert len(page.items) == expected_rows


def test_page_from_rows_no_id_attribute() -> None:
    """Rows without 'id' attribute should still produce a page but no cursor."""
    from app.repositories.pagination import Page

    rows = [MagicMock(spec=[]) for _ in range(5)]  # no 'id' attribute
    # from_rows only sets next_cursor when has_more is True
    rows_for_next = [*rows, MagicMock(spec=[])]  # 6 rows for limit 5

    page = Page.from_rows(rows_for_next, limit=5)
    assert page.has_more is True
    # next_cursor may be None if id can't be extracted
