"""Reusable, I/O-free snapshots matching the signed Core test projection."""

from __future__ import annotations

from scripts.owned_nats_outage import ContainerSnapshot

# A full signed Core projection fixture, not a duplicated production selector.
CORE_SERVICES = (
    "backend",
    "caddy",
    "flagd",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "mailpit",
    "migrations",
    "minio",
    "minio-init",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "postgres-databases-init",
    "redis",
    "revocation-redis",
    "spicedb",
    "spicedb-migrate",
    "tempo",
    "tempo-healthprobe",
    "ws-hub",
)
NO_HEALTHCHECK = frozenset({"caddy", "flagd", "gateway", "mailpit", "tempo", "ws-hub"})
CORE_INITIALIZERS = frozenset(
    {"migrations", "minio-init", "postgres-databases-init", "spicedb-migrate"}
)


def core_container_snapshots() -> tuple[ContainerSnapshot, ...]:
    return tuple(
        ContainerSnapshot(
            container_id=f"{index:064x}",
            service=service,
            identity=f"{index + 100:064x}",
            running=service not in CORE_INITIALIZERS,
            status="exited" if service in CORE_INITIALIZERS else "running",
            health=(
                None
                if service in CORE_INITIALIZERS or service in NO_HEALTHCHECK
                else "healthy"
            ),
            restart_count=0,
            exit_code=0,
            oom_killed=False,
        )
        for index, service in enumerate(CORE_SERVICES, 1)
    )


