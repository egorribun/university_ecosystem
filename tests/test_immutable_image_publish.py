from __future__ import annotations

import importlib.util
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quality" / "publish_immutable_image.py"
LOCAL_REF = "university-ecosystem/backend:scan-" + "a" * 40
SUBJECT = "ghcr.io/egorribun/university_ecosystem/backend"
FINAL_REF = SUBJECT + ":" + "a" * 40
LOCAL_ID = "sha256:" + "1" * 64
DIGEST = "sha256:" + "2" * 64


def _load_script() -> ModuleType:
    assert SCRIPT.is_file(), "immutable image publisher is required"
    spec = importlib.util.spec_from_file_location("immutable_image_publish", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDocker:
    def __init__(
        self,
        remote_lookups: Sequence[subprocess.CompletedProcess[str]],
        *,
        remote_image_id: str = LOCAL_ID,
    ) -> None:
        self.remote_lookups = list(remote_lookups)
        self.remote_image_id = remote_image_id
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        normalized = tuple(command)
        self.commands.append(normalized)
        if normalized[:4] == (
            "docker",
            "buildx",
            "imagetools",
            "inspect",
        ):
            assert self.remote_lookups
            return self.remote_lookups.pop(0)
        if normalized[:3] == ("docker", "image", "inspect"):
            image_id = LOCAL_ID if normalized[-1] == LOCAL_REF else self.remote_image_id
            return _result(stdout=image_id + "\n")
        if normalized[:2] in {
            ("docker", "pull"),
            ("docker", "tag"),
            ("docker", "push"),
        }:
            return _result()
        raise AssertionError(f"unexpected command: {normalized!r}")


def _result(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _lookup(digest: str = DIGEST) -> subprocess.CompletedProcess[str]:
    return _result(stdout=f'"{digest}"\n')


def _missing(message: str = "manifest unknown") -> subprocess.CompletedProcess[str]:
    return _result(returncode=1, stderr=message)


def _publish(module: ModuleType, runner: Callable[[Sequence[str]], object]) -> str:
    return module.publish_immutable_image(
        final_ref=FINAL_REF,
        local_ref=LOCAL_REF,
        subject_name=SUBJECT,
        runner=runner,
    )


def test_existing_identical_tag_is_reused_without_push() -> None:
    module = _load_script()
    docker = FakeDocker([_lookup()])

    assert _publish(module, docker) == DIGEST
    assert not any(command[:2] == ("docker", "push") for command in docker.commands)
    assert not any(command[:2] == ("docker", "tag") for command in docker.commands)


def test_existing_different_tag_fails_before_push() -> None:
    module = _load_script()
    docker = FakeDocker([_lookup()], remote_image_id="sha256:" + "3" * 64)

    with pytest.raises(module.PublicationError, match="different image content"):
        _publish(module, docker)

    assert not any(command[:2] == ("docker", "push") for command in docker.commands)


@pytest.mark.parametrize(
    "diagnostic",
    [
        "unauthorized: authentication required",
        "dial tcp: network is unreachable",
        "unexpected status from HEAD request: 500 Internal Server Error",
        "unauthorized: authentication required; manifest unknown",
    ],
)
def test_lookup_auth_network_and_server_errors_fail_closed(diagnostic: str) -> None:
    module = _load_script()
    docker = FakeDocker([_missing(diagnostic)])

    with pytest.raises(module.PublicationError, match="remote tag lookup failed"):
        _publish(module, docker)

    assert not any(command[:2] == ("docker", "push") for command in docker.commands)


def test_manifest_404_then_identical_race_reuses_without_push() -> None:
    module = _load_script()
    missing = _missing(
        "unexpected status from HEAD request to "
        "https://ghcr.io/v2/owner/repo/manifests/tag: 404 Not Found"
    )
    docker = FakeDocker([missing, _lookup()])

    assert _publish(module, docker) == DIGEST
    assert not any(command[:2] == ("docker", "push") for command in docker.commands)


def test_manifest_unknown_create_path_reverifies_pushed_digest_and_content() -> None:
    module = _load_script()
    docker = FakeDocker([_missing(), _missing(), _lookup()])

    assert _publish(module, docker) == DIGEST
    assert sum(command[:2] == ("docker", "push") for command in docker.commands) == 1
    assert ("docker", "pull", f"{SUBJECT}@{DIGEST}") in docker.commands


def test_race_to_different_content_and_post_push_mismatch_fail_closed() -> None:
    module = _load_script()
    raced = FakeDocker([_missing(), _lookup()], remote_image_id="sha256:" + "4" * 64)
    with pytest.raises(module.PublicationError, match="different image content"):
        _publish(module, raced)
    assert not any(command[:2] == ("docker", "push") for command in raced.commands)

    post_push = FakeDocker(
        [_missing(), _missing(), _lookup()],
        remote_image_id="sha256:" + "5" * 64,
    )
    with pytest.raises(module.PublicationError, match="different image content"):
        _publish(module, post_push)
    assert sum(command[:2] == ("docker", "push") for command in post_push.commands) == 1
