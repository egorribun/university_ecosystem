"""Exercise the dedicated revocation Redis URL guard with synthetic data."""

from __future__ import annotations

import base64
import io
import os
import runpy
import secrets
import sys
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOST = "sample-revocation-redis-master"
PASSWORD = f"{secrets.token_hex(8)}:@/{secrets.token_hex(8)}".encode()
ENCODED = quote(PASSWORD.decode("ascii"), safe="")


def _workflow_guard() -> str:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["deploy"]["steps"]
    step = next(
        item for item in steps if item.get("name") == "Verify effective Secret contract"
    )
    prefix = step["run"].split('\' "$revocation_redis_service_host"', 1)[0]
    return textwrap.dedent(prefix.rsplit("| python3 -c '\n", 1)[1])


def _guard_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    url: str,
    encoded_password: bytes,
) -> int:
    # Use an in-memory FD-3 substitute so the same test runs on Windows.
    guard = tmp_path / "guard.py"
    guard.write_text(_workflow_guard(), encoding="utf-8")
    output = io.StringIO()
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdin", io.StringIO(url))
        patch.setattr(sys, "argv", ["revocation-guard", HOST])
        patch.setattr(
            os, "fdopen", lambda *args, **kwargs: io.BytesIO(encoded_password)
        )
        with (
            redirect_stdout(output),
            redirect_stderr(output),
            pytest.raises(SystemExit) as result,
        ):
            runpy.run_path(str(guard), run_name="__main__")
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
    tmp_path: Path,
    url: str,
    password: bytes,
    expected: int,
) -> None:
    assert (
        _guard_result(monkeypatch, tmp_path, url, base64.b64encode(password))
        == expected
    )


def test_malformed_store_credential_is_rejected_without_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert (
        _guard_result(
            monkeypatch, tmp_path, f"redis://:{ENCODED}@{HOST}:6379/0", b"bad!"
        )
        == 1
    )
