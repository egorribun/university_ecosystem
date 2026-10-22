"""Exact stored-row retry/drain classifications, independent of network timing."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.owned_nats_outage import (
    OutboxVerdict,
    StoredEventState,
    classify_outage_attempt,
    classify_outbox_drain,
)

EVENT = "00000000-0000-7000-8000-000000000001"
OTHER = "00000000-0000-7000-8000-000000000002"
PENDING = StoredEventState(
    stored_event_id=EVENT,
    processed_at_present=False,
    error_count=0,
    dlq_count=0,
)


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_retry_proof_requires_positive_nonterminal_count(count: int) -> None:
    state = replace(PENDING, error_count=count)

    assert classify_outage_attempt(EVENT, state) is OutboxVerdict.RETRYABLE


def test_zero_attempt_pending_state_waits_but_does_not_prove_outage() -> None:
    assert classify_outage_attempt(EVENT, PENDING) is OutboxVerdict.WAIT


@pytest.mark.parametrize(
    "state",
    [
        replace(PENDING, error_count=5),
        replace(PENDING, error_count=6),
        replace(PENDING, error_count=1, processed_at_present=True),
        replace(PENDING, processed_at_present=True),
        replace(PENDING, error_count=1, dlq_count=1),
        replace(PENDING, error_count=1, dlq_count=2),
    ],
)
def test_terminal_or_prematurely_processed_state_is_not_retry_proof(
    state: StoredEventState,
) -> None:
    assert classify_outage_attempt(EVENT, state) is OutboxVerdict.TERMINAL


@pytest.mark.parametrize(
    "state",
    [
        None,
        replace(PENDING, stored_event_id=OTHER),
        replace(PENDING, processed_at_present=1),
        replace(PENDING, error_count=-1),
        replace(PENDING, error_count=True),
        replace(PENDING, error_count=1.0),
        replace(PENDING, dlq_count=-1),
        replace(PENDING, dlq_count=True),
        replace(PENDING, dlq_count=0.0),
    ],
)
def test_missing_wrong_or_malformed_exact_row_fails_closed(
    state: StoredEventState | None,
) -> None:
    assert classify_outage_attempt(EVENT, state) is OutboxVerdict.INVALID
    assert classify_outbox_drain(EVENT, 1, state) is OutboxVerdict.INVALID


@pytest.mark.parametrize(
    "expected", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"]
)
def test_invalid_retained_row_identity_is_not_pollable(expected: str) -> None:
    state = replace(PENDING, stored_event_id=expected, error_count=1)

    assert classify_outage_attempt(expected, state) is OutboxVerdict.INVALID
    assert classify_outbox_drain(expected, 1, state) is OutboxVerdict.INVALID


@pytest.mark.parametrize(("observed", "current"), [(1, 1), (1, 2), (1, 4), (4, 4)])
def test_drain_requires_processed_row_and_non_decreasing_retry_count(
    observed: int, current: int
) -> None:
    state = replace(PENDING, processed_at_present=True, error_count=current)

    assert classify_outbox_drain(EVENT, observed, state) is OutboxVerdict.DRAINED


def test_pending_after_restore_waits_for_the_same_retained_event() -> None:
    state = replace(PENDING, error_count=2)

    assert classify_outbox_drain(EVENT, 1, state) is OutboxVerdict.WAIT


@pytest.mark.parametrize(
    "state",
    [
        replace(PENDING, error_count=5, processed_at_present=True, dlq_count=1),
        replace(PENDING, error_count=1, processed_at_present=True, dlq_count=1),
        replace(PENDING, error_count=1, dlq_count=1),
        replace(PENDING, error_count=5),
        replace(PENDING, error_count=6, processed_at_present=True),
    ],
)
def test_processed_timestamp_never_overrides_exact_dlq_or_terminal_retry(
    state: StoredEventState,
) -> None:
    assert classify_outbox_drain(EVENT, 1, state) is OutboxVerdict.TERMINAL


@pytest.mark.parametrize("observed", [0, -1, 5, True, 1.0])
def test_drain_requires_valid_prior_outage_observation(observed: object) -> None:
    state = replace(PENDING, processed_at_present=True, error_count=1)

    assert classify_outbox_drain(EVENT, observed, state) is OutboxVerdict.INVALID


@pytest.mark.parametrize("processed", [False, True])
@pytest.mark.parametrize("current", [0, 1])
def test_retry_counter_reset_or_decrease_does_not_prove_drain(
    processed: bool, current: int
) -> None:
    state = replace(PENDING, processed_at_present=processed, error_count=current)

    assert classify_outbox_drain(EVENT, 2, state) is OutboxVerdict.INVALID
