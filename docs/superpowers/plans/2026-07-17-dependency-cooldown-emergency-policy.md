# Dependency Cooldown Emergency Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce a seven-day maturity window for routine dependency updates without delaying visibility of security advisories, while making every urgent cooldown exception targeted, reviewable, and reproducible.

**Architecture:** `pyproject.toml` is the authoritative uv resolver policy. Renovate gives every routine package rule an explicit seven-day minimum release age. Its sole security exception uses the boolean `minimumReleaseAge: false` and is last, so it overrides routine matching rules, security alerts remain visible immediately, and they cannot automerge until a human follows the targeted override runbook. This is Renovate's explicit no-delay representation; Renovate documents that `"0 days"` is treated as null, while the current Semgrep rule accepts only `"7 days"` or `false`. A deterministic pytest module parses the three policy artifacts and prevents a future ordering change from silently delaying security alerts or broadening the override.

**Tech Stack:** uv 0.11.28+, Renovate JSON configuration, TOML/JSON/text parsing with Python 3.14 standard library, pytest, Docker only when the local host lacks Rust for a truthful `uv lock` regeneration.

## Global Constraints

- Work only in `C:\Users\egorribun\Documents\university_ecosystem\.worktrees\quality-roadmap` on `codex/quality-roadmap`.
- Keep `exclude-newer = "7 days"` in the existing root `[tool.uv]` table; do not create a root `uv.toml`, because it would override the existing uv project settings.
- Keep ordinary PyPI updates behind the same seven-day window in Renovate, as recommended by the uv Renovate integration guide. Give every other non-security Renovate package rule the same explicit seven-day value so the Semgrep supply-chain gate and policy agree.
- Preserve immediate security-update visibility with the one explicit `minimumReleaseAge: false` exception, disable its automerge, place it after every routine package rule, and make the targeted emergency procedure mandatory before merge.
- The emergency command may exempt only an explicitly named package with `--exclude-newer-package "<package>=false"`; do not use `--exclude-newer false`, `UV_EXCLUDE_NEWER=false`, a `nosemgrep` suppression, `SKIP=semgrep`, or `--no-verify`.
- An emergency PR must record the advisory identifier, package, selected version, exact command, lockfile diff, test evidence, and security review. A dependency version change remains subject to the normal vulnerability gate.
- Regenerate `uv.lock` with `uv lock`, never `uv lock --upgrade`; reject any package-version churn not directly required by the policy metadata.
- Preserve the already staged Wave 0.3 coverage work; this prerequisite exists solely to make its normal security hook truthful and passable.

---

## File Structure

- `tests/test_dependency_resolution_policy.py` — deterministic regression tests for uv, Renovate rule precedence, alert settings, and the emergency runbook.
- `pyproject.toml` — project-local seven-day resolver cooldown.
- `renovate.json` — explicit seven-day routine rules plus one final non-automerge security exception.
- `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md` — operator procedure for a targeted, auditable CVE exception.
- `uv.lock` — uv-generated metadata proving the configured cooldown; no intentional dependency-version changes.

### Task 1: Cooldown policy and audited targeted exception

**Files:**

- Create: `tests/test_dependency_resolution_policy.py`
- Create: `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`
- Modify: `pyproject.toml`
- Modify: `renovate.json`
- Modify: `uv.lock`

**Interfaces:**

- Consumes: root `[tool.uv]`, root `renovate.json`, and the emergency runbook.
- Produces: a seven-day default resolver policy, immediate but non-automerge security visibility, and a package-scoped command that allows urgent lock regeneration without disabling the policy globally.

- [ ] **Step 1: Write the failing policy tests**

Create `tests/test_dependency_resolution_policy.py` with standard-library parsing only. The tests must assert the global uv value, find the final security rule by its semantics, require every other Renovate package rule to carry the explicit seven-day default, require `automerge is False` and the boolean exception on security updates, require both OSV and Renovate vulnerability alerts enabled, and require the runbook's targeted command and audit fields.

```python
assert pyproject["tool"]["uv"].get("exclude-newer") == "7 days"
assert security_rule_index == len(package_rules) - 1
assert all(rule["minimumReleaseAge"] == "7 days" for rule in package_rules[:-1])
assert security_rule["minimumReleaseAge"] is False
assert security_rule["automerge"] is False
assert "--exclude-newer-package \"<package>=false\"" in runbook
assert "Do not use `UV_EXCLUDE_NEWER=false`" in runbook
```

- [ ] **Step 2: Run the focused RED test**

Run:

```powershell
C:\Users\egorribun\Documents\university_ecosystem\.venv\Scripts\python.exe -m pytest tests\test_dependency_resolution_policy.py -q --basetemp .tmp\dependency-cooldown-red
```

Expected: assertions fail because the root uv cooldown and runbook do not exist, and Renovate has only the old three-day/auto-merge policy.

- [ ] **Step 3: Implement the minimum policy and runbook**

At the start of the existing `[tool.uv]` table, add:

```toml
# Semgrep supply-chain cooldown; targeted incident exceptions use the runbook.
exclude-newer = "7 days"
```

Set `minimumReleaseAge` to `"7 days"` on every existing non-security `packageRules` entry, including the general PyPI rule. Put this one security rule **last** in `packageRules`, after every routine rule, so Renovate's later matching rule wins for a security advisory:

```json
{
  "description": "Surface security updates immediately; require an audited targeted uv cooldown override",
  "matchCategories": ["security"],
  "automerge": false,
  "minimumReleaseAge": false,
  "labels": ["security", "manual-cooldown-override-required"]
}
```

Create `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`. It must require a CVE/GHSA/OSV identifier, the exact affected package and fixed version, a security reviewer, an ordinary PR, the exact targeted command below, `uv lock --check`, relevant test/vulnerability-gate evidence, and a review of the `uv.lock` diff. It must state that broad cooldown disablement and automatic merge are prohibited.

```bash
uv lock --upgrade-package "<package>" --exclude-newer-package "<package>=false"
```

- [ ] **Step 4: Regenerate and inspect the lockfile without an upgrade sweep**

Use a Rust-capable environment matching the project toolchain, then run:

```bash
uv lock
uv lock --check
git diff -- uv.lock
```

Expected: uv writes `exclude-newer` metadata and `exclude-newer-span = "P7D"`; package-version entries do not change. If the local Windows host cannot load a Rust toolchain, use an ephemeral Docker image containing pinned Python 3.14, Rust 1.94.1, and uv 0.11.28, mount only this worktree, execute the same commands, then remove the temporary image and helper file.

- [ ] **Step 5: Run focused GREEN verification**

Run:

```powershell
C:\Users\egorribun\Documents\university_ecosystem\.venv\Scripts\python.exe -m pytest tests\test_dependency_resolution_policy.py tests\test_quality_configuration.py -q --basetemp .tmp\dependency-cooldown-green
C:\Users\egorribun\Documents\university_ecosystem\.venv\Scripts\python.exe -m ruff check tests\test_dependency_resolution_policy.py tests\test_quality_configuration.py
C:\Users\egorribun\Documents\university_ecosystem\.venv\Scripts\python.exe -m ruff format --check tests\test_dependency_resolution_policy.py tests\test_quality_configuration.py
git diff --check
```

Expected: both modules pass, Ruff is clean, and no whitespace error is reported. Run `uv lock --check` inside the Rust-capable environment when the local worktree venv cannot load `rust_ext`.

- [ ] **Step 6: Commit only after independent review**

Stage only the five files above together with the already verified Wave 0.3 coverage files and the hook-required `.secrets.baseline` refresh. Run the normal pre-commit hooks without any skip, then commit with:

```bash
git commit -m "feat(wave212): align coverage and dependency policies"
```

## Plan Self-Review

- Spec coverage: the task gives every routine Renovate package rule Semgrep's required seven-day default, matches uv's PyPI timing, retains immediate security visibility through the one final boolean exception, disables silent security automerge, and supplies an auditable package-specific exception.
- Truthfulness: the targeted uv command does not claim that a generic zero-day path is safe; a human must review the advisory and lockfile diff before merging.
- Scope: no application runtime behavior, package version, broad override, lockfile upgrade sweep, or external deployment state is changed.
- Placeholder scan: all file paths, policy values, commands, test invariants, and forbidden alternatives are explicit.
