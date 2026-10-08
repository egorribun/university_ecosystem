# ADR-047: Risk-Based Quality Policy for the MVP Release

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
   the current floors stay in force; coverage is not the current release
   blocker.
3. **Mutation testing leaves the release gate.** `ci-success` stops depending
   on mutation jobs. Full mutmut and Stryker runs continue in
   `nightly-full-gate.yml` and `manual-mutation-evidence.yml`. Their scores are
   published to the quality dashboard and checked for regression: a drop of more
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
   [the MVP release plan](../superpowers/plans/MVP_RELEASE_PLAN.md).

This decision supersedes, for the MVP release, the rule "do not weaken the
quality contract" and the "100 % viable mutation score" release criterion in
[the former master plan](../superpowers/plans/MVP_MASTER_PLAN.md), the mutation
part of section 4 of `AGENTS.md`, and the release-gate role of the aggregate
Stryker threshold described in ADR-040. ADR-040's presentation ignorer itself
stays.

## Implementation stages

Each stage is one reviewable change set with its own contract tests; a stage
is done only when the touched contract tests and the pull-request lane pass.

| Stage | Change | Files |
| --- | --- | --- |
| Q1 | Remove the nine mutation jobs from `ci-success` (needs and results array) and from the release rationale; keep them in nightly and manual workflows; update the CI check catalog | `.github/workflows/ci.yml`, `quality/ci-check-catalog.json`, `quality/release-required-checks.json`, `tests/test_quality_workflow_contract.py`, `tests/test_workflow_fail_closed_contracts.py`, `tests/test_ci_check_catalog.py`, `tests/test_frontend_ci_performance_contracts.py` |
| Q2 | Nightly mutation regression check against the previous complete run; publish scores to the dashboard | `scripts/check_mutation_score.py`, `frontend/stryker.config.mjs`, `scripts/quality/generate_dashboard.py`, `.github/workflows/nightly-full-gate.yml` |
| Q3 | Coverage ratchet and 90 % non-Tier 0 patch coverage | `quality/quality-contract.json`, `quality/coverage-manifest.schema.json`, `scripts/quality/validate_quality_contract.py`, `codecov.yml`, `tests/test_quality_contract.py`, `tests/test_quality_configuration.py` |
| Q4 | Pull-request time budget and scanner de-duplication | `.github/workflows/ci.yml`, `.github/workflows/trufflehog.yml`, `.github/workflows/sonar.yml`, `quality/release-required-checks.json`, related contract tests |

## Consequences

- The MVP can be released once product acceptance passes; mutation debt
  becomes tracked, visible work instead of a release blocker.
- Test effort concentrates on Tier 0 and on behaviour; new tests are not
  written only to kill presentation or equivalent mutants.
- Regressions in non-Tier 0 code are caught by the coverage ratchet, the patch
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
