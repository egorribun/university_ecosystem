from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo

import pytest

from scripts.quality import check_stabilization_window as gate


@pytest.mark.parametrize("local_day_offset", [-1, 1])
def test_default_window_uses_utc_day_not_host_calendar(
    monkeypatch: pytest.MonkeyPatch, local_day_offset: int
) -> None:
    utc_day = date(2026, 8, 8)

    class HostDate(date):
        @classmethod
        def today(cls) -> date:
            return utc_day + timedelta(days=local_day_offset)

    class UtcClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            assert tz is UTC
            return datetime(2026, 8, 8, 12, tzinfo=UTC)

    monkeypatch.setattr(gate, "date", HostDate)
    monkeypatch.setattr(gate, "datetime", UtcClock)
    runs = [
        {
            "conclusion": "success",
            "head_branch": "main",
            "completed_at": f"{utc_day - timedelta(days=offset)}T01:00:00Z",
        }
        for offset in range(30)
    ]

    result = gate.evaluate_window(runs, branch="main")

    assert result["eligible"] is True
    assert result["as_of"] == "2026-08-08"
    assert result["required_days"] == 30
    assert result["missing_dates"] == []


def test_explicit_as_of_does_not_read_current_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            raise AssertionError("explicit as_of must not read the current clock")

    monkeypatch.setattr(gate, "datetime", UnavailableClock)
    result = gate.evaluate_window(
        [{"conclusion": "success", "completed_at": "2026-08-08T01:00:00Z"}],
        days=1,
        as_of=date(2026, 8, 8),
    )

    assert result["eligible"] is True
    assert result["as_of"] == "2026-08-08"


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-08-09T00:30:00+03:00", date(2026, 8, 8)),
        ("2026-08-07T23:30:00-03:00", date(2026, 8, 8)),
        ("2026-08-08T00:00:00Z", date(2026, 8, 8)),
        ("2026-08-08", date(2026, 8, 8)),
    ],
)
def test_explicit_date_and_aware_timestamp_contract_is_unchanged(
    timestamp: str, expected: date
) -> None:
    assert gate._parse_date(timestamp) == expected
