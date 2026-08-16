#!/usr/bin/env python3
"""Render a small, deterministic quality trend dashboard from JSON snapshots.

The script intentionally consumes the normalized quality manifest rather than
parsing tool-specific coverage formats.  This keeps the dashboard honest: a
missing report is shown as missing instead of being silently treated as 0%.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _percent(component: dict[str, Any], metric: str) -> str:
    metrics = component.get("metrics", {})
    entry = metrics.get(metric, {}) if isinstance(metrics, dict) else {}
    value = entry.get("percent") if isinstance(entry, dict) else None
    return "—" if value is None else f"{float(value):.2f}%"


def _snapshot_row(path: Path, snapshot: dict[str, Any]) -> str:
    generated = snapshot.get("generated_at", "unknown")
    commit = snapshot.get("commit_sha", "unknown")
    components = snapshot.get("components", {})
    python = components.get("python", {})
    frontend = components.get("frontend", {})
    go_values = [
        components.get(name, {}).get("metrics", {}).get("statements", {}).get("percent")
        for name in ("go-gateway", "go-ws-hub", "go-file-processor", "go-shared")
    ]
    go_values = [float(value) for value in go_values if value is not None]
    go_summary = "—" if not go_values else f"{sum(go_values) / len(go_values):.2f}%"
    return (
        f"| `{generated}` | `{commit[:12]}` | {_percent(python, 'lines')} | "
        f"{_percent(frontend, 'lines')} | {go_summary} | "
        f"[{path.as_posix()}]({path.as_posix()}) |"
    )


def _register_rows(register: list[dict[str, Any]], today: date) -> list[str]:
    rows: list[str] = []
    for item in register:
        identifier = item.get("id", "unknown")
        owner = item.get("owner", "unknown")
        expires = item.get("expires_on", "")
        try:
            days = (date.fromisoformat(expires) - today).days
            status = "expired" if days < 0 else f"{days}d left"
        except (TypeError, ValueError):
            status = "invalid expiry"
        rows.append(f"| `{identifier}` | {owner} | `{expires}` | **{status}** |")
    return rows or ["| — | — | — | none |"]


def render_dashboard(
    snapshots: list[tuple[Path, dict[str, Any]]],
    contract: dict[str, Any],
    *,
    today: date | None = None,
) -> str:
    """Return deterministic Markdown for the supplied quality history."""

    today = today or date.today()
    snapshots = sorted(snapshots, key=lambda item: str(item[1].get("generated_at", "")))
    rows = [_snapshot_row(path, snapshot) for path, snapshot in snapshots]
    if not rows:
        rows = ["| — | — | — | — | — | no snapshots |"]

    policy = contract.get("policy", {})
    exclusions = contract.get("exclusions", [])
    quarantines = contract.get("quarantines", [])
    if not isinstance(exclusions, list):
        exclusions = []
    if not isinstance(quarantines, list):
        quarantines = []

    return "\n".join(
        [
            "# Quality dashboard",
            "",
            "This file is generated from normalized quality manifests. A `—` means "
            "evidence was not observed; it is never interpreted as a passing score.",
            "",
            f"Last rendered: `{today.isoformat()}`",
            f"Required patch coverage: **{policy.get('patch_coverage', 'unknown')}%**",
            f"Required viable mutation score: **{policy.get('viable_mutant_score', 'unknown')}%**",
            "",
            "## Coverage trend",
            "",
            "| Generated | Commit | Python lines | Frontend lines | Go statements (mean) | Evidence |",
            "| --- | --- | ---: | ---: | ---: | --- |",
            *rows,
            "",
            "## Exclusions",
            "",
            "| ID | Owner | Expires | Status |",
            "| --- | --- | --- | --- |",
            *_register_rows(exclusions, today),
            "",
            "## Quarantines",
            "",
            "| ID | Owner | Expires | Status |",
            "| --- | --- | --- | --- |",
            *_register_rows(quarantines, today),
            "",
            "## Interpretation",
            "",
            "A release is certifiable only when the required-check matrix, the "
            "coverage manifest, mutation gates, contract tests, and Tier0 evidence "
            "all pass. This dashboard is trend evidence, not a bypass for CI.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "quality" / "history",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPOSITORY_ROOT / "quality" / "quality-contract.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "testing" / "dashboard.md",
    )
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    paths = (
        sorted(args.history_dir.glob("*.json"))[-args.limit :]
        if args.history_dir.exists()
        else []
    )
    snapshots = [(path, _read_json(path)) for path in paths]
    dashboard = render_dashboard(snapshots, _read_json(args.contract))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dashboard, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
