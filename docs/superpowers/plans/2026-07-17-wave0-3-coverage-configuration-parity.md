# Wave 0.3 Coverage Configuration Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local Python and frontend coverage commands emit the canonical artifacts and enforce the approved quality-contract floors without hiding handwritten runtime code.

**Architecture:** A repository-level pytest module parses only tracked configuration files with the Python standard library and asserts the contract's report paths, reporter formats, thresholds, and intentionally narrow exclusions. Native tools remain the report producers: pytest-cov writes Cobertura XML and JSON, Vitest writes LCOV and JSON, and Sonar only imports those artifacts. The task does not fabricate unsupported metric dimensions or make the currently measured product coverage appear higher than it is.

**Tech Stack:** Python 3.13-3.14 standard library (`json`, `pathlib`, `re`, `tomllib`), pytest, coverage.py/pytest-cov, Vitest V8 coverage, Make, SonarQube Cloud properties.

## Global Constraints

- Work only in `C:\Users\egorribun\Documents\university_ecosystem\.worktrees\quality-roadmap` on branch `codex/quality-roadmap`.
- Preserve application behavior and public APIs. This task changes quality-tool configuration and its contract test only.
- `quality/quality-contract.json` remains the canonical policy: programme and component floors are exactly lines/statements 99, branches/functions 98, and Tier 0 100.
- Python must retain `branch = true`; `fail_under` is exactly 99 and must be configured only once in `[tool.coverage.report]`, not overridden by a conflicting Makefile flag.
- Canonical raw paths are exactly `coverage.xml`, `artifacts/coverage/python/coverage.json`, `frontend/coverage/lcov.info`, and `frontend/coverage/coverage-final.json`.
- Vitest must retain real handwritten `src` runtime code in its measurement universe. Test files, generated route/API output, TypeScript declaration files, and test setup may be omitted; routes, pages, workers, application shells, API runtime modules, feature barrels, and stores may not be blanket omissions.
- Do not lower a quality-contract floor, add a broad coverage exclusion, add a retry, fake a coverage artifact, or make an unsupported metric look measured.
- Every new behavior follows TDD: add the focused assertion, observe its expected RED result, make the minimum configuration changes, then re-run the focused module before broader verification.
- Findings about backend application settings, Compose/Helm, and service environment contracts are follow-up Wave 1/Wave 8 tasks; do not mix them into this focused report-parity commit.

---

## File Structure

- `tests/test_quality_configuration.py` — parses the quality contract, TOML, JSON, Makefile, Vitest source, and Sonar properties; it is the regression contract for all relationships in this task.
- `pyproject.toml` — owns Python branch collection, the one native `fail_under` value, and coverage.py XML/JSON defaults.
- `frontend/vitest.config.ts` — owns frontend coverage reporters, handwritten-source universe, narrow omission set, and native threshold values.
- `Makefile` — makes both Python coverage entry points create the canonical report directory and emit the two Python artifacts without a second threshold.
- `frontend/package.json` — remains the CI frontend command boundary; modify only if the test proves it does not invoke `vitest run --coverage`.
- `sonar-project.properties` — remains the importer boundary; modify only if the test proves either path differs from the canonical raw artifact path.

### Task 1: Native coverage report configuration contract

**Files:**

- Create: `tests/test_quality_configuration.py`
- Modify: `pyproject.toml`
- Modify: `frontend/vitest.config.ts`
- Modify: `Makefile`
- Verify without gratuitous edits: `frontend/package.json`
- Verify without gratuitous edits: `sonar-project.properties`

**Interfaces:**

- Consumes: `quality/quality-contract.json`, `pyproject.toml`, `frontend/vitest.config.ts`, `frontend/package.json`, `Makefile`, and `sonar-project.properties` from the repository root.
- Produces: `tests/test_quality_configuration.py` passing only when native configurations and local commands agree on canonical coverage artifacts and policy floors.
- Produces from `make backend-test` and `make coverage`: `coverage.xml` and `artifacts/coverage/python/coverage.json`.
- Produces from `npm run test:ci --prefix frontend`: `frontend/coverage/lcov.info` and `frontend/coverage/coverage-final.json`.

- [ ] **Step 1: Write the failing configuration-contract tests**

Create `tests/test_quality_configuration.py`. Keep parsing local and deterministic: use `tomllib.loads`, `json.loads`, a small `key=value` parser for Sonar, and literal/string checks for the TypeScript and Makefile configuration. Do not import the application, Vite, or package-manager code.

```python
from __future__ import annotations

import json
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_contract() -> dict[str, object]:
    return json.loads(
        (REPOSITORY_ROOT / "quality" / "quality-contract.json").read_text(
            encoding="utf-8"
        )
    )


def _read_pyproject() -> dict[str, object]:
    return tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_python_coverage_policy_and_output_paths_match_quality_contract() -> None:
    contract = _read_contract()
    coverage = _read_pyproject()["tool"]["coverage"]

    assert coverage["run"]["branch"] is True
    assert coverage["report"]["fail_under"] == contract["coverage_minimums"]["lines"]
    assert coverage["xml"]["output"] == "coverage.xml"
    assert coverage["json"]["output"] == "artifacts/coverage/python/coverage.json"
```

Add a second test which reads `frontend/vitest.config.ts` and asserts literal presence of `"lcov"` and `"json"`, thresholds `99, 98, 98, 99` for statements/branches/functions/lines, `include: ["src/**/*"]`, and absence of each forbidden runtime-family exclusion below:

```python
FORBIDDEN_VITEST_EXCLUSIONS = (
    '"src/workers/**/*"',
    '"**/routes/**/*"',
    '"**/pages/**/*"',
    '"src/App.tsx"',
    '"src/AppProviders.tsx"',
    '"**/api/events.ts"',
    '"**/api/stories.ts"',
    '"**/api/news.ts"',
    '"**/config/navigation.ts"',
    '"**/stores/index.ts"',
    '"**/features/index.ts"',
)
```

Add a third test which asserts both Make targets include `mkdir -p artifacts/coverage/python`, `--cov-report=xml:coverage.xml`, and `--cov-report=json:artifacts/coverage/python/coverage.json`, do not include `--cov-fail-under=`, and asserts these exact Sonar values:

```python
assert sonar["sonar.python.coverage.reportPaths"] == "coverage.xml"
assert sonar["sonar.javascript.lcov.reportPaths"] == "frontend/coverage/lcov.info"
assert package["scripts"]["test:ci"].startswith("vitest run --coverage")
```

- [ ] **Step 2: Run the focused module and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_configuration.py -q --basetemp .tmp\wave03-quality-config-red
```

Expected: FAIL because Python has a 93 floor and no JSON output configuration, Vitest has no LCOV reporter plus lower thresholds and runtime-family exclusions, and Makefile does not create the canonical Python JSON report. Record the failing assertion names and the relevant actual values in the implementer report. A collection/import error is not valid RED evidence; correct the test until it fails on the missing behavior.

- [ ] **Step 3: Make the minimum native configuration changes**

Set the Python configuration to the policy-owned floor and report defaults:

```toml
[tool.coverage.report]
fail_under = 99
show_missing = true

[tool.coverage.xml]
output = "coverage.xml"

[tool.coverage.json]
output = "artifacts/coverage/python/coverage.json"
```

Keep the existing `branch = true`, source universe, and only the pre-existing explicitly documented omissions. Do not add a new omission to make an aggregate look better.

Use this Vitest coverage shape, retaining the existing generated/test/declaration/setup exclusions and removing the forbidden runtime-family entries from Step 1:

```ts
coverage: {
  provider: "v8",
  reporter: ["text", "json", "lcov", "html"],
  include: ["src/**/*"],
  exclude: [
    "src/tests/**/*",
    "src/**/__tests__/**/*",
    "src/**/*.test.{ts,tsx}",
    "src/**/*.stories.{ts,tsx}",
    "src/setupTests.ts",
    "src/routeTree.gen.ts",
    "src/api/generated/**/*",
    "**/*.d.ts",
    "src/test/**/*",
  ],
  thresholds: {
    statements: 99,
    branches: 98,
    functions: 98,
    lines: 99,
  },
},
```

For both `backend-test` and `coverage`, create the JSON output parent and use the exact paths rather than a second threshold flag:

```make
mkdir -p artifacts/coverage/python
pytest --cov=app --cov-report=xml:coverage.xml --cov-report=json:artifacts/coverage/python/coverage.json --cov-report=term-missing --junitxml=pytest-report.xml
```

The `coverage` target may retain its HTML report and its terminal format, but it must also include the exact XML and JSON flags above. Preserve `frontend/package.json` and `sonar-project.properties` unchanged when their existing values satisfy the new tests; the task is parity, not forced churn.

- [ ] **Step 4: Run focused GREEN verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_configuration.py -q --basetemp .tmp\wave03-quality-config-green
python -m ruff check tests/test_quality_configuration.py
python -m ruff format --check tests/test_quality_configuration.py
```

Expected: all configuration-contract tests pass, Ruff reports no errors, and the formatter reports no changes needed.

- [ ] **Step 5: Produce and inspect the native artifacts**

Run a bounded Python producer command with the policy threshold temporarily overridden only for this measurement run, so the artifacts are inspectable even while the product coverage-improvement waves are incomplete:

```powershell
New-Item -ItemType Directory -Force artifacts\coverage\python | Out-Null
.\.venv\Scripts\python.exe -m pytest tests/test_quality_configuration.py --cov=app --cov-report=xml:coverage.xml --cov-report=json:artifacts/coverage/python/coverage.json --cov-fail-under=0 -q --basetemp .tmp\wave03-artifact-producer
Test-Path coverage.xml
Test-Path artifacts\coverage\python\coverage.json
```

Then run the frontend native producer:

```powershell
npm run test:ci --prefix frontend
Test-Path frontend\coverage\lcov.info
Test-Path frontend\coverage\coverage-final.json
```

Expected: all four `Test-Path` checks are `True`. If Vitest correctly fails its newly truthful 99/98 threshold, retain the generated reports as evidence, record the measured shortfall, and report `DONE_WITH_CONCERNS` rather than weakening its threshold or adding an exclusion. Do not modify application tests or implementation in this task to chase those future coverage gaps.

- [ ] **Step 6: Commit the focused deliverable**

Before staging, confirm only the planned tracked files changed and generated reports remain ignored:

```powershell
git status --short
git diff --check
git add tests/test_quality_configuration.py pyproject.toml frontend/vitest.config.ts Makefile
git commit -m "feat(wave212): align coverage report configuration"
```

If `frontend/package.json` or `sonar-project.properties` needed a minimal correction proven by the contract test, add that exact file to the staging command. Do not stage generated coverage files, `.tmp`, or unrelated working-tree changes.

## Plan Self-Review

- Spec coverage: Task 1 enforces all Wave 0.3 requirements: Python branch/floor/output parity, Vitest LCOV/JSON/source/exclusion/threshold parity, Makefile producer parity, and Sonar/package consumer parity.
- Scope: the task changes only coverage configuration and an on-disk contract test. Broader environment findings from the read-only inventory stay explicit follow-up work instead of becoming unrelated behavior changes.
- TDD: the first test module is intentionally created before configuration is changed; Step 2 requires a behavior-specific RED result and Step 4 requires focused GREEN evidence.
- Truthfulness: the artifact producer may override the threshold only for a diagnostic run; it never changes the checked-in policy. A native tool reporting a real shortfall remains a concern for subsequent coverage waves.
- Placeholder scan: this plan contains exact file paths, exact strings, expected outcomes, commands, and staging boundaries; it does not rely on undefined helpers or future implementation details.
