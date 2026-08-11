# Same-run Performance Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace invalid cross-run historical blocking comparisons with a statistically sound, fail-closed same-run base/head performance gate, while preserving the existing required contexts and a strict greater-than-10-percent regression policy.

**Architecture:** The two required regression jobs resolve immutable base and candidate SHAs, execute both revisions in an isolated GitHub-hosted runner, alternate twelve base/head pairs, and retain every raw output. A new standard-library Python comparator validates the evidence, evaluates paired lower-is-better ratios, and emits a deterministic machine-readable decision. Historical `benchmark-action` chart publication becomes an isolated main-only publisher; it cannot decide pull-request acceptance.

**Tech Stack:** Python 3.14 standard library and pytest, GitHub Actions, Go 1.26 benchmark output, Rust Criterion bencher output, YAML/actionlint, Git worktrees, GitHub artifacts.

## Global Constraints

- Preserve the exact required context names `WS-Hub Go Benchmark Regression Gate` and `Rust Native Optimizer Regression Gate`; preserve the currently required advisory context names `Run Go Benchmarks` and `Rust Criterion Benchmarks (pyo3-sanitizer)` as read-only evidence jobs.
- Retain the policy threshold exactly: a confirmed regression is a metric whose paired median ratio is **strictly greater than `1.10`** and whose deterministic one-sided 95% bootstrap lower bound is also **strictly greater than `1.10`**. Do not lower the threshold, sample count, workload, or test scope to make a run pass.
- Require exactly twelve complete paired samples for each benchmark/metric. Missing, malformed, non-finite, duplicate, mismatched, or incomplete evidence is an integrity failure, never a pass or a fallback to `gh-pages` history.
- Use only GitHub-hosted runners for public pull-request execution. Do not introduce `self-hosted`, a configurable runner label, `pull_request_target`, mutable branch-name comparison inputs, or a persistent runner requirement.
- Use immutable SHA inputs: PR base and GitHub's synthetic merge `github.sha`, `github.event.before` and `github.sha` for a main push, and a required `base_sha` plus the dispatch ref SHA for manual evidence. Reject all-zero, identical, and non-ancestor base/candidate pairs.
- Run the decision comparator only from the detached immutable base worktree. If that base lacks the tool during first rollout, fail closed rather than falling back to candidate/PR source; document the deliberate bootstrap sequence.
- Keep broad historical charts advisory (`fail-on-alert: false`) and give write capability only to an explicit main-only history-publisher job. PR and manual jobs must be `contents: read`, must not comment, and must not publish history.
- Use `apply_patch` for repository edits, preserve unrelated worktree changes, do not include a `Co-Authored-By` trailer, and do not associate testing/quality work with waves.
- Do not update the live roadmap as closed until a fresh hosted run on the new implementation has completed and its raw artifacts/comparison output are inspected.

## Required two-phase bootstrap

The comparator, capture helper, and Rust image must be read from the immutable
base worktree. They therefore cannot safely be introduced and enforced by the
same pull request: its base commit has no trusted copy of those assets.

1. **Phase 1 — asset bootstrap.** Publish only the protected comparator,
   capture helper, Rust Dockerfile, ownership/config prerequisites, unit tests,
   and this runbook. Its staged diff must contain **zero**
   `.github/workflows/**` changes. The current base workflow's path filter will
   intentionally leave required benchmark contexts absent for this asset-only
   PR; widening that legacy workflow would execute its write-capable jobs for
   every PR, so it is not an acceptable workaround. Because GitHub evaluates
   CODEOWNERS from the PR base and `main` does not yet contain these new rules,
   Phase 1 requires a documented explicit owner/manual review of the complete
   staged diff before the repository's one-time `RepositoryRole` admin bypass.
   Record this exact bootstrap reason in the PR description or merge commit,
   as required by `AGENTS.md`: `asset bootstrap / no safe preexisting required
   context; base is missing base-trusted performance tooling; retaining path
   filter avoids widening legacy writable PR workflow`. This exception never
   counts as hosted performance proof; CODEOWNERS enforcement begins in Phase
   2 once the Phase-1 SHA is on `main`.
2. **Phase 2 — enforcement.** Only after the Phase-1 SHA is in `main`, rebase
   or create the activation PR so its base worktree contains all trusted assets.
   It enables the read-only isolated workflows, removes the PR path filter only
   as part of the accompanying permission refactor, and must pass ordinary
   required contexts with no bypass. A change to the helper or Dockerfile takes
   effect in the next base revision; if a trusted asset itself needs an
   emergency repair, use the same reviewed two-step release procedure and the
   documented emergency bypass rather than falling back to candidate code.

## Comparator Contract

The new `scripts/quality/compare_paired_benchmarks.py` command will expose this stable CLI:

```powershell
uv run python scripts/quality/compare_paired_benchmarks.py `
  --format go `
  --base-dir artifacts/ws-hub/base `
  --candidate-dir artifacts/ws-hub/candidate `
  --expected-pairs 12 `
  --base-revision <40-hex-base-sha> `
  --candidate-revision <40-hex-head-sha> `
  --toolchain-json artifacts/ws-hub/toolchain.json `
  --output artifacts/ws-hub/comparison.json
```

Each directory contains exactly `pair-01.txt` through `pair-12.txt`. The command pairs files by that canonical filename, rather than by filesystem ordering. It writes JSON even for an integrity failure when enough metadata is available, and exits `0` for a validated pass, `1` for a statistically confirmed regression, and `2` for invalid evidence or command usage.

The result has this shape (additional diagnostic fields are allowed, but these keys are mandatory):

```json
{
  "schema_version": 1,
  "format": "go",
  "base_revision": "<sha>",
  "candidate_revision": "<sha>",
  "expected_pairs": 12,
  "threshold_ratio": 1.1,
  "toolchain": {"go": "go version ..."},
  "decision": "pass",
  "metrics": [
    {
      "benchmark": "BenchmarkClientLookup",
      "metric": "ns/op",
      "base_values": [1.0],
      "candidate_values": [1.01],
      "ratios": [1.01],
      "median_ratio": 1.01,
      "one_sided_95_lower_bound": 0.99,
      "decision": "pass"
    }
  ]
}
```

For Go, accept canonical `go test -benchmem` records such as `BenchmarkClientLookup-8 100 12.5 ns/op 4 B/op 1 allocs/op`; normalize the terminal processor suffix consistently and require all three lower-is-better units. The required WS-Hub command includes `-benchmem`, so a missing Go allocation metric is invalid evidence, not a reduced latency-only gate. For Criterion bencher output, accept canonical `test <name> ... bench: <number> ns/iter ...` records and normalize `ns/iter` to the `ns/op` metric. Reject unsupported or repeated records instead of guessing.

For `ns/op` and any positive-valued allocation metric, compute `candidate_value / base_value` for every pair. Seed `random.Random` from the SHA-256 digest of the canonical serialized metric identity and ratios, resample the twelve paired ratios 10,000 times, calculate a median per resample, and take the deterministic fifth percentile as the one-sided 95% lower bound. A non-finite or negative value, zero `ns/op` base, empty bootstrap distribution, or absent metric on either side is invalid evidence.

`B/op` and `allocs/op` legitimately use zero. When all twelve base and candidate values are zero, report an explicit `zero_stable` pass without fabricating a ratio. When all base values are zero and any candidate value is positive, report a confirmed allocation regression (an infinite relative increase). A mixture of zero and nonzero base allocation values is an integrity failure, because no single finite ratio distribution can represent it. This preserves strict allocation regression detection without making allocation-free benchmarks permanently red.

---

### Task 1: Specify the comparator with failing tests first

**Files:**
- Create: `tests/test_compare_paired_benchmarks.py`
- Create: `scripts/quality/compare_paired_benchmarks.py`
- Read: `scripts/quality/aggregate_go_benchmarks.py`
- Read: `tests/test_aggregate_go_benchmarks.py`

**Interfaces:**
- Input: twelve named raw base files and twelve named raw candidate files in Go or Criterion bencher format, SHA metadata, and a toolchain JSON file.
- Output: a versioned comparison JSON document and exit status `0`, `1`, or `2` as defined above.

- [ ] **Step 1: Write RED parser/validation tests for one valid Go pair and one valid Criterion pair.**

  Create fixtures through `tmp_path` that write `pair-01.txt` through `pair-12.txt`, with a stable `BenchmarkLookup-8 ... ns/op B/op allocs/op` Go record and a stable `test native_conflicts/100 ... bench: 120 ns/iter (+/- 4)` Criterion record. Assert that parsing preserves the benchmark identity, normalizes Criterion to `ns/op`, and returns exactly twelve ordered values for each present metric.

  Also add parameterized RED tests that expect `EvidenceIntegrityError` for: a missing `pair-12.txt`, a duplicate benchmark record in one raw file, a malformed numeric token, `nan`/`inf`, zero `ns/op` base, a mixed zero/nonzero allocation baseline, a metric present on only one side, and a base/candidate benchmark-name mismatch. Add explicit tests that twelve `0 B/op`/`0 allocs/op` values are a `zero_stable` pass, while any positive candidate allocation against an all-zero base is a regression.

  Run:

  ```powershell
  uv run pytest -q tests/test_compare_paired_benchmarks.py
  ```

  Expected before implementation: collection fails because the comparator module does not yet exist.

- [ ] **Step 2: Implement typed, fail-closed parsers and pair loading.**

  Add frozen dataclasses `BenchmarkSample`, `MetricComparison`, and `ComparisonResult`, plus `EvidenceIntegrityError`. Implement `parse_go_benchmark_output(text: str) -> dict[str, dict[str, float]]` and `parse_bencher_output(text: str) -> dict[str, dict[str, float]]`; validate each numeric token with `math.isfinite`, reject duplicate `(benchmark, metric)` records in a single file, and use a deliberate regex for each supported format.

  Implement `load_paired_samples(base_dir, candidate_dir, expected_pairs, parser)` so it requires precisely `pair-{index:02d}.txt` on both sides, rejects unexpected pair files, checks the complete benchmark/metric key set on every pair, and produces ordered base/candidate value arrays. Do not read files through a glob whose order can vary.

- [ ] **Step 3: Make the parser suite GREEN and run adjacent quality tests.**

  Run:

  ```powershell
  uv run pytest -q tests/test_compare_paired_benchmarks.py tests/test_aggregate_go_benchmarks.py
  uv run ruff check scripts/quality/compare_paired_benchmarks.py tests/test_compare_paired_benchmarks.py
  uv run ruff format --check scripts/quality/compare_paired_benchmarks.py tests/test_compare_paired_benchmarks.py
  ```

  Expected: all tests pass; no parser accepts an ambiguous record.

### Task 2: Implement deterministic statistics, report generation, and CLI behavior

**Files:**
- Modify: `scripts/quality/compare_paired_benchmarks.py`
- Modify: `tests/test_compare_paired_benchmarks.py`

**Interfaces:**
- Input: validated ordered paired values from Task 1.
- Output: per-metric ratios, median, deterministic one-sided lower bound, decision, and report file.

- [ ] **Step 1: Add RED decision-boundary and deterministic-output tests.**

  Cover all three policy edges with synthetic twelve-pair fixtures:

  ```python
  # Always 1.10: not a failure because the policy is strictly greater.
  ratios_at_threshold = [1.10] * 12
  # Median > 1.10 but lower confidence bound <= 1.10: not proven; pass.
  noisy_ratios = [1.00] * 5 + [1.11] * 7
  # Every pair > 1.10: confirmed regression.
  proven_ratios = [1.12] * 12
  ```

  Assert that a repeated call produces byte-identical JSON, reports raw values and revisions/toolchain, returns `0` for the first two cases, returns `1` for the third, and reports `2` for an integrity failure. Include a test that one failed metric makes the aggregate decision `regression` even when all other metrics pass.

- [ ] **Step 2: Implement deterministic one-sided bootstrap and report assembly.**

  Implement `paired_median_ratio(base_values, candidate_values)`, `bootstrap_lower_bound(ratios, confidence=0.95, iterations=10_000)`, and `compare_paired_samples(...)`. Implement the explicit zero-allocation branch from the contract before division. Build the bootstrap seed from `hashlib.sha256(json.dumps({"benchmark": name, "metric": unit, "ratios": ratios}, sort_keys=True, separators=(",", ":")).encode()).digest()` and use `random.Random(seed_int)`. Sort bootstrap medians and select index `floor((1 - confidence) * iterations)`.

  Set a metric decision to `regression` only if both its median and bound are `> 1.10`; set aggregate decision to `pass` only when every metric passes. Serialize with sorted keys, compact stable separators, and a final newline so repeated execution is byte-for-byte reproducible.

- [ ] **Step 3: Implement the command-line boundary and make the statistics suite GREEN.**

  Use `argparse` with required `--format`, `--base-dir`, `--candidate-dir`, `--base-revision`, `--candidate-revision`, `--toolchain-json`, and `--output`; default `--expected-pairs` to `12` but reject any value other than `12`. Validate full 40-hex commit SHAs, load a JSON object toolchain, write the result atomically through a sibling temporary file plus `Path.replace`, and map exceptions to exit `2` without a traceback unless `--verbose` is explicitly supplied.

  Run:

  ```powershell
  uv run pytest -q tests/test_compare_paired_benchmarks.py
  uv run python scripts/quality/compare_paired_benchmarks.py --help
  uv run ruff check scripts/quality/compare_paired_benchmarks.py tests/test_compare_paired_benchmarks.py
  uv run ruff format --check scripts/quality/compare_paired_benchmarks.py tests/test_compare_paired_benchmarks.py
  ```

  Expected: all policy boundaries and deterministic report checks pass.

### Task 3: Convert the required WS-Hub gate to same-run paired evidence

**Files:**
- Modify: `.github/workflows/benchmark.yml`
- Modify: `tests/test_quality_workflow_contract.py`

**Interfaces:**
- Input: an immutable base SHA and candidate SHA, plus the exact WS-Hub source at both revisions.
- Output: `artifacts/performance/ws-hub/base/pair-01.txt` through `pair-12.txt`, corresponding candidate files, `toolchain.json`, `comparison.json`, and the unchanged required context.

- [ ] **Step 1: Write RED workflow-contract tests before changing YAML.**

  Replace the historical-action assertions for `ws-hub-regression` with assertions that it has the unchanged name, `runs-on: ubuntu-latest`, `permissions: {contents: read}`, an explicit immutable base resolver, and no `benchmark-action/github-action-benchmark` step. Require the resolver text to contain all PR/push SHA sources, the all-zero guard, `git fetch`, `git cat-file -e`, and `git worktree add --detach`.

  Require the capture text to invoke only the base-worktree helper through an
  absolute trusted Python executable with `-I`; pass a fresh
  `${RUNNER_TEMP}` artifact root, the immutable revisions, and `--format go`.
  Require the helper rather than YAML to own the exact twelve-pair alternation,
  warm-up, `go mod download && go mod verify` prefetch, and offline
  `go test -mod=readonly -buildvcs=false -bench=. -run=^$ -benchmem -count=1
  -benchtime=1s ./...` measurement. Reject a capture-step `EXIT` trap, host
  `actions/cache`, bare `python`, candidate helper paths, and host-side raw
  benchmark commands. Require comparator invocation with `--format go`,
  `--expected-pairs 12`, both revisions, and host-only raw/JSON artifact upload.

- [ ] **Step 2: Implement immutable setup and alternating WS-Hub capture.**

  Check out `github.sha` with `fetch-depth: 0` and `persist-credentials: false`;
  resolve/fetch/validate immutable SHA pairs; reject equal/non-ancestor pairs;
  and create a detached base worktree under `${RUNNER_TEMP}`. Hash and retain
  the base comparator before the helper runs. Invoke the base-only helper with
  distinct base/candidate source mounts and a new host-only evidence root below
  `${RUNNER_TEMP}`; it creates private per-side caches, prefetches over the
  network, and makes every recorded measurement offline in a non-root,
  read-only, capability-dropped Docker container with CPU/memory/PID/output
  bounds. It records the container tool version, image reference/content ID,
  Docker version, and trusted Rust-Dockerfile hash.

  Recheck the comparator hash, invoke it with the trusted absolute Python
  executable and `-I`, then upload the complete evidence root with `if:
  always()`. Add a separate `Cleanup detached base worktree` step after
  comparison and upload, also `if: always()`; never use a capture-step `EXIT`
  trap. Do not aggregate repeated samples or mutate a checkout.

- [ ] **Step 3: Make the WS-Hub contract suite GREEN.**

  Run:

  ```powershell
  uv run pytest -q tests/test_quality_workflow_contract.py -k "performance or manual_performance"
  actionlint .github/workflows/benchmark.yml
  ```

  Expected: the required WS-Hub context remains present, but no historical cross-run result can choose its pass/fail decision.

### Task 4: Convert the required Rust-native and manual gates, then isolate historical publication

**Files:**
- Modify: `.github/workflows/benchmark.yml`
- Modify: `.github/workflows/manual-performance-evidence.yml`
- Modify: `tests/test_quality_workflow_contract.py`

**Interfaces:**
- Input: the same immutable revisions and Native Rust Criterion bencher command at both revisions.
- Output: a separate native raw-evidence artifact and the same comparator decision; manual runs are distinct/read-only; charts publish only from `main`.

- [ ] **Step 1: Add RED contract tests for native/manual/security invariants.**

  Require the unchanged required Rust-native context to use the same
  resolver/base-helper/comparator structure with `--format rust`, the trusted
  base Dockerfile path, twelve alternating pairs, a trusted base-worktree
  comparator, and a raw artifact. Require that
  `manual-performance-evidence.yml` has a required string
  `workflow_dispatch.inputs.base_sha`, `permissions: {contents: read}`, all
  jobs explicitly read-only, distinct manual job names, strict ancestor
  validation, and the same helper boundary.

  Require no workflow text contains `pull_request_target`, `self-hosted`, `PERFORMANCE_BENCHMARK_RUNNER`, or a `runs-on` expression/variable. Require all PR-facing jobs use `persist-credentials: false`; require `comment-on-alert: false` wherever historical `benchmark-action` remains. Require any `contents: write` permission to exist only on a job whose `if` restricts it to `push` on `refs/heads/main`.

- [ ] **Step 2: Implement Rust-native same-run capture and manual evidence.**

  Do not install or run a host Rust toolchain in the required native jobs. Build
  the digest-pinned Rust/Python image from only the base-worktree Dockerfile and
  an empty build context. The helper performs `cargo fetch --locked
  --manifest-path native/rust_ext/Cargo.toml` before the offline warm-up and
  twelve alternating `cargo bench --locked --offline --manifest-path
  native/rust_ext/Cargo.toml --bench conflict_bench --no-default-features --
  --output-format bencher` measurements. Store base/candidate `pair-01.txt`
  through `pair-12.txt` under a native-specific host-only artifact root and
  call the comparator with `--format bencher`. Set the manual dispatch input to
  required, validate/fetch it with the same base resolver, and keep all its
  jobs read-only and uniquely named.

- [ ] **Step 3: Move historical charts into a main-only publisher.**

  Keep `benchmark` and `rust-criterion` as read-only, advisory evidence jobs so their existing required context names still exist on PRs. Remove their `benchmark-action` calls and upload their raw outputs as artifacts. Add a separate `publish-performance-history` job that:

  - has `needs` on the four evidence/regression jobs;
  - has `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`;
  - alone declares `permissions: {contents: write}`;
  - downloads the raw advisory artifacts and invokes `benchmark-action/github-action-benchmark` with `auto-push: true`, `comment-on-alert: false`, and `fail-on-alert: false` for the Go and Criterion histories.

  The publisher must not run on PR or manual evidence paths. The two comparator jobs, not the publisher, own all outcomes for the required 110% contexts.

- [ ] **Step 4: Make native/manual/publisher contracts GREEN.**

  Run:

  ```powershell
  uv run pytest -q tests/test_quality_workflow_contract.py -k "performance or manual_performance"
  actionlint .github/workflows/benchmark.yml .github/workflows/manual-performance-evidence.yml
  ```

  Expected: no public PR code receives write credentials or a self-hosted execution route, and manual evidence cannot satisfy a required pull-request check.

### Task 5: Integrate, review, publish, and verify fresh remote evidence

**Files:**
- Modify: `docs/testing/roadmap-100-percent-quality-closure-plan.md` only after a fresh successful hosted run
- Read: all files changed by Tasks 1–4, `.github/actionlint.yaml`, current GitHub ruleset/run artifacts

**Interfaces:**
- Input: completed implementation and fresh workflow runs at the pushed commit.
- Output: published code, artifact-backed result, accurate roadmap evidence, or a narrow external blocker record.

- [ ] **Step 1: Run focused and cross-file local verification.**

  Run:

  ```powershell
  uv run pytest -q tests/test_compare_paired_benchmarks.py tests/test_capture_isolated_benchmarks.py tests/test_aggregate_go_benchmarks.py tests/test_quality_workflow_contract.py
  uv run ruff check scripts/quality/compare_paired_benchmarks.py scripts/quality/capture_isolated_benchmarks.py tests/test_compare_paired_benchmarks.py tests/test_capture_isolated_benchmarks.py tests/test_quality_workflow_contract.py
  uv run ruff format --check scripts/quality/compare_paired_benchmarks.py scripts/quality/capture_isolated_benchmarks.py tests/test_compare_paired_benchmarks.py tests/test_capture_isolated_benchmarks.py tests/test_quality_workflow_contract.py
  actionlint .github/workflows/benchmark.yml .github/workflows/manual-performance-evidence.yml
  git diff --check
  ```

  Expected: zero failures. If a command fails, use `superpowers:systematic-debugging` before modifying the implementation; do not paper over the failure with `continue-on-error` or reduced assertions.

- [ ] **Step 2: Conduct an independent focused code review before publication.**

  Review parser ambiguity, SHA validation/ancestry, trusted helper/comparator
  bootstrap behavior, container mounts/network/permissions/resource bounds,
  streaming output cap, image provenance, temporary-worktree cleanup, shell
  quoting, pair ordering, job permissions, branch/event guards, manual context
  disjointness, artifact coverage, and preservation of all required job names.
  Resolve every P1/P2 finding with a regression test and rerun Step 1. Ensure
  `.github/CODEOWNERS` owns the comparator, helper, and Dockerfile and the
  active ruleset requires code-owner review before merge.

- [ ] **Step 3: Commit and push the implementation.**

  Stage only approved changed paths, check the staged diff, and publish:

  ```powershell
  git diff --cached --check
  git commit -m "fix(quality): compare performance within one runner"
  git push origin egorribun
  git ls-remote --heads origin egorribun
  ```

  Expected: the remote branch SHA equals the local committed SHA and the pre-push checks pass.

- [ ] **Step 4: Obtain fresh hosted proof and inspect it.**

  Wait for the PR workflow at the new SHA; if the benchmark path is not triggered by the changed paths, dispatch a workflow that includes the same code/commit and required base SHA without changing source scope. Inspect both required jobs, download or view the artifacts, and verify `comparison.json` records twelve base/candidate values per metric, exact revisions, a GitHub-hosted run, the `1.1` threshold, and a comparator-owned decision.

  Run:

  ```powershell
  gh run list --commit <new-sha> --workflow benchmark.yml --json databaseId,status,conclusion,url
  gh run view <run-id> --log-failed
  ```

  Expected: both preserved required contexts are green due valid same-run evidence, not due `gh-pages` comparison.

- [ ] **Step 5: Update the roadmap only with live evidence, then publish that documentation separately.**

  Add the run ID, commit SHA, artifact/comparison fact, and remaining external certification blockers (Codecov authorization, absent DAST target, certification key, and genuine 30-day window) to the roadmap. Do not claim full closure until all external gates are genuinely satisfied. Re-run relevant roadmap/contract checks, commit as `docs(quality): record same-run performance evidence`, push, and verify the remote SHA.

## Plan self-review

- [ ] Confirm every approved-spec invariant maps to at least one test and implementation step: immutable revisions, GitHub-hosted-only execution, twelve alternating pairs, strict 1.10 threshold, deterministic one-sided bound, fail-closed parser, artifact retention, no PR write token, main-only advisory publisher, and manual-context isolation.
- [ ] Search this plan for unfinished planning markers before execution:

  ```powershell
  $forbidden = ('TO' + 'DO') + '|' + ('TB' + 'D') + '|' + ('place' + 'holder') + '|' + ('implement' + ' later') + '|' + ('fill' + ' in')
  rg -n -- $forbidden docs/superpowers/plans/2026-08-11-same-run-performance-gates.md
  ```

- [ ] Verify Markdown and repository diff integrity:

  ```powershell
  git diff --check -- docs/superpowers/plans/2026-08-11-same-run-performance-gates.md
  ```
