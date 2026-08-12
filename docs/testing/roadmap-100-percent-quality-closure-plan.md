# Closure Plan — Maximum Credible Test Coverage Roadmap

**Companion to:** `docs/testing/roadmap-100-percent-quality.md`
**Audit baseline commit:** `ce588bb0a1c08eb66ff2e5558349096a51d3ed4a` (the "finalize quality-roadmap" merge)
**Repository HEAD at audit snapshot:** `671b79c466348e37530d601f787404400e395723` (latest E2E navigation-stability hardening at that checkpoint)
**Audit date:** 2026-08-09
**Status:** the observations below are retained as an audit snapshot, not a claim about the current checkout. Certification remains fail-closed on terminal current-HEAD CI and full-nightly mutation evidence, the 30-day promotion prerequisites, authorized DAST/certification inputs, and unresolved third-party dependency findings.

> **Live enforcement policy (repository source, not remote certification):**
> `quality/quality-contract.json` requires `patch_coverage = 100` and
> `viable_mutant_score = 100`. The source wiring must still be confirmed by a
> terminal current-HEAD PR run and full-nightly artifact before it is treated as
> certification evidence.

## Final control audit — 2026-08-09

This checkpoint replaces stale “pending” conclusions from the historical
execution ledgers below. It does not turn a passing bounded PR gate into a
claim that the long-running or manually provisioned workstreams are complete.

### Current-HEAD evidence — 2026-08-09

- The latest pushed commits are `ac6b14d36`, `89961dc37`, `3268476dc`, and
  `671b79c46`. They close the observed hydration race in the login/a11y and
  settings/i18n flows, add bounded retries for Firefox `NS_BINDING_ABORTED`
  navigation aborts, and apply that retry helper to every remaining E2E
  `networkidle` navigation. Local repeated evidence is green: i18n is `32/32`
  across eight repetitions; the targeted notifications/schedule slice is
  `6 passed, 6 skipped` (the skips are service-worker-dependent cases); and
  the a11y target passed four repetitions.
- Fast CI run `31310271914` targets this exact SHA. Every executed test and
  artifact-producing step passed: Python four shards, frontend four Vitest
  shards plus aggregate merge, Go gateway/ws-hub/file-processor, Rust test
  suites, security/static/contract/migration jobs, and all four browser
  projects. The Chromium functional steps passed in all four shards; Firefox
  completed `52 passed, 65 skipped` with no page-navigation flake; WebKit and
  mobile-WebKit completed successfully; all Lighthouse lanes passed. The
  `13` job failures are exclusively the mandatory Codecov upload step after
  the preceding test/coverage/artifact steps succeeded. The run's aggregate
  `Coverage & Quality Policy Gate` is therefore skipped by its dependency,
  not failed by a coverage violation; the incremental mutmut shards remain
  in progress at this checkpoint.
- Exact raw artifacts from `31310271914` were recomputed with
  `scripts/quality/normalize_coverage_reports.py` in a Linux container using
  the same runner path as CI. The resulting manifest has
  `commit_sha=671b79c466348e37530d601f787404400e395723`,
  `validation.valid=true`, and `tier0` evidence for 54 files. The official
  `validate_quality_contract.py --manifest` check passed. This is exact
  current-HEAD artifact evidence, but it is recorded as a recomputation
  because the CI policy job could not upload its manifest after Codecov made
  the upstream jobs non-green.
- The current normalized values are shown in the table below. Unsupported
  counters remain `n/a`; missing infrastructure/scripts/workflows reports are
  not converted into false coverage claims. Rust crypto's `100% (0/0)` branch
  value means the source report contains no branch sites.

### Current normalized coverage — run `31310271914`, SHA `671b79c46`

| Component | Lines | Statements | Branches | Functions |
| --- | ---: | ---: | ---: | ---: |
| Python | 99.4904% | n/a | 98.5048% | n/a |
| Frontend | 99.4820% | 99.4820% | 98.0787% | 98.1013% |
| Go gateway | 98.8764% derived | 99.0809% | n/a | n/a |
| Go ws-hub | 98.7771% derived | 99.0119% | n/a | n/a |
| Go file-processor | 99.1372% derived | 99.2401% | n/a | n/a |
| Rust native | 100% | n/a | 100% | 100% |
| Rust PyO3 sanitizer | 99.3769% | n/a | 50% | 100% |
| Rust WASM sanitizer | 100% | n/a | 100% | 100% |
| Rust crypto | 100% | n/a | 100% (0/0) | 100% |
| Tier0 (54 files) | 100% (7266/7266) | unsupported by source reports | 100% (1732/1732) | 100% (532/532) |

- Full nightly run `31307154620` is still executing its full mutmut job on
  the earlier SHA `ac6b14d36`. Its four backend unit shards and Chromium
  functional workload completed successfully; their job conclusions are
  Codecov-only failures. Miri, disposable MinIO/SpiceDB, all backend
  integration shards, Firefox, WebKit, mobile-WebKit, and the nightly load/
  chaos lane completed successfully. Its full frontend mutation job also
  completed successfully: Stryker tested `33/33` mutants with `0 survived` and
  a `100.00%` score. There are no `frontend/src` changes between that SHA and
  the current HEAD, so the full frontend score remains exact for the current
  production tree. Current-HEAD nightly run `31310278607`
  is queued behind it under the intentionally non-canceling nightly
  concurrency group and cannot yet provide current-HEAD full-mutation proof.
- The current GitHub secret inventory still has no `CODECOV_TOKEN`, and OIDC
  authentication reaches Codecov but receives `Repository not found`. This
  remains an external repository-onboarding/authorization action; upload
  failures stay blocking by design.
- The live `main` stabilization calculation remains `eligible: false`: the
  16 completed nightly runs from 2026-07-24 through 2026-08-08 all concluded
  `failure`, so the required 30 consecutive green calendar days are `0/30`.
  The promotion workflow is present on this branch but cannot certify the
  default branch until it is merged and has eligible run history.
- DAST still has no authorized target URL, release certification still has no
  protected `QUALITY_CERTIFICATION_KEY`, and advisory Go integration,
  cross-browser, chaos/migration-resilience, and continuous-performance
  checks cannot be promoted without their documented live evidence. These
  are external deployment/evidence prerequisites, not silently closable
  repository TODOs.

### Live continuation — 2026-08-12 (published source SHA `1820e4efe`)

This dated section records fresh evidence without rewriting the historical
audit below. The source hardening from `763f4c260` (portable JSON nesting
guard) and `1820e4efe` (Dishka lifecycle/mutmut timeout repair) is published on
`egorribun`; PR [#1229](https://github.com/egorribun/university_ecosystem/pull/1229)
was merged to `main` as `c838c2000cf5b73d4dfa38dfa4a7d239c13cbb0b`.

- Focused local evidence on the published source commit is green:
  `uv run pytest -q tests/test_lifespan_restart_contract.py tests/test_lifespan.py`
  => `32 passed, 2 warnings`; the reconstructed mutmut lifecycle union =>
  `95 passed, 1 skipped, 3 warnings`. Ruff check, Ruff format check,
  `git diff --check`, and all pre-push hooks passed.
- Fast CI run
  [31553098588](https://github.com/egorribun/university_ecosystem/actions/runs/31553098588)
  targets `1820e4efeba721260f37d20b4995dd69b9c5359a` and is terminal
  `success`: 104 jobs, 99 successful, 5 skipped, 0 failed. `CI Success`,
  `Coverage & Quality Policy Gate`, and all exact mutmut shards (`16/16`)
  passed.
- Current performance run
  [31553098414](https://github.com/egorribun/university_ecosystem/actions/runs/31553098414)
  is terminal `success` for Go, WS-Hub regression, Rust Criterion, and Rust
  native optimizer gates; history publication was intentionally skipped.
  SQLMap smoke run
  [31553098424](https://github.com/egorribun/university_ecosystem/actions/runs/31553098424)
  is also terminal `success` on the same SHA.
- Codecov processing is independently confirmed for source SHA
  `1820e4efeba721260f37d20b4995dd69b9c5359a`: the v2 commit endpoint returned
  HTTP 200 with `state=complete`, `ci_passed=true`, total line coverage
  `99.47%` (`84,927/85,371` hits, `917` files), `12` sessions, and `100%`
  diff coverage. The current OIDC uploads were accepted and queued without a
  repository-authorization error. The later `ae0cee538`/`54a1d1871` commits
  are documentation-only descendants, so this is source-equivalent evidence;
  no new code coverage upload is expected for them.
- Full nightly run
  [31555962606](https://github.com/egorribun/university_ecosystem/actions/runs/31555962606)
  targets the exact published source SHA `ae0cee53866945da9b3a298e48a05a9bb7d02757`
  but is still `pending` behind the older non-canceling diagnostic run
  [31543639360](https://github.com/egorribun/university_ecosystem/actions/runs/31543639360).
  The earlier queued run `31554388135` was automatically cancelled when this
  newer run was dispatched; no running workflow was manually cancelled.
  No full-mutation, Stryker, Miri, load/chaos, browser-matrix, or nightly
  artifact score may be inferred until the current-SHA run is terminal and
  its artifacts are inspected.
- External blockers remaining are an explicitly authorized DAST target (local
  SQLMap is not authorization), the
  protected `QUALITY_CERTIFICATION_KEY`, the 30-day stabilization window,
  advisory-workload promotion evidence, and a managed filesystem permission
  profile for the formal Deep Security Scan. This roadmap remains fail-closed;
  the goal is not complete from these results alone.

### Security hardening continuation — 2026-08-12 (published `7973577a9`)

The current canonical `egorribun` tip is
`7973577a9d45ed4e2d0f6cc955c26ee454a274b5`, pushed and verified on the remote.
The preceding `71acdac82` commit hardens push-subscription SSRF validation and
moves Codecov OIDC uploads and release/deploy credentials behind trusted `main`
conditions; `db9c3dc6b` additionally scopes nightly workflow permissions, and
`7973577a9` closes the IPv4-mapped IPv6 literal bypass in the SSRF blocklist. PR
test jobs no longer receive `id-token: write` or inherited secrets. The selected
changed-file pre-commit suite, YAML parsing, actionlint, Semgrep, Ruff, mypy,
and the focused SSRF regression tests are green (`120 passed, 3 warnings`); the
broader selected push/SSRF/quality-contract run remains `142 passed, 3
warnings`.

- The standard Codex Security scan
  `9ccd3274-fd28-4971-93ae-362bec838d8e` completed before this hardening and
  reported three bundled npm dependency findings (two high, one medium:
  `ip-address`, `brace-expansion`, and `undici`). The application SSRF and CI
  credential findings were remediated in `71acdac82`; the bundled dependency
  findings remain explicitly open because the release tool owns those copies
  and `npm audit fix --package-lock-only --dry-run` cannot safely replace them.
  A fresh local `npm audit --package-lock-only` reports `7` advisories
  (`2` high, `5` moderate), while the GitHub Dependabot API reports `6` open
  alerts (`1` high, `5` moderate); both are the same nested npm-tooling
  exposure viewed through different advisory databases.
  The formal Deep Scan remains unavailable under the current host permission
  profile and is not claimed as passed.
- Current full nightly
  [31559213815](https://github.com/egorribun/university_ecosystem/actions/runs/31559213815)
  targeted `71acdac8204c6331f5fd56aee62a4abcc984d53d` but was automatically
  cancelled by GitHub's single-pending-run queue at 2026-08-12T03:19:38Z when
  the newer main-branch run
  [31559727370](https://github.com/egorribun/university_ecosystem/actions/runs/31559727370)
  (SHA `c838c2000cf5b73d4dfa38dfa4a7d239c13cbb0b`) entered the queue. No
  running workflow was manually cancelled. The old diagnostic run
  [31543639360](https://github.com/egorribun/university_ecosystem/actions/runs/31543639360)
  remains in progress; after it releases the slot, the main run must start
  before a new exact-`7973577a9` dispatch is queued. No nightly score or
  artifact result is inferred until the relevant current-HEAD run is terminal
  and its mutation, Stryker, Miri, browser, load/chaos, and coverage artifacts
  are inspected.
- A fresh stabilization-window query over completed `main` nightly runs,
  evaluated on 2026-08-12, returned `eligible: false`,
  `latest_success_date: null`, and no successful dates in the required 30-day
  interval. DAST still has no authorized target URL and release certification
  still has no protected `QUALITY_CERTIFICATION_KEY`; these remain external
  blockers rather than repository code gaps.
- Codecov's v2 commit endpoint for merged `main` SHA
  `c838c2000cf5b73d4dfa38dfa4a7d239c13cbb0b` is independently complete:
  `state=complete`, `ci_passed=true`, 99.47% total coverage
  (`84,925/85,371` hits, 917 files, 12 sessions), and 100% diff coverage.
  This is source-equivalent evidence for the merged quality code; the security
  branch still needs its own trusted-main integration run after merge.

### Local hardening update — 2026-08-10 (not certification evidence)

This is local candidate evidence for the current worktree. It must be linked
to a terminal current-HEAD PR run and full-nightly artifacts after publication;
it is not a replacement for external certification.

- The complete Python suite passed with isolated xdist workers and strict
  async-warning gates:
  `uv run pytest -q -n 16 -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`
  produced `7210 passed, 71 skipped, 298 warnings` in `938.51s`. The warnings
  are separately reported known Pydantic, dependency-deprecation, and
  environment-gated notices; the two enforced warning classes were clean.
- The focused quality-closure selection also passed with those gates:
  `370 passed, 8 warnings` in `187.89s`. Its warnings are the known Pydantic
  and structlog exception-formatting notices, not un-awaited coroutine paths.
- Local test hardening now models synchronous repository/session APIs with
  `MagicMock` and asynchronous APIs with `AsyncMock`. It closes four formerly
  hidden un-awaited-coroutine paths in media, notification retry, reset-MFA,
  and DB-DLQ listener tests. The affected five modules passed the same strict
  warning gates (`124 passed`).
- Mutation evidence handling now fails closed on early errors, reserves its
  budget per child workflow, and permits safe empty shards. `Dockerfile.test`
  uses a restricted build context that excludes secrets and caches; its smoke
  test passed (`19 passed`). The DAST workflow now fails explicitly when no
  authorized target URL is supplied.
- Changed Python files passed Ruff check and format check; the changed Python
  sources/scripts passed `py_compile`; `uv lock --check`, YAML parsing for the
  quality workflows, and `actionlint v1.7.7` also passed.
- The formal Codex Security diff scan did not create a scan because the
  working tree changed after selection. Manual scoped security reviews are
  useful local evidence, but they are not reported as a completed formal scan.

The external blockers above remain unchanged: Codecov repository authorization,
an authorized DAST target, the protected certification key, terminal
current-HEAD PR/full-nightly artifacts, the `0/30` stabilization window, and
promotion evidence for advisory workloads. None may be marked closed from this
local update.

### Historical evidence retained from earlier checkpoints

Everything in this subsection is retained for reproducibility only; it is not
the live certification basis for the current SHA.

- The audit began from a clean tree at `d5bedc62991caf7f3d9618974b8a9a3a5e310ea1`;
  quality-gate hardening was then committed as `702278a8d`, `465c29055`, and
  `b9405c5da` (the dependency-policy contract was updated with the newly
  pinned security cutoffs and passed its remote shard), `1394a79bc` (the
  repeated-mutmut Dishka lifecycle regression was fixed and covered locally),
  `825141d0d` (manual performance dispatch was added), `a23052dc4` (the
  lifecycle-owned Dishka shutdown marker was added after the first fresh
  nightly still found a global-ASGI lifecycle leak), `d8a25844e` (the lifespan
  test's package import was aliased so it cannot replace the FastAPI app fixture
  during the second context-manager scenario), and `113e91723` (lifespan now
  recreates closed application containers; the infrastructure fixture installs
  a fresh full container at every boundary; and a restart contract test covers
  the closed-root path).
  The earlier fresh evidence below remains tied to its exact source commit.
- The fresh remote CI run `31272523668` for source commit
  `496ed7f2c5c0fd33da738b4687b4c31281f14d7e` completed with `105` jobs,
  `success`, and zero failed jobs. Its normalized quality manifest was valid
  and the quality-contract validator passed.
- The active `main` ruleset `8335285` is enforced and now contains the core
  CI, coverage, inventory, backend/frontend, Go, Rust, contract, security,
  migration, Helm, Docker, workflow, and Kyverno checks. The documented admin
  bypass remains intentionally enabled under the repository bypass policy.
- Local static and contract checks passed: `uv lock --check`, Ruff check and
  format, mypy (349 files), source/test inventory, 224 quality-contract tests,
  frontend typecheck, ESLint, Prettier, i18n parity, dead-code and dependency
  checks. The complete frontend Vitest suite also passed on the local Node 26
  host.
- Local Go unit suites passed for gateway, ws-hub, file-processor, uni-cli, and
  SPIFFE. Local Rust tests and stable/nightly LLVM coverage runs passed for
  native, PyO3 sanitizer, WASM sanitizer, and rust-crypto. Local `go test
  -race` cannot run on this Windows host because CGO is enabled but no C
  compiler is installed; the remote current-HEAD Go integration job passed.
- The full local Python coverage run exceeded the 30-minute host budget before
  producing an aggregate artifact. The complete four-shard Python result from
  the fresh current-HEAD CI run is therefore the authoritative aggregate for
  this checkpoint. This is an environment-duration limitation, not evidence
  of a Python test failure.
- Codecov uploads were reproduced as rejected when no repository token was
  available. The upload path is now switched to Codecov OIDC with explicit
  GitHub `id-token: write` permissions and `fail_ci_if_error: true`; the empty
  token inputs were removed so OIDC is the sole authentication path. The fresh
  run `31276786678` successfully obtained OIDC tokens and completed the test
  work, but Codecov rejected every upload with `Repository not found`. The
  repository must be onboarded/authorized in Codecov (or receive a valid
  repository token) before this external gate can be certified. The fresh
  current-HEAD CI run `31278744917` for `b9405c5da` completed with `105` jobs:
  all repository tests and quality jobs passed, while the `13` component
  Codecov uploads returned the same `Repository not found` response and the
  aggregate `CI Success` job consequently failed closed.
- Follow-up local regression evidence is current: the quality closure slice
  passes `231` tests; the targeted provider-replacement sequence passes `22/22`
  (`test_schedule_api_coverage.py`, `test_search_api.py`, and `test_graphql.py`);
  Ruff, `uv lock --check`, and the repository dependency
  audit pass. The Python lock now removes unused `diskcache`, pins patched
  `h2>=4.4.1`, and constrains transitive `mcp` to the patched `<2` line.
- The targeted repeated-lifecycle regression is now green locally: the full
  GraphQL file passed twice through separate `pytest.main()` runs (`15 + 15`),
  while the broader Windows clean-test profile timed out at its 15-minute host
  budget without producing a test failure. The old nightly run `31275975109`
  then reached terminal `failure` before mutation scoring: its clean-test
  phase failed at `tests/test_graphql.py::test_graphql_schedule_query` with
  `assert 0 == 1` after the app-level Dishka container had been closed and
  reused. The first fixture-only reset in `1394a79bc` did not observe a
  container closed by an earlier global `TestClient` lifespan; the lifecycle-
  owned marker fix is in `a23052dc4`. Its backend shard exposed a test-only
  package-import rebinding, fixed in `d8a25844e` and covered locally by all
  `28` lifespan tests. Fresh nightly run `31288102177` is executing against
  `d8a25844e`, and its terminal result is intentionally pending.
- The fresh remote performance run `31287050376` on source commit
  `825141d0d` completed successfully across all four jobs: Go benchmarks,
  WS-Hub's blocking 110% regression gate, Rust Criterion, and the native
  optimizer's blocking 110% regression gate.
- In fresh nightly `31288102177`, all four backend unit shards completed their
  pytest workloads successfully (`1775`–`1795` passed tests per shard). Their
  job conclusions are failure only because the fail-closed Codecov uploads
  still receive `Repository not found`, matching the already documented
  external authorization blocker.
- The same nightly's Chromium matrix completed its functional suites with
  `56` passed and `61` skipped; its only failure was the frontend E2E Codecov
  upload returning `Repository not found`. Firefox, WebKit, and mobile-WebKit
  completed successfully.
- The live stabilization query for `main` returned `16` completed nightly
  runs from 2026-07-24 through 2026-08-08, all with `failure` conclusions.
  Running `check_stabilization_window.py` against that API response for
  `2026-08-09` produced `eligible: false`, `latest_success_date: null`, and
  `no successful workflow run is available`. The promotion workflow is present
  on this pushed branch but is not yet registered on default `main`; GitHub's
  dispatch API therefore returned `404 workflow ... not found on the default
  branch` until the branch is merged.

### Historical normalized coverage (run `31272523668`; not current HEAD)

The following values are from the historical CI manifest named in this
heading, not from the current HEAD. “n/a” means that the source report format
does not provide that counter; it is not silently treated as 100%.

| Component | Lines | Statements | Branches | Functions |
| --- | ---: | ---: | ---: | ---: |
| Python | 99.5097% | n/a | 98.5262% | n/a |
| Frontend | 99.4999% | 99.4999% | 98.1009% | 98.1013% |
| Go gateway | 98.8764% derived | 99.0809% | n/a | n/a |
| Go ws-hub | 98.7771% derived | 99.0119% | n/a | n/a |
| Go file-processor | 99.1372% derived | 99.2401% | n/a | n/a |
| Rust native | 100% | n/a | 100% | 100% |
| Rust PyO3 sanitizer | 99.3769% | n/a | 50% | 100% |
| Rust WASM sanitizer | 100% | n/a | 100% | 100% |
| Rust crypto | 100% | n/a | 100% (0/0) | 100% |
| Tier0 (54 files) | 100% (7266/7266) | unsupported by source reports | 100% (1730/1730) | 100% (532/532) |

The contract deliberately enforces no Rust component branch floor because the
PyO3 sanitizer's native branch report is 50%; its required line/function
floors pass. Tier0's strict per-file line/branch/function validator passes all
54 matched files, while the generator still labels the aggregate as
`measurement_only` by design.

The local Node 26 V8 report measured 99.4979% statements, 98.0935% functions,
and 97.6824% branches; the repository CI contract runs Node 22 and its fresh
normalized artifact passes 99/98/98. No Node 22 runtime is installed on this
host, so the local branch discrepancy remains an environment-specific
verification note rather than a code change inferred from a mismatched
instrumentation runtime.

### Historical closure status at the audit snapshot (not current HEAD)

- Closed and evidenced at the historical audit SHA: local regression fixes,
  browser-navigation stability, functional fast-matrix execution, exact raw
  artifact normalization, aggregate coverage floors, Tier0 per-file metrics,
  Checkov/Kyverno, contracts, Schemathesis, migrations, security jobs, Go
  integration execution, and the repository's blocking incremental mutation
  wiring. The exact manifest and contract validator both pass; the CI policy
  job itself is skipped only because its required upstream Codecov uploads are
  fail-closed.
- Not yet closure-certified: current-HEAD full nightly/mutmut completion,
  Codecov repository authorization, the 30-day green stabilization window, and promotion of
  advisory Go integration, cross-browser, chaos/migration-resilience, and
  continuous-performance checks. DAST still requires an authorized target URL
  and release signing still requires the protected certification key. These
  are explicit evidence or deployment prerequisites, not reasons to weaken a
  gate.
- The historical Checkov findings and file-processor Pact mismatch cited by
  the older ledger are no longer current blockers: `.checkov.yml` is blocking
  with scoped skips, current Checkov/Kyverno/contract jobs pass, and the
  historical wording remains below only as audit history.

### Historical phase text and current-state reconciliation

The execution plan below was intentionally retained as an audit trail. Its
“currently absent”, baseline-count, and “task” paragraphs describe the state
that existed when the plan was written, not a second live backlog. The live
closure matrix for this audit is:

| Workstream | Current repository evidence | State |
| --- | --- | --- |
| Python, frontend, Go, Rust, and Tier0 coverage | Exact raw artifacts from `31310271914`, recomputed manifest for SHA `671b79c46`, contract validator, Tier0 per-file checks | current metrics pass contract floors; CI upload is blocked only by Codecov |
| Stateful/property testing and disposable MinIO/SpiceDB cells | Fast CI functional jobs plus nightly container cell | closed in code; current-HEAD nightly evidence tracked |
| Python mutmut and frontend Stryker | Python source uses immutable PR-base SHA selection, exact mutant-name shards, a 25-minute wall-clock failure boundary (20-minute maximum execution cap, 30-second KILL grace, and four-minute proof/upload reserve), scope-local JSON evidence, and a 100% viable-score gate; the full nightly uses the same exporter in `--all` mode. The cited Stryker run remains historical evidence only. | terminal current-HEAD PR and full-nightly artifacts are still required; a source inspection or old frontend run is not renewed certification |
| Go goleak/fuzz/integration and Rust fuzz/proptest/Miri | Go workflows/tests, Rust suites, nightly Miri job | repository wiring and bounded execution pass; promotion/evidence history tracked |
| Pact, schema compatibility, browser matrix, SSR cache assertions | contract workflow/provider verification, four-project browser matrix, production SSR E2E | current functional checks pass; promotion window tracked |
| Checkov, Kyverno, negative security, performance baselines | blocking Checkov, Kyverno tests, security suites, Lighthouse and benchmark gates | current fast security/Lighthouse checks pass; durable current-HEAD baseline and promotion evidence tracked |
| Dashboard and certification | quality-history workflow, dashboard/certification generators, release hook, runbook | repository wiring closed; durable certification remains key/window dependent |
| Codecov | all callers use OIDC and fail closed; current run `31310271914` reaches OIDC but gets `Repository not found` | blocked on Codecov repository authorization |
| Advisory promotion | `scripts/quality/check_stabilization_window.py` and `quality-promotion-check.yml` | intentionally blocked until 30 consecutive green calendar days (`0/30`) |

### Live source enforcement (not certification evidence)

- Pull-request mutation execution resolves the immutable PR base SHA, assigns
  exact mutant names to shards, and fails beyond a 25-minute total wall-clock
  deadline. Its stats-derived execution cap is at most 20 minutes; after the
  30-second KILL grace, four minutes remain for proof, score verification, and
  upload. If setup leaves less than the verified shard budget, the job fails
  rather than emitting incomplete evidence. The exporter writes scope-local
  machine-readable evidence before the blocking 100% viable-score gate runs.
- The full nightly run starts from a newly-created `mutants/` directory, runs
  the complete mutmut universe, and invokes the same exporter with `--all` so
  `caught_by_type_check` is preserved as an accepted kill.
- A score is eligible to pass only when the universe is non-empty and each
  evaluated mutant is conclusively killed by tests or a configured type check.
  Survivors and `timeout`, `suspicious`, `no_tests`, `not_checked`, `skipped`,
  `interrupted`, or `segfault` evidence fail closed.
- Load/chaos remains a nightly, advisory workstream while the Temporal CI boot
  issue is unresolved. The obsolete dispatch-only `ci.yml` job and its inert
  `Load and Chaos Resilience Tests` context were removed; the matching context
  must be removed from active ruleset `8335285` during the controller's remote
  reconciliation. This is not a promotion claim.
- These statements describe reviewed repository source. They do not replace a
  terminal current-HEAD PR run, a full-nightly artifact, Codecov authorization,
  or the required 30-day promotion evidence.

## Execution ledger — 2026-07-27 (uncommitted)

This section records only independently verified results from the current closure
work. The historical measurements below remain unchanged so that the original
audit baseline is reproducible. Python reports were collected with `uv run` and
checked one file at a time after bounded test runs; no `.md` or `.diff` file is
intended for the checkpoint commit.

### Verified closures

- Python Tier0/auth, metrics/observability, cache, database, NATS, and the
  previously closed long-tail modules remain verified from the earlier
  checkpoint.
- `app/core/config/mixins/jwt_settings.py`: 133/133 statements, 48/48 branch
  pairs.
- `app/core/config/mixins/csp_settings.py`: 155/155 statements, 48/48 branch
  pairs.
- `app/api/ws/presence.py`: 159/159 statements, 50/50 branch pairs.
- `app/api/ws/connection_manager.py`: 209/209 statements, 64/64 branch pairs.
- `app/api/spotify.py`: 261/261 statements, 72/72 branch pairs.
- `app/api/notifications.py`: 297/297 statements, 90/90 branch pairs.
- `app/services/notifications/news_events.py`: 147/147 statements, 52/52
  branch pairs.
- `app/services/notification_templates.py`: 362/362 statements, 196/196
  branch pairs.
- `app/services/privacy_cleanup.py`: 91/91 statements, 4/4 branch pairs.
- `app/utils/request_coalescing.py`: 72/72 statements, 14/14 branch pairs.
- Notification model/repository and cleanup closures added during this session
  are also verified at 100% in their isolated reports.
- Go bounded verification on 2026-07-27: `go test ./... -count=1 -timeout=90s`
  passed for gateway (7 packages, 34s), ws-hub (4 packages, 9s), and
  file-processor (6 packages, 11s). Their fresh local statement profiles are
  87.9%, 81.9%, and 88.0%, respectively; these are measurements, not closure
  claims. Existing ws-hub and gateway `TestMain` goleak checks completed as
  part of the passing package runs. Local `-race` is blocked by the Windows
  environment lacking a C compiler (`go test -race` requires CGO).
- Additional Go modules `services/cmd/uni-cli` and `services/pkg/spiffe` also
  passed their bounded `go test ./...` runs.
- Frontend bounded verification: `npm run typecheck` passed and a one-worker
  Vitest smoke selection passed 24/24 tests. The full Vitest suite was not
  allowed to run unbounded on this host after its 120-second guard expired.
- Frontend property-based verification: the fast-check utility contract suite
  passed 5/5 in one worker. The scoped Stryker run mutated one pure utility file
  with 33 mutants and killed all 33 (100.00% mutation score) under
  `--concurrency 1`; generated reports remain temporary and uncommitted.
- CI wiring fixes verified by contract tests/static inspection: cross-browser
  advisory mode is now passed as an explicit reusable-workflow input (so the
  caller has no invalid job-level `continue-on-error`), the opt-in load/chaos
  job no longer uses a constant-false condition, and the GitHub Actions MinIO
  service no longer uses an unsupported `command` key. Full actionlint and
  remote CI verification remain open.
- Targeted Ruff is clean for all closure/contract test files changed in this
  session. A full `uv run ruff check tests` still reports 34 pre-existing
  findings in unrelated stress/security/tenant tests; those were not silently
  rewritten as part of this closure batch.
- Fixed a real testing-mode observability defect in
  `app/core/logging.py`: console structlog now formats positional `%s`
  arguments before event renaming. The logging regression suite passes 11/11.
- Regenerated frontend API SDK/types and MSW mocks from a freshly generated
  FastAPI OpenAPI document. The generated diff now includes `ChallengeState`,
  `MfaChallengeOut.state`, and the audit time-travel endpoint; frontend
  `npm run typecheck` passes, followed by a bounded one-worker API smoke of
  24/24 tests. Remote drift rerun remains pending.
- Fixed the Pact provider workflow's localhost service wiring by publishing
  Postgres/Redis ports; its workflow contract suite passes 14/14. A remote
  provider rerun remains pending.
- Fixed the file-processor Pact body mismatch at its source: the consumer and
  provider now declare the JSON-encoded protobuf representation as
  `application/json`, allowing Pact V4 structural matchers to run instead of
  comparing matcher documents as opaque `application/grpc` bytes. File-
  processor Go tests pass; remote Pact verification remains pending.

## Execution ledger — 2026-07-30 (uncommitted)

- Frontend service-worker API caching tests now cover the private
  session-aware `NetworkFirst` handler: session cache isolation, shared-cache
  fallback, and the synthetic 6-second timeout response. The isolated file
  passes 34/34 tests with one Vitest worker; `src/sw/api.ts` measures 100% for
  lines, branches, functions, and statements in the targeted coverage run.
- Fixed test-only mock lifecycle leakage in
  `frontend/src/sw/__tests__/api.test.ts`: `vi.restoreAllMocks()` was restoring
  the Workbox constructor to an empty mock between tests, producing a false
  `strategy.handle is not a function` failure. The teardown now clears calls,
  restores globals, and explicitly restores real timers.
- Frontend fast-check coverage expanded with idempotency properties for
  `sanitizeArticleHtml` and `sanitizeHttpUrl`; the property suite passes 7/7
  in one worker. Targeted ESLint and `npm run typecheck` pass.
- Current HEAD remains the user's `0b8d305c6`; the working tree intentionally
  contains the uncommitted frontend, Go, Python-test, and ledger changes from
  this closure session. No `.diff` or temporary coverage artifacts are part of
  the intended checkpoint.
- Rust verification on the resumed branch: `native/rust_ext` passes 48/48
  tests and measures 99.89% lines / 98.92% functions with
  `cargo llvm-cov --no-default-features`; `frontend/rust-crypto` passes 2 lib
  tests plus 15 native integration/property tests; `frontend/wasm-sanitizer`
  passes 15/15 integration/property tests. The fuzz/proptest wiring already
  present in both frontend Rust crates is therefore locally verified; remote
  fuzz/Miri/coverage runs and stabilization evidence remain open.
- Fresh `uv` verification on the resumed HEAD: quality workflow/contract/
  configuration suites pass 48/48, and the metrics regression set passes
  64/64. The earlier remote metrics failure is not reproducible in the local
  bounded suites after the current branch's credential-normalization fix.
- Fresh Tier0 auth measurement on the resumed tree: 122 bounded tests pass;
  `app/services/auth/lockout.py`,
  `app/services/auth/graphql_token_validator.py`,
  `app/services/auth/login_session_manager.py`, `app/auth/security.py`, and
  `app/api/auth/login.py` all measure 100% lines and 100% branches. The
  metrics/observability slice also passes 92/92 with both
  `app/core/metrics.py` and `app/core/observability.py` at 100% lines and
  branches.
- Fresh cache-specific measurement passes 162/162; `app/deps/cache.py`
  measures 100% lines and 100% branches across the Memory, Redis, cluster,
  NATS KV, tiered-cache, decorator, and error-path cases.
- Fresh configuration measurement passes 97/97; `app/core/config/notifications.py`
  measures 100% lines and 100% branches with the notification/configuration
  closure tests.
- Fresh event API measurement passes 57/57 with one PostgreSQL-only test
  skipped by its explicit marker; `app/api/events.py` measures 100% lines and
  100% branches.
- Fresh users API measurement passes 13/13; `app/api/users.py` measures 100%
  lines and 100% branches.
- Fresh news API measurement passes 28/28; `app/api/news.py` measures 100%
  lines and 100% branches.
- Fresh push-router measurement passes 113/113 across the focused router,
  endpoint, and booster suites; `app/routers/notifications.py` now measures
  100% lines and 100% branches. The final missing `unsubscribe` rate-limit
  branch is covered by a direct HTTP 429/retry-after regression test.
- Notification support slices are also locally closed: the schema suite passes
  6/6 with `app/schemas/notifications.py` at 100% lines and branches, the
  model closure passes 2/2 with `app/models/notifications.py` at 100% lines,
  and the push-service slice passes 70/70 with
  `app/services/push_service.py` at 100% lines and branches. The package-wide
  model measurement is intentionally reported as a per-file result because
  unrelated model files remain below the global floor in that narrow run.
- Fresh stats API measurement passes 18/18; `app/api/stats.py` measures 100%
  lines and 100% branches. Fresh sessions API measurement passes 13/13 after
  adding the cookie-token fallback regression; `app/api/sessions.py` now
  measures 100% lines and 100% branches.
- Fresh health API measurement passes 30/30; `app/api/health.py` measures
  100% lines and 100% branches. Fresh config-base measurement passes 38/38;
  `app/core/config/base.py` measures 100% lines and 100% branches.
- Fresh cache/database settings measurement passes 41/41, including the
  cgroup-v1/v2 and fallback cases; both `app/core/config/cache.py` and
  `app/core/config/database.py` measure 100% lines and 100% branches.
- Frontend push-subscription closure advanced with public failure/recovery
  scenarios for permission denial, registration fallback, VAPID lookup errors,
  persistence 409/429/permanent failures, concurrent ensure locking, stale
  unsubscribe, local cleanup, browser lookup failures, and recovery resync.
  The bounded one-worker push set passes 57/57; targeted `src/push/subscribe.ts`
  coverage is now 88.92% lines, 83.07% branches, and 100% functions. Remaining
  defensive storage/concurrency branches stay explicitly open for the broader
  frontend 99/98/98 target.
- Frontend WebSocket closure advanced: the combined one-worker suites for
  `src/tests/hooks/useChatWebSocket.test.tsx` and
  `src/hooks/__tests__/useChatWebSocket.test.tsx` pass 52/52. The targeted
  `src/hooks/useChatWebSocket.ts` report measures 100% lines/statements, 98.18%
  branches, and 100% functions. Covered behavior includes ticket auth/transient
  failures, reconnect caps and terminal close codes, room rejoin/leave races,
  heartbeat cleanup, typing expiry/caps, read/reaction/message frame cache
  updates, RxDB fallback/error paths, and the 200-message sliding window. The
  whole frontend long-tail and global 99/98/98 target remain open.
- `useProfileSync` closure advanced with 74 bounded one-worker tests across
  bootstrap, encrypted/legacy/versioned cache restore, migration, storage and
  BroadcastChannel synchronization, cancellation, error handling, and crypto
  failures. Targeted `src/hooks/auth/useProfileSync.ts` coverage now measures
  93.34% lines, 85.65% branches, and 100% functions. This work also fixed two
  production defects exposed by the tests: `readCachedEnvelope()` now parses
  and returns the stored JSON envelope, and the render-only encrypted-cache
  placeholder (`id: "-1"`) is no longer inserted as authoritative TanStack
  Query data. SSR/LHCI-specific and remaining defensive branches stay open.
- Frontend `api/client.ts` closure advanced with 57 bounded one-worker tests
  across the existing ETag, retry, rate-limit, language, SSR-cookie, CSRF, and
  instance suites plus new LHCI adapter, BroadcastChannel, abort, ETag-error,
  rate-limit-bypass, and legacy-wrapper regressions. The combined run passes
  57/57; targeted coverage measures 96.92% lines, 80% branches, and 100%
  functions. The roadmap's broader frontend 99/98/98 target remains open; the
  remaining uncovered cases are defensive URL/header and rate-window branches.
- Frontend rate-limit interceptor closure advanced with 21 bounded one-worker
  tests, including concurrent queue release, rolling-window backpressure,
  timer replacement, online recovery, abort reasons, and non-GET release
  guards. The combined run passes 21/21; targeted coverage measures 92.85%
  lines, 93.82% branches, and 100% functions. The remaining branches are
  defensive queue-notification guards that are not reachable through the
  exported API without mutating private waiter state.
- Frontend `useLoginFlow.ts` closure advanced from 20 to 26 bounded hook tests:
  passkey validation short-circuit plus recovery-code MFA expired/success,
  locked, generic, and Axios-detail paths are now exercised. The targeted run
  passes 26/26 and measures 100% lines/statements and functions, with 96.34%
  branches; only defensive suggestion/passkey fallback branches remain.
- Frontend Trusted Types utility closure advanced to 10 bounded tests covering
  policy caching, CSP creation failures, failure sentinels, safe HTML fallback,
  same-origin/backend-origin URL allowlisting, and malformed backend origins.
  The targeted run passes 10/10 and measures 98.86% lines, 84.21% branches,
  and 88.88% functions; only the defensive invalid `window.location` parse
  catch remains unreachable in jsdom.
- Frontend `useWebAuthn.ts` now has an isolated 11-test hook suite covering
  credential loading/non-array and failure responses, dialog resets, browser
  support, registration validation/success/428 step-up/retry and error
  fallbacks, plus deletion success/step-up/error paths. The one-worker run
  passes 11/11 and measures 100% lines/statements and functions, with 95.65%
  branches; only two defensive branch outcomes remain.
- Post-closure frontend integration check is clean: the new hook mocks pass
  Prettier, ESLint, and the repository-wide `npm run typecheck`; the final
  targeted WebAuthn run remains 11/11 with one worker.
- Frontend `useDndSettings.ts` closure expanded from 4 to 9 bounded hook tests:
  disable/update payloads, HH:MM:SS and non-standard values, no-op and
  in-flight guards, end-time blur, and Axios validation-array aggregation are
  now covered. The targeted run passes 9/9 with 100% lines/statements and
  functions and 87.05% branches; remaining branches are null-normalization
  and disabled blur guards that are defensive/no-op paths.
- Frontend `usePasswordChange.ts` closure expanded from 5 to 11 bounded hook
  tests covering all local validation states, `ok:false` response handling,
  busy-submit suppression, 428 step-up callback/retry, classified current/same
  password errors, generic and validation-array Axios details. The targeted
  run passes 11/11 with 100% lines/statements and functions and 96.22%
  branches; two defensive detail-resolution outcomes remain.
- Frontend `useSessionManagement.ts` now has a real-QueryClient 10-test hook
  suite covering tab gating/query errors, current/active/revoked sorting,
  single-session revoke/logout, revoke-all, step-up retry callbacks, API
  detail/generic failures, and timestamp formatting. The targeted run passes
  10/10 with 100% lines/statements and functions and 83.63% branches; four
  defensive null/formatting outcomes remain.
- Frontend `useTotpEnrollment.ts` now has an isolated 11-test hook suite
  covering derived MFA state, pending-enrollment auto-resume, start/confirm/
  cancel flows, step-up retry, limit guards, refresh, and error/snackbar paths.
  The bounded one-worker run passes 11/11 and measures 95.45% lines,
  93.75% branches, and 100% functions; the remaining uncovered lines are
  defensive fallback and callback-identity outcomes. The heavyweight full
  `Settings.totp` UI coverage run remains intentionally open after exceeding
  the bounded execution window; no fresh test process remains active.
- Frontend `useEmailChange.ts` closure expanded to 11 bounded hook tests for
  required/no-change/pending-email validation, busy-submit suppression,
  successful refresh, step-up retry, invalid-password and string-detail
  handling, validation-array aggregation, and missing-user state. The targeted
  run passes 11/11 and measures 100% lines/statements and functions with
  98.24% branches; the only remaining branch is a defensive resolver path
  superseded by the handler's earlier Axios-detail classification.
- Frontend `useNowPlaying.ts` closure expanded to 11 stable bounded tests for
  request validation/header policy, payload normalization, null/204 responses,
  invalid cache and storage failures, 401 reauthentication, 429 retry-after
  variants, cache persistence, and visibility-triggered refetch. The one-worker
  run passes 11/11 and measures 91.71% lines, 88.57% branches, and 82.35%
  functions; only the production polling/retry callback branches remain open,
  because polling is intentionally disabled in Vitest's test environment and
  the real QueryClient terminal-error seam is not bounded-stable.
- Frontend `MfaChallengeView.tsx` closure expanded to 18 behavior and
  accessibility tests covering empty-email fallback, no-methods, TOTP submit
  and trust-device paths, TOTP-specific errors, WebAuthn supported/unsupported
  states, both-method separator, recovery-code Enter/button/empty/back paths,
  busy controls, general errors, restart affordance, and axe checks. The
  bounded one-worker run passes 18/18 with 100% statements, lines, and branches;
  the remaining 77.77% function metric consists only of browser/start-over
  callback wrappers without additional decision logic.
- Frontend `NowPlayingCard.tsx` image lifecycle closure expanded to 8 tests
  covering image load/error fallback, hover transforms, track reset, paused
  progress, generic Spotify fallback, and zero-duration safety. The targeted
  run passes 8/8 and measures 88.36% lines, 59.45% branches, and 83.33%
  functions; the remaining paths are production-only animation/reduced-motion
  branches intentionally bypassed by the test-environment guard.
 - Frontend `InstallPrompt.tsx` closure expanded to 32 combined bounded tests
   covering install accepted/dismissed/rejected flows, suppression windows,
   malformed and failing storage, app-installed cleanup, push unsupported/
   denied/default/granted visibility, Safari guidance, LHCI suppression, update
   toast lifecycle, and success/error/info feedback. The one-worker run passes
   32/32 and measures 92.18% lines, 90.14% branches, and 90.9% functions; the
   remaining block is the granted-toggle JSX that is intentionally hidden by
   the preceding `pushSupported && permission === "granted"` visibility effect.
 - Frontend `NewsDetail.tsx` closure expanded to 7 bounded tests covering
   loading/error recovery, browser-history fallback, swipe navigation and the
   Firefox reading-progress fallback, localized rendering, share options/copy,
   deletion success, and deletion failure feedback. The one-worker run passes
   7/7 and measures 100% statements/lines, 90.47% branches, and 61.9%
   functions; the remaining function/branch gaps are callback/render variants
   without uncovered executable statements.
 - The remote rerun of job `90699730876` (`90716869133`, commit
  `0b8d305c6`) completed with one failure after 3,662 passes. A minimal local
  reproduction identified the deterministic cause: `test_force_reload_security_config`
  left a reloaded `app.core.config` singleton behind, while the metrics module
  retained its imported singleton. The config reload test now restores the
  module objects, and the authorization test patches `metrics.settings` at the
  lookup site. The exact repro passes 3/3, the config/metrics slice passes
  65/65, and the final combined quality/config/metrics regression slice passes
  123/123; a fresh remote run is still required before claiming CI closure.
- Gateway vector-router closure on the resumed branch: targeted behavioral
  tests cover state-string/default/collision/removal paths, fallback routing,
  HTTP 400/500 responses, gRPC validation/filtering, and multi-shard routing.
  The root `gateway` package passes all tests at 99.2% statements; all seven
  `services/gateway/...` packages pass their bounded suite. One defensive
  error branch in `ExecuteVectorQuery` remains structurally unreachable because
  `Route` converts `ErrEmptyRing` into the documented fallback result.
- ws-hub bounded verification on the resumed branch: all four
  `services/ws-hub/...` packages pass; the hub package's safe JetStream ACK/NAK
  nil/core-message guards and WebTransport nil/closed paths are now directly
  exercised. The hub package measures 81.4% statements locally, so
  transport/bootstrap and long-running subscriber paths remain open rather
  than being overstated as closed.
- Production SSR cache-policy E2E smoke passes 1/1 in a single Chromium worker:
  HTML is `no-store, private, max-age=0`, hashed assets are immutable for one
  year, and the service-worker response is non-cacheable. The production build
  previously reported a 726 KB `index-*` chunk (and a 1,003 KB map vendor
  chunk), above the repository's 500 KB main-bundle budget. A bounded fresh
  production build after adding explicit vendor splits for RxDB/Dexie,
  accessibility helpers, router core, validation, and TanStack Start now
  produces `index-C41OwRrZ.js` at 339,661 bytes (331 KiB), below the 500 KiB
  CI limit. The exact budget check and `npm run typecheck` both pass; the map
  vendor chunk remains separately cacheable and does not count as the main
  chunk.
- Phase 9.1 cache-poisoning hardening: `cached_endpoint` now includes the
  current tenant context in every cache identity, in addition to the existing
  authenticated-user identity; the repository-level news cache key now also
  carries the tenant context. The tenant-isolation regression suite passes
  20/20, and targeted Ruff is clean for the four changed cache/security files.

### Still open

The roadmap is not fully certification-complete. The remaining gates are
Codecov repository authorization; current-HEAD full nightly/mutmut evidence;
the required 30-day green stabilization window;
promotion of the currently advisory Go integration, cross-browser, and
chaos/migration-resilience checks; a current durable performance baseline; an
authorized DAST target; and the protected release certification key. The
repository wiring and bounded functional evidence are present, but these
items must not be marked complete from YAML presence or bounded
unit-coverage evidence alone.

## 0. Why this document exists

An audit of `docs/testing/roadmap-100-percent-quality.md` against the real repository state found that the roadmap is **not complete**, despite its own checkboxes marking Waves 0–1 `[x]`. The final "finalize quality-roadmap" PR (#1207, merge commit `ce588bb0a`) was merged into `main` while its own **"Coverage & Quality Policy Gate"** and **"CI Success"** required jobs were reporting `failure`. This was possible because neither the classic branch-protection API nor the active GitHub ruleset (`id 8335285`) on `main` ever listed those jobs in `required_status_checks` — a governance gap, not a one-off mistake.

This document is the actionable closure plan. It is organized as phases with concrete files, functions, line/branch counts, and CI changes. Every number quoted below was measured directly, not estimated:

- Python: recomputed via `scripts/quality/normalize_coverage_reports.py` and direct XML parsing against `backend-coverage-All-Python 3.14/coverage.xml` downloaded from CI run `29842664722` (the last run that actually executed on the final merged tree).
- Go: recomputed via `go tool cover -func=coverage.out` against the three downloaded `go-coverage-services-*` artifacts from the same run.
- Rust: recomputed via `cargo llvm-cov` JSON (`rust-coverage/*/llvm.json`) from the same run.
- Frontend: recomputed via `frontend-coverage/coverage-final.json` (Istanbul/v8 format) from the same run.
- Governance: recomputed live via `gh api repos/egorribun/university_ecosystem/rulesets/8335285` and `.../branches/main/protection`.

## 1. Decisions already made (do not re-litigate these during implementation)

| Question                                                                                                                                                                                                                                     | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Governance model for a de-facto solo-maintainer repo                                                                                                                                                                                         | **Technical self-enforcement.** Add every blocking CI job to the GitHub ruleset's `required_status_checks`. Do not rely on human review discipline as the primary gate. `ownership-mapping.json`/`CODEOWNERS` become accurate documentation, not blocking review gates, because there is no second active contributor (`Semeno-v` has `write` access but 0 commits in the entire history).                                                                                                                                    |
| `quality-contract.json` floors (99%/98% Python, 99% Go statements, 100% Tier0, 100% mutation score, 100% diff coverage) vs. the historically lower CI floors (90% Go, 85% mutation, 80% diff coverage) | **Ratchet up to the contract values.** Do not lower the contract. Source now enforces the 100% patch-coverage and viable-mutation policy; the historical lower figures are retained only to explain the original audit conflict. Remote evidence remains separately required. |
| Chromium-only E2E vs. the roadmap's required Firefox/WebKit/mobile-WebKit matrix                                                                                                                                                             | **Include the full matrix as its own workstream with an explicit stabilization budget** (Phase 7), landed as advisory-then-blocking, mirroring the existing `go-integration-*` advisory→blocking precedent already used in this repo.                                                                                                                                                                                                                                                                                         |
| CI gating strategy once ~15 more jobs become required                                                                                                                                                                                        | **Fast PR gate + nightly full gate on `main`.** Only bounded-duration jobs (unit tests, coverage, lint, incremental mutation) block PRs. Long-running suites (full-repo mutation score, load/chaos, the new browser shards) run nightly via `schedule: cron` + `workflow_dispatch` (the pattern already used by `weekly-cleanup.yml` and `dast.yml`) and become required for merges to `main` only after they are green for 30 days, exactly like the existing `go-integration-*` promotion criterion documented in `ci.yml`. |
| `bypass_actors: [{actor_type: RepositoryRole, actor_id: 5 (admin), bypass_mode: always}]` on the ruleset                                                                                                                                     | **Left technically unchanged** (not selected for hardening in this plan). Documented explicitly as an accepted risk for a solo-owned repository, with a _process_ rule (state the bypass reason in the PR description) rather than a technical lock — because removing admin bypass on a single-owner repo risks the owner locking themselves out with no path to override a false-positive gate.                                                                                                                             |

## Phase G — Governance and branch-protection hardening (do this first)

Rationale for going first: every other phase's "done" state can be silently unmerged again if the enforcement gap that let PR #1207 land with failing gates is not closed first.

### G.1 — Add real required status checks to the ruleset

Current `required_status_checks` on ruleset `8335285` (`main`):

```text
CI Diagnostic
Pre-commit & Linting (Read-only)
```

`ci-success` and `coverage-policy-gate` are absent, and `ci-success`'s own dependency array does **not** even reference `security-audit`'s sub-jobs correctly in a way GitHub treats as a single check name — verify actual GitHub check-run names (they can differ from job ids) before adding.

**Task G.1.1** — Enumerate the exact GitHub check-run _display names_ (not YAML job ids) for every job that must gate merges. Use `gh api repos/egorribun/university_ecosystem/commits/<sha>/check-runs` on a recent commit to get the authoritative name list, since display names come from the workflow's `name:` field, not the job key.

**Task G.1.2** — Add to `required_status_checks.required_status_checks[]` in the ruleset (via `gh api --method PUT repos/.../rulesets/8335285` or the repo Settings UI):

- `CI Success`
- `Coverage & Quality Policy Gate`
- `Source/Test Inventory & Anti-Pattern Check`
- `Backend Tests (Python 3.14) / Unit Tests (All-Python 3.14)`
- `Backend Tests (Python 3.14) / Integration Tests (All-Python 3.14)`
- `Backend Type Check`
- `Frontend Tests / Lint & Format`
- `Frontend Tests / Unit Tests`
- `Frontend Tests / Production Build`
- `Go Tests (services/gateway) / Test Go Service (services/gateway)`
- `Go Tests (services/ws-hub) / Test Go Service (services/ws-hub)`
- `Go Tests (services/file-processor) / Test Go Service (services/file-processor)`
- `Go Tests (services/cmd/uni-cli) / Test Go Service (services/cmd/uni-cli)`
- `Rust — cargo test (×3 crates) + wasm-pack + coverage`
- `Rust Lint & Format`
- `Alembic Migrations`
- `DB Migration Gate (Postgres)`
- `Helm Lint & Validate`
- `Contract Tests`
- `Schemathesis — API Schema Conformance`
- `OpenAPI Backward Compatibility Check` (from `contract-validation.yml`)
- `Verify OpenAPI Types`
- `Security Audit / Semgrep SAST`
- `Security Audit / Python Dependency Audit`
- `Security Audit / Node.js Dependency Audit`
- `Security Audit / Go Vulnerability Scan`
- `Security Audit / detect-secrets Baseline Integrity`
- `Trivy Image Scan`

**Historical classification (superseded)** — `mutation-tests-incremental` is
now a blocking input to `ci-success`. Full-nightly promotion remains subject to
the separate evidence and stabilization process; the other long-running lanes
listed here retain their individually documented promotion conditions.

**Task G.1.4** — Re-verify with a throwaway PR that a deliberately-broken `coverage-policy-gate` now blocks merge (cannot be bypassed except by the documented admin override in G.3).

### G.2 — Fast/Full CI split

See Phase 14 (Ratchet sequencing table) for the authoritative ratchet floors; the fast/full job classification is described inline below. Summary of the mechanics:

**Implemented source wiring** — `.github/workflows/nightly-full-gate.yml`
uses `schedule: cron: "0 1 * * *"` and `workflow_dispatch`. Its mutation lane
runs full-repo `mutmut run` without an incremental filter, then writes
`mutants/mutmut-cicd-stats.json` through
`scripts/export_mutmut_shard_stats.py --all` and applies the fail-closed 100%
viable-score checker. The workflow also carries the long-running load/chaos,
browser-matrix, Go-integration, Kyverno, and Miri lanes. Source wiring is not
evidence that a particular nightly revision has completed successfully.

**Task G.2.2** — Add a Slack/GitHub-issue-on-failure step to `nightly-full-gate.yml` so nightly regressions are not silently ignored (there is no PR to fail against).

**Task G.2.3** — Promotion is measured by `quality-promotion-check.yml`,
which calls `scripts/quality/check_stabilization_window.py` against completed
nightly runs and fails closed until every day in the required 30-day window is
green. Only then may the named checks be added to the ruleset; the workflow
never changes branch protection automatically.

### G.3 — Document (do not remove) the admin bypass

**Task G.3.1** — Add a `## Bypass policy` section to `AGENTS.md` (or `CONTRIBUTING.md` if one exists) stating: admin-role bypass on the `main` ruleset is intentionally left at `bypass_mode: always` because this is a single-active-maintainer repository and a hard lock risks an unrecoverable deadlock (e.g., a required check breaks due to a third-party service outage with no other admin to grant an exception). Any bypass merge must state the specific reason in the PR description or merge commit message. This is a process control, not a technical one, and is explicitly weaker than a hard block — accepted as a known, documented trade-off.

### G.4 — Fix fictitious ownership mapping

**Task G.4.1** — In `quality/ownership-mapping.json`, replace every `@backend-team`, `@frontend-team`, `@go-team`, `@rust-team`, `@devops-team`, `@platform-team`, `@security-team` value with the real, single active owner (`@egorribun`). Keep the path-prefix structure (it is still useful for the orphan/ownership checker in `scripts/quality/check_orphans_and_anti_patterns.py`), only the owner string changes.

**Task G.4.2** — In `.github/CODEOWNERS`, replace `@security-team`/`@devops-team` references with `@egorribun`. Keep `require_code_owner_review: true` in the ruleset as-is (it currently resolves to the same single person, so it adds no false safety but also no false friction).

**Task G.4.3** — Re-run `scripts/quality/generate_test_inventory.py` + `scripts/quality/check_orphans_and_anti_patterns.py` locally after G.4.1 to confirm no owner-resolution regression (the checker will now resolve every path to `@egorribun`; confirm it still passes with `Quality inventory validation passed`).

### G.5 — Codecov integration (OIDC, fail-closed)

**Task G.5.1** — All Codecov callers now request GitHub OIDC with
`id-token: write` and set `use_oidc: true`; the repository no longer depends
on a manually created `CODECOV_TOKEN`.

**Task G.5.2** — `codecov.yml` is present with per-component flags and the
same contract floors for Python, frontend, Go, native Rust, PyO3, WASM, and
rust-crypto.

**Task G.5.3** — Backend, frontend, E2E, Go, and Rust upload callers are all
present and use `fail_ci_if_error: true`; the post-change CI run is the final
remote proof that must show both successful OIDC authorization and accepted
uploads. Run `31276786678` proved the OIDC exchange but Codecov returned
`Repository not found`, so this task remains externally blocked.

### G.6 — Checkov blocking gate — closed

`.checkov.yml` contains only scoped, documented skips;
`.github/workflows/checkov.yml` has no `soft_fail` escape hatch, and the
current remote Checkov job passed. Further work is governance promotion and
review of the skip register when IaC changes.

## Phase 0 — Close the Tier0 measurement gap

Historical phase note (superseded by the current-HEAD evidence above): the
roadmap's Wave 2 exit gate and the "Definition of maximum" both require 100%
line/branch/function coverage and explicit negative-path tests for every Tier0
path. The old plan text below predates the Tier0 implementation; the current
`scripts/quality/normalize_coverage_reports.py` now emits per-file Tier0
evidence and `validate_quality_contract.py` validates it against the contract.

**Task 0.1** — Extend `normalize_coverage_reports.py` to accept the already-existing `quality/ownership-mapping.json` `tier0_rules` glob list and cross-reference it against every parsed report's per-file breakdown (Python XML, Go coverprofile per-line, Rust llvm-cov per-file, frontend LCOV per-file) to produce a `tier0` aggregate: `{lines: {covered, total, percent}, branches: {...}, functions: {...}, files: [{path, component, lines_percent, branches_percent, ...}]}`.

**Task 0.2** — Update `quality/coverage-manifest.schema.json` to make `tier0` a required, non-nullable object (currently implicitly allows `null` because nothing populates it).

**Task 0.3** — Update `validate_quality_contract.py`'s consumption in the `coverage-policy-gate` CI step (or add a new dedicated check step) to fail the job if any Tier0 file's line, branch, or function coverage is below 100% — not just the aggregate `tier0.coverage` contract floor, but per-file, matching the roadmap's literal wording ("Every Tier 0 ... path has 100% line, branch and function coverage").

**Task 0.4** — This phase has a hard dependency on Phase 2.1 (Python Tier0 file closure) landing first, or the new gate will immediately fail CI on rollout. Land Task 0.1–0.2 (measurement only, non-blocking) before Task 0.3 (enforcement).

## Phase 1 — Wave 1 remediation: activate historical-duration sharding

`tests/conftest.py` already implements a correct greedy bin-packing shard algorithm keyed off `quality/test-durations.json` (`--shard-id`/`--num-shards` pytest options), but no workflow ever passes these flags — `reusable-backend-tests.yml` only uses `pytest-xdist -n auto`.

**Task 1.1** — Decide sharding strategy: keep `xdist -n auto` for intra-shard parallelism (it is legitimately better for CPU-bound-per-worker distribution) and layer the existing `--shard-id`/`--num-shards` on top for splitting the suite across separate CI runner matrix legs (the two mechanisms are complementary, not redundant — xdist parallelizes within one runner, `--shard-id` splits across runners).

**Task 1.2** — Add a `strategy: matrix: shard: [0, 1, 2, 3]` to the `backend-tests` job in `ci.yml`, passing `--shard-id=${{ matrix.shard }} --num-shards=4` alongside the existing `-n auto`, splitting backend test wall-clock time roughly 4x.

**Task 1.3** — Regenerate `quality/test-durations.json` from the CI `pytest-report.xml` (junit timing data) after every significant test-suite change; add a small `scripts/quality/update_test_durations.py` helper that parses `pytest-report.xml` and rewrites the JSON, and call it as a post-step in `reusable-backend-tests.yml` with the output committed via a scheduled bot PR (weekly, alongside `weekly-cleanup.yml`).

## Phase 2 — Python backend coverage closure

Current measured state (component `python`): **95.54% lines (17,971/18,809), 85.92% branches (3,471/4,040)**. Contract floor: **99% lines, 98% branches**. Gap: **838 lines, 569 branches** at the aggregate level. (Note on totals: the sum of missing lines and branches across the 114 individual files in Phase 2.2 totals 1003 lines / 648 branches. This static snapshot variance occurs because Phase 2.3 branch-only files and XML condition-coverage rounding are excluded from the Phase 2.2 line-gap list, while the aggregate gap reflects the net repository deficit against contract floors. Treat per-file numbers as the authoritative work breakdown.)

### 2.1 — Tier0 files (mandatory 100%, do these before anything else in this phase)

| File                                           | Lines gap    | Branches gap |
| ---------------------------------------------- | ------------ | ------------ |
| `app/services/auth/lockout.py`                 | 12 (134/146) | 11 (33/44)   |
| `app/services/auth/graphql_token_validator.py` | 4 (69/73)    | 3 (15/18)    |
| `app/services/auth/login_session_manager.py`   | 2 (71/73)    | 0 (8/8)      |
| `app/auth/security.py`                         | 2 (232/234)  | 1 (61/62)    |
| `app/api/auth/login.py`                        | 1 (118/119)  | —            |

For each: read the file, identify the exact uncovered lines via `coverage report --show-missing` (or open `coverage.xml`'s `<line number=... hits="0">` entries), write behavior-level tests through the public service/API surface (per the roadmap's "Replace coverage boosters that only call internals with behavioural tests" instruction — do not add trivial internal-call tests here, these are Tier0 auth paths and need real negative-path assertions: expired/malformed tokens, lockout threshold boundaries, concurrent login-session races).

### 2.2 — Non-Tier0 line-coverage closure, ordered by total missing (lines + branches) descending

Work through this list top-to-bottom; it is already sorted so the highest-leverage files come first. Each row is `path — lines missing / branches missing`.

1. `app/core/metrics.py` — 38 / 63
2. `app/core/observability.py` — 59 / 32
3. `app/deps/cache.py` — 40 / 27
4. `app/api/ws/presence.py` — 35 / 20
5. `app/core/config/notifications.py` — 32 / 20
6. `app/api/ws/connection_manager.py` — 22 / 25
7. `app/api/spotify.py` — 29 / 17
8. `app/api/notifications.py` — 29 / 15
9. `app/api/events.py` — 30 / 11
10. `app/api/users.py` — 32 / 7
11. `app/services/notifications/news_events.py` — 16 / 23
12. `app/core/nats_broker.py` — 25 / 13
13. `app/api/news.py` — 20 / 17
14. `app/core/config/base.py` — 22 / 15
15. `app/repositories/chat_repository.py` — 24 / 10
16. `app/schemas/schemas.py` — 19 / 14
17. `app/core/events.py` — 20 / 7
18. `app/api/health.py` — 22 / 4
19. `app/core/localization/core.py` — 15 / 8
20. `app/api/stats.py` — 17 / 5
21. `app/services/partition_manager.py` — 16 / 6
22. `app/services/notifications/schedule_reminders.py` — 9 / 13
23. `app/schemas/notifications.py` — 11 / 10
24. `app/api/sessions.py` — 12 / 8
25. `app/core/database.py` — 8 / 12
26. `app/core/config/mixins/jwt_settings.py` — 13 / 7
27. `app/models/users.py` — 12 / 8
28. `app/repositories/user_repository.py` — 13 / 7
29. `app/routers/notifications.py` — 9 / 11
30. `app/api/schedule.py` — 16 / 2
31. `app/core/container.py` — 18 / 0
32. `app/core/config/cache.py` — 12 / 5
33. `app/services/chat/creation_service.py` — 9 / 8
34. `app/core/config/database.py` — 12 / 3
35. `app/api/deps/auth.py` — 9 / 5
36. `app/api/internal/csp_report.py` — 10 / 4
37. `app/core/cache.py` — 8 / 6
38. `app/services/stats_cache.py` — 6 / 8
39. `app/core/ssrf.py` — 9 / 4
40. `app/repositories/news_repository.py` — 9 / 4
41. `app/services/nats_messaging.py` — 6 / 7
42. `app/services/user/profile_service.py` — 8 / 5
43. `app/services/event_handlers.py` — 8 / 4
44. `app/services/notifications/delivery.py` — 4 / 8
45. `app/repositories/schedule_repository.py` — 7 / 4
46. `app/services/audit_service.py` — 4 / 7
47. `app/services/image_proxy.py` — 9 / 2
48. `app/utils/files.py` — 5 / 6
49. `app/api/stories.py` — 8 / 1
50. `app/cli/migrate_passwords.py` — 4 / 5
51. `app/core/config/mixins/cors_settings.py` — 4 / 5
52. `app/services/file_scanner.py` — 5 / 4
53. `app/services/notification_queue.py` — 8 / 1
54. `app/services/schedule_service.py` — 6 / 3
55. `app/core/localization/formatting.py` — 2 / 6
56. `app/management/weekly_cleanup.py` — 4 / 4
57. `app/models/user_loaders.py` — 5 / 3
58. `app/scripts/backfill_uuids.py` — 5 / 3
59. `app/services/event_service.py` — 3 / 5
60. `app/api/images.py` — 3 / 4
61. `app/core/config/mixins/csp_settings.py` — 2 / 5
62. `app/core/middleware/content_size.py` — 4 / 3
63. `app/cqrs/queries.py` — 2 / 5
64. `app/management/normalize_static.py` — 4 / 3
65. `app/models/stories.py` — 3 / 4
66. `app/utils/migrations.py` — 6 / 1
67. `app/api/ws/authenticator.py` — 4 / 2
68. `app/cli/db.py` — 4 / 2
69. `app/models/auth.py` — 4 / 2
70. `app/services/notification_service.py` — 6 / 0
71. `app/services/notifications_retention.py` — 5 / 1
72. `app/services/chat/attachment_service.py` — 3 / 3
73. `app/services/user/media_service.py` — 3 / 3
74. `app/utils/request_coalescing.py` — 2 / 4
75. `app/core/event_decorators.py` — 2 / 3
76. `app/core/feature_flags.py` — 4 / 1
77. `app/core/internal_access.py` — 3 / 2
78. `app/services/notification_templates.py` — 1 / 4
79. `app/services/privacy_cleanup.py` — 4 / 1
80. `app/services/user_service.py` — 5 / 0
81. `app/services/user/compliance_service.py` — 2 / 3
82. `app/services/user/logic.py` — 2 / 3
83. `app/api/admin/audit.py` — 2 / 2
84. `app/core/cache_versioning.py` — 4 / 0
85. `app/core/config/app_gen.py` — 2 / 2
86. `app/services/cache_warmup.py` — 2 / 2
87. `app/services/ical.py` — 2 / 2
88. `app/main.py` — 2 / 1
89. `app/api/websocket.py` — 3 / 0
90. `app/cli/infra.py` — 3 / 0
91. `app/core/task_registry.py` — 2 / 1
92. `app/core/middleware/request_id.py` — 2 / 1
93. `app/services/data_access.py` — 2 / 1
94. `app/services/geolocation.py` — 1 / 2
95. `app/api/ws/ticket.py` — 2 / 0
96. `app/core/health.py` — 1 / 1
97. `app/core/spicedb_watch.py` — 1 / 1
98. `app/core/config/security.py` — 1 / 1
99. `app/core/config/storage.py` — 1 / 1
100. `app/core/di/spicedb.py` — 1 / 1
101. `app/core/policies/csp.py` — 1 / 1
102. `app/models/notifications.py` — 2 / 0
103. `app/repositories/active_session_repository.py` — 2 / 0
104. `app/repositories/user_stats_repository.py` — 2 / 0
105. `app/services/fraud_detection_service.py` — 1 / 1
106. `app/services/story_cleanup.py` — 2 / 0
107. `app/services/auth/login_session_manager.py` (branches only, already listed in 2.1 for lines) — see 2.1
108. `app/services/notifications/cleanup.py` — 1 / 1
109. `app/workers/outbox.py` — 2 / 0
110. `app/api/dlq.py` — 1 / 0
111. `app/repositories/audit_repository.py` — 1 / 0
112. `app/services/email_change_cleanup.py` — 1 / 0
113. `app/services/mfa_challenge_cleanup.py` — 1 / 0
114. `app/services/password_reset_cleanup.py` — 1 / 0
115. `app/services/push_service.py` — 1 / 0
116. `app/services/geolocation.py` (duplicate entry, see 94)

### 2.3 — Branch-only closure (files already at 100% lines, branches still short)

These files need only new _branch_ conditions covered (e.g., an `if/else` arm, an exception path, a default-parameter fallback), not new lines — typically 1-3 targeted test cases each:

`app/core/protocols.py` (16 branches), `app/services/chat/command_service.py` (10), `app/services/auth_service.py` (6), `app/api/validation.py` (4), `app/repositories/base.py` (4), `app/openapi.py` (3), `app/core/circuit_breaker.py` (3), `app/core/config/__init__.py` (3), `app/services/notifications/core.py` (3), `app/core/event_retry.py` (2), `app/core/security_headers.py` (2), `app/core/spicedb.py` (2), `app/repositories/health_repository.py` (2), `app/services/news_service.py` (2), `app/services/story_service.py` (2), `app/services/auth/fingerprint_service.py` (2), and 19 additional files with exactly 1 missing branch each (`app/api/ws/serializers.py`, `app/auth/rbac.py`, `app/auth/handlers/logout.py`, `app/core/event_dlq.py`, `app/core/event_registry.py`, `app/core/middleware/response_hardening.py`, `app/core/middleware/setup.py`, `app/cqrs/bus.py`, `app/graphql/schema.py`, `app/management/reset_mfa.py`, `app/routers/schedule.py`, `app/services/minio_storage.py`, `app/services/push_topics.py`, `app/services/ws_hub_client.py`, `app/services/user/analytics_service.py`, `app/services/user/stats_service.py`, `app/utils/pagination.py`, `app/workers/notifications.py`, `app/core/ratelimit/circuit_breaker.py`).

### 2.4 — Replace mock-only "disposable" integration cells with real containers

The roadmap requires "disposable PostgreSQL, Valkey, NATS, MinIO and SpiceDB integration cells." Postgres/Valkey/NATS already use real containers (via `tests/conftest.py`'s `testcontainers.postgres.PostgresContainer` pattern and the `docker-compose`-backed integration test services). MinIO and SpiceDB do not.

**Task 2.4.1** — Add a `testcontainers.minio.MinioContainer` (or equivalent generic container wrapper if the official module lacks one) fixture to `tests/conftest.py`, gated the same way as the existing Postgres container (`USE_TESTCONTAINERS_MINIO=1` env var, falling back to mocks only when unset — do not remove the existing mock-based unit tests in `tests/test_minio_storage_coverage.py`, they remain valid as fast unit tests; add a new `tests/integration/test_minio_integration.py` for the container-backed cell).

**Task 2.4.2** — Add a disposable SpiceDB container (official `authzed/spicedb` image supports an in-memory `--datastore-engine=memory` flag for exactly this use case) fixture, and a new `tests/integration/test_spicedb_integration.py` exercising real ReBAC permission checks (not mocked `core/spicedb.py` calls) — schema load, relationship write, permission check, permission revoke, and negative "denied" assertions.

**Task 2.4.3** — Update `tests/chaos/test_minio_chaos.py` to run its failure-injection scenarios (S3Error, timeout) against the real container via network fault injection (reuse the existing ToxiProxy setup already present for other chaos tests — see `docker-compose.infra.yml`) instead of `unittest.mock.MagicMock`.

### 2.5 — Hypothesis stateful testing

The roadmap requires "Hypothesis/Schemathesis **stateful**/property tests." Current `tests/test_property_based.py` and `tests/test_pydantic_routes_hypothesis.py` use `@given`/`strategies` but zero `RuleBasedStateMachine` usage.

**Task 2.5.1** — Add a `RuleBasedStateMachine` in `tests/test_property_based.py` (or a new `tests/test_stateful_ratelimit.py`) modeling the rate limiter / circuit breaker (`app/core/circuit_breaker.py`, referenced by Tier0 rules) state transitions: `record_success`, `record_failure`, `is_open`, `half_open_probe` as rules, with invariants asserting the breaker never allows requests through while genuinely open and always resets after the cooldown window.

**Task 2.5.2** — Add a second `RuleBasedStateMachine` modeling session/login lockout lifecycle (`app/services/auth/lockout.py`) — `record_failed_attempt`, `record_successful_login`, `is_locked`, `time_advance` as rules, with an invariant asserting the account is never lockable below the configured threshold and never permanently locked past the configured window.

### 2.6 — Mutation testing gate rework

**Historical planning baseline (superseded; retained for audit):** At the time
this section was written, the gate used an 85% score, a 20-minute budget,
silent verification skip, and advisory classification.

**Implemented enforcement wiring (not certification evidence):**
`policy.viable_mutant_score` is `100`. Pull-request mutation execution uses
the immutable PR base SHA, exact-name shards, a 25-minute fail-closed
wall-clock budget (20-minute execution cap, 30-second KILL grace, and
four-minute evidence reserve), and scope-local machine-readable statistics.
The checker accepts only complete
evidence: every evaluated mutant must be killed by tests or a configured type
check; survivors, an empty universe, and `timeout`, `suspicious`, `no_tests`,
`not_checked`, `skipped`, `interrupted`, or `segfault` fail the gate. The
nightly lane evaluates the complete universe with the same exporter in `--all`
mode. A terminal current-HEAD PR run and full-nightly artifact are still
required before this source wiring can be certified.

**Implemented registry:** `quality/mutation-exclusions.json` exists, is
schema-validated, and currently has no exclusions. A future equivalent-mutant
record must include path, reason, owner, issue, evidence, and expiry; it must
not silently create a passing denominator.

**Promotion boundary:** `mutation-tests-incremental` is already a blocking
input to `ci-success`. Fresh ruleset/API evidence is still required before
claiming branch-protection status; the 30-day window applies to promotion of
the full and other advisory lanes.

### 2.7 — diff-cover floor

**Task 2.7.1** — In `reusable-backend-tests.yml`, change `uv run diff-cover coverage.xml --compare-branch=origin/$compareBranch --fail-under=80` to `--fail-under=100`, but land this **last**, after Phase 2.2's backlog is materially reduced — otherwise every future PR touching a still-uncovered legacy file will be blocked on unrelated legacy debt. Sequence: raise to 90 once 2.2 items 1–60 are closed, then 100 once 2.2 is fully closed.

## Phase 3 — Frontend coverage closure

Current measured state (component `frontend`): **91.81% lines, 82.12% branches, 82.21% functions** — all three already clear the contract floor (91/82/82). The remaining gap is not about hitting the contract minimum; it is about hitting the roadmap's actual stated target of "at least 99% line/statement coverage" for handwritten production components (the `frontend` component's contract floor of 91/82/82 is itself a placeholder floor below the roadmap's stated 99%/98% "maximum" language — this is flagged in Phase 14's ratchet table).

Raw counts across the whole `src/`: **4,056 missing statements, 1,955 missing branches, 388 missing functions** across 537 files with any gap.

### 3.1 — Highest-leverage files (top 60 by total missing units, descending)

Each row: `path — missing statements / missing branches / missing functions`.

1. `src/hooks/auth/useProfileSync.ts` — 252 / 48 / 6
2. `src/push/subscribe.ts` — 129 / 78 / 0
3. `src/pages/StoriesAdmin.tsx` — 144 / 27 / 13
4. `src/pages/Profile.tsx` — 107 / 26 / 14
5. `src/components/map/WeatherParticles.tsx` — 128 / 3 / 10
6. `src/pages/settings/hooks/useWebAuthn.ts` — 91 / 2 / 2
7. `src/hooks/useChatWebSocket.ts` — 69 / 23 / 1
8. `src/api/client.ts` — 48 / 27 / 7
9. `src/pages/Schedule.tsx` — 58 / 15 / 4
10. `src/pages/Register.tsx` — 41 / 23 / 9
11. `src/components/auth/MfaChallengeView.tsx` — 59 / 3 / 6
12. `src/components/profile/NowPlayingCard.tsx` — 36 / 28 / 3
13. `src/pages/NewsDetail.tsx` — 42 / 8 / 14
14. `src/components/pwa/InstallPrompt.tsx` — 47 / 13 / 1
15. `src/pages/settings/hooks/useSessionManagement.ts` — 50 / 7 / 4
16. `src/components/messenger/ChatWindow.tsx` — 25 / 33 / 1
17. `src/components/news/NewsCardEditDialog.tsx` — 36 / 20 / 2
18. `src/pages/EventDetail.tsx` — 37 / 11 / 10
19. `src/pages/settings/hooks/useTotpEnrollment.ts` — 44 / 13 / 1
20. `src/hooks/useNowPlaying.ts` — 29 / 21 / 5
21. `src/components/dashboard/ScheduleCard.tsx` — 34 / 17 / 2
22. `src/pages/settings/hooks/useDndSettings.ts` — 29 / 22 / 0
23. `src/components/messenger/NewChatModal.tsx` — 34 / 12 / 3
24. `src/features/news/components/NewsFormDialog.tsx` — 21 / 27 / 1
25. `src/hooks/features/useMessengerController.ts` — 19 / 30 / 0
26. `src/contexts/MessengerContext.tsx` — 33 / 14 / 1
27. `src/pages/settings/SettingsSecurity.tsx` — 40 / 6 / 2
28. `src/components/stories/StoryViewer.tsx` — 28 / 19 / 0
29. `src/features/events/components/EventsHeader.tsx` — 33 / 11 / 3
30. `src/components/messenger/ChatArea.tsx` — 13 / 27 / 6
31. `src/components/map/MapLibreMap.tsx` — 30 / 7 / 7
32. `src/components/map/MapSearchBar.tsx` — 29 / 11 / 3
33. `src/components/settings/ui/Layout.tsx` — 35 / 6 / 2
34. `src/contexts/AppShellContext.tsx` — 19 / 23 / 1
35. `src/hooks/auth/useLoginFlow.ts` — 39 / 3 / 0
36. `src/api/interceptors/rateLimit.ts` — 31 / 10 / 0
37. `src/components/schedule/ScheduleMobileView.tsx` — 26 / 12 / 3
38. `src/components/dashboard/WeatherAmbient.tsx` — 35 / 4 / 0
39. `src/components/events/EventDetailEditDialog.tsx` — 24 / 14 / 1
40. `src/components/mfa/OtpEntry.tsx` — 31 / 8 / 0
41. `src/components/schedule/DayColumn.tsx` — 29 / 9 / 1
42. `src/components/search/SearchDialog.tsx` — 21 / 15 / 3
43. `src/pages/ResetPassword.tsx` — 18 / 19 / 2
44. `src/pages/Settings.tsx` — 33 / 4 / 2
45. `src/components/events/EventEditDialog.tsx` — 16 / 12 / 10
46. `src/components/news/NewsDetailHero.tsx` — 32 / 4 / 2
47. `src/pages/ForgotPassword.tsx` — 28 / 8 / 2
48. `src/sw/api.ts` — 37 / 0 / 1
49. `src/components/schedule/ScheduleListView.tsx` — 22 / 12 / 2
50. `src/pages/settings/hooks/usePasswordChange.ts` — 30 / 6 / 0
51. `src/components/events/EventFileManager.tsx` — 31 / 4 / 0
52. `src/components/motion/PageFadeIn.tsx` — 27 / 6 / 2
53. `src/components/motion/ScrollReveal.tsx` — 28 / 6 / 1
54. `src/pages/Dashboard.tsx` — 19 / 14 / 2
55. `src/pages/settings/hooks/useEmailChange.ts` — 28 / 7 / 0
56. `src/AppProviders.tsx` — 31 / 1 / 2
57. `src/components/events/EventDetailBody.tsx` — 34 / 0 / 0
58. `src/features/admin/AdminAuditFeature.tsx` — 15 / 15 / 3
59. `src/utils/trustedTypes.ts` — 20 / 10 / 3
60. `src/components/mfa/StepUpDialog.tsx` — 19 / 12 / 0

For each: write user-facing Testing Library interactions (per the roadmap's Wave 3.3 instruction) covering the missing branches — these are overwhelmingly error/loading/empty/permission-denied/reconnect paths in hooks and dialogs, not dead code. `src/push/subscribe.ts` and `src/hooks/useChatWebSocket.ts` specifically need WebSocket reconnection and push-subscription-failure branch coverage (roadmap Wave 3.2's explicit "WebSocket reconnection" requirement). `src/sw/api.ts` needs PWA/service-worker branch coverage (Wave 3.2's "PWA/service worker" requirement).

### 3.2 — Long-tail cleanup (files 61–537)

477 files, aggregate 2,764 missing units (1,483 statements / 1,079 branches / 202 functions), each individually small (1–15 missing units). Do not itemize these; track as a single running backlog task with a burn-down chart in the Phase 10 dashboard. Suggested execution rule: whenever any of these files is touched for an unrelated feature/bugfix PR, its diff-coverage requirement (Phase 3.5 below) will force it toward 100% incidentally — supplement with a dedicated monthly "coverage debt" sweep of 10–15 files from this list until exhausted.

### 3.3 — Frontend mutation testing (currently absent entirely)

**Task 3.3.1** — Add `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` to `frontend/package.json` devDependencies.

**Task 3.3.2** — Author `frontend/stryker.config.mjs` scoped initially to pure utility modules with no DOM/React dependency: `src/utils/*.ts`, `src/i18n/formatters.ts`, validation schemas (Valibot-based files under `src/schemas/` if present, or equivalent), and pure reducers/state-machine hooks (`src/hooks/features/useMessengerController.ts`'s reducer logic if extractable).

**Task 3.3.3** — Add a `stryker-incremental` job to the fast PR gate (diff-scoped, same pattern as Python's `mutation-tests-incremental`) and a `stryker-full` job to `nightly-full-gate.yml`, both gated at the Phase 14 ratchet floor.

### 3.4 — Frontend property-based testing (currently absent entirely)

**Task 3.4.1** — Add `fast-check` to `frontend/package.json` devDependencies.

**Task 3.4.2** — Add property tests for: URL-state serialization/deserialization (`src/router.ts`'s search-param helpers), date/i18n formatters (`src/i18n/formatters.ts`), and any hand-rolled parsers (`src/utils/sanitize.ts`, `src/utils/sanitizeArticleHtml.ts` — round-trip and idempotency properties: sanitizing already-sanitized output must be a no-op, matching the existing `strip_html` idempotency fix referenced in git history).

### 3.5 — Frontend diff-coverage tooling (currently absent entirely)

**Task 3.5.1** — Add a `diff-cover frontend/coverage/lcov.info --compare-branch=origin/main --fail-under=<ratchet floor>` step to `reusable-frontend-tests.yml`, mirroring the Python setup in `reusable-backend-tests.yml`. `diff-cover` supports LCOV input natively, so no additional tooling is needed beyond the existing `uv`-managed Python environment (it is a Python package, already available via the backend's `uv` toolchain, callable from the frontend job with a `uv run` prefix or a dedicated `pip install diff-cover` step if frontend jobs don't have `uv` set up).

## Phase 4 — Go services coverage and hardening

Current measured state: `go-gateway` **92.56% statements**, `go-ws-hub` **91.70%**, `go-file-processor` **90.74%**. Contract floor: **99%**. CI's honest current floor: **90%** (explicitly documented in `ci.yml`'s matrix comments as "measured unit-only reality").

### 4.1 — Lowest-covered functions by service (target for new table-driven/fuzz tests)

**gateway** (`services/gateway`):

- `cmd/gateway/main.go:151 setupRouter` — 75.0%
- `cmd/gateway/main.go:128 initGRPC` — 80.0%
- `middleware/auth.go:766 Optional` — 80.9%
- `cmd/gateway/main.go:109 initSentry` / `cmd/gateway/main.go:349 initTracer` — 85.7% each
- `cmd/gateway/main.go:47 main` — 86.4%
- `middleware/ratelimit.go:42 NewRateLimiter` — 90.0%
- `middleware/auth.go:448 listenOnce` — 90.0%
- `middleware/auth.go:478 shouldRefreshProbabilistic` — 87.5%
- `middleware/auth.go:256 fetchJWKSPublicKey` — 91.7%
- `middleware/auth.go:540 verifySession` — 92.9%
- `middleware/auth.go:656 Validate` — 92.3%

**ws-hub** (`services/ws-hub`):

- `pkg/hub/hub.go:376 SubscribeToNATS` — **59.1%** (lowest in the entire Go codebase — prioritize first)
- `pkg/hub/client.go:233 WritePump` — 76.2%
- `pkg/hub/client.go:77 ReadPump` / `pkg/hub/client.go:135 handleIncomingMessage` — 83.3% each
- `pkg/hub/auth_client.go:75 NewInternalAPIAuthClient` — 83.3%
- `pkg/hub/hub.go:518 handleCacheInvalidation` — 83.9%
- `internal/telemetry/telemetry.go:36 InitTracer` — 81.8%
- `main.go:24 main` / `main.go:114 setupHub` — 84.6% each
- `pkg/hub/client.go:179 handleMessage` — 84.2%
- `pkg/hub/hub.go:309 broadcastMessage` — 88.5%
- `pkg/hub/handlers.go:293 tryForceRefreshJWKS` — 88.9%
- `main.go:136 setupHandlers` — 88.2%

**file-processor** (`services/file-processor`):

- `cmd/file-processor/main.go:255 startNatsSubscriber` — **44.4%** (lowest in the entire Go codebase — prioritize first)
- `internal/workflow/workflow.go:311 encodeImage` — 71.4%
- `internal/workflow/workflow.go:258 downloadAndDecodeImage` — 80.8%
- `cmd/file-processor/main.go:235 setupTemporalWorker` — 83.3%
- `cmd/file-processor/main.go:430 runServers` — 85.0%
- `cmd/file-processor/main.go:604 initTracer` — 85.7%
- `cmd/file-processor/main.go:78 runMain` — 88.2%

For the `main.go`/bootstrap-heavy functions (`setupRouter`, `initGRPC`, `startNatsSubscriber`, `setupTemporalWorker`), prefer **`go-integration-*` tests against real testcontainers** (they are already advisory-running against `testcontainers-go` per ADR-022) over unit mocks — this is genuinely hard-to-unit-test bootstrap wiring, and the roadmap's own integration-cell requirement fits this code better than forcing artificial unit coverage.

### 4.2 — goleak

**Task 4.2.1** — Add `go.uber.org/goleak` as a dependency to all three `services/*/go.mod`.

**Task 4.2.2** — Add a `TestMain(m *testing.M) { goleak.VerifyTestMain(m) }` to one `_test.go` file per package in each service (standard goleak entry-point pattern), starting with `services/ws-hub/pkg/hub` (the package with the most goroutine-heavy code: `SubscribeToNATS`, `ReadPump`/`WritePump`, `StartLimiterCleanup`) and `services/gateway/middleware` (JWKS refresher goroutine in `StartJWKSRefresher`/`listenOnce`).

### 4.3 — Fuzz coverage gaps

**Task 4.3.1** — Add `services/gateway/middleware/auth_fuzz_test.go`'s existing but never-executed `FuzzJWTValidation` to a CI step — either extend `.github/workflows/go-fuzz.yml` with a second job for gateway, or add it to `ci.yml`'s existing `go-fuzz` job as a third `go test -fuzz=` invocation alongside the two ws-hub fuzz targets.

### 4.4 — Integration tests: advisory → blocking

**Task 4.4.1** — Track `go-integration-ws-hub`, `go-integration-file-processor`, `go-integration-gateway` flake rate for 30 days (the criterion already documented in `ci.yml`'s `ci-success` comments). Once below 1%, move them from the "reported but not blocking" section of `ci-success` into the blocking `results[]` array and into the Phase G.1 ruleset required-checks list.

### 4.5 — Coverage ratchet

**Task 4.5.1** — Raise `coverage-threshold` in `ci.yml`'s Go test matrix from 90 to 95 once Phase 4.1's lowest-covered functions (SubscribeToNATS, startNatsSubscriber, and the `main.go` bootstrap functions) are addressed via 7.1's integration-test approach; raise to 99 once fully closed. See Phase 14 for the exact sequencing.

## Phase 5 — Rust, PyO3, and browser WASM

Current measured state: `rust-native` **88.53% lines (571/645), 80.0% functions (56/70)** — the only failing Rust component. `rust-pyo3-sanitizer` (99.37%/100%) and `rust-wasm-sanitizer` (100%/100%) already pass.

### 5.1 — `native/rust_ext/src/lib.rs` closure

This is the **only file** in the entire native Rust surface below target — 74 missing lines, 14 missing functions, all concentrated in one file.

**Task 5.1.1** — Run `cargo llvm-cov --html` locally on `native/rust_ext` to get the exact uncovered line ranges (the aggregate JSON used for this audit does not carry per-line detail; only per-file summaries were extracted). Cross-reference against the existing `proptest`/fuzz targets in `native/rust_ext/fuzz/fuzz_targets/` to identify which of the 14 uncovered functions are FFI error-mapping paths (per the roadmap's "FFI error mapping" requirement) versus pure-Rust internal logic, and prioritize FFI error paths first since those are the ones with an explicit roadmap callout.

### 5.2 — Track `rust-crypto` as a real contract component

Currently `frontend/rust-crypto` has tests (`tests/native.rs`, `tests/wasm.rs`) but is **absent from `quality/quality-contract.json`'s `components` map** and from `normalize_coverage_reports.py`'s `--rust-report` CLI options — meaning its coverage is never measured or gated at all, despite the roadmap's Wave 5 intro explicitly naming it alongside `rust_ext`, `pyo3-sanitizer`, and `wasm-sanitizer`.

**Task 5.2.1** — Add `rust-crypto` to `quality/quality-contract.json`'s `components` (coverage floors matching the other Rust components: 99 lines / 98 functions) and to `quality/coverage-manifest.schema.json`'s `componentName` enum.

**Task 5.2.2** — Add a `--rust-report rust-crypto=artifacts/coverage/rust/rust-crypto/llvm.json` invocation to the `coverage-policy-gate` job in `ci.yml`, and a corresponding `cargo llvm-cov` step in `rust-lint`/a new dedicated coverage job for `frontend/rust-crypto`.

### 5.3 — Fuzz coverage for the two crates currently without it

**Task 5.3.1** — Add `fuzz/fuzz_targets/` to `frontend/wasm-sanitizer` (currently only `native/rust_ext` and `crates/pyo3-sanitizer` have fuzz harnesses) targeting the sanitization entry points exposed to browser WASM bindings, with malformed-byte and boundary-size inputs per the roadmap's explicit Wave 5.3 wording.

**Task 5.3.2** — Add `fuzz/fuzz_targets/` to `frontend/rust-crypto` targeting HMAC/crypto primitive boundaries (empty input, maximum-length input, non-UTF8 byte sequences).

**Task 5.3.3** — Add both new fuzz targets to `.github/workflows/rust-fuzz.yml`'s job matrix.

### 5.4 — proptest for the two crates currently without it

**Task 5.4.1** — Add `proptest` as a dev-dependency to `frontend/wasm-sanitizer/Cargo.toml` and `frontend/rust-crypto/Cargo.toml` (currently only `native/rust_ext` and `crates/pyo3-sanitizer` use it), with properties covering round-trip encode/decode invariants and idempotency of sanitization.

### 5.5 — Miri (currently entirely absent from CI)

**Task 5.5.1** — Add a new `.github/workflows/rust-miri.yml` (or a job within `nightly-full-gate.yml`) running `cargo +nightly miri test` for `crates/pyo3-sanitizer` and `frontend/rust-crypto` (pure-Rust logic without heavy FFI/syscall dependencies — Miri cannot interpret PyO3's C-API calls or WASM host bindings, so scope it explicitly to the subset of each crate's test suite that exercises pure Rust logic, documented via a `#[cfg(not(miri))]` skip list for the FFI-heavy tests, matching the roadmap's own "Miri or sanitizer cells where platform support permits" qualifier).

## Phase 6 — Contracts, schemas, and compatibility

Current state: exactly one Pact contract exists (`tests/contracts/pacts/ws-hub-university-backend.json`, 1 interaction, consumer-side only via the `contract-tests` CI job's `-k "not integration"` pytest filter). No provider-side verification job exists.

**Task 6.1** — Add a `pact-provider-verify` CI job that runs the backend as the provider and replays the existing ws-hub consumer pact against it (using `pact-python`'s verifier, already compatible with the existing `PACT_DO_NOT_TRACK` env var setup in `contract-tests`).

**Task 6.2** — Author new consumer pacts for the two other cross-process boundaries currently covered only by hand-written schema-assertion tests (`tests/contracts/test_gateway_rest_contract.py`, `tests/contracts/test_file_processor_grpc_contract.py`) — convert or supplement these with real Pact consumer definitions so they participate in the same provider-verification replay mechanism as the ws-hub contract, per the roadmap's "consumer-driven provider verification and contract replay in both producer and consumer jobs" requirement.

**Task 6.3** — Add explicit backward/forward payload-migration tests for at least one enum that has evolved historically (search `alembic/versions/` for any migration that added an enum value) — a round-trip test asserting an old-shape persisted payload still deserializes correctly under the current schema.

## Phase 7 — Full browser matrix (advisory → blocking, dedicated stabilization budget)

Current state: `playwright.config.ts` declares `chromium`, `firefox`, `webkit`, `mobile-webkit` projects, but every CI workflow (`reusable-e2e-tests.yml`'s caller in `ci.yml`) only ever passes `browser: chromium`. The `ci.yml` comment explicitly states "Chromium-only by design."

**Task 7.1** — Add `firefox`, `webkit`, `mobile-webkit` as additional `browser` matrix values in `ci.yml`'s `e2e-tests` job, but land them first as a **separate, non-blocking job** (`e2e-tests-cross-browser`, `continue-on-error: true`, not in `ci-success`'s blocking array) so failures are visible without blocking merges during stabilization.

**Task 7.2** — Triage failures per browser. WebKit historically has known flakiness classes in this ecosystem (memory/OOM behavior under CI runners, timing differences in animation-heavy tests) — budget for: adjusting `testTimeout`/expect-timeout values per-browser via Playwright's `use: { ...devices[...] }` overrides, auditing the `reduced-motion` test helpers (already present in 19 test files) for WebKit-specific gaps, and re-running the existing `visual-regression.spec.ts`/`visual.spec.ts` baselines per-browser (Chromatic baselines are Chromium-only today; decide whether to extend Chromatic multi-browser or keep visual regression Chromium-only while functional E2E goes cross-browser).

**Task 7.3** — Once `e2e-tests-cross-browser` is green for 30 consecutive days across all three new browsers, split it into per-browser required jobs and add them to the Phase G.1 ruleset required-checks list, retiring the "Chromium-only by design" comment in `ci.yml`.

**Task 7.4** — Add Cache-Control header assertions to the SSR-focused E2E specs (`hydration.spec.ts` and/or a new `ssr-caching.spec.ts`) asserting the production preview server (`npm run build && npm run preview`, already the existing `webServer` config) emits expected cache headers for static assets vs. the SSR HTML shell — this specific gap (no header assertions anywhere in `tests/e2e/`) is independent of the browser-matrix work and can land immediately without waiting for Task 7.1–10.3.

## Phase 8 — Data, deployment, and infrastructure

**Task 8.1** — Checkov `soft_fail` removal: see Phase G.6 above (already scheduled there; cross-referenced here for Wave 8 traceability).

**Task 8.2** — Add a `kyverno-test` CI job. Kyverno ships a native `kyverno test` CLI subcommand for exactly this purpose (policy unit testing without a live cluster) — author `k8s/kyverno/tests/` with at least one positive and one negative test case per policy in `k8s/kyverno/cluster-policies.yaml`, and wire `kyverno test k8s/kyverno/tests/` into a new job in `ci.yml`.

**Task 8.3** — `load-and-chaos-tests` advisory → blocking: this job's blocker is the production Temporal container failing to boot reliably in CI (`W144`-class issue per the existing `ci-success` comment). Track root cause separately (likely a Temporal server config/entrypoint issue specific to the CI environment, not a test-quality issue) and move to `nightly-full-gate.yml` in the interim per Phase G.2, revisiting blocking-promotion once the Temporal boot issue has a documented fix. The obsolete dispatch-only CI definition was removed because it could only produce a skipped required status; remote ruleset context removal remains an auditable controller action, not a promotion.

## Phase 9 — Non-functional, security, and resilience

**Task 9.1** — Expand the abuse/negative-security test suite beyond the existing RLS/tenant-isolation coverage (`tests/integration/test_rls_matrix.py`, `test_rls_messages.py` — 10 tests total today) with explicit scenarios for: privilege escalation (attempt to elevate role via a manipulated JWT claim or a repository-layer bypass), replay-attack resistance (reused nonce/CSRF token, reused WebSocket ticket), and cache-poisoning (crafted cache key collision across tenants in `app/deps/cache.py` / `app/core/cache_versioning.py`, which are both already flagged as coverage-gap files in Phase 2.2 — combine the new negative-security tests with that closure work rather than treating them as separate effort).

**Task 9.2** — Add a documented, statistically-stable performance regression baseline for the native optimizer (`native/rust_ext`) and the WebSocket hub, using the existing `criterion` benchmark infra already present for `pyo3-sanitizer` (`Rust Criterion Benchmarks (pyo3-sanitizer)` job) as the template — extend it to `native/rust_ext` and formalize the currently-ungated `WS-Hub Go Benchmark Regression Gate` job's thresholds (verify it currently has real fail-under thresholds, not just report-and-continue).

## Phase 10 — Certification, dashboard, and maintenance

**Task 10.1** — Author `scripts/quality/generate_dashboard.py`: reads the history of `quality-manifest.json` artifacts (requires archiving them somewhere durable across runs — e.g., committing a rolling `artifacts/quality/history/<date>.json` snapshot via a scheduled bot commit, or using GitHub's artifact retention plus a small script that fetches the last N runs via `gh api`) and renders a static HTML/Markdown trend dashboard (coverage per component over time, mutation score over time, Tier0 status, open exclusions/quarantines with expiry countdown) — published as a GitHub Pages artifact or committed to `docs/testing/dashboard.md`.

**Task 10.2** — Author a certification record generator (`scripts/quality/generate_certification.py`) invoked on tagged releases (hook into `.github/workflows/release.yml`), producing a signed/hashed record containing: exact commit SHA, the full required-check matrix results, all coverage/mutation/contract report hashes, current exclusion/quarantine register contents, and known limitations — satisfying the roadmap's Wave 10.4 exit gate.

**Task 10.3** — Write a quarterly flaky-test-audit runbook (`docs/testing/flaky-test-audit-runbook.md`): process for reviewing `--run-quarantined` marked tests, checking quarantine expiry dates against `quality/quality-contract.json`'s `quarantines` register (currently empty — this becomes actionable once any quarantine is ever added), and a disaster-recovery exercise checklist (restore from a migration snapshot, verify Alembic downgrade/upgrade round-trip against a production-like dataset size).

## Phase 14 — Ratchet sequencing table

Raise contract floors only after the corresponding phase's backlog is materially closed, in this order, to avoid ever re-triggering the exact "Coverage & Quality Policy Gate fails on merge" failure mode this plan exists to fix:

| Step | Component                                    | Metric                   | From → To                                                                        | Gate condition to proceed                                                                                      |
| ---- | -------------------------------------------- | ------------------------ | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1    | `python`                                     | `tier0.*`                | n/a → 100% (measured)                                                            | Phase 0 (measurement) lands + Phase 2.1 (5 Tier0 files) closed                                                 |
| 2    | `python`                                     | lines                    | 95.54 → 97                                                                       | Phase 2.2 items 1–60 closed                                                                                    |
| 3    | `python`                                     | lines                    | 97 → 99                                                                          | Phase 2.2 items 61–116 + Phase 2.3 closed                                                                      |
| 4    | `python`                                     | branches                 | 85.92 → 92                                                                       | Phase 2.2 items 1–60 closed                                                                                    |
| 5    | `python`                                     | branches                 | 92 → 98                                                                          | Phase 2.2 items 61–116 + Phase 2.3 closed                                                                      |
| 6    | `go-*`                                       | statements               | 90 → 95                                                                          | Phase 4.1 lowest-covered functions addressed via integration tests                                             |
| 7    | `go-*`                                       | statements               | 95 → 99                                                                          | Phase 4.1 fully closed                                                                                         |
| 8    | `rust-native`                                | lines/functions          | 88.5/80 → 99/98                                                                  | Phase 5.1 (`lib.rs`) closed                                                                                    |
| 9    | `frontend`                                   | lines/branches/functions | 91/82/82 → 95/88/88                                                              | Phase 3.1 (top-60) closed                                                                                      |
| 10   | `frontend`                                   | lines/branches/functions | 95/88/88 → 99/98/98                                                              | Phase 3.2 (long tail) closed                                                                                   |
| 11   | `policy.patch_coverage` (backend)            | diff-cover               | 80 → 90 → 100                                                                    | Phase 2.2 items 1–60 closed, then fully closed                                                                 |
| 12   | `policy.patch_coverage` (frontend, new)      | diff-cover               | n/a → 80 → 100                                                                   | Phase 3.5 tooling lands, then Phase 3.1 closed                                                                 |
| 13   | `policy.viable_mutant_score` (Python)        | mutmut                   | 85% historical audit baseline → 100% viable score, fail-closed in exact PR shards and the full nightly universe | source wiring and local contract tests; terminal current-HEAD PR and nightly artifacts still required |
| 14   | `policy.viable_mutant_score` (frontend, new) | Stryker                  | n/a → 100 (scoped to pure utilities)                                             | Phase 3.3 lands                                                                                                |

Never skip a step or raise a floor before its gate condition — this table exists specifically to prevent a repeat of the PR #1207 failure mode where a contract floor was aspirational rather than earned.

## Phase 15 — Execution order

1. **Phase G** (governance) — must land before any other phase's "done" state can be trusted to stay merged.
2. **Phase 0** (Tier0 measurement, non-blocking sub-tasks only) — land measurement before enforcement.
3. **Phase 2.1** (Python Tier0 file closure) — small, high-priority, unblocks Phase 0's enforcement sub-task.
4. **Phase 0** (Tier0 enforcement sub-task) — now safe to make blocking.
5. **Phases 2–5** (Python, Frontend, Go, Rust) in any order convenient for working sessions — independent except where a ratchet-table gate condition specifies.
6. **Phases 6, 8, 9** (contracts, data/deployment, non-functional & security) — independent, can interleave with the above.
7. **Phase 7 (browser matrix)** — dedicated stabilization effort; budget calendar time for WebKit flake triage before promoting to blocking.
8. **Phase 10 (dashboard/certification)** — do this last; consumes stabilized trend data.
9. **Phase 14 ratchet steps** — applied incrementally throughout, gated exactly as specified in the table.
