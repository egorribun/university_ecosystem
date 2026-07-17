# Renovate Cooldown Policy Validator Correction Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` task-by-task. This correction must be reviewed
> independently before it is considered accepted.

**Goal:** Replace the invalid `minimumReleaseAge: false` workaround with a
schema-valid, immediate, non-automerge security-alert path, and make official
Renovate configuration validation a blocking CI check.

**Why this correction is required:** Semgrep's current Renovate rule accepts
`"7 days"` or `false` in a `packageRules` entry. The official Renovate schema
and `renovate-config-validator` accept `minimumReleaseAge` only as a string or
`null`; the boolean therefore makes the repository configuration invalid. The
official `vulnerabilityAlerts` object is the valid special path: it defaults to
`minimumReleaseAge: null` and `prCreation: immediate`, applies to security fix
PRs, and avoids a Semgrep-scanned security `packageRules` exception.

**Architecture:** All ordinary `packageRules` keep the explicit seven-day
maturity window. Remove the `matchCategories: ["security"]` package rule
entirely. Configure the official `vulnerabilityAlerts` object explicitly with
`minimumReleaseAge: null`, `prCreation: "immediate"`, `automerge: false`, and
the existing security/manual-override labels. Renovate applies that object to
GitHub and OSV vulnerability package rules as a forced child configuration, so
the valid immediate security path overrides normal maturity rules without a
global uv bypass. A pinned Renovate CLI validation target runs locally and in
CI; deterministic pytest tests the intended policy shape and the CI contract.

**Tech stack:** official Renovate pre-commit hook `43.268.4`
(`ece9d8611e4e7da8cbcf7ea28039ec7928316032`),
`renovate-config-validator --strict`, existing SHA-pinned pre-commit GitHub
Action, pytest with standard-library TOML/JSON/text parsing, existing uv lock
validation.

## Constraints

- Work only in `C:\\Users\\egorribun\\Documents\\university_ecosystem\\.worktrees\\quality-roadmap` on `codex/quality-roadmap`.
- Do not rewrite, reset, or bypass the prior commit. Make a narrow corrective
  commit on top of it.
- Do not use Semgrep suppression, `SKIP=semgrep`, `--no-verify`, a broad uv
  cooldown disablement, or a package-version upgrade sweep.
- Retain `pyproject.toml` `exclude-newer = "7 days"`; emergency lock regeneration
  remains exactly package-scoped through the existing runbook command.
- Every `packageRules` item must explicitly retain `minimumReleaseAge: "7 days"`.
  There must be no `matchCategories: ["security"]` item and no boolean value for
  `minimumReleaseAge` anywhere in `renovate.json`.
- `vulnerabilityAlerts` must remain enabled and explicitly set
  `minimumReleaseAge: null`, `prCreation: "immediate"`, `automerge: false`, and
  labels `security` plus `manual-cooldown-override-required`.
- Keep `osvVulnerabilityAlerts: true`; Renovate's vulnerability pipeline uses
  the `vulnerabilityAlerts` child configuration for both GitHub alerts and its
  OSV-derived vulnerability package rules.
- Add the official `renovatebot/pre-commit-hooks` hook at exact release `43.268.4`
  (immutable commit `ece9d8611e4e7da8cbcf7ea28039ec7928316032`) with
  `args: [--strict]` and `pass_filenames: false`. The latter is essential:
  Renovate treats a supplied filename as global/self-hosted config, while no
  filename discovers root `renovate.json` as repository config.
- The existing `pre-commit-check` action deliberately tolerates ordinary hook
  exit code 1 so formatters can autofix. Add a separate blocking shell step in
  that existing job; it already participates in `ci-success`, so no new CI job,
  action, Node setup, or aggregation wiring is needed.

## File Structure

- Modify: `renovate.json` — valid built-in security-alert configuration.
- Modify: `tests/test_dependency_resolution_policy.py` — regression contract for
  valid alert handling and the absence of the invalid package rule.
- Modify: `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md` — describe the valid
  `vulnerabilityAlerts` security path without claiming a boolean schema value.
- Modify: `docs/superpowers/plans/2026-07-17-dependency-cooldown-emergency-policy.md`
  — mark the invalid approach superseded.
- Create: `docs/superpowers/plans/2026-07-17-renovate-validator-correction.md`
  — this decision record and execution plan.
- Modify: `.pre-commit-config.yaml` — official strict Renovate validator hook.
- Modify: `Makefile` — reproducible `renovate-config-validate` target that
  invokes the configured hook.
- Modify: `.github/workflows/ci.yml` — explicit blocking validator step in the
  existing aggregated pre-commit job.

## Task 1: RED test and valid security-alert model

1. Amend `tests/test_dependency_resolution_policy.py` **before** the production
   config. The test must require:

   ```python
   assert all(rule["minimumReleaseAge"] == "7 days" for rule in package_rules)
   assert not any(
       rule.get("matchCategories") == ["security"] for rule in package_rules
   )
   assert renovate["vulnerabilityAlerts"] == {
       "enabled": True,
       "labels": ["security", "manual-cooldown-override-required"],
       "automerge": False,
       "minimumReleaseAge": None,
       "prCreation": "immediate",
   }
   ```

   It must also require the exact official pre-commit hook revision/configuration,
   a `renovate-config-validate` Make target, and the explicit blocking validator
   invocation in the CI workflow.

2. Run the focused test to demonstrate RED against the current boolean package
   rule. On this Windows host, use the established file-only test isolation:

   ```powershell
   C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe -m pytest --noconftest tests\\test_dependency_resolution_policy.py -q --basetemp .tmp\\renovate-correction-red
   ```

   Expected: assertions fail because the security package rule still exists and
   `vulnerabilityAlerts` lacks the explicit valid contract.

3. Implement the valid configuration:

   ```json
   "vulnerabilityAlerts": {
     "enabled": true,
     "labels": ["security", "manual-cooldown-override-required"],
     "automerge": false,
     "minimumReleaseAge": null,
     "prCreation": "immediate"
   }
   ```

   Remove the security `packageRules` entry rather than converting it to `null`.
   This leaves Semgrep with only explicit seven-day routine package rules while
   Renovate's built-in security-alert force configuration has the valid `null`
   opt-out.

4. Update the runbook and both plans to state that Renovate's immediate path is
   `vulnerabilityAlerts` with `null`, not a package-rule boolean. Preserve every
   existing audit field, targeted uv command, and prohibition.

## Task 2: Official validator as a local and CI gate

1. Add the official pre-commit hook, using the exact release and strict
   repository-config behavior:

   ```yaml
   - repo: https://github.com/renovatebot/pre-commit-hooks
     rev: 43.268.4 # ece9d8611e4e7da8cbcf7ea28039ec7928316032
     hooks:
       - id: renovate-config-validator
         args: [--strict]
         pass_filenames: false
   ```

   Add this local target; it intentionally delegates version resolution to the
   exact pre-commit hook rather than invoking unpinned `npx`:

   ```make
   renovate-config-validate:
	pre-commit run renovate-config-validator --all-files
   ```

2. Add a `Validate Renovate configuration (strict)` shell step immediately after
   the existing `pre-commit/action` in `.github/workflows/ci.yml`:

   ```yaml
   run: python -m pre_commit run renovate-config-validator --all-files
   ```

   It must not use `continue-on-error`. This explicit step is blocking because
   the generic pre-commit action intentionally tolerates ordinary exit code 1;
   `pre-commit-check` is already a blocking `ci-success` prerequisite.

3. Run the actual official validator locally. First record the existing failure
   (the validator reports that the old boolean should be a string); then require
   this command to pass after the correction:

   ```powershell
   pre-commit run renovate-config-validator --all-files
   ```

   Remove the temporary workspace-only npm cache created while diagnosing the
   invalid prior configuration after all validation is complete.

## Task 3: Verification, review, and commit

Run all of the following after the correction:

```powershell
C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe -m pytest --noconftest tests\\test_dependency_resolution_policy.py tests\\test_quality_configuration.py -q --basetemp .tmp\\renovate-correction-green
C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe -m ruff check tests\\test_dependency_resolution_policy.py tests\\test_quality_configuration.py
C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe -m ruff format --check tests\\test_dependency_resolution_policy.py tests\\test_quality_configuration.py
make renovate-config-validate
git diff --check HEAD
```

Also run `uv lock --check` in the existing pinned Rust-capable Docker route;
no lockfile regeneration or package-version change is expected. Run normal
pre-commit hooks and a real commit without skips only after a focused self-review.
Then give the corrective diff to a fresh reviewer. If any Important/Critical
finding remains, fix it in a new commit and repeat the review.

## Success Criteria

- Official `renovate-config-validator --strict` accepts the configuration.
- Semgrep accepts the configuration with no suppression.
- Security alerts are immediate, non-automerge, labelled for manual targeted
  uv override, and use valid Renovate semantics.
- Routine dependency updates retain a universal seven-day Renovate window and
  the uv PyPI resolver window.
- The validator is enforceable locally and blocks `ci-success` in CI.
- No package version, runtime behavior, coverage policy, or unrelated file is
  changed.
