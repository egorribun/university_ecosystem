"""PreToolUse safety interceptor.

Evaluates tool calls (command execution, file writes/edits) against safety policies.
Blocks destructive actions (deny), flags high-impact operations for confirmation (ask),
and allows safe development workflows (allow).
"""

from __future__ import annotations

import os
import re
import shlex
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
PROTECTED_GIT_BRANCHES = frozenset({"main", "master", "egorribun"})
HOOK_PATH_TOKEN = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9_])\.agents/hooks(?:/|\.json(?=$|[^A-Za-z0-9_.-])|$)"
)
HOOK_MUTATORS = frozenset(
    {
        "add-content",
        "chmod",
        "clear-content",
        "copy",
        "copy-item",
        "cp",
        "del",
        "erase",
        "icacls",
        "install",
        "ln",
        "move-item",
        "mv",
        "new-item",
        "out-file",
        "patch",
        "remove-item",
        "rename-item",
        "rm",
        "rmdir",
        "rd",
        "set-acl",
        "set-content",
        "tee",
        "touch",
        "truncate",
        "xcopy",
        "robocopy",
    }
)
GIT_GLOBAL_WITH_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace"}
PUSH_WITH_VALUE = {"--exec", "--push-option", "--receive-pack", "--repo", "-o"}
SHELL_FLAGS = {
    "bash": {"-c", "-lc", "-cl"},
    "cmd": {"/c", "/k"},
    "cmd.exe": {"/c", "/k"},
    "powershell": {"-c", "-command"},
    "pwsh": {"-c", "-command"},
    "sh": {"-c"},
    "zsh": {"-c", "-lc", "-cl"},
}
INLINE_WRITE = re.compile(
    r"(?i)(?:\b(?:write(?:_text|_bytes)?|writeFile(?:Sync)?|unlink(?:Sync)?|"
    r"rename(?:Sync)?|replace|remove|chmod|Set-Content|Add-Content|Out-File|"
    r"Remove-Item|Move-Item|Copy-Item|New-Item|copy(?:file|2)?)\s*(?:\(|\b)|"
    r"\bopen\s*\([^)]*,\s*['\"](?:w|a|x)|(?:^|\s)(?:>>?|&>>?|>\|)\s*)"
)


def _shell_segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|>\n")
    lexer.whitespace = " \t\r"
    lexer.escape = ""
    lexer.whitespace_split = True
    lexer.commenters = "#"
    result: list[list[str]] = []
    current: list[str] = []
    for token in lexer:
        if token and all(char in ";&|\n" for char in token):
            if current:
                result.append(current)
                current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def _program(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _unwrap_command(tokens: list[str]) -> list[str]:
    index = 0
    wrappers = {"sudo", "command", "env", "exec", "nohup", "time"}
    value_options = {"-u", "--unset", "-C", "--chdir", "--user", "--group", "-g"}
    while index < len(tokens) and _program(tokens[index]) in wrappers:
        wrapper = _program(tokens[index])
        index += 1
        if wrapper in {"env", "sudo", "command", "time"}:
            while index < len(tokens) and tokens[index].startswith("-"):
                option = tokens[index]
                index += 2 if option in value_options else 1
        if wrapper == "env":
            while index < len(tokens) and re.match(
                r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[index]
            ):
                index += 1
    while index < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[index]):
        index += 1
    return tokens[index:]


def _git_call(tokens: list[str]) -> tuple[str, list[str]] | None:
    tokens = _unwrap_command(tokens)
    if not tokens or _program(tokens[0]) not in {"git", "git.exe"}:
        return None
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        if option == "--":
            index += 1
            break
        index += 2 if option in GIT_GLOBAL_WITH_VALUE else 1
    if index >= len(tokens):
        return None
    return tokens[index].casefold(), tokens[index + 1 :]


def _protected_ref(value: str, *, refspec: bool = False) -> bool:
    branch = value.strip("'\"")
    if refspec and ":" in branch:
        branch = branch.rsplit(":", 1)[1]
    branch = branch.lstrip("+").casefold()
    for prefix in ("refs/heads/", "refs/remotes/"):
        if branch.startswith(prefix):
            branch = branch[len(prefix) :]
    if branch.startswith("origin/"):
        branch = branch[len("origin/") :]
    if branch in PROTECTED_GIT_BRANCHES:
        return True
    if branch.count("*") == 1:
        prefix, suffix = branch.split("*", 1)
        return any(
            name.startswith(prefix)
            and name.endswith(suffix)
            and len(name) >= len(prefix) + len(suffix)
            for name in PROTECTED_GIT_BRANCHES
        )
    return False


def _push_state(args: list[str]) -> tuple[list[str], bool, bool]:
    refs: list[str] = []
    force = delete = False
    index = 0
    while index < len(args):
        option = args[index]
        if option == "--":
            refs.extend(args[index + 1 :])
            break
        if option in {
            "--force",
            "--force-with-lease",
            "-f",
            "-uf",
            "-fu",
        } or option.startswith("--force-with-lease="):
            force = True
        if option in {"--delete", "-d", "--prune"}:
            delete = True
        if option == "--mirror":
            force = delete = True
        if option in PUSH_WITH_VALUE:
            index += 2
            continue
        if option.startswith("--") and "=" in option:
            index += 1
            continue
        if option.startswith("-"):
            force = force or (
                not option.startswith("--") and "f" in option[1:].casefold()
            )
            delete = delete or (
                not option.startswith("--") and "d" in option[1:].casefold()
            )
            index += 1
            continue
        refs.append(option)
        index += 1
    if (
        len(refs) > 1
        and ":" not in refs[0]
        and not refs[0].startswith(("+", "refs/heads/"))
    ):
        refs = refs[1:]
    elif (
        len(refs) == 1
        and refs[0].casefold() not in PROTECTED_GIT_BRANCHES
        and ":" not in refs[0]
        and not refs[0].startswith(("+", "refs/heads/"))
    ):
        refs = []
    forced_refspec = any(ref.startswith("+") for ref in refs)
    return (
        refs,
        force or forced_refspec,
        delete or any(ref.startswith(":") for ref in refs),
    )


def _protected_git_reason(tokens: list[str]) -> str | None:
    parsed = _git_call(tokens)
    if parsed is None:
        return None
    command, args = parsed
    if command == "push":
        refs, force, delete = _push_state(args)
        if any(option in {"--mirror", "--prune"} for option in args):
            return "Mirror or prune pushes may delete protected branches."
        if delete and any(_protected_ref(ref, refspec=True) for ref in refs):
            return "Deleting main/master/egorribun through git push is prohibited."
        if force and (
            not refs or any(_protected_ref(ref, refspec=True) for ref in refs)
        ):
            return "Force-pushing to main/master/egorribun is prohibited."
    if command in {"branch", "update-ref", "symbolic-ref"}:
        deleting = any(
            arg in {"-d", "-D", "--delete"}
            or (arg.startswith("-") and "d" in arg[1:].casefold())
            for arg in args
        )
        targets = [arg for arg in args if arg != "--" and not arg.startswith("-")]
        if deleting and any(_protected_ref(target) for target in targets):
            return "Deleting main/master/egorribun refs is prohibited."
    return None


def _mutates_hook(tokens: list[str]) -> bool:
    tokens = _unwrap_command(tokens)
    if not tokens or not any(
        HOOK_PATH_TOKEN.search(token.replace("\\", "/")) for token in tokens
    ):
        return False
    program = _program(tokens[0])
    if program in HOOK_MUTATORS:
        return True
    if program in {"sed", "perl"} and any(
        arg == "-i" or arg.startswith("-i") for arg in tokens[1:]
    ):
        return True
    inline_code_programs = {
        "python",
        "python3",
        "python.exe",
        "python3.exe",
        "node",
        "node.exe",
    }
    if program in inline_code_programs:
        code_flags = {"-c", "-e", "--eval"}
        has_code_flag = any(arg.casefold() in code_flags for arg in tokens[1:])
        if has_code_flag and INLINE_WRITE.search(" ".join(tokens[1:])):
            return True
    flags = {flag.casefold() for flag in SHELL_FLAGS.get(program, set())}
    if any(arg.casefold() in flags for arg in tokens[1:]) and INLINE_WRITE.search(
        " ".join(tokens[1:])
    ):
        return True
    if any(token in {">", ">>", "&>", "&>>", ">|", "&>|"} for token in tokens):
        return True
    parsed = _git_call(tokens)
    return parsed is not None and parsed[0] in {
        "apply",
        "checkout",
        "restore",
        "rm",
        "mv",
        "reset",
    }


def _nested_shell(tokens: list[str]) -> list[list[str]]:
    tokens = _unwrap_command(tokens)
    if not tokens:
        return []
    flags = {flag.casefold() for flag in SHELL_FLAGS.get(_program(tokens[0]), set())}
    for index, token in enumerate(tokens[1:], start=1):
        if token.casefold() in flags:
            payload = " ".join(tokens[index + 1 :])
            return _shell_segments(payload) if payload else []
    return []


def _pre_tool_command_policy(command: str) -> str | None:
    try:
        segments = _shell_segments(command)
        for segment in segments:
            for tokens in [segment, *_nested_shell(segment)]:
                if _mutates_hook(tokens):
                    return "Modifying files under .agents/hooks or .agents/hooks.json is prohibited."
                reason = _protected_git_reason(tokens)
                if reason is not None:
                    return reason
    except ValueError:
        return "Unable to safely inspect malformed shell quoting; command denied."
    return None


def evaluate_run_command(cmd_line: str) -> dict[str, Any]:
    """Evaluate a shell command string for safety."""
    if not cmd_line or not cmd_line.strip():
        return {"decision": "allow", "reason": "Empty command."}

    cmd_normalized = cmd_line.strip()

    policy_reason = _pre_tool_command_policy(cmd_normalized)
    if policy_reason is not None:
        return {
            "decision": "deny",
            "reason": f"[PreToolUse Safety Block] {policy_reason} Command: {cmd_normalized[:80]}",
        }

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

    # Resolve relative tool paths from the repository root and normalize
    # backslash separators before checking the final in-repository target.
    repo_root = find_repo_root()
    target_text = str(target_file)
    if os.name != "nt":
        target_text = target_text.replace("\\", "/")
        if re.match(r"^[a-zA-Z]:/", target_text):
            return {
                "decision": "deny",
                "reason": f"[PreToolUse Safety Block] File modifications must stay inside the repository: '{target_file}'.",
            }
    target_path = Path(target_text)
    if not target_path.is_absolute():
        target_path = repo_root / target_path
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
    raw_lower = target_text.replace("\\", "/").lower()
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
    try:
        resolved_repo = repo_root.resolve()
        resolved_path = target_path.resolve()
        rel_path = resolved_path.relative_to(resolved_repo).as_posix()
        rel_path_key = rel_path.casefold()
        if (
            rel_path_key == ".agents/hooks"
            or rel_path_key == ".agents/hooks.json"
            or rel_path_key.startswith(".agents/hooks/")
        ):
            return {
                "decision": "deny",
                "reason": f"[PreToolUse Safety Block] Modifications to hook policy files are prohibited: '{rel_path}'.",
            }
        if rel_path_key in {path.casefold() for path in CRITICAL_PROTECTED_FILES}:
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
