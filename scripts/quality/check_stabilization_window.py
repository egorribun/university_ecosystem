#!/usr/bin/env python3
"""Evaluate the calendar-day stability window for a quality workflow.

The promotion rule is deliberately fail-closed: a successful workflow run is
required for every day in the window, and the newest successful run must be on
the requested as-of date.  A single green run can never be mistaken for a
30-day stabilization record.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


def _parse_date(value: str) -> date:
    """Parse an ISO date or timestamp into a UTC calendar date."""

    normalized = value.strip().replace("Z", "+00:00")
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return datetime.fromisoformat(normalized).astimezone(UTC).date()


def _successful_run_dates(
    runs: Iterable[dict[str, Any]], *, branch: str | None
) -> set[date]:
    dates: set[date] = set()
    for run in runs:
        if run.get("conclusion") != "success":
            continue
        if branch is not None and run.get("head_branch") != branch:
            continue
        timestamp = (
            run.get("completed_at")
            or run.get("updated_at")
            or run.get("run_started_at")
            or run.get("created_at")
        )
        if isinstance(timestamp, str) and timestamp:
            dates.add(_parse_date(timestamp))
    return dates


def evaluate_window(
    runs: Iterable[dict[str, Any]],
    *,
    days: int = 30,
    as_of: date | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    """Return a machine-readable stabilization decision."""

    if days < 1:
        raise ValueError("days must be positive")
    successful_dates = _successful_run_dates(runs, branch=branch)
    latest = max(successful_dates) if successful_dates else None
    effective_as_of = as_of or date.today()
    expected_latest = effective_as_of
    expected_dates = {
        expected_latest - timedelta(days=offset) for offset in range(days)
    }
    missing_dates = sorted(expected_dates - successful_dates)
    stale = latest != expected_latest
    eligible = latest is not None and not stale and not missing_dates
    if eligible:
        reason = f"{days} consecutive successful calendar days are present"
    elif latest is None:
        reason = "no successful workflow run is available"
    elif stale:
        reason = f"latest successful run is {latest.isoformat()}, expected {expected_latest.isoformat()}"
    else:
        reason = f"missing successful run dates: {', '.join(item.isoformat() for item in missing_dates)}"
    return {
        "eligible": eligible,
        "required_days": days,
        "as_of": effective_as_of.isoformat(),
        "branch": branch,
        "latest_success_date": latest.isoformat() if latest else None,
        "successful_dates": sorted(item.isoformat() for item in successful_dates),
        "missing_dates": [item.isoformat() for item in missing_dates],
        "reason": reason,
    }


def _load_runs(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        runs = value
    elif isinstance(value, dict) and isinstance(value.get("workflow_runs"), list):
        runs = value["workflow_runs"]
    else:
        raise ValueError("runs JSON must be an array or a workflow_runs object")
    if not all(isinstance(item, dict) for item in runs):
        raise ValueError("every workflow run must be a JSON object")
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--branch")
    parser.add_argument("--as-of", type=_parse_date)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_window(
        _load_runs(args.runs),
        days=args.days,
        as_of=args.as_of,
        branch=args.branch,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
