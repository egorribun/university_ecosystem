# Quality Contract Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Establish a machine-validated, versioned quality policy that makes coverage targets, waivers and CI evidence truthful before raising any metric.

**Architecture:** A small standard-library Python validator reads one canonical JSON quality contract from the repository root. The contract owns programme floors, Tier 0 policy, empty exclusion/quarantine registers and required artifact names. Later tasks add report normalizers and CI wiring, while the validator stays deterministic and independently tested.

**Tech Stack:** Python 3.13–3.14 standard library, pytest, JSON, GitHub Actions, coverage.py, Vitest, Go cover profiles and cargo llvm-cov.

## Global Constraints

- Work only in C:\Users\egorribun\Documents\university_ecosystem\.worktrees\quality-roadmap; do not touch the user’s original checkout or its untracked artifacts.
- Preserve application behaviour and public APIs. This wave changes quality tooling, documentation and CI policy only.
- The canonical policy file is quality/quality-contract.json; it must be valid UTF-8 JSON, version 1, and use no comments or duplicate keys.
- The validator is scripts/quality/validate_quality_contract.py; it must use only the Python standard library and work when invoked from any current working directory.
- Minimum programme thresholds are exactly: 99 for lines/statements, 98 for branches/functions, 100 for Tier 0 dimensions, 100 for patch coverage, and 100 for viable-mutant mutation score.
- Contract components are exactly python, frontend, go-gateway, go-ws-hub, go-file-processor, rust-native, rust-pyo3-sanitizer, rust-wasm-sanitizer, infrastructure, workflows and scripts.
- An exclusion or quarantine record must contain a unique non-wildcard id, a non-wildcard repository-relative path or test identifier, a non-empty reason, owner, issue, ISO date expires_on, and evidence. The initial registers are empty.
- An expiry may be at most 30 days after its created_on date; any record expiring on or before validation day is rejected. IDs and paths cannot be duplicated across a register.
- Every new behavior must follow TDD: create a focused test, observe its expected failure, implement the minimum code, re-run the focused test, then run the relevant suite.
- Do not add a dependency, a broad skip, a blanket coverage omission, a test retry, or a fake coverage artifact.
- All Python code follows the repository Ruff conventions and type annotations; test names explain user-observable policy behavior.

---

### Task 1: Versioned quality policy validator

**Files:**
- Create: quality/quality-contract.json
- Create: scripts/quality/validate_quality_contract.py
- Create: tests/test_quality_contract.py
- Modify: docs/testing/roadmap-100-percent-quality.md

**Interfaces:**
- Consumes: a UTF-8 JSON file passed with --contract PATH, or repository-root/quality/quality-contract.json when omitted.
- Produces: process exit code 0 and the line Quality contract is valid. on success; exit code 1 and one diagnostic per violation prefixed ERROR: on policy violations; exit code 2 for an unreadable/malformed command argument.
- Public Python function: validate_contract(contract: dict[str, object], *, today: datetime.date) -> list[str].
- Public Python function: main(argv: Sequence[str] | None = None) -> int.

- [ ] **Step 1: Write the failing repository-contract test**

Create tests/test_quality_contract.py with an executable-subprocess test that invokes the missing script from a temporary working directory:

~~~python
def test_repository_quality_contract_is_accepted_from_another_directory(
    tmp_path: Path,
) -> None:
    result = _run_validator(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Quality contract is valid.\n"
~~~

Add _run_validator(cwd: Path, contract: Path | None = None) -> subprocess.CompletedProcess[str] that calls sys.executable, the absolute repository script path, and optionally --contract.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_contract.py::test_repository_quality_contract_is_accepted_from_another_directory -q --basetemp .tmp\quality-contract-red
~~~

Expected: FAIL because scripts/quality/validate_quality_contract.py does not exist. Do not create the validator before observing this failure.

- [ ] **Step 3: Add failing validation-behaviour tests**

Add independent tests that copy the repository contract into a temporary JSON file, alter exactly one field, invoke the script with --contract, and assert exit code 1 plus the named diagnostic:

~~~python
def test_rejects_component_floor_below_programme_minimum(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["components"]["python"]["coverage"]["branches"] = 97

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "python.coverage.branches must be at least 98" in result.stderr


def test_rejects_expired_unowned_quarantine(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["quarantines"] = [{
        "id": "frontend-router-flake",
        "test": "frontend/src/__tests__/router.test.ts",
        "path": "frontend/src/routes/router.ts",
        "reason": "deterministic reproducer pending",
        "owner": "",
        "issue": "QUALITY-1",
        "created_on": "2026-06-01",
        "expires_on": "2026-06-30",
        "evidence": "trace.zip",
    }]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "quarantines[0].owner must be a non-empty string" in result.stderr
    assert "quarantines[0].expires_on must be after validation day" in result.stderr
~~~

Also test duplicate exclusion IDs, wildcard paths, missing required components, a Tier 0 coverage value below 100, malformed JSON with exit code 2 and an expiry more than 30 days after created_on.

- [ ] **Step 4: Run the new tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_contract.py -q --basetemp .tmp\quality-contract-red-validation
~~~

Expected: the new tests fail because no implementation exists; failures must be assertion failures about missing/invalid validator behavior, not a fixture or import error.

- [ ] **Step 5: Add the minimal canonical contract**

Create quality/quality-contract.json with the exact shape below. Keep exclusions and quarantines empty:

~~~json
{
  "version": 1,
  "policy": {
    "patch_coverage": 100,
    "viable_mutant_score": 100,
    "required_pr_matrix": true
  },
  "coverage_minimums": {
    "lines": 99,
    "statements": 99,
    "branches": 98,
    "functions": 98,
    "tier0": 100
  },
  "components": {
    "python": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "frontend": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "go-gateway": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "go-ws-hub": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "go-file-processor": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "rust-native": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "rust-pyo3-sanitizer": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "rust-wasm-sanitizer": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "infrastructure": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "workflows": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "scripts": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}}
  },
  "tier0": {"coverage": {"lines": 100, "statements": 100, "branches": 100, "functions": 100}},
  "required_artifacts": ["coverage.xml", "frontend/coverage/lcov.info"],
  "exclusions": [],
  "quarantines": []
}
~~~

- [ ] **Step 6: Implement the smallest validator**

Create scripts/quality/validate_quality_contract.py. Resolve the default repository root from Path(__file__).resolve().parents[2], parse command line arguments with argparse, load JSON with json.loads, and write diagnostics to stderr.

validate_contract must accumulate, rather than stop at, all detectable policy errors. It must validate:

1. top-level keys and version equals 1;
2. exact component set and a numeric, inclusive 0–100 value for each coverage metric;
3. global component floors and Tier 0 value of exactly 100 for all four metrics;
4. policy values of exactly 100, 100 and true;
5. non-empty unique artifact paths with no wildcard, absolute path or parent traversal;
6. each register record using its correct identity (path for exclusions, test plus path for quarantines), required metadata, ISO dates, non-wildcard values, duplicate ID/path detection, expiry after today and a maximum 30-day lifetime.

On valid input, main prints exactly Quality contract is valid. On validation errors, it prints each error as ERROR: followed by the message and returns 1. On malformed JSON, missing file or invalid command argument, it prints ERROR: followed by the message and returns 2.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_contract.py -q --basetemp .tmp\quality-contract-green
.\.venv\Scripts\python.exe scripts\quality\validate_quality_contract.py
~~~

Expected: all focused tests pass and the script prints exactly Quality contract is valid.

- [ ] **Step 8: Run quality checks and commit**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m ruff check scripts\quality tests\test_quality_contract.py
.\.venv\Scripts\python.exe -m ruff format --check scripts\quality tests\test_quality_contract.py
git add quality/quality-contract.json scripts/quality/validate_quality_contract.py tests/test_quality_contract.py docs/testing/roadmap-100-percent-quality.md
git commit -m "feat(quality): add validated coverage contract"
~~~

Expected: lint and formatting pass; commit contains only Task 1 artifacts.

### Task 2: Coverage artifact manifest and normalizers

**Files:**
- Create: scripts/quality/normalize_coverage_reports.py
- Create: tests/test_coverage_manifest.py
- Create: quality/coverage-manifest.schema.json
- Modify: quality/quality-contract.json

**Interfaces:**
- Consumes: coverage.xml, frontend/coverage/lcov.info, Go coverprofile files and cargo llvm-cov JSON passed by command-line paths.
- Produces: a deterministic quality-artifacts.json containing commit SHA, source roots, report hashes, timestamps, measured metrics, missing reports and validation result.

- [ ] **Step 1: Write focused failing parser tests**

Use small fixture files under tests/fixtures/quality/ for one valid and one malformed instance of each report family. Assert the normalizer emits canonical component names, metrics in 0–100, report SHA-256 and no filesystem-dependent ordering.

- [ ] **Step 2: Observe RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_coverage_manifest.py -q --basetemp .tmp\coverage-manifest-red
~~~

Expected: FAIL because the normalizer does not exist.

- [ ] **Step 3: Implement standard-library report normalizers**

Parse XML with xml.etree.ElementTree, LCOV text directly, Go function/profile summaries and cargo JSON. Do not infer a missing metric as 100; use explicit null plus an actionable error. Validate every component against the quality contract and serialize deterministically with sorted keys.

- [ ] **Step 4: Verify GREEN and commit**

Run focused tests, Ruff check, formatter check and then:

~~~powershell
git add scripts/quality/normalize_coverage_reports.py tests/test_coverage_manifest.py tests/fixtures/quality quality/coverage-manifest.schema.json quality/quality-contract.json
git commit -m "feat(quality): normalize coverage evidence"
~~~

### Task 3: Native report configuration and local parity

**Files:**
- Modify: pyproject.toml
- Modify: frontend/vitest.config.ts
- Modify: frontend/package.json
- Modify: Makefile
- Modify: sonar-project.properties
- Create: tests/test_quality_configuration.py

**Interfaces:**
- Produces Python XML/JSON and frontend LCOV/JSON reports at the exact paths declared in the quality contract.
- Keeps local targets and CI commands parameter-compatible; no command may claim a threshold different from its native configuration.

- [ ] **Step 1: Write failing configuration-contract tests**

Assert from Python that:

1. coverage.py is branch-enabled and its configured floor is not below 99;
2. Vitest reporters include lcov, coverage includes handwritten src code and does not exclude an entire runtime family without an explicit quality-contract entry;
3. Sonar paths match generated reports;
4. Make targets invoke the same report-producing commands.

- [ ] **Step 2: Observe RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_configuration.py -q --basetemp .tmp\quality-config-red
~~~

Expected: FAIL against the current contradictory thresholds/reporters/exclusions.

- [ ] **Step 3: Align configurations minimally**

Add LCOV to Vitest, report paths to all local commands, and contract-compatible thresholds. Replace only proven generated/test/bootstrap omissions with explicit contract records; do not add blanket routes, pages, workers or API families to exclusions. Keep operationally impractical tool dimensions declared as a future normalizer error until the matching tool is introduced rather than fabricating data.

- [ ] **Step 4: Verify and commit**

Run the configuration tests, a focused Python coverage run, npm run test:ci, report existence assertions, formatter/lint and commit:

~~~powershell
git add pyproject.toml frontend/vitest.config.ts frontend/package.json Makefile sonar-project.properties tests/test_quality_configuration.py quality/quality-contract.json
git commit -m "feat(quality): align coverage report contracts"
~~~

### Task 4: Required CI policy gate

**Files:**
- Modify: .github/workflows/ci.yml
- Modify: .github/workflows/reusable-python-tests.yml
- Modify: .github/workflows/reusable-frontend-tests.yml
- Modify: .github/workflows/reusable-go-tests.yml
- Create: tests/test_quality_workflow_contract.py
- Modify: docs/testing/roadmap-100-percent-quality.md

**Interfaces:**
- CI invokes the policy validator before upload and invokes the report normalizer after all native reports are generated.
- A policy failure blocks PR completion; it cannot be hidden behind continue-on-error, conditional artifact absence or an advisory summary.

- [ ] **Step 1: Write failing workflow-contract tests**

Parse workflow YAML as text/structured YAML and assert that the quality policy job has no continue-on-error, is included in the aggregate required gate, invokes both scripts, uploads their reports and declares all required artifact paths.

- [ ] **Step 2: Observe RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_workflow_contract.py -q --basetemp .tmp\quality-workflow-red
~~~

Expected: FAIL because the policy job is absent.

- [ ] **Step 3: Add CI wiring**

Install only dependencies already present in each reusable job, generate reports before upload, run validator/normalizer with the checked-out SHA, expose normalized report as a required artifact and wire its result into the PR aggregate required check. Preserve action SHA pinning and existing platform-specific jobs.

- [ ] **Step 4: Verify and commit**

Run focused workflow tests, every edited workflow's syntax/format check available in the repository, the validator, and commit:

~~~powershell
git add .github/workflows tests/test_quality_workflow_contract.py docs/testing/roadmap-100-percent-quality.md
git commit -m "feat(quality): require coverage evidence policy"
~~~

## Plan self-review

- Spec coverage: Task 1 establishes strict policy and waiver controls; Task 2 makes reports comparable; Task 3 removes existing report/configuration contradictions; Task 4 makes the result a required CI gate.
- Placeholder scan: each task declares exact paths, commands, success/failure expectations and interface boundary.
- Consistency: all later tasks consume quality/quality-contract.json and scripts/quality/validate_quality_contract.py defined in Task 1.
