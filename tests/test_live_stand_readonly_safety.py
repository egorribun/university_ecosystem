from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import live_stand


def test_status_does_not_recreate_missing_owner_key_or_touch_stand_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repo"
    git_metadata = repository / ".git"
    git_metadata.mkdir(parents=True)
    worktree = tmp_path / live_stand.WORKTREE_NAME
    worktree.mkdir()
    (worktree / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git", lambda *_args: ".git")
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "a" * 64)
    published_ports = {
        name: live_stand.PORT_RANGE[0] + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    live_stand.create_stand_owner(worktree, published_ports=published_ports)

    owner_key = git_metadata / "live-stand-owner.key"
    assert owner_key.is_file()
    owner_key.unlink()

    env_file = worktree / ".env"
    env_file.write_text("LIVE_STAND_SENTINEL=keep\n", encoding="utf-8")
    env_docker_file = worktree / ".env.docker"
    env_docker_file.write_text("LIVE_TEST_VOLUME=owned-data\n", encoding="utf-8")
    marker = worktree / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    env_before = env_file.read_bytes()
    env_docker_before = env_docker_file.read_bytes()
    vapid_file = worktree / live_stand.VAPID_FILE
    vapid_file.write_text(
        json.dumps({"public": "synthetic-public", "private": "synthetic-private"}),
        encoding="utf-8",
    )
    vapid_before = vapid_file.read_bytes()
    password_file = worktree / live_stand.ADMIN_PASSWORD_FILE
    password_file.write_text(
        json.dumps({"password": "synthetic-password"}),  # pragma: allowlist secret
        encoding="utf-8",
    )
    password_before = password_file.read_bytes()

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("read-only status must not query Docker or generate keys")

    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", forbidden)
    monkeypatch.setattr(live_stand, "generate_vapid_keys", forbidden)
    monkeypatch.setattr(live_stand, "_run", forbidden)

    assert live_stand.main(["status"]) == 2
    assert "missing live stand owner key" in capsys.readouterr().err
    assert not owner_key.exists()
    assert marker.read_bytes() == marker_before
    assert env_file.read_bytes() == env_before
    assert env_docker_file.read_bytes() == env_docker_before
    assert vapid_file.read_bytes() == vapid_before
    assert password_file.read_bytes() == password_before
