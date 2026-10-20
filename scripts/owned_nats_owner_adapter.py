"""Run-wide pinned signed-owner adapter for the disabled NATS coordinator.

This fragment connects the existing descriptor reader and lifecycle lease to
``OutagePorts`` callbacks. It does not read Docker or enable the coordinator.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scripts import live_nats_transport as transport
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline, DeadlineVerdict

_SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class OwnerFilePins:
    """Caller-trusted immutable pins for the existing private in-place files."""

    repository: str = field(repr=False)
    state_root: str = field(repr=False)
    source_sha: str = field(repr=False)
    owner_uid: int = field(repr=False)


class OwnerReadNotReady(RuntimeError):
    """Closed non-sensitive failure at the owner-port boundary."""


class SignedOwnerLeasePort:
    """Keep one existing lifecycle lease across all signed-owner rereads."""

    __slots__ = ("_lease", "_pins", "_sleep")

    def __init__(self, pins: OwnerFilePins, *, sleep: Callable[[float], None]) -> None:
        self._pins = pins
        self._sleep = sleep
        self._lease: transport.LifecycleLockLease | None = None

    @staticmethod
    def _deadline_live(deadline: object) -> bool:
        if type(deadline) is not Deadline:
            return False
        try:
            return deadline.timeout_for(1.0).verdict is DeadlineVerdict.VALID
        except Exception:
            return False

    @staticmethod
    def _pins_valid(pins: object) -> bool:
        if type(pins) is not OwnerFilePins:
            return False
        try:
            return (
                type(pins.repository) is str
                and Path(pins.repository).is_absolute()
                and type(pins.state_root) is str
                and Path(pins.state_root).is_absolute()
                and type(pins.source_sha) is str
                and _SOURCE_SHA.fullmatch(pins.source_sha) is not None
                and type(pins.owner_uid) is int
                and pins.owner_uid >= 0
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return False

    def acquire_lock(self, *, deadline: Deadline) -> object | None:
        """Acquire the existing sibling lock once and retain its exact lease."""
        if (
            self._lease is not None
            or not self._pins_valid(self._pins)
            or not callable(self._sleep)
            or not self._deadline_live(deadline)
        ):
            return None
        lease = transport.acquire_existing_lifecycle_lock(
            self._pins.state_root,
            deadline=deadline,
            sleep=self._sleep,
        )
        if type(lease) is not transport.LifecycleLockLease:
            return None
        # The coordinator checks the operation deadline after this callback. Keep
        # and return a late lease so its outer finally can still release it.
        self._lease = lease
        return lease

    def read_signed_owner(self, *, deadline: Deadline) -> OwnerEvidence:
        """Reread signed owner metadata under the retained run-wide lease."""
        lease = self._lease
        if (
            lease is None
            or lease._released
            or not self._pins_valid(self._pins)
            or not self._deadline_live(deadline)
        ):
            raise OwnerReadNotReady
        result = transport.read_signed_owner_v11_under_lease(
            lease,
            pinned_repository=self._pins.repository,
            pinned_state_root=self._pins.state_root,
            pinned_source_sha=self._pins.source_sha,
            pinned_owner_uid=self._pins.owner_uid,
            deadline=deadline,
        )
        if (
            self._lease is not lease
            or lease._released
            or not self._deadline_live(deadline)
            or type(result) is not transport.OwnerParseResult
            or result.status is not transport.OwnerParseStatus.SIGNED_METADATA
            or type(result.owner) is not OwnerEvidence
        ):
            raise OwnerReadNotReady
        return result.owner

    def release_lock(self, lease: object, *, deadline: Deadline) -> None:
        """Release only the exact lease returned by this adapter's acquisition."""
        if type(lease) is not transport.LifecycleLockLease or self._lease is not lease:
            raise OwnerReadNotReady
        released = transport.release_lifecycle_lock(lease, deadline=deadline)
        if released is not True:
            raise OwnerReadNotReady
        self._lease = None

    def __repr__(self) -> str:
        return "<SignedOwnerLeasePort>"
