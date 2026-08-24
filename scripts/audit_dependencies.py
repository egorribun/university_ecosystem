from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterable


class AuditFailure(Exception):
    """Raised when an audit check fails."""


def parse_date(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise AuditFailure(f"Invalid date '{raw}', expected YYYY-MM-DD") from exc


def load_allowlist(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        raise AuditFailure(f"Allowlist file not found: {path}")

    data = yaml.safe_load(path.read_text()) or {}
    return data


def ensure_not_expired(entries: Iterable[dict[str, Any]], *, label: str) -> None:
    today = dt.datetime.now(dt.UTC).date()
    for entry in entries:
        expires_raw = entry.get("expires")
        if not expires_raw:
            raise AuditFailure(f"{label} entry missing expiry date: {entry}")

        expires = parse_date(str(expires_raw))
        if expires < today:
            owner = entry.get("owner", "(unknown owner)")
            identifier = entry.get("id") or entry.get("package")
            raise AuditFailure(
                f"{label} entry for '{identifier}' expired on {expires} "
                f"(owner: {owner})"
            )


def collect_npm_advisory_ids(package_dir: pathlib.Path) -> set[str]:
    cmd = ["npm", "audit", "--audit-level=high", "--json"]
    import os

    result = subprocess.run(  # noqa: S603
        cmd, cwd=package_dir, capture_output=True, text=True, shell=os.name == "nt"
    )

    if result.returncode not in (0, 1):
        raise AuditFailure(f"npm audit failed: {result.stderr or result.stdout}")

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AuditFailure(f"npm audit produced invalid JSON: {exc}") from exc

    advisories: set[str] = set()
    for vulnerability in (payload.get("vulnerabilities") or {}).values():
        if vulnerability.get("severity") not in {"high", "critical"}:
            continue
        for via in vulnerability.get("via", []):
            if isinstance(via, str):
                advisories.add(via)
            elif isinstance(via, dict):
                source = via.get("source") or via.get("url") or via.get("name")
                if source:
                    advisories.add(str(source))
    return advisories


def validate_npm_overrides(
    package_dir: pathlib.Path, allowlist: dict[str, Any]
) -> None:
    overrides = (allowlist.get("npm") or {}).get("overrides") or []
    ensure_not_expired(overrides, label="NPM override")

    package_json = package_dir / "package.json"
    if not package_json.exists():
        raise AuditFailure(f"package.json not found at {package_json}")

    package_data = json.loads(package_json.read_text())
    configured_overrides = package_data.get("overrides") or {}

    for entry in overrides:
        package = entry.get("package")
        expected_version = entry.get("pinned_version")
        if not package or not expected_version:
            raise AuditFailure(
                f"Override entry must include package and pinned_version: {entry}"
            )

        configured_version = configured_overrides.get(package)
        if configured_version != expected_version:
            raise AuditFailure(
                f"Expected override for {package!r} to pin version "
                f"{expected_version}, got {configured_version!r}."
            )


def check_allowances(
    found_ids: set[str], allowed_entries: list[dict[str, Any]], *, ecosystem: str
) -> None:
    ensure_not_expired(allowed_entries, label=f"{ecosystem} advisory allowlist")

    allowed_ids = {str(entry.get("id")) for entry in allowed_entries if entry.get("id")}
    missing = sorted(found_ids - allowed_ids)
    if missing:
        formatted = "\n".join(f"- {value}" for value in missing)
        # LOW-W19: format both args into a single string so the message is readable
        raise AuditFailure(
            f"{ecosystem} audit found advisories that are not in the allowlist:\n"
            f"{formatted}\n"
            "Add a temporary allowlist entry with an owner and expiry if this "
            "cannot be fixed immediately."
        )


def audit_npm(args: argparse.Namespace, allowlist: dict[str, Any]) -> None:
    if not args.npm:
        return

    package_dir = pathlib.Path(args.npm)
    validate_npm_overrides(package_dir, allowlist)

    advisories = collect_npm_advisory_ids(package_dir)
    allowed = (allowlist.get("npm") or {}).get("advisories") or []
    check_allowances(advisories, allowed, ecosystem="npm")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enforce dependency audit allowlists.")
    parser.add_argument(
        "--allowlist", required=True, help="Path to the audit allowlist YAML file."
    )
    parser.add_argument("--npm", help="Path to the npm project directory to audit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    allowlist = load_allowlist(pathlib.Path(args.allowlist))

    try:
        audit_npm(args, allowlist)
    except AuditFailure as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(
        "Dependency audits passed with no unapproved advisories or missing overrides."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
