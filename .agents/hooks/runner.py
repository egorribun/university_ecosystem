"""CLI runner entry point for Antigravity Deterministic Lifecycle Hooks.

Routes hook events (PreToolUse, PostToolUse, Stop) to specialized evaluators.
Enforces strict camelCase JSON protocol over standard I/O.
"""

from __future__ import annotations

import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from .common import read_json_stdin, write_json_stdout
    from .post_tool_linter import evaluate_post_tool
    from .pre_tool_safety import evaluate_pre_tool
    from .stop_quality_gate import evaluate_stop
except (ImportError, ValueError):
    from common import read_json_stdin, write_json_stdout
    from post_tool_linter import evaluate_post_tool
    from pre_tool_safety import evaluate_pre_tool
    from stop_quality_gate import evaluate_stop


def parse_event_type(args: list[str]) -> str:
    """Parse the hook event type from CLI arguments."""
    if not args:
        return "pre-tool"

    for i, arg in enumerate(args):
        if arg in ("--event", "-e") and i + 1 < len(args):
            return args[i + 1].lower()
        if not arg.startswith("-"):
            return arg.lower()

    return "pre-tool"


def main() -> int:
    """Main CLI entry point."""
    event_raw = parse_event_type(sys.argv[1:])
    event = event_raw.replace("_", "-").lower()

    # Read protojson input from stdin
    payload = read_json_stdin()

    try:
        if event in ("pre-tool", "pre-tool-use", "pretooluse"):
            result = evaluate_pre_tool(payload)
            write_json_stdout(result)
            return 0

        elif event in ("post-tool", "post-tool-use", "posttooluse"):
            result = evaluate_post_tool(payload)
            write_json_stdout(result)
            return 0

        elif event in ("stop", "stop-gate", "quality-gate"):
            result = evaluate_stop(payload)
            write_json_stdout(result)
            return 0

        else:
            sys.stderr.write(f"[hooks.runner] Unknown event type: {event_raw}\n")
            write_json_stdout(
                {"decision": "allow", "reason": f"Unknown hook event '{event_raw}'."}
            )
            return 0

    except Exception as exc:
        sys.stderr.write(
            f"[hooks.runner] Error processing hook event '{event_raw}': {exc}\n"
        )
        # Safe fallback: do not crash agent loop
        if "pre" in event:
            write_json_stdout(
                {"decision": "allow", "reason": f"Hook exception fallback: {exc}"}
            )
        elif "post" in event:
            write_json_stdout({})
        elif "stop" in event:
            write_json_stdout(
                {"decision": "allow", "reason": f"Hook exception fallback: {exc}"}
            )
        else:
            write_json_stdout({})
        return 0


if __name__ == "__main__":
    sys.exit(main())
