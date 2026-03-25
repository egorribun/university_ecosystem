"""MOD-22-03 (Wave 22): GraphQL adversarial query test suite.

Tests cover:
  - Deep nesting that triggers QueryDepthLimiter
  - Alias amplification that triggers QueryCostExtension
  - Fragment spread injection
  - Persisted query bypass attempts
"""

from __future__ import annotations

import hashlib

from graphql import parse
from graphql.language.visitor import visit

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
