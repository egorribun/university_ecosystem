"""Build the private, disposable PostgreSQL prerequisite for AUD-189.

The caller owns the disposable namespace, resource lifecycle and readiness wait.
This module only constructs manifests; the returned Secrets contain credentials
and must never be printed or included in receipts.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

import yaml
from networkpolicy_runtime_backup_restore import FIXTURE_SQL

POSTGRES_NAME = "netpol-backup-postgres"
CREDENTIALS_NAME = "netpol-backup-postgres-credentials"
RESTORE_NAME = "netpol-backup-restore"
INIT_CONFIG = "netpol-backup-postgres-init"

_INIT_PREFIX = r"""#!/bin/sh
set -eu
set +x
# Do not log password-bearing role statements, even on database errors.
export PGOPTIONS='-c log_statement=none -c log_min_error_statement=panic'
psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres >/dev/null 2>&1 <<'SQL'
\getenv reader_password BACKUP_READER_PASSWORD
\getenv restore_password BACKUP_RESTORE_PASSWORD
CREATE ROLE backup_reader LOGIN PASSWORD :'reader_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE backup_restorer LOGIN PASSWORD :'restore_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE backup_source;
CREATE DATABASE backup_restore OWNER backup_restorer;
REVOKE ALL ON DATABASE backup_source FROM PUBLIC;
REVOKE ALL ON DATABASE backup_restore FROM PUBLIC;
GRANT CONNECT ON DATABASE backup_source TO backup_reader;
SQL
psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname backup_source >/dev/null 2>&1 <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
"""
_INIT_SUFFIX = r"""
GRANT USAGE ON SCHEMA public TO backup_reader;
GRANT SELECT ON TABLE public.aud189_backup_fixture TO backup_reader;
SQL
psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname backup_restore >/dev/null 2>&1 <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO backup_restorer;
SQL
"""


def _secret_env(name: str, key: str) -> dict[str, Any]:
    return {
        "name": name,
        "valueFrom": {"secretKeyRef": {"name": CREDENTIALS_NAME, "key": key}},
    }


def _valid_secret_name(name: str) -> bool:
    return (
        isinstance(name, str)
        and 0 < len(name) <= 253
        and all(
            len(part) <= 63
            and re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", part) is not None
            for part in name.split(".")
        )
    )


def _object(kind: str, name: str, **fields: Any) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name, "namespace": "probe-a"},
        **fields,
    }


def fixture_objects(
    root: Path,
    namespace: str,
    postgres_image: str,
    *,
    source_secret_name: str,
    source_secret_key: str,
) -> list[dict[str, Any]]:
    """Return private manifests bound to the chart pin and rendered Secret ref."""
    if namespace != "probe-a":
        raise ValueError("backup fixture requires the disposable probe-a namespace")
    if not _valid_secret_name(source_secret_name) or source_secret_name in {
        CREDENTIALS_NAME,
        RESTORE_NAME,
    }:
        raise ValueError("invalid or conflicting source Secret name")
    if (
        not isinstance(source_secret_key, str)
        or len(source_secret_key) > 253
        or not re.fullmatch(r"(?!\.$)(?!\.\.)[-._a-zA-Z0-9]+", source_secret_key)
    ):
        raise ValueError("invalid source Secret key")
    values = yaml.safe_load(
        (root / "charts/university-ecosystem/values.yaml").read_text(encoding="utf-8")
    )
    if (
        not isinstance(postgres_image, str)
        or not re.search(r"@sha256:[0-9a-f]{64}$", postgres_image)
        or values["backup"]["postgresImage"] != postgres_image
    ):
        raise ValueError("PostgreSQL image must match the tracked chart pin")

    bootstrap_password, reader_password, restore_password = (
        secrets.token_hex(32) for _ in range(3)
    )
    source_url = f"postgresql://backup_reader:{reader_password}@{POSTGRES_NAME}:5432/backup_source"
    restore_url = f"postgresql://backup_restorer:{restore_password}@{POSTGRES_NAME}:5432/backup_restore"
    labels = {
        "app.kubernetes.io/name": "postgresql",
        "netpol-fixture": "backup-postgres",
    }
    pod = _object(
        "Pod",
        POSTGRES_NAME,
        spec={
            "automountServiceAccountToken": False,
            "hostNetwork": False,
            "containers": [
                {
                    "name": "postgres",
                    "image": postgres_image,
                    "env": [
                        {"name": "POSTGRES_USER", "value": "postgres"},
                        {"name": "POSTGRES_DB", "value": "postgres"},
                        {
                            "name": "POSTGRES_INITDB_ARGS",
                            "value": "--auth-host=scram-sha-256 --auth-local=scram-sha-256",
                        },
                        _secret_env("POSTGRES_PASSWORD", "bootstrap-password"),
                        _secret_env("BACKUP_READER_PASSWORD", "reader-password"),
                        _secret_env("BACKUP_RESTORE_PASSWORD", "restore-password"),
                    ],
                    "volumeMounts": [
                        {"name": "data", "mountPath": "/var/lib/postgresql/data"},
                        {
                            "name": "init",
                            "mountPath": "/docker-entrypoint-initdb.d",
                            "readOnly": True,
                        },
                    ],
                    "readinessProbe": {
                        "exec": {
                            "command": [
                                "sh",
                                "-ec",
                                'PGPASSWORD="$BACKUP_READER_PASSWORD" '
                                "psql -X -w -h 127.0.0.1 -U backup_reader -d backup_source "
                                "-v ON_ERROR_STOP=1 -tAc "
                                "'SELECT count(*) FROM public.aud189_backup_fixture' "
                                "2>/dev/null | grep -qx 3 >/dev/null 2>&1",
                            ]
                        },
                        "periodSeconds": 3,
                        "timeoutSeconds": 2,
                    },
                }
            ],
            "volumes": [
                {"name": "data", "emptyDir": {}},
                {"name": "init", "configMap": {"name": INIT_CONFIG}},
            ],
        },
    )
    pod["metadata"]["labels"] = labels
    return [
        _object(
            "Secret",
            CREDENTIALS_NAME,
            stringData={
                "bootstrap-password": bootstrap_password,
                "reader-password": reader_password,
                "restore-password": restore_password,
            },
        ),
        _object(
            "Secret", source_secret_name, stringData={source_secret_key: source_url}
        ),
        _object("Secret", RESTORE_NAME, stringData={"database-url": restore_url}),
        _object(
            "ConfigMap",
            INIT_CONFIG,
            data={"init.sh": _INIT_PREFIX + FIXTURE_SQL + _INIT_SUFFIX},
        ),
        pod,
        _object(
            "Service",
            POSTGRES_NAME,
            spec={
                "selector": {"netpol-fixture": "backup-postgres"},
                "ports": [{"port": 5432, "targetPort": 5432}],
            },
        ),
    ]
