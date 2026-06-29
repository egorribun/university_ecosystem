"""Tests for Repository Pattern."""

from __future__ import annotations

import re
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hypo_settings
from hypothesis import strategies as st

from app.repositories.base import BaseRepository, ReadOnlyRepository


def test_base_repository_is_abstract():
    """Verify BaseRepository requires model property."""
    with pytest.raises(TypeError):
        BaseRepository(MagicMock())


def test_readonly_repository_is_abstract():
    """Verify ReadOnlyRepository requires model property."""
    with pytest.raises(TypeError):
        ReadOnlyRepository(MagicMock())


def test_repository_pattern_generics():
    """Test repository uses proper generic types."""
    # With traditional Generic, type params are accessible via __parameters__
    base_params = BaseRepository.__parameters__
    readonly_params = ReadOnlyRepository.__parameters__

    assert len(base_params) == 4  # T, DTOT, CreateT, UpdateT
    assert len(readonly_params) == 2  # T, DTOT


def test_user_repository_import():
    """Test UserRepository can be imported."""
    from app.repositories.user_repository import UserRepository, get_user_repository

    assert UserRepository is not None
    assert get_user_repository is not None


def test_event_repository_import():
    """Test EventRepository can be imported."""
    from app.repositories.event_repository import EventRepository, get_event_repository

    assert EventRepository is not None
    assert get_event_repository is not None


def test_repository_init():
    """Test repository __init__ package exports."""
    from app.repositories import BaseRepository as BR
    from app.repositories import ReadOnlyRepository as ROR

    assert BR is BaseRepository
    assert ROR is ReadOnlyRepository


# ── _cast_id property-based tests ───────────────────────────────────────────
#
# ``ReadOnlyRepository._cast_id`` is on every read path and is a security
# boundary — invalid UUIDs are rejected explicitly before they reach the
# database driver. A previous "len >= 32" check silently passed arbitrary
# 33-char strings, which then crashed deep inside asyncpg with a cryptic
# DataError. These tests pin the regex-based validation contract.


class _StubRepo(ReadOnlyRepository[Any, Any]):
    """Minimal concrete subclass used to exercise ``_cast_id`` in isolation."""

    @property
    def model(self) -> type[Any]:
        return type(self)

    @property
    def dto_class(self) -> type[Any]:
        return type(self)


@pytest.fixture
def repo() -> _StubRepo:
    return _StubRepo(MagicMock())


_UUID_DASHED_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# --- Example-based tests for documented behaviour ---


def test_cast_id_accepts_uuid_unchanged(repo: _StubRepo) -> None:
    """A ``uuid.UUID`` is returned unchanged (no copy needed)."""
    u = uuid.uuid4()
    assert repo._cast_id(u) is u


def test_cast_id_passes_through_non_strings(repo: _StubRepo) -> None:
    """Integer or other non-string IDs are returned unchanged (e.g. for int PKs)."""
    assert repo._cast_id(42) == 42
    assert repo._cast_id(None) is None


def test_cast_id_parses_canonical_form(repo: _StubRepo) -> None:
    """Canonical 8-4-4-4-12 form parses to a UUID instance."""
    s = "12345678-1234-1234-1234-1234567890ab"
    result = repo._cast_id(s)
    assert isinstance(result, uuid.UUID)
    assert str(result) == s


def test_cast_id_parses_hex_form(repo: _StubRepo) -> None:
    """32-char hex (no dashes) form parses to a UUID instance."""
    s = "1234567812341234123412345678" + "90ab"
    result = repo._cast_id(s)
    assert isinstance(result, uuid.UUID)
    # `uuid.UUID(hex=...)` produces canonical dashed form when stringified.
    assert str(result).replace("-", "") == s.lower()


def test_cast_id_accepts_uppercase(repo: _StubRepo) -> None:
    """The regex is case-insensitive — uppercase UUIDs parse fine."""
    s = "12345678-1234-1234-1234-1234567890AB"
    result = repo._cast_id(s)
    assert isinstance(result, uuid.UUID)


@pytest.mark.parametrize(
    "garbage",
    [
        "",  # empty
        "not-a-uuid",  # arbitrary
        "12345",  # too short
        "12345678-1234-1234-1234-1234567890ab-extra",  # too long with extra
        "12345678-1234-1234-1234",  # truncated
        "12345678-1234-1234-1234-1234567890ag",  # 'g' not hex
        # The previous len-only check would have accepted these silently:
        "x" * 33,  # 33 non-hex chars
        "x" * 32,  # 32 non-hex chars (matches old length but not regex)
        # Injection-style payloads:
        "'; DROP TABLE users--",
        "../../etc/passwd",
        "<script>alert(1)</script>",
    ],
)
def test_cast_id_rejects_invalid_strings(repo: _StubRepo, garbage: str) -> None:
    """Malformed UUID strings raise ValueError at the repository boundary."""
    with pytest.raises(ValueError, match="Invalid UUID format"):
        repo._cast_id(garbage)


# --- Property-based exhaustive coverage ---


@hypo_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(uuid_value=st.uuids())
def test_cast_id_round_trip_uuid_objects(uuid_value: uuid.UUID) -> None:
    """Any UUID object is returned unchanged (identity preservation)."""
    repo = _StubRepo(MagicMock())
    assert repo._cast_id(uuid_value) is uuid_value


@hypo_settings(max_examples=100)
@given(uuid_value=st.uuids())
def test_cast_id_canonical_string_round_trip(uuid_value: uuid.UUID) -> None:
    """str(uuid) round-trips through ``_cast_id`` to the same UUID."""
    repo = _StubRepo(MagicMock())
    result = repo._cast_id(str(uuid_value))
    assert isinstance(result, uuid.UUID)
    assert result == uuid_value


@hypo_settings(max_examples=100)
@given(uuid_value=st.uuids())
def test_cast_id_hex_string_round_trip(uuid_value: uuid.UUID) -> None:
    """The 32-char hex form round-trips to the same UUID."""
    repo = _StubRepo(MagicMock())
    result = repo._cast_id(uuid_value.hex)
    assert isinstance(result, uuid.UUID)
    assert result == uuid_value


@hypo_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(garbage=st.text(min_size=0, max_size=80))
def test_cast_id_rejects_random_garbage(garbage: str) -> None:
    """Random text either matches the UUID regex (rare) or raises cleanly."""
    repo = _StubRepo(MagicMock())
    if _UUID_DASHED_RE.match(garbage) or re.fullmatch(r"[0-9a-f]{32}", garbage, re.I):
        # The string IS a valid UUID format — accept it.
        result = repo._cast_id(garbage)
        assert isinstance(result, uuid.UUID)
    else:
        # Not a valid format — must raise ValueError, never anything else.
        with pytest.raises(ValueError, match="Invalid UUID format"):
            repo._cast_id(garbage)


# --- _escape_like SQL injection defence ---


class TestEscapeLike:
    """``_escape_like`` neutralises SQL LIKE wildcards.

    Unescaped user input in LIKE patterns enables two attacks: ``%`` /
    ``_`` turns a selective query into a full-table scan (DoS), and
    crafted patterns can enumerate rows by exploiting ``_`` (single-char
    wildcard) to brute-force column values.
    """

    def test_escapes_percent(self) -> None:
        assert _StubRepo._escape_like("100%") == "100\\%"

    def test_escapes_underscore(self) -> None:
        assert _StubRepo._escape_like("foo_bar") == "foo\\_bar"

    def test_escapes_backslash_first(self) -> None:
        """Escape character is escaped first to prevent double-escape collision."""
        assert _StubRepo._escape_like("a\\b") == "a\\\\b"

    def test_combines_all_three(self) -> None:
        """Combined: backslash escaped first, then % and _."""
        assert _StubRepo._escape_like("\\%_") == "\\\\\\%\\_"

    def test_passes_safe_text_through(self) -> None:
        """Plain text without wildcards is unchanged."""
        assert _StubRepo._escape_like("hello world") == "hello world"

    def test_custom_escape_char(self) -> None:
        """A non-default escape character can be supplied."""
        assert _StubRepo._escape_like("100%", escape_char="!") == "100!%"

    @hypo_settings(max_examples=50)
    @given(text=st.text(min_size=0, max_size=40))
    def test_escape_like_idempotent_on_safe_text(self, text: str) -> None:
        """Text with no wildcards survives the escape unchanged."""
        if "%" not in text and "_" not in text and "\\" not in text:
            assert _StubRepo._escape_like(text) == text
