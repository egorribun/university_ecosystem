"""AUD-313: the owned-stand seed gate verifies an owner-issued record, not env alone."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import live_stand, seed_target
from tests.symlink_support import FILE_SYMLINKS_SUPPORTED

PROJECT = "ue-live-0123456789abcdef"
DATABASE_URL = "postgresql+asyncpg://tester@postgres:5432/demo"


def _owner_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> live_stand.StandOwner:
    worktree = tmp_path / "ue-live"
    (worktree / ".secrets").mkdir(parents=True)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    return live_stand.StandOwner(
        repository=str(tmp_path / "repo"),
        worktree=str(worktree),
        project_name=PROJECT,
        published_ports=(),
        schema_version=1,
    )


def test_written_owner_record_is_readable_by_other_uids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = _owner_for(tmp_path, monkeypatch)

    record_path = live_stand._write_seed_owned_stand_record(owner)

    mode = record_path.stat().st_mode
    assert mode & 0o444 == 0o444
    if os.name == "posix":
        assert stat.S_IMODE(mode) == 0o644


def test_restrictive_umask_still_yields_a_readable_owner_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = _owner_for(tmp_path, monkeypatch)

    previous_umask = os.umask(0o077)
    try:
        record_path = live_stand._write_seed_owned_stand_record(owner)
    finally:
        os.umask(previous_umask)

    mode = record_path.stat().st_mode
    assert mode & 0o444 == 0o444
    if os.name == "posix":
        assert stat.S_IMODE(mode) == 0o644


def _mountinfo_line(path: Path, options: str = "ro,relatime") -> str:
    escaped_path = (
        str(path)
        .replace("\\", r"\134")
        .replace(" ", r"\040")
        .replace("\t", r"\011")
        .replace("\n", r"\012")
    )
    return f"42 1 8:1 /source {escaped_path} {options} - ext4 /dev/root rw"


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": 1,
        "project_name": PROJECT,
        "database_host": "postgres",
    }
    record.update(overrides)
    return record


@pytest.fixture
def stand_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Set the env flags an attacker or stale shell could export, plus a record path."""
    monkeypatch.delenv("UE_SEED_TARGET", raising=False)
    monkeypatch.setenv("LIVE_STAND_SEED_PROJECT", PROJECT)
    monkeypatch.setenv("LIVE_STAND_OWNER_VERIFIED", "1")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", PROJECT)
    monkeypatch.setattr(seed_target, "_configured_database_url", lambda: DATABASE_URL)
    record_path = tmp_path / "owned-stand.json"
    monkeypatch.setattr(seed_target, "OWNED_STAND_RECORD_PATH", record_path)
    monkeypatch.setattr(
        seed_target,
        "_read_mountinfo_text",
        lambda: _mountinfo_line(record_path),
    )
    return record_path


def _write_record(path: Path, record: object) -> None:
    path.write_text(json.dumps(record), encoding="utf-8")


def test_env_flags_alone_are_refused_without_the_owner_record(
    stand_environment: Path,
) -> None:
    assert not stand_environment.exists()

    with pytest.raises(RuntimeError, match="owner-issued live stand record"):
        seed_target.require_owned_live_stand_target()


def test_matching_owner_record_accepts_the_owned_stand(
    stand_environment: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_record(stand_environment, _record())

    assert seed_target.require_owned_live_stand_target() == PROJECT
    # The hosted AUD-313 evidence line the focused live workflow counts.
    assert capsys.readouterr().out == (
        f"AUD-313 seed target verified for {PROJECT}: "
        "owner record is one exact read-only mount\n"
    )


def test_matching_ordinary_file_is_refused_without_exact_readonly_mount(
    stand_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_record(stand_environment, _record())
    monkeypatch.setattr(seed_target, "_read_mountinfo_text", lambda: "")

    with pytest.raises(RuntimeError, match="owner-issued live stand record"):
        seed_target.require_owned_live_stand_target()
    # A refused target never prints the evidence line.
    assert "AUD-313 seed target verified" not in capsys.readouterr().out


def test_record_mount_must_be_exact_unique_and_read_only(
    stand_environment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exact_readonly = _mountinfo_line(stand_environment)
    parent_readonly = _mountinfo_line(stand_environment.parent)
    exact_writable = _mountinfo_line(stand_environment, "rw,relatime")

    monkeypatch.setattr(seed_target, "_read_mountinfo_text", lambda: exact_readonly)
    assert seed_target._has_exact_readonly_mount(stand_environment)

    for mountinfo in (
        parent_readonly,
        exact_writable,
        f"{exact_readonly}\n{exact_writable}",
    ):
        monkeypatch.setattr(
            seed_target, "_read_mountinfo_text", lambda text=mountinfo: text
        )
        assert not seed_target._has_exact_readonly_mount(stand_environment)


@pytest.mark.parametrize(
    "record",
    [
        _record(project_name="ue-live-fedcba9876543210"),
        _record(database_host="remote-db"),
        _record(schema_version=2),
        _record(schema_version=True),
        {"schema_version": 1, "project_name": PROJECT},
        _record(extra="unexpected"),
        ["not", "an", "object"],
        "plain text",
    ],
)
def test_record_must_match_project_host_and_schema_exactly(
    stand_environment: Path, record: object
) -> None:
    _write_record(stand_environment, record)

    with pytest.raises(RuntimeError):
        seed_target.require_owned_live_stand_target()


def test_malformed_json_record_is_refused(stand_environment: Path) -> None:
    stand_environment.write_text("{not json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="owner-issued live stand record"):
        seed_target.require_owned_live_stand_target()


def test_oversized_record_is_refused_before_it_is_parsed(
    stand_environment: Path,
) -> None:
    padding = "x" * seed_target.OWNED_STAND_RECORD_MAX_BYTES
    stand_environment.write_text(
        json.dumps({**_record(), "padding": padding}), encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="owner-issued live stand record"):
        seed_target.require_owned_live_stand_target()


def test_directory_in_place_of_the_record_is_refused(stand_environment: Path) -> None:
    stand_environment.mkdir()

    with pytest.raises(RuntimeError, match="owner-issued live stand record"):
        seed_target.require_owned_live_stand_target()


@pytest.mark.skipif(
    not FILE_SYMLINKS_SUPPORTED, reason="native file symlink privilege unavailable"
)
def test_symlinked_record_is_refused(stand_environment: Path, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.json"
    _write_record(target, _record())
    stand_environment.symlink_to(target)

    with pytest.raises(RuntimeError, match="owner-issued live stand record"):
        seed_target.require_owned_live_stand_target()


def test_database_host_still_must_be_the_compose_postgres_service(
    stand_environment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_record(stand_environment, _record())
    monkeypatch.setattr(
        seed_target,
        "_configured_database_url",
        lambda: "postgresql+asyncpg://tester@remote-db:5432/demo",
    )

    with pytest.raises(RuntimeError, match="postgres service"):
        seed_target.require_owned_live_stand_target()


def test_admin_smoke_target_does_not_read_the_owned_stand_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("UE_SEED_TARGET", seed_target.ADMIN_SMOKE_TARGET)
    monkeypatch.setattr(
        seed_target, "OWNED_STAND_RECORD_PATH", tmp_path / "must-not-be-read.json"
    )
    monkeypatch.setattr(
        seed_target,
        "_require_admin_smoke_target",
        lambda: seed_target.ADMIN_SMOKE_PROJECT,
    )

    assert seed_target.require_owned_live_stand_target() == "ci-admin-smoke"


@pytest.mark.parametrize(
    "tamper_after_first_run", [False, True], ids=["before-seed", "between-scripts"]
)
def test_seed_rechecks_signed_owner_before_issuing_or_reusing_unsigned_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tamper_after_first_run: bool
) -> None:
    repository = tmp_path / "repository"
    worktree = repository / "stand"
    worktree.mkdir(parents=True)
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(
        live_stand, "_owner_signing_key", lambda *, create: bytes(range(32))
    )
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "d" * 64)
    ports = {
        name: 30000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    owner = live_stand.create_stand_owner(worktree, published_ports=ports)
    owner = live_stand._write_stand_owner_update(
        worktree,
        replace(
            owner,
            compose_resource_fingerprint="e" * 64,
            service_roots=("backend",),
            selected_services=("backend",),
        ),
    )
    assert live_stand.load_stand_owner(worktree) == owner
    marker_path = worktree / live_stand.STAND_FILE
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert "signature" in marker

    def tamper_with_signed_project() -> None:
        changed = dict(marker)
        changed["project_name"] = (
            PROJECT if owner.project_name != PROJECT else "ue-live-fedcba9876543210"
        )
        marker_path.write_text(json.dumps(changed), encoding="utf-8")

    evidence = live_stand.ComposeResourceEvidence(
        fingerprint="e" * 64,
        managed_volumes=(),
        service_roots=("backend",),
        selected_services=("backend",),
    )
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda *_a: None)
    monkeypatch.setattr(live_stand, "stand_environment", lambda *_a: {})
    monkeypatch.setattr(live_stand, "load_vapid", lambda _path: {})
    monkeypatch.setattr(
        live_stand, "_owner_compose_resource_evidence", lambda *_a, **_kw: evidence
    )
    monkeypatch.setattr(
        live_stand, "_assert_compose_volume_ownership", lambda *_a, **_kw: None
    )
    runs: list[list[str]] = []

    def run_seed(command: list[str], **_kwargs: object) -> None:
        runs.append(command)
        record_path = worktree / live_stand.SEED_OWNED_STAND_RECORD
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record == _record(project_name=owner.project_name)
        assert "signature" not in record
        assert (
            f"{record_path}:{live_stand.SEED_OWNED_STAND_CONTAINER_PATH}:ro" in command
        )
        with monkeypatch.context() as seed:
            seed.delenv("UE_SEED_TARGET", raising=False)
            for index, argument in enumerate(command[:-1]):
                if argument == "--env" and "=" in command[index + 1]:
                    name, value = command[index + 1].split("=", 1)
                    seed.setenv(name, value)
            seed.setattr(seed_target, "OWNED_STAND_RECORD_PATH", record_path)
            seed.setattr(
                seed_target,
                "_read_mountinfo_text",
                lambda: _mountinfo_line(record_path),
            )
            seed.setattr(seed_target, "_configured_database_url", lambda: DATABASE_URL)
            assert seed_target.require_owned_live_stand_target() == owner.project_name
        tamper_with_signed_project()

    monkeypatch.setattr(live_stand, "_run", run_seed)
    if not tamper_after_first_run:
        tamper_with_signed_project()

    with pytest.raises(live_stand.StandError, match="signature is invalid"):
        live_stand._seed_locked("fixture-password", owner=owner)

    assert len(runs) == int(tamper_after_first_run)
    assert not (worktree / live_stand.SEED_OWNED_STAND_RECORD).exists()


def test_seed_writes_record_for_each_run_and_removes_it_afterwards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    (worktree / ".secrets").mkdir(parents=True)
    owner = live_stand.StandOwner(
        repository=str(tmp_path / "repo"),
        worktree=str(worktree),
        project_name=PROJECT,
        published_ports=(),
        schema_version=1,
    )
    seen_mounts: list[str] = []
    record_during_runs: list[dict[str, object]] = []

    def capture(command: list[str], **_kwargs: object) -> None:
        mounts = [
            command[index + 1]
            for index, token in enumerate(command)
            if token == "-v" and index + 1 < len(command)
        ]
        seen_mounts.extend(mounts)
        mount = next(
            mount
            for mount in mounts
            if mount.endswith(f":{live_stand.SEED_OWNED_STAND_CONTAINER_PATH}:ro")
        )
        host_path = Path(
            mount.rsplit(f":{live_stand.SEED_OWNED_STAND_CONTAINER_PATH}")[0]
        )
        record_during_runs.append(json.loads(host_path.read_text(encoding="utf-8")))

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
    monkeypatch.setattr(
        live_stand, "_require_owned_docker_daemon", lambda *_a, **_k: None
    )
    monkeypatch.setattr(live_stand, "stand_environment", lambda *_a: {})
    monkeypatch.setattr(live_stand, "load_vapid", lambda _path: {})
    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", lambda *_a: None
    )
    monkeypatch.setattr(live_stand, "_run", capture)

    live_stand._seed_locked("fixture-password", owner=replace(owner))

    expected_record = {
        "schema_version": 1,
        "project_name": PROJECT,
        "database_host": "postgres",
    }
    assert len(record_during_runs) == len(live_stand.SEED_SCRIPTS)
    assert all(record == expected_record for record in record_during_runs)
    assert all(
        mount.endswith(f":{live_stand.SEED_OWNED_STAND_CONTAINER_PATH}:ro")
        for mount in seen_mounts
        if live_stand.SEED_OWNED_STAND_CONTAINER_PATH in mount
    )
    assert not (worktree / live_stand.SEED_OWNED_STAND_RECORD).exists()


def test_seed_removes_record_even_when_a_seed_run_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    (worktree / ".secrets").mkdir(parents=True)
    owner = live_stand.StandOwner(
        repository=str(tmp_path / "repo"),
        worktree=str(worktree),
        project_name=PROJECT,
        published_ports=(),
        schema_version=1,
    )

    def fail(*_args: object, **_kwargs: object) -> None:
        raise live_stand.StandError("seed failed")

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
    monkeypatch.setattr(
        live_stand, "_require_owned_docker_daemon", lambda *_a, **_k: None
    )
    monkeypatch.setattr(live_stand, "stand_environment", lambda *_a: {})
    monkeypatch.setattr(live_stand, "load_vapid", lambda _path: {})
    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", lambda *_a: None
    )
    monkeypatch.setattr(live_stand, "_run", fail)

    with pytest.raises(live_stand.StandError, match="seed failed"):
        live_stand._seed_locked("fixture-password", owner=owner)

    assert not (worktree / live_stand.SEED_OWNED_STAND_RECORD).exists()
