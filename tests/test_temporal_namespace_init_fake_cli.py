"""Run the namespace initializer against a bounded fake CLI, never Temporal."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/temporal/namespace-init.sh"
WORKER_TOKEN = secrets.token_urlsafe(32)
ADMIN_TOKEN = secrets.token_urlsafe(32)
PRIVATE_MARKER = "PRIVATE-MARKER-DO-NOT-LEAK"

FAKE_TEMPORAL = r"""#!/bin/sh
set -eu
log='__LOG__'
count='__COUNT__'
mode='__MODE__'
config=''
previous=''
for argument in "$@"; do
  if [ "$previous" = '--config-file' ]; then config=$argument; fi
  previous=$argument
done
{
  printf 'CALL'
  for argument in "$@"; do printf '<%s>' "$argument"; done
  printf '\n'
  env
} >> "$log"

case "$*" in
  *'operator namespace describe'*)
    case "$config" in
      */worker.toml)
        if [ "$mode" = 'worker-success' ] && grep -Fq "api_key = '__WORKER__'" "$config"; then exit 0; fi
        exit 1
        ;;
      */profile.toml)
        if ! grep -Fq "api_key = '__ADMIN__'" "$config"; then exit 1; fi
        current=0
        if [ -f "$count" ]; then current=$(cat "$count"); fi
        current=$((current + 1))
        printf '%s\n' "$current" > "$count"
        if [ "$mode" = 'admin-create' ] && [ "$current" -ge 2 ]; then exit 0; fi
        exit 1
        ;;
    esac
    exit 1
    ;;
  *'operator cluster health'*)
    if [ "$mode" != 'worker-success' ] && [ "$mode" != 'admin-bad-profile' ] &&
       grep -Fq "api_key = '__ADMIN__'" "$config"; then exit 0; fi
    exit 1
    ;;
  *'operator namespace create'*)
    if [ "$mode" = 'admin-create' ] || [ "$mode" = 'admin-reverify-fails' ]; then
      if grep -Fq "api_key = '__ADMIN__'" "$config"; then exit 0; fi
    fi
    exit 1
    ;;
esac
exit 1
"""


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_case(
    tmp_path: Path,
    *,
    mode: str,
    worker: str | None = WORKER_TOKEN,
    admin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("sh")
    if os.name == "nt" or not shell:
        pytest.skip("POSIX shell is required for the fake CLI contract")

    root = tmp_path / mode
    runtime = root / "runtime"
    runtime.mkdir(parents=True)
    worker_dir = root / "worker"
    worker_dir.mkdir()
    bootstrap_dir = root / "bootstrap"
    bootstrap_dir.mkdir()
    bindir = root / "bin"
    bindir.mkdir()
    key_path = worker_dir / "token"
    if worker is not None:
        key_path.write_text(worker, encoding="ascii")
    profile_path = bootstrap_dir / "profile.toml"
    if admin is not None:
        profile_path.write_text(
            f"[profile.default]\naddress = '127.0.0.1:7233'\napi_key = '{admin}'\n",
            encoding="ascii",
        )

    _executable(
        bindir / "id", '#!/bin/sh\ncase "$1" in -u|-g) echo 1000;; *) exit 1;; esac\n'
    )
    _executable(bindir / "sleep", "#!/bin/sh\nexit 0\n")
    log_path = root / "cli.log"
    count_path = root / "admin-describes"
    temporal = (
        FAKE_TEMPORAL.replace("__LOG__", str(log_path))
        .replace("__COUNT__", str(count_path))
        .replace("__MODE__", mode)
        .replace("__WORKER__", WORKER_TOKEN)
        .replace("__ADMIN__", ADMIN_TOKEN)
    )
    _executable(bindir / "temporal", temporal)

    source = SCRIPT.read_text(encoding="utf-8")
    source = source.replace(
        "/run/temporal-bootstrap/profile.toml", str(profile_path)
    ).replace("/run/temporal-worker/token", str(key_path))
    source = source.replace("/run/temporal-bootstrap-runtime", str(runtime))
    source = source.replace(
        "PATH=/usr/local/bin:/usr/bin:/bin",
        f"PATH={bindir}:/usr/local/bin:/usr/bin:/bin",
    )
    script_path = root / "namespace-init.sh"
    script_path.write_text(source, encoding="utf-8")

    return subprocess.run(  # noqa: S603 - fixed test script in a temporary directory
        [shell, str(script_path)],
        cwd=root,
        env={
            "PATH": f"{bindir}:/usr/local/bin:/usr/bin:/bin",
            "TEMPORAL_TEST_SECRET": PRIVATE_MARKER,
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def _recorded_cli_calls(log: str) -> list[tuple[str, ...]]:
    calls = []
    for line in log.splitlines():
        if not line.startswith("CALL"):
            continue
        assert line.startswith("CALL<") and line.endswith(">")
        encoded_arguments = line[4:]
        arguments = tuple(encoded_arguments[1:-1].split("><"))
        assert arguments and all(arguments)
        assert "".join(f"<{argument}>" for argument in arguments) == encoded_arguments
        assert len(arguments) >= 3
        calls.append(arguments)
    return calls


def test_worker_token_succeeds_without_minting_admin_profile(tmp_path: Path) -> None:
    result = _run_case(tmp_path, mode="worker-success")
    assert result.returncode == 0, result.stderr
    log = (tmp_path / "worker-success/cli.log").read_text(encoding="utf-8")
    calls = _recorded_cli_calls(log)
    assert [call[:3] for call in calls] == [
        ("operator", "namespace", "describe"),
    ]
    assert len(calls) == 1
    timeout_index = calls[0].index("--command-timeout")
    assert calls[0][timeout_index + 1] == "2s"
    config_index = calls[0].index("--config-file")
    assert calls[0][config_index + 1].endswith("/worker.toml")
    assert "api_key" not in log
    assert f"TEMPORAL_TEST_SECRET={PRIVATE_MARKER}" not in log
    assert PRIVATE_MARKER not in result.stdout + result.stderr
    assert not (tmp_path / "worker-success/runtime/worker.toml").exists()


def test_admin_profile_creates_then_reverifies_namespace(tmp_path: Path) -> None:
    result = _run_case(
        tmp_path,
        mode="admin-create",
        admin=ADMIN_TOKEN,
    )
    assert result.returncode == 0, result.stderr
    log = (tmp_path / "admin-create/cli.log").read_text(encoding="utf-8")
    calls = _recorded_cli_calls(log)
    assert [call[:3] for call in calls] == [
        ("operator", "namespace", "describe"),
        ("operator", "cluster", "health"),
        ("operator", "namespace", "describe"),
        ("operator", "namespace", "create"),
        ("operator", "namespace", "describe"),
    ]
    assert len(calls) == 5
    assert [
        call[call.index("--config-file") + 1].rsplit("/", 1)[-1] for call in calls
    ] == [
        "worker.toml",
        "profile.toml",
        "profile.toml",
        "profile.toml",
        "profile.toml",
    ]
    assert all(call[call.index("--command-timeout") + 1] == "2s" for call in calls)
    assert WORKER_TOKEN not in log
    assert ADMIN_TOKEN not in log
    assert PRIVATE_MARKER not in log + result.stdout + result.stderr
    assert not (tmp_path / "admin-create/runtime/worker.toml").exists()


@pytest.mark.parametrize(
    ("mode", "worker", "admin", "expected_output"),
    [
        ("missing-worker", None, ADMIN_TOKEN, "worker credential unavailable"),
        ("malformed-worker", "bad$token", ADMIN_TOKEN, "worker credential is invalid"),
        ("missing-admin", WORKER_TOKEN, None, "namespace could not be verified"),
        (
            "admin-bad-profile",
            WORKER_TOKEN,
            "malformed-admin-profile",
            "authenticated health check failed",
        ),
        ("admin-reverify-fails", WORKER_TOKEN, ADMIN_TOKEN, "could not be verified"),
    ],
    ids=[
        "missing-worker",
        "malformed-worker",
        "missing-admin",
        "admin-bad-profile",
        "admin-reverify-fails",
    ],
)
def test_invalid_credentials_and_unverified_namespace_fail_closed(
    tmp_path: Path,
    mode: str,
    worker: str | None,
    admin: str | None,
    expected_output: str,
) -> None:
    result = _run_case(
        tmp_path,
        mode=mode,
        worker=worker,
        admin=admin,
    )
    assert result.returncode != 0
    assert expected_output in result.stderr
    transcript = result.stdout + result.stderr
    assert PRIVATE_MARKER not in transcript
    assert WORKER_TOKEN not in transcript
    assert ADMIN_TOKEN not in transcript
    assert not (tmp_path / mode / "runtime/worker.toml").exists()
    log_path = tmp_path / mode / "cli.log"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if mode == "missing-admin":
        calls = _recorded_cli_calls(log)
        assert [call[:3] for call in calls] == [
            ("operator", "namespace", "describe"),
        ] * 24
        assert len(calls) == 24
        assert all(
            call[call.index("--config-file") + 1].endswith("/worker.toml")
            for call in calls
        )
        assert all(call[call.index("--command-timeout") + 1] == "2s" for call in calls)
    if mode == "admin-reverify-fails":
        assert (tmp_path / mode / "admin-describes").read_text(
            encoding="ascii"
        ).strip() == "24"
