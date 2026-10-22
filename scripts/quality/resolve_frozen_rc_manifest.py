"""Resolve a reviewed frozen-RC manifest without exposing invalid input."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_MANIFEST_BYTES = 4096
ERROR = "ERROR: frozen RC manifest is invalid or not frozen"


def parse_manifest(document: object) -> str:
    """Return the exact frozen SHA, rejecting unknown or unfrozen selections."""
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "source_sha",
    }:
        raise ValueError("invalid manifest fields")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("invalid manifest version")
    source_sha = document["source_sha"]
    if (
        not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
    ):
        raise ValueError("invalid frozen source")
    return source_sha


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate manifest field")
        document[key] = value
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        manifest = arguments.manifest
        if manifest.is_symlink() or not manifest.is_file():
            raise ValueError("manifest must be a regular file")
        with manifest.open("rb") as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError("manifest exceeds size limit")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields)
        source_sha = parse_manifest(document)
    except (OSError, ValueError, RecursionError):
        print(ERROR, file=sys.stderr)
        return 1
    print(source_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
