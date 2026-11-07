"""Run the AUD-363/454 proof against a CI-owned PostgreSQL service."""

import asyncio
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import asyncpg
import yaml
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

_MODULE = "tests.integration.test_aud363_454_borrowed_session_postgres"
_COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.test.yml"
_CASES = (
    "test_read_committed_revalidation_respects_rls_and_preserves_dirty_uow",
    "test_borrowed_read_committed_broadcast_observes_committed_removal",
    "test_repeatable_read_cannot_authorize_or_publish",
    "test_typing_and_presence_progress_under_saturated_pool",
    "test_removal_committed_while_broadcast_prepares_is_not_delivered",
    "test_removal_during_inflight_send_bounds_exposure_to_that_broadcast",
)


class ProofError(RuntimeError):
    """The owned proof could not be established."""


def _pinned_postgres_image() -> str:
    """Read the existing immutable PostgreSQL image pin from test Compose."""
    try:
        compose = yaml.safe_load(_COMPOSE_FILE.read_text(encoding="utf-8"))
        image = compose["services"]["postgres"]["image"]
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, TypeError):
        raise ProofError("AUD-363/454 PostgreSQL image pin unavailable") from None
    if (
        not isinstance(image, str)
        or re.fullmatch(r"pgvector/pgvector:pg17@sha256:[0-9a-f]{64}", image) is None
    ):
        raise ProofError("AUD-363/454 PostgreSQL image pin is invalid")
    return image


def inspect_service(container_id: str) -> str:
    """Check the exact runner-provided service before touching PostgreSQL."""
    docker = shutil.which("docker")
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None or not docker:
        raise ProofError("AUD-363/454 owned service identity unavailable")
    expected_image = _pinned_postgres_image()
    try:
        result = subprocess.run(  # noqa: S603  # Resolved Docker and validated ID.
            [docker, "inspect", container_id],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        if result.returncode:
            raise ProofError("AUD-363/454 owned service inspection failed")
        records = json.loads(result.stdout)
        if not isinstance(records, list) or len(records) != 1:
            raise ProofError("AUD-363/454 owned service identity unavailable")
        record = records[0]
        config = record["Config"]
        host = record["HostConfig"]
        environment = config["Env"]
        if not isinstance(environment, list) or not all(
            isinstance(item, str) for item in environment
        ):
            raise ProofError("AUD-363/454 owned service environment unavailable")
        passwords = [
            item.removeprefix("POSTGRES_PASSWORD=")
            for item in environment
            if item.startswith("POSTGRES_PASSWORD=")
        ]
        expected_env = {
            "POSTGRES_USER": "aud363_admin",
            "POSTGRES_DB": "postgres",
        }
        valid = (
            record["Id"] == container_id
            and record["State"]["Running"] is True
            and config["Image"] == expected_image
            and all(
                [item for item in environment if item.startswith(key + "=")]
                == [key + "=" + value]
                for key, value in expected_env.items()
            )
            and len(passwords) == 1
            and bool(passwords[0])
            and host["PortBindings"]["5432/tcp"]
            == [{"HostIp": "127.0.0.1", "HostPort": "15432"}]
            and host["Memory"] == 805306368
            and host["MemorySwap"] == 805306368
            and host["Binds"] in (None, [])
            and bool(host["Tmpfs"]["/var/lib/postgresql/data"])
            and record["Mounts"] == []
        )
    except (
        OSError,
        subprocess.SubprocessError,
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
    ):
        raise ProofError("AUD-363/454 owned service inspection failed") from None
    if not valid:
        raise ProofError("AUD-363/454 owned service identity mismatch")
    return passwords[0]


async def bootstrap(admin_password: str, role_password: str) -> None:
    """Create the role and database without adopting or dropping existing objects."""
    if re.fullmatch(r"[0-9a-f]{64}", role_password) is None:
        raise ProofError("AUD-363/454 role credential is invalid")
    try:
        connection = await asyncpg.connect(
            host="127.0.0.1",
            port=15432,
            user="aud363_admin",
            password=admin_password,
            database="postgres",
            timeout=5,
        )
        try:
            admin = await connection.fetchrow(
                "SELECT current_database(), current_user, rolsuper "
                "FROM pg_roles WHERE rolname = current_user"
            )
            if admin is None or tuple(admin) != ("postgres", "aud363_admin", True):
                raise ProofError("AUD-363/454 bootstrap identity mismatch")
            await connection.execute(
                "CREATE ROLE audit_ws_reader LOGIN NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS "
                f"PASSWORD '{role_password}'"
            )
            await connection.execute(
                "CREATE DATABASE audit_ws_borrowed OWNER audit_ws_reader TEMPLATE template0"
            )
            await connection.execute(
                "REVOKE ALL ON DATABASE audit_ws_borrowed FROM PUBLIC"
            )
            role = await connection.fetchrow(
                "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
                "rolinherit, rolreplication, rolbypassrls FROM pg_roles "
                "WHERE rolname = 'audit_ws_reader'"
            )
            memberships = await connection.fetchval(
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r "
                "ON r.oid = m.member WHERE r.rolname = 'audit_ws_reader'"
            )
            if (
                role is None
                or tuple(role)
                != (
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                )
                or memberships != 0
            ):
                raise ProofError("AUD-363/454 restricted role verification failed")
        finally:
            await connection.close()
    except (asyncpg.PostgresError, OSError, TimeoutError):
        raise ProofError("AUD-363/454 database bootstrap failed") from None


def run_proof(role_password: str, temp_root: Path) -> None:
    """Run only the six proof cases with the generic database harness isolated."""
    if re.fullmatch(r"[0-9a-f]{64}", role_password) is None:
        raise ProofError("AUD-363/454 role credential is invalid")
    child_env = os.environ.copy()
    for key in (
        "DATABASE_URL",
        "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET",
        "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_URL",
        "UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL",
        "USE_TESTCONTAINERS_POSTGRES",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_TESTRUNUID",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "PYTHONOPTIMIZE",
        "AUD363_ADMIN_PASSWORD",
        "AUD363_POSTGRES_CONTAINER_ID",
    ):
        child_env.pop(key, None)
    child_env["AUD363_WS_DISPOSABLE"] = "1"
    child_env["AUD363_WS_DISPOSABLE_PG_URL"] = (
        "postgresql+asyncpg://audit_ws_reader:"
        f"{role_password}@127.0.0.1:15432/audit_ws_borrowed"
    )
    try:
        # The directory (report, basetemp, and any child artifacts) is removed on
        # every outcome, including failures and timeouts.
        with tempfile.TemporaryDirectory(
            prefix="aud363-proof-", dir=temp_root
        ) as directory_name:
            directory = Path(directory_name)
            report = directory / "junit.xml"
            test_file = "tests/integration/test_aud363_454_borrowed_session_postgres.py"
            result = subprocess.run(  # noqa: S603  # Current interpreter and fixed test cases.
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *(f"{test_file}::{name}" for name in _CASES),
                    "-n",
                    "0",
                    "--no-cov",
                    "-p",
                    "no:cacheprovider",
                    "-o",
                    "xfail_strict=true",
                    f"--junitxml={report}",
                    f"--basetemp={directory / 'pytest'}",
                    "-q",
                ],
                env=child_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180,
                check=False,
            )
            if result.returncode != 0:
                raise ProofError("AUD-363/454 pytest process failed")
            validate_report(report)
    except (OSError, subprocess.SubprocessError):
        raise ProofError("AUD-363/454 pytest process failed") from None


def validate_report(path: Path) -> None:
    """Require exactly the six intended successful cases in one pytest suite."""
    try:
        root = ElementTree.parse(path).getroot()
    except (DefusedXmlException, ElementTree.ParseError, OSError):
        raise ProofError("AUD-363/454 report could not be read") from None
    suites = list(root.iter("testsuite"))
    if root.tag not in {"testsuite", "testsuites"} or len(suites) != 1:
        raise ProofError("AUD-363/454 report has an unexpected suite")
    suite = suites[0]
    if any(
        suite.get(key) != expected
        for key, expected in (
            ("tests", "6"),
            ("skipped", "0"),
            ("failures", "0"),
            ("errors", "0"),
        )
    ):
        raise ProofError("AUD-363/454 suite did not report six passes")
    cases = list(root.iter("testcase"))
    actual = Counter((case.get("classname"), case.get("name")) for case in cases)
    expected = Counter({(_MODULE, name): 1 for name in _CASES})
    if actual != expected or any(
        case.find(status) is not None
        for case in cases
        for status in ("skipped", "failure", "error")
    ):
        raise ProofError("AUD-363/454 named proof cases did not all pass")


def main() -> int:
    try:
        container_id = os.environ.get("AUD363_POSTGRES_CONTAINER_ID", "")
        runner_temp = os.environ.get("RUNNER_TEMP", "")
        if not container_id or not runner_temp:
            raise ProofError("owned PostgreSQL configuration missing")
        temp_root = Path(runner_temp)
        if not temp_root.is_dir():
            raise ProofError("runner temporary directory unavailable")
        admin_password = inspect_service(container_id)
        role_password = secrets.token_hex(32)
        asyncio.run(bootstrap(admin_password, role_password))
        if not hmac.compare_digest(admin_password, inspect_service(container_id)):
            raise ProofError("owned PostgreSQL identity changed")
        run_proof(role_password, temp_root)
    except Exception:
        # Fail closed on ProofError and on any unexpected error alike. The
        # message is fixed, so no exception text or credential reaches the log.
        print("AUD363_454_OWNED_POSTGRES_REJECTED", file=sys.stderr)
        return 1
    for name in _CASES:
        print(f"AUD363_454_CASE status=passed nodeid={_MODULE}::{name}")
    print("AUD-363/454: all six named PostgreSQL cases passed without skips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
