"""Replay a local Pact file against a live HTTP provider.

This script is intentionally small and side-effect free apart from the Pact
verifier's HTTP requests.  It is used by CI after starting the real FastAPI
backend, so the provider replay cannot be satisfied by a hand-written stub.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pact-file", type=Path, required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--provider", default="university-backend")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    pact_file = args.pact_file.resolve()
    if not pact_file.is_file():
        raise FileNotFoundError(f"Pact file does not exist: {pact_file}")

    # Import only when invoked: Windows developers can still run the rest of
    # the contract suite even though pact_ffi is Linux CI infrastructure here.
    from urllib.parse import urlparse

    from pact import Verifier

    parsed_url = urlparse(args.provider_url)
    host = parsed_url.hostname or "localhost"

    (
        Verifier(args.provider, host=host)
        .add_transport(url=args.provider_url)
        .add_source(pact_file)
        .set_request_timeout(10_000)
        .verify()
    )
    print(f"Pact provider verification passed: {args.provider} <- {pact_file.name}")


if __name__ == "__main__":
    main()
