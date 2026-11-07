"""Require the mature Alpine backports for CVE-2026-107891 in final images."""

import shlex
from pathlib import Path

import pytest

from tests.test_runtime_zlib_security_pin import (
    ARCHIVE_BRANCHES,
    _assert_runtime_zlib_pin,
    _runtime_runs,
)

ROOT = Path(__file__).resolve().parents[1]
MUSL_VERSIONS = {"3.24": "1.2.6-r3", "3.23": "1.2.5-r24"}
DOCKER_FILES = (ROOT / "services/caddy/Dockerfile", ROOT / "frontend.Dockerfile")


def _assert_runtime_musl_pins(source: str, branch: str) -> None:
    # Reuse the exact, fail-closed signed-archive install contract. This rejects
    # fake installs, unsafe APK options, later downgrades and alternate roots.
    _assert_runtime_zlib_pin(source, branch)
    install = next(run for run in _runtime_runs(source) if "&& apk add " in run)
    packages = shlex.split(
        install.split("&& apk add --no-cache ", 1)[1].split(" && ", 1)[0]
    )
    for package in ("musl", "musl-utils"):
        assert [pin for pin in packages if pin.split("=", 1)[0] == package] == [
            f"{package}={MUSL_VERSIONS[branch]}"
        ], "install both exact musl backports for the runtime Alpine branch"


@pytest.mark.parametrize(
    "dockerfile", DOCKER_FILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
def test_final_runtime_installs_both_fixed_musl_packages(dockerfile: Path) -> None:
    _assert_runtime_musl_pins(
        dockerfile.read_text(encoding="utf-8"),
        ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()],
    )


@pytest.mark.parametrize(
    "dockerfile", DOCKER_FILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
@pytest.mark.parametrize("package", ["musl", "musl-utils"])
@pytest.mark.parametrize(
    "replacement",
    ["missing", "unversioned", "vulnerable", "wrong-branch", "mutable", "duplicate"],
)
def test_musl_contract_rejects_missing_or_wrong_version(
    dockerfile: Path, package: str, replacement: str
) -> None:
    source = dockerfile.read_text(encoding="utf-8")
    branch = ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()]
    pin = f"{package}={MUSL_VERSIONS[branch]}"
    substitutions = {
        "missing": "",
        "unversioned": package,
        "vulnerable": f"{package}=" + {"3.24": "1.2.6-r2", "3.23": "1.2.5-r23"}[branch],
        "wrong-branch": f"{package}="
        + MUSL_VERSIONS[{"3.24": "3.23", "3.23": "3.24"}[branch]],
        "mutable": f"{package}>={MUSL_VERSIONS[branch]}",
        "duplicate": f"{pin} {pin}",
    }
    assert source.count(pin) == 1
    with pytest.raises(AssertionError):
        _assert_runtime_musl_pins(
            source.replace(pin, substitutions[replacement]), branch
        )


@pytest.mark.parametrize(
    "dockerfile", DOCKER_FILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
@pytest.mark.parametrize("location", ["builder", "comment", "echo"])
def test_musl_contract_rejects_pins_outside_install(
    dockerfile: Path, location: str
) -> None:
    source = dockerfile.read_text(encoding="utf-8")
    branch = ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()]
    pins = [f"{package}={MUSL_VERSIONS[branch]}" for package in ("musl", "musl-utils")]
    for pin in pins:
        source = source.replace(pin, "")
    fake = {
        "builder": "FROM node AS fake\nRUN apk add --no-cache " + " ".join(pins) + "\n",
        "comment": "# " + " ".join(pins) + "\n",
        "echo": "RUN echo '" + " ".join(pins) + "'\n",
    }[location]
    altered = fake + source if location == "builder" else source + "\n" + fake
    with pytest.raises(AssertionError):
        _assert_runtime_musl_pins(altered, branch)
