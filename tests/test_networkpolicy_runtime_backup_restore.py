"""Offline contracts for the disposable backup restore Job."""

from __future__ import annotations

import copy
import importlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "k8s"))


@pytest.fixture
def restore():
    return importlib.import_module("networkpolicy_runtime_backup_restore")


@pytest.fixture
def backup_job():
    tmp_path = str(PurePosixPath("/", "tmp"))
    values = yaml.safe_load(
        (ROOT / "charts/university-ecosystem/values.yaml").read_text(encoding="utf-8")
    )["backup"]
    restricted = {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    labels = {
        "app.kubernetes.io/name": "university-ecosystem",
        "app.kubernetes.io/instance": "probe-a",
        "app.kubernetes.io/component": "backup",
    }
    pod = {
        "serviceAccountName": "probe-a-backup",
        "automountServiceAccountToken": False,
        "restartPolicy": "OnFailure",
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "fsGroup": 1000,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "initContainers": [
            {
                "name": "database-dump",
                "image": values["postgresImage"],
                "imagePullPolicy": "IfNotPresent",
                "command": ["/bin/sh", "-ec"],
                "args": ['pg_dump --file=/backup/database.dump "$DATABASE_URL"'],
                "env": [
                    {
                        "name": "DATABASE_URL",
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": "probe-a-connections",
                                "key": "backup-database-url",
                            }
                        },
                    },
                    {"name": "HOME", "value": tmp_path},
                ],
                "securityContext": copy.deepcopy(restricted),
                "resources": {"limits": {"memory": "512Mi"}},
                "volumeMounts": [
                    {"name": "backup-data", "mountPath": "/backup"},
                    {"name": "tmp", "mountPath": tmp_path},
                ],
            }
        ],
        "containers": [
            {
                "name": "upload",
                "image": values["s3ClientImage"],
                "imagePullPolicy": "IfNotPresent",
                "command": ["/bin/sh", "-ec"],
                "args": ["rclone copyto /backup/database.dump backup:fixture/object"],
                "env": [
                    {"name": "BACKUP_BUCKET", "value": "netpol-backup"},
                    {"name": "RCLONE_CONFIG_BACKUP_TYPE", "value": "s3"},
                    {"name": "RCLONE_CONFIG_BACKUP_PROVIDER", "value": "Other"},
                    {
                        "name": "RCLONE_CONFIG_BACKUP_ENDPOINT",
                        "value": "https://backup.example.invalid",
                    },
                    {
                        "name": "RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID",
                        "valueFrom": {
                            "secretKeyRef": {"name": "fixture-s3", "key": "access"}
                        },
                    },
                    {
                        "name": "RCLONE_CONFIG_BACKUP_SECRET_ACCESS_KEY",
                        "valueFrom": {
                            "secretKeyRef": {"name": "fixture-s3", "key": "secret"}
                        },
                    },
                    {"name": "HOME", "value": tmp_path},
                    {"name": "RCLONE_CA_CERT", "value": "/etc/backup-ca/ca.crt"},
                ],
                "securityContext": copy.deepcopy(restricted),
                "resources": {"limits": {"memory": "256Mi"}},
                "volumeMounts": [
                    {"name": "backup-data", "mountPath": "/backup", "readOnly": True},
                    {"name": "tmp", "mountPath": tmp_path},
                    {
                        "name": "proof-ca",
                        "mountPath": "/etc/backup-ca",
                        "readOnly": True,
                    },
                ],
            }
        ],
        "volumes": [
            {"name": "backup-data", "emptyDir": {}},
            {"name": "tmp", "emptyDir": {}},
            {"name": "proof-ca", "configMap": {"name": "backup-public-ca"}},
        ],
    }
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": "probe-a-db-backup-proof", "namespace": "probe-a"},
        "spec": {"template": {"metadata": {"labels": labels}, "spec": pod}},
    }


def test_restore_job_copies_selector_security_and_pinned_clients_without_mutation(
    restore, backup_job
):
    original = copy.deepcopy(backup_job)
    job = restore.build_restore_job(
        backup_job, name="netpol-backup-restore", restore_secret="netpol-backup-restore"
    )
    assert backup_job == original
    assert job["apiVersion"] == "batch/v1"
    assert job["kind"] == "Job"
    assert job["metadata"] == {"name": "netpol-backup-restore", "namespace": "probe-a"}
    assert job["spec"]["backoffLimit"] == 0
    assert 0 < job["spec"]["activeDeadlineSeconds"] <= 600
    template = job["spec"]["template"]
    source = backup_job["spec"]["template"]
    assert template["metadata"] == source["metadata"]
    pod, old = template["spec"], source["spec"]
    assert pod["serviceAccountName"] == old["serviceAccountName"]
    assert pod["securityContext"] == old["securityContext"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["restartPolicy"] == "Never"
    assert len(pod["initContainers"]) == len(pod["containers"]) == 1
    readback, verifier = pod["initContainers"][0], pod["containers"][0]
    upload, dump = old["containers"][0], old["initContainers"][0]
    assert (readback["name"], verifier["name"]) == ("readback", "restore")
    for client, source_client in ((readback, upload), (verifier, dump)):
        assert client["image"] == source_client["image"]
        assert "@sha256:" in client["image"]
        assert client["securityContext"] == source_client["securityContext"]
        assert client["resources"] == source_client["resources"]
    assert readback["env"] == upload["env"]
    assert {v["name"]: v for v in pod["volumes"]}["proof-ca"] == {
        "name": "proof-ca",
        "configMap": {"name": "backup-public-ca"},
    }
    assert {m["name"]: m for m in readback["volumeMounts"]}["proof-ca"] == {
        "name": "proof-ca",
        "mountPath": "/etc/backup-ca",
        "readOnly": True,
    }
    assert {v["name"]: v for v in pod["volumes"]}["backup-data"] == {
        "name": "backup-data",
        "emptyDir": {"sizeLimit": "64Mi"},
    }
    assert {v["name"]: v for v in pod["volumes"]}["tmp"] == {
        "name": "tmp",
        "emptyDir": {"sizeLimit": "8Mi"},
    }
    assert not {m["name"]: m for m in readback["volumeMounts"]}["backup-data"].get(
        "readOnly", False
    )
    assert {m["name"]: m for m in verifier["volumeMounts"]}["backup-data"]["readOnly"]
    env = {item["name"]: item for item in verifier["env"]}
    assert env["DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {
        "name": "netpol-backup-restore",
        "key": "database-url",
    }
    assert "probe-a-connections" not in str(verifier)


def test_fixed_fixture_and_scripts_enforce_single_object_restore_and_marker(
    restore, backup_job
):
    job = restore.build_restore_job(
        backup_job, name="restore-proof", restore_secret="restore-secret"
    )
    pod = job["spec"]["template"]["spec"]
    readback = pod["initContainers"][0]["args"][0]
    verify = pod["containers"][0]["args"][0]
    assert "CREATE TABLE public.aud189_backup_fixture" in restore.FIXTURE_SQL
    assert "fixture_id integer PRIMARY KEY" in restore.FIXTURE_SQL
    assert "fixture_value text NOT NULL" in restore.FIXTURE_SQL
    row_pattern = r"\((\d+), '([^']+)'\)"
    seed_rows = re.findall(row_pattern, restore.FIXTURE_SQL)
    assert seed_rows == [
        ("1", "aud189-public-fixture-one"),
        ("2", "aud189-public-fixture-two"),
        ("3", "aud189-public-fixture-three"),
    ]
    assert re.findall(row_pattern, verify) == seed_rows * 2
    assert "rclone lsf" in readback and "--recursive" in readback
    assert "wc -c" in readback and "-eq 33" in readback
    assert "university-" in readback and ".dump" in readback
    assert readback.index("case ") < readback.index("rclone copyto")
    assert "backup:$BACKUP_BUCKET/$object" in readback
    assert "rclone delete" not in readback
    assert "current_database()" in verify and "backup_restore" in verify
    assert verify.index("current_database()") < verify.index("pg_restore")
    assert "--exit-on-error" in verify and "--no-owner" in verify
    assert "--no-privileges" in verify and "ON_ERROR_STOP=1" in verify
    assert "pg_catalog.pg_attribute" in verify and "pg_catalog.pg_constraint" in verify
    assert "EXCEPT ALL" in verify
    assert verify.index("pg_restore") < verify.index("EXCEPT ALL")
    assert verify.index("EXCEPT ALL") < verify.index(restore.RESTORE_RECEIPT)
    assert restore.RESTORE_RECEIPT == "AUD189_BACKUP_RESTORE_OK"


def _local_shell() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        assert git is not None, "Git Bash is required for offline shell checks"
        shell = Path(git).resolve().parent.parent / "bin" / "bash.exe"
        assert shell.is_file(), "Git Bash is required for offline shell checks"
        return str(shell)
    shell = shutil.which("sh")
    assert shell is not None, "A POSIX shell is required for offline shell checks"
    return shell


def _run_stubbed_shell(tmp_path, script, stubs, **environment):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in stubs.items():
        path = bin_dir / name
        path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "FIXTURE_WORK": tmp_path.as_posix(),
        "TRACE": (tmp_path / "trace").as_posix(),
        "DATABASE_URL": "unused-offline-fixture",
        "BACKUP_BUCKET": "fixture-bucket",
        "FAIL": "",
        **environment,
    }
    return subprocess.run(
        ["/bin/sh", "-es"],
        executable=_local_shell(),
        input=script,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize(
    ("listing", "failure", "exit_code", "copied"),
    [
        ("university-20261116T120000Z.dump\n", "", 0, True),
        ("", "", 12, False),
        (
            "university-20261116T120000Z.dump\nuniversity-20261116T120001Z.dump\n",
            "",
            12,
            False,
        ),
        ("university-20261116T12000xZ.dump\n", "", 12, False),
        ("university-20261116T120000Z.dump", "", 12, False),
        ("university-20261116T120000Z.dumpx", "", 12, False),
        ("university-20261116T120000Z.dump\r\n", "", 12, False),
        ("university-20261116T120000Z.dump\n", "list", 11, False),
        ("university-20261116T120000Z.dump\n", "wc", 12, False),
        ("university-20261116T120000Z.dump\n", "copy", 13, True),
        ("university-20261116T120000Z.dump\n", "empty", 14, True),
        ("university-20261116T120000Z.dump\n", "missing", 14, True),
    ],
)
def test_readback_script_copies_only_one_exact_fixture_object(
    restore, tmp_path, listing, failure, exit_code, copied
):
    object_list = str(PurePosixPath("/", "tmp", "object-list"))
    script = restore._READBACK.replace(
        object_list, '"$FIXTURE_WORK/object-list"'
    ).replace("/backup/database.dump", '"$FIXTURE_WORK/database.dump"')
    stub = r"""case "$1" in
  lsf) if [ "$FAIL" = list ]; then printf 'listing details\n' >&2; exit 1; fi
    printf '%s' "$LISTING" ;;
  copyto) [ "$2" = --max-transfer ] && [ "$3" = 60M ] &&
    [ "$4" = --cutoff-mode ] && [ "$5" = hard ] || exit 1
    for argument in "$@"; do
      case "$argument" in
        --max-size*|--min-size*|--filter*|--exclude*|--include*|--files-from*) exit 1 ;;
      esac
    done
    printf 'copy\n' >> "$TRACE"
    if [ "$FAIL" = copy ]; then printf 'download details\n' >&2; exit 1; fi
    if [ "$FAIL" = empty ]; then : > "$FIXTURE_WORK/database.dump"; exit 0; fi
    if [ "$FAIL" = missing ]; then exit 0; fi
    printf 'synthetic archive' > "$FIXTURE_WORK/database.dump" ;;
  *) exit 1 ;;
esac
"""
    if failure == "wc":
        script = "wc() { printf 'count details\\n' >&2; return 1; }\n" + script
    result = _run_stubbed_shell(
        tmp_path, script, {"rclone": stub}, LISTING=listing, FAIL=failure
    )
    assert result.returncode == exit_code
    assert result.stdout == "" and result.stderr == ""
    archive = tmp_path / "database.dump"
    if exit_code == 0:
        assert archive.read_bytes() == b"synthetic archive"
    elif failure == "empty":
        assert archive.exists() and archive.stat().st_size == 0
    else:
        assert not archive.exists()
    assert (tmp_path / "trace").exists() is copied


@pytest.mark.parametrize("failure", ["", "precheck", "restore", "verify"])
def test_restore_script_prints_marker_only_after_all_steps(restore, tmp_path, failure):
    psql = r"""body=$(cat)
case "$body" in
  *current_database*) step=precheck ;;
  *"EXCEPT ALL"*) step=verify ;;
  *) exit 1 ;;
esac
printf '%s\n' "$step" >> "$TRACE"
[ "$FAIL" != "$step" ]
"""
    pg_restore = r"""printf 'restore\n' >> "$TRACE"
[ "$FAIL" != restore ]
"""
    result = _run_stubbed_shell(
        tmp_path,
        restore._RESTORE,
        {"psql": psql, "pg_restore": pg_restore},
        FAIL=failure,
    )
    trace = (tmp_path / "trace").read_text(encoding="utf-8").splitlines()
    expected = ["precheck", "restore", "verify"]
    assert trace == (expected[: expected.index(failure) + 1] if failure else expected)
    assert (result.returncode == 0) is (not failure)
    assert result.stdout == (restore.RESTORE_RECEIPT + "\n" if not failure else "")
    assert result.stderr == ""


def test_accepts_secret_and_ca_dns_subdomains(restore, backup_job):
    pod = backup_job["spec"]["template"]["spec"]
    pod["initContainers"][0]["env"][0]["valueFrom"]["secretKeyRef"]["name"] = (
        "source.fixture"
    )
    pod["volumes"][2]["configMap"]["name"] = "ca.fixture"
    job = restore.build_restore_job(
        backup_job, name="restore-proof", restore_secret="restore.fixture"
    )
    verifier = job["spec"]["template"]["spec"]["containers"][0]
    assert verifier["env"][0]["valueFrom"]["secretKeyRef"]["name"] == "restore.fixture"


def test_restore_accepts_rendered_backup_job_and_shared_postgres_fixture(restore):
    from networkpolicy_runtime_backup_job import build_backup_job
    from networkpolicy_runtime_backup_postgres import fixture_objects

    from tests.test_helm_staging_contract import _render_staging

    resources = _render_staging(
        "--set",
        "backup.enabled=true",
        "--set-string",
        "backup.minioEndpoint=https://backup.probe.invalid:443",
        release_name="backup-proof",
    )
    cronjob = next(
        item
        for item in resources
        if item.get("kind") == "CronJob"
        and item["metadata"]["labels"].get("app.kubernetes.io/component") == "backup"
    )
    cronjob["metadata"]["namespace"] = "probe-a"
    job = build_backup_job(cronjob, ca_configmap="proof-ca")
    result = restore.build_restore_job(
        job, name="netpol-backup-restore", restore_secret="netpol-backup-restore"
    )
    source_pod = job["spec"]["template"]["spec"]
    restored_pod = result["spec"]["template"]["spec"]
    assert result["spec"]["template"]["metadata"] == job["spec"]["template"]["metadata"]
    assert (
        restored_pod["initContainers"][0]["image"]
        == source_pod["containers"][0]["image"]
    )
    assert (
        restored_pod["containers"][0]["image"]
        == source_pod["initContainers"][0]["image"]
    )
    source_ref = source_pod["initContainers"][0]["env"][0]["valueFrom"]["secretKeyRef"]
    objects = fixture_objects(
        ROOT,
        "probe-a",
        source_pod["initContainers"][0]["image"],
        source_secret_name=source_ref["name"],
        source_secret_key=source_ref["key"],
    )
    init = next(obj for obj in objects if obj["kind"] == "ConfigMap")
    assert init["data"]["init.sh"].count(restore.FIXTURE_SQL) == 1


@pytest.mark.parametrize(
    "name", ["", "Uppercase", "-bad", "bad-", "a" * 64, "bad/name"]
)
def test_rejects_invalid_job_and_secret_names(restore, backup_job, name):
    with pytest.raises(ValueError):
        restore.build_restore_job(
            backup_job, name=name, restore_secret="restore-secret"
        )
    with pytest.raises(ValueError):
        restore.build_restore_job(backup_job, name="restore-proof", restore_secret=name)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong-kind",
        "same-job-name",
        "same-secret",
        "missing-dump",
        "missing-upload",
        "extra-dump",
        "extra-upload",
        "unbound-image",
        "bad-source-secret",
        "bad-source-name",
        "empty-source-key",
        "malformed-env",
        "duplicate-env",
        "plaintext-endpoint",
        "untrusted-ca",
        "disabled-ca-verification",
        "missing-data",
        "missing-tmp",
        "missing-ca-volume",
        "wrong-mount-path",
        "non-ephemeral-volume",
        "writable-ca",
        "unbound-extra-mount",
        "unsafe-token",
    ],
)
def test_rejects_ambiguous_or_unsafe_backup_inputs(restore, backup_job, fault):
    pod = backup_job["spec"]["template"]["spec"]
    name, secret = "restore-proof", "restore-secret"
    if fault == "wrong-kind":
        backup_job["kind"] = "CronJob"
    elif fault == "same-job-name":
        name = backup_job["metadata"]["name"]
    elif fault == "same-secret":
        secret = "probe-a-connections"
    elif fault == "missing-dump":
        pod["initContainers"] = []
    elif fault == "missing-upload":
        pod["containers"] = []
    elif fault == "extra-dump":
        pod["initContainers"].append(copy.deepcopy(pod["initContainers"][0]))
    elif fault == "extra-upload":
        pod["containers"].append(copy.deepcopy(pod["containers"][0]))
    elif fault == "unbound-image":
        pod["containers"][0]["image"] = "rclone/rclone:latest"
    elif fault == "bad-source-secret":
        pod["initContainers"][0]["env"][0] = {"name": "DATABASE_URL", "value": "x"}
    elif fault == "bad-source-name":
        ref = pod["initContainers"][0]["env"][0]["valueFrom"]["secretKeyRef"]
        ref["name"] = "INVALID"
    elif fault == "empty-source-key":
        ref = pod["initContainers"][0]["env"][0]["valueFrom"]["secretKeyRef"]
        ref["key"] = ""
    elif fault == "malformed-env":
        pod["containers"][0]["env"].append("malformed")
    elif fault == "duplicate-env":
        pod["containers"][0]["env"].append(pod["containers"][0]["env"][0])
    elif fault == "plaintext-endpoint":
        pod["containers"][0]["env"][3]["value"] = "http://backup.example.invalid"
    elif fault == "untrusted-ca":
        pod["containers"][0]["env"][-1]["value"] = "/elsewhere/ca.crt"
    elif fault == "disabled-ca-verification":
        pod["containers"][0]["env"].append(
            {"name": "RCLONE_NO_CHECK_CERTIFICATE", "value": "true"}
        )
    elif fault == "missing-data":
        pod["volumes"] = [
            item for item in pod["volumes"] if item["name"] != "backup-data"
        ]
    elif fault == "missing-tmp":
        pod["volumes"] = [item for item in pod["volumes"] if item["name"] != "tmp"]
    elif fault == "missing-ca-volume":
        pod["volumes"] = [item for item in pod["volumes"] if item["name"] != "proof-ca"]
    elif fault == "wrong-mount-path":
        pod["initContainers"][0]["volumeMounts"][0]["mountPath"] = "/unexpected"
    elif fault == "non-ephemeral-volume":
        pod["volumes"][0] = {"name": "backup-data", "persistentVolumeClaim": {}}
    elif fault == "writable-ca":
        pod["containers"][0]["volumeMounts"][-1]["readOnly"] = False
    elif fault == "unbound-extra-mount":
        pod["containers"][0]["volumeMounts"].append(
            {"name": "unbound", "mountPath": "/unbound"}
        )
    elif fault == "unsafe-token":
        pod["automountServiceAccountToken"] = True
    with pytest.raises(ValueError):
        restore.build_restore_job(backup_job, name=name, restore_secret=secret)
