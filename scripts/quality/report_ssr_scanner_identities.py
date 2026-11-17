"""Report only the three reviewed SSR scanner identities, never source values."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED = (
    ("services/gateway/cmd/ssr-mtls-fixture/main.go", "Secret Keyword", 94),
    ("services/gateway/cmd/ssr-mtls-fixture/main_test.go", "Basic Auth Credentials", 112),
    ("services/gateway/cmd/ssr-proxy/main_test.go", "Basic Auth Credentials", 39),
)
MAX_SCAN_BYTES = 8 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{40}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def reviewed_identities(document, source_sha):
    """Validate everything before returning a bounded metadata-only receipt."""
    if (
        not isinstance(source_sha, str)
        or _HEX.fullmatch(source_sha) is None
        or source_sha == "0" * 40
        or not isinstance(document, dict)
        or not isinstance(document.get("results"), dict)
    ):
        raise ValueError("invalid receipt input")
    results = document["results"]
    identities = []
    for path, detector, line in EXPECTED:
        entries = results.get(path)
        if not isinstance(entries, list):
            raise ValueError("missing reviewed finding")
        matches = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("type") == detector
            and type(entry.get("line_number")) is int
            and entry["line_number"] == line
        ]
        if len(matches) != 1:
            raise ValueError("ambiguous reviewed finding")
        finding = matches[0]
        digest = finding.get("hashed_secret")
        if (
            finding.get("filename") != path
            or not isinstance(digest, str)
            or _HEX.fullmatch(digest) is None
        ):
            raise ValueError("invalid reviewed identity")
        identities.append(
            {"path": path, "type": detector, "line": line, "hashed_secret": digest}
        )
    return {"source_sha": source_sha, "identities": identities}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan")
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    try:
        with Path(args.scan).open("rb") as stream:
            raw = stream.read(MAX_SCAN_BYTES + 1)
        if len(raw) > MAX_SCAN_BYTES:
            raise ValueError("scan too large")
        document = json.loads(raw, object_pairs_hook=unique_object)
        receipt = reviewed_identities(document, args.source_sha)
    except (OSError, ValueError, TypeError, RecursionError):
        print("ERROR: reviewed SSR identity receipt unavailable.", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
