"""Custom Strawberry schema extensions for the university ecosystem GraphQL API.

D-06 (audit 2026-03-08): Adds query complexity/cost analysis to prevent
resource-exhaustive queries that evade the existing depth and token limits.
"""

from __future__ import annotations

import logging

from app.core.logging import get_logger
from collections.abc import Iterator
from typing import TYPE_CHECKING

from graphql import GraphQLError
from graphql.language.ast import FieldNode
from graphql.language.visitor import Visitor, visit
from strawberry.extensions import SchemaExtension

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

    def on_validate(self) -> Iterator[None]:
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
        else:
            logger.debug("GraphQL query cost=%d (max=%d)", cost, _MAX_QUERY_COST)


__all__ = ["QueryCostExtension"]
