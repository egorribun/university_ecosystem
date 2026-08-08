# Quality Closure to Reference State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every actionable requirement in `docs/testing/roadmap-100-percent-quality-closure-plan.md`, prove the result with fresh local and GitHub evidence, and publish all repository changes.

**Architecture:** Treat the roadmap as an evidence contract, not as a checklist of YAML files. First build a current gap matrix from the repository, CI runs, ruleset, secrets, and coverage manifests; then repair code/workflows/tests and rerun the affected gates. External state that cannot be fabricated, such as a secret value or a 30-day stabilization window, is represented by an automated fail-closed check and a precise residual record rather than marked complete without evidence.

**Tech Stack:** Python 3.14/pytest/coverage/mutmut, React 19/Vitest/V8/Stryker/fast-check, Go 1.26/race/fuzz/goleak, Rust/cargo-llvm-cov/proptest/Miri, Playwright, Checkov, Kyverno, GitHub Actions, GitHub rulesets, Codecov, Pact, k6/load-chaos, Markdown.

## Global Constraints

- Preserve the repository's `egorribun` branch convention and commit without a `Co-Authored-By` trailer.
- Keep testing and coverage work independent of wave numbering in audit records and commit messages.
- Keep Python relationships explicitly `lazy="noload"`, frontend validation Valibot-only, and all project-specific AGENTS.md security/error-handling rules intact.
- Do not weaken `quality/quality-contract.json`, mutation policy, diff coverage, or Tier0 requirements to make a gate pass.
- Use `apply_patch` for repository edits and explicit paths for staging; preserve unrelated worktree changes.
- Do not claim closure until fresh command output or fresh GitHub evidence proves each stated requirement.

---

### Task 1: Build the current closure matrix

**Files:**
- Read: `docs/testing/roadmap-100-percent-quality-closure-plan.md`
- Read: `quality/quality-contract.json`
- Read: `quality/coverage-manifest.schema.json`
- Read: `.github/workflows/ci.yml`
- Read: `.github/workflows/nightly-full-gate.yml`
- Read: `.github/workflows/checkov.yml`
- Read: `quality/ownership-mapping.json`
- Modify: `docs/testing/roadmap-100-percent-quality-closure-plan.md`

**Interfaces:**
- Consumes: roadmap requirements, current HEAD, ruleset data, GitHub secret names, workflow results, coverage manifest artifacts, and local tool versions.
- Produces: a line-item matrix classifying every former open item as closed, failing, advisory, manual, or time-window dependent, with exact evidence identifiers.

- [ ] **Step 1: Capture repository and GitHub baseline.**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
gh auth status
gh api repos/egorribun/university_ecosystem/rulesets/8335285
gh secret list
gh run list --workflow nightly-full-gate.yml --limit 20 --json databaseId,headSha,status,conclusion,createdAt
```

Expected: a clean worktree, authenticated GitHub access, the active ruleset, secret inventory, and the complete recent nightly history.

- [ ] **Step 2: Reconcile every `Still open`, `Task G.*`, and Phase 0–10/14 item with current code and CI.**

Run:

```powershell
rg -n "Still open|Task [G0-9]|Phase [0-9]+|advisory|30 consecutive|CODECOV|Miri|Stryker|Pact|DAST|performance" docs/testing/roadmap-100-percent-quality-closure-plan.md .github/workflows quality scripts
```

Expected: no item is silently omitted from the matrix.

- [ ] **Step 3: Record only evidence-backed changes in the roadmap.**

Use the existing audit section format and include the exact commit/run IDs, metric source, and residual reason for each unresolved external gate.

- [ ] **Step 4: Run the roadmap contract tests.**

Run: `uv run pytest tests/test_quality_contract.py tests/test_coverage_manifest.py tests/test_quality_workflow_contract.py tests/test_quality_certification_dashboard.py -q`

Expected: zero failures.

### Task 2: Close coverage and mutation enforcement without weakening targets

**Files:**
- Read/Modify as required: `quality/quality-contract.json`, `quality/mutation-exclusions.json`, `scripts/quality/normalize_coverage_reports.py`, `scripts/quality/validate_quality_contract.py`
- Read/Modify as required: `.github/workflows/ci.yml`, `.github/workflows/nightly-full-gate.yml`, `.github/workflows/reusable-frontend-tests.yml`, `.github/workflows/reusable-backend-tests.yml`
- Test: `tests/test_quality_contract.py`, `tests/test_coverage_manifest.py`, relevant stack tests under `tests/`

**Interfaces:**
- Consumes: Task 1's gap matrix and raw reports from Python, frontend, Go, and Rust.
- Produces: strict, reproducible aggregate/per-file coverage and mutation evidence with no silent skips or unsupported-report masquerading.

- [ ] **Step 1: Generate fresh Python, frontend, Go, and Rust reports using the repository CI commands.**
- [ ] **Step 2: Normalize all reports through `normalize_coverage_reports.py` and validate the manifest through `validate_quality_contract.py --manifest`.**
- [ ] **Step 3: Run incremental and full mutation gates; if a clean-test failure or survivor appears, reproduce it with the smallest affected test set, add a behavior-level regression test, and rerun the mutation gate.**
- [ ] **Step 4: Run frontend Stryker and fast-check closure for the complete authored diff and nightly full scope; keep equivalent-mutant exclusions empty unless a documented, independently proven equivalence exists.**
- [ ] **Step 5: Verify Tier0 line/branch/function coverage per file and ensure the generator status and validator semantics agree with the roadmap's enforcement phase.**

### Task 3: Close integration, browser, security, performance, and infrastructure gates

**Files:**
- Read/Modify as required: `.github/workflows/nightly-full-gate.yml`, `.github/workflows/ci.yml`, `.github/workflows/checkov.yml`, `.checkov.yml`, `k8s/`, `docker-compose*.yml`, `tests/contracts/`, `tests/e2e/`, performance/security workflow files
- Test: Go integration suites, Pact provider replay, Playwright browser matrix, Kyverno tests, Checkov, DAST, performance and chaos workflows

**Interfaces:**
- Consumes: the exact failing job logs and artifacts from Task 1/2.
- Produces: green current-HEAD integration/browser/security/performance evidence or a narrowly scoped code/workflow fix with a regression test.

- [ ] **Step 1: Re-run current-HEAD nightly-full-gate and capture each job result/artifact.**
- [ ] **Step 2: Reproduce each failure locally where platform support exists; install only missing test tools required by the repository's documented commands.**
- [ ] **Step 3: Fix the smallest root cause, add or strengthen the corresponding regression/contract test, and rerun the affected job locally.**
- [ ] **Step 4: Verify Pact consumer/provider replay, all four Playwright projects, Checkov blocking behavior, Kyverno policy tests, negative security suites, DAST, load/chaos, and performance thresholds.**
- [ ] **Step 5: Do not promote an advisory check until the repository has actual green evidence for the documented stabilization window; add an automated window calculator if the current workflow cannot prove it.**

### Task 4: Resolve governance and external service dependencies safely

**Files:**
- Read/Modify as required: `.github/workflows/checkov.yml`, Codecov workflow/configuration files, `quality/ownership-mapping.json`, `.github/CODEOWNERS`, `AGENTS.md`, `docs/testing/roadmap-100-percent-quality-closure-plan.md`

**Interfaces:**
- Consumes: GitHub ruleset/check-run names, secret inventory, Codecov upload behavior, and ownership validation output.
- Produces: fail-closed governance configuration, accurate ownership, and an explicit external-action record when a secret or time window cannot be supplied by repository changes.

- [ ] **Step 1: Verify all required status checks against real check-run display names and compare them with the current ruleset.**
- [ ] **Step 2: Make Checkov and coverage upload failures observable and blocking without hiding findings behind `soft_fail` or `continue-on-error`.**
- [ ] **Step 3: Verify Codecov using the supported current authentication path; if a secret value is genuinely required, add a preflight that fails with an actionable message and record the exact user-only action rather than inventing a token.**
- [ ] **Step 4: Validate ownership mapping and bypass-policy documentation with the inventory checker.**
- [ ] **Step 5: Recheck the 30-day promotion rule from actual run timestamps; never synthesize historical green days.**

### Task 5: Final verification, publication, and handoff

**Files:**
- Modify: only files proven necessary by Tasks 1–4
- Verify: all changed files, generated artifacts, commit, branch, and remote runs

- [ ] **Step 1: Run the complete relevant local checks from AGENTS.md plus `git diff --check`, targeted regressions, and final coverage/quality validation.**
- [ ] **Step 2: Review `git status`, the complete diff, and staged paths; remove only verified generated temporary files.**
- [ ] **Step 3: Commit with the repository's required style and no `Co-Authored-By` trailer.**
- [ ] **Step 4: Push `egorribun`, verify `git ls-remote`, and monitor all triggered GitHub checks to completion.**
- [ ] **Step 5: Re-read this plan and the roadmap, confirm every criterion's evidence or documented external blocker, then mark the goal complete only when no repository-side work remains.**
