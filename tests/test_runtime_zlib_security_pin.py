"""Keep the CVE-2026-85091 backport in both final production images."""

import re
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = (ROOT / "services/caddy/Dockerfile", ROOT / "frontend.Dockerfile")
ZLIB_PIN = "zlib=1.3.2-r1"
ARCHIVE_BRANCHES = {"services/caddy/Dockerfile": "3.23", "frontend.Dockerfile": "3.24"}
# SHA256 of the official, signed October 6 backports, not the moving APKINDEX.
ARCHIVE_SHA256 = {
    "3.23": {
        "x86_64": "ee62e1864c235901e2aa4d1868c7ae8f7cc5d0740a98c48a2525332eb4bfda73",
        "aarch64": "82d52fa82a46c73aae8b9f95d7f31a196137f3ce4a000980cdbbfc05c245e7bf",
    },
    "3.24": {
        "x86_64": "63aeea03c15a2f9018f81805cfc8aa926bdf5cd68921f22149c2fbb5d0ee9f47",
        "aarch64": "1f77a542ac6634761b9fe38d8bdca19b154071dcfa25432e73f2bc8a0740a33f",
    },
}


def _archive_prefix(branch: str) -> str:
    hashes = ARCHIVE_SHA256[branch]
    return (
        'RUN zlib_arch="$(apk --print-arch)"'
        ' && case "$zlib_arch" in'
        f' x86_64) zlib_sha256="{hashes["x86_64"]}" ;;'
        f' aarch64) zlib_sha256="{hashes["aarch64"]}" ;;'
        ' *) echo "Unsupported zlib architecture: $zlib_arch" >&2; exit 1 ;;'
        " esac"
        " && wget -q -O /tmp/zlib.apk"
        f' "https://dl-cdn.alpinelinux.org/alpine/v{branch}/main/'
        '${zlib_arch}/zlib-1.3.2-r1.apk"'
        " && printf '%s  %s\\n' \"$zlib_sha256\" /tmp/zlib.apk | sha256sum -c -"
    )


def _runtime_runs(source: str) -> list[str]:
    runtime = re.split(r"(?im)^FROM[ \t]+", source)[-1]
    runtime = re.sub(r"[ \t]*\\\r?\n[ \t]*", " ", runtime)
    return [line for line in runtime.splitlines() if line.startswith("RUN ")]


def _assert_runtime_zlib_pin(source: str, archive_branch: str | None = None) -> None:
    """Require the repository's single, fail-closed runtime APK install form."""
    stages = re.split(r"(?im)^FROM[ \t]+", source)
    assert len(stages) > 1, "missing Docker runtime stage"
    runtime = re.sub(r"[ \t]*\\\r?\n[ \t]*", " ", stages[-1])
    if archive_branch is not None:
        # The shell prelude is intentionally exact. Do not generalize this into
        # a permissive shell parser or bless a different download/checksum flow.
        prefix = _archive_prefix(archive_branch)
        archive_runs = [
            line for line in runtime.splitlines() if line.startswith(prefix)
        ]
        assert len(archive_runs) == 1, "require the reviewed signed-archive prelude"
        archive_run = archive_runs[0]
        assert archive_run.startswith(prefix + " && apk ")
        assert archive_run.count("&& rm /tmp/zlib.apk") == 1, (
            "remove the verified archive"
        )
        runtime = runtime.replace(archive_run, "RUN " + archive_run[len(prefix) + 4 :])
    installs: list[list[str]] = []
    user_selected = False
    for line in runtime.splitlines():
        line = line.lstrip()
        if re.match(r"(?i)^USER[ \t]+", line):
            user_selected = True
        if not re.match(r"(?i)^RUN[ \t]+", line):
            continue
        lexer = shlex.shlex(line[4:], posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
        if "apk" not in tokens:
            continue
        # This is a deliberately narrow source contract, not a shell evaluator.
        # Only && chains preserve installation failure as the RUN exit status.
        assert not user_selected, "APK installation must precede USER"
        assert all(
            not re.fullmatch(r"[();<>|&]+", token) or token == "&&" for token in tokens
        ), "APK install must use a fail-closed && chain"
        command: list[str] = []
        for token in [*tokens, "&&"]:
            if token == "&&":
                if "apk" in command:
                    if command == ["apk", "update"]:
                        assert not installs, "APK updates must precede installation"
                    else:
                        assert command[:3] == ["apk", "add", "--no-cache"], (
                            "use only apk add --no-cache with the exact zlib backport"
                        )
                        packages = command[3:]
                        if archive_branch is not None:
                            assert (
                                " ".join(packages[-2:]) == "zlib=1.3.2-r1 /tmp/zlib.apk"
                            ), (
                                "install the verified local archive, not only the moving index"
                            )
                            packages = packages[:-1]
                        assert packages and all(
                            re.fullmatch(
                                r"[a-z0-9][a-z0-9+_.-]*=[0-9][a-zA-Z0-9+_.-]*", package
                            )
                            for package in packages
                        ), (
                            "install only exact package pins, including the exact zlib backport"
                        )
                        installs.append(packages)
                command = []
            else:
                command.append(token)
    assert len(installs) == 1, "final runtime must install the exact zlib backport once"
    assert installs[0].count(ZLIB_PIN) == 1, (
        "final runtime must install the exact zlib backport"
    )
    assert [package for package in installs[0] if package.startswith("zlib=")] == [
        ZLIB_PIN
    ], "do not introduce a second zlib package selection"


@pytest.mark.parametrize(
    "dockerfile", DOCKERFILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
def test_final_production_image_installs_fixed_zlib(dockerfile: Path) -> None:
    _assert_runtime_zlib_pin(
        dockerfile.read_text(encoding="utf-8"),
        ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()],
    )


@pytest.mark.parametrize(
    "dockerfile", DOCKERFILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
@pytest.mark.parametrize("replacement", ["zlib=1.3.2-r0", "zlib", "zlib>=1.3.2-r1", ""])
def test_runtime_contract_rejects_vulnerable_or_mutable_zlib(
    dockerfile: Path, replacement: str
) -> None:
    source = dockerfile.read_text(encoding="utf-8")
    assert source.count(ZLIB_PIN) == 1
    with pytest.raises(AssertionError):
        _assert_runtime_zlib_pin(
            source.replace(ZLIB_PIN, replacement),
            ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()],
        )


@pytest.mark.parametrize(
    "source",
    [
        "FROM node AS base\nRUN apk add --no-cache zlib=1.3.2-r1\nFROM node AS runtime\n",
        "FROM node\n# RUN apk add --no-cache zlib=1.3.2-r1\n",
        'FROM node\nRUN echo "apk add --no-cache zlib=1.3.2-r1"\n',
        "FROM node\nUSER 10001:10001\nRUN apk add --no-cache zlib=1.3.2-r1\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1 || true\n",
        "FROM node\nRUN apk add --no-cache --allow-untrusted zlib=1.3.2-r1\n",
        "FROM node\nRUN apk add zlib=1.3.2-r1\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1; true\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1 | cat\n",
        "FROM node\nRUN apk add --no-cache --simulate zlib=1.3.2-r1\n",
        "FROM node\nRUN apk add --no-cache -s zlib=1.3.2-r1\n",
        "FROM node\nRUN apk add --no-cache --root /tmp/apk-root zlib=1.3.2-r1\n",
        "FROM node\nRUN apk --root /tmp/apk-root add --no-cache zlib=1.3.2-r1\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1\nRUN apk add --no-cache zlib=1.3.2-r0\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1 && apk add --no-cache zlib=1.3.2-r0\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1\nUSER 0\nRUN apk add --no-cache zlib=1.3.2-r0\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1\nRUN apk del zlib\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1\nRUN apk upgrade\n",
        "FROM node\nRUN apk add --no-cache zlib=1.3.2-r1 zlib=1.3.2-r0\n",
    ],
    ids=[
        "builder-only",
        "comment",
        "echo",
        "after-user",
        "fail-open",
        "untrusted",
        "cached",
        "masked-by-semicolon",
        "masked-by-pipeline",
        "simulate",
        "simulate-short-option",
        "alternate-root",
        "alternate-root-global-option",
        "later-downgrade",
        "chained-downgrade",
        "downgrade-after-user",
        "later-remove",
        "later-unpinned-upgrade",
        "conflicting-zlib-selection",
    ],
)
def test_runtime_contract_rejects_ineffective_or_unsafe_installs(source: str) -> None:
    with pytest.raises(AssertionError):
        _assert_runtime_zlib_pin(source)


@pytest.mark.parametrize(
    "run",
    [
        "RUN apk add --no-cache 'zlib=1.3.2-r1'",
        "RUN apk update && apk add --no-cache zlib=1.3.2-r1 && echo done",
        "RUN apk add --no-cache \\\n  zlib=1.3.2-r1 \\\n  curl=8.23.0-r0",
    ],
    ids=["quoted-pin", "chained-install", "multiline-install"],
)
def test_runtime_contract_accepts_repository_install_forms(run: str) -> None:
    _assert_runtime_zlib_pin(f"FROM node AS runtime\n{run}\nUSER 10001:10001\n")


@pytest.mark.parametrize(
    "dockerfile", DOCKERFILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("https://dl-cdn.alpinelinux.org", "http://dl-cdn.alpinelinux.org"),
        ("dl-cdn.alpinelinux.org", "untrusted.example"),
        ("/main/", "/community/"),
        ("zlib-1.3.2-r1.apk", "zlib-1.3.2-r0.apk"),
        ("$(apk --print-arch)", "x86_64"),
        ("exit 1 ;;", "exit 0 ;;"),
        ("wget -q -O", "wget -q --no-check-certificate -O"),
        ("wget -q -O", "wget -O"),
        ("| sha256sum -c -", "| cat"),
        ("| sha256sum -c -", "| sha256sum -c - || true"),
        ("&& apk add --no-cache", "; apk add --no-cache"),
        ("zlib=1.3.2-r1", "zlib=1.3.2-r1 --allow-untrusted"),
        ("zlib=1.3.2-r1", "zlib=1.3.2-r1 --simulate"),
        ("zlib=1.3.2-r1", "zlib=1.3.2-r1 --root /tmp/other"),
        ("zlib=1.3.2-r1 /tmp/zlib.apk", "zlib=1.3.2-r1 /tmp/other.apk"),
        ("&& rm /tmp/zlib.apk", "&& true"),
    ],
)
def test_runtime_archive_contract_rejects_unsafe_changes(
    dockerfile: Path, old: str, new: str
) -> None:
    source = dockerfile.read_text(encoding="utf-8")
    assert old in source
    with pytest.raises(AssertionError):
        _assert_runtime_zlib_pin(
            source.replace(old, new),
            ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()],
        )


@pytest.mark.parametrize(
    "dockerfile", DOCKERFILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
@pytest.mark.parametrize("failure", ["", "wget", "sha256sum", "install"])
@pytest.mark.parametrize("arch", ["x86_64", "aarch64", "unsupported"])
def test_runtime_archive_shell_fails_closed(
    dockerfile: Path, failure: str, arch: str, tmp_path: Path
) -> None:
    source = dockerfile.read_text(encoding="utf-8")
    branch = ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()]
    run = next(
        line[4:]
        for line in _runtime_runs(source)
        if line.startswith(_archive_prefix(branch))
    )
    log = tmp_path / "commands.log"
    for command in ("apk", "wget", "sha256sum", "rm", "addgroup", "adduser", "chown"):
        script = tmp_path / command
        script.write_text(
            "#!/bin/sh\n"
            f"command={command}\n"
            'printf "%s %s\\n" "$command" "$*" >> "$COMMAND_LOG"\n'
            'if [ "$command $*" = "apk --print-arch" ]; then printf "%s\\n" "$TEST_ARCH"; exit 0; fi\n'
            'if [ "$command" = sha256sum ]; then\n'
            "  IFS= read -r checksum\n"
            '  [ "$checksum" = "$EXPECTED_SHA256  /tmp/zlib.apk" ] || exit 1\n'
            "fi\n"
            '[ "$command" != "$FAILURE" ] || exit 1\n'
            'if [ "$command" = apk ] && [ "$1" = add ] && [ "$FAILURE" = install ]; then exit 1; fi\n'
        )
        script.chmod(0o755)
    _assert_runtime_zlib_pin(source, branch)
    result = subprocess.run(
        ["/bin/sh"],
        input=run,
        env={
            "PATH": str(tmp_path),
            "COMMAND_LOG": str(log),
            "TEST_ARCH": arch,
            "EXPECTED_SHA256": ARCHIVE_SHA256[branch].get(arch, ""),
            "FAILURE": failure,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    commands = log.read_text(encoding="utf-8").splitlines()
    if arch == "unsupported":
        assert result.returncode != 0
        assert commands == ["apk --print-arch"]
    elif failure:
        assert result.returncode != 0
        assert not any(command.startswith("rm ") for command in commands)
        if failure in {"wget", "sha256sum"}:
            assert not any(command.startswith("apk add ") for command in commands)
    else:
        assert result.returncode == 0, result.stderr
        assert commands[1] == (
            "wget -q -O /tmp/zlib.apk https://dl-cdn.alpinelinux.org/alpine/"
            f"v{branch}/main/{arch}/zlib-1.3.2-r1.apk"
        )
        install = next(
            command for command in commands if command.startswith("apk add ")
        )
        assert "zlib=1.3.2-r1 /tmp/zlib.apk" in install
        assert commands.index("sha256sum -c -") < commands.index(install)
        assert commands.index(install) < commands.index("rm /tmp/zlib.apk")


@pytest.mark.parametrize(
    "dockerfile", DOCKERFILES, ids=lambda path: path.relative_to(ROOT).as_posix()
)
@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
def test_runtime_archive_rejects_changed_integrity_or_branch(
    dockerfile: Path, arch: str
) -> None:
    source = dockerfile.read_text(encoding="utf-8")
    branch = ARCHIVE_BRANCHES[dockerfile.relative_to(ROOT).as_posix()]
    for altered in (
        source.replace(ARCHIVE_SHA256[branch][arch], "0" * 64),
        source.replace(f"/alpine/v{branch}/", "/alpine/edge/"),
        source.replace("zlib=1.3.2-r1 /tmp/zlib.apk", "zlib=1.3.2-r1"),
        source + "\nRUN apk add --no-cache zlib=1.3.2-r0\n",
    ):
        with pytest.raises(AssertionError):
            _assert_runtime_zlib_pin(altered, branch)
