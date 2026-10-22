"""Deterministic absolute budgets; no lock, subprocess, network or sleep."""

from __future__ import annotations

import math

import pytest

from scripts.owned_nats_outage import Deadline, DeadlineVerdict


class FakeClock:
    def __init__(self, now: object = 100.0) -> None:
        self.now = now
        self.error: Exception | None = None

    def __call__(self) -> object:
        if self.error is not None:
            raise self.error
        return self.now


def test_short_child_clamps_timeout_to_phase_remaining() -> None:
    clock = FakeClock()
    primary = Deadline.after(60, clock=clock)
    phase = primary.child(8)

    assert primary.verdict is DeadlineVerdict.VALID
    assert phase.verdict is DeadlineVerdict.VALID
    assert phase.expires_at == 108.0

    clock.now = 103.0
    budget = phase.timeout_for(10)
    assert budget.verdict is DeadlineVerdict.VALID
    assert budget.seconds == 5.0

    shorter_call = phase.timeout_for(3)
    assert shorter_call.verdict is DeadlineVerdict.VALID
    assert shorter_call.seconds == 3.0


def test_child_cannot_extend_parent_deadline() -> None:
    clock = FakeClock()
    primary = Deadline.after(10, clock=clock)
    phase = primary.child(45)

    assert primary.expires_at == 110.0
    assert phase.expires_at == 110.0


def test_expired_primary_rejects_timeout_and_child_creation() -> None:
    clock = FakeClock()
    primary = Deadline.after(10, clock=clock)
    clock.now = 110.0

    budget = primary.timeout_for(5)
    assert budget.verdict is DeadlineVerdict.EXPIRED
    assert budget.seconds is None

    expired_child = primary.child(5)
    assert expired_child.verdict is DeadlineVerdict.EXPIRED
    child_budget = expired_child.timeout_for(1)
    assert child_budget.verdict is DeadlineVerdict.EXPIRED
    assert child_budget.seconds is None


@pytest.mark.parametrize(
    "bad",
    [0, -1, True, "1", math.nan, math.inf, -math.inf, 10**400],
)
def test_invalid_caps_never_produce_timeout_seconds(bad: object) -> None:
    clock = FakeClock()
    deadline = Deadline.after(10, clock=clock)

    assert Deadline.after(bad, clock=clock).verdict is DeadlineVerdict.INVALID
    assert deadline.child(bad).verdict is DeadlineVerdict.INVALID

    budget = deadline.timeout_for(bad)
    assert budget.verdict is DeadlineVerdict.INVALID
    assert budget.seconds is None


@pytest.mark.parametrize(
    "bad_now",
    [True, None, "100", math.nan, math.inf, -math.inf, 10**400],
)
def test_malformed_clock_at_construction_is_invalid(bad_now: object) -> None:
    deadline = Deadline.after(1, clock=lambda: bad_now)

    assert deadline.verdict is DeadlineVerdict.INVALID
    assert deadline.expires_at is None


def test_non_callable_clock_is_invalid() -> None:
    deadline = Deadline.after(1, clock=object())

    assert deadline.verdict is DeadlineVerdict.INVALID
    assert deadline.expires_at is None


def test_raising_clock_during_construction_is_invalid() -> None:
    def broken_clock() -> object:
        raise RuntimeError("clock unavailable")

    deadline = Deadline.after(1, clock=broken_clock)

    assert deadline.verdict is DeadlineVerdict.INVALID
    assert deadline.expires_at is None


def test_malformed_clock_during_timeout_and_child_is_invalid() -> None:
    clock = FakeClock()
    deadline = Deadline.after(10, clock=clock)
    clock.now = math.nan

    budget = deadline.timeout_for(1)
    assert budget.verdict is DeadlineVerdict.INVALID
    assert budget.seconds is None
    assert deadline.child(1).verdict is DeadlineVerdict.INVALID


def test_raising_clock_during_timeout_and_child_is_invalid() -> None:
    clock = FakeClock()
    deadline = Deadline.after(10, clock=clock)
    clock.error = RuntimeError("clock unavailable")

    budget = deadline.timeout_for(1)
    assert budget.verdict is DeadlineVerdict.INVALID
    assert budget.seconds is None
    assert deadline.child(1).verdict is DeadlineVerdict.INVALID


def test_backwards_clock_after_successful_sample_is_invalid() -> None:
    clock = FakeClock()
    deadline = Deadline.after(10, clock=clock)

    clock.now = 101.0
    first = deadline.timeout_for(5)
    assert first.verdict is DeadlineVerdict.VALID
    assert first.seconds == 5.0

    clock.now = 100.5
    backwards = deadline.timeout_for(5)
    assert backwards.verdict is DeadlineVerdict.INVALID
    assert backwards.seconds is None


def test_child_and_parent_share_clock_regression_guard() -> None:
    clock = FakeClock()
    primary = Deadline.after(60, clock=clock)
    child = primary.child(30)
    clock.now = 110.0
    assert child.timeout_for(10).verdict is DeadlineVerdict.VALID

    clock.now = 109.0
    assert primary.timeout_for(10).verdict is DeadlineVerdict.INVALID


def test_clock_failure_cannot_be_cleared_by_a_later_sample() -> None:
    clock = FakeClock()
    primary = Deadline.after(60, clock=clock)
    clock.now = math.nan
    assert primary.timeout_for(1).verdict is DeadlineVerdict.INVALID

    clock.now = 101.0
    assert primary.timeout_for(1).verdict is DeadlineVerdict.INVALID
    assert primary.child(1).verdict is DeadlineVerdict.INVALID


def test_overflowing_absolute_expiry_is_invalid() -> None:
    clock = FakeClock(1e308)
    deadline = Deadline.after(1e308, clock=clock)

    assert deadline.verdict is DeadlineVerdict.INVALID
    assert deadline.expires_at is None


def test_expired_primary_does_not_consume_fresh_restoration_reserve() -> None:
    clock = FakeClock()
    primary = Deadline.after(2, clock=clock)
    clock.now = 102.0

    assert primary.timeout_for(1).verdict is DeadlineVerdict.EXPIRED

    restoration = Deadline.after(120, clock=clock)
    assert restoration.verdict is DeadlineVerdict.VALID
    assert restoration.expires_at == 222.0

    budget = restoration.timeout_for(45)
    assert budget.verdict is DeadlineVerdict.VALID
    assert budget.seconds == 45.0
