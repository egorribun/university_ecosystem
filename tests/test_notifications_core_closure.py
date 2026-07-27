"""Branch closure tests for notifications core utilities."""

import datetime as dt
from types import SimpleNamespace

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
