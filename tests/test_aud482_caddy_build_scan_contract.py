"""Bind the isolated Caddy scan to the production build's package selection."""

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "services/caddy/Dockerfile"
WORKFLOW = ROOT / ".github/workflows/reusable-security-audit.yml"


def _command_args(
    source: str, command: tuple[str, ...], *, docker: bool = False
) -> list[str]:
    folded = re.sub(r"\\\r?\n\s*", " ", source)
    matches: list[list[str]] = []
    for line in folded.splitlines():
        if docker and not line.lstrip().startswith("RUN "):
            continue
        tokens = shlex.split(line, comments=True)
        for index in range(len(tokens) - len(command) + 1):
            if tokens[index : index + len(command)] != list(command):
                continue
            args = tokens[index + len(command) :]
            stop = next(
                (
                    i
                    for i, token in enumerate(args)
                    if token in {"&&", "||", ";", ">", "|"}
                ),
                len(args),
            )
            matches.append(args[:stop])
    assert len(matches) == 1, f"expected exactly one {command} command"
    return matches[0]


def _build_tags(args: list[str]) -> frozenset[str]:
    values = []
    for index, arg in enumerate(args):
        if arg == "-tags":
            assert index + 1 < len(args), "missing Go build tags"
            values.append(args[index + 1])
        elif arg.startswith("-tags="):
            values.append(arg.removeprefix("-tags="))
    assert len(values) == 1, "expected exactly one Go build tags argument"
    tags = values[0].split(",")
    assert all(re.fullmatch(r"[A-Za-z0-9_.]+", tag) for tag in tags)
    return frozenset(tags)


def _assert_matching_build_tags(dockerfile: str, step: dict[str, Any]) -> None:
    """Require the scanner and its comparison graph to select build packages."""
    builder = _build_tags(_command_args(dockerfile, ("go", "build"), docker=True))
    scanner = _build_tags(_command_args(step["run"], ("govulncheck",)))
    graph = _build_tags(_command_args(step["run"], ("go", "list")))
    assert builder == scanner == graph, "Caddy build and scan tags differ"


def test_caddy_build_scan_and_graph_use_the_same_tags() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["govulncheck"]["steps"]
    step = next(
        item for item in steps if item.get("name") == "Scan isolated Caddy module"
    )
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    _assert_matching_build_tags(dockerfile, step)

    # Without nomysql the real Go package graph includes go-sql-driver/mysql,
    # which the unchanged scan excludes. The earlier graph contract accepts it.
    mutated = dockerfile.replace("-tags nobadger,nomysql,nopgx", "-tags nobadger,nopgx")
    assert mutated != dockerfile
    with pytest.raises(AssertionError, match="Caddy build and scan tags differ"):
        _assert_matching_build_tags(mutated, step)
