"""Tests for Repository Pattern."""

from unittest.mock import MagicMock

import pytest

from app.repositories.base import BaseRepository, ReadOnlyRepository


def test_base_repository_is_abstract():
    """Verify BaseRepository requires model property."""
    with pytest.raises(TypeError):
        BaseRepository(MagicMock())  # type: ignore


def test_readonly_repository_is_abstract():
    """Verify ReadOnlyRepository requires model property."""
    with pytest.raises(TypeError):
        ReadOnlyRepository(MagicMock())  # type: ignore


def test_repository_pattern_generics():
    """Test repository uses proper generic types."""
    # With traditional Generic, type params are accessible via __parameters__
    base_params = BaseRepository.__parameters__
    readonly_params = ReadOnlyRepository.__parameters__

    assert len(base_params) == 3  # T, CreateT, UpdateT
    assert len(readonly_params) == 1  # T


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
