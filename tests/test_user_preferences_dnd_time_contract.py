"""Contracts for local wall-clock quiet-hour boundaries."""

from __future__ import annotations

from datetime import UTC, time, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.users import UserProfileUpdate


@pytest.mark.parametrize("field", ["dnd_start", "dnd_end"])
def test_profile_quiet_hours_accept_local_wall_clock_values(field: str) -> None:
    payload = UserProfileUpdate(
        dnd_enabled=True,
        dnd_start="22:15:00",
        dnd_end="07:00:00",
        timezone="Europe/Istanbul",
    )

    expected = time(22, 15) if field == "dnd_start" else time(7, 0)
    actual = getattr(payload, field)
    assert actual == expected
    assert actual.tzinfo is None
    assert payload.timezone == "Europe/Istanbul"


@pytest.mark.parametrize("field", ["dnd_start", "dnd_end"])
@pytest.mark.parametrize(
    "value",
    [
        time(22, 15, tzinfo=UTC),
        time(22, 15, tzinfo=timezone(timedelta(hours=3))),
    ],
)
def test_profile_quiet_hours_reject_explicit_time_offsets(
    field: str, value: time
) -> None:
    with pytest.raises(ValidationError, match="local wall-clock"):
        UserProfileUpdate(**{field: value})


def test_nested_preferences_reject_explicit_time_offsets() -> None:
    with pytest.raises(ValidationError, match="local wall-clock"):
        UserProfileUpdate(
            preferences={
                "dnd_enabled": True,
                "dnd_start": "22:15:00+03:00",
                "dnd_end": "07:00:00",
                "timezone": "Europe/Istanbul",
            }
        )
