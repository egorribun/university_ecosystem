"""PreToolUse safety interceptor.

Evaluates tool calls (command execution, file writes/edits) against safety policies.
Blocks destructive actions (deny), flags high-impact operations for confirmation (ask),
and allows safe development workflows (allow).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from .common import find_repo_root, get_field
except (ImportError, ValueError):
    from common import find_repo_root, get_field

# Hard block patterns: strictly prohibited destructive operations
DENY_COMMAND_PATTERNS = [
    # Root and primary directory wipes (Unix, GNU, POSIX & Windows)
    (
        re.compile(
            r"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*|-r\s+-f|-f\s+-r|--recursive\s+--force|--force\s+--recursive|--recursive\s+-f|-f\s+--recursive|--force\s+-r|-r\s+--force)\s+['\"]?(?:\/|\/\*|~|\/etc|\/usr|\/var|\/bin|\/lib|[c-zC-Z]:[\\/])['\"]?(?:\s|[\\/]|$|['\"\)`;|&])",
            re.IGNORECASE,
        ),
        "Recursive deletion of root, home, or system directory is strictly prohibited.",
    ),
    # Windows cmd.exe mass deletion patterns
    (
        re.compile(
            r"\b(del|erase)\b.*(?:\/s|\/f|\/q|-[a-zA-Z]*f).*([c-zC-Z]:[\\/]|\\|\*|\.git)",
            re.IGNORECASE,
        ),
        "Mass deletion targeting drive root or critical system directories is prohibited.",
    ),
    (
        re.compile(
            r"\b(rmdir|rd)\b.*(?:\/s|\/q|-r).*([c-zC-Z]:[\\/]|\\|\.git)",
            re.IGNORECASE,
        ),
        "Recursive directory removal targeting drive root or .git is prohibited.",
    ),
    # PowerShell destructive deletion patterns
    (
        re.compile(
            r"\b(?:remove-item|ri|rmdir|rd|del|erase|clear-item)\b(?=.*(?:-recurse|-r\b|/s))(?=.*(?:-force|-fo\b|/f|/q))(?=.*(?:[c-zC-Z]:[\\/]|/|\*|\.git|~))",
            re.IGNORECASE,
        ),
        "PowerShell recursive forced deletion of critical paths is prohibited.",
    ),
    # Git directory deletion (rm, PowerShell, cmd)
    (
        re.compile(
            r"\b(?:rm|remove-item|ri|del|erase|rd|rmdir)\b.*(?:\s|-[a-zA-Z]*)\.git(?:\s|[\\/]|$|\*|['\"\)`;|&])",
            re.IGNORECASE,
        ),
        "Direct deletion of the .git directory is prohibited.",
    ),
    # Disk & filesystem wiping
    (
        re.compile(
            r"\b(mkfs(\.[a-zA-Z0-9]+)?|fdisk|parted|diskpart|format\s+[a-zA-Z]:(?:\s|$))",
            re.IGNORECASE,
        ),
        "Raw disk partition or format operations are strictly prohibited.",
    ),
    (
        re.compile(
            r"\bdd\s+.*if=(/dev/zero|/dev/urandom|/dev/random)\b",
            re.IGNORECASE,
        ),
        "Direct block storage overwrites via dd are strictly prohibited.",
    ),
    # Fork bombs and execution stalls
    (
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE),
        "Fork bomb patterns are strictly prohibited.",
    ),
    # Secret exfiltration patterns (piping or posting secret keys to remote endpoints)
    (
        re.compile(
            r"\b(curl|wget|nc|ncat|socat|Invoke-WebRequest|Invoke-RestMethod)\b.*(@\.env|@\.secrets|\.secrets[\\/]|\.pem\b|id_rsa\b|--post-file[=\s]+[^\s]*\.env|-T\s+[^\s]*\.env|--upload-file\s+[^\s]*\.env|-InFile[=\s]+[^\s]*(\.env|\.secrets|\.pem|id_rsa)|-InFile\s+[^\s]*\.env)",
            re.IGNORECASE,
        ),
        "Attempted exfiltration of sensitive secret files (.env, .secrets, private keys).",
    ),
    (
        re.compile(
            r"\b(cat|type|Get-Content)\s+([^\n|]*\.env|[^\n|]*\.secrets|.*\.pem|.*id_rsa)\s*\|\s*(curl|wget|nc|ncat|socat|Invoke-RestMethod|Invoke-WebRequest)\b",
            re.IGNORECASE,
        ),
        "Attempted piping of sensitive secret data to network endpoints.",
    ),
    # Forced push to main or master
    (
        re.compile(
            r"\bgit\s+push\b.*(--force(?:-with-lease)?|-f)\b.*(\bmain\b|\bmaster\b)",
            re.IGNORECASE,
        ),
        "Force-pushing to primary branch (main/master) is strictly prohibited.",
    ),
    (
        re.compile(
            r"\bpython(?:3)?\b.*(?:open|read_text|Path).*?(?:\.env|\.secrets|\.pem|id_rsa).*?(?:requests|httpx|urllib|socket|curl|post|send)",
            re.IGNORECASE,
        ),
        "Executing code that reads secrets and sends them over the network is strictly prohibited.",
    ),
    (
        re.compile(
            r"\brm\s+.*(?:\$HOME|\$USERPROFILE|%USERPROFILE%|%HOMEDRIVE%%HOMEPATH%)",
            re.IGNORECASE,
        ),
        "Recursive deletion of a user home directory is strictly prohibited.",
    ),
]

# High-impact operations requiring explicit confirmation (ask)
ASK_COMMAND_PATTERNS = [
    # Destructive SQL DDL
    (
        re.compile(
            r"\b(DROP\s+(?:DATABASE|SCHEMA|TABLE|OWNED|ROLE)|TRUNCATE(?:\s+TABLE)?|ALTER\s+TABLE\s+.*\s+DROP\s+COLUMN)\b",
            re.IGNORECASE,
        ),
        "Destructive database schema operation (DROP/TRUNCATE) requires explicit confirmation.",
    ),
    # Destructive Git operations
    (
        re.compile(
            r"\bgit\s+reset\s+--hard\b",
            re.IGNORECASE,
        ),
        "Hard git reset destroys uncommitted changes and requires confirmation.",
    ),
    (
        re.compile(
            r"\bgit\s+clean\s+(-[a-zA-Z]*f[a-zA-Z]*d[a-zA-Z]*|-[a-zA-Z]*d[a-zA-Z]*f[a-zA-Z]*)\b",
            re.IGNORECASE,
        ),
        "Forced git clean removes untracked files and requires confirmation.",
    ),
]

# Sensitive files that should not be directly overwritten with arbitrary data
CRITICAL_PROTECTED_FILES = {
    ".secrets/jwt_rs256.pem",
    ".secrets/jwt_rs256.pub",
    ".git/config",
    ".git/HEAD",
}


def evaluate_run_command(cmd_line: str) -> dict[str, Any]:
    """Evaluate a shell command string for safety."""
    if not cmd_line or not cmd_line.strip():
        return {"decision": "allow", "reason": "Empty command."}

    cmd_normalized = cmd_line.strip()

    # Check DENY patterns
    for pattern, reason in DENY_COMMAND_PATTERNS:
        if pattern.search(cmd_normalized):
            return {
                "decision": "deny",
                "reason": f"[PreToolUse Safety Block] {reason} Command: {cmd_normalized[:80]}",
            }

    # Check ASK patterns
    for pattern, reason in ASK_COMMAND_PATTERNS:
        if pattern.search(cmd_normalized):
            return {
                "decision": "ask",
                "reason": f"[PreToolUse Safety Prompt] {reason} Command: {cmd_normalized[:80]}",
            }

    return {"decision": "allow", "reason": "Command passed safety inspection."}


def evaluate_file_modification(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Evaluate file creation or replacement for safety."""
    target_file = get_field(
        args, "TargetFile", "target_file", "path", "file", default=""
    )
    if not target_file:
        return {"decision": "allow", "reason": "No target file specified."}

    # Normalize and resolve path
    target_path = Path(target_file)
    try:
        resolved_path = target_path.resolve()
        path_str = resolved_path.as_posix()
    except Exception:
        path_str = str(target_path).replace("\\", "/")

    # Check for system path traversal outside repository
    system_paths = [
        "/etc/",
        "/usr/",
        "/bin/",
        "/sbin/",
        "c:/windows/",
        "c:/program files/",
        "c:/program files (x86)/",
    ]
    path_lower = path_str.lower()
    raw_lower = str(target_file).replace("\\", "/").lower()
    for sys_path in system_paths:
        if (
            path_lower.startswith(sys_path)
            or sys_path in path_lower
            or raw_lower.startswith(sys_path)
            or sys_path in raw_lower
        ):
            return {
                "decision": "deny",
                "reason": f"[PreToolUse Safety Block] Modifications to system path '{target_file}' are prohibited.",
            }

    # Check critical protected files
    repo_root = find_repo_root()
    try:
        resolved_repo = repo_root.resolve()
        resolved_path = target_path.resolve()
        rel_path = resolved_path.relative_to(resolved_repo).as_posix()
        if rel_path in CRITICAL_PROTECTED_FILES:
            return {
                "decision": "ask",
                "reason": f"[PreToolUse Safety Prompt] Target file '{rel_path}' is a critical security artifact. Overwrite requires confirmation.",
            }
    except (ValueError, OSError):
        return {
            "decision": "deny",
            "reason": f"[PreToolUse Safety Block] File modifications must stay inside the repository: '{target_file}'.",
        }

    return {
        "decision": "allow",
        "reason": "File modification passed safety inspection.",
    }


def evaluate_pre_tool(payload: dict[str, Any]) -> dict[str, Any]:
    """Main evaluation entry point for PreToolUse events."""
    tool_call = get_field(payload, "toolCall", "tool_call", default={})
    if not isinstance(tool_call, dict):
        return {"decision": "allow", "reason": "No toolCall in payload."}

    tool_name = get_field(tool_call, "name", "tool_name", default="")
    args = get_field(tool_call, "args", "arguments", default={})
    if not isinstance(args, dict):
        args = {}

    if tool_name in {"run_command", "shell_command", "exec_command", "terminal"}:
        cmd_line = get_field(
            args, "CommandLine", "commandLine", "command_line", "cmd", default=""
        )
        return evaluate_run_command(cmd_line)

    if tool_name in {
        "write_to_file",
        "replace_file_content",
        "write_file",
        "edit_file",
        "apply_patch",
    }:
        return evaluate_file_modification(tool_name, args)

    # Default to allow for read-only / other harmless tools
    return {"decision": "allow", "reason": f"Tool '{tool_name}' allowed by default."}
