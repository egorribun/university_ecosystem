# Original User Request

## Initial Request — 2026-08-21T02:17:08+03:00

Build and configure a production-grade, state-of-the-art developer harness for Antigravity, equipping both workspace-level (.agents/) and global (~/.gemini/config/) environments with deterministic lifecycle hooks, closed-loop quality gates, hierarchical architectural rules, and specialized multi-agent subagent definitions.

Working directory: c:\Users\egorribun\Documents\university_ecosystem
Integrity mode: development

## Requirements

### R1. Deterministic Lifecycle Hook Engine
Implement a robust, cross-platform lifecycle hook system (`hooks.json` driven by an OS-agnostic Python runner) enforcing safety and deterministic feedback:
- `PreToolUse`: Intercept and block dangerous commands (unauthorized file deletions, raw destructive DB operations, sensitive secret leaks).
- `PostToolUse`: Automatically run formatting, type-checks, and syntax validations (Ruff for Python, TypeScript compiler `tsc`, ESLint/Biome) on modified files immediately after edits, returning any errors into the agent's feedback loop.
- `Stop`: Quality gate blocking the agent from stopping or self-certifying completion if any tests, linters, or typecheckers report failures.

### R2. Hierarchical Architectural Rules & Progressive Context
Deploy granular, hierarchical `AGENTS.md` rules throughout repository subdirectories (`app/`, `frontend/`, `services/`, root) defining architectural invariants, gotchas, anti-patterns, and strict type constraints to minimize context pollution and prevent regressions.

### R3. Autonomous Multi-Agent Topology
Configure and define specialized subagent profiles (`lead_architect`, `tdd_developer`, `qa_e2e_tester`, `security_auditor`, `perf_optimizer`) with optimized workspace isolation modes (`branch`, `share`, `inherit`) and specialized system prompts.

### R4. Complete MCP & Verification Tooling Standard
Provide unified configurations and integration recipes for browser E2E validation (Playwright / Chrome DevTools MCP), database & cache state verification (Postgres, Redis MCP), persistent memory graph (`memory` MCP), and real-time library documentation (`context7` MCP).

## Acceptance Criteria

### Lifecycle Hook Execution
- [ ] Hook runner script handles `PreToolUse`, `PostToolUse`, and `Stop` events with valid protojson camelCase payload contracts.
- [ ] Attempting a destructive command (e.g. `rm -rf /` or unauthorized drops) triggers a `deny` or `ask` decision from `PreToolUse`.
- [ ] Editing a Python or TypeScript file immediately triggers automatic formatting and syntax validation.
- [ ] `Stop` hook returns `{"decision": "continue", "reason": "..."}` whenever linters, type checkers, or unit tests fail.

### Rule Coverage & Invariants
- [ ] Domain-scoped `AGENTS.md` exist in root, backend (`app/`), frontend (`frontend/`), and Go services (`services/`).
- [ ] All rules strictly forbid anti-patterns, enforce zero-warning policies, and adhere to progressive disclosure.

### Subagent Definitions & Multi-Agent Workflows
- [ ] Subagent definitions are created and ready for invocation via `invoke_subagent`.
- [ ] Subagent configs correctly specify workspace modes (`share` / `branch`) for non-destructive, isolated task execution.

### End-to-End Verification
- [ ] Verification script (`verify_harness.py`) passes 100% of test cases verifying hook payloads, lint triggers, and subagent invocation contracts.

## Follow-up — 2026-08-21T00:40:15Z

Refactor .gitignore to persistently track Antigravity developer harness assets (.agents/hooks, .agents/subagents, .agents/skills, docs/mcp, verify_harness.py), perform a comprehensive audit and synchronization across all markdown documentation files in the repository to eliminate outdated information and broken references, and cleanly commit all changes strictly following repository invariants.

Working directory: c:\Users\egorribun\Documents\university_ecosystem
Integrity mode: development

## Requirements

### R1. Refactor .gitignore & Track Harness Assets
Update `.gitignore` so that permanent harness assets in `.agents/` (`hooks.json`, `hooks/`, `subagents.json`, `subagents/`, `skills/`, `ORIGINAL_REQUEST.md`), `verify_harness.py`, `scripts/verify_challenger_*.py`, and `docs/mcp/` are properly tracked in Git, while ensuring transient runtime caches (`.agents/**/__pycache__/`, `.agents/**/.gate_state.json`, `.agents/sentinel/`, temporary worker logs) remain ignored.

### R2. Comprehensive Markdown Documentation Audit
Conduct an exhaustive audit of all project markdown documentation (`AGENTS.md`, `CLAUDE.md`, `README.md`, `README.ru.md`, `PROJECT.md`, `TEST_INFRA.md`, `TEST_READY.md`, `app/AGENTS.md`, `frontend/AGENTS.md`, `services/AGENTS.md`, `docs/mcp/*.md`, `docs/audits/INDEX.md`):
- Ensure all file paths, component references, CLI commands, and architectural descriptions reflect the true current state of the workspace.
- Eliminate broken links, contradictory guidelines, obsolete notes, and misinformation.
- Ensure strict formatting, correct Markdown link syntax, and consistency across Russian and English documentation.

### R3. Clean Git Commit
Stage and commit all modified, untracked, and unignored files using clean, structured commit messages adhering to repository invariants (strictly forbidding `Co-Authored-By` trailers).

## Acceptance Criteria

### Repository Tracking & .gitignore
- [ ] `.gitignore` is refined to allow tracking of `.agents/hooks/`, `.agents/subagents/`, `.agents/skills/`, `docs/mcp/`, and `verify_harness.py`.
- [ ] Running `git status` shows all core harness files and documentation files staged or tracked.
- [ ] Ephemeral caches and runtime directories (`__pycache__`, temporary logs) remain safely ignored.

### Documentation Integrity
- [ ] All `.md` files contain valid, verifiable paths and accurate command references.
- [ ] No dead links, phantom references, or outdated architectural claims exist.
- [ ] Root `AGENTS.md`, `CLAUDE.md`, and domain `AGENTS.md` files are fully aligned.

### Verification & Commit Execution
- [ ] `python verify_harness.py` passes with 100% success rate.
- [ ] `git status` confirms a clean working tree after commits with zero unstaged or lost modifications.
- [ ] Zero `Co-Authored-By` trailers in commit history.

