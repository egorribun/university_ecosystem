"""Report only the three reviewed SSR scanner identities, never source values."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

EXPECTED = (
    ("services/gateway/cmd/ssr-mtls-fixture/main.go", "Secret Keyword", 94),
    (
        "services/gateway/cmd/ssr-mtls-fixture/main_test.go",
        "Basic Auth Credentials",
        112,
    ),
    ("services/gateway/cmd/ssr-proxy/main_test.go", "Basic Auth Credentials", 39),
)
EXPECTED_BLOBS = {
    "services/gateway/cmd/ssr-mtls-fixture/main.go": bytes(
        (
            212,
            113,
            252,
            9,
            61,
            29,
            21,
            14,
            229,
            180,
            218,
            208,
            161,
            136,
            11,
            98,
            12,
            225,
            173,
            81,
        )
    ),
    "services/gateway/cmd/ssr-mtls-fixture/main_test.go": bytes(
        (
            68,
            3,
            255,
            104,
            113,
            146,
            134,
            159,
            24,
            124,
            44,
            38,
            65,
            233,
            52,
            45,
            52,
            106,
            93,
            46,
        )
    ),
    "services/gateway/cmd/ssr-proxy/main_test.go": bytes(
        (
            237,
            199,
            26,
            229,
            186,
            179,
            216,
            201,
            65,
            163,
            207,
            219,
            58,
            246,
            75,
            124,
            216,
            184,
            249,
            150,
        )
    ),
}
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SCAN_BYTES = 8 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{40}")


def read_regular(path, limit):
    # The diagnostic runs on Linux. Refuse unsupported no-follow platforms.
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("not a bounded regular file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file grew beyond limit")
    return data


def git_blob_digest(data):
    header = b"blob " + str(len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data, usedforsecurity=False).digest()


def validate_sources(root):
    for relative_path, expected in EXPECTED_BLOBS.items():
        path = root / relative_path
        if path.parent.resolve() != path.parent:
            raise ValueError("source directory is redirected")
        data = read_regular(path, MAX_SOURCE_BYTES)
        actual = git_blob_digest(data)
        if actual != expected:
            raise ValueError("reviewed source changed")


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
        validate_sources(Path(__file__).resolve().parents[2])
        raw = read_regular(Path(args.scan), MAX_SCAN_BYTES)
        document = json.loads(raw, object_pairs_hook=unique_object)
        receipt = reviewed_identities(document, args.source_sha)
    except (OSError, ValueError, TypeError, RecursionError, AttributeError):
        print("ERROR: reviewed SSR identity receipt unavailable.", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
