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

## Follow-up — 2026-08-21T01:37:02Z

Use a very large team of agents. Autonomously diagnose, repair, and verify all 13 failing and 1 cancelled CI/CD checks on GitHub Pull Request #1249 while conducting an exhaustive, full-stack architectural and code quality audit across the entire University Ecosystem Platform to establish a hardened, zero-debt MVP foundation.

Working directory: c:\Users\egorribun\Documents\university_ecosystem
Integrity mode: development

## Requirements

### R1. Automated CI/CD Check Resolution for PR #1249
Identify the root causes of all failing and cancelled checks across all test shards, linter gates, mutation testing, E2E browser tests, security scanners, and benchmark gates on active PR #1249. Implement clean, robust fixes without weakening assertions, bypassing quality gates, or introducing regressions.

### R2. Comprehensive Multi-Stack Codebase Audit & Polishing
Perform an exhaustive code quality, security, and architectural audit across every component: Python 3.14 FastAPI backend, React 19 / TypeScript frontend, Go 1.22+ microservices (`gateway`, `ws-hub`, `file-processor`), native Rust optimizer, Helm charts, and Kubernetes manifests. Eliminate dead code, type inaccuracies, antipatterns, missing error handling, and unmanaged test skips.

### R3. Quality Contract & System Harmony Verification
Ensure strict compliance with `quality/quality-contract.json` across statement, branch, and function coverage metrics on critical paths. Validate that pre-commit hooks, static analysis tools (`ruff`, `mypy`, `golangci-lint`, `bandit`, `semgrep-sast`), and runtime security checks pass with zero warnings, guaranteeing harmonious inter-service communication across REST, gRPC, WebSocket, and GraphQL interfaces.

### R4. Autonomous Git & Subsystem Delivery
Incrementally commit fixes per subsystem adhering to domain `AGENTS.md` conventions (using `feat(waveXX): ...` / `fix(waveXX): ...` commit messages, strictly omitting `Co-Authored-By`), push to branch `egorribun`, and iterate autonomously using GitHub CLI (`gh`) until all PR check runs are completely green.

## Acceptance Criteria

### PR CI/CD & Harness Integrity
- [ ] All 14 previously failing and cancelled GitHub Actions check runs on PR #1249 pass with green status (`conclusion: SUCCESS`).
- [ ] `python verify_harness.py` passes 100% of lifecycle, safety, and subagent tests with 0 errors.

### Backend Subsystem (Python 3.14 + FastAPI + Dishka DI)
- [ ] `python -m ruff check app/` and `python -m ruff format --check app/` report 0 errors and 0 warnings.
- [ ] `python -m mypy --config-file pyproject.toml app/` passes with 0 type errors.
- [ ] `python scripts/custom_ast_linter.py app/` and `python scripts/check_no_python2_except.py` pass cleanly.
- [ ] All pytest test shards (unit, integration, query plans, auth cookie flow, docker startup contracts) pass without unmanaged dynamic skips.
- [ ] Mutmut incremental mutation stats and Schemathesis API conformance gates pass.

### Frontend Subsystem (React 19 + TypeScript + Vite SSR)
- [ ] `cd frontend && npx tsc --noEmit` completes with 0 type diagnostics.
- [ ] `cd frontend && npm run lint` passes with 0 warnings.
- [ ] `cd frontend && npm run test` passes all component and store tests.
- [ ] `cd frontend && npm run build` succeeds without SSR or bundling defects.
- [ ] Playwright E2E test matrix across Chromium, Firefox, WebKit, and Mobile WebKit executes without timeouts or selector failures.

### Go Microservices (gateway, ws-hub, file-processor)
- [ ] `golangci-lint run` passes cleanly across all services in `services/`.
- [ ] `go test -v -race ./...` passes without race conditions or leaks.
- [ ] WS-Hub paired benchmark comparison passes with 0 performance regressions.

### Security, Infra & Code Integrity
- [ ] Pre-commit tools (`detect-secrets`, `gitleaks`, `bandit`, `semgrep-sast`, `renovate-config-validator`) pass with clean baseline.
- [ ] All Helm charts in `charts/` and Kubernetes manifests in `k8s/` pass validation and Kyverno security policies.
- [ ] All git commits are clean, properly formatted, and strictly exclude any `Co-Authored-By` trailers.
