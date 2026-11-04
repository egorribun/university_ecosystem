"""Execute the bootstrap wrapper against a fake psql, never a database."""

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("diagnostic", "psql_exit", "wrapper_exit", "state"),
    [
        ("psql:/bootstrap/bootstrap-app-roles.sql:73: ERROR:  42601", 3, 3, "42601"),
        ("psql:/bootstrap/bootstrap-app-roles.sql:91: ERROR:  42501", 3, 3, "42501"),
        (
            "psql:/bootstrap/bootstrap-app-roles.sql:73: ERROR:  42601 extra",
            3,
            3,
            "UNKNOWN",
        ),
        ("psql:/untrusted.sql:73: ERROR:  42601", 3, 3, "UNKNOWN"),
        ("psql:/bootstrap/bootstrap-app-roles.sql:x: ERROR:  42601", 3, 3, "UNKNOWN"),
        ("psql:/bootstrap/bootstrap-app-roles.sql:73: ERROR:  abcde", 3, 3, "UNKNOWN"),
        ("connection failed", 2, 2, "UNKNOWN"),
        ("", 0, 0, "UNKNOWN"),
        ("UE_BOOTSTRAP_EXIT=0", 3, 1, "UNKNOWN"),
        ("UE_BOOTSTRAP_EXIT=invalid", 3, 3, "UNKNOWN"),
        ("UE_BOOTSTRAP_EXIT=999", 3, 3, "UNKNOWN"),
    ],
)
def test_bootstrap_wrapper_projects_only_sqlstate(
    tmp_path: Path, diagnostic: str, psql_exit: int, wrapper_exit: int, state: str
) -> None:
    shell = shutil.which("sh")
    assert shell is not None, "POSIX shell is required for the wrapper contract"
    stub = tmp_path / "psql"
    stub.write_text(
        "#!/bin/sh\n"
        "[ \"$PGOPTIONS\" != '' ] || exit 91\n"
        "for argument do\n"
        '  case "$argument" in *"$PGPASSWORD"*) exit 92;; esac\n'
        "done\n"
        "printf '%s\\n' \"$PGPASSWORD\"\n"
        'printf \'%s\\n\' "$PGPASSWORD" "$FAKE_DIAGNOSTIC" >&2\n'
        'exit "$FAKE_EXIT"\n'
    )
    stub.chmod(0o700)
    sentinel = uuid.uuid4().hex
    environment = {
        "PATH": str(tmp_path),
        "POSTGRES_DB": "university",
        "PGPASSWORD": sentinel,
        "UE_MIGRATOR_DB_PASSWORD": sentinel,
        "UE_APP_DB_PASSWORD": sentinel,
        "UE_WORKER_DB_PASSWORD": sentinel,
        "UE_SPICEDB_DB_PASSWORD": sentinel,
        "UE_TEMPORAL_DB_PASSWORD": sentinel,
        "FAKE_DIAGNOSTIC": diagnostic,
        "FAKE_EXIT": str(psql_exit),
    }
    if "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    # Fixed wrapper plus isolated fake psql; timeout bounds a broken shell fixture.
    result = subprocess.run(  # noqa: S603 - fixed shell and repository wrapper arguments
        [shell, str(ROOT / "infrastructure/postgres-roles/run-bootstrap.sh")],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == wrapper_exit
    assert sentinel not in result.stdout + result.stderr
    if wrapper_exit:
        assert result.stdout == ""
        assert result.stderr == (
            f"[postgres-roles-init] phase=reconcile exit={wrapper_exit} sqlstate={state}\n"
        )
    else:
        assert result.stdout == "[postgres-roles-init] Reconciled database roles.\n"
        assert result.stderr == ""
