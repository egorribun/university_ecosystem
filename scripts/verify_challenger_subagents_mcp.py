#!/usr/bin/env python3
"""Challenger 2 Empirical Verification Suite for Subagents & MCP Standards."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".agents"
SUBAGENTS_DIR = AGENTS_DIR / "subagents"
DOCS_MCP_DIR = REPO_ROOT / "docs" / "mcp"
USER_HOME = Path.home()
GEMINI_CONFIG_DIR = USER_HOME / ".gemini" / "config"
MCP_CONFIG_FILE = GEMINI_CONFIG_DIR / "mcp_config.json"
GLOBAL_CONFIG_FILE = GEMINI_CONFIG_DIR / "config.json"

VALID_BUILTIN_TOOLS = {
    "view_file",
    "find_by_name",
    "grep_search",
    "read_url_content",
    "run_command",
    "replace_file_content",
    "write_to_file",
    "list_dir",
    "schedule",
    "manage_task",
    "send_message",
}

VALID_WORKSPACE_MODES = {"branch", "share", "inherit"}
VALID_FS_PERMS = {"read-only", "read-write"}
VALID_BINARY_PERMS = {"allow", "deny"}
VALID_ROLES = {"Architect", "Developer", "QA", "Security", "Performance"}


def test_subagent_registry_and_files() -> list[str]:
    errors = []
    reg_path = AGENTS_DIR / "subagents.json"
    if not reg_path.exists():
        return [f"Registry not found: {reg_path}"]

    try:
        registry = json.loads(reg_path.read_text("utf-8"))
    except Exception as e:
        return [f"Failed to parse subagents.json: {e}"]

    if "subagents" not in registry or not isinstance(registry["subagents"], dict):
        return ["subagents.json missing 'subagents' dictionary"]

    subagents = registry["subagents"]
    expected_subagents = {
        "lead_architect": {
            "mode": "inherit",
            "fs": "read-only",
            "terminal": "deny",
            "role": "Architect",
        },
        "tdd_developer": {
            "mode": "branch",
            "fs": "read-write",
            "terminal": "allow",
            "role": "Developer",
        },
        "qa_e2e_tester": {
            "mode": "share",
            "fs": "read-only",
            "terminal": "allow",
            "role": "QA",
        },
        "security_auditor": {
            "mode": "inherit",
            "fs": "read-only",
            "network": "deny",
            "role": "Security",
        },
        "perf_optimizer": {
            "mode": "inherit",
            "fs": "read-only",
            "terminal": "allow",
            "role": "Performance",
        },
    }

    if set(subagents.keys()) != set(expected_subagents.keys()):
        errors.append(
            f"Subagents mismatch. Expected {set(expected_subagents.keys())}, got {set(subagents.keys())}"
        )

    # Load MCP server list for tool validation
    mcp_servers = set()
    if MCP_CONFIG_FILE.exists():
        try:
            mcp_data = json.loads(MCP_CONFIG_FILE.read_text("utf-8"))
            mcp_servers = set(mcp_data.get("mcpServers", {}).keys())
        except Exception:  # noqa: S110
            pass

    for name, exp in expected_subagents.items():
        if name not in subagents:
            continue
        entry = subagents[name]
        if "path" not in entry or "workspaceMode" not in entry:
            errors.append(f"Registry entry {name} missing path or workspaceMode")
            continue

        if entry["workspaceMode"] != exp["mode"]:
            errors.append(
                f"Registry {name} workspaceMode expected {exp['mode']}, got {entry['workspaceMode']}"
            )

        subagent_file = REPO_ROOT / entry["path"]
        if not subagent_file.exists():
            errors.append(f"Subagent file not found: {subagent_file}")
            continue

        try:
            subagent = json.loads(subagent_file.read_text("utf-8"))
        except Exception as e:
            errors.append(f"Failed to parse {subagent_file}: {e}")
            continue

        # Schema checks
        if subagent.get("name") != name:
            errors.append(f"{name}: subagent name mismatch ({subagent.get('name')})")
        if subagent.get("workspaceMode") != exp["mode"]:
            errors.append(
                f"{name}: file workspaceMode expected {exp['mode']}, got {subagent.get('workspaceMode')}"
            )
        if subagent.get("role") != exp["role"]:
            errors.append(
                f"{name}: role expected {exp['role']}, got {subagent.get('role')}"
            )
        if not (0.0 <= subagent.get("temperature", -1) <= 1.0):
            errors.append(
                f"{name}: temperature {subagent.get('temperature')} out of range [0.0, 1.0]"
            )
        if not (1 <= subagent.get("maxSteps", 0) <= 100):
            errors.append(f"{name}: maxSteps {subagent.get('maxSteps')} invalid")
        if not subagent.get("systemPrompt") or len(subagent["systemPrompt"]) < 100:
            errors.append(f"{name}: systemPrompt empty or too short (<100 chars)")

        # Permissions check
        perms = subagent.get("permissions", {})
        if perms.get("fileSystem") != exp.get("fs", "read-only"):
            errors.append(
                f"{name}: fileSystem permission expected {exp.get('fs')}, got {perms.get('fileSystem')}"
            )
        if "terminal" in exp and perms.get("terminal") != exp["terminal"]:
            errors.append(
                f"{name}: terminal permission expected {exp['terminal']}, got {perms.get('terminal')}"
            )
        if "network" in exp and perms.get("network") != exp["network"]:
            errors.append(
                f"{name}: network permission expected {exp['network']}, got {perms.get('network')}"
            )

        if perms.get("fileSystem") not in VALID_FS_PERMS:
            errors.append(f"{name}: invalid fileSystem perm {perms.get('fileSystem')}")
        if perms.get("terminal") not in VALID_BINARY_PERMS:
            errors.append(f"{name}: invalid terminal perm {perms.get('terminal')}")
        if perms.get("network") not in VALID_BINARY_PERMS:
            errors.append(f"{name}: invalid network perm {perms.get('network')}")

        # Tools check
        tools = subagent.get("tools", [])
        if not tools or not isinstance(tools, list):
            errors.append(f"{name}: tools must be a non-empty list")
        for tool in tools:
            if tool in VALID_BUILTIN_TOOLS:
                continue
            mcp_match = re.match(r"^mcp\(([^/]+)/([^)]+)\)$", tool)
            if mcp_match:
                server_name, _tool_name = mcp_match.groups()
                if mcp_servers and server_name not in mcp_servers:
                    errors.append(
                        f"{name}: tool '{tool}' references unknown MCP server '{server_name}'"
                    )
            else:
                errors.append(f"{name}: invalid tool format '{tool}'")

    return errors


def test_mcp_documentation_and_configs() -> list[str]:
    errors = []
    required_docs = [
        "MCP_RECIPES.md",
        "BROWSER_E2E_MCP.md",
        "DB_CACHE_MCP.md",
        "MEMORY_CONTEXT7_MCP.md",
    ]
    for doc_name in required_docs:
        doc_path = DOCS_MCP_DIR / doc_name
        if not doc_path.exists():
            errors.append(f"Missing doc: {doc_path}")
            continue
        content = doc_path.read_text("utf-8")
        if len(content) < 2000:
            errors.append(f"Doc {doc_name} too short (<2000 chars)")

    # Verify ports in DB_CACHE_MCP.md
    db_cache_content = (DOCS_MCP_DIR / "DB_CACHE_MCP.md").read_text("utf-8")
    if "15433" not in db_cache_content:
        errors.append("DB_CACHE_MCP.md missing Postgres port 15433")
    if "63791" not in db_cache_content:
        errors.append("DB_CACHE_MCP.md missing Redis port 63791")

    # Verify global configs
    if not MCP_CONFIG_FILE.exists():
        errors.append(f"Missing {MCP_CONFIG_FILE}")
    else:
        try:
            mcp_cfg = json.loads(MCP_CONFIG_FILE.read_text("utf-8"))
            servers = mcp_cfg.get("mcpServers", {})
            expected_servers = [
                "chrome-devtools-mcp",
                "context7",
                "docker",
                "elasticsearch",
                "github",
                "gopls-mcp-server",
                "kubernetes",
                "memory",
                "minio",
                "playwright",
                "postgres",
                "redis",
                "sequential-thinking",
            ]
            for s in expected_servers:
                if s not in servers:
                    errors.append(f"mcp_config.json missing server '{s}'")
        except Exception as e:
            errors.append(f"Failed to parse mcp_config.json: {e}")

    if not GLOBAL_CONFIG_FILE.exists():
        errors.append(f"Missing {GLOBAL_CONFIG_FILE}")
    else:
        try:
            glb_cfg = json.loads(GLOBAL_CONFIG_FILE.read_text("utf-8"))
            grants = (
                glb_cfg.get("userSettings", {})
                .get("globalPermissionGrants", {})
                .get("allow", [])
            )
            expected_grants = [
                "mcp(chrome-devtools-mcp/*)",
                "mcp(context7/*)",
                "mcp(docker/*)",
                "mcp(elasticsearch/*)",
                "mcp(github/*)",
                "mcp(gopls-mcp-server/*)",
                "mcp(kubernetes/*)",
                "mcp(memory/*)",
                "mcp(minio/*)",
                "mcp(playwright/*)",
                "mcp(postgres/*)",
                "mcp(redis/*)",
                "mcp(sequential-thinking/*)",
            ]
            for g in expected_grants:
                if g not in grants:
                    errors.append(f"config.json missing grant '{g}'")
        except Exception as e:
            errors.append(f"Failed to parse config.json: {e}")

    return errors


def main() -> int:
    print("=== CHALLENGER 2 EMPIRICAL VALIDATION ===")
    subagent_errors = test_subagent_registry_and_files()
    mcp_errors = test_mcp_documentation_and_configs()

    all_errors = subagent_errors + mcp_errors

    print(f"\n[Subagent & Schema Checks]: {'PASS' if not subagent_errors else 'FAIL'}")
    for err in subagent_errors:
        print(f"  - ERROR: {err}")

    print(f"\n[MCP Docs & Config Checks]: {'PASS' if not mcp_errors else 'FAIL'}")
    for err in mcp_errors:
        print(f"  - ERROR: {err}")

    if not all_errors:
        print("\n>>> ALL EMPIRICAL CHALLENGER 2 CHECKS PASSED SUCCESSFULLY <<<")
        return 0
    else:
        print(f"\n>>> FAILED WITH {len(all_errors)} ERRORS <<<")
        return 1


if __name__ == "__main__":
    sys.exit(main())
