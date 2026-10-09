# ADR-047: Risk-Based Quality Policy for the MVP Release

<!-- cspell:ignore mutmut -->

## Status

Accepted — owner decision of 2026-10-08. Implementation is staged (see
"Implementation stages"); until a stage lands, the machine-enforced contract it
changes stays in force exactly as it is today.

## Date

2026-10-08

## Context

The quality contract requires 100 % line, statement, branch and function
coverage for every measured component and a 100 % viable mutation score for
mutmut (backend) and Stryker (frontend). The requirement is enforced in several
places at once:

- `quality/quality-contract.json` (`policy.patch_coverage`,
  `policy.viable_mutant_score`, `coverage_minimums`, `components`);
- `scripts/quality/validate_quality_contract.py`, which rejects any policy value
  other than 100 and any measured component floor below 100;
- `codecov.yml` (project and patch targets of 100 %);
- `frontend/stryker.config.mjs` (`break: 100` for the aggregate run) and
  `scripts/check_mutation_score.py`;
- the `ci-success` aggregate in `.github/workflows/ci.yml`, which needs nine
  mutation jobs (`mutation-tests-stats`, `mutation-tests-universe-base`,
  `mutation-tests-universe`, `mutation-tests-incremental`, `mutation-scope`,
  `stryker-preflight`, `stryker-aggregate`, `stryker-evidence-roundtrip`,
  `frontend-mutation-required-context`);
- contract tests that pin each of the above.

Observed on 2026-10-08 (see `docs/superpowers/plans/STATUS.md`):

- the latest complete frontend inventory (43,200 mutants) scored 88.7 %
  (37,221 killed, 4,672 survived); ADR-040 already estimated about 1,500
  presentation survivors in half of the universe;
- full backend runs (about 54,450 mutants, 128 shards) were cancelled at the
  60-minute planning ceiling or failed before a global score existed;
- no certified quality snapshot has ever been published
  (`docs/testing/dashboard.md`);
- in the 30 days before this decision the branch received 1,111 commits, of
  which 16 were `feat` commits; the remaining effort went to quality, CI and
  evidence work, and the MVP release is blocked on these gates.

A uniform 100 % mutation score cannot be reached by writing tests alone:
equivalent mutants cannot be killed, and killing presentation mutants pins
styling rather than behaviour (ADR-040). The cost grows with the code base, so
the gate competes directly with product work.

## Decision

1. **Tier 0 keeps 100 %.** Files matched by `tier0_rules` in
   `quality/ownership-mapping.json` (authentication, sessions, MFA, security,
   rate limiting, PII, cryptography, ReBAC, CSRF, migrations, native and WASM
   crates) keep 100 % line, statement, branch and function coverage. The rule
   list is unchanged by this ADR.
2. **Non-Tier 0 coverage becomes a ratchet.** Each component floor equals the
   value measured on the last certified `main` run, rounded down to one decimal,
   and may never decrease. Changed non-Tier 0 lines in a pull request need at
   least 90 % patch coverage. Until the first certified `main` baseline exists,
   the current floors stay in force and remain blocking in CI. Owner clarification
   on 2026-10-08 keeps these gates until Q3; if they block MVP, bringing Q3 forward
   requires a separate decision. Tier 0 is never relaxed.
3. **Mutation testing leaves the release gate.** `ci-success` stops depending
   on mutation jobs. Full mutmut and Stryker runs continue in
   `nightly-full-gate.yml` and `manual-mutation-evidence.yml`. After Q2 lands,
   their scores are published to the quality dashboard and checked for regression: a drop of more
   than one percentage point against the previous complete run fails the nightly
   job and opens follow-up work, but does not block a release. The working
   target is 80 % for domain logic and 100 % for Tier 0 files.
4. **Equivalent mutants are recorded, not chased.** A mutant proven equivalent
   may be listed in `quality/mutation-exclusions.json` with owner, reason,
   evidence and an expiry date at most 90 days ahead. Quarantine and manual
   reclassification as `Killed` remain forbidden.
5. **Pull-request CI gets a time budget.** The blocking pull-request lane
   (lint, types, unit, contract, OpenAPI and GraphQL drift, Tier 0 coverage)
   targets 15 minutes of wall-clock time. Mutation, Schemathesis, DAST, chaos,
   cross-browser end-to-end and kind runs move to scheduled or manual lanes.
   Duplicate scanners are reduced to one tool per concern in the blocking
   lane: Gitleaks for secrets (TruffleHog moves to the weekly schedule) and
   CodeQL for static analysis (Semgrep and Bandit stay in pre-commit, Sonar
   becomes advisory).
6. **Release certification is split from the MVP.** The `v1.0.0` definition of
   done is product acceptance; items that certify production delivery move to
   `v1.1`. The split is recorded in
   [the consolidated MVP master plan](../superpowers/plans/MVP_MASTER_PLAN.md).

This decision supersedes, for the MVP release, the rule "do not weaken the
quality contract" and the "100 % viable mutation score" release criterion in
[the previous master-plan revision](../superpowers/plans/MVP_MASTER_PLAN.md), the mutation
part of section 4 of `AGENTS.md`, and the release-gate role of the aggregate
Stryker threshold described in ADR-040. ADR-040's presentation ignorer itself
stays.

## Implementation stages

Each stage is one reviewable change set with its own contract tests; a stage
is done only when the touched contract tests and the pull-request lane pass.

| Stage | Change | Files |
| --- | --- | --- |
| Q1 | Remove the entire mutation execution graph from PR/main-push CI, including Stryker shards; remove mutation needs, results, event assertions and blocking summaries from `ci-success` and the release rationale; retain full nightly/manual evidence and update the check catalog | `.github/workflows/ci.yml`, `quality/ci-check-catalog.json`, `quality/release-required-checks.json`, `tests/test_quality_workflow_contract.py`, `tests/test_workflow_fail_closed_contracts.py`, `tests/test_ci_check_catalog.py`, `tests/test_frontend_ci_performance_contracts.py` |
| Q2 | Nightly mutation regression check against the previous complete run; publish scores to the dashboard | `scripts/check_mutation_score.py`, `frontend/stryker.config.mjs`, `scripts/quality/generate_dashboard.py`, `.github/workflows/nightly-full-gate.yml` |
| Q3 | Coverage ratchet and 90 % non-Tier 0 patch coverage | `quality/quality-contract.json`, `quality/coverage-manifest.schema.json`, `scripts/quality/validate_quality_contract.py`, `codecov.yml`, `tests/test_quality_contract.py`, `tests/test_quality_configuration.py` |
| Q4 | Move Schemathesis, DAST, chaos, cross-browser E2E and kind to scheduled/manual lanes; preserve Chromium PR smoke; implement the PR time budget and scanner de-duplication | `.github/workflows/ci.yml`, affected scheduled/manual workflows, `.github/workflows/trufflehog.yml`, `.github/workflows/sonar.yml`, `quality/ci-check-catalog.json`, `quality/release-required-checks.json`, related contract tests |

Owner clarification on 2026-10-08 makes Q1 and Q4 mandatory before `v1.0.0`.
Q4 includes the scheduled/manual migration of Schemathesis, DAST, chaos,
cross-browser E2E and kind, with synchronized triggers, dependencies, check
catalog, release requirements and tests. Preserve PR live Chromium smoke,
Tier 0 and the currently enforced coverage floors. Q2 and Q3 stay in `v1.1`.
Existing six-image publication, signing, SBOM and provenance machinery remains
part of the MVP release; comprehensive published-image acceptance in kind is
deferred. Already started work ends at the bounded checkpoints in the master
plan, rather than restoring the previous certification gate.

On 2026-10-09 the owner also confirmed moving the full four-shard Chromium
suite and Lighthouse to scheduled/manual execution while retaining live
Chromium PR smoke. Preserve their full scenarios and assertions. The owner
authorized removing only the 14 existing Q1/Q4 contexts listed
[below](#authorized-required-context-removals) from main ruleset `8335285`,
after the corresponding workflow diff is complete, reviewed and checked.
In a subsequent explicit approval on the same date, the owner authorized
removing exactly one additional context, `Security Audit / Semgrep SAST`, after
the reviewed scanner de-duplication change passes its checks. CodeQL stays
blocking and Semgrep stays in pre-commit. The expected count is 91 to 76;
all other protection rules and contexts remain unchanged. This is not bypass
permission. The migration and the 15-minute budget are not yet implemented or
verified by that authorization.

### Authorized required-context removals

The exact scope of the 2026-10-09 authorization for ruleset `8335285` is:

| Stage | Exact context |
| --- | --- |
| Q1 | `Incremental Mutation Tests (frontend)` |
| Q4 | `E2E Tests (shard 1/4) / E2E Tests (chromium)` |
| Q4 | `E2E Tests (shard 2/4) / E2E Tests (chromium)` |
| Q4 | `E2E Tests (shard 3/4) / E2E Tests (chromium)` |
| Q4 | `E2E Tests (shard 4/4) / E2E Tests (chromium)` |
| Q4 | `Frontend Tests / Lighthouse Audit` |
| Q4 | `Frontend Tests / Lighthouse Audit (content)` |
| Q4 | `Frontend Tests / Lighthouse Audit (core)` |
| Q4 | `Frontend Tests / Lighthouse Audit (fallback)` |
| Q4 | `Frontend Tests / Lighthouse Audit (realtime)` |
| Q4 | `Schemathesis - API Schema Conformance` |
| Q4 | `Chaos Loadtest Orchestrator` |
| Q4 | `SQLMap Scan` |
| Q4 | `TruffleHog Scan` |

The subsequent approval adds only `Security Audit / Semgrep SAST` to this list.
This records the approved boundary, not a fresh ruleset readback or permission
to remove other contexts. Preserve every other rule, blocking CodeQL, coverage,
Gitleaks, migration and supply-chain gates. Do not emit compatibility checks
that report success in place of the removed protection. Current execution and
ruleset evidence belong in [STATUS](../superpowers/plans/STATUS.md).

Q4 includes SQLMap and TruffleHog trigger/catalog/required-profile migration.
DAST is already weekly/manual and Sonar is already advisory; preserve those
paths. No kind PR/main job currently exists, so verify that absence rather than
creating a new lane. The Q4 scanner de-duplication removes the hosted Semgrep
job from the reusable security audit, retains blocking CodeQL, and keeps the
Docker-backed Semgrep pre-commit hook mandatory locally and skipped in CI.
Hosted evidence is still required for the updated source. The 15-minute budget
is measured as critical-path wall time; a miss leaves the budget criterion open.

## Consequences

- The MVP can be released once product acceptance passes; mutation debt
  becomes tracked, visible work instead of a release blocker.
- Test effort concentrates on Tier 0 and on behaviour; new tests are not
  written only to kill presentation or equivalent mutants.
- After Q2/Q3, regressions in non-Tier 0 code are caught by the coverage ratchet, the patch
  floor and the nightly mutation regression check rather than by a uniform
  100 % gate. A real regression can therefore reach `main` before the nightly
  run reports it; Tier 0 keeps the strict gate for that reason.
- Some contract tests that pin the old policy are rewritten in stages Q1–Q4;
  each rewrite must keep the fail-closed behaviour of the checks that remain.

## Alternatives considered

- **Keep 100 % everywhere.** Rejected: the gate has not been met on any
  complete inventory and blocks the release indefinitely.
- **Lower every threshold to a single number (for example 80 %).** Rejected:
  it weakens authentication and cryptography code as much as presentation code.
- **Remove mutation testing.** Rejected: nightly mutation runs still find weak
  tests in domain logic and are cheap to keep outside the blocking lane.
