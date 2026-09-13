# CI capacity and mutation bottleneck audit

Date: 2026-09-08 (Europe/Moscow)

This is a read-only, evidence-first audit of the current GitHub Actions
capacity configuration. It records the observed bottleneck without changing a
workflow, quality threshold, mutation inventory, or release semantics. The
listed runs are historical/non-green observations and are not release
evidence for the current local checkout.

## Scope and identity

- Branch under development: `egorribun`.
- Local checkout at audit time: `1c27845a314c24dae4dff33e4c3b8caad252a272`.
- Remote `origin/egorribun` at audit time: `ba42b3d8e093390e6d1e463906b3f311325d980a`.
- Current workflow source is `.github/workflows/ci.yml`; reusable frontend
  jobs are defined in `.github/workflows/reusable-frontend-tests.yml`.
- No workflow files were modified by this audit.

The workflow run records below belong to earlier pushed heads while the
branch was being repaired. They are useful for queue and barrier diagnosis
only. Their failures, skipped mutation legs, and stale source heads must not
be copied into a quality manifest.

## Static workflow contract

The current workflow preserves the complete inventory and fail-closed gates:

| Lane | Logical inventory | Physical fan-out | Current cap | Barrier |
|---|---:|---:|---:|---|
| Frontend Stryker | 64 shards / complete preflight universe | 64 jobs | `max-parallel: 6`, `STRYKER_CONCURRENCY=4` | `stryker-preflight` and successful `coverage-policy-gate` |
| Python mutmut stats | all changed-Python stats shards | dynamic matrix | `max-parallel: 8` | pre-commit, backend/type readiness and coverage gate |
| Python mutmut execution | 128 logical assignments | at most 64 validated physical groups | `max-parallel: 10` | pre-commit, stats/universe readiness and coverage gate |

The mutation producer caps are therefore `6 + 10 = 16` hosted jobs, with
four slots intentionally reserved for required diagnostics and aggregators.
The matrix builder still validates the complete 128-assignment plan and the
64-way Stryker list; there is no inventory reduction, exclusion, quarantine,
or `continue-on-error` path. The workflow-level concurrency group remains
`ci-matrix-${{ github.ref }}` with `cancel-in-progress: true`.

`stryker-preflight` currently needs only `pre-commit-check`, so its static DAG
does not wait for the reusable frontend Lighthouse aggregate. Stryker shards,
mutmut stats, and mutmut execution still require `coverage-policy-gate`.
`coverage-policy-gate` waits for `backend-tests`, `frontend-tests`, `go-tests`,
and `rust-tests`, and is the single owner of the merged SHA-bound coverage
manifest. This conservative barrier prevents expensive mutation fan-out when
any foundational coverage producer is red.

## Live timing observations

The measurements were produced with the repository's read-only analyzer:

```text
uv run python scripts/quality/analyze_ci_critical_path.py \
  --repository egorribun/university_ecosystem \
  --run-id <run> --concurrency-cap 20 --diagnostic-lower-bound \
  --output <temporary-file>
```

The Jobs API does not expose the workflow `needs` graph for every nested
reusable-workflow leg. Consequently, `critical_path_lower_bound_seconds` is the
analyzer's dependency-free lower bound for the returned job records (strict
exact analysis requires an attempt-bound `--dag-json` sidecar), while
`wall_clock_seconds`, queue waits, and observed peak are direct timing observations.

| Run | Source head | Result | Job records | Wall clock | Lower bound | Observed peak | Average utilization | Max queue wait |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| `34169372392` | `ba42b3d8` | failure | 117 | 1,601 s (26m41s) | 973 s | 20 | 0.573048 | 676 s |
| `34189435982` | `ff0a3d0a` | failure | 113 | 2,070 s (34m30s) | 947 s | 19 | 0.441618 | 698 s |
| `34191511980` | `1005b058` | failure | 113 | 6,988 s (1h56m28s) | 943 s | 9 | 0.134237 | 3,370 s |
| `34194122647` | `6e330e5c` | failure | 113 | 6,171 s (1h42m51s) | 909 s | 8 | 0.150097 | 3,941 s |

The long queue waits in the last two runs are dominated by Schemathesis and
other required jobs, not by a running mutation matrix. They demonstrate
runner starvation/availability variability but are not comparable green
capacity benchmarks.

For run `34169372392` (`ba42b3d8`), the relevant event times were:

- Frontend unit aggregate: `23:28:01–23:29:49Z`.
- Frontend Lighthouse aggregate: `23:30:43–23:30:56Z`.
- Stryker preflight: `23:30:58–23:31:48Z`.
- Longest backend unit shard: ended at `23:37:03Z`.
- Coverage policy gate: `23:37:06–23:38:29Z`, failed because all four
  frontend coverage metrics were below the 100% floor.
- All Stryker shard and mutmut execution legs were skipped as a consequence
  of the failed coverage gate.

This run confirms that the existing preflight declaration does not serialize
on Lighthouse. It also confirms why removing the coverage barrier blindly is
unsafe: a red frontend coverage contract would otherwise allocate the full
mutation matrix and produce no release-valid evidence.

## Optimization decision

No safe workflow rewrite is justified by the current evidence.

The plan's proposed `frontend-coverage-ready` context cannot be added as a
small caller-level dependency today. `frontend-tests` invokes a reusable
workflow whose caller job completes only after unit coverage, build, bundle,
and Lighthouse jobs. Exposing the nested unit aggregate early would require
splitting the reusable workflow (or duplicating its unit/coverage work) and a
new signed artifact protocol. A speculative split could duplicate tests,
alter artifact provenance, or start mutation on partial coverage, so it is
explicitly deferred.

Likewise, changing `max-parallel`, inner Stryker concurrency, or mutmut
physical grouping is not accepted from these failed/non-comparable runs. The
full 64/128 inventory and all release-blocking thresholds remain unchanged.

## Required next measurement cycle

After the frontend coverage and mutation defects are green on one source SHA:

1. Produce three consecutive comparable green `CI - Matrix Expansion` runs.
2. For each run, retain the exact source/tested merge SHA, workflow run and
   attempt, job IDs, queue/dependency/setup/test/artifact durations, p95 shard
   duration, timeout/error rate, CPU/RSS and billed runner minutes.
3. Compare only measured candidates (`STRYKER_CONCURRENCY=2/4`, lane budgets
   `8/8`, `9/7`, `7/9`, and validated mutmut physical groups) while keeping
   64 Stryker shards, 128 mutmut logical assignments, empty exclusion lists,
   and fail-closed aggregators.
4. Accept a capacity change only when all three runs reduce the critical path
   without starvation, timeout, reliability, provenance, coverage, mutation,
   or security regression.

Until that evidence exists, the current 6/10 mutation caps and coverage phase
barrier are the measured safe configuration. This note intentionally records
an `OPEN-PERF/EVIDENCE-BLOCKED` condition rather than claiming a speedup.

## Addendum: current active matrix (2026-09-13)

The next source SHA, `d8518043898cc6a39c295a37dadca230e06baf57`, is running as
workflow `CI - Matrix Expansion` run `34743194178` (attempt 1). This is a live
diagnostic observation, not release evidence. The Jobs API currently reports
310 jobs: 219 completed, 16 in progress, and 75 queued, with one completed
cancellation. The active mutation
fan-out is 10 Python execution groups plus 6 frontend Stryker shards, which
matches the documented 16-job mutation budget and leaves four hosted slots for
other required work.

The only completed failures in this run are the two mutmut groups below:

- group 29: `app.cli.migrate_passwords.x__report_bcrypt_users__mutmut_15`,
  which removes the deterministic `order_by(User.id)` clause;
- group 41: `app.workers.cdc_outbox.xǁCdcOutboxWorkerǁdispatch_insert_record__mutmut_25`,
  which changes the warning template and is observable through the structured
  logging contract.

Exact-evidence artifacts show 8 killed and 1 survived mutant in each group.
Both survivors are stale-test-snapshot failures: the local RED-to-GREEN fixes
now assert the deterministic query ordering and the exact warning template and
arguments in `tests/test_cli_migrate_passwords_closure.py` and
`tests/test_cdc_outbox_closure.py`. The current run cannot see those
post-source assertions, so it must not be re-used as a mutation or release
result. The focused fixes are now committed locally in `8f3c699c4`; after this
run reaches a terminal state, push the commits, run the two affected shards on
the resulting SHA, and only then start the three-green-run capacity measurement
cycle above.

No workflow caps, inventory, exclusions, retry policy, or quality thresholds
were changed by this addendum. The `OPEN-PERF/EVIDENCE-BLOCKED` status remains
in force until three comparable green runs provide queue, dependency, setup,
test, artifact, CPU/RSS, reliability, and billed-minute evidence.

The same run also provides a concrete timeout signal: job `103690583926`
(`Frontend mutation shard 24/64`) was cancelled at the 120-minute job timeout
while its `Run fresh Stryker shard` step had consumed approximately 119.5
minutes. The follow-up evidence upload failed because the report did not
exist, and logs are unavailable until the workflow is terminal. This is a
real cancellation, not a reason to raise the timeout or relax the mutation
gate. The preflight plan assigned 801 mutants to shard 24, while shard 19
completed 247 mutants in approximately 91.6 minutes; the comparison shows
that mutant count alone is not a safe duration predictor. The next tuning
experiment is therefore bounded, cost-aware first-attempt rebalancing that
preserves the 64-shard denominator, hotspot isolation, full inventory, and
fail-closed evidence checks.
