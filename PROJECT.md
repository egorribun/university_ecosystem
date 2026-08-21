# Project: Antigravity Developer Harness Implementation

## Architecture
The Antigravity Developer Harness equips both workspace-level (`.agents/`) and global (`~/.gemini/config/`) environments with deterministic lifecycle hooks, closed-loop quality gates, hierarchical architectural rules, specialized multi-agent subagent topologies, and unified MCP tooling recipes.

```
university_ecosystem/
├── .agents/
│   ├── hooks.json                      # Antigravity hook declaration (PreToolUse, PostToolUse, Stop)
│   ├── hooks/
│   │   ├── runner.py                  # OS-agnostic CLI runner entry point
│   │   ├── pre_tool_safety.py         # Intercepts & blocks destructive commands / drops / leaks
│   │   ├── post_tool_linter.py        # Automated formatting (Ruff, tsc, gofmt) on file edit
│   │   ├── stop_quality_gate.py       # Blocks stop if linters, typecheckers, or tests fail
│   │   └── common.py                  # Stdio JSON protojson serialization & error handling
│   ├── subagents.json                 # Master subagent registry
│   └── subagents/
│       ├── lead_architect.json        # Lead architect profile (inherit)
│       ├── tdd_developer.json         # TDD developer profile (branch)
│       ├── qa_e2e_tester.json         # QA & browser tester profile (share)
│       ├── security_auditor.json      # Security & crypto auditor profile (inherit)
│       └── perf_optimizer.json        # Performance optimizer profile (inherit)
├── AGENTS.md                          # Root workspace standards, CI/CD, Git rules, quality contract
├── app/
│   └── AGENTS.md                      # Backend Python 3.14, FastAPI, SQLAlchemy (lazy=noload), Dishka DI
├── frontend/
│   └── AGENTS.md                      # Frontend React 19, Valibot, TanStack Router/Query, Zustand, SSR
├── services/
│   └── AGENTS.md                      # Go microservices (ws-hub, gateway, file-processor, Caddy)
├── docs/mcp/
│   ├── MCP_RECIPES.md                 # Complete catalog and integration recipes for all MCP servers
│   ├── BROWSER_E2E_MCP.md             # Playwright and Chrome DevTools MCP recipe
│   ├── DB_CACHE_MCP.md                # Postgres and Redis MCP recipe
│   └── MEMORY_CONTEXT7_MCP.md         # Persistent Memory and Context7 live docs recipe
└── verify_harness.py                  # 100% automated test suite verifying all harness subsystems
```

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F1 | `hooks.json` Configuration | Antigravity lifecycle hook declaration matching tool calls and events | M1 | ORIGINAL_REQUEST §R1 |
| F2 | Hook Runner CLI Entry Point | Cross-platform Python runner supporting `pre-tool`, `post-tool`, and `stop` commands | M1 | ORIGINAL_REQUEST §R1 |
| F3 | Protojson camelCase Serializer | Strict camelCase JSON I/O protocol handler conforming to Antigravity hook contracts | M1 | ORIGINAL_REQUEST §R1 |
| F4 | PreToolUse Safety Interceptor | Blocks destructive commands (`rm -rf /`, raw DB drops, secret exfiltration) returning `deny`/`ask` | M1 | ORIGINAL_REQUEST §R1 |
| F5 | PostToolUse Automated Linter | Triggers in-place formatting & syntax validation (`ruff`, `tsc`, `gofmt`) upon file edits | M1 | ORIGINAL_REQUEST §R1 |
| F6 | Stop Quality Gate Enforcement | Prevents agent stop (`decision: continue`) when linters, typecheckers, or tests report failures | M1 | ORIGINAL_REQUEST §R1 |
| F7 | Root `AGENTS.md` Rules | Workspace-wide Git rules, zero-warning quality contract (100% coverage), CI/CD, Docker/K8s | M2 | ORIGINAL_REQUEST §R2 |
| F8 | Backend `app/AGENTS.md` Rules | Python 3.14, FastAPI, SQLAlchemy 2.0 (`lazy="noload"`), Dishka DI (TD-33-08), Argon2id | M2 | ORIGINAL_REQUEST §R2 |
| F9 | Frontend `frontend/AGENTS.md` Rules | React 19, TypeScript strict, TanStack Router/Query, Zustand, Valibot-only, SSR, ARIA | M2 | ORIGINAL_REQUEST §R2 |
| F10 | Services `services/AGENTS.md` Rules | Go 1.22+, `ws-hub` locks/frames, `gateway` JWKS/XFetch, `file-processor` envs/GraphQL, Caddy | M2 | ORIGINAL_REQUEST §R2 |
| F11 | `lead_architect` Subagent Profile | Subagent profile with `inherit` mode, ADR governance, Dishka DI and architecture rules | M3 | ORIGINAL_REQUEST §R3 |
| F12 | `tdd_developer` Subagent Profile | Subagent profile with `branch` mode for isolated RED-GREEN-REFACTOR execution | M3 | ORIGINAL_REQUEST §R3 |
| F13 | `qa_e2e_tester` Subagent Profile | Subagent profile with `share` mode, Playwright & Chrome DevTools MCP, ARIA & hydration tests | M3 | ORIGINAL_REQUEST §R3 |
| F14 | `security_auditor` Subagent Profile | Subagent profile with `inherit` mode, Argon2id, RS256 JWKS, path traversal, detect-secrets | M3 | ORIGINAL_REQUEST §R3 |
| F15 | `perf_optimizer` Subagent Profile | Subagent profile with `inherit` mode, EXPLAIN ANALYZE, TieredCache, bundle budget (<500 KB) | M3 | ORIGINAL_REQUEST §R3 |
| F16 | Master Subagent Registry | `.agents/subagents.json` indexing all subagents with path and workspaceMode mappings | M3 | ORIGINAL_REQUEST §R3 |
| F17 | Browser E2E MCP Recipe | Playwright and Chrome DevTools MCP configuration, tool mappings, and verification recipes | M4 | ORIGINAL_REQUEST §R4 |
| F18 | Database & Cache MCP Recipe | Postgres (port 15433) and Redis (port 63791) MCP configs, queries, and state assertions | M4 | ORIGINAL_REQUEST §R4 |
| F19 | Persistent Memory & Context7 Recipe | Memory MCP graph persistence and Context7 live library API documentation recipes | M4 | ORIGINAL_REQUEST §R4 |
| F20 | MCP Master Guide (`MCP_RECIPES.md`) | Comprehensive catalog and workflow guide across all 14 configured MCP servers | M4 | ORIGINAL_REQUEST §R4 |
| F21 | `verify_harness.py` Harness Test Suite | Comprehensive test suite (7 test classes, 100% assertions pass) verifying all harness subsystems | M5 | ORIGINAL_REQUEST Acceptance |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | Deterministic Lifecycle Hook Engine | F1, F2, F3, F4, F5, F6: `.agents/hooks.json` & `.agents/hooks/` (`runner.py`, `pre_tool_safety.py`, `post_tool_linter.py`, `stop_quality_gate.py`, `common.py`) | none | DONE |
| M2 | Hierarchical Architectural Rules | F7, F8, F9, F10: Refactor root `AGENTS.md`, create `app/AGENTS.md`, `frontend/AGENTS.md`, `services/AGENTS.md` | none | DONE |
| M3 | Autonomous Multi-Agent Topology | F11, F12, F13, F14, F15, F16: `.agents/subagents/` (5 profiles) & `.agents/subagents.json` | none | DONE |
| M4 | MCP & Tooling Integration Recipes | F17, F18, F19, F20: `docs/mcp/` (`MCP_RECIPES.md`, `BROWSER_E2E_MCP.md`, `DB_CACHE_MCP.md`, `MEMORY_CONTEXT7_MCP.md`) | none | DONE |
| M5 | E2E Verification & Harness Testing | F21: Implement `verify_harness.py` with 7 test suites, pass 100% test cases | M1, M2, M3, M4 | DONE |

---

## Interface Contracts

### 1. Antigravity Hook Runner Contract
- **Event Inputs (stdin)**: JSON with camelCase fields:
  - `PreToolUse`: `{"conversationId": string, "workspacePaths": string[], "stepIdx": int, "toolCall": {"name": string, "args": object}}`
  - `PostToolUse`: `{"conversationId": string, "workspacePaths": string[], "stepIdx": int, "toolCall": {"name": string, "args": object}, "error": string}`
  - `Stop`: `{"conversationId": string, "workspacePaths": string[], "executionNum": int, "terminationReason": string, "error": string, "fullyIdle": bool}`
- **Event Outputs (stdout)**:
  - `PreToolUse`: `{"decision": "allow" | "deny" | "ask" | "force_ask", "reason": string}`
  - `PostToolUse`: `{}`
  - `Stop`: `{"decision": "continue", "reason": string}` (when failing) or `{"decision": "allow"}` / `{}` (when passing).

### 2. Subagent Definition Schema
```json
{
  "name": "string",
  "displayName": "string",
  "description": "string",
  "role": "string",
  "workspaceMode": "branch | share | inherit",
  "model": "string",
  "temperature": "number",
  "maxSteps": "number",
  "tools": ["string"],
  "permissions": {
    "fileSystem": "read-only | read-write",
    "terminal": "allow | deny",
    "network": "allow | deny"
  },
  "systemPrompt": "string"
}
```

---

## Code Layout

- `.agents/hooks.json`
- `.agents/hooks/runner.py`
- `.agents/hooks/pre_tool_safety.py`
- `.agents/hooks/post_tool_linter.py`
- `.agents/hooks/stop_quality_gate.py`
- `.agents/hooks/common.py`
- `AGENTS.md` (root)
- `app/AGENTS.md`
- `frontend/AGENTS.md`
- `services/AGENTS.md`
- `.agents/subagents.json`
- `.agents/subagents/lead_architect.json`
- `.agents/subagents/tdd_developer.json`
- `.agents/subagents/qa_e2e_tester.json`
- `.agents/subagents/security_auditor.json`
- `.agents/subagents/perf_optimizer.json`
- `docs/mcp/MCP_RECIPES.md`
- `docs/mcp/BROWSER_E2E_MCP.md`
- `docs/mcp/DB_CACHE_MCP.md`
- `docs/mcp/MEMORY_CONTEXT7_MCP.md`
- `verify_harness.py`
