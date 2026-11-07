"""Exercise the dedicated revocation Redis URL guard with synthetic data."""

from __future__ import annotations

import base64
import io
import os
import runpy
import secrets
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOST = "sample-revocation-redis-master"
PASSWORD = f"{secrets.token_hex(8)}:@/{secrets.token_hex(8)}".encode()
ENCODED = quote(PASSWORD.decode("ascii"), safe="")
# The current helper also enforces cache/store separation. Keep this synthetic
# cache credential distinct so the existing URL matrix tests the URL contract.
CACHE_PASSWORD = PASSWORD + b"-cache"


def _workflow_guard() -> Path:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["deploy"]["steps"]
    step = next(
        item for item in steps if item.get("name") == "Verify effective Secret contract"
    )
    run = step["run"]
    helper = ROOT / ".github/scripts/verify_revocation_redis_target.py"
    assert (
        "python3 -I .github/scripts/verify_revocation_redis_target.py "
        '"$revocation_redis_service_host"' in run
    )
    assert "3< <(printf '%s' \"$revocation_redis_password_b64\")" in run
    assert "4< <(printf '%s' \"$cache_redis_password_b64\")" in run
    assert helper.is_file()
    return helper


def _guard_result(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    encoded_password: bytes,
    encoded_cache_password: bytes,
) -> int:
    # Keep both secret-file descriptors in memory so the test runs on Windows.
    credentials = {3: encoded_password, 4: encoded_cache_password}

    def open_descriptor(descriptor: int, mode: str) -> io.BytesIO:
        assert mode == "rb"
        return io.BytesIO(credentials[descriptor])

    output = io.StringIO()
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdin", io.StringIO(url))
        patch.setattr(sys, "argv", ["revocation-guard", HOST])
        patch.setattr(os, "fdopen", open_descriptor)
        with (
            redirect_stdout(output),
            redirect_stderr(output),
            pytest.raises(SystemExit) as result,
        ):
            runpy.run_path(str(_workflow_guard()), run_name="__main__")
    assert output.getvalue() == ""
    return result.value.code


@pytest.mark.parametrize(
    ("url", "password", "expected"),
    [
        pytest.param(f"redis://:{ENCODED}@{HOST}:6379/0", PASSWORD, 0, id="encoded"),
        pytest.param(
            f"redis://default:{ENCODED}@{HOST}:6379/0", PASSWORD, 0, id="default-user"
        ),
        pytest.param(
            f"redis://:{ENCODED}@{HOST}:6379/0",
            PASSWORD + b"\n",
            0,
            id="mounted-trailing-lf",
        ),
        pytest.param(
            f"rediss://:{ENCODED}@{HOST}:6379/0", PASSWORD, 1, id="unsupported-tls"
        ),
        pytest.param(f"redis://{HOST}:6379/0", PASSWORD, 1, id="missing-password"),
        pytest.param(f"redis://:wrong@{HOST}:6379/0", PASSWORD, 1, id="wrong-password"),
        pytest.param(
            f"redis://other:{ENCODED}@{HOST}:6379/0", PASSWORD, 1, id="unknown-user"
        ),
        pytest.param(
            f"redis://:{ENCODED}@{HOST}:6379/0?db=1",
            PASSWORD,
            1,
            id="database-override",
        ),
        pytest.param(
            f"redis://:{ENCODED}@{HOST}:6379/0#ignored", PASSWORD, 1, id="fragment"
        ),
        pytest.param(
            f"redis://:%ff%xx@{HOST}:6379/0", PASSWORD, 1, id="invalid-percent"
        ),
        pytest.param(f"redis://:{ENCODED}@other:6379/0", PASSWORD, 1, id="wrong-host"),
        pytest.param(f"redis://:{ENCODED}@{HOST}:6380/0", PASSWORD, 1, id="wrong-port"),
        pytest.param(
            f"redis://:{ENCODED}@{HOST}:6379/1", PASSWORD, 1, id="wrong-database"
        ),
        pytest.param(
            f"redis://:{ENCODED}@{HOST}:6379/0", b"", 1, id="empty-store-password"
        ),
        pytest.param(
            f"redis://:{ENCODED}@{HOST}:6379/0",
            PASSWORD + b"\x00",
            1,
            id="nul-store-password",
        ),
    ],
)
def test_dedicated_store_url_guard_matches_store(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    password: bytes,
    expected: int,
) -> None:
    assert (
        _guard_result(
            monkeypatch,
            url,
            base64.b64encode(password),
            base64.b64encode(CACHE_PASSWORD),
        )
        == expected
    )


def test_malformed_store_credential_is_rejected_without_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _guard_result(
            monkeypatch,
            f"redis://:{ENCODED}@{HOST}:6379/0",
            b"bad!",
            base64.b64encode(CACHE_PASSWORD),
        )
        == 1
    )
