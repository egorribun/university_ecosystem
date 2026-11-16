"""Offline contracts for the disposable AUD-189 PostgreSQL prerequisite."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/k8s"))


def test_postgres_fixture_helper_is_available() -> None:
    assert importlib.util.find_spec("networkpolicy_runtime_backup_postgres") is not None


@pytest.fixture
def fixture_module():
    return importlib.import_module("networkpolicy_runtime_backup_postgres")


@pytest.fixture
def image() -> str:
    values = yaml.safe_load(
        (ROOT / "charts/university-ecosystem/values.yaml").read_text(encoding="utf-8")
    )
    return values["backup"]["postgresImage"]


def _objects(module, image: str, **overrides):
    arguments = {
        "source_secret_name": "university-connections",
        "source_secret_key": "backup-database-url",
    }
    arguments.update(overrides)
    return module.fixture_objects(ROOT, "probe-a", image, **arguments)


def _one(objects, kind: str, name: str):
    matches = [
        obj
        for obj in objects
        if obj["kind"] == kind and obj["metadata"]["name"] == name
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_private(condition: bool) -> None:
    # Do not let assertion introspection print generated fixture credentials.
    if not condition:
        raise AssertionError("private fixture credential contract failed")


def test_fixture_target_and_ephemeral_server_match_chart(fixture_module, image):
    objects = _objects(fixture_module, image)
    assert len(objects) == 6
    assert all(obj["metadata"]["namespace"] == "probe-a" for obj in objects)
    pod = _one(objects, "Pod", "netpol-backup-postgres")
    service = _one(objects, "Service", "netpol-backup-postgres")
    labels = pod["metadata"]["labels"]
    assert labels["app.kubernetes.io/name"] == "postgresql"
    assert all(labels.get(k) == v for k, v in service["spec"]["selector"].items())
    assert service["spec"]["ports"] == [{"port": 5432, "targetPort": 5432}]
    spec = pod["spec"]
    assert spec["automountServiceAccountToken"] is False
    assert spec.get("hostNetwork", False) is False
    assert len(spec["containers"]) == 1
    container = spec["containers"][0]
    assert container["image"] == image
    assert any(volume.get("emptyDir") == {} for volume in spec["volumes"])
    assert any(
        volume.get("configMap", {}).get("name") == "netpol-backup-postgres-init"
        for volume in spec["volumes"]
    )
    assert any(
        mount["mountPath"] == "/docker-entrypoint-initdb.d"
        and mount["readOnly"] is True
        for mount in container["volumeMounts"]
    )


def test_distinct_generated_roles_are_scoped_to_separate_secrets(fixture_module, image):
    objects = _objects(fixture_module, image)
    credentials = _one(objects, "Secret", "netpol-backup-postgres-credentials")
    source = _one(objects, "Secret", "university-connections")
    restore = _one(objects, "Secret", "netpol-backup-restore")
    assert set(source["stringData"]) == {"backup-database-url"}
    assert set(restore["stringData"]) == {"database-url"}
    server = credentials["stringData"]
    assert set(server) == {"bootstrap-password", "reader-password", "restore-password"}
    _assert_private(
        len(set(server.values())) == 3
        and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in server.values())
    )
    for secret, key, role, database, password_key in (
        (
            source,
            "backup-database-url",
            "backup_reader",
            "backup_source",
            "reader-password",
        ),
        (
            restore,
            "database-url",
            "backup_restorer",
            "backup_restore",
            "restore-password",
        ),
    ):
        url = urlsplit(secret["stringData"][key])
        _assert_private(
            url.scheme == "postgresql"
            and url.username == role
            and url.password == server[password_key]
            and url.hostname == "netpol-backup-postgres"
            and url.port == 5432
            and url.path == f"/{database}"
            and not url.query
            and not url.fragment
        )
    again = _one(
        _objects(fixture_module, image), "Secret", "netpol-backup-postgres-credentials"
    )
    _assert_private(all(server[key] != again["stringData"][key] for key in server))
    nonsecret_manifests = json.dumps(
        [obj for obj in objects if obj["kind"] != "Secret"]
    )
    _assert_private(
        all(password not in nonsecret_manifests for password in server.values())
    )


def test_fixture_accepts_valid_rendered_secret_reference(fixture_module, image):
    objects = _objects(
        fixture_module,
        image,
        source_secret_name="database.connections",
        source_secret_key="_backup.database-url",
    )
    assert set(_one(objects, "Secret", "database.connections")["stringData"]) == {
        "_backup.database-url"
    }


def test_seed_uses_shared_fixture_and_narrow_database_roles(fixture_module, image):
    from networkpolicy_runtime_backup_restore import FIXTURE_SQL

    objects = _objects(fixture_module, image)
    init = _one(objects, "ConfigMap", "netpol-backup-postgres-init")["data"]["init.sh"]
    assert init.count(FIXTURE_SQL) == 1
    assert "CREATE DATABASE backup_source" in init
    assert "CREATE DATABASE backup_restore OWNER backup_restorer" in init
    assert "GRANT CONNECT ON DATABASE backup_source TO backup_reader" in init
    assert "GRANT SELECT ON TABLE public.aud189_backup_fixture TO backup_reader" in init
    assert (
        init.count("NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS") == 2
    )
    assert "GRANT ALL" not in init
    assert "pg_read_all_data" not in init
    assert "BYPASSRLS;" not in init.replace("NOBYPASSRLS;", "")
    assert "set +x" in init
    assert all(
        ">/dev/null 2>&1" in line
        for line in init.splitlines()
        if line.startswith("psql ")
    )


@pytest.mark.parametrize("fail_psql", [False, True])
def test_init_script_is_fail_closed_and_does_not_echo_credentials(
    fixture_module, image, tmp_path, monkeypatch, fail_psql
):
    from networkpolicy_runtime_kube import run_command

    shell = shutil.which("sh")
    if not shell:
        git = shutil.which("git")
        assert git is not None
        shell = str(Path(git).resolve().parents[1] / "bin" / "sh.exe")
    fake_psql = tmp_path / "psql"
    fake_psql.write_text(
        "#!/bin/sh\n"
        'printf \'CALL %s\\n\' "$*" >> "$TRACE_FILE"\n'
        'while IFS= read -r line; do printf \'%s\\n\' "$line" >> "$TRACE_FILE"; done\n'
        'if [ "$FAIL_PSQL" = 1 ]; then\n'
        '  printf \'%s\\n\' "$POSTGRES_PASSWORD" "$BACKUP_READER_PASSWORD"\n'
        "  printf '%s\\n' \"$BACKUP_RESTORE_PASSWORD\" >&2\n"
        "  exit 9\n"
        "fi\n",
        encoding="utf-8",
        newline="\n",
    )
    fake_psql.chmod(0o755)
    init = _one(
        _objects(fixture_module, image), "ConfigMap", "netpol-backup-postgres-init"
    )
    script = tmp_path / "init.sh"
    script.write_text(init["data"]["init.sh"], encoding="utf-8", newline="\n")
    trace = tmp_path / "trace"
    passwords = ("a" * 64, "b" * 64, "c" * 64)
    env = {
        "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", ""),
        "MSYS_NO_PATHCONV": "1",
        "TRACE_FILE": trace.as_posix(),
        "FAIL_PSQL": "1" if fail_psql else "0",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": passwords[0],
        "BACKUP_READER_PASSWORD": passwords[1],
        "BACKUP_RESTORE_PASSWORD": passwords[2],
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if fail_psql:
        with pytest.raises(subprocess.CalledProcessError) as failure:
            run_command([shell, str(script)], timeout=10)
        result = failure.value
    else:
        result = run_command([shell, str(script)], timeout=10)
    transcript = trace.read_text(encoding="utf-8")
    assert (result.returncode != 0) is fail_psql
    assert transcript.count("CALL ") == (1 if fail_psql else 3)
    _assert_private(
        not result.stdout
        and not result.stderr
        and all(password not in transcript for password in passwords)
    )


def test_server_receives_only_secret_references_and_requires_authenticated_readiness(
    fixture_module, image
):
    pod = _one(_objects(fixture_module, image), "Pod", "netpol-backup-postgres")
    container = pod["spec"]["containers"][0]
    env = {item["name"]: item for item in container["env"]}
    for name, key in (
        ("POSTGRES_PASSWORD", "bootstrap-password"),
        ("BACKUP_READER_PASSWORD", "reader-password"),
        ("BACKUP_RESTORE_PASSWORD", "restore-password"),
    ):
        assert env[name]["valueFrom"]["secretKeyRef"] == {
            "name": "netpol-backup-postgres-credentials",
            "key": key,
        }
        assert "value" not in env[name]
    assert (
        env["POSTGRES_INITDB_ARGS"]["value"]
        == "--auth-host=scram-sha-256 --auth-local=scram-sha-256"
    )
    readiness = " ".join(container["readinessProbe"]["exec"]["command"])
    assert "127.0.0.1" in readiness
    assert "backup_reader" in readiness and "backup_source" in readiness
    assert "aud189_backup_fixture" in readiness
    assert ">/dev/null 2>&1" in readiness


@pytest.mark.parametrize("namespace", ["", "probe-b", "PROBE-A", "../probe-a"])
def test_fixture_rejects_other_namespaces(fixture_module, image, namespace):
    with pytest.raises(ValueError):
        fixture_module.fixture_objects(
            ROOT,
            namespace,
            image,
            source_secret_name="university-connections",
            source_secret_key="backup-database-url",
        )


@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        "UPPER",
        "../invalid",
        "a..b",
        "a" * 64,
        "netpol-backup-restore",
        "netpol-backup-postgres-credentials",
    ],
)
def test_fixture_rejects_unsafe_or_conflicting_source_secret_names(
    fixture_module, image, name
):
    with pytest.raises(ValueError):
        _objects(fixture_module, image, source_secret_name=name)


@pytest.mark.parametrize(
    "key", [None, "", "../invalid", ".", "..", "..hidden", "é", "a" * 254]
)
def test_fixture_rejects_unsafe_secret_keys(fixture_module, image, key):
    with pytest.raises(ValueError):
        _objects(fixture_module, image, source_secret_key=key)


def test_fixture_rejects_an_untracked_or_unpinned_image(fixture_module, image):
    for other in (
        None,
        "pgvector/pgvector:pg17",
        image.replace("pgvector/pgvector", "other/image"),
    ):
        with pytest.raises(ValueError):
            _objects(fixture_module, other)
