"""PowerShell launcher coverage for owned in-place live-stand state roots."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import shutil
import stat
import string
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# The launcher fixtures use PowerShell 7, whose redirected text output is UTF-8.
POWERSHELL = shutil.which("pwsh")
PORT_NAMES = (
    "BACKEND",
    "FRONTEND",
    "POSTGRES",
    "GATEWAY",
    "WS_HUB",
    "TEMPORAL_GRPC",
    "TEMPORAL_WEB",
    "IMGPROXY",
    "GRAFANA",
    "PROMETHEUS",
    "ALLOY",
    "PYROSCOPE",
    "CADDY_HTTP",
    "CADDY_HTTPS",
    "MAILPIT",
)
CURRENT_PORT_NAMES = (*PORT_NAMES[:-1], "MINIO", "MAILPIT")
LIVE_CORE_ROOTS = (
    "caddy",
    "mailpit",
    "notifications-worker",
    "outbox-worker",
    "spicedb",
)


def _fixture_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "source checkout"
    project.mkdir()
    shutil.copy2(ROOT / "start-docker.ps1", project / "start-docker.ps1")
    for name in ("docker-compose.full.yml", "docker-compose.live.yml"):
        shutil.copy2(ROOT / name, project / name)
    runtime_files = (
        "config/nats.conf.template",
        "services/temporal/config.yaml",
        "services/temporal/entrypoint.sh",
        "infrastructure/observability/prometheus.yml",
        "infrastructure/observability/alerts/gateway.yaml",
        "infrastructure/observability/tempo.yaml",
        "infrastructure/observability/loki.yaml",
        "infrastructure/observability/alloy/config.alloy",
        "infrastructure/observability/grafana/provisioning/datasources/datasources.yaml",
        "k8s/flagd/flags.json",
        "infrastructure/Caddyfile",
    )
    for relative in runtime_files:
        source = ROOT / relative
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return project, tmp_path / "temp" / "ue-live-acceptance" / "run-36854541120"


def _vapid_pair() -> tuple[str, str]:
    # The launcher validates key shape and the uncompressed P-256 public point.
    private = bytes.fromhex("01" * 32)
    public = b"\x04" + bytes.fromhex("02" * 64)
    return (
        base64.urlsafe_b64encode(public).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(private).decode("ascii").rstrip("="),
    )


def _owner_marker(
    project: Path, state_root: Path, *, version: int = 7
) -> dict[str, object]:
    port_names = CURRENT_PORT_NAMES if version == 11 else PORT_NAMES
    payload: dict[str, object] = {
        "version": version,
        "repository": str(project.resolve()),
        "worktree": str(state_root.resolve()),
        "project_name": "ue-live-36854541120abcd1",
        "published_ports": {
            name: 32000 + index for index, name in enumerate(port_names)
        },
        "daemon_fingerprint": "d" * 64,
        "compose_resource_fingerprint": None,
        "resume_compose_resource_fingerprint": None,
        "source_sha": "a" * 40,
    }
    if version == 11:
        payload.update(
            {
                "resume_compose_resource_schema_version": None,
                "stack": "core",
                "service_roots": list(LIVE_CORE_ROOTS),
                "selected_services": [],
            }
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = b"owner-key-fixture-material-32bytes!"[:32]
    signature = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**payload, "signature": signature}


def _windows_user_sid() -> str:
    whoami = shutil.which("whoami.exe") or shutil.which("whoami")
    assert whoami is not None
    identity = subprocess.run(  # noqa: S603 - fixed Windows identity query
        [whoami, "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        check=True,
        timeout=10,
    )
    rows = identity.stdout.splitlines()
    assert len(rows) == 1
    # The account column may use the Windows console code page. Only the final
    # SID field is consumed; it is ASCII and can be decoded strictly.
    sid_field = rows[0].rsplit(b",", maxsplit=1)[-1].strip().strip(b'"')
    sid = sid_field.decode("ascii")
    assert sid.startswith("S-1-")
    return sid


def _secure_state_tree(state_root: Path) -> None:
    if os.name == "nt":
        icacls = shutil.which("icacls.exe") or shutil.which("icacls")
        assert icacls is not None
        sid = _windows_user_sid()
        # Native icacls output is localized and unused; keep it as bytes rather
        # than assuming PowerShell's UTF-8 stream encoding.
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool and pytest-owned temp path
            [icacls, str(state_root), "/reset", "/T", "/C"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool and validated SID
            [icacls, str(state_root), "/setowner", f"*{sid}", "/T", "/C"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool and validated SID
            [
                icacls,
                str(state_root),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return
    state_root.chmod(0o700)
    for path in state_root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)


def _live_environment(
    state_root: Path, public: str, private: str, *, current_schema: bool = False
) -> dict[str, str]:
    env = os.environ.copy()
    temp_root = state_root.parents[1]
    env["TEMP"] = str(temp_root)
    env["TMP"] = str(temp_root)
    if os.name != "nt":
        env["TMPDIR"] = str(temp_root)
    # -NoProfile still uses the .NET startup cache on Unix.
    env["XDG_CACHE_HOME"] = str(temp_root / ".powershell-cache")
    env["COMPOSE_PROJECT_NAME"] = "ue-live-36854541120abcd1"
    port_names = CURRENT_PORT_NAMES if current_schema else PORT_NAMES
    ports = {name: 32000 + index for index, name in enumerate(port_names)}
    env["LIVE_BASE_URL"] = f"http://localhost:{ports['CADDY_HTTP']}"
    env["LIVE_VAPID_PUBLIC_KEY"] = public
    env["LIVE_VAPID_PRIVATE_KEY"] = private
    env["LIVE_STAND_SOURCE_SHA"] = "a" * 40
    for name, port in ports.items():
        if name == "MAILPIT":
            env["LIVE_MAILPIT_PORT"] = str(port)
        else:
            env[f"LIVE_HOST_PORT_{name}"] = str(port)
    return env


def _run_prepare(
    project: Path,
    state_root: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    # Some callers supply stand_environment() instead of _live_environment().
    environment = env.copy()
    environment["XDG_CACHE_HOME"] = str(project / ".powershell-cache")
    return subprocess.run(  # noqa: S603 - fixed PowerShell file and constrained test arguments
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(project / "start-docker.ps1"),
            "-PrepareOnly",
            "-ExtraCompose",
            "docker-compose.live.yml",
            "-LiveStandStateRoot",
            str(state_root),
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=40,
    )


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _write_env_value(path: Path, key: str, value: str) -> None:
    prefix = f"{key}="
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            replaced = True
    if not replaced:
        lines.append(f"{prefix}{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _remove_env_values(path: Path, keys: tuple[str, ...]) -> None:
    prefixes = tuple(f"{key}=" for key in keys)
    lines = path.read_text(encoding="utf-8").splitlines()
    retained = [line for line in lines if not line.startswith(prefixes)]
    path.write_text("\n".join(retained) + "\n", encoding="utf-8")


def _single_mfa_key_material(
    values: dict[str, str], ring_name: str, active_name: str
) -> tuple[str, bytes]:
    ring = values.get(ring_name, "")
    active_id = values.get(active_name, "")
    if not ring or not active_id or ring.count(":") != 1 or "," in ring:
        raise AssertionError("invalid single-key MFA ring fixture")
    key_id, encoded = ring.split(":", 1)
    if not key_id or key_id != active_id or not encoded:
        raise AssertionError("invalid active MFA key binding")
    if any(char not in string.ascii_letters + string.digits + "-_" for char in encoded):
        raise AssertionError("invalid MFA key encoding")
    try:
        material = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise AssertionError("invalid MFA key encoding") from exc
    if len(material) != 32:
        raise AssertionError("unexpected MFA key length")
    return ring, material


def _windows_acl_summary(path: Path) -> dict[str, object]:
    powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
    assert powershell is not None
    env = os.environ.copy()
    env["LIVE_STAND_ACL_TARGET"] = str(path)
    script = r"""
$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $env:LIVE_STAND_ACL_TARGET
$ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
$rules = @($acl.Access | ForEach-Object {
    [pscustomobject]@{
        Sid = $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        Type = $_.AccessControlType.ToString()
        Rights = $_.FileSystemRights.ToString()
    }
})
[pscustomobject]@{ OwnerSid = $ownerSid; Rules = $rules } | ConvertTo-Json -Depth 5 -Compress
"""
    result = subprocess.run(  # noqa: S603 - fixed PowerShell executable and test temp path
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


def _assert_windows_private_acl(path: Path) -> None:
    acl = _windows_acl_summary(path)
    user_sid = _windows_user_sid()
    assert acl["OwnerSid"] == user_sid
    rules = acl["Rules"]
    assert isinstance(rules, list)
    allow_rules = [rule for rule in rules if rule["Type"] == "Allow"]
    assert {rule["Sid"] for rule in allow_rules} == {user_sid, "S-1-5-18"}
    assert all("FullControl" in rule["Rights"] for rule in allow_rules)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_refuses_state_root_outside_owned_temp_parent_without_writes(
    tmp_path: Path,
) -> None:
    project, state_root = _fixture_project(tmp_path)
    outside_root = tmp_path / "unowned-state"
    outside_root.mkdir()
    public, private = _vapid_pair()
    source_before = {
        name: (project / name).read_bytes()
        for name in (
            "start-docker.ps1",
            "docker-compose.full.yml",
            "docker-compose.live.yml",
        )
    }

    result = _run_prepare(
        project,
        outside_root,
        _live_environment(state_root, public, private),
    )

    assert result.returncode != 0
    assert "owned temporary" in (result.stdout + result.stderr).lower()
    assert not (project / ".env").exists()
    assert not (project / ".env.docker").exists()
    assert not (project / ".secrets").exists()
    assert {
        name: (project / name).read_bytes() for name in source_before
    } == source_before


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_prepare_only_writes_live_configuration_under_owned_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    parent_environment = os.environ.copy()
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    public, private = _vapid_pair()
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root)), encoding="utf-8"
    )
    state_overlay = state_root / "docker-compose.live-state.yml"
    state_overlay.write_text("services: {}\n", encoding="utf-8")
    _secure_state_tree(state_root)
    env = _live_environment(state_root, public, private)

    result = _run_prepare(project, state_root, env)

    assert result.returncode == 0, result.stderr[-2000:]
    assert profile.read_bytes() == sentinel
    assert os.environ == parent_environment
    assert (state_root / ".env").is_file()
    assert (state_root / ".env.docker").is_file()
    assert (state_root / ".env.docker.workers").is_file()
    assert (secrets_root / "jwt_rs256.pem").is_file()
    assert (secrets_root / "jwt_rs256.pub.pem").is_file()
    assert (secrets_root / "temporal_api_key").is_file()
    assert state_overlay.read_text(encoding="utf-8") == "services: {}\n"
    assert not (project / ".env").exists()
    assert not (project / ".env.docker").exists()
    assert not (project / ".env.docker.workers").exists()
    assert not (project / ".secrets").exists()
    if os.name != "nt":
        assert stat.S_IMODE(state_root.stat().st_mode) == 0o700
        assert stat.S_IMODE(secrets_root.stat().st_mode) == 0o700
        for path in (
            state_root / ".env",
            state_root / ".env.docker",
            state_root / ".env.docker.workers",
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in (
            secrets_root / "jwt_rs256.pem",
            secrets_root / "jwt_rs256.pub.pem",
            secrets_root / "temporal_api_key",
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o644
        for path in (
            secrets_root / "live-stand-owner.key",
            secrets_root / "live-vapid.json",
            secrets_root / "live-stand.json",
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        for path in (
            state_root / ".env",
            state_root / ".env.docker",
            state_root / ".env.docker.workers",
            secrets_root / "jwt_rs256.pem",
            secrets_root / "jwt_rs256.pub.pem",
            secrets_root / "temporal_api_key",
        ):
            _assert_windows_private_acl(path)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_generates_and_preserves_run_local_audit_and_email_mfa_keys(
    tmp_path: Path,
) -> None:
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    public, private = _vapid_pair()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root, version=11)), encoding="utf-8"
    )
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    env = _live_environment(state_root, public, private, current_schema=True)

    first_result = _run_prepare(project, state_root, env)

    assert first_result.returncode == 0, "fresh PrepareOnly setup failed"
    docker_env_path = state_root / ".env.docker"
    compose_env_path = state_root / ".env"
    worker_env_path = state_root / ".env.docker.workers"
    generated_docker = _read_env_file(docker_env_path)
    generated_compose = _read_env_file(compose_env_path)
    generated_workers = _read_env_file(worker_env_path)
    generated_key = generated_docker.get("AUDIT_LOG_SECRET", "")
    generated_is_independent = not hmac.compare_digest(
        generated_key, generated_docker.get("SECRET_KEY", "")
    )
    generated_was_not_printed = generated_key not in (
        first_result.stdout + first_result.stderr
    )
    mfa_key_names = (
        "MFA_EMAIL_OTP_HMAC_KEYS",
        "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID",
        "MFA_EMAIL_DELIVERY_KEKS",
        "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID",
    )
    mfa_values = {name: generated_docker.get(name, "") for name in mfa_key_names}
    otp_active_id = mfa_values["MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID"]
    otp_ring, otp_material = _single_mfa_key_material(
        generated_docker,
        "MFA_EMAIL_OTP_HMAC_KEYS",
        "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID",
    )
    delivery_ring, delivery_material = _single_mfa_key_material(
        generated_docker,
        "MFA_EMAIL_DELIVERY_KEKS",
        "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID",
    )
    key_material_is_independent = not hmac.compare_digest(
        otp_material, delivery_material
    )
    assert key_material_is_independent
    mfa_compose_matches = all(
        hmac.compare_digest(generated_compose.get(name, ""), value)
        for name, value in mfa_values.items()
    )
    worker_has_delivery_kek = hmac.compare_digest(
        generated_workers.get("MFA_EMAIL_DELIVERY_KEKS", ""), delivery_ring
    )
    api_only_key_names_absent_from_worker = all(
        name not in generated_workers
        for name in (
            "MFA_EMAIL_OTP_HMAC_KEYS",
            "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID",
            "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID",
        )
    )
    mfa_files_match = (
        mfa_compose_matches
        and worker_has_delivery_kek
        and api_only_key_names_absent_from_worker
    )
    assert mfa_files_match
    mfa_secrets_not_printed = all(
        secret not in (first_result.stdout + first_result.stderr)
        for secret in (
            otp_ring,
            delivery_ring,
            otp_ring.split(":", 1)[1],
            delivery_ring.split(":", 1)[1],
        )
    )
    assert mfa_secrets_not_printed
    assert len(generated_key) == 64
    assert generated_key.isascii() and generated_key.isalnum()
    assert generated_is_independent
    assert generated_compose.get("AUDIT_LOG_SECRET") == generated_key
    assert generated_workers.get("AUDIT_LOG_SECRET") == generated_key
    assert generated_was_not_printed
    assert not (project / ".env").exists()
    assert not (project / ".env.docker").exists()

    preserved_key = ",".join((secrets.token_hex(32), secrets.token_hex(32)))
    _write_env_value(docker_env_path, "AUDIT_LOG_SECRET", preserved_key)
    _remove_env_values(docker_env_path, mfa_key_names)

    second_result = _run_prepare(project, state_root, env)

    preserved_docker = _read_env_file(docker_env_path)
    preserved_compose = _read_env_file(compose_env_path)
    preserved_workers = _read_env_file(worker_env_path)
    preserved_was_not_printed = preserved_key not in (
        second_result.stdout + second_result.stderr
    )
    assert second_result.returncode == 0, "preserved-key PrepareOnly setup failed"
    assert hmac.compare_digest(
        preserved_docker.get("AUDIT_LOG_SECRET", ""), preserved_key
    )
    assert hmac.compare_digest(
        preserved_compose.get("AUDIT_LOG_SECRET", ""), preserved_key
    )
    assert hmac.compare_digest(
        preserved_workers.get("AUDIT_LOG_SECRET", ""), preserved_key
    )
    assert preserved_was_not_printed
    preserved_mfa_values = _read_env_file(docker_env_path)
    preserved_mfa_compose = _read_env_file(compose_env_path)
    preserved_mfa_workers = _read_env_file(worker_env_path)
    mfa_values_preserved = all(
        hmac.compare_digest(preserved_mfa_values.get(name, ""), value)
        and hmac.compare_digest(preserved_mfa_compose.get(name, ""), value)
        for name, value in mfa_values.items()
    )
    worker_delivery_kek_preserved = hmac.compare_digest(
        preserved_mfa_workers.get("MFA_EMAIL_DELIVERY_KEKS", ""), delivery_ring
    )
    api_only_key_names_remain_absent = all(
        name not in preserved_mfa_workers
        for name in (
            "MFA_EMAIL_OTP_HMAC_KEYS",
            "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID",
            "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID",
        )
    )
    mfa_values_preserved = (
        mfa_values_preserved
        and worker_delivery_kek_preserved
        and api_only_key_names_remain_absent
    )
    assert mfa_values_preserved
    preserved_rings_not_printed = all(
        secret not in (second_result.stdout + second_result.stderr)
        for secret in (
            otp_ring,
            delivery_ring,
            otp_ring.split(":", 1)[1],
            delivery_ring.split(":", 1)[1],
        )
    )
    assert preserved_rings_not_printed

    conflicting_active_id = "conflicting-active-id"
    _write_env_value(
        compose_env_path, "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID", conflicting_active_id
    )
    mismatched_result = _run_prepare(project, state_root, env)
    mismatch_stays_unmodified = hmac.compare_digest(
        _read_env_file(compose_env_path).get("MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID", ""),
        conflicting_active_id,
    )
    docker_rings_unchanged = all(
        hmac.compare_digest(_read_env_file(docker_env_path).get(name, ""), value)
        for name, value in mfa_values.items()
    )
    mismatch_fails_closed = (
        mismatched_result.returncode != 0
        and "refusing to replace key material" in mismatched_result.stderr.lower()
        and mismatch_stays_unmodified
        and docker_rings_unchanged
    )
    mismatched_secrets_not_printed = all(
        secret not in (mismatched_result.stdout + mismatched_result.stderr)
        for secret in (otp_ring, delivery_ring)
    )
    assert mismatch_fails_closed
    assert mismatched_secrets_not_printed
    _write_env_value(
        compose_env_path, "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID", otp_active_id
    )

    _write_env_value(docker_env_path, "MFA_EMAIL_DELIVERY_KEKS", "")
    failed_closed = _run_prepare(project, state_root, env)
    after_invalid = _read_env_file(docker_env_path)
    assert failed_closed.returncode != 0
    assert "refusing to replace key material" in failed_closed.stderr.lower()
    invalid_ring_remains_empty = after_invalid.get("MFA_EMAIL_DELIVERY_KEKS") == ""
    assert invalid_ring_remains_empty
    otp_ring_preserved = hmac.compare_digest(
        after_invalid.get("MFA_EMAIL_OTP_HMAC_KEYS", ""), otp_ring
    )
    assert otp_ring_preserved
    failed_closed_rings_not_printed = all(
        secret not in (failed_closed.stdout + failed_closed.stderr)
        for secret in (
            otp_ring,
            delivery_ring,
            otp_ring.split(":", 1)[1],
            delivery_ring.split(":", 1)[1],
        )
    )
    assert failed_closed_rings_not_printed


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
@pytest.mark.parametrize("invalid_kind", ["short_rotation_entry", "placeholder"])
def test_prepare_only_replaces_invalid_audit_rotation_entries_without_printing(
    tmp_path: Path, invalid_kind: str
) -> None:
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    public, private = _vapid_pair()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root, version=11)), encoding="utf-8"
    )
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    env = _live_environment(state_root, public, private, current_schema=True)
    first_result = _run_prepare(project, state_root, env)
    assert first_result.returncode == 0, "initial PrepareOnly setup failed"

    if invalid_kind == "short_rotation_entry":
        invalid_value = f"short-a-{'a' * 22},short-b-{'b' * 22}"
        assert len(invalid_value) >= 32
        assert all(len(part) < 32 for part in invalid_value.split(","))
    else:
        invalid_value = f"example-{secrets.token_hex(32)}"
    docker_env_path = state_root / ".env.docker"
    _write_env_value(docker_env_path, "AUDIT_LOG_SECRET", invalid_value)

    result = _run_prepare(project, state_root, env)

    generated = _read_env_file(docker_env_path).get("AUDIT_LOG_SECRET", "")
    generated_was_not_printed = generated not in (result.stdout + result.stderr)
    assert result.returncode == 0, "invalid audit-key PrepareOnly setup failed"
    assert len(generated) == 64 and generated.isascii() and generated.isalnum()
    assert generated != invalid_value
    assert "example" not in generated.lower()
    assert generated_was_not_printed
    assert invalid_value not in (result.stdout + result.stderr)
    assert _read_env_file(state_root / ".env").get("AUDIT_LOG_SECRET") == generated
    assert (
        _read_env_file(state_root / ".env.docker.workers").get("AUDIT_LOG_SECRET")
        == generated
    )


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
@pytest.mark.parametrize("port_case", ["missing", "mismatched"])
def test_prepare_only_rejects_unsigned_minio_port_before_environment_writes(
    tmp_path: Path, port_case: str
) -> None:
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    public, private = _vapid_pair()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    marker_path = secrets_root / "live-stand.json"
    marker_path.write_text(
        json.dumps(_owner_marker(project, state_root, version=11)), encoding="utf-8"
    )
    marker_before = marker_path.read_bytes()
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    env = _live_environment(state_root, public, private, current_schema=True)
    if port_case == "missing":
        env.pop("LIVE_HOST_PORT_MINIO")
    else:
        env["LIVE_HOST_PORT_MINIO"] = "32100"

    result = _run_prepare(project, state_root, env)

    assert result.returncode != 0
    expected_error = (
        "PrepareOnly requires a complete, unique live-stand port map."
        if port_case == "missing"
        else "PrepareOnly live-stand ports do not match the signed owner."
    )
    assert expected_error in result.stderr
    assert marker_path.read_bytes() == marker_before
    assert not (state_root / ".env").exists()
    assert not (state_root / ".env.docker").exists()
    assert not (state_root / ".env.docker.workers").exists()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_prepare_only_accepts_python_generated_in_place_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    parent_environment = os.environ.copy()
    project, _ = _fixture_project(tmp_path)
    state_root = (
        tmp_path
        / "temp"
        / "ue-live-acceptance"
        / f"run-prepare-only-{uuid.uuid4().hex}"
    )
    state_root.parent.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location(
        "live_stand_prepare_only_proof", ROOT / "scripts" / "live_stand.py"
    )
    assert spec is not None and spec.loader is not None
    live_stand = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = live_stand
    spec.loader.exec_module(live_stand)
    live_stand.REPO_ROOT = project
    live_stand.WORKTREE = state_root
    live_stand.IN_PLACE_MODE = True
    live_stand.SOURCE_SHA = "a" * 40
    live_stand.docker_daemon_fingerprint = lambda: "d" * 64
    live_stand._ensure_private_state_directory(state_root, protect_new_windows=True)
    owner = live_stand.create_stand_owner(
        state_root,
        published_ports=live_stand.choose_published_ports(),
    )
    vapid = live_stand.load_or_create_vapid(state_root)
    live_stand._write_in_place_compose_override(state_root)
    environment = live_stand.stand_environment(
        vapid, owner.project_name, dict(owner.published_ports)
    )
    environment["TEMP"] = str(state_root.parents[1])
    environment["TMP"] = str(state_root.parents[1])
    if os.name != "nt":
        environment["TMPDIR"] = str(state_root.parents[1])

    result = _run_prepare(project, state_root, environment)

    assert result.returncode == 0, f"PrepareOnly exited with status {result.returncode}"
    assert profile.read_bytes() == sentinel
    assert os.environ == parent_environment
    assert (state_root / ".env").is_file()
    assert (state_root / ".env.docker").is_file()
    assert (state_root / ".env.docker.workers").is_file()
    if os.name == "nt":
        for path in (
            state_root,
            state_root / ".secrets",
            state_root / ".secrets" / "live-stand-owner.key",
            state_root / ".secrets" / "live-stand.json",
            state_root / ".secrets" / "live-vapid.json",
            state_root / "docker-compose.live-state.yml",
            state_root / ".env",
            state_root / ".env.docker",
            state_root / ".env.docker.workers",
            state_root / ".secrets" / "jwt_rs256.pem",
            state_root / ".secrets" / "jwt_rs256.pub.pem",
            state_root / ".secrets" / "temporal_api_key",
        ):
            _assert_windows_private_acl(path)


@pytest.mark.skipif(
    POWERSHELL is None or os.name == "nt",
    reason="requires POSIX permissions and PowerShell 7",
)
def test_launcher_rejects_permissive_owned_state_root_before_secret_reads(
    tmp_path: Path,
) -> None:
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    public, private = _vapid_pair()
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root)), encoding="utf-8"
    )
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    state_root.chmod(0o755)

    result = _run_prepare(
        project,
        state_root,
        _live_environment(state_root, public, private),
    )

    assert result.returncode != 0
    assert "private permissions" in (result.stdout + result.stderr).lower()
    assert not (state_root / ".env").exists()
    assert not (state_root / ".env.docker").exists()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_rejects_compose_without_override_support_before_env_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    parent_environment = os.environ.copy()
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    public, private = _vapid_pair()
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root)), encoding="utf-8"
    )
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "docker-commands.txt"
    if os.name == "nt":
        fake_docker = fake_bin / "docker.cmd"
        fake_docker.write_text(
            "@echo off\r\n"
            '>>"%LIVE_STAND_DOCKER_LOG%" echo %*\r\n'
            'if "%1"=="compose" if "%2"=="version" echo v2.24.3\r\n'
            "exit /b 0\r\n",
            encoding="utf-8",
        )
    else:
        # PowerShell on Unix invokes native executables, not Windows batch files.
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$LIVE_STAND_DOCKER_LOG"\n'
            'if [ "$1" = compose ] && [ "${2:-}" = version ]; then\n'
            '  printf "v2.24.3\\n"\n'
            "fi\nexit 0\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o700)
    env = _live_environment(state_root, public, private)
    env["PATH"] = os.pathsep.join((str(fake_bin), env.get("PATH", "")))
    env["LIVE_STAND_DOCKER_LOG"] = str(command_log)

    assert POWERSHELL is not None
    result = subprocess.run(  # noqa: S603 - fixed PowerShell file and test-owned launcher args
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(project / "start-docker.ps1"),
            "-Build",
            "-ExtraCompose",
            "docker-compose.live.yml",
            "-LiveStandStateRoot",
            str(state_root),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )

    assert result.returncode != 0
    assert "Docker Compose 2.24.4 or newer" in (result.stdout + result.stderr)
    assert command_log.read_text(encoding="utf-8").splitlines() == [
        "info",
        "compose version --short",
    ]
    assert not (state_root / ".env").exists()
    assert not (state_root / ".env.docker").exists()
    assert not (project / ".env").exists()
    assert not (project / ".secrets").exists()
    assert profile.read_bytes() == sentinel
    assert os.environ == parent_environment


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
@pytest.mark.parametrize(
    ("case", "env_name", "mutation"),
    [
        ("duplicate_docker_key", ".env.docker", "duplicate_field"),
        ("duplicate_compose_key", ".env", "duplicate_field"),
        ("duplicate_otp_key_id", ".env.docker", "duplicate_otp_id"),
        ("invalid_otp_base64url", ".env.docker", "invalid_otp_encoding"),
        ("undersized_otp_hmac", ".env.docker", "short_otp_hmac"),
        ("invalid_delivery_kek_length", ".env.docker", "short_delivery_kek"),
    ],
)
def test_prepare_only_rejects_ambiguous_or_malformed_mfa_key_material(
    tmp_path: Path, case: str, env_name: str, mutation: str
) -> None:
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    public, private = _vapid_pair()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root, version=11)), encoding="utf-8"
    )
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    env = _live_environment(state_root, public, private, current_schema=True)

    initial = _run_prepare(project, state_root, env)
    assert initial.returncode == 0, "initial PrepareOnly setup failed"

    docker_env_path = state_root / ".env.docker"
    compose_env_path = state_root / ".env"
    worker_env_path = state_root / ".env.docker.workers"
    docker_values = _read_env_file(docker_env_path)
    otp_ring = docker_values["MFA_EMAIL_OTP_HMAC_KEYS"]
    delivery_ring = docker_values["MFA_EMAIL_DELIVERY_KEKS"]
    otp_key_id, _ = otp_ring.split(":", 1)
    delivery_key_id, _ = delivery_ring.split(":", 1)
    target_path = state_root / env_name
    target_key = (
        "MFA_EMAIL_DELIVERY_KEKS"
        if mutation == "short_delivery_kek"
        else "MFA_EMAIL_OTP_HMAC_KEYS"
    )
    invalid_material = ""

    if mutation == "duplicate_field":
        lines = target_path.read_text(encoding="utf-8").splitlines()
        prefix = f"{target_key}="
        matches = [line for line in lines if line.startswith(prefix)]
        assert len(matches) == 1, "expected one generated MFA key field"
        target_path.write_text("\n".join((*lines, matches[0])) + "\n", encoding="utf-8")
        invalid_material = matches[0].split("=", 1)[1]
    elif mutation == "duplicate_otp_id":
        invalid_material = f"{otp_ring},{otp_ring}"
        _write_env_value(docker_env_path, target_key, invalid_material)
    elif mutation == "invalid_otp_encoding":
        invalid_material = f"{otp_key_id}:!"
        _write_env_value(docker_env_path, target_key, invalid_material)
    elif mutation == "short_otp_hmac":
        encoded = base64.urlsafe_b64encode(bytes(range(31))).decode("ascii").rstrip("=")
        invalid_material = f"{otp_key_id}:{encoded}"
        _write_env_value(docker_env_path, target_key, invalid_material)
    else:
        encoded = base64.urlsafe_b64encode(bytes(range(31))).decode("ascii").rstrip("=")
        invalid_material = f"{delivery_key_id}:{encoded}"
        _write_env_value(docker_env_path, target_key, invalid_material)

    paths = (docker_env_path, compose_env_path, worker_env_path)
    before = {path: path.read_bytes() for path in paths}
    failed = _run_prepare(project, state_root, env)
    after = {path: path.read_bytes() for path in paths}
    combined_output = failed.stdout + failed.stderr

    files_unchanged = all(
        hmac.compare_digest(before[path], after[path]) for path in paths
    )
    key_material_not_printed = all(
        material not in combined_output
        for material in (otp_ring, delivery_ring, invalid_material)
        if material
    )
    assert failed.returncode != 0, f"{case}: malformed configuration was accepted"
    assert "refusing to replace key material" in failed.stderr.lower()
    assert files_unchanged, f"{case}: env files changed after rejected configuration"
    assert key_material_not_printed, f"{case}: key material appeared in command output"
