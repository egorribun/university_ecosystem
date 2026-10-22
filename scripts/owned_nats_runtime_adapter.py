"""Compose the existing owner lease with a read-only owned Core observation.

This adapter performs read-only Docker observation when its runtime callback is
invoked. It does not expose an outage command or establish Docker authority:
the executable, configuration and local socket pins remain caller-trusted.
"""

from __future__ import annotations

from dataclasses import replace

from scripts import live_nats_transport as transport
from scripts import owned_nats_docker as docker
from scripts.owned_nats_coordinator import (
    OwnerEvidence,
    RuntimeEvidence,
    RuntimeObservationPhase,
    RuntimeObservationRecorder,
)
from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_owner_adapter import (
    SignedOwnerLeasePort,
)


class RuntimeReadNotReady(RuntimeError):
    """Closed non-sensitive failure at the owner-bound runtime boundary."""


class OwnedCoreRuntimePort:
    """Forward owner lease callbacks and bind runtime reads to that exact lease."""

    __slots__ = (
        "_compose_pins",
        "_docker_pins",
        "_lazy_core",
        "_lease",
        "_owner_port",
        "_runtime_diagnostic",
    )

    def __init__(
        self,
        owner_port: SignedOwnerLeasePort,
        docker_pins: docker.DockerReadPins,
        compose_pins: docker.ComposeConfigPins,
    ) -> None:
        if (
            type(owner_port) is not SignedOwnerLeasePort
            or type(docker_pins) is not docker.DockerReadPins
            or type(compose_pins) is not docker.ComposeConfigPins
        ):
            raise RuntimeReadNotReady
        try:
            self._owner_port = owner_port
            self._docker_pins = replace(docker_pins)
            self._compose_pins = replace(compose_pins)
            self._lazy_core = False
            self._runtime_diagnostic: RuntimeObservationPhase | None = None
            self._lease: transport.LifecycleLockLease | None = None
        except (AttributeError, TypeError, ValueError) as error:
            raise RuntimeReadNotReady from error

    @classmethod
    def for_owned_core(cls, owner_port: SignedOwnerLeasePort) -> OwnedCoreRuntimePort:
        """Create the fixed source-bound lazy Core path without reading Docker."""
        if type(owner_port) is not SignedOwnerLeasePort:
            raise RuntimeReadNotReady
        try:
            runtime = cls.__new__(cls)
            runtime._owner_port = owner_port
            runtime._docker_pins = None
            runtime._compose_pins = None
            runtime._lazy_core = True
            runtime._runtime_diagnostic = None
            runtime._lease = None
            return runtime
        except (AttributeError, TypeError, ValueError) as error:
            raise RuntimeReadNotReady from error

    @property
    def runtime_diagnostic(self) -> RuntimeObservationPhase | None:
        phase = self._runtime_diagnostic
        return phase if type(phase) is RuntimeObservationPhase else None

    @staticmethod
    def _deadline_live(deadline: object) -> bool:
        return docker._live(deadline)

    def _same_active_lease(self) -> bool:
        lease = self._lease
        try:
            return (
                type(lease) is transport.LifecycleLockLease
                and self._owner_port._lease is lease
                and not lease._released
            )
        except AttributeError:
            return False

    def _bootstrap_active(
        self, lease: transport.LifecycleLockLease, deadline: object
    ) -> bool:
        return (
            self._lease is lease
            and self._same_active_lease()
            and self._deadline_live(deadline)
        )

    def acquire_lock(self, *, deadline: Deadline) -> object | None:
        """Retain the exact owner-port lease for all coordinator callbacks."""
        if self._lease is not None or not self._deadline_live(deadline):
            return None
        try:
            lease = self._owner_port.acquire_lock(deadline=deadline)
            owner_lease = self._owner_port._lease
        except Exception:
            return None
        if (
            type(lease) is not transport.LifecycleLockLease
            or owner_lease is not lease
            or lease._released
        ):
            return None
        # Preserve a lease acquired just as the deadline expires so the
        # coordinator's finally path can still attempt its exact cleanup.
        self._lease = lease
        return lease

    def read_signed_owner(self, *, deadline: Deadline) -> OwnerEvidence:
        """Reread signed owner evidence only while the retained lease is held."""
        if not self._same_active_lease() or not self._deadline_live(deadline):
            raise RuntimeReadNotReady
        lease = self._lease
        if type(lease) is not transport.LifecycleLockLease:
            raise RuntimeReadNotReady
        try:
            owner = self._owner_port.read_signed_owner(deadline=deadline)
        except Exception:
            raise RuntimeReadNotReady from None
        if (
            not self._bootstrap_active(lease, deadline)
            or type(owner) is not OwnerEvidence
        ):
            raise RuntimeReadNotReady

        if self._lazy_core:
            if not self._bootstrap_active(lease, deadline):
                raise RuntimeReadNotReady
            try:
                resolved = docker.resolve_core_docker_pins(owner, deadline=deadline)
            except Exception:
                raise RuntimeReadNotReady from None
            if not self._bootstrap_active(lease, deadline):
                raise RuntimeReadNotReady
            if (
                type(resolved) is not tuple
                or len(resolved) != 2
                or type(resolved[0]) is not docker.DockerReadPins
                or type(resolved[1]) is not docker.ComposeConfigPins
                or not docker._factory_provenance_valid(resolved[0])
                or not self._valid_pins(
                    owner,
                    resolved[0].daemon_fingerprint,
                    resolved[0],
                    resolved[1],
                )
            ):
                raise RuntimeReadNotReady
            if not self._bootstrap_active(lease, deadline):
                raise RuntimeReadNotReady
            try:
                after_factory = self._owner_port.read_signed_owner(deadline=deadline)
            except Exception:
                raise RuntimeReadNotReady from None
            if (
                not self._bootstrap_active(lease, deadline)
                or type(after_factory) is not OwnerEvidence
                or after_factory != owner
            ):
                raise RuntimeReadNotReady
            try:
                docker_pins = replace(resolved[0])
                compose_pins = replace(resolved[1])
            except (AttributeError, TypeError, ValueError) as error:
                raise RuntimeReadNotReady from error
            if (
                not self._bootstrap_active(lease, deadline)
                or not self._valid_pins(
                    owner,
                    docker_pins.daemon_fingerprint,
                    docker_pins,
                    compose_pins,
                )
                or not docker._factory_provenance_valid(docker_pins)
            ):
                raise RuntimeReadNotReady
            self._docker_pins = docker_pins
            self._compose_pins = compose_pins
            self._lazy_core = False
            if not self._bootstrap_active(lease, deadline):
                raise RuntimeReadNotReady
            return after_factory
        return owner

    def release_lock(self, lease: object, *, deadline: Deadline) -> None:
        """Release only the exact lease captured by this composite port."""
        if (
            type(lease) is not transport.LifecycleLockLease
            or self._lease is not lease
            or self._owner_port._lease is not lease
            or lease._released
        ):
            raise RuntimeReadNotReady
        try:
            self._owner_port.release_lock(lease, deadline=deadline)
            owner_lease = self._owner_port._lease
        except Exception:
            raise RuntimeReadNotReady from None
        if owner_lease is not None or not lease._released:
            raise RuntimeReadNotReady
        self._lease = None

    @staticmethod
    def _valid_pins(
        owner: OwnerEvidence,
        pinned_daemon: object,
        docker_pins: object,
        compose_pins: object,
    ) -> bool:
        admitted = docker._compose_owner(owner)
        if (
            admitted is None
            or type(pinned_daemon) is not str
            or type(docker_pins) is not docker.DockerReadPins
            or type(compose_pins) is not docker.ComposeConfigPins
        ):
            return False
        try:
            return (
                docker._absolute_path(docker_pins.executable, allow_root=False)
                and docker._absolute_path(docker_pins.config_directory, allow_root=True)
                and docker._absolute_path(docker_pins.cwd, allow_root=True)
                and docker._local_endpoint(docker_pins.endpoint)
                and docker._fingerprint(docker_pins.daemon_fingerprint)
                and docker._environment(docker_pins.environment) is not None
                and docker_pins.cwd == admitted.worktree
                and docker_pins.daemon_fingerprint == admitted.daemon_fingerprint
                and pinned_daemon == admitted.daemon_fingerprint
                and docker._compose_layout(admitted, compose_pins)
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return False

    def observe_runtime(
        self,
        owner: OwnerEvidence,
        pinned_daemon: str,
        *,
        deadline: Deadline,
    ) -> RuntimeEvidence:
        """Observe complete owned Core inventory under two same-lease rereads."""
        self._runtime_diagnostic = RuntimeObservationPhase.RUNTIME_BINDING
        diagnostic = RuntimeObservationRecorder()
        if (
            not self._same_active_lease()
            or not self._deadline_live(deadline)
            or type(owner) is not OwnerEvidence
        ):
            raise RuntimeReadNotReady
        try:
            requested_owner = replace(owner)
            docker_pins = replace(self._docker_pins)
            compose_pins = replace(self._compose_pins)
        except (AttributeError, TypeError, ValueError) as error:
            raise RuntimeReadNotReady from error
        if not self._valid_pins(
            requested_owner, pinned_daemon, docker_pins, compose_pins
        ):
            raise RuntimeReadNotReady

        retained_lease = self._lease
        before = self.read_signed_owner(deadline=deadline)
        try:
            before_snapshot = replace(before)
        except (AttributeError, TypeError, ValueError) as error:
            raise RuntimeReadNotReady from error
        if before_snapshot != requested_owner:
            raise RuntimeReadNotReady

        # The helper receives distinct immutable snapshots. Keep these local
        # originals to detect a callback that mutates even a frozen object.
        helper_owner = replace(before_snapshot)
        helper_docker_pins = replace(docker_pins)
        helper_compose_pins = replace(compose_pins)
        try:
            evidence = docker.observe_owned_core_runtime(
                helper_owner,
                helper_docker_pins,
                helper_compose_pins,
                deadline=deadline,
                diagnostic=diagnostic,
            )
        except Exception:
            self._runtime_diagnostic = (
                diagnostic.phase or RuntimeObservationPhase.RUNTIME_BINDING
            )
            raise RuntimeReadNotReady from None
        if (
            not self._deadline_live(deadline)
            or self._lease is not retained_lease
            or not self._same_active_lease()
            or helper_owner != before_snapshot
            or helper_docker_pins != docker_pins
            or helper_compose_pins != compose_pins
        ):
            raise RuntimeReadNotReady

        after = self.read_signed_owner(deadline=deadline)
        if (
            after != before_snapshot
            or owner != before_snapshot
            or not self._deadline_live(deadline)
            or self._lease is not retained_lease
            or not self._same_active_lease()
        ):
            raise RuntimeReadNotReady
        if type(evidence) is not RuntimeEvidence:
            self._runtime_diagnostic = (
                diagnostic.phase or RuntimeObservationPhase.RUNTIME_BINDING
            )
            raise RuntimeReadNotReady
        self._runtime_diagnostic = None
        return evidence

    def __repr__(self) -> str:
        return "<OwnedCoreRuntimePort>"
