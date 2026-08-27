#!/usr/bin/env python3
"""Verify an on-disk release certification against its expected SHA and HMAC."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from scripts.quality.generate_certification import verify_record_hmac

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def verify_certification(
    path: Path, *, expected_commit_sha: str, key: bytes
) -> dict[str, Any]:
    if not _COMMIT_SHA.fullmatch(expected_commit_sha):
        raise ValueError(
            "expected release commit SHA must be exactly 40 lowercase hexadecimal characters"
        )
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("certification record must be a JSON object")
    if record.get("commit_sha") != expected_commit_sha:
        raise ValueError("certification record does not match the release commit SHA")
    verify_record_hmac(record, key)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    args = parser.parse_args()
    key = os.environ.get("QUALITY_CERTIFICATION_KEY", "").encode("utf-8")
    try:
        verify_certification(
            args.record,
            expected_commit_sha=args.expected_commit_sha,
            key=key,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
