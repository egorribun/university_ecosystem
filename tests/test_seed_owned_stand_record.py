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
    stand_environment: Path,
) -> None:
    _write_record(stand_environment, _record())

    assert seed_target.require_owned_live_stand_target() == PROJECT


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
