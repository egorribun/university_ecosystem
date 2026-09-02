"""Generate frontend message limits from the backend-owned contract."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPOSITORY_ROOT / "frontend/src/api/schemas/messageLimits.ts"
SOURCE = REPOSITORY_ROOT / "app/core/config/storage.py"


def _message_limit() -> int:
    """Read the literal contract without importing application dependencies."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, ast.Name) and target.id == "CHAT_MAX_MESSAGE_LENGTH"
                for target in targets
            ):
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    return value.value
                break
    raise RuntimeError(f"missing literal CHAT_MAX_MESSAGE_LENGTH in {SOURCE}")


def _render() -> str:
    message_limit = _message_limit()

    return f"""/**
 * GENERATED FILE — do not edit by hand.
 * Source: app/core/config/storage.py:CHAT_MAX_MESSAGE_LENGTH
 * Regenerate with: python scripts/generate_message_contract.py
 */
export const CHAT_MESSAGE_MAX_LENGTH = {message_limit} as const
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked-in generated contract is stale",
    )
    args = parser.parse_args()
    expected = _render()
    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else None
    if args.check:
        if current != expected:
            print(f"stale generated message contract: {TARGET}")
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
