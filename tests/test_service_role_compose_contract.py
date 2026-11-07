"""Compose contract: SpiceDB and Temporal log in as their own roles, and the daily
partition-retention service runs without overlap as the schema owner.

The full Compose files are parsed as YAML after the override tags are removed, the
same way test_compose_runtime_credential_isolation.py reads them. Behaviour against
a real server is proven in test_service_role_bootstrap_postgres.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = "docker-compose.yml"
FULL = "docker-compose.full.yml"
PROD = "docker-compose.prod.yml"
ROLES_READY = {"postgres-roles-init": {"condition": "service_completed_successfully"}}
# The role and database names are read from the bootstrap source, so this contract
# cannot drift from the role that infrastructure/postgres-roles creates.
SERVICE_ROLES_SQL = (
    ROOT / "infrastructure" / "postgres-roles" / "bootstrap-service-roles.sql"
)


def _source_owners() -> dict[str, str]:
    """Map each service database to its owning login, as the bootstrap SQL declares."""
    source = SERVICE_ROLES_SQL.read_text(encoding="utf-8")
    owners = dict(re.findall(r"\('(\w+)', '(ue_\w+)'\)", source))
    assert owners == {
        "spicedb": "ue_spicedb",
        "temporal": "ue_temporal",
        "temporal_visibility": "ue_temporal",
    }, owners
    return owners


SPICEDB_ROLE = _source_owners()["spicedb"]
TEMPORAL_ROLE = _source_owners()["temporal"]


def _load(name: str) -> dict[str, Any]:
    source = (ROOT / name).read_text(encoding="utf-8")
    source = source.replace("!override", "").replace("!reset", "")
    document: dict[str, Any] = yaml.safe_load(source)
    return document


def _services(name: str) -> dict[str, Any]:
    services: dict[str, Any] = _load(name)["services"]
    return services


def _environment(service: dict[str, Any]) -> dict[str, Any]:
    environment: dict[str, Any] = service.get("environment") or {}
    return environment


def test_spicedb_migrate_and_server_log_in_as_spicedb_role_only() -> None:
    for name in (BASE, FULL):
        services = _services(name)
        for service_name in ("spicedb-migrate", "spicedb"):
            service = services[service_name]
            command = yaml.safe_dump(service.get("command"))
            assert f"postgres://{SPICEDB_ROLE}@postgres:5432/spicedb" in command, (
                name,
                service_name,
            )
            assert "POSTGRES_USER" not in yaml.safe_dump(service), (name, service_name)
            environment = _environment(service)
            assert environment["PGPASSWORD"].startswith("${UE_SPICEDB_DB_PASSWORD:?"), (
                name,
                service_name,
            )
            assert "POSTGRES_PASSWORD" not in yaml.safe_dump(service), (
                name,
                service_name,
            )
            assert (
                service["depends_on"]["postgres-roles-init"]
                == (ROLES_READY["postgres-roles-init"])
            ), (name, service_name)


def test_temporal_admin_tools_and_server_log_in_as_temporal_role_only() -> None:
    for name in (BASE, FULL):
        services = _services(name)
        admin = services["temporal-admin-tools"]
        admin_env = _environment(admin)
        assert admin_env["SQL_USER"] == TEMPORAL_ROLE, name
        assert admin_env["SQL_PASSWORD"].startswith("${UE_TEMPORAL_DB_PASSWORD:?"), name
        assert "POSTGRES_PASSWORD" not in yaml.safe_dump(admin), name
        assert (
            admin["depends_on"]["postgres-roles-init"]
            == ROLES_READY["postgres-roles-init"]
        ), name

        server = services["temporal"]
        server_env = _environment(server)
        assert server_env["POSTGRES_USER"] == TEMPORAL_ROLE, name
        assert server_env["POSTGRES_PWD"].startswith("${UE_TEMPORAL_DB_PASSWORD:?"), (
            name
        )
        assert "POSTGRES_PASSWORD" not in yaml.safe_dump(server), name
        assert (
            server["depends_on"]["postgres-roles-init"]
            == ROLES_READY["postgres-roles-init"]
        ), name


def test_roles_init_receives_both_service_passwords_after_databases_exist() -> None:
    for name in (BASE, FULL):
        roles = _services(name)["postgres-roles-init"]
        environment = _environment(roles)
        assert "UE_SPICEDB_DB_PASSWORD" in environment, name
        assert "UE_TEMPORAL_DB_PASSWORD" in environment, name
        assert roles["depends_on"]["postgres-databases-init"] == {
            "condition": "service_completed_successfully"
        }, name


def test_prod_overlay_feeds_the_service_passwords_from_secret_files() -> None:
    document = _load(PROD)
    secrets = document["secrets"]
    for secret, variable in (
        ("ue_spicedb_db_password", "UE_SPICEDB_DB_PASSWORD_SOURCE_FILE"),
        ("ue_temporal_db_password", "UE_TEMPORAL_DB_PASSWORD_SOURCE_FILE"),
    ):
        assert variable in secrets[secret]["file"], secret
    roles = _services(PROD)["postgres-roles-init"]
    environment = _environment(roles)
    assert environment["UE_SPICEDB_DB_PASSWORD_FILE"] == (
        "/run/secrets/ue_spicedb_db_password"
    )
    assert environment["UE_TEMPORAL_DB_PASSWORD_FILE"] == (
        "/run/secrets/ue_temporal_db_password"
    )
    assert {"ue_spicedb_db_password", "ue_temporal_db_password"} <= set(
        roles["secrets"]
    )


def test_partition_maintenance_runs_daily_without_overlap_as_the_owner() -> None:
    service = _services(FULL)["partition-maintenance"]
    script = service["command"][-1]
    assert "python -m app.services.partition_manager" in script
    assert "sleep 86400" in script
    assert "sleep 900" in script
    # One sequential loop: the next run starts only after the previous one returns.
    assert script.index("python -m app.services.partition_manager") < script.index(
        "sleep 86400"
    )
    assert service["env_file"] == ["docker-compose.runtime-app.allowlist"]
    environment = _environment(service)
    assert environment["DATABASE_URL"].startswith(
        "postgresql+asyncpg://ue_migrator:${UE_MIGRATOR_DB_PASSWORD:?"
    )
    assert service["depends_on"]["migrations"] == {
        "condition": "service_completed_successfully"
    }
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert "ports" not in service
    assert service["restart"] == "unless-stopped"


def test_partition_maintenance_is_only_in_the_full_stack() -> None:
    assert "partition-maintenance" not in _services(BASE)
    assert "partition-maintenance" not in _services(PROD)
