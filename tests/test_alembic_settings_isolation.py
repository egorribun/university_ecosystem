"""Migration bootstrap must not create a new runtime idempotency-key consumer.

Only offline environment/metadata loading is exercised. Historical revisions
that encrypt, sign, or access Redis retain their separate capability requirements.
No migration is applied, and no runtime settings validation is replaced.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

pytest_plugins = ("pytester",)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_ENTRYPOINT = PROJECT_ROOT / "alembic" / "env.py"
# Preserve only ordinary process plumbing, never application settings or CI
# exemptions. Python's interpreter and installed packages come from pytester.
_PROCESS_ENVIRONMENT = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
)

_CHILD_SOURCE = r'''
"""Clean-process probes with no revision DDL or inherited application settings."""

import contextlib
import importlib
import importlib.abc
import io
import json
import logging
import os
from pathlib import Path
import secrets
import sys

from pydantic import ValidationError


def _configure_runtime_environment(*, include_idempotency):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    spotify_key = Fernet.generate_key().decode("ascii")
    totp_key = Fernet.generate_key().decode("ascii")
    assert spotify_key != totp_key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    generated = {
        name: secrets.token_urlsafe(48)
        for name in (
            "SECRET_KEY",
            "NATS_AUTH_TOKEN",
            "AUDIT_LOG_SECRET",
            "TOKEN_HMAC_SECRET",
            "CSRF_HMAC_SECRET",
            "INTERNAL_HMAC_SECRET",
            "INTERNAL_AUTH_TOKEN",
            "SPICEDB_PRESHARED_KEY",
            "WS_HUB_INTERNAL_SECRET",
            "ELASTICSEARCH_PASSWORD",
        )
    }
    generated.update(
        {
            "SPOTIFY_TOKEN_SECRET": spotify_key,
            "MFA_TOTP_ENCRYPTION_KEYS": f"isolated:{totp_key}",
            "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID": "isolated",
            "CACHE_REDIS_URL": "redis://cache.alembic-isolation.invalid:6379/0",
            "REVOCATION_REDIS_URL": (
                "redis://revocation.alembic-isolation.invalid:6379/0"
            ),
            "RATE_LIMIT_STORAGE_BACKEND": "redis",
            "RATE_LIMIT_STORAGE_URI": (
                "redis://rate-limit.alembic-isolation.invalid:6379/1"
            ),
            "TRUSTED_PROXIES": "10.0.0.0/8",
            "EVENT_FILE_SCANNER_ENABLED": "true",
            "EVENT_FILE_SCANNER_HOST": "clamd.alembic-isolation.invalid",
            "MINIO_SECURE": "true",
            "ELASTICSEARCH_URL": "https://search.alembic-isolation.invalid",
            "SMTP_HOST": "relay.alembic-isolation.invalid",
            "SMTP_PORT": "587",
            "SMTP_SECURITY": "starttls",
            "ALGORITHM": "RS256",
            "JWT_PRIVATE_KEY_PATH": "",
            "JWT_SIGNING_KEYS": json.dumps([f"isolated-rs256:{private_pem}"]),
            "JWT_ACTIVE_KID": "isolated-rs256",
        }
    )
    if include_idempotency:
        generated["IDEMPOTENCY_HMAC_SECRET"] = secrets.token_urlsafe(48)
    os.environ.update(generated)


def _bootstrap_metadata():
    import sqlalchemy as sa

    from alembic.config import Config
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory

    environment_file = Path(os.environ["MIGRATION_ISOLATION_ENTRYPOINT"])
    output = io.StringIO()
    config = Config(output_buffer=output)
    config.set_main_option("script_location", str(environment_file.parent))
    config.set_main_option("path_separator", "os")
    script = ScriptDirectory.from_config(config)
    assert Path(script.env_py_location).resolve() == environment_file.resolve()
    callbacks = []

    def inspect_loaded_metadata(revisions, migration_context):
        assert revisions == ()
        assert migration_context.as_sql is True
        assert migration_context.dialect.name == "postgresql"
        metadata = migration_context.opts["target_metadata"]
        assert isinstance(metadata, sa.MetaData)
        expected_columns = {
            "users": {"id", "email"},
            "events": {"id", "search_vector"},
            "messages": {"id", "chat_id"},
            "stored_events": {
                "id",
                "aggregate_id_uuid",
                "sequence_number",
                "processed_at",
            },
            "tenants": {"id"},
        }
        for table_name, columns in expected_columns.items():
            assert table_name in metadata.tables
            assert columns <= set(metadata.tables[table_name].c.keys())
        assert {"user_stats", "vector_chunks"} <= set(metadata.tables)
        expected_indexes = {
            "ix_chat_participants_user_id_chat_id",
            "ix_chat_participants_chat_id_user_id",
            "ix_messages_unread_chat_sender",
            "idx_messages_chat_pagination_covering",
            "idx_news_comment_cursor",
            "ix_stored_events_pending_created",
            "ix_stored_events_pending_aggregate_created",
            "ix_stored_events_aggregate_uuid",
        }
        actual_indexes = {
            index.name
            for table in metadata.tables.values()
            for index in table.indexes
        }
        assert expected_indexes <= actual_indexes
        callbacks.append(True)
        # No historical revision function is selected or executed.
        return ()

    with EnvironmentContext(
        config,
        script,
        fn=inspect_loaded_metadata,
        as_sql=True,
        starting_rev="base",
        destination_rev="base",
        output_buffer=output,
    ):
        script.run_env()

    assert callbacks == [True]
    assert set(output.getvalue().split()) <= {"BEGIN;", "COMMIT;"}
    return {"outcome": "metadata-loaded", "callbacks": 1, "revision_ddl": False}


def _safe_validation_error(error):
    # Never return input values, exception context, rendered messages, or secrets.
    errors = error.errors(
        include_url=False, include_context=False, include_input=False
    )
    expected_message = (
        "Value error, Production secret validation failed:\n"
        "  · IDEMPOTENCY_HMAC_SECRET must be set in production. "
        "An empty value makes idempotency keys enumerable from the "
        "Idempotency-Key request header."
    )
    return {
        "outcome": "validation-error",
        "errors": [
            {"loc": list(item["loc"]), "type": item["type"]} for item in errors
        ],
        "idempotency_only": (
            len(errors) == 1
            and errors[0]["loc"] == ()
            and errors[0]["type"] == "value_error"
            and errors[0]["msg"] == expected_message
        ),
    }


def _assert_runtime_validation_after_metadata(mode):
    if mode == "migration-db-only":
        try:
            importlib.import_module("app.core.config")
        except RuntimeError as error:
            assert getattr(error, "missing_required", ()) == ("SECRET_KEY",)
        else:
            raise AssertionError("Ordinary runtime accepted a missing SECRET_KEY")
    elif mode == "migration-without-idempotency":
        try:
            importlib.import_module("app.core.config")
        except ValidationError as error:
            assert _safe_validation_error(error)["idempotency_only"] is True
        else:
            raise AssertionError("Ordinary runtime accepted missing idempotency HMAC")
    else:
        configuration = importlib.import_module("app.core.config")
        assert configuration.settings.idempotency_hmac_secret
        assert not configuration.settings.has_development_fallbacks


def test_clean_process_probe():
    assert "app.core.config" not in sys.modules
    assert "app.models" not in sys.modules
    assert "tests.conftest" not in sys.modules
    assert "CI" not in os.environ
    assert "GITHUB_ACTIONS" not in os.environ
    assert "PYTEST_PLUGINS" not in os.environ
    assert "PYTEST_ADDOPTS" not in os.environ
    assert os.environ["ENVIRONMENT"] in {"production", "staging"}
    assert os.environ["ENV_FILE_PATH"] == ""
    assert "IDEMPOTENCY_HMAC_SECRET" not in os.environ
    assert "IDEMPOTENCY_HMAC_SECRET_FILE" not in os.environ
    assert not any(name.endswith("_FILE") for name in os.environ)

    mode = os.environ["MIGRATION_ISOLATION_MODE"]
    assert mode in {
        "migration-configured",
        "migration-db-only",
        "migration-without-idempotency",
        "partition-configured",
        "partition-without-idempotency",
        "runtime-configured",
        "runtime-without-idempotency",
    }
    forbidden_imports = []

    class RuntimeImportGuard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if (
                fullname == "app.core.config"
                or fullname.startswith("app.core.config.")
                or fullname == "app.core.database"
                or fullname == "app.utils.encryption"
            ):
                forbidden_imports.append(fullname)
                raise ImportError("Runtime import is forbidden during metadata loading")
            return None

    forbidden_attempts = []

    def forbid_external_effects(event, _arguments):
        if event in {
            "socket.connect",
            "socket.getaddrinfo",
            "socket.bind",
            "socket.sendto",
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
            "os.exec",
            "os.fork",
            "sqlite3.connect",
        }:
            forbidden_attempts.append(event)
            raise RuntimeError("External effects are forbidden in this offline probe")

    sys.addaudithook(forbid_external_effects)
    logging.disable(logging.CRITICAL)
    # Pytester prints child output; retain imports/validation logs privately.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
        io.StringIO()
    ):
        try:
            if mode != "migration-db-only":
                _configure_runtime_environment(
                    include_idempotency=mode.endswith("-configured")
                )
            if mode.startswith("migration-"):
                guard = RuntimeImportGuard()
                sys.meta_path.insert(0, guard)
                try:
                    result = _bootstrap_metadata()
                finally:
                    sys.meta_path.remove(guard)
                assert forbidden_imports == []
                assert not any(
                    name == "app.core.config"
                    or name.startswith("app.core.config.")
                    or name in {"app.core.database", "app.utils.encryption"}
                    for name in sys.modules
                )
                _assert_runtime_validation_after_metadata(mode)
            elif mode.startswith("partition-"):
                partition = importlib.import_module("app.services.partition_manager")
                database = importlib.import_module("app.core.database")
                assert database._engine is None
                assert partition.engine is database.engine
                result = {"outcome": "partition-loaded", "database_initialized": False}
            else:
                configuration = importlib.import_module("app.core.config")
                configured = configuration.Settings()
                assert configured.environment == os.environ["ENVIRONMENT"]
                assert configured.app_process_role == "api"
                assert not configured.has_development_fallbacks
                assert configured.idempotency_hmac_secret
                assert configured.password_hibp_check_enabled is True
                result = {"outcome": "runtime-loaded", "development_fallbacks": False}
        except ValidationError as error:
            result = _safe_validation_error(error)
        except RuntimeError as error:
            missing = getattr(error, "missing_required", ())
            result = {
                "outcome": "runtime-error",
                "missing_required": list(missing),
            }
        except Exception as error:
            result = {"outcome": "unexpected-error", "kind": type(error).__name__}

    assert forbidden_attempts == []
    assert forbidden_imports == []
    Path(os.environ["MIGRATION_ISOLATION_RESULT"]).write_text(
        json.dumps(result, sort_keys=True) + "\n", encoding="utf-8"
    )
'''


@pytest.fixture
def isolated_alembic_probe(pytester, monkeypatch: pytest.MonkeyPatch):
    ast.parse(_CHILD_SOURCE)
    assert ALEMBIC_ENTRYPOINT.is_file()
    probe = pytester.makepyfile(test_isolated_probe=_CHILD_SOURCE)
    ini = pytester.makeini("[pytest]\n")
    result_path = pytester.path / "safe-result.json"

    def run(mode: str, environment: str) -> dict[str, object]:
        assert environment in {"production", "staging"}
        if result_path.exists():
            result_path.unlink()
        process_environment = {
            name: os.environ[name]
            for name in _PROCESS_ENVIRONMENT
            if name in os.environ
        }
        process_environment.update(
            {
                "PYTHONPATH": str(PROJECT_ROOT),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONNOUSERSITE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "ENV_FILE_PATH": "",
                "ENVIRONMENT": environment,
                "DATABASE_URL": (
                    "postgresql+asyncpg://migration.alembic-isolation.invalid/"
                    "offline_probe"
                ),
                "AUTO_CREATE_SCHEMA": "false",
                "MIGRATION_ISOLATION_ENTRYPOINT": str(ALEMBIC_ENTRYPOINT),
                "MIGRATION_ISOLATION_MODE": mode,
                "MIGRATION_ISOLATION_RESULT": str(result_path),
            }
        )
        with monkeypatch.context() as child_environment:
            for name in tuple(os.environ):
                child_environment.delenv(name)
            for name, value in process_environment.items():
                child_environment.setenv(name, value)
            result = pytester.runpytest_subprocess(
                "-c",
                str(ini),
                "--noconftest",
                f"--confcutdir={pytester.path}",
                "-p",
                "no:cacheprovider",
                "-q",
                "--tb=no",
                str(probe),
                timeout=30,
            )

        result.assert_outcomes(passed=1)
        assert result.ret == pytest.ExitCode.OK
        assert result_path.is_file(), (
            "Clean-process probe did not write its safe result"
        )
        return json.loads(result_path.read_text(encoding="utf-8"))

    return run


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_configured_offline_alembic_loads_real_metadata_without_revision_ddl(
    isolated_alembic_probe, environment: str
) -> None:
    result = isolated_alembic_probe("migration-configured", environment)

    assert result == {
        "outcome": "metadata-loaded",
        "callbacks": 1,
        "revision_ddl": False,
    }


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_database_only_offline_alembic_loads_real_metadata(
    isolated_alembic_probe, environment: str
) -> None:
    result = isolated_alembic_probe("migration-db-only", environment)

    assert result == {
        "outcome": "metadata-loaded",
        "callbacks": 1,
        "revision_ddl": False,
    }


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_offline_alembic_does_not_require_runtime_idempotency_hmac(
    isolated_alembic_probe, environment: str
) -> None:
    result = isolated_alembic_probe("migration-without-idempotency", environment)

    assert result == {
        "outcome": "metadata-loaded",
        "callbacks": 1,
        "revision_ddl": False,
    }


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_migration_job_partition_step_still_uses_runtime_validation(
    isolated_alembic_probe, environment: str
) -> None:
    """Track R7's remaining runtime-settings dependency until isolation lands.

    Expire this characterization when the partition-maintenance command uses
    database-only settings; see R7 in docs/audits/AUDIT-2026-11-01-review.md.
    The migration Job launches Alembic and partition maintenance separately.
    """
    migration = isolated_alembic_probe("migration-without-idempotency", environment)
    partition = isolated_alembic_probe("partition-without-idempotency", environment)

    assert migration == {
        "outcome": "metadata-loaded",
        "callbacks": 1,
        "revision_ddl": False,
    }
    assert partition == {
        "outcome": "validation-error",
        "errors": [{"loc": [], "type": "value_error"}],
        "idempotency_only": True,
    }


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_partition_step_imports_with_full_settings_without_initializing_database(
    isolated_alembic_probe, environment: str
) -> None:
    result = isolated_alembic_probe("partition-configured", environment)

    assert result == {"outcome": "partition-loaded", "database_initialized": False}


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_ordinary_runtime_settings_accept_complete_configuration(
    isolated_alembic_probe, environment: str
) -> None:
    result = isolated_alembic_probe("runtime-configured", environment)

    assert result == {"outcome": "runtime-loaded", "development_fallbacks": False}


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_ordinary_runtime_settings_still_reject_missing_idempotency_hmac(
    isolated_alembic_probe, environment: str
) -> None:
    result = isolated_alembic_probe("runtime-without-idempotency", environment)

    assert result == {
        "outcome": "validation-error",
        "errors": [{"loc": [], "type": "value_error"}],
        "idempotency_only": True,
    }


def test_probe_discards_parent_database_and_env_file_redirections(
    isolated_alembic_probe, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    poisoned_env = tmp_path / "parent.env"
    poisoned_env.write_text("DATABASE_URL=sqlite:///parent-only.db\n", encoding="utf-8")
    values = {
        "DATABASE_URL": "sqlite:///parent-only.db",
        "database_url": "sqlite:///casefold-parent.db",
        "DATABASE_URL_FILE": str(tmp_path / "must-not-open"),
        "database_url_file": str(tmp_path / "must-not-open-lower"),
        "DATABASE_READ_REPLICA_URL": "sqlite:///replica-parent.db",
        "ENV_FILE_PATH": str(poisoned_env),
        "env_file_path": str(poisoned_env),
        "SECRET_KEY_FILE": str(tmp_path / "runtime-key-must-not-open"),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    # Windows folds environment variable names, so differently cased inputs can
    # address the same key. Compare with the effective environment after setup.
    parent_environment = {name: os.environ[name] for name in values}
    result = isolated_alembic_probe("migration-db-only", "production")
    assert result == {
        "outcome": "metadata-loaded",
        "callbacks": 1,
        "revision_ddl": False,
    }
    assert {name: os.environ[name] for name in values} == parent_environment
