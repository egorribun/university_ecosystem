"""Build a positive, disposable restore Job from the rendered backup Job.

The backup Job must have transferred one archive to its dedicated bucket before
the restore Job starts. Use a freshly created, isolated ``backup_restore``
database. This module only builds the restore manifest.
"""

from __future__ import annotations

import copy
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

RESTORE_RECEIPT = "AUD189_BACKUP_RESTORE_OK"
FIXTURE_SQL = """CREATE TABLE public.aud189_backup_fixture (
    fixture_id integer PRIMARY KEY,
    fixture_value text NOT NULL
);
INSERT INTO public.aud189_backup_fixture (fixture_id, fixture_value) VALUES
    (1, 'aud189-public-fixture-one'),
    (2, 'aud189-public-fixture-two'),
    (3, 'aud189-public-fixture-three');
"""

# Readback exit codes: 11 listing, 12 inventory, 13 download, 14 empty archive.
_READBACK = r"""set -eu
set +x
umask 077
export LC_ALL=C
rclone lsf --recursive --files-only --contimeout 10s --timeout 30s --retries 1 --low-level-retries 1 "backup:$BACKUP_BUCKET" > /tmp/object-list 2>/dev/null || exit 11
object_bytes=$(wc -c 2>/dev/null < /tmp/object-list) || exit 12
[ "$object_bytes" -eq 33 ] 2>/dev/null || exit 12
IFS= read -r object 2>/dev/null < /tmp/object-list || exit 12
case "$object" in
  university-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.dump) ;;
  *) exit 12 ;;
esac
rclone copyto --max-transfer 60M --cutoff-mode hard --contimeout 10s --timeout 30s --retries 1 --low-level-retries 1 "backup:$BACKUP_BUCKET/$object" /backup/database.dump >/dev/null 2>&1 || exit 13
[ -s /backup/database.dump ] || exit 14
"""

_RESTORE = """set -eu
set +x
umask 077
psql --no-psqlrc --set=ON_ERROR_STOP=1 --dbname="$DATABASE_URL" >/dev/null 2>&1 <<'SQL'
DO $aud189$
BEGIN
    IF current_database() <> 'backup_restore' THEN
        RAISE EXCEPTION 'unexpected fixture database';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
    ) THEN
        RAISE EXCEPTION 'fixture database is not empty';
    END IF;
END;
$aud189$;
SQL
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$DATABASE_URL" /backup/database.dump >/dev/null 2>&1
psql --no-psqlrc --set=ON_ERROR_STOP=1 --dbname="$DATABASE_URL" >/dev/null 2>&1 <<'SQL'
DO $aud189$
BEGIN
    IF (
        SELECT array_agg(a.attname::text || ':' ||
            pg_catalog.format_type(a.atttypid, a.atttypmod) || ':' ||
            a.attnotnull::text ORDER BY a.attnum)
        FROM pg_catalog.pg_attribute AS a
        WHERE a.attrelid = to_regclass('public.aud189_backup_fixture')
          AND a.attnum > 0 AND NOT a.attisdropped
    ) IS DISTINCT FROM ARRAY['fixture_id:integer:true', 'fixture_value:text:true'] THEN
        RAISE EXCEPTION 'fixture columns differ';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint AS c
        WHERE c.conrelid = to_regclass('public.aud189_backup_fixture')
          AND c.contype = 'p' AND c.conkey = ARRAY[1]::smallint[]
    ) THEN
        RAISE EXCEPTION 'fixture primary key differs';
    END IF;
    IF EXISTS (
        SELECT fixture_id, fixture_value FROM public.aud189_backup_fixture
        EXCEPT ALL VALUES
            (1, 'aud189-public-fixture-one'),
            (2, 'aud189-public-fixture-two'),
            (3, 'aud189-public-fixture-three')
    ) OR EXISTS (
        VALUES
            (1, 'aud189-public-fixture-one'),
            (2, 'aud189-public-fixture-two'),
            (3, 'aud189-public-fixture-three')
        EXCEPT ALL SELECT fixture_id, fixture_value FROM public.aud189_backup_fixture
    ) THEN
        RAISE EXCEPTION 'fixture rows differ';
    END IF;
END;
$aud189$;
SQL
printf '%s\\n' 'AUD189_BACKUP_RESTORE_OK'
"""


def _name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 63
        and re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", value) is not None
    )


def _resource_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 253
        and all(_name(part) for part in value.split("."))
    )


def _only(items: Any, expected: str) -> dict[str, Any]:
    if (
        not isinstance(items, list)
        or len(items) != 1
        or not isinstance(items[0], dict)
        or items[0].get("name") != expected
    ):
        raise ValueError("invalid backup workload")
    return items[0]


def _named(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError("invalid backup workload")
    result = {item["name"]: item for item in items}
    if len(result) != len(items):
        raise ValueError("invalid backup workload")
    return result


def build_restore_job(
    backup_job: dict[str, Any], *, name: str, restore_secret: str
) -> dict[str, Any]:
    """Derive a bounded readback/restore Job without mutating its input.

    ``backup_job`` must be the chart-derived Job with the proof CA attached.  The
    source bucket is dedicated to this fixture and starts empty.  The separate
    restore Secret supplies a URL for a precreated isolated ``backup_restore``
    database owned by its generated, restricted fixture role.
    """
    if not _name(name) or not _resource_name(restore_secret):
        raise ValueError("invalid restore identity")
    try:
        if backup_job["apiVersion"] != "batch/v1" or backup_job["kind"] != "Job":
            raise ValueError("expected backup Job")
        metadata = backup_job["metadata"]
        if name == metadata["name"] or not _name(metadata["namespace"]):
            raise ValueError("invalid restore identity")
        template = copy.deepcopy(backup_job["spec"]["template"])
        pod = template["spec"]
        if pod.get("automountServiceAccountToken") is not False:
            raise ValueError("unsafe backup workload")
        dump = _only(pod["initContainers"], "database-dump")
        upload = _only(pod["containers"], "upload")
        for container in (dump, upload):
            if not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", container["image"]):
                raise ValueError("backup image is not digest pinned")
        dump_env = _named(dump["env"])
        source_ref = dump_env["DATABASE_URL"]["valueFrom"]["secretKeyRef"]
        if not _resource_name(source_ref["name"]) or not source_ref["key"]:
            raise ValueError("invalid source database reference")
        if source_ref["name"] == restore_secret:
            raise ValueError("restore Secret must be separate")
        upload_env = _named(upload["env"])
        endpoint = urlsplit(upload_env["RCLONE_CONFIG_BACKUP_ENDPOINT"]["value"])
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
            or upload_env["RCLONE_CA_CERT"]["value"] != "/etc/backup-ca/ca.crt"
            or "RCLONE_NO_CHECK_CERTIFICATE" in upload_env
        ):
            raise ValueError("invalid backup TLS configuration")
        volumes = _named(pod["volumes"])
        dump_mounts = _named(dump["volumeMounts"])
        upload_mounts = _named(upload["volumeMounts"])
        for container_mounts in (dump_mounts, upload_mounts):
            for volume_name, mount_path in (
                ("backup-data", "/backup"),
                ("tmp", str(PurePosixPath("/", "tmp"))),
            ):
                if container_mounts[volume_name]["mountPath"] != mount_path:
                    raise ValueError("invalid backup mount")
                if "emptyDir" not in volumes[volume_name]:
                    raise ValueError("backup scratch space is not ephemeral")
        ca_mount = upload_mounts["proof-ca"]
        if (
            ca_mount["mountPath"] != "/etc/backup-ca"
            or ca_mount.get("readOnly") is not True
            or not _resource_name(volumes["proof-ca"]["configMap"]["name"])
        ):
            raise ValueError("invalid backup CA mount")
        for mount_name in set(dump_mounts) | set(upload_mounts):
            if mount_name not in volumes:
                raise ValueError("missing backup volume")
        readback = copy.deepcopy(upload)
        readback.update(name="readback", command=["/bin/sh", "-ec"], args=[_READBACK])
        for mount in readback["volumeMounts"]:
            if mount["name"] == "backup-data":
                mount.pop("readOnly", None)
        verifier = copy.deepcopy(dump)
        verifier.update(name="restore", command=["/bin/sh", "-ec"], args=[_RESTORE])
        for env in verifier["env"]:
            if env["name"] == "DATABASE_URL":
                env["valueFrom"]["secretKeyRef"] = {
                    "name": restore_secret,
                    "key": "database-url",
                }
        for mount in verifier["volumeMounts"]:
            if mount["name"] == "backup-data":
                mount["readOnly"] = True
        pod["initContainers"] = [readback]
        pod["containers"] = [verifier]
        pod["volumes"] = [
            {"name": "backup-data", "emptyDir": {"sizeLimit": "64Mi"}},
            {"name": "tmp", "emptyDir": {"sizeLimit": "8Mi"}},
            *[
                copy.deepcopy(volumes[volume_name])
                for volume_name in sorted(
                    (set(dump_mounts) | set(upload_mounts)) - {"backup-data", "tmp"}
                )
            ],
        ]
        pod["restartPolicy"] = "Never"
        pod["hostNetwork"] = False
        pod["enableServiceLinks"] = False
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": name, "namespace": metadata["namespace"]},
            "spec": {
                "backoffLimit": 0,
                "activeDeadlineSeconds": 300,
                "ttlSecondsAfterFinished": 600,
                "template": template,
            },
        }
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("invalid backup workload") from exc
