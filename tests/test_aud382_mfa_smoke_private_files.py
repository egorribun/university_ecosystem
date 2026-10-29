"""Exercise MFA overlap smoke files through the real shell entrypoint."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import signal
import subprocess
import uuid
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / ".github/deployment-smoke/mfa-key-overlap.sh"
)

# The smoke script needs jq and HTTPS endpoints. These small command stubs provide
# deterministic responses without contacting a service; the real Bash script,
# its redirections, process boundaries, and filesystem operations still run.
JQ_STUB = r"""#!/usr/bin/env python3
import json
import os
import stat
import sys

args = sys.argv[1:]
values = {}
null_input = False
raw = False
check = False
index = 0
while index < len(args):
    arg = args[index]
    if arg in ("--arg", "--argjson"):
        value = args[index + 2]
        values[args[index + 1]] = json.loads(value) if arg == "--argjson" else value
        index += 3
    elif arg in ("--null-input", "--raw-output", "--exit-status"):
        null_input |= arg == "--null-input"
        raw |= arg == "--raw-output"
        check |= arg == "--exit-status"
        index += 1
    else:
        break
expression = args[index]
if null_input:
    if "password" in values:
        result = {"email": values["email"], "password": values["password"], "trust_device": False}
    elif "queued_at_epoch" in values:
        result = {"challenge_token": values["challenge_token"], "queued_at_epoch": values["queued_at_epoch"]}
    elif "operation" in values:
        result = dict(values)
    else:
        result = {"method": "email_otp", "challenge_token": values["challenge_token"], "code": values["code"]}
else:
    with open(args[index + 1], encoding="utf-8") as stream:
        data = json.load(stream)
    if check:
        if "mfa_required" in expression:
            ok = data.get("status") == "mfa_required" and len(data.get("methods", [])) == 1
        elif "delivered" in expression:
            ok = data.get("status") == "delivered" and data.get("challenge_token") == values["challenge_token"] and len(data.get("code", "")) == 6
        else:
            ok = bool(data.get("user", {}).get("id"))
        sys.exit(0 if ok else 1)
    if expression.startswith("[.methods"):
        result = data["methods"][0]["challenge_token"]
    else:
        result = data.get(expression.lstrip(".").split()[0], "")

metadata = os.fstat(sys.stdout.fileno())
if stat.S_ISREG(metadata.st_mode):
    target = os.readlink("/proc/self/fd/1")
    with open(os.environ["MFA_TEST_WRITES"], "a", encoding="utf-8") as audit:
        audit.write(json.dumps({"path": target, "mode": stat.S_IMODE(metadata.st_mode)}) + "\n")
print(result if raw else json.dumps(result))
"""

CURL_STUB = r"""#!/usr/bin/env python3
import datetime
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
def value(option):
    return args[args.index(option) + 1]

url = args[-1]
output = Path(value("--output"))
if url.endswith("/csrf-cookie"):
    Path(value("--cookie-jar")).write_text("example.invalid\tFALSE\t/\tTRUE\t0\tcsrf_token\t" + os.environ["MFA_TEST_CSRF"] + "\n", encoding="utf-8")
    sys.exit(0)

payload = json.loads(Path(value("--data-binary")[1:]).read_text(encoding="utf-8"))
if url.endswith("/login/json"):
    operation = "login"
    assert payload["password"] == os.environ["MFA_SMOKE_PASSWORD"]
    old = Path(value("--cookie-jar")).name.startswith("old-")
    token = os.environ["MFA_TEST_OLD_TOKEN" if old else "MFA_TEST_NEW_TOKEN"]
    response = {"status": "mfa_required", "methods": [{"method": "email_otp", "challenge_token": token}]}
elif url == os.environ["MFA_SMOKE_MAILBOX_URL"]:
    operation = "mailbox"
    old = payload["challenge_token"] == os.environ["MFA_TEST_OLD_TOKEN"]
    response = {"status": "delivered", "challenge_token": payload["challenge_token"], "delivery_id": os.environ["MFA_TEST_OLD_ID" if old else "MFA_TEST_NEW_ID"], "code": os.environ["MFA_TEST_CODE"], "delivered_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
else:
    operation = "verify"
    assert payload["code"] == os.environ["MFA_TEST_CODE"]
    with open(value("--cookie-jar"), "a", encoding="utf-8") as cookies:
        cookies.write("example.invalid\tFALSE\t/\tTRUE\t0\taccess_token_v2\t" + os.environ["MFA_TEST_ACCESS"] + "\n")
    response = {"user": {"id": "synthetic-user"}}

with open(os.environ["MFA_TEST_CALLS"], "a", encoding="utf-8") as calls:
    calls.write(operation + "\n")
if operation == os.environ.get("MFA_TEST_BLOCK_AT"):
    Path(os.environ["MFA_TEST_READY"]).touch()
    while not Path(os.environ["MFA_TEST_RELEASE"]).exists():
        time.sleep(0.02)
if operation == os.environ.get("MFA_TEST_FAIL_AT"):
    sys.exit(7)
output.write_text(json.dumps(response), encoding="utf-8")
print("200", end="")
"""


@pytest.fixture
def smoke(tmp_path: Path) -> dict[str, object]:
    runner = tmp_path / "runner"
    state = runner / "state"
    state.mkdir(parents=True)
    commands = tmp_path / "bin"
    commands.mkdir()
    for name, source in (("jq", JQ_STUB), ("curl", CURL_STUB)):
        path = commands / name
        path.write_text(source, encoding="utf-8", newline="\n")
        path.chmod(0o700)
    env = os.environ.copy()
    env.update(
        PATH=f"{commands}{os.pathsep}{env['PATH']}",
        RUNNER_TEMP=str(runner),
        MFA_SMOKE_STATE_DIR=str(state),
        MFA_SMOKE_BASE_URL="https://api.example.invalid",
        MFA_SMOKE_MAILBOX_URL="https://mail.example.invalid",
        MFA_SMOKE_EMAIL=f"{secrets.token_hex(4)}@example.invalid",
        MFA_SMOKE_PASSWORD=secrets.token_urlsafe(24),
        MFA_SMOKE_MAILBOX_TOKEN=secrets.token_urlsafe(24),
        MFA_TEST_OLD_TOKEN=secrets.token_hex(24),
        MFA_TEST_NEW_TOKEN=secrets.token_hex(24),
        MFA_TEST_OLD_ID=str(uuid.uuid4()),
        MFA_TEST_NEW_ID=str(uuid.uuid4()),
        MFA_TEST_CODE=f"{secrets.randbelow(1_000_000):06d}",
        MFA_TEST_CSRF=secrets.token_hex(12),
        MFA_TEST_ACCESS=secrets.token_hex(12),
        MFA_TEST_WRITES=str(tmp_path / "writes.jsonl"),
        MFA_TEST_CALLS=str(tmp_path / "calls.txt"),
        MFA_TEST_READY=str(tmp_path / "ready"),
        MFA_TEST_RELEASE=str(tmp_path / "release"),
    )
    return {"state": state, "env": env, "tmp": tmp_path}


async def _start(
    smoke: dict[str, object], mode: str, **extra: str
) -> asyncio.subprocess.Process:
    assert mode in {"prepare", "verify-old", "verify-new"}
    env = dict(smoke["env"])
    env.update(extra)
    return await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        'umask 000; exec "$1" "$2" "$3"',
        "_",
        "/bin/bash",
        str(SCRIPT),
        mode,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )


def _run(
    smoke: dict[str, object], mode: str, **extra: str
) -> subprocess.CompletedProcess[str]:
    async def invoke() -> subprocess.CompletedProcess[str]:
        process = await _start(smoke, mode, **extra)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
        except TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.communicate()
            raise
        assert process.returncode is not None
        return subprocess.CompletedProcess(
            [str(SCRIPT), mode], process.returncode, stdout.decode(), stderr.decode()
        )

    return asyncio.run(invoke())


def _assert_no_transient_requests(smoke: dict[str, object]) -> None:
    state = smoke["state"]
    assert isinstance(state, Path)
    transient_names = {
        "login-payload.json",
        "mailbox-old-request.json",
        "mailbox-new-request.json",
        "verify-old-request.json",
        "verify-new-request.json",
    }
    assert not [
        path
        for path in state.rglob("*")
        if path.name in transient_names and not path.is_symlink()
    ]
    assert not list(state.glob("mfa-overlap-*"))


def _must_succeed(smoke: dict[str, object], mode: str) -> None:
    result = _run(smoke, mode)
    assert result.returncode == 0, result.stderr
    _assert_no_transient_requests(smoke)


def test_login_payload_is_private_when_writer_opens_it(
    smoke: dict[str, object],
) -> None:
    result = _run(smoke, "prepare")
    assert result.returncode == 0, result.stderr
    audit = Path(smoke["env"]["MFA_TEST_WRITES"])
    writes = [
        json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()
    ]
    login = [
        record for record in writes if record["path"].endswith("login-payload.json")
    ]
    assert len(login) == 1
    assert login[0]["mode"] == 0o600


def test_three_phase_flow_creates_private_requests_and_removes_them(
    smoke: dict[str, object],
) -> None:
    state = smoke["state"]
    assert isinstance(state, Path)
    sentinel = state / "unrelated-metadata"
    sentinel.write_text("preserve", encoding="utf-8")
    _must_succeed(smoke, "prepare")
    assert (state / "old-challenge.json").is_file()
    assert (state / "old-cookies.txt").is_file()
    _must_succeed(smoke, "verify-old")
    assert (state / "old-verified").is_file()
    assert (state / "old-delivery.json").is_file()
    _must_succeed(smoke, "verify-new")
    assert sentinel.read_text(encoding="utf-8") == "preserve"

    audit = Path(smoke["env"]["MFA_TEST_WRITES"])
    writes = [
        json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()
    ]
    requests = [
        record
        for record in writes
        if "request.json" in record["path"]
        or record["path"].endswith("login-payload.json")
    ]
    assert len(requests) == 6
    assert all(record["mode"] == 0o600 for record in requests)


def test_existing_request_symlink_is_neither_followed_nor_removed(
    smoke: dict[str, object],
) -> None:
    state = smoke["state"]
    assert isinstance(state, Path)
    target = state / "unrelated-metadata"
    target.write_text("preserve", encoding="utf-8")
    link = state / "login-payload.json"
    link.symlink_to(target)
    _must_succeed(smoke, "prepare")
    assert link.is_symlink()
    unchanged = target.read_text(encoding="utf-8") == "preserve"
    assert unchanged, "unrelated metadata changed"


def test_other_invocation_directory_is_not_removed(smoke: dict[str, object]) -> None:
    state = smoke["state"]
    assert isinstance(state, Path)
    other = state / "mfa-overlap-other"
    other.mkdir()
    (other / "sentinel").write_text("preserve", encoding="utf-8")
    result = _run(smoke, "prepare")
    assert result.returncode == 0, result.stderr
    assert (other / "sentinel").read_text(encoding="utf-8") == "preserve"
    assert set(state.glob("mfa-overlap-*")) == {other}


def test_private_directory_creation_failure_stops_before_requests(
    smoke: dict[str, object],
) -> None:
    commands = Path(smoke["env"]["PATH"].split(os.pathsep)[0])
    mktemp = commands / "mktemp"
    mktemp.write_text("#!/bin/sh\nexit 23\n", encoding="utf-8")
    mktemp.chmod(0o700)
    result = _run(smoke, "prepare")
    assert result.returncode != 0
    assert not Path(smoke["env"]["MFA_TEST_CALLS"]).exists()
    _assert_no_transient_requests(smoke)


def test_private_directory_cleanup_failure_is_not_success(
    smoke: dict[str, object],
) -> None:
    commands = Path(smoke["env"]["PATH"].split(os.pathsep)[0])
    remove = commands / "rm"
    remove.write_text(
        '#!/bin/sh\n/bin/rm "$@" || exit $?\n[ "$1" != "-rf" ]\n',
        encoding="utf-8",
    )
    remove.chmod(0o700)
    result = _run(smoke, "prepare")
    assert result.returncode != 0
    _assert_no_transient_requests(smoke)


@pytest.mark.parametrize(
    ("mode", "operation"),
    [("prepare", "login"), ("verify-old", "mailbox"), ("verify-new", "verify")],
)
def test_request_cleanup_on_command_failure(
    smoke: dict[str, object], mode: str, operation: str
) -> None:
    if mode != "prepare":
        _must_succeed(smoke, "prepare")
    if mode == "verify-new":
        _must_succeed(smoke, "verify-old")
    result = _run(smoke, mode, MFA_TEST_FAIL_AT=operation)
    assert result.returncode != 0
    _assert_no_transient_requests(smoke)


@pytest.mark.parametrize("interruption", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("recipient", ["process", "group"])
def test_request_cleanup_on_termination(
    smoke: dict[str, object], interruption: signal.Signals, recipient: str
) -> None:
    async def exercise() -> None:
        process = await _start(smoke, "prepare", MFA_TEST_BLOCK_AT="login")
        marker = Path(smoke["env"]["MFA_TEST_READY"])
        try:
            deadline = asyncio.get_running_loop().time() + 10
            while (
                not marker.exists()
                and process.returncode is None
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.02)
            assert marker.exists(), (
                "login request did not reach the controlled endpoint"
            )
            if recipient == "group":
                os.killpg(process.pid, interruption)
            else:
                os.kill(process.pid, interruption)
                Path(smoke["env"]["MFA_TEST_RELEASE"]).touch()
            await asyncio.wait_for(process.communicate(), timeout=10)
            assert process.returncode == 128 + interruption
            _assert_no_transient_requests(smoke)
        finally:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.communicate()

    asyncio.run(exercise())


@pytest.mark.parametrize("state_value", ["missing", "invalid-token", "invalid-json"])
def test_verify_new_rejects_missing_or_invalid_old_challenge(
    smoke: dict[str, object], state_value: str
) -> None:
    _must_succeed(smoke, "prepare")
    _must_succeed(smoke, "verify-old")
    state = smoke["state"]
    assert isinstance(state, Path)
    challenge = state / "old-challenge.json"
    if state_value == "missing":
        challenge.unlink()
    elif state_value == "invalid-token":
        challenge.write_text(json.dumps({"challenge_token": "bad"}), encoding="utf-8")
    else:
        challenge.write_text("{", encoding="utf-8")
    calls = Path(smoke["env"]["MFA_TEST_CALLS"])
    before = calls.read_text(encoding="utf-8")
    result = _run(smoke, "verify-new")
    assert result.returncode != 0
    assert calls.read_text(encoding="utf-8") == before
    _assert_no_transient_requests(smoke)


def test_verify_new_rejects_reused_old_challenge(smoke: dict[str, object]) -> None:
    _must_succeed(smoke, "prepare")
    _must_succeed(smoke, "verify-old")
    result = _run(
        smoke, "verify-new", MFA_TEST_NEW_TOKEN=smoke["env"]["MFA_TEST_OLD_TOKEN"]
    )
    assert result.returncode != 0
    _assert_no_transient_requests(smoke)
