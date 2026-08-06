"""Branch closure tests for notifications core utilities."""

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.notifications import core


def test_current_local_time_handles_naive_clock_result(monkeypatch):
    real_datetime = dt.datetime

    class NaiveDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 1, 1, 12, 0, 0)

    monkeypatch.setattr(core.dt, "datetime", NaiveDateTime)

    result = core._current_local_time(None)

    assert result.tzinfo is None


def test_room_label_prefixes_ignores_empty_translations(monkeypatch):
    monkeypatch.setattr(core, "SUPPORTED_LOCALES", ("en",))
    monkeypatch.setattr(core, "translate", lambda *args, **kwargs: "   ")

    assert core._room_label_prefixes() == {"room", "aud"}


@pytest.mark.asyncio
async def test_fetch_active_user_ids_ignores_empty_exclusion_set():
    db = SimpleNamespace()
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    async def execute(_stmt):
        return result

    db.execute = execute

    assert await core._fetch_active_user_ids(db, exclude=[None]) == []
    assert await core._fetch_active_user_ids(db) == []


class _Rows:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return list(self.values)


class _Database:
    def __init__(self, values):
        self.values = values

    async def execute(self, _stmt):
        return _Rows(self.values)


@pytest.mark.asyncio
async def test_fetch_active_user_ids_applies_exclusion_and_safety_warning(monkeypatch):
    ids = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(core, "_MAX_BROADCAST_RECIPIENTS", 2)
    logger = MagicMock()

    with patch("app.core.logging.get_logger", return_value=logger):
        result = await core._fetch_active_user_ids(
            _Database(ids),
            exclude=[ids[0], None],
        )

    assert result == ids
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_admin_ids_returns_database_rows():
    ids = [uuid.uuid4(), uuid.uuid4()]

    assert await core._fetch_admin_ids(_Database(ids)) == ids
