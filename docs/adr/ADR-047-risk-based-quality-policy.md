# ADR-047: Risk-Based Quality Policy for the MVP Release

<!-- cspell:ignore mutmut -->

## Status

Accepted — owner decision of 2026-10-08. Implementation is staged (see
"Implementation stages"); until a stage lands, the machine-enforced contract it
changes stays in force exactly as it is today.

## Date

2026-10-08

## Context

At the time this ADR was adopted, the quality contract required 100 % line, statement, branch and function
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

1. **Tier 0 keeps 100 %, subject only to the finite migration decision below.**
   Files matched by tier0_rules in quality/ownership-mapping.json (authentication,
   sessions, MFA, security, rate limiting, PII, cryptography, ReBAC, CSRF,
   migrations, native and WASM crates) keep 100 % line, statement, branch and
   function coverage. The sole exception is the exact source-bound baseline
   approved on 2026-10-14 for 131 unchanged legacy migration files, through
   2026-11-13. New, modified or unmatched migrations and every other Tier 0 file
   remain at 100 % for all metrics; see the later owner decision below.
2. **Non-Tier 0 coverage becomes a ratchet.** Each component floor equals the
   value measured on the last certified `main` run, rounded down to one decimal,
   and may never decrease. Changed non-Tier 0 lines in a pull request need at
   least 90 % patch coverage. Until the first certified `main` baseline exists,
   the current floors stay in force and remain blocking in CI. Owner clarification
   on 2026-10-08 keeps these gates until Q3; if they block MVP, bringing Q3 forward
   requires a separate decision. Other Tier 0 files remain strict; the only finite
   migration exception is the source-bound 131-file baseline described below.
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

On 2026-10-12 the owner approved a further, separately recorded ruleset change:
the two compatibility contexts `Backend Tests (Python 3.14) / Unit Tests (All-Python 3.14)`
and `Backend Tests (Python 3.14) / Integration Tests (All-Python 3.14)` were removed
because they reported skipped (green) when backend tests failed; `CI Success`
keeps aggregating the real backend jobs. The same change added
`Security Policy Integrity`, `Vulnerability gate (CRITICAL/HIGH)`,
`Cargo Deny Scan` and `Zizmor Actions Scan` as required contexts and a CodeQL
`code_scanning` rule (security alerts high or higher). The push-only gate is
named `Vulnerability gate (CRITICAL/HIGH, main)` so its skipped pull-request
instance cannot satisfy the required pull-request context.

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

## Owner-approved exact detect-secrets dispositions (2026-10-12 UTC)

On 2026-10-12 UTC, the owner approved exact-match dispositions for 85 reviewed
identities: 83 verified public or synthetic findings and two linked account
fixtures limited to the internal synthetic demo. The external status of those
linked fixtures remains unverified; this approval does not authorize their use
outside that demo.

A separate owner decision on 2026-10-12 UTC approves exactly one additional
identity: the public NATS image digest detected at
tests/test_workflow_fail_closed_contracts.py:43 as a Hex High Entropy String
(category public_integrity_digest). This is the sole 86th identity in the
approved set; it does not amend or broaden the original 85-identity approval.
The added record retains reviewed_on 2026-10-12 and expires_on 2027-01-10.
No other finding, baseline entry, inline pragma, scanner exclusion, or policy
change is covered.

Each record is scoped to an exact repository path, detector type and finding
digest, and carries owner and evidence metadata with `reviewed_on` 2026-10-12
and `expires_on` 2027-01-10 (90 days). No wildcard, category-wide permission, or
future finding is covered. An unmatched or changed identity remains fail-closed
and requires a separate owner decision. This approval authorizes no new
`.secrets.baseline` entries, inline pragmas, or broad scanner exclusions.

The existing baseline identity set remains at 319 and the 78 required contexts
remain unchanged. This decision authorizes no bypass or further context change.
It records policy scope only; implementation, test results, hosted checks and
release readiness are separate. Revalidate the final source SHA and record the
evidence in [STATUS](../superpowers/plans/STATUS.md) before making a release
claim.

## Owner-approved additional exact detect-secrets dispositions (2026-10-13 UTC)

On 2026-10-13 UTC, the owner approved exactly 27 additional exact-match
disposition identities from the reviewed proposal: 12 public integrity digests
and 15 independent contract fingerprints. Each new record is limited to its
exact repository path, detector type and finding digest. The records retain
per-identity owner and evidence metadata, with reviewed_on 2026-10-13 and
expires_on 2027-01-10. No wildcard, category-wide permission, or future
finding is covered; changed or unmatched identities remain fail-closed.

Together with the 86 identities approved on 2026-10-12, these additions
brought the approved scope to exactly 113 records before the separate Caddy
and four-identity decisions recorded below. The two linked account fixtures from the
earlier approval remain limited to the internal synthetic demo; their external
status remains unverified. The baseline remains at 319 identities and the 78
required contexts remain unchanged. This decision authorizes no new
.secrets.baseline entries, inline pragmas, scanner exclusions, bypass, or
context changes. It records the owner's policy decision only. Integration,
final-source recheck, tests and hosted checks are pending and must be reported
separately; no release readiness is implied.

## Separate Caddy approval and four additional owner-approved identities

The owner approved exactly one Caddy image-digest disposition in a separate
decision, extending the approved scope from 113 to 114. Implementation is
tracked in [MVP STATUS](../superpowers/plans/STATUS.md). This decision is
separate from the 27 identities approved above.

On 2026-10-13 UTC, the owner approved exactly four additional exact-match
disposition identities: two synthetic fake Redis `Secret Keyword` findings in
`tests/test_chat_command_failure_paths.py`, one public NATS image digest, and
one public imgproxy image digest in `tests/test_docker_startup_contracts.py`.
Each record is restricted to its exact repository path, detector type and
finding digest, with `reviewed_on` 2026-10-13 and `expires_on` 2027-01-10.
Changed or unmatched identities remain fail-closed. The Go builder digest
observed in the same test file already matches an existing disposition and is
not a fifth addition.

The approved scope is 118 exact identities: the prior 113, the separately
approved Caddy identity, and these four new approvals. The linked account
fixtures from the earlier approval remain limited to the internal synthetic
demo; their external status remains unverified. The baseline remains at 319
identities and the 78 required contexts remain unchanged. This approval
authorizes no new `.secrets.baseline` entries, inline pragmas, scanner
exclusions, bypass, or context changes. It records the owner's policy decision
only. Policy integration, final-source recheck, tests and hosted checks remain
separate and must be reported separately; no release readiness is implied.

## Owner-approved exact 17 detect-secrets dispositions (2026-10-14 UTC)

On 2026-10-14 UTC, the owner approved exactly 17 additional exact-match
disposition identities. They are the exact repository-path, detector-type, and
finding-digest tuples recorded in quality/security-false-positive-dispositions.json:
15 public_integrity_digest / Hex High Entropy String findings in
quality/quality-contract.json and two in
scripts/quality/validate_quality_contract.py. Each new record has reviewed_on
2026-10-14 and expires_on 2027-01-10. No raw finding digests are duplicated in
this prose; the policy records remain the identity source.

The previous 118 records remain unchanged. This decision extends the approved
scope to exactly 135 identities; it authorizes no other finding, wildcard,
category-wide permission, baseline entry, inline pragma, broad scanner
exclusion, bypass, or context change. Changed or unmatched identities remain
fail-closed. The baseline remains at 319 identities, all 78 required contexts
remain unchanged, CodeQL remains blocking, and hooks are unchanged. Approval
does not itself change the policy file or certify a source SHA; integration,
tests, hosted checks, and final-source validation remain separate.

## Owner-approved exact 90 detect-secrets dispositions (2026-10-15 UTC)

On 2026-10-15 UTC, the owner approved exactly 90 additional exact-match
disposition identities, extending the historically approved 135 to exactly 225.
They are the exact repository-path, detector-type, and finding-digest tuples in
quality/security-false-positive-dispositions.json: 54 public_integrity_digest,
27 independent_contract_fingerprint, and 9 external_kubernetes_secret_reference
identities. Each new record has reviewed_on 2026-10-15 and expires_on 2027-01-10.
The previous 135 records remain unchanged; no raw finding digests are duplicated
here. The public-integrity category retains its existing behavior.
`independent_contract_fingerprint` extends the existing v3 category only for these
finite v4 identities; its prior v3 behavior remains unchanged.
`external_kubernetes_secret_reference` is the sole new category and requires exact
identity matching plus reviewed semantic evidence. No cross-category reclassification
is authorized.
This decision does not reclassify existing findings across categories. Changed or
unmatched identities remain fail-closed.

The approval covers only these 90 identities. It authorizes no additional finding,
wildcard, baseline entry, inline pragma, broad scanner exclusion, bypass, or
context change. The baseline remains at 319 identities, all 78 required contexts
remain unchanged, CodeQL remains blocking, and hooks are unchanged. Validator
integration, final-source scan, tests, and hosted checks remain separate; no
release readiness is implied.

## Owner-approved finite legacy migration baseline (2026-10-14 UTC)

On 2026-10-14 UTC, the owner approved a finite no-decrease baseline for exactly
131 unchanged Alembic migration files under alembic/versions, source-bound to
base commit ac74e915 and expiring 2026-11-13.
The per-file native or derived metrics, source identity, and provenance remain
in the quality contract and its bound evidence; this is not an aggregate-only
exemption. The baseline applies only while each listed source file is
unchanged. New, modified, or unmatched migrations, including PR-touched files,
remain subject to 100 % lines, statements, branches, and functions. All other
Tier 0 files, current per-component floors, the 100 % patch floor, and the
blocking validator remain unchanged. Q3 and its coverage ratchet remain v1.1;
this approval does not advance Q3. Policy integration and final-source
verification are separate from the owner decision.

## Owner-approved exact 18 detect-secrets dispositions (2026-10-16 Europe/Istanbul; 2026-10-15 UTC)

On 2026-10-16 Europe/Istanbul (2026-10-15 UTC), the owner approved exactly 18
additional exact-match disposition identities, extending the historically
approved 225 to exactly 243. The approval covers only the exact path, detector
type, and finding-digest tuples recorded in
`quality/security-false-positive-dispositions.json` by this owner-reviewed update.
Raw digests and private paths are not duplicated here. The 18 identities comprise 9
in the existing `external_kubernetes_secret_reference` category; 3 in the
existing `ci_test_contract_sentinel` category across two new finite path/type
pairs; and 6 in the new `source_contract_identifier` category across five finite
path/type pairs and requiring both fixed semantic evidence markers.

Every new identity requires its own exact per-record digest match. The new
category is not a wildcard or category-wide approval; no identity is approved
automatically. Each record has `reviewed_on` 2026-10-15 and `expires_on`
2027-01-10 and remains subject to the existing approval-status and expiry
validation. The previous 225 records remain unchanged. Changed or unmatched
identities remain fail-closed.

This decision authorizes only these 18 identities. It grants no cross-category
reclassification, baseline entry, inline pragma, broad scanner exclusion,
bypass, expiry bypass, other identity, or context change. The finite 131-file
migration baseline is untouched. The baseline remains at 319 identities, all
78 required contexts remain unchanged, CodeQL remains blocking, and hooks are
unchanged. Authorization does not establish integration, validator test,
final-source scan, or hosted-check results; each requires independent evidence.
No release readiness is implied.

## Owner-approved exact seven follow-up dispositions (2026-10-16 Europe/Istanbul; 2026-10-15 UTC)

On 2026-10-16 Europe/Istanbul (2026-10-15 UTC), the owner approved exactly
seven additional exact-match identities in the existing
`external_kubernetes_secret_reference` category. This extends the historically
approved 243 identities to 250 and preserves every prior record. Each addition
requires its exact path/type/finding-digest match and carries `reviewed_on`
2026-10-15 and `expires_on` 2027-01-10. No raw digests or private paths are
repeated here. No category-wide match, automatic approval, cross-category
reclassification, baseline entry, pragma, broad exclusion, bypass, or context
change is authorized.

The 4,408-file / 483-finding / 0-unmatched result predates removal of 21 inline
detect-secrets pragma comments and is historical. The post-removal unfiltered scan
covered 4,408 files / 490 findings, with 7 unmatched against the then-current
243-record overlay. A root-controlled private conditional 250-overlay run reported
0 unmatched on the pre-integration candidate overlay; it is not a post-integration
final-source result or a hosted check. The approved 250-record policy support is now
integrated in source. Its canonical policy tests passed 250 tests in 36.16 seconds
and Ruff check/format passed before this documentation update; final-source
validation and hosted checks remain required for each published source. The 319-identity baseline, 78 required
contexts, blocking CodeQL, hooks, and migration exception remain unchanged.

## Owner-approved exact two follow-up dispositions (2026-10-16)

On 2026-10-16, the owner approved exactly two additional exact-match disposition
identities in the existing external_kubernetes_secret_reference category: Secret Keyword
public Kubernetes object references at security/trivy-university-values.yaml and
tests/test_mfa_helm_contract.py. The exact path/type/finding-digest tuples are recorded
in quality/security-false-positive-dispositions.json; raw digests are not repeated here.
Each record has reviewed_on 2026-10-16 and expires_on 2027-01-10. The prior 250 records
remain unchanged, extending the approved scope to exactly 252. Changed or unmatched
identities remain fail-closed.

This decision authorizes only these two exact identities. It does not authorize
category-wide matching, baseline entries, inline pragmas, broad scanner exclusions,
bypasses, reclassification, or context changes. The baseline remains at 319 identities,
all 78 required contexts remain unchanged, CodeQL remains blocking, hooks are unchanged,
and the finite 131-file migration exception remains unchanged. The policy records do not
establish passing tests, final-source validation, or hosted checks; no release readiness
is implied.

## Owner-approved exact nine Go source-contract identifiers (2026-10-16)

On 2026-10-16, the owner approved exactly nine additional exact-match `Secret Keyword` identities in the existing `source_contract_identifier` category, extending the approved scope from 252 to 261 and preserving all prior 252 records. The finite additions cover three function-binding/restoration patterns across the gateway, file-processor, and ws-hub Go configuration packages: portable opener selection, Unix opener selection, and test cleanup restoration. The exact path/type/finding-digest tuples are recorded in `quality/security-false-positive-dispositions.json`; raw digests are not repeated here. Each record has `reviewed_on` 2026-10-16 and `expires_on` 2027-01-10. See the [dated audit supplement](../audits/AUDIT-2026-10.md#owner-approved-nine-go-source-contract-identifiers-2026-10-16).

This decision authorizes only those nine exact identities. It does not permit category-wide matching, automatic approval, baseline entries, inline pragmas, broad scanner exclusions, bypasses, reclassification, or context changes. The baseline remains at 319 identities, all 78 required contexts remain unchanged, CodeQL remains blocking, hooks remain unchanged, and the finite 131-file migration exception is untouched. These policy records do not establish current-source scan, final-source validation, or hosted-check results. No release readiness is implied.

## Owner-approved exact 18 font-provenance dispositions (2026-10-20 UTC)

The owner separately approved exactly 18 additional path/type/finding-digest
identities and the reviewed validator/test diff: 16 public checksums for the
PDF font, source assets and generation tools, plus two npm SRI findings. The
records remain in the existing `public_integrity_digest` category; SRI support
adds only the two reviewed finite path/type pairs. The exact tuples are in
`quality/security-false-positive-dispositions.json`. The prior 264 records are
preserved unchanged, for 282 approved identities; additions expire on 2027-01-10.

Changed or unmatched identities remain blocking. This permits no category-wide
match, automatic approval, other identity, reclassification, baseline entry,
inline pragma, broad exclusion, expiry extension, bypass or context change.
The 319 baseline identities, 78 required context/app pairs, blocking CodeQL,
hooks and finite131 migration exception remain unchanged. Approval is separate
from integration, final-source scanning, tests and hosted checks, and establishes
no release or visual acceptance.

## Owner-approved exact three auth validation copy dispositions (2026-10-23)

The owner approved exactly three additional path/type/finding-digest identities
and the reviewed validator/test diff for public English password-validation
messages in `frontend/src/i18n/locales/en/auth.json`. The new
`auth_validation_ui_copy` category matches only those three exact identities,
requires their existing category, and caps expiry at 2027-01-10. The exact tuples
are recorded in `quality/security-false-positive-dispositions.json`. The previous
298 records are preserved unchanged, for exactly 301 approved identities.

Changed, unmatched or expired findings remain blocking. This decision permits
no additional identity, broad match, automatic approval, baseline entry, inline
pragma, reclassification, expiry extension or scanner bypass. Baseline319,
Gitleaks25, the 78 required context/app pairs, blocking CodeQL, hooks and finite131
remain unchanged. Integration, final-source scans and hosted checks require
their own evidence; this approval establishes no release or visual acceptance.

## Owner-approved finite scanner-policy additions (2026-10-23)

The owner approved exactly nine additional finite path/type/finding-digest dispositions: seven records associated with AUD-253/Trivy and two SEO identities. Together with the existing 301 records, the approved union is exactly 310. The exact identities, categories, evidence and expiry dates are recorded in `quality/security-false-positive-dispositions.json`; only those nine additions are covered by this approval.

Separately, Trivy v4 test-fixture handling is approved only for the exact fixture findings `KSV0008` and `KSV0024`, through 2026-11-22. This fixture boundary is separate from the nine disposition records and does not authorize a general rule exclusion, production-image exception, or workflow identity. No new workflow identity is approved or included. Neither approval closes AUD-253 or AUD-297.

The detect-secrets baseline remains at 319 identities; Gitleaks remains at 25 immutable fingerprints; all 78 required context/app pairs, blocking CodeQL, hooks, and existing thresholds remain unchanged. These approvals establish no scan, test, hosted-check, or release result. See the [dated audit supplement](../audits/AUDIT-2026-10.md#owner-approved-finite-scanner-policy-additions-2026-10-23).


## Owner-approved five exact baseline-fixture dispositions (2026-10-23)

The owner approved exactly five additional exact path/type/finding-digest dispositions, preserving the prior 310 records and extending the finite approved union to 315. One `public_integrity_digest` is bound to `tests/fixtures/full-backend-reusable-baseline.v4.yaml:8`; four `independent_contract_fingerprint` identities are bound to lines 21, 24, 25, and 26 of that fixture. Each addition is restricted to its exact existing category and identity and expires on 2027-01-10; the exact tuples remain in `quality/security-false-positive-dispositions.json`.

This approval adds no category-wide match, baseline identity, pragma, reclassification, broad exclusion, expiry extension, bypass, or required-check change. It does not alter the 319-identity detect-secrets baseline, 25 Gitleaks fingerprints, 78 required context/app pairs, blocking CodeQL, hooks, or quality thresholds. Policy approval alone establishes no scan, test, hosted-check, or release result. See the [dated audit supplement](../audits/AUDIT-2026-10.md#owner-approved-five-exact-baseline-fixture-dispositions-2026-10-23).

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

## Global GHSA allowlist removal (2026-10-23)

The owner's instruction to close all October audit findings includes the exact
removal of the two global vulnerability suppressions identified by AUD-379 and
AUD-479: `GHSA-4c8g-83qw-93j6` and `GHSA-v2hh-gcrm-f6hx`. Dependency Review now
requires an empty global `allow-ghsas` list. Its delta guard permits removals
and rejects additions; all other policy lists and scalar settings retain their
existing restrictions. This tightens vulnerability detection and grants no new
exception, package exclusion, expiry extension or scanner bypass.

The owner-authored pull-request requirement, vulnerability/license checks,
existing finite license dispositions, all 78 required context/app pairs,
blocking CodeQL, hooks and coverage floors remain in force. This decision is
separate from the finite detect-secrets and Gitleaks inventories. Local tests
and this policy record do not establish current-source hosted success or
closure of either finding; the final source still needs its required checks.


## Owner-approved two exact AUD-495 cache-key canaries (2026-10-23)

The owner explicitly approved exactly two new `aud495_cache_key_redaction_test_fixture` dispositions and the reviewed validator/test diff. The exact path/type/digest identities are the synthetic logger-redaction canaries in `tests/test_cache_object_keys_aud495.py` at source lines 109 and 159. The policy preserves the ordered prior 315 records and appends only these two, for exactly 317 records; both expire on 2027-01-10. This category accepts only those two immutable identities and their evidence markers.

The 319-identity detect-secrets baseline, 25 historical Gitleaks fingerprints, 78 required context/app pairs, blocking CodeQL, hooks and coverage floors remain unchanged. No baseline entry, broad match, expiry extension or automatic approval is authorized. A new or changed identity remains blocking. Policy adoption alone does not prove a final-source scan or hosted check. See the [audit checkpoint](../audits/AUDIT-2026-10.md#owner-approved-two-exact-aud-495-cache-key-canaries-2026-10-23).

## Owner-approved one exact AUD-495 public integrity digest (2026-10-24)

The owner approved exactly one new finite detect-secrets disposition and the reviewed validator/test diff for the public SHA-256 digest used by the immutable policy-prefix source-contract test in `tests/test_verify_secrets_baseline.py`. It uses the exact `Hex High Entropy String` identity and the `public_integrity_digest` category; the validator constrains path, type, digest, evidence and expiry. The policy preserves the ordered 317-record prefix and appends this one record, for exactly 318 records.

The owner is `egorribun`, reviewed on 2026-10-24, with expiry 2027-01-10. The 319-identity detect-secrets baseline, 25 Gitleaks fingerprints and 78 required context/app pairs remain unchanged. No additional identity, broad rule, baseline entry, Gitleaks entry or scanner bypass is authorized. Policy adoption does not establish a final-source scan or hosted-check result; those remain required for the final source. See the [audit checkpoint](../audits/AUDIT-2026-10.md#owner-approved-one-exact-aud-495-public-integrity-digest-2026-10-24).

## Owner-approved three exact public digest dispositions (2026-10-24)

The owner explicitly approved exactly three additional detect-secrets identities
after the post-rollover scan of source `1cadcd03` reported them. The policy
preserves all 318 ordered prior records and appends only these three, for exactly
321 records. Each new record has owner `egorribun`, review date 2026-10-24 and
expiry 2027-01-10.

- `tests/integration/test_aud350_stored_event_timestamp_migration.py`:
  one `Hex High Entropy String` under `public_integrity_digest`, binding the
  frozen historical AUD-350 migration bytes independently of the candidate.
- `tests/test_verify_secrets_baseline.py`: two `Hex High Entropy String`
  identities under `independent_contract_fingerprint`, binding the first and
  second historical AUD-495 cache-canary finding identities. These are new
  fingerprints of quoted public finding hashes, not the original canary
  credentials or a reclassification of their existing dispositions.

The exact ordered additions are records 319-321 in
`quality/security-false-positive-dispositions.json`; their identity tuples,
categories and required evidence are independently constrained by
`scripts/verify_secrets_baseline.py` and source-bound tests in
`tests/test_verify_secrets_baseline.py`. The existing policy-prefix singleton
on the reserved verifier-test path is unchanged. Every other identity on that
path remains rejected; neither the category nor the path receives a broad
allowance. New entries cannot change path, detector, digest, category, owner,
review date or approved expiry scope.

The raw source checksum and historical fingerprint literals remain unchanged.
The first 318 policy records, detect-secrets baseline319, Gitleaks25, all 78
required context/app pairs, blocking CodeQL, hooks and coverage floors are
preserved. No additional identity, inline pragma, broad exclusion, automatic
approval or scanner bypass is authorized. This approval and candidate source do
not establish a successful scan, test or hosted check; final-source evidence
remains required.


## Owner-approved two exact public Git-blob dispositions (2026-10-24)

At 05:35 UTC the owner explicitly approved the two public Git-hash exceptions
requested after the hosted detect-secrets failure. The ordered 321-record
policy prefix is unchanged; only records 322-323 are appended, for exactly 323
finite identities. Both are `Hex High Entropy String` findings in the existing
`public_integrity_digest` category, owned by `egorribun`, reviewed on
2026-10-24 and expiring on 2027-01-10:

- `tests/helpers/migration_148642dd1207_trace.py`, assignment `SOURCE_GIT_BLOB`,
  identifies the complete source bytes of
  `alembic/versions/148642dd1207_fix_missing_tables.py`.
- `tests/test_mfa_webauthn_tombstone.py`, assignment
  `HISTORICAL_ORCHESTRATOR_BLOB`, identifies the complete source bytes of
  `tests/test_migration_148642dd1207_orchestrator.py`.

The exact detector fingerprints are recorded in the policy and independently
in `tests/fixtures/public-git-blob-dispositions.json`. Source contracts compute
the Git blob SHA-1 from the actual referred bytes and then the detect-secrets
SHA-1 of the consumer's literal. No Git pin is changed or duplicated as a new
test literal. The validator restricts both reserved paths and fingerprints,
category, evidence, owner, review date and finite expiry. It remains
filesystem-independent: removal of a consumer may leave a stale historical
record, while a changed pin is a distinct finding requiring its own disposition.

The retired-factor guard treats only the exact second record's
`identity.path` as inactive scanner bookkeeping. Its detector fingerprint,
path, type and category must all match; evidence, category and every other
field remain scanned for active retired-factor references. Runtime and backend
test guards remain in force. The independent JSON fixture avoids introducing
a second backend-source exemption or obscuring the literal path.

Baseline319, Gitleaks25, all 78 required context/app pairs, blocking CodeQL,
hooks and quality floors are unchanged. No baseline addition, inline pragma,
broad exclusion, reclassification, expiry extension or scanner bypass is
authorized. No migration waiver is established by these scanner dispositions.
Accepted audit scope remains 282/512; policy adoption is not a passing scan,
test, hosted-check, full-CI or release result. Final-source validation remains
required.


## Exact public Git-blob rebindings for preference preservation (2026-10-24)

Under the owner's authorization to apply analogous narrow, justified audit
exceptions without another approval round, this update appends exactly two
`public_integrity_digest` records for the reviewed preference-preservation
repair. All 323 preceding records remain byte-for-byte unchanged; the total
is 325. The additions retain owner `egorribun`, review date 2026-10-24 and
expiry 2027-01-10, with the same exact `Hex High Entropy String` detector type.

The two new identities bind `SOURCE_GIT_BLOB` in the migration trace helper
to the reviewed migration source, and `HISTORICAL_ORCHESTRATOR_BLOB` in the
retired-factor guard to the reviewed orchestrator test source. They are new
records, not replacements for the two historical pins. The public Git blobs
were fetched and independently rehashed using Git's byte-length header.
Their detector fingerprints were computed with the pinned detect-secrets
v1.5.0 SHA-1-of-UTF-8 algorithm. These are **computed expected findings**, not
yet a claim that a hosted scanner emitted them or that a scan passed.

The validator now admits only the four explicit historical/rebound
path/type/fingerprint tuples on the two reserved consumer paths. No
path-wide or category-wide allowance is added. The independent JSON fixture
preserves its first two records, and policy tests preserve the complete
323-record prefix before checking the exact two-record suffix. Source-binding
tests derive the current literal and referred Git blob and require a matching
approved identity; stale historical records do not force an old current pin.

The retired-factor scanner-bookkeeping guard recognizes only the two exact
historical/rebound identities for its own path, under the same category.
Only `identity.path` is normalized; other identity fields, category, evidence
and active retired-factor references remain checked. Negative tests exercise
both records, changed scope and path/fingerprint transfer. The literal Git
pin remains explicit; production migration changes are a separate candidate.

Baseline319, Gitleaks25, all 78 required context/app pairs, blocking CodeQL,
hooks, expiry caps and quality floors remain unchanged. This grants no Squawk
waiver, broad exclusion, inline pragma, reclassification or scanner bypass.
The accepted ledger remains 283/512. Hosted scanner output, source-bound tests
and final-source required checks must establish their own results.
