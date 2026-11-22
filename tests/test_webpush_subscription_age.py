"""The provider-gone evidence buckets a subscription's age into closed classes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.webpush import _subscription_age_class

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "lt_10s"),
        (9.999, "lt_10s"),
        (10, "lt_60s"),
        (59.5, "lt_60s"),
        (60, "lt_600s"),
        (599, "lt_600s"),
        (600, "ge_600s"),
        (86_400, "ge_600s"),
    ],
)
def test_age_buckets_have_closed_half_open_bounds(
    seconds: float, expected: str
) -> None:
    assert _subscription_age_class(NOW - timedelta(seconds=seconds), NOW) == expected


def test_naive_timestamps_are_read_as_utc() -> None:
    naive = (NOW - timedelta(seconds=30)).replace(tzinfo=None)
    assert _subscription_age_class(naive, NOW) == "lt_60s"


@pytest.mark.parametrize(
    "created_at", [None, "2026-11-22T12:00:00Z", 0, NOW + timedelta(seconds=1)]
)
def test_missing_malformed_or_future_timestamps_are_unknown(created_at: object) -> None:
    assert _subscription_age_class(created_at, NOW) == "unknown"
