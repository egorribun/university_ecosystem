"""Effective worker policy admission; no settings mutation or process I/O."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.owned_nats_outage import (
    WorkerPolicy,
    WorkerPolicyVerdict,
    validate_worker_policy,
)

DEFAULT = WorkerPolicy(poll_interval_seconds=5.0, batch_size=20, max_retries=5)


@pytest.mark.parametrize(
    "policy",
    [
        DEFAULT,
        WorkerPolicy(poll_interval_seconds=1.0, batch_size=50, max_retries=5),
        WorkerPolicy(poll_interval_seconds=10.0, batch_size=2, max_retries=5),
    ],
)
def test_effective_worker_policy_supports_bounded_observation(
    policy: WorkerPolicy,
) -> None:
    assert validate_worker_policy(policy) is WorkerPolicyVerdict.VALID


@pytest.mark.parametrize(
    "policy",
    [
        replace(DEFAULT, poll_interval_seconds=0.0),
        replace(DEFAULT, poll_interval_seconds=-1.0),
        replace(DEFAULT, poll_interval_seconds=0.5),
        replace(DEFAULT, poll_interval_seconds=10.1),
        replace(DEFAULT, poll_interval_seconds=float("inf")),
        replace(DEFAULT, poll_interval_seconds=float("nan")),
        replace(DEFAULT, poll_interval_seconds=True),
        replace(DEFAULT, poll_interval_seconds=None),
        replace(DEFAULT, poll_interval_seconds="5"),
        replace(DEFAULT, batch_size=0),
        replace(DEFAULT, batch_size=1),
        replace(DEFAULT, batch_size=True),
        replace(DEFAULT, batch_size=20.0),
        replace(DEFAULT, max_retries=4),
        replace(DEFAULT, max_retries=6),
        replace(DEFAULT, max_retries=True),
        replace(DEFAULT, max_retries=5.0),
    ],
)
def test_unsuitable_policy_is_refused_without_changing_worker(
    policy: WorkerPolicy,
) -> None:
    assert validate_worker_policy(policy) is WorkerPolicyVerdict.INVALID
