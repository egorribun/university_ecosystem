#!/usr/bin/env python3
"""Create a content-addressed quality certification record for a release."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_record(
    *,
    commit_sha: str,
    contract_path: Path,
    report_paths: list[Path],
    check_results: dict[str, Any],
    known_limitations: list[str],
    signing_key: bytes | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    contract = _load_object(contract_path)
    record: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "commit_sha": commit_sha,
        "required_checks": check_results,
        "contract_sha256": _sha256(contract_path),
        "report_hashes": {
            path.as_posix(): _sha256(path)
            for path in sorted(report_paths, key=lambda item: item.as_posix())
        },
        "exclusions": contract.get("exclusions", []),
        "quarantines": contract.get("quarantines", []),
        "known_limitations": known_limitations,
    }
    unsigned = _canonical(record)
    record["record_sha256"] = hashlib.sha256(unsigned).hexdigest()
    if signing_key:
        record["hmac_sha256"] = hmac.new(
            signing_key, unsigned, hashlib.sha256
        ).hexdigest()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPOSITORY_ROOT / "quality" / "quality-contract.json",
    )
    parser.add_argument("--report", type=Path, action="append", default=[])
    parser.add_argument(
        "--report-dir",
        type=Path,
        action="append",
        default=[],
        help="Directory containing additional report evidence to hash recursively",
    )
    parser.add_argument(
        "--checks",
        type=Path,
        required=True,
        help="JSON object mapping required check names to results",
    )
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    checks = _load_object(args.checks)
    if not checks:
        parser.error("--checks must contain the completed required-check matrix")
    report_paths = list(args.report)
    for report_dir in args.report_dir:
        if not report_dir.is_dir():
            parser.error(f"report directory does not exist: {report_dir}")
        report_paths.extend(
            path for path in report_dir.rglob("*") if path.is_file()
        )
    missing = [
        str(path) for path in [args.contract, *report_paths] if not path.is_file()
    ]
    if missing:
        parser.error(f"missing evidence files: {', '.join(missing)}")
    key_text = os.environ.get("QUALITY_CERTIFICATION_KEY")
    record = build_record(
        commit_sha=args.commit_sha,
        contract_path=args.contract,
        report_paths=report_paths,
        check_results=checks,
        known_limitations=args.limitation,
        signing_key=key_text.encode("utf-8") if key_text else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
