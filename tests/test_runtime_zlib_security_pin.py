"""Keep the CVE-2026-85091 backport in both final production images."""

import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = (ROOT / "services/caddy/Dockerfile", ROOT / "frontend.Dockerfile")
ZLIB_PIN = "zlib=1.3.2-r1"


def _assert_runtime_zlib_pin(source: str) -> None:
    """Require the repository's single, fail-closed runtime APK install form."""
    stages = re.split(r"(?im)^FROM[ \t]+", source)
    assert len(stages) > 1, "missing Docker runtime stage"
    runtime = re.sub(r"\\\r?\n[ \t]*", " ", stages[-1])
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
    _assert_runtime_zlib_pin(dockerfile.read_text(encoding="utf-8"))


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
        _assert_runtime_zlib_pin(source.replace(ZLIB_PIN, replacement))


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
