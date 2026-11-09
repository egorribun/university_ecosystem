#!/usr/bin/env python3
"""Select the deterministic security rule subset from a pinned semgrep-rules checkout (AUD-380).

A rule is kept when its ``metadata.category`` is ``security`` and its
``metadata.subcategory`` is not exactly ``["audit"]`` (an unset subcategory is
kept). Secret rules are not selected: Gitleaks and detect-secrets already gate
secrets with reviewed inventories. Rule files that do not
declare a top-level ``rules`` list are not rules and are skipped. The combined
configuration is written with sorted rule ids and stable bytes so the scan
input is reproducible. Unparseable rule files, malformed rules, duplicate rule
ids and an empty selection fail closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIRECTORIES = (
    "python",
    "javascript",
    "typescript",
    "go",
    "yaml",
    "dockerfile",
    "bash",
    "rust",
    "generic/ci",
)
RULE_SUFFIXES = frozenset({".yaml", ".yml"})


class SelectionError(ValueError):
    """Raised when the rule subset cannot be selected deterministically."""


def _rule_files(rules_root: Path, directories: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    for directory in directories:
        base = rules_root / directory
        if not base.is_dir():
            raise SelectionError(f"rule directory is missing: {directory}")
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in RULE_SUFFIXES:
                continue
            if ".test." in path.name:
                continue
            files.append(path)
    return sorted(files)


def _rules_in(path: Path) -> list[dict[str, Any]]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise SelectionError(f"cannot parse rule file {path}: {exc}") from exc
    if not isinstance(loaded, dict) or "rules" not in loaded:
        return []
    rules = loaded["rules"]
    if not isinstance(rules, list):
        raise SelectionError(f"rules is not a list in {path}")
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            raise SelectionError(f"malformed rule without a string id in {path}")
    return rules


def _is_kept(rule: dict[str, Any], path: Path) -> bool:
    metadata = rule.get("metadata", {})
    if not isinstance(metadata, dict):
        raise SelectionError(f"rule {rule['id']} metadata is not a mapping in {path}")
    if metadata.get("category") != "security":
        return False
    subcategory = metadata.get("subcategory")
    if subcategory is None:
        return True
    values = [subcategory] if isinstance(subcategory, str) else subcategory
    if not isinstance(values, list):
        raise SelectionError(f"rule {rule['id']} subcategory is malformed in {path}")
    return values != ["audit"]


def qualified_id(path: Path, rules_root: Path, rule_id: str) -> str:
    """Return Semgrep's path-qualified check id (dotted rule path, then the id).

    Upstream rule ids are short and repeat across language directories, while
    Semgrep reports findings under this qualified form. Using it keeps the flat
    combined configuration unambiguous and the finding keys reproducible.
    """

    relative = path.relative_to(rules_root).with_suffix("").as_posix()
    return ".".join([*relative.split("/"), rule_id])


def select_rules(
    rules_root: Path, directories: Sequence[str] = DEFAULT_DIRECTORIES
) -> tuple[list[dict[str, Any]], int, int]:
    """Return kept rules with qualified ids, sorted by id, plus kept and dropped counts."""

    kept: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    dropped = 0
    for path in _rule_files(rules_root, directories):
        for rule in _rules_in(path):
            rule_id = qualified_id(path, rules_root, rule["id"])
            if rule_id in seen:
                raise SelectionError(f"duplicate rule id within a file: {rule_id}")
            seen.add(rule_id)
            if _is_kept(rule, path):
                kept[rule_id] = {**rule, "id": rule_id}
            else:
                dropped += 1
    if not kept:
        raise SelectionError("the security rule selection is empty")
    return [kept[rule_id] for rule_id in sorted(kept)], len(kept), dropped


def render_config(rules: list[dict[str, Any]]) -> str:
    """Render a deterministic configuration; JSON is valid Semgrep YAML."""

    return (
        json.dumps(
            {"rules": rules}, indent=2, sort_keys=True, ensure_ascii=False, default=str
        )
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rules, kept, dropped = select_rules(args.rules_root)
    except SelectionError as exc:
        print(f"::error::Semgrep rule selection: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_config(rules), encoding="utf-8", newline="\n")
    print(f"Semgrep rule selection: kept {kept} rule(s), dropped {dropped}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
