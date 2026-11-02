"""Runtime services connect as dedicated login roles, never as the bootstrap superuser.

Row-level security isolates tenant rows only while the connecting role is neither a
superuser nor BYPASSRLS. These contracts keep every deployment surface on that model:
the Compose files, the Helm chart, the environment examples, the role bootstrap and
the launcher that generates its passwords. The database behaviour itself (isolation,
DML-only grants, convergence on reruns) was proven against a live PostgreSQL 17 when
the bootstrap was introduced; this module guards the wiring that keeps it true.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.test_helm_staging_contract import _render_staging

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
BOOTSTRAP_SQL = ROOT / "infrastructure" / "postgres-roles" / "bootstrap-app-roles.sql"
ROLES_MOUNT = "./infrastructure/postgres-roles:/bootstrap:ro"
COMPOSE_FILES = tuple(sorted(path.name for path in ROOT.glob("docker-compose*.yml")))

# The login each Compose service may use for DATABASE_URL.
RUNTIME_ROLE_BY_SERVICE = {
    "backend": "ue_app",
    "outbox-worker": "ue_app",
    "notifications-worker": "ue_worker",
    "migrations": "ue_migrator",
}
# The disposable test-runner stack keeps the bootstrap superuser. Its integration
# suite creates roles, extensions and fixtures, and it is never deployed. Converting
# it needs an owner decision, so this exception is named rather than implied.
TEST_RUNNER_SUPERUSER_EXCEPTIONS = {("docker-compose.test.yml", "tests")}
_ROLE_URL = re.compile(r"postgresql\+asyncpg://([^:/@]+):")
_WHOLE_VARIABLE = re.compile(r"\$\{([A-Z][A-Z0-9_]*):\?[^}]*\}")


def _compose(name: str) -> dict[str, Any]:
    # Compose's `!reset` and `!override` tags have no PyYAML meaning; drop them.
    text = (ROOT / name).read_text(encoding="utf-8")
    loaded: dict[str, Any] = yaml.safe_load(
        text.replace("!override", "").replace("!reset", "")
    )
    return loaded


def _env_example_value(variable: str) -> str:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{variable}="):
            return line.split("=", 1)[1]
    raise AssertionError(f".env.example does not define {variable}")


def _database_user(value: str) -> str:
    """Return the login named by a DATABASE_URL value or by its example variable."""
    whole = _WHOLE_VARIABLE.fullmatch(value)
    if whole:
        example = _env_example_value(whole.group(1))
        match = _ROLE_URL.match(example)
        assert match, f"{whole.group(1)} has no login in .env.example"
        return match.group(1)
    match = _ROLE_URL.match(value)
    assert match, "DATABASE_URL does not name a login"
    return match.group(1)


@pytest.mark.parametrize("compose_name", COMPOSE_FILES)
def test_compose_database_urls_use_the_dedicated_login_of_each_service(
    compose_name: str,
) -> None:
    services = _compose(compose_name).get("services") or {}
    for service_name, service in services.items():
        environment = service.get("environment")
        if not isinstance(environment, dict):
            continue
        url = environment.get("DATABASE_URL")
        if not isinstance(url, str):
            continue
        user = _database_user(url)
        if (compose_name, service_name) in TEST_RUNNER_SUPERUSER_EXCEPTIONS:
            assert user == "postgres", "the documented test-runner exception moved"
            continue
        assert service_name in RUNTIME_ROLE_BY_SERVICE, (
            f"{compose_name}:{service_name} must not receive a database URL"
        )
        assert user == RUNTIME_ROLE_BY_SERVICE[service_name], (
            f"{compose_name}:{service_name} connects as {user!r}"
        )
        assert user != "postgres"


def test_production_database_secrets_are_split_by_service() -> None:
    prod = _compose("docker-compose.prod.yml")
    secrets = prod["secrets"]
    secret_by_service = {
        "backend": "database_url",
        "outbox-worker": "database_url",
        "notifications-worker": "notifications_database_url",
        "migrations": "migration_database_url",
    }
    source_by_secret = {
        "database_url": "DATABASE_URL_SOURCE_FILE",
        "notifications_database_url": "NOTIFICATIONS_DATABASE_URL_SOURCE_FILE",
        "migration_database_url": "MIGRATION_DATABASE_URL_SOURCE_FILE",
    }
    for secret_name, source in source_by_secret.items():
        assert source in secrets[secret_name]["file"]
    for service_name, secret_name in secret_by_service.items():
        service = prod["services"][service_name]
        assert secret_name in service["secrets"]
        assert service["environment"]["DATABASE_URL_FILE"] == (
            f"/run/secrets/{secret_name}"
        )
    # The migration Job and the notifications worker never mount the runtime URL.
    for service_name in ("migrations", "notifications-worker"):
        assert "database_url" not in prod["services"][service_name]["secrets"]


def test_bootstrap_grants_are_dml_only_and_bypass_only_for_the_worker() -> None:
    sql = BOOTSTRAP_SQL.read_text(encoding="utf-8")
    assert re.search(r"ALTER ROLE ue_app WITH LOGIN NOSUPERUSER [^;]*NOBYPASSRLS", sql)
    assert re.search(
        r"ALTER ROLE ue_worker WITH LOGIN NOSUPERUSER [^;]*NOBYPASSRLS", sql
    )
    assert re.search(r"ALTER ROLE ue_migrator WITH LOGIN SUPERUSER", sql)

    # Membership in ue_rls_bypass is the only query-level authority; the worker is its
    # only grantee, and any drifted membership on the runtime login is revoked.
    assert re.findall(r"GRANT ue_rls_bypass TO (\w+);", sql) == ["ue_worker"]
    assert "REVOKE ue_rls_bypass FROM ue_app" in sql

    privilege_lines = [
        line
        for line in sql.splitlines()
        if line.startswith(("GRANT ", "ALTER DEFAULT PRIVILEGES"))
        and "ue_rls_bypass" not in line
        and "CONNECT" not in line
    ]
    assert privilege_lines
    forbidden = re.compile(
        r"\b(TRUNCATE|REFERENCES|TRIGGER|ALL PRIVILEGES|CREATE|BYPASSRLS|SUPERUSER)\b"
    )
    for line in privilege_lines:
        assert not forbidden.search(line), line
    assert any("ON TABLES" in line and "DELETE" in line for line in privilege_lines)
    assert any("ON SEQUENCES" in line for line in privilege_lines)
    assert "REVOKE CREATE ON SCHEMA public FROM ue_app, ue_worker;" in sql


def test_role_bootstrap_runs_only_through_the_roles_job() -> None:
    for name in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(name)["services"]
        roles_job = services["postgres-roles-init"]
        assert ROLES_MOUNT in roles_job["volumes"]
        assert roles_job["restart"] == "no"
        assert roles_job["depends_on"]["postgres"]["condition"] == "service_healthy"
        assert roles_job["read_only"] is True
        for service_name, service in services.items():
            if service_name == "postgres-roles-init":
                continue
            for volume in service.get("volumes") or []:
                assert "infrastructure/postgres-roles" not in str(volume), service_name
        migrations = services["migrations"]["depends_on"]
        assert migrations["postgres-roles-init"]["condition"] == (
            "service_completed_successfully"
        )

    # Files in the initdb directory run without psql variables on first start, so no
    # role statement may live there.
    for path in (ROOT / "infrastructure" / "postgres-init").iterdir():
        assert "ROLE" not in path.read_text(encoding="utf-8").upper(), path.name


def test_chart_projects_the_owner_url_only_into_the_migration_job() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    connections = values["connections"]
    assert connections["databaseURLKey"] == "database-url"
    assert connections["migrationDatabaseURLKey"] == "migration-database-url"

    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
    assert (
        "migrationDatabaseURLKey" in schema["properties"]["connections"]["properties"]
    )

    job = (CHART / "templates" / "migration-job.yaml").read_text(encoding="utf-8")
    assert "connections.migrationDatabaseURLKey" in job
    assert "connections.databaseURLKey" not in job
    for template in ("backend-deployment.yaml", "outbox-worker-deployment.yaml"):
        text = (CHART / "templates" / template).read_text(encoding="utf-8")
        assert "connections.databaseURLKey" in text, template
        assert "migrationDatabaseURLKey" not in text, template


def test_chart_refuses_one_key_for_both_runtime_and_owner_urls() -> None:
    with pytest.raises(subprocess.CalledProcessError) as raised:
        _render_staging("--set", "connections.migrationDatabaseURLKey=database-url")
    stderr = raised.value.stderr
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    assert "must differ" in (text or "")


def test_launcher_generates_and_mirrors_the_database_role_passwords() -> None:
    script = (ROOT / "start-docker.ps1").read_text(encoding="utf-8")
    for key in (
        "UE_MIGRATOR_DB_PASSWORD",
        "UE_APP_DB_PASSWORD",
        "UE_WORKER_DB_PASSWORD",
    ):
        # One template line in each of .env.docker and .env.
        assert script.count(f"{key}=$") == 2, key
        assert f'"{key}"' in script, key
    assert "function Ensure-DatabaseRolePasswords" in script
    assert "\nEnsure-DatabaseRolePasswords\n" in script
    assert "'POSTGRES_(?:USER|PASSWORD)|'" in script
    assert "'UE_(?:MIGRATOR|APP|WORKER)_DB_PASSWORD)='" in script


def test_env_examples_name_each_runtime_login() -> None:
    assert _database_user("${DATABASE_URL:?set}") == "ue_app"
    assert _database_user("${NOTIFICATIONS_DATABASE_URL:?set}") == "ue_worker"
    assert _database_user("${MIGRATION_DATABASE_URL:?set}") == "ue_migrator"
    env_docker = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
    for key in (
        "UE_MIGRATOR_DB_PASSWORD",
        "UE_APP_DB_PASSWORD",
        "UE_WORKER_DB_PASSWORD",
    ):
        assert f"{key}=" in env_docker, key
        assert f"{key}=" in (ROOT / ".env.example").read_text(encoding="utf-8"), key


def test_configuration_reference_documents_each_login_role() -> None:
    document = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")
    for token in (
        "`ue_app`",
        "`ue_worker`",
        "`ue_migrator`",
        "`ue_rls_bypass`",
        "`NOTIFICATIONS_DATABASE_URL`",
        "`MIGRATION_DATABASE_URL`",
        "`UE_APP_DB_PASSWORD`",
        "BYPASSRLS",
    ):
        assert token in document, token
