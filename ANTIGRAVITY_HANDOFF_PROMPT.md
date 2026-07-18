# Handoff Prompt: Continue Wave 0.3 in Google Antigravity

Use the following prompt verbatim in Google Antigravity.

```text
You are continuing work in the existing University Ecosystem repository. Work
carefully, preserve context, and do not reset or discard any changes. The user
originally requested a comprehensive quality and test-coverage roadmap for the
entire project, but the current session must close only the already-started
Wave 0.3: coverage/dependency-policy configuration and its correction. Do not
start the next test-coverage wave until this one is honestly closed.

## Worktree and Git

Primary worktree:

C:\\Users\\egorribun\\Documents\\university_ecosystem\\.worktrees\\quality-roadmap

Branch:

codex/quality-roadmap

Original checkout:

C:\\Users\\egorribun\\Documents\\university_ecosystem

Base commit:

1079a4b9a6b9cc3305a50459a403d3fa357a41de

Important recent commits:

- `e8571bd91d261ff5dc24b33988aa7793df7fe2a1`
  `feat(wave212): align coverage and dependency policies`
- `0de917e02` `docs(wave212): detail coverage configuration parity plan`

Critical: commit `e8571bd...` contains an invalid Renovate configuration and
is not the final solution. A narrow corrective diff is already prepared on top
of it, but it is not committed.

Before any action, run:

```powershell
git status --short
git log --oneline -5
git diff --cached --check
git diff --check HEAD
git diff e8571bd91d261ff5dc24b33988aa7793df7fe2a1 --stat
```

Read `AGENTS.md` completely before acting. Do not use `git reset --hard`,
`git checkout --`, rebase, force-push, `--no-verify`, `SKIP=semgrep`,
`nosemgrep`, broad exclusions, or any security-gate bypass. Use `apply_patch`
for normal file edits and preserve unrelated user changes.

## Wave 0.3 objective and discovered defect

Commit `e8571bd...` added coverage/dependency policies, including canonical
coverage artifacts, strict frontend coverage thresholds, a seven-day uv
dependency cooldown, a Renovate cooldown policy, contract tests, and an
emergency dependency-update runbook.

It also used this invalid Renovate value in a security `packageRule`:

```json
"minimumReleaseAge": false
```

The official Renovate schema accepts `string | null` for
`minimumReleaseAge`, not a boolean. The official validator confirmed:

```text
Configuration option packageRules[15].minimumReleaseAge should be a string
```

Semgrep accepted the boolean, so Semgrep alone is insufficient validation.

## Prepared corrective diff

These files are already modified or staged; inspect the actual index and
worktree rather than assuming their state:

- `.github/workflows/ci.yml`
- `.pre-commit-config.yaml`
- `Makefile`
- `docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`
- `docs/superpowers/plans/2026-07-17-dependency-cooldown-emergency-policy.md`
- `docs/superpowers/plans/2026-07-17-renovate-validator-correction.md` (new)
- `renovate.json`
- `tests/test_dependency_resolution_policy.py`

The correct final Renovate model is:

```json
"osvVulnerabilityAlerts": true,
"vulnerabilityAlerts": {
  "enabled": true,
  "labels": ["security", "manual-cooldown-override-required"],
  "automerge": false,
  "minimumReleaseAge": null,
  "prCreation": "immediate"
}
```

Required invariants:

1. Every `packageRules` item has exactly `"minimumReleaseAge": "7 days"`.
2. No `packageRules` item has `"matchCategories": ["security"]`.
3. `renovate.json` contains no boolean `minimumReleaseAge`.
4. Security updates are immediate but do not automerge.
5. `osvVulnerabilityAlerts: true` remains enabled.
6. `pyproject.toml` retains `exclude-newer = "7 days"` under `[tool.uv]`.
7. Emergency regeneration remains package-scoped:

```shell
uv lock --upgrade-package "<package>" --exclude-newer-package "<package>=false"
```

Never use `uv lock --upgrade`, `uv lock --exclude-newer false`, or
`UV_EXCLUDE_NEWER=false`.

## Official Renovate validator contract

`.pre-commit-config.yaml` must use the official hook:

```yaml
- repo: https://github.com/renovatebot/pre-commit-hooks
  rev: 43.268.4 # ece9d8611e4e7da8cbcf7ea28039ec7928316032
  hooks:
    - id: renovate-config-validator
      args: [--strict]
      pass_filenames: false
```

`pass_filenames: false` is required: passing a filename makes Renovate treat
the config as global/self-hosted; no filename lets it discover the root
repository `renovate.json`.

`Makefile` must contain:

```make
renovate-config-validate:
	pre-commit run renovate-config-validator --all-files
```

This Windows host has no `make`, `mingw32-make`, or `nmake`. Do not install a
build tool solely to exercise this wrapper. The test checks the exact Make
target, and the equivalent configured pre-commit command has passed.

The regression test must verify the exact pinned hook, strict arguments,
`pass_filenames: false`, Make target, absence of the boolean package rule,
exact `vulnerabilityAlerts`, the audited runbook, and a genuinely blocking CI
step. Its `_workflow_named_step()` helper must inspect the actual workflow
step block and prove that it contains no `continue-on-error`.

## Evidence already collected

The following focused command passed with `6 passed`:

```powershell
C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe `
  -m pytest --noconftest `
  tests\\test_dependency_resolution_policy.py `
  tests\\test_quality_configuration.py `
  -q --basetemp .tmp\\renovate-correction-green
```

These also passed:

```powershell
C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe `
  -m ruff check tests\\test_dependency_resolution_policy.py tests\\test_quality_configuration.py

C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe `
  -m ruff format --check tests\\test_dependency_resolution_policy.py tests\\test_quality_configuration.py

python -m pre_commit run renovate-config-validator --all-files
```

`uv lock --check` passed inside a temporary pinned Docker environment:

- Python 3.14.6
- Rust 1.94.1
- uv 0.11.28
- output: `Resolved 247 packages`

Re-run relevant checks after any change; do not claim success based only on
these historical results.

## Why the corrective commit is currently blocked

The prepared diff adds this strict step to the existing `pre-commit-check` job
in `.github/workflows/ci.yml`:

```yaml
- name: Validate Renovate configuration (strict)
  run: python -m pre_commit run renovate-config-validator --all-files
```

There is no `continue-on-error` on this step. This is architecturally strong:
the active GitHub ruleset actually requires the existing job's check.

Read-only GitHub API evidence:

```text
Repository: egorribun/university_ecosystem
Ruleset ID: 8335285
Ruleset: main
Enforcement: active
Required GitHub Actions checks:
- CI Diagnostic
- Pre-commit & Linting (Read-only)
```

That existing job has display name `Pre-commit & Linting (Read-only)`, so the
strict step inside it is genuinely merge-blocking.

However, ordinary local pre-commit currently fails for legacy findings exposed
because this large workflow file becomes part of the staged diff. Command:

```powershell
C:\\Users\\egorribun\\Documents\\university_ecosystem\\.venv\\Scripts\\python.exe `
  -m pre_commit run --hook-stage pre-commit
```

Exact result:

- Ruff/imports/format: passed.
- hardcoded-secret scan: passed.
- Python 2 except gate: passed.
- actionlint: passed.
- Renovate validator: passed.
- detect-secrets: failed only on existing `.github/workflows/ci.yml:1946`:
  `SECRET_KEY: "dummy-secret-key-for-migrations-integration-test-12345678"`.
  `git blame` identifies commit `a72dcd904a` from 2026-07-08; the line is not
  part of this corrective diff.
- semgrep-docker: failed safe.directory setup for the linked worktree, then
  reported 10 pre-existing findings in `ci.yml`, including workflow environment
  secrets, `curl | shell`, and `secrets: inherit`. Renovate JSON scan reported
  zero findings.
- Trivy: no source finding; it timed out after about 15 minutes while scanning
  temporary diagnostic binary caches `.tmp/npm-*-validator` and
  `.tmp/pre-commit-home-validator`.

Never suppress, skip, or hide these findings to make a commit pass.

## Decision requiring explicit user authorization

The user has not explicitly authorized either a remote GitHub ruleset mutation
or a material remediation of the ten legacy Semgrep findings. Ask before either
path.

### Path A: preserve the current integration

Keep the strict step in legacy `ci.yml`, thereby strengthening the already
required check. This requires a real remediation of the ten legacy Semgrep
findings, a valid transparent treatment of the existing detect-secrets dummy
fixture only after proof it is a false positive, and a safe-directory fix. It
materially expands this wave into separate CI security remediation. Do not start
it without explicit approval.

### Path B: recommended when time is limited

1. Remove the newly added strict step from legacy `.github/workflows/ci.yml`.
2. Create a separate SHA-pinned workflow such as
   `.github/workflows/renovate-config-validation.yml`.
3. Run only the configured strict hook using:

```yaml
- uses: pre-commit/action@2c7b3805fd2a0fd8c1884dcaebf91fc102a13ecd
  with:
    extra_args: renovate-config-validator --all-files
```

Use SHA-pinned checkout/setup actions, `permissions: contents: read`, no
`continue-on-error`, and push/pull_request triggers without a path filter if
the check is required.

The actual `pre-commit/action` metadata installs pre-commit and invokes
`pre-commit run --show-diff-on-failure --color=always $extra_args`, so this
executes only the desired strict configured hook.

4. Externally update GitHub ruleset `main` (ID `8335285`) to add the new job as
   a required status check while preserving both existing required checks.

A standalone workflow is not an equivalent gate without the remote ruleset
update. That mutation needs explicit user authorization. Ask:

> Do you authorize creating the standalone strict Renovate workflow and
> modifying active GitHub ruleset `main` (ID 8335285) to require its job while
> retaining the existing required checks?

If approved, read the complete current ruleset first, retain `CI Diagnostic`
and `Pre-commit & Linting (Read-only)`, add only the new job context, then
read the ruleset again to verify the exact final required-check set. Do not
push or open a PR without separate approval.

## Temporary cache cleanup

Before re-running Trivy, remove only the temporary validator caches and only
after proving each resolved absolute target is under the quality-roadmap
worktree. Never delete `.tmp` broadly; it can contain unrelated files.

Example safety pattern:

```powershell
$worktree = (Resolve-Path '.').Path
$target = (Resolve-Path '.tmp\\npm-renovate-cache').Path

if (-not $target.StartsWith(
  $worktree + [IO.Path]::DirectorySeparatorChar,
  [StringComparison]::OrdinalIgnoreCase
)) {
  throw "Refusing to remove a path outside the worktree: $target"
}

Remove-Item -LiteralPath $target -Recurse -Force
```

First enumerate exact validator-cache directories. Do not remove caches still
needed by a running validation process.

## Documents, review, and scope boundary

Tracked plans:

- `docs/superpowers/plans/2026-07-17-dependency-cooldown-emergency-policy.md`
  is marked superseded for the Renovate security path.
- `docs/superpowers/plans/2026-07-17-renovate-validator-correction.md` records
  the valid correction.

Ignored implementation report already exists at:

```text
.superpowers/sdd/dependency-cooldown-task-1-report.md
```

It records RED/GREEN evidence, Docker evidence, Make limitation, and exact
normal-hook root causes. Do not commit ignored `.superpowers` artifacts.

Before a final commit, ensure both whitespace checks pass:

```powershell
git diff --cached --check
git diff --check HEAD
```

A preliminary independent review found the policy shape sound, but a fresh
independent review is still required after the final commit. Do not mark the
wave complete before that review.

Frontend test context is intentionally out of scope for this final Wave 0.3
closure: the full frontend suite previously passed 3160 tests, while truthful
coverage remains below the new strict target (lines/statements 87.27%, branches
81.90%, functions 81.04%). Do not lower thresholds or add broad runtime
exclusions; that is the next coverage wave.

## Mandatory continuation order

1. Read `AGENTS.md`.
2. Inspect Git status, staged/worktree diffs, and whitespace.
3. Do no destructive cleanup without verified absolute paths.
4. Ask the user to choose Path A or authorize Path B.
5. After authorization, use TDD: update/add a regression test, demonstrate RED,
   implement the smallest solution, and demonstrate GREEN.
6. Re-run relevant focused pytest, Ruff, official Renovate validation, lock
   validation when policy changes, diff checks, and normal pre-commit with no
   bypasses.
7. If normal pre-commit is not clean, do not commit.
8. After fully green evidence, create a narrow commit on top of `e8571bd...`:

```text
fix(wave212): validate renovate cooldown policy
```

9. Obtain a fresh independent review of the final commit.
10. Only then mark Wave 0.3 complete. Do not begin the next coverage wave
    without a new user decision.

## Primary references

- https://docs.renovatebot.com/config-validation/
- https://docs.renovatebot.com/configuration-options/#minimumreleaseage
- https://docs.renovatebot.com/configuration-options/#vulnerabilityalerts
- https://github.com/renovatebot/pre-commit-hooks

Core principle: do not make checks green at any cost. Preserve a truthful,
enforceable security gate; do not hide legacy findings; and do not claim the
wave is complete without evidence and independent final review.
```
