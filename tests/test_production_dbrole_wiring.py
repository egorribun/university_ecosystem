"""Source contracts; deployed authentication and identity need PostgreSQL proof."""

from pathlib import Path

from tests.test_aud191_production_compose_env_contract import (
    _compose,
    _merged_environment,
)

ROOT = Path(__file__).resolve().parents[1]


def test_roles_init_uses_secret_files_without_password_arguments() -> None:
    base = _compose("docker-compose.yml")["services"]["postgres-roles-init"]
    production = _compose("docker-compose.prod.yml")["services"]["postgres-roles-init"]
    environment = _merged_environment(base, production)
    for name in (
        "PGPASSWORD",
        "UE_MIGRATOR_DB_PASSWORD",
        "UE_APP_DB_PASSWORD",
        "UE_WORKER_DB_PASSWORD",
    ):
        assert name not in environment
        assert environment[f"{name}_FILE"].startswith("/run/secrets/")
    assert base["entrypoint"] == ["/bin/sh", "/bootstrap/run-bootstrap.sh"]
    assert "command" not in base
    full = _compose("docker-compose.full.yml")["services"]["postgres-roles-init"]
    assert full["entrypoint"] == base["entrypoint"]
    assert "command" not in full
    wrapper = (ROOT / "infrastructure/postgres-roles/run-bootstrap.sh").read_text()
    assert "psql -X --no-password" in wrapper
    assert "-v migrator_password" not in wrapper
    assert "-v app_password" not in wrapper
    assert "-v worker_password" not in wrapper
    assert "2>&1 >/dev/null" in wrapper
    assert "| collect_outcome" in wrapper
    assert "-v VERBOSITY=sqlstate -v SHOW_CONTEXT=never" in wrapper
    for setting in (
        "log_statement=none",
        "log_min_error_statement=panic",
        "log_min_duration_statement=-1",
        "log_min_duration_sample=-1",
        "log_transaction_sample_rate=0",
        "log_parameter_max_length_on_error=0",
    ):
        assert f"-c {setting}" in wrapper
    assert "export PGOPTIONS" in wrapper
    driver = (
        ROOT / "infrastructure/postgres-roles/bootstrap-from-environment.sql"
    ).read_text()
    for role in ("migrator", "app", "worker"):
        assert f"\\getenv {role}_password UE_{role.upper()}_DB_PASSWORD" in driver


def test_pooler_preserves_runtime_identities_and_excludes_admin_credentials() -> None:
    services = _compose("docker-compose.prod.yml")["services"]
    pooler = services["pgbouncer"]
    assert set(pooler["secrets"]) == {"ue_app_db_password", "ue_worker_db_password"}
    assert set(pooler["environment"]) == {"POSTGRES_DB"}
    assert pooler["entrypoint"] == ["/bin/sh", "/pooler/start.sh"]
    assert (
        pooler["depends_on"]["postgres-roles-init"]["condition"]
        == "service_completed_successfully"
    )
    script = (ROOT / "infrastructure/pgbouncer/start.sh").read_text()
    mapping = script.split("[databases]\n", 1)[1].split("[pgbouncer]", 1)[0]
    assert mapping == "${POSTGRES_DB} = host=postgres port=5432\n"
    assert "auth_type = scram-sha-256" in script
    assert "umask 077" in script
    assert "write_user ue_app /run/secrets/ue_app_db_password" in script
    assert "write_user ue_worker /run/secrets/ue_worker_db_password" in script
    assert "/entrypoint.sh" not in script
    assert "pgbouncer" not in services["migrations"]["depends_on"]
