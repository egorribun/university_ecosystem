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

1. **Tier 0 keeps 100 % for every applicable metric.**
   Files matched by tier0_rules in quality/ownership-mapping.json (authentication,
   sessions, MFA, security, rate limiting, PII, cryptography, ReBAC, CSRF,
   migrations, native and WASM crates) keep 100 % line, statement, branch and
   function coverage. The owner retired the obsolete 131-file legacy migration
   exception on 2026-11-02. The current baseline migration
   `alembic/versions/202611020000_mvp_baseline.py`, all other migrations and
   every other Tier 0 file remain at 100 % for all four metrics. No migration
   coverage exception is active; the dated decisions below preserve its history.
2. **Non-Tier 0 coverage becomes a ratchet.** Each component floor equals the
   value measured on the last certified `main` run, rounded down to one decimal,
   and may never decrease. Changed non-Tier 0 lines in a pull request need at
   least 90 % patch coverage. Until the first certified `main` baseline exists,
   the current floors stay in force and remain blocking in CI. Owner clarification
   on 2026-10-08 keeps these gates until Q3; if they block MVP, bringing Q3 forward
   requires a separate decision. Every Tier 0 file remains strict; retiring the
   historical migration exception does not advance Q3 or change other floors.
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

**Historical decision, retired by the owner on 2026-11-02 below.** The original
scope, evidence and expiry are retained in an immutable test fixture, not an
active exception in the current quality contract.

On 2026-10-14 UTC, the owner approved a finite no-decrease baseline for exactly
131 unchanged Alembic migration files under alembic/versions, source-bound to
base commit ac74e915 and expiring 2026-11-13.
The per-file native or derived metrics, source identity, and provenance were
recorded in the quality contract and its bound evidence; this was not an
aggregate-only exemption. The baseline applied only while each listed source
file was unchanged. New, modified, or unmatched migrations, including PR-touched files,
remain subject to 100 % lines, statements, branches, and functions. All other
Tier 0 files, current per-component floors, the 100 % patch floor, and the
blocking validator remain unchanged. Q3 and its coverage ratchet remain v1.1;
this approval does not advance Q3. Policy integration and final-source
verification are separate from the owner decision.

## Owner-approved retirement of obsolete migration coverage baseline (2026-11-02 UTC)

On 2026-11-02 at 09:28 UTC, the owner approved removal of only
`/tier0/legacy_migration_baselines` from `quality/quality-contract.json`,
with corresponding ADR-047, contributor guidance and test updates. The retired
object covered exactly 131 paths and 524 metric records, bound to
`ac74e915ae539f098f0fa1e7c83b355703069984` with the original
`2026-11-13` expiry date. Its canonical sorted-JSON SHA-256 is
`b66b48835365bac8cf52df8c7925633e12009a0fb7eba33f3c6ac8fedd60d3fe`.
At source `4cdc241f66bbbf4bc884215aa4d61dc3906f1c6e`, all 131 listed
files are absent after migration consolidation; the current
`alembic/versions/202611020000_mvp_baseline.py` was never in that list.

The current baseline and all other Tier 0 migrations retain 100 % line,
statement, branch and function coverage. No other threshold, exception list,
coverage scope, 100 % patch floor, required context/app pair (all 78), blocking
CodeQL check or hook is changed by this retirement. Q2/Q3 activation and the
separate security and model-default decisions are outside this approval.

A lossless representation of the retired object is retained in
`tests/fixtures/quality/legacy-migration-baselines-ac74e915.json`.
Only its 15 verified public Git and report-integrity fields use explicitly
named `*_bytes` arrays. The test loader checks exact 20-byte or 32-byte widths
and integer byte values, reconstructs only those fixed fields, and authenticates
the complete original object against its independent canonical digest before
use. This representation follows the existing public digest-byte convention;
it adds no scanner filter, path exclusion or finding disposition.
Historical source-binding tests restore bytes from the full pinned base commit
into an isolated temporary fixture; they never execute those migrations.
Missing history or source bytes fail the tests rather than being skipped.
Existing mutation, expiry, changed-source, strict-metric and exact-residual
negative controls remain. Malformed digest arrays, extra fields and changed
paths, metrics or digest bytes are rejected; the current baseline also has four-metric
100 % / 99 % controls. Production validation is not relaxed to ignore missing
sources, and the historical fixture does not reactivate the exception.

This policy retirement is not schema-equivalence proof, permission to activate
an unproved successor workflow, a deployment approval or a passing CI result.
Each resulting source revision still requires its own validation evidence.

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


## Two observed public source-metadata dispositions (2026-10-24)

Under the owner's task-scoped authorization for analogous narrow, justified
audit exceptions, this update appends exactly two records to the unchanged
325-record prefix, for 327 dispositions. Both findings were actually reported
on source `764b474318c9b0a226b070a30ff3dd4b61c9472f` by security job 120811736955 and baseline-verification
job 120811862789. The records retain owner `egorribun`, review date 2026-10-24
and expiry 2027-01-10.

1. `frontend/scripts/generate-zod-root-lock-candidate.mjs:19` is an exact
   `Hex High Entropy String` under `public_integrity_digest`. Its explicit
   `EXPECTED_ZOD_SOURCE_SHA` literal is the public upstream commit referenced
   by the official `colinhacks/zod` v4.6.7 tag. Hosted metadata job 120800858421
   reports the same registry gitHead and a mature publication date. This
   establishes a public source identifier and matching metadata, not
   cryptographic package-publish provenance. The module is reused as a pure
   helper by the staged generator, so the literal and its comparison remain.
2. `tests/test_logging_pii_redaction_contract.py:176` is an exact
   `Secret Keyword` under `source_contract_identifier`. The captured value
   is the public signing-key name `csrf-signing-key`, not signing material.
   It occurs in the benign `secret_name` metadata field and the expected
   output of `test_sensitive_field_matching_preserves_related_nonsecret_metadata`.
   Keeping this negative control prevents an overly broad token/secret-prefix
   redactor from hiding useful metadata. Its second occurrence has the same
   path/type/fingerprint identity, not another disposition.

The pinned detect-secrets v1.5.0 Python quoted-colon keyword rule extracts the
label, and `PotentialSecret.hash_secret` hashes the exact UTF-8 value with
SHA-1. The public commit literal is hashed the same way. The independently
computed fingerprints are stored as exact detector identity bytes in the
policy, validator and test expectations; neither consumer value is altered,
encoded, copied elsewhere to evade scanning, or covered by an inline pragma.

A separate finite cohort reserves both paths and fingerprints and binds each
to its existing category, evidence, owner, review date and expiry cap. The
original 17-identity source-contract cohort remains unchanged; the effective
category receives only the single new label identity. Source-binding tests
bind the actual upstream-pin literal and the real redaction assertion. The
required Node helper guards exercise the default upstream-pin comparison,
including rejection of a different well-formed Git identifier.
Changed values, transferred paths/types/categories, missing evidence, pending
approval, expiry extensions and extra identities remain rejected. Historical
records may become stale; no current value is automatically approved.

Baseline319, Gitleaks25, all 78 required context/app pairs, blocking CodeQL,
hooks, quality floors and existing expiries remain unchanged. No broad
exclusion, baseline addition, reclassification or scanner bypass is introduced.
The accepted ledger remains 283/512. Policy adoption does not establish a
passing final-source scan, regression suite, full CI or release result.


## Exact migration catalog-proof pin and coordinated scanner scope (2026-10-24)

The same task-scoped owner authorization covers one additional reviewed public
Git-blob identity for `SOURCE_GIT_BLOB` in
`tests/helpers/migration_148642dd1207_trace.py`. The referenced migration blob
is `cf93b261eeccfb2b136144fd34fa71a3fa557ecd`; all 100385 source bytes were
independently rehashed with Git blob framing. Its exact detect-secrets v1.5.0
SHA-1-of-UTF-8 fingerprint is
`81b6af2e547f39bae2a9b534b9141d58f7d6c428`. This is a **computed expected
finding**; unlike the two metadata findings above, it has not yet been
confirmed by a hosted scan of the new consumer literal.

The coordinated policy contains exactly 328 records: the entire published
325-record prefix remains byte-for-byte unchanged, followed by the two observed
metadata records above and this one public integrity-digest record. The new
record retains owner `egorribun`, review date 2026-10-24 and expiry 2027-01-10.
The independent Git-blob fixture appends only its fifth record; the validator
adds only the fifth reserved path/type/digest tuple. Existing metadata and
negative controls cover changed paths, detectors, fingerprints, categories,
owners, dates, evidence, expiry, duplicate records and unapproved additions.
The current-source binding derives the referred Git blob from actual bytes
and requires an exact approved detector identity; old records may become stale.
No historical record, consumer path, scanner category or expiry is widened.
The production migration and its pin-only trace rebind are coordinated changes,
not evidence of PostgreSQL GREEN or a Squawk exception.

Separately, the coordinated Gitleaks inventory grows from 25 to exactly 26
immutable historical fingerprints. Its sole addition is
`75de40e472f1ef8fccedea286b0b5b456c29f1c5:tests/test_cwv_rum_security.py:generic-api-key:939`.
The public historical source at that exact location is a verifier call argument
expression, not a credential value. The original 25 fingerprints are unchanged.
Independent inventory tests reject commit/path/rule/line drift, wildcard or
global forms, duplicate or extra entries, and changes to the original set.
No later copy of the expression or broader path receives an exception.
Gitleaks26 is adopted only with its exact inventory and matching contract tests.

Baseline319, all 78 required context/app pairs, blocking CodeQL, hooks, quality
floors and prior expiry caps remain unchanged. No baseline entry, inline pragma,
reclassification, automatic approval or broad scanner exclusion is authorized.
The accepted ledger remains 283/512; these policy records do not close another
audit item or establish a passing final-source scan, full CI or release result.
The owner explicitly authorized publication of the audit results, CI references,
exact hashes and exception identities, and retention of the already recorded
archive metadata in STATUS, INDEX and this ADR. The archive itself, live secrets
and private personal data are not part of this update; no permanent permission
rule is created.


## Exact orchestrator fixture-isolation Git-pin rebind (2026-10-24)

Under the same owner authorization for narrow, justified public-hash audit
exceptions, append exactly one `public_integrity_digest` disposition to the
unchanged 328-record policy prefix, for exactly 329 records. It covers only
`HISTORICAL_ORCHESTRATOR_BLOB` in
`tests/test_mfa_webauthn_tombstone.py`, with detector type
`Hex High Entropy String`, owner `egorribun`, review date 2026-10-24 and
expiry 2027-01-10. All earlier records, categories and expiry dates remain
unchanged.

The reviewed public orchestrator blob is
`069deb3c6984e1e9992b01f6ce4313ea3cc49a57` (18034 bytes); independently
rehashing its complete Git blob framing reproduces that identity. The pinned
detect-secrets v1.5.0 SHA-1-of-UTF-8 algorithm gives the exact finding identity
`2057dcee41384aada06da79e9afb1d07194c9891`. This remains a **computed expected
finding**, not a hosted scanner observation of the new pin.

The source change follows the actual unit-test RED in job 120865063488:
the standalone unavailable-inspector test reached preferences backfill before
its intended later `has_table` failure. One additional test-local backfill
stub restores that isolation while retaining the original expected exception
and operation assertions. The production migration is unchanged by this
fixture correction; the new test source still requires hosted GREEN.

The independent JSON fixture appends only its sixth record. The metadata
validator admits only the sixth exact path/type/fingerprint tuple, with the
existing owner/date/evidence/expiry checks. Prefix tests preserve all 328
prior records and isolate the one-record suffix. Current-source verification
continues to derive the complete referred Git blob and its detector identity;
old approved records may become stale but cannot approve a changed pin.

The retirement guard adds only the third exact identity for its own scanner
bookkeeping path. Only its matching `identity.path` is normalized; all other
fields, evidence, categories and active runtime references remain scanned.
All three own-path records receive the existing negative scope and reference
controls. No path-wide exemption, extra backend-source allowance, wildcard,
inline pragma, baseline addition, reclassification or automatic approval is
introduced. Baseline319, Gitleaks26, all 78 required context/app pairs, blocking
CodeQL, hooks and quality floors are unchanged. This policy update accepts no
additional audit item and establishes neither full CI nor release readiness.


## Exact public Alembic revision identifier disposition (2026-10-24)

Under the owner's task-scoped authorization for narrow, justified public-source
exceptions, append exactly one record to the unchanged 329-record policy
prefix as record 330, before the two coordinated Git-pin additions below. The finding is
`Hex High Entropy String` at
`tests/integration/test_migration_148642dd1207.py:1823`: the public
groups-sequence successor revision passed directly to `command.upgrade`.
It is a public Alembic revision identifier, not a Git-blob digest or credential.
The new exact-only category is `public_alembic_revision_identifier`; it does
not reclassify any existing record or authorize arbitrary revision-shaped values.

The initial hosted observation is
[security/types job 120891538662](https://github.com/egorribun/university_ecosystem/actions/runs/40100380000/job/120891538662).
The same finding recurred on source `e6a97bd3` in
[security/types job 120896980362](https://github.com/egorribun/university_ecosystem/actions/runs/40102373009/job/120896980362).
The exact path/type/SHA-1-of-UTF-8 identity is recorded in the policy and
independently in `tests/fixtures/public-alembic-revision-disposition.json`.
The original literal remains explicit and unchanged. Source-binding tests
derive it from the direct upgrade call and require the exact public revision
definition and `down_revision` relationship; sequence runtime semantics remain
the responsibility of the PostgreSQL regression tests, not scanner authorization.

The tests-first
[contract job 120896980434](https://github.com/egorribun/university_ecosystem/actions/runs/40102373009/job/120896980434)
ran 24 new revision guards on that source: the full policy lane reported
**7 failed / 469 passed**, with exactly the expected missing record,
missing category, total-count and four generic-category/scope bypass failures.
The independent consumer lane passed all 2442 cases. These are pre-fix
observations, not a claim that the new policy or migration index plan is GREEN.

The validator reserves only this exact identity, its path and fingerprint.
Changed paths, detector types, digests or categories cannot fall through to
generic hash categories; changed evidence, owner, review date, pending approval,
duplicate/extra identities and expiry extensions remain rejected. The record
retains owner `egorribun`, review date 2026-10-24 and expiry 2027-01-10.
Historical prefix contracts remain exact and bounded, and all 329 preceding
records retain their original categories, evidence and expiry dates.

Four separate public compiler-golden findings remain undisposed in this
332-record coordinated policy below. Their new negative/source-binding tests are intentionally
tests-first; their fixture is not an approval and does not match scanner
findings until a separately reviewed policy update. No global hash, SRI,
path-wide or category-wide allowance is introduced.

Baseline319, Gitleaks26, all 78 required context/app pairs, blocking CodeQL,
hooks and coverage floors remain unchanged. There is no baseline addition,
inline pragma, automatic approval, blanket waiver or scanner bypass. This
record closes no additional audit item, grants no Squawk exception and does
not establish a passing final-source scan, full CI, deployment or release.
Fresh hosted evidence is required for the new source.


## Exact post-primary-key duplicate-index source rebind (2026-10-24)

The coordinated policy contains exactly 332 records: the complete published
329-record prefix, the observed Alembic revision record above, and two new
`public_integrity_digest` identities. They bind `SOURCE_GIT_BLOB` in
`tests/helpers/migration_148642dd1207_trace.py` and `HISTORICAL_ORCHESTRATOR_BLOB`
in `tests/test_mfa_webauthn_tombstone.py`. The owner, review date and
expiry remain `egorribun`, 2026-10-24 and 2027-01-10. This uses the existing
exact public-Git-blob mechanism; no new matching rule or broad hash allowance
is introduced.

The production change removes only the redundant upgrade-side
`CREATE INDEX IF NOT EXISTS ix_groups_id ON groups (id)` immediately after
attaching the validated unique index as `groups_pkey`. The identical downgrade
index build is retained. All transaction boundaries, access-exclusive locking,
preflights, data conversions, enforcing checks, final key and foreign-key
validations remain byte-for-byte unchanged. The source has 100312 bytes and
its complete Git blob framing was independently rehashed before the trace
pin was rebound. The resulting exact SHA-1-of-UTF-8 detector identity is
recorded in the policy and seventh public-Git-blob fixture record. It is a
**computed expected finding**, not an observed scanner result for the new pin.

The tests-first
[PostgreSQL diagnostic job 120901869267](https://github.com/egorribun/university_ecosystem/actions/runs/40103663774/job/120901869267)
on source `36e84f25` reported exactly **2 failed / 71 passed**. Only the two
legacy-key cases retained the redundant physical index; both integer-key
controls, rollback catalog/data checks, helper downgrade/upgrade round trips
and sequence/UUID successor controls passed. That result authorizes this
narrow implementation step; it is not post-fix GREEN. The helper round trips
do not establish a full-revision downgrade guarantee.

The existing legacy-upgrade orchestrator assertion also required the removed
index. Its narrow update retains the dropped-column assertion, requires the
primary-key attachment and forbids only the redundant index creation. The
reviewed test has 18098 bytes; its complete Git blob framing and the new pin's
detector fingerprint were independently recomputed. The eighth Git-pin fixture
record binds this source change. Both pin findings remain computed expectations,
not hosted observations or automatic approvals.

All six earlier Git-pin fixture records and all 329 published policy records
are unchanged. Existing per-record positive and negative controls apply to
both new tuples; bounded prefix guards isolate policy records 331 and 332.
Current-source verification still recomputes each entire referred Git blob and
the literal's detector fingerprint. The retirement guard adds only the fourth
exact own-path bookkeeping identity. Only its matching `identity.path` is
normalized; evidence, categories, other fields and active retired-factor
references remain scanned. The previous three identities and all negative
controls remain, with the same controls applied to the fourth identity.

The four compiler-golden identities remain tests-first only, targeting a
future 336-record policy after their own observed RED and review. Their fixture
does not approve scanner findings. Baseline319, Gitleaks26, all 78 required
context/app pairs, blocking CodeQL, hooks, expiry caps and coverage floors are
unchanged. The modified migration still requires Tier 0 coverage and fresh
hosted PostgreSQL, trace, rollback and scanner evidence. Remaining Squawk
findings remain blocking; no downtime guarantee, blanket waiver, production
deployment, additional audit closure or full-CI success is claimed.


## Four exact public compiler-golden metadata dispositions (2026-10-24)

Under the same task-scoped owner authorization for narrow public-source audit
exceptions, append exactly four records to the unchanged 332-record policy
prefix, for 336 finite dispositions. The immutable source is
`frontend/scripts/react-compiler-zod-compat/legacy-baseline.json`, captured by
[legacy compiler job 120802074003](https://github.com/egorribun/university_ecosystem/actions/runs/40069691438/job/120802074003).
It preserves historical behavior and artifact identities; it is not a
vulnerability-closure certificate or a current-source identifier.

The four actual findings were reported by
[security/types job 120896980362](https://github.com/egorribun/university_ecosystem/actions/runs/40102373009/job/120896980362)
and repeated on source `ee35e6de` in
[job 120916104166](https://github.com/egorribun/university_ecosystem/actions/runs/40108844098/job/120916104166):

- `sourceSha`, line 9: the public Git commit of the legacy capture,
  `Hex High Entropy String` under `public_integrity_digest`.
- `compilerIntegrity`, line 13: the complete public npm SHA-512 SRI for
  `eslint-plugin-react-compiler@19.1.0-rc.2`,
  `Base64 High Entropy String` under `public_package_integrity_metadata`.
- `compilerBundleSha256`, line 14: the unchanged official rc.2 bundle checksum,
  `Hex High Entropy String` under `public_integrity_digest`.
- `formatterEntrySha256`, line 133: the historical pre-override
  `zod-validation-error@3.5.4` entry-file checksum, not the separately tested
  adapter formatter, with the same exact Hex detector and integrity category.

The pinned detector hashes each complete UTF-8 literal with SHA-1, including
the SRI algorithm prefix. The exact path/type/digest tuples and categories are
stored in the policy, validator and independent
`tests/fixtures/public-compiler-golden-dispositions.json`. Source tests derive
all four hashes from their actual JSON fields, retain the capture kind/status
and source link, and require the compiler SRI to match the unchanged current
lockfile. The existing frontend parity tests own the complete 37-case runtime
corpus and installed artifact/formatter checks; scanner authorization does not
replace those checks or widen the adapter's compatibility claim.

Before implementation,
[contract job 120916104222](https://github.com/egorribun/university_ecosystem/actions/runs/40108844098/job/120916104222)
reported exactly **33 failed / 531 passed** in the 564-case policy cohort.
All 33 failures belonged to the new golden guards: missing records/count/SRI
scope and currently accepted scope or approval mutations. The additional
category-generated achievement-URL reclassification control passed, as did
the revision and both migration pin chains. The separate consumer result was
6 V2 fixture failures / 2474 passed, not full contract GREEN.

The validator now reserves only the four exact identities, their path and
fingerprints, categories and evidence. The existing SRI category gains one
path/type pair behind the exact reservation, not a path-wide SRI allowance.
Changed paths, types, digests, categories, owners, review dates, evidence,
pending approvals, expiry extensions, duplicate/extra records and transferred
digests remain rejected. Owner `egorribun`, review date 2026-10-24 and expiry
2027-01-10 are retained. No matching algorithm, detector or existing identity
is reclassified; all 332 earlier records and eight Git-pin fixture records
remain unchanged.

A separate new V2 invalid-private-field test finding in
`tests/test_live_stand.py` is not approved by these four records and still
requires its own disposition decision and strict tests. The accompanying V2
sentinel fixture and 26 source/scope guards are tests-first only, targeting a
future 337-record policy after their own observed RED; they authorize no
additional scanner finding. Baseline319, Gitleaks26,
all 78 required context/app pairs, blocking CodeQL, hooks, expiry caps and
coverage floors remain unchanged. No baseline entry, inline pragma, broad
exclusion, automatic approval or scanner bypass is introduced. This update
closes no additional audit item and establishes neither final-source scanner
GREEN nor PostgreSQL, full-CI, deployment or release success.


## Exact V2 invalid-private-field sentinel disposition (2026-10-24)

Under the existing task-scoped owner authorization for analogous narrow
exceptions, append exactly one record to the unchanged 336-record prefix,
for 337 finite dispositions. Its existing category is
`ci_test_contract_sentinel`; no category, detector or matching algorithm is
introduced. The exact `tests/test_live_stand.py` / `Secret Keyword` identity
is independently recorded in
`tests/fixtures/live-registration-private-field-disposition.json` and the
policy. It is the synthetic invalid password-field value in
`test_live_reset_registration_v2_rejects_private_fields_and_wrong_types`,
not credentials or request data. The raw sentinel is not copied into this
policy documentation.

The finding was observed in
[security/types job 120916104166](https://github.com/egorribun/university_ecosystem/actions/runs/40108844098/job/120916104166).
On source `8d5011b0`, the tested merge `8e397586` had the identical source
tree; [scanner job 120938703794](https://github.com/egorribun/university_ecosystem/actions/runs/40116445226/job/120938703794)
reported only this unmatched finding at line 13907. The four compiler-golden
findings were no longer unmatched. This is source-specific evidence, not a
passing final-source scanner result.

Before implementation,
[contract job 120938602851](https://github.com/egorribun/university_ecosystem/actions/runs/40116445226/job/120938602851)
executed all 590 policy cases: exactly **6 failed / 584 passed**, without
policy setup errors. The failures were the missing record, total 336 rather
than 337, rejected exact category/path pair, and three unexpectedly accepted
mutations: a transplanted digest, integrity-category reclassification and an
unknown digest at the reserved path. All other existing policy controls
passed. The consumer cohort separately reported 20 tenant-context failures
and 2483 passes; all seven V2 Python cases passed. These results do not imply
full Contract GREEN.

The finite identity and evidence tuple reuse the existing reserved path-or-
digest guard. Only its exact path/type pair is added to the existing sentinel
category behind that reservation. No path-wide or digest-wide permission is
created. The whole validator function body is unchanged. Existing evidence,
owner `egorribun`, review date 2026-10-24 and maximum expiry 2027-01-10
checks remain enforced. Changed path, detector, digest, category, owner,
review date, evidence, pending approval, expiry extension, duplicate and extra
records remain rejected.

Source guards derive the fingerprint from the actual sole exact scalar,
require its invalid-field dictionary, serialization and rejection assertion,
and reject destructive corpus edits, deletion or aliasing while retaining
the real append-only cases. These are bounded AST contracts, not a proof of
arbitrary Python semantics. All 26 sentinel tests, previous historical
prefix slices, four golden fixture records and eight Git-pin fixture records
remain unchanged; only eleven active cumulative-count assertions advance
from 336 to 337. The prior formatter-only repair is retained.

Baseline319, Gitleaks26, all 78 required context/app pairs, blocking CodeQL,
hooks, expiry caps and coverage floors remain unchanged. There is no baseline
entry, inline pragma, broad exclusion, automatic approval or scanner bypass.
This record adds no accepted audit ID; ledger292 remains unchanged. Fresh
590-case policy and raw scanner results are required on the final source.
No additional migration closure, full CI, release or deployment success is
claimed.

## Nine exact owner-approved integrity dispositions (2026-10-26)

Three separate owner decisions authorize exactly nine appended identities:
one migration-source Git checksum, seven Node compiler-facade integrity
identities, and one updated migration-orchestrator Git checksum. The ordered
337-record prefix is unchanged; the active finite policy now contains 346
records. The new suffix contains six `public_integrity_digest` identities
and three `public_package_integrity_metadata` identities, all within their
existing categories. The exact paths, detector types and finding digests
are recorded in `quality/security-false-positive-dispositions.json`.

The first eight additions retain review date 2026-10-25; the final Git-pin
addition is reviewed on 2026-10-26. All nine expire on 2027-01-10. Existing
records, their expiry dates, origin metadata and historical fingerprints
are preserved. Source-bound validator checks and the finite Git-blob fixture
bind the additions to the reviewed artifacts; changed identities and category
transplants remain blocking. The retired-factor consumer masks only the
additional exact approved identity and tests path, type, digest and category
near misses. This adds no path-wide permission or scanner bypass.

The bounded private verification passed 625 tests using all 69 declared input
files: the full disposition-policy module and two selected retired-factor
consumer tests. This is not a full canonical MFA or final-source result.
Integrated canonical tests, the final scanner run and required checks on the
published source remain mandatory. This policy record closes no audit item.
Baseline319, Gitleaks26, all 78 required context/app pairs, blocking CodeQL,
hooks and coverage floors are unchanged.

## Owner-approved scoped decisions (2026-10-27)

### Forward-only migration preparation

The owner authorized development and checks for a staged, forward-recoverable migration design because the applied status of `148642dd1207` is unknown. Keep that historical revision immutable and use additive forward revisions only. Phase commits and forward recovery are allowed for development. Cutover requires either draining old writers or a designed and tested compatibility period. This approval does not authorize a merge, release, deployment, scanner exception, warning suppression, or any claim of global rollback or zero downtime; it does not itself clear existing Squawk findings.

### Exact Caddy dependency cooldown

The owner authorized the early security update to exactly `curl=8.23.0-r0` and `libcurl=8.23.0-r0` in the project Caddy runtime. Every other dependency cooldown rule remains unchanged. Builds, installed-version checks, compatibility tests and the blocking image scan remain required; no scanner waiver or deployment is authorized.

### AUD-247 public integrity digest

The owner approved one exact append-only `public_integrity_digest` after the existing 346-record prefix; the approved integration bundle yields 347 records. Its identity is the single appended entry in [the disposition policy](../../quality/security-false-positive-dispositions.json), for `tests/test_security_hardening_workflow_contract.py` and detector type `Hex High Entropy String`. The exact digest and evidence remain authoritative in that record and its finite validator; this decision permits no other identity. The record is owned by `egorribun`, evidence review date 2026-10-26, owner approval date 2026-10-27, expiry 2027-01-10. It becomes effective only with the exact source-bound validator, test and policy integration and final-source checks; it grants no other disposition and closes no audit or coverage item.

The evidence phrase “binary was not executed” is scoped to the private release-asset review. It does not claim the checksum-bound binary was absent from CI: root-verified hosted records report the same checksum and CI execution after hash verification. The release asset remains mutable.

### One Ruff S603 call

The owner authorized exactly one inline `# noqa: S603` on the `subprocess.run` call in `_run_coverage_worker` at `tests/test_coverage_manifest.py:2012`. That call uses the fixed `sys.executable` with `-B`, `-I` and `-X utf8`, invokes the repository-owned static `_COVERAGE_ISOLATION_WORKER` via `-c`, uses the explicit constrained worker environment, and does not invoke a shell. The authorization covers only that call and does not allow a file/module-level suppression, Ruff configuration change, or any other S603 exception. The source annotation is limited to the reviewed call. Final-source Ruff, tests, scanner checks and required hosted results remain mandatory.

These decisions preserve the 319-entry detect-secrets baseline, the 26 Gitleaks fingerprints, all 78 required CI context/app pairs, blocking CodeQL, hooks and coverage floors. Policy records and owner approvals do not replace final-source tests, scans or required hosted checks.

## Authorized inactive historical-148 preparation (2026-10-28)

The owner authorized preparation of a narrow CI rule with tests for the exact
37 historical Squawk observations, solely for a new empty MVP database and
through 2026-11-13 at 00:00 UTC. The historical migration, atomicity and raw
scanner evidence must remain unchanged. These are accepted-risk candidates, not
false warnings or elimination of blocking-lock/rewrite/drop risks. Populated
database execution, deployment and an unrestricted scanner waiver were not
authorized.

The historical148 preparation (plan file removed 2026-11-03; see git history)
records complete ordinary and expanded SQL plus JSON evidence. Stage A contains
an exact `prepared-inactive` inventory and a
[pure historical recognizer](https://github.com/egorribun/university_ecosystem/blob/3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9/scripts/quality/validate_historical148_squawk.py)
with compiled fingerprints of that policy and capture. It accepts bounded byte
inputs, normalizes only raw-warning JSON representation/order and checks the real
UTC window. Its only positive verdict is `matched-diagnostic-inventory`, not
scanner success or migration permission. No CLI, file reader or migration-gate
consumer is connected; raw Squawk failures remain blocking. Preparation is not
activation. Exact-source tests and required checks still need their own receipts.

Before a separate reviewed activation diff, obtain actual owned-template0 and
empty-catalog admission, recapture source-bound evidence after renderer changes,
handle merge-parent metadata correctly and verify the other 141 migrations
strictly. Neither a captured declaration nor the prepared matcher substitutes
for those receipts. The contract requires fail-closed real UTC expiry with no
caller override or automatic extension.

This preparation changes no migration bytes, raw gates, existing scanner
arguments, secret dispositions, coverage floors, required context/app pairs or
blocking CodeQL. No audit finding closes from this package alone.


## Fifty-eight exact historical-148 integrity dispositions (2026-10-29)

The owner approved exactly 58 additional `public_integrity_digest` identities:
29 in `quality/historical148-squawk-policy.json`, 27 in the immutable historical
capture fixture and two canonical-document fingerprints in its validator.
The ordered 347-record prefix is unchanged; the finite approved union is 405.
Each addition is bound to the exact path, detector type and finding digest,
with source-binding tests for the complete reviewed source blobs. The owner is
`egorribun`, review date 2026-10-29, and unchanged expiry 2027-01-10.

The fresh [pre-commit report](https://github.com/egorribun/university_ecosystem/actions/runs/40848658856/job/123362944161)
reported all 58 locations; [baseline verification](https://github.com/egorribun/university_ecosystem/actions/runs/40848658856/job/123364470337)
independently reported 58 new identities. The public literals at those exact
source locations determine the SHA-1 detector fingerprints; the logs do not
print a raw fingerprint inventory. Repeated literals in one file remain one
path/type/digest identity, not additional approvals.

This decision preserves the 319-identity detect-secrets baseline, 26 historical
Gitleaks fingerprints, 78 required context/app pairs, blocking CodeQL, hooks,
coverage floors and existing expiry caps. The two pre-existing identities that
share a public digest remain bound to their original paths, categories and
approval metadata. New or changed identities remain blocking; no category-wide
match, baseline addition, inline pragma or scanner bypass is authorized.

These are public source-integrity values, not credentials. This disposition
neither activates the prepared Squawk matcher nor accepts migration risks,
changes migration bytes or authorizes execution or deployment. Approval and
source-bound tests do not substitute for final-source scans or hosted checks.

## Historical-148 recapture without a new disposition (2026-10-29)

The 35aeedeb recapture (plan section removed 2026-11-03; see git history)
binds the inactive recognizer to actual SQL/JSON after the reviewed renderer
correction. Both SQL inputs and all 37 warning objects, apart from actual
temporary paths, remain unchanged. The migration, atomicity, raw exits and
prepared-inactive status are preserved. The old capture remains historical
evidence; no scanner-success or execution permission is inferred.

This is evidence maintenance, not an additional owner-approved secret
disposition. The approved union stays 405; the 319-entry baseline, 26 Gitleaks
fingerprints, current expiry caps and all other gates remain unchanged.
The prior 58-identity approval cannot be transferred to new paths, fingerprints
or whole-source bindings. Obtain the actual new scanner inventory and review
each public integrity literal; any new finite approval and its source-bound
negative tests are a separate change. Until then, unmatched identities and
source-binding mismatches remain blocking. No audit acceptance increases.

## Pool-safe historical-148 recapture without activation (2026-10-29)

The 36f70a0f recapture (plan section removed 2026-11-03; see git history)
updates the inactive evidence after the renderer's owned-pool privacy correction.
Its exact-source 41 lifecycle and seven PostgreSQL controls pass; the three
Pool regressions pass by whole-file/cohort evidence, not printed named results.
Both SQL inputs and all 37 warning objects, except the actual ordinary temporary
path, remain unchanged. Raw exits stay 1, the historical migration and atomicity
are unchanged, and both older fixtures are retained.

This is evidence maintenance only. The policy remains `prepared-inactive`;
the matcher still returns only `matched-diagnostic-inventory` and has no CI
admission adapter. The 2026-11-13 UTC expiry is unchanged. No scanner warning is
suppressed, reclassified or relabelled as success.

The approved secret-disposition union remains exactly 405, the 319-entry baseline and
26 Gitleaks fingerprints are unchanged, and the earlier 58-identity decision does not transfer
to new paths, fingerprints or whole-source bindings. Existing mismatches remain
blocking. Capture the actual scanner inventory before proposing any new finite
approval and corresponding negative tests; no blanket hash exception, expiry
extension or implied owner authorization is introduced here.

## Three source-bound Redis integration Ruff annotations

The owner explicitly approved this limited scope on 2026-10-30. Exactly three
line-level annotations are authorized in
`scripts/quality/run_owned_redis_contracts.py`:

- S603 on `subprocess.run` in `_command`: the resolved Docker executable, fixed
  argument structure, bounded transport timeout, and runtime marker value supplied
  through stdin, without a shell.
- S603 on `subprocess.run` in `main`: `sys.executable` with `-m pytest`,
  preserving the reviewed integration arguments and child environment, without
  a shell.
- S104 on the single `"0.0.0.0"` literal in `_inspect` that is compared with
  Docker inspect `HostIp` metadata. This site validates the existing service
  binding metadata; it does not create or configure a listener.

No additional or relocated annotation, broad or file-level suppression, Ruff
configuration change, or general S603/S104 exception is authorized. The earlier
coverage-worker grant remains separate and unchanged. Source-bound positive and
negative tests bind the exact subprocess calls and metadata comparison, including
their lexical function owners; extra, missing, moved, nested, broad, expanded-rule
and changed-call annotations must be rejected. Normal Ruff checks and
final-source hosted verification remain mandatory.

The two S603 annotations were initially published without this required separate
authorization. Independent review identified that mistake, and commit
`65254d0a5d58542d283a920d9b56e7e5be630e44` removed them to restore the strict gate.
Its own Actions run reported the two S603 sites and the S104 comparison as errors.
This later decision permits only the three reviewed sites above; it does not
retroactively make the earlier policy review complete.

The 319-entry detect-secrets baseline, 405 finite dispositions, 26 Gitleaks
fingerprints, required CI contexts, hooks and coverage floors remain unchanged.
No additional hash identity is admitted by this decision. The annotations and
scope tests establish neither Redis runtime acceptance nor full CI, release or
deployment readiness; those still require their own evidence.


## Eighty-nine exact public integrity dispositions (2026-10-30)

The owner explicitly approved the finite
[89-identity manifest](https://github.com/egorribun/university_ecosystem/blob/15349c991d5ef99098b452008f0f6813ba0b9561/docs/audits/evidence/security-digest-triage-2026-10-30.json)
on 2026-10-30. This is a separate decision, not a transfer of the earlier
58-identity approval. The ordered 405-record prefix and all of its metadata
remain unchanged; the approved union becomes **494** within the unchanged
512-record cap.

The actual [pre-commit scan](https://github.com/egorribun/university_ecosystem/actions/runs/41028695091/job/123972932796)
and [baseline-integrity check](https://github.com/egorribun/university_ecosystem/actions/runs/41028695091/job/123974070270)
reported the same 89 unmatched identities on source
`56ed5df3a31742730d9b3e8e7e2d9acc46182dd9`. Their actual PR checkout
`3ea36c26c2941f44260569d5870790582bbc1e89` has the identical complete Git tree
`97dbc7ffe58e6c24f3dcd20afdcc9260ae76fe16`. Each reported public literal was
checked against its immutable source blob and detector fingerprint. The seven
source blobs remain identical in the test-only successor `34ebe406`.

All additions use category `public_integrity_digest`, detector
`Hex High Entropy String`, owner `egorribun`, review date 2026-10-30 and the
unchanged expiry **2027-01-10**. The manifest contains:

- four identities in `quality/historical148-squawk-policy.json`;
- one in `scripts/quality/run_owned_redis_contracts.py`;
- two in `scripts/quality/validate_historical148_squawk.py`;
- 27 each in the retained `35aeedeb`, `36f70a0f` and `3d83fb27`
  historical148 capture fixtures;
- one in `tests/test_aud427_428_contract_quality.py`.

These are 37 Git source identities, 39 SQL digests, six trace-source digests,
three Squawk binary checksums, two compiled canonical-document digests and two
Redis OCI digests. They are public integrity values, not credentials.
The authorization covers only the manifest's exact path/type/digest tuples
and reviewed source bindings. Diagnostic line numbers are not identities;
an unrelated path, changed value or unapproved additional finding does not
inherit this decision.

Source-bound positive and negative controls must preserve the exact old prefix
and metadata, require the complete approved addition, reject modified source
bindings and altered path/type/digest/category/owner/expiry, and reject
duplicates, wildcard or extra identities and untrusted candidate expansion.
The old historical-58 reconstruction and no-transfer controls remain required.
Approval does not establish final-source scanner or test success.

The 319-identity detect-secrets baseline is unchanged. Its separately reported
20 stale identities are informational, are not part of this grant and are not
removed. The 26 Gitleaks fingerprints, scanner rules, expiry caps, required
contexts, hooks, blocking CodeQL and coverage floors also remain unchanged.
No baseline addition, inline secret pragma, broad hash exclusion or automatic
approval is authorized.

This decision does not activate the prepared Squawk recognizer, suppress its
37 raw warnings, accept migration execution risks, alter migration bytes or
authorize deployment. The historical148 preparation's 2026-11-13 expiry is
separate and unchanged. No audit finding is accepted by this policy update.


## AUD-447 owned CI allocation: five-identity disposition — 2026-10-31

The owner approved exactly five public test identities at 17:29 UTC and
explicitly approved publication of the complete policy artifact at 17:39 UTC.
This is a finite, source-bound extension of the existing
`ci_test_contract_sentinel` category, not a path-wide or detector-wide allowance.

| Source path | Detector | Diagnostic line | Public purpose |
| --- | --- | ---: | --- |
| tests/integration/test_aud447_dlq_auth_scrub_postgres.py | Secret Keyword | 98 | Exact password equality before connecting to the owned loopback CI service |
| tests/test_aud447_dlq_auth_scrub_migration.py | Basic Auth Credentials | 290 | Owned disposable allocation positive and rejection controls |
| tests/test_aud447_dlq_auth_scrub_migration.py | Basic Auth Credentials | 350 | Wrong-password negative control, rejected before engine creation |
| tests/test_quality_workflow_contract.py | Basic Auth Credentials | 7465 | Source-only contract for the step-local owned service URL |
| tests/test_quality_workflow_contract.py | Secret Keyword | 7479 | Source-only contract for disposable PostgreSQL service metadata |

Line numbers describe the reviewed source; they are not the identity key.
Identity is the exact path, detector and digest. The pinned detect-secrets
detectors derive these from the public test values, not credentials from an
environment or deployed database. Tests independently reconstruct each digest
from the reviewed literal and pin all three source blobs plus the workflow.
The recovered raw-regex postimage is part of that source binding.

The policy grows **494 → 499** records. All previous 494 records, metadata and
order remain unchanged and are covered by a canonical-prefix checksum.
The five new records require the exact evidence text, owner `egorribun`,
review date **2026-10-31**, approved status and expiry **2027-01-10**.
The validator rejects changed paths, detectors, digests, categories, evidence,
owners, dates, wildcards, duplicates and a sixth identity. The two previously
approved Hex identities in the shared quality-contract file remain valid only
under their exact prior identities and category. Historical 405-prefix and
89-record controls retain their own review date and bounded population.

Negative controls exercise the actual validator, source changes/transplants,
append-only population, expiry, trusted-base versus owner-authored candidate
loading and unchanged cap. Candidate-only additions do not acquire trusted-base
authorization. No generic category path/type pair is added.

The record limit remains **512**, artifact byte cap **512 KiB**, baseline
**315** identities and Gitleaks **26** fingerprints. The scanner's separately
reported 20 stale baseline identities and 418 active matches on the preceding
source are observations, not this policy's record count, and are not modified
or extrapolated. Scanner settings, trust boundaries, required contexts,
coverage thresholds and existing blocking gates remain unchanged.

This decision authorizes neither production database access nor migration
execution, deployment, new credentials, additional identities, inline pragmas
or a Squawk exception. It accepts no audit finding. Hosted execution on the
new source must independently confirm scanner and contract success; a reviewed
policy or a prior-source PASS does not supply that evidence.


## 2026-11-01: finite three-entry v4 workflow-binding refresh

The owner approved a conditional, two-stage update on 2026-11-01: publish
only the three reviewed fixture fields first, then add their exact dispositions
only if the actual repository scan reports exactly the expected three findings.
Any additional or ambiguous finding stops that admission step.

The source-only stage was published in
[e71d06a3](https://github.com/egorribun/university_ecosystem/commit/e71d06a380ab5a478ae2df4d8832f5c758e80998).
The dedicated [scanner job 124805024868](https://github.com/egorribun/university_ecosystem/actions/runs/41291740905/job/124805024868)
reported exactly three new findings and no extras. The same result was repeated
after the separate metadata/test changes in
[b543fc02](https://github.com/egorribun/university_ecosystem/commit/b543fc0235fed27468b162519b5f36917d450e5b),
in [scanner job 124820361602](https://github.com/egorribun/university_ecosystem/actions/runs/41296936313/job/124820361602).
Both actual PR checkouts have the exact full tree of their respective branch
heads. The fixture bytes, pinned scanner requirements and scan configuration
are identical across those two sources.

All three rows use detector **Hex High Entropy String** and the exact path
`tests/fixtures/full-backend-reusable-baseline.v4.yaml`:

| Observed line | Exact field | Category |
| --- | --- | --- |
| 8 | source_files.nightly | public_integrity_digest |
| 10 | source_files.reusable_full_backend_mutation | public_integrity_digest |
| 15 | nightly_preserved_jobs.frontend-mutation-shards | independent_contract_fingerprint |

The workflow digests bind the reviewed nightly recovery changes and the
reusable workflow's existing checkout hardening. The fingerprint binds only
the reviewed frontend-mutation-shards job. Other fixture fields, historical
identities and validation predicates remain unchanged.

The scanner logs expose path, line and detector, not the detector's digest.
The three identities are therefore explicitly **DERIVED**, not exported:
each observed line has one unambiguous public scalar; the installed
detect-secrets 1.5.0 / PyYAML 6.0.3 pipeline preserves that scalar, and the pinned
official implementation hashes its UTF-8 value with SHA-1. Independent review
checked the full mapping against the actual source and scan configuration.
See the pinned
[YAML transformer](https://github.com/Yelp/detect-secrets/blob/01886c8a910c64595c47f186ca1ffc0b77fa5458/detect_secrets/transformers/yaml.py),
[Hex detector](https://github.com/Yelp/detect-secrets/blob/01886c8a910c64595c47f186ca1ffc0b77fa5458/detect_secrets/plugins/high_entropy_strings.py)
and [identity hashing](https://github.com/Yelp/detect-secrets/blob/01886c8a910c64595c47f186ca1ffc0b77fa5458/detect_secrets/core/potential_secret.py).
No new raw-scan export, scanner exclusion or inline pragma is introduced.

This source change appends exactly **three** records: **499 → 502**.
The previous 499 records retain their bytes, order, categories, evidence,
owners and individual expiry dates. Their canonical 494-record prefix and
the subsequent exact five AUD-447 records remain independently checked;
no historical record is retired, renewed or replaced.

The new records require the exact evidence text, owner `egorribun`, review
date **2026-11-01**, approved status and expiry **2027-01-10**. The v4 fixture
is restricted to 45 exact identity/category pairs: the prior 42 and these
three. Only the three new digests are reserved globally against transplantation.
The 25 previously approved off-fixture collision records remain admitted
unchanged; historical metadata is not rewritten.

The published tests-first contract produced **24 semantic failures** against
the old validator: two rejected exact new fingerprint admissions, 21 accepted
scope/metadata mutations and one accepted unknown fourth fixture identity.
The other 33 new cases passed by complete containing-cohort inference, not a
named PASS list. The policy cohort was **806 PASS / 24 FAIL**, without setup
or collection errors. Those RED receipts justify the narrow guard correction;
they do not establish success of this new implementation.

Negative controls cover changed identities/categories/approval metadata,
new-digest transplantation, unknown fourth identities, duplicates, the
unchanged cap, append-only ordered population, expiry and trusted-base versus
owner-authored candidate loading. Historical date cohorts retain their prior
bounded populations. The complete current policy is tested on 2026-11-01;
older records with earlier individual expiry dates are not silently extended.

The record cap remains **512**, artifact byte cap **512 KiB**, baseline
**315** identities and Gitleaks **26** fingerprints. The separate 20 stale
baseline findings are unchanged. No SQL capture, migration-148 source pin,
Squawk admission, dependency/license allowance, CI threshold, required context,
deployment or production-database authority is included. The audit registry
remains **442/512**. This change requires its own scanner and contract receipts;
neither earlier scans nor source review establishes a GREEN final source.

## Owner decision 2026-10-31: finite historical-148 Squawk admission activated

The owner activated one finite Squawk admission for the unchanged historical revision `148642dd1207` (parent `f7aa476e968a`) in the Alembic job. It admits only the exact 37-finding diagnostic inventory in [quality/historical148-squawk-policy.json](https://github.com/egorribun/university_ecosystem/blob/3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9/quality/historical148-squawk-policy.json): 13 `ordinary-parent-live` and 24 `expanded-populated-diagnostic` findings. Matching is exact by scenario SQL digest, rule and location. The scanner pins and the seven ordered `--exclude` arguments are unchanged.

- Scope: creation of a new empty MVP database only (`execution_scope: new-empty-mvp-only`). Populated upgrades are not admitted.
- Expiry: `2026-11-13T00:00:00Z`, read from the real UTC clock by `scripts/quality/historical148_squawk_admission.py`, which accepts no caller clock. Extension or widening requires a new owner decision.
- Mechanism: the `Historical 148642dd1207 ordinary Squawk admission input` step renders the unchanged revision and records its raw exits and JSON run. The evidence step binds the migration by `git hash-object` of the working-tree file and fails unless both raw exits are `1`, both JSON runs exit `1` with empty stderr, and each scenario's warning multiset equals the policy exactly. A new, changed, missing, duplicate or extra warning fails, as do a changed SQL digest, migration object, scanner digest, version or argument list, and an expired policy. Changed migrations keep the fatal raw gate.
- Raw visibility: the raw Squawk output and exit codes stay in the logs. A raw failure is never converted into scanner success.
- Policy pins: `status` becomes `owner-activated-finite`, and an `activation` record is appended after the existing keys, so no existing line reference moves. The `alembic/env.py` provenance pin is rebound to the reviewed AUD-434 blob `ac2f50a2…` (was `e8d54326…`). The immutable 3d83fb27 capture is unchanged. The validator's compiled `_POLICY_SHA256` is rebound to `1c43d246…` (was `8df4a533…`).
- Disposition rebinds (owner decision 2026-10-31; one-to-one, same path and type, no identity added): record 351 (`quality/historical148-squawk-policy.json`, env.py pin, `e8d54326…` → `ac2f50a2…`); record 376 (`scripts/quality/validate_historical148_squawk.py`, historical-148 policy fingerprint, `cbf0c9d7…` → `00fb9655…`, which changes because the historical reconstruction hashes the activated policy bytes with only the recapture fields restored); and record 410 (`scripts/quality/validate_historical148_squawk.py`, compiled policy fingerprint, `8df4a533…` → `1c43d246…`). The disposition count stays **502**. Evidence text and line references are unchanged.
- Verifier and contract pins: the historical-148 and October-30 identity tables, the pinned policy and validator blobs, the October-30 405-record and AUD-447 494-record prefix digests, and the single exact env.py difference allowed against the 3d83fb27 capture are updated for exactly these rebinds. The migration workflow contracts expect the admission verdict as the final decision and the unchanged-148 input step as the source of the ordinary outputs; the squawk shell harness again exercises the admission stub, with collector failures first. All negative tests are kept.
- Limits: this is not scanner success, deployment or merge approval, populated-database admission, or a suppression of the 37 raw findings. It does not accept AUD-327, AUD-348 or AUD-433. Any change to `148642dd1207`, to its rendered SQL, or to a pinned scanner input needs a new source-bound capture and a new owner decision.


## Ten obsolete test baseline identities retired (2026-11-01)

The owner approved only the ten obsolete `Secret Keyword` identities below,
eight existing-record line-number updates, and the scan timestamp.
The detect-secrets baseline changes **315 → 305**. This removes obsolete
exceptions after the password-fixture repairs; it adds no finding, disposition,
pragma, wildcard, category change, automatic approval, or scanner bypass.

The [own ac6 hook output](https://github.com/egorribun/university_ecosystem/actions/runs/41340638481/job/124949683580)
contains the actual postimage with `generated_at = 2026-11-01T19:20:23Z`.
It matches the earlier own-bcac postimage except for that timestamp.
The approved source-bound retired population is:

| Existing baseline path | Retired recorded lines | Detector |
| --- | --- | --- |
| `tests/test_notifications_api.py` | 43, 175 | Secret Keyword |
| `tests/test_notifications_service.py` | 619 | Secret Keyword |
| `tests/test_sessions_api.py` | 213, 291, 423, 451 | Secret Keyword |
| `tests/test_notifications_localization.py` | 22 | Secret Keyword |
| `tests/test_missing_logic_v5.py` | 52 | Secret Keyword |
| `tests/test_auth_security.py` | 76 | Secret Keyword |

These rows identify the ten existing path/type/digest tuples removed by the
reviewed baseline diff, not permission to remove another finding at those paths.
The eight retained-identity moves are `tests/test_auth_security.py`
367→78, 196→208, 207→219, 224→236, 247→259, 264→276, 309→321, and
`tests/test_notifications_api.py` 108→43. Their digests, detector types and
`is_secret` statuses are unchanged. Empty result keys disappear only for
notifications_service, notifications_localization and missing_logic_v5; no
remaining result is discarded.

All **305** retained identities and their classification/status fields are
preserved apart from those eight line numbers. The separately reported **20**
older stale identities are retained for separate review; this decision does not
retire them. Scanner plugins, filters and version remain unchanged.
The disposition policy stays **502**, its cap **512**, and existing individual
expiries (including 2027-01-10) are not extended. Gitleaks stays **26**.
The historical policy-prefix counts of 315 in verifier tests are not this
baseline cardinality and must not be rewritten as 305.

The audit register stays **449 accepted / 63 open**. Historical 315/319 scan
receipts remain dated evidence, not claims about the new baseline.
The final published source still needs its own scan and required checks;
retirement approval and a reconstructed postimage do not establish full CI,
coverage, deployment readiness, or acceptance of another finding.


## Owner decision 2026-11-02: two exact public integrity dispositions

The owner approved exactly two append-only `public_integrity_digest`
identities of detector type `Hex High Entropy String`: the public pre-squash
commit in `tests/integration/test_mvp_baseline_schema_equivalence.py` and
the official slsa-verifier v2.7.1 linux-amd64 attestation checksum in
`tests/test_aud378_slsa_provenance_attestation.py`. The exact path/type/digest
triples and provenance are authoritative in the two appended policy records.
The unchanged 502-record prefix becomes 504 records; the cap remains 512.

Owner `egorribun` approved this scope on 2026-11-02. Both new records use
`expires_on: 2027-01-09`, because the existing schema includes that date:
they are rejected on and after 2027-01-10. No older record is extended.
The validator reserves these exact paths and digest bytes, checks the exact
metadata and evidence, and retains fail-closed mutation and expiry tests.

The baseline remains 304 identities. Only scanner-produced timestamp or
line-number metadata may be refreshed; no identity, triage status, plugin,
filter, pragma, wildcard, or category is added to the baseline. These two
identities were derived using the pinned detect-secrets 1.5.0 SHA-1 algorithm,
not exported from the scanner. The second value is the attestation checksum,
not the verifier executable checksum. Gitleaks fingerprints and all other
exceptions are separate. Approval and source review are not scanner success,
audit acceptance, full CI, merge, deployment, or production-database authority.


## One exact historical public test-password hash fingerprint, 2026-11-01

Owner `egorribun` approved exactly one additional Gitleaks fingerprint on
2026-11-01 at 20:51:36 UTC:
`3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9:.secrets.baseline:generic-api-key:1820`.
The historical baseline line stores the SHA-1 digest of the public password
fixture in `tests/test_auth_security.py:78` at that commit, not a newly introduced
credential. The historical baseline and test blobs are respectively
`25f7a8b881d1277103010320cfe925663279578b` and
`d5a5f31448930f5abf1692632ad58d245b4745ca`.
[Gitleaks on source e6bbbb5](https://github.com/egorribun/university_ecosystem/actions/runs/41428407935/job/125220561352)
reported exactly this one `generic-api-key` identity with scanner exit 2.

The exact inventory grows **26 to 27**, preserving all previous fingerprints.
The current detect-secrets baseline stays **304** identities and its separate
policy stays **504** dispositions; the older 305/502 approval-context counts
are historical, not restored. No other commit, path, rule, line, hash copy,
pattern, expiry, scanner setting, required context, hook or threshold is approved
by this decision. Changed and unmatched findings remain blocking.
The audit ledger stays **449 accepted / 63 open out of 512**. This disposition
is not audit acceptance, scanner success, full CI or release evidence; the
published source still requires its own scans and required hosted checks.


### One exact reviewed workflow-commit disposition (2026-11-02)

The owner approved one additional public-integrity disposition for the reviewed
workflow-source commit in `tests/test_verify_secrets_baseline.py`, field
`_REVIEWED_SOURCE_COMMIT_OVERRIDES`, for
`.github/workflows/reusable-backend-tests.yml`. The referenced
[public Dependabot commit](https://github.com/egorribun/university_ecosystem/commit/e77defff9ddf944793bc7107fa6b5df9e2f7903a)
records the previously reviewed setup-python update; it is not credential material.

Only that exact path, `Hex High Entropy String` detector, digest, evidence and
approval metadata are accepted. The owner is `egorribun`, reviewed on
`2026-11-02`; the existing inclusive date schema stores `2027-01-09`, so the
approval is inactive from `2027-01-10`. There is no expiry extension, wildcard,
inline pragma, category change or automatic approval.

The original 504 records remain unchanged and in order; this appends one record
for an approval-checkpoint total of **505** under the unchanged cap **512**. Baseline **304**,
Gitleaks **27**, all 78 required CI context/app pairs and all quality thresholds
are unchanged. The three older dispositions on the same test path retain their
own identities, categories, evidence and expiry dates. Exact prefix, source-value,
scope-mutation and expiry-boundary controls cover this addition. These source
contracts do not claim a hosted scan or required-check pass and add no accepted
audit finding.


## Retired migration-source dispositions after ADR-051 (2026-11-02)

The owner authorized removal of dispositions whose source files were removed by
ADR-051. At this retirement checkpoint the policy contained **349** exact identities: **505 − 156**.
The separately approved workflow commit identity remains present. Every surviving
record, including its category, evidence, owner and expiry, retains its original
value and relative order. Baseline **304**, Gitleaks **27**, the **78** required
context/app pairs, the cap **512**, hooks and coverage floors are unchanged.

The retirement is finite and source-specific:

| Removed source path                                                          | Records |
| ---------------------------------------------------------------------------- | ------: |
| `quality/historical148-squawk-policy.json`                                   |      33 |
| `scripts/quality/validate_historical148_squawk.py`                           |       4 |
| `tests/fixtures/historical148-squawk-capture-15eaaa.json`                    |      27 |
| `tests/fixtures/historical148-squawk-capture-35aeedeb.json`                  |      27 |
| `tests/fixtures/historical148-squawk-capture-36f70a0f.json`                  |      27 |
| `tests/fixtures/historical148-squawk-capture-3d83fb27.json`                  |      27 |
| `tests/helpers/migration_148642dd1207_trace.py`                              |       5 |
| `tests/integration/test_aud350_stored_event_timestamp_migration.py`          |       1 |
| `tests/integration/test_aud447_dlq_auth_scrub_postgres.py`                   |       1 |
| `tests/integration/test_historical_attendance_sender_migrations_postgres.py` |       1 |
| `tests/integration/test_migration_148642dd1207.py`                           |       1 |
| `tests/test_aud447_dlq_auth_scrub_migration.py`                              |       2 |

The old Squawk policy, recognizer and admission wrapper are removed; the earlier
148 admission and its November 13 expiry are historical evidence, not an active
exception. Current raw Squawk failures remain blocking, with the same pinned
scanner and seven ordered exclusions. Recreating any retired path does not
reactivate its approval. Candidate policy loading rejects all twelve retired
paths; trusted pre-retirement policies are fully validated before those exact
paths are omitted from the active matching set. No missing-file wildcard or
filesystem-driven exemption is introduced.

Historical prefix/approval regressions read the immutable 504-record Git blob
and the independently pinned subsequent one-record approval. Separate live
inventory and loader regressions reject a restored retired record, altered or
missing survivors, unrelated paths, changed expiry and reordered rows. Historical
records remain provenance, not scanner matching authority. Source/data review
alone is not hosted validation, schema-equivalence proof, or audit acceptance;
final-source scanner, coverage and required-check evidence remains necessary.


## Exact internal HTTP mTLS chart references (2026-11-02)

The owner explicitly approved these three additions on 2026-11-02 at 15:15 UTC
in response to the exact three-path/type/value question.

The three owner-reviewed Secret Keyword identities in the two
`charts/university-ecosystem/values*.yaml` files are public Kubernetes Secret
object/key references, not credential material: the staging backend Secret
object name and the `tls.key` key name in each file. Matching uses each exact
path, type and digest; this description grants no filename wildcard exemption.
The existing `external_kubernetes_secret_reference` category is retained.
At that approval checkpoint the policy contained **352** identities: the unchanged, ordered **349** survivors
plus exactly these **3** records. Their owner is `egorribun`, reviewed on
2026-11-02, with inclusive `expires_on: 2027-01-09`, so they cannot match on
or after 2027-01-10. No earlier record is reclassified or extended.
Baseline **304**, Gitleaks **27**, the **449/512** audit ledger, all **78** required
context/app pairs, hooks and coverage floors remain unchanged. No inline
allowlist comment is added. Source/data review is not a passing hosted scan,
test execution, audit acceptance or release approval.


## Deleted-source baseline retirement (2026-11-02)

Under the owner's existing permission to remove entries whose source file was
deleted, the baseline retires exactly **62 identities across 47 deleted paths**
from the 304-identity checkpoint, leaving **242**. This is deletion-only:
all retained records, relative ordering, line numbers, classifications, detector
settings, filters, version and generated timestamp are unchanged. The timestamp
remains the previous scanner timestamp; this edit is not a fresh scan result.

The exact deletion commits are:

- [Skill-mirror removal](https://github.com/egorribun/university_ecosystem/commit/a4d5ad402e4e9509a2812edafc868f988403fba0): 19 identities across 13 paths.
- [Dead logging-test removal](https://github.com/egorribun/university_ecosystem/commit/b16a40c2b316522841108615d602573b854d1008): one identity in one path.
- [ADR-051 migration squash](https://github.com/egorribun/university_ecosystem/commit/2eb51a77e683896f6138c1fd237370c7edd434ab): 42 identities across 33 paths.

For every path, its blob exists in the deletion commit's parent tree, is absent
from that commit's tree, and remains absent at the cdc64d3 checkpoint. These are
repository deletions, not assumptions about ignored or local-only files.
The earlier decision retaining 20 older stale entries remains historical; this
separate review now establishes their deletion together with the 42 migration
entries. Restoration of a source file is not covered by its retired baseline
entry. New or changed findings remain blocking under the existing verifier.

| Deleted source path | Retired identities |
| --- | ---: |
| `.opencode/skills/api-design-principles/references/rest-best-practices.md` | 1 |
| `.opencode/skills/api-endpoint-builder/SKILL.md` | 2 |
| `.opencode/skills/api-security-best-practices/SKILL.md` | 1 |
| `.opencode/skills/fastapi-templates/resources/implementation-playbook.md` | 1 |
| `.opencode/skills/javascript-testing-patterns/resources/implementation-playbook.md` | 3 |
| `.opencode/skills/k6-load-testing/SKILL.md` | 1 |
| `.opencode/skills/pci-compliance/SKILL.md` | 1 |
| `.opencode/skills/playwright-skill/API_REFERENCE.md` | 2 |
| `.opencode/skills/postgres-best-practices/rules/security-privileges.md` | 1 |
| `.opencode/skills/python-testing-patterns/resources/implementation-playbook.md` | 2 |
| `.opencode/skills/secrets-management/SKILL.md` | 1 |
| `.opencode/skills/security-scanning-security-sast/SKILL.md` | 1 |
| `.opencode/skills/sql-injection-testing/SKILL.md` | 2 |
| `alembic/versions/1b15294cc8d7_add_pgvector_embeddings.py` | 2 |
| `alembic/versions/202501200001_add_english_fields_to_events.py` | 1 |
| `alembic/versions/202601130001_add_performance_indexes.py` | 1 |
| `alembic/versions/202601260001_add_outbox_columns_to_stored_events.py` | 1 |
| `alembic/versions/202602270001_merge_heads.py` | 1 |
| `alembic/versions/2956fd6376cc_fix_groups_id_sequence.py` | 1 |
| `alembic/versions/2bc18c38157c_add_department_and_position_to_user.py` | 1 |
| `alembic/versions/2e93eecad1e0_add_role_constraints.py` | 1 |
| `alembic/versions/306c0a36d925_merge_heads.py` | 2 |
| `alembic/versions/3081a2b724cc_create_dead_letter_jobs_table.py` | 2 |
| `alembic/versions/30fa2627aa5e_add_lesson_type_to_schedule.py` | 1 |
| `alembic/versions/31e81f57c53d_add_signature_to_data_access_logs.py` | 2 |
| `alembic/versions/3f1cf9168805_decompose_user_model.py` | 1 |
| `alembic/versions/4e39503c07cd_add_outbox_notification_trigger.py` | 2 |
| `alembic/versions/57bdf5bf9375_resolve_role_case_mismatch_and_drop_.py` | 1 |
| `alembic/versions/65319a2b1d7f_add_english_fields_to_news.py` | 1 |
| `alembic/versions/6a898bba5589_implement_partitioning.py` | 1 |
| `alembic/versions/6bdc356a128b_add_is_used_to_invite_codes.py` | 2 |
| `alembic/versions/7db0b7a03e37_add_speaker_and_photo_url_to_events.py` | 1 |
| `alembic/versions/933372f5da9a_init_schema.py` | 1 |
| `alembic/versions/96809b6dc35d_add_chat_models.py` | 2 |
| `alembic/versions/a4bfc1ba3076_add_invite_codes_table.py` | 1 |
| `alembic/versions/ab93b27831f3_add_webauthn_support_v2.py` | 1 |
| `alembic/versions/b85f4f3edc89_add_attachments.py` | 1 |
| `alembic/versions/bd67902ca2cd_emove_author_from_news_add_image_url.py` | 1 |
| `alembic/versions/c8d0b5515f2d_add_schedule_and_news_indexes.py` | 1 |
| `alembic/versions/d0b0cb4c1910_merge_data_access_logs_head.py` | 1 |
| `alembic/versions/db31ef5d7ea4_add_trusted_devices.py` | 1 |
| `alembic/versions/ede66395ff71_merge_chat_message_index_and_.py` | 1 |
| `alembic/versions/f2d2414a6b67_add_functional_email_index.py` | 1 |
| `alembic/versions/f9d2b1f5e2d0_create_push_subscriptions_table.py` | 2 |
| `alembic/versions/ffe470bc9ca2_merge_quiet_hours_push_subscriptions.py` | 2 |
| `alembic/versions/fix_sender_id_type.py` | 1 |
| `tests/test_logging_utils.py` | 1 |

At that deleted-source checkpoint the separate disposition policy stayed **352**, Gitleaks stays **27**, the audit
ledger stays **449 accepted / 63 open**, and all **78** required context/app pairs,
hooks, coverage floors and expiry dates remain unchanged. No new baseline
identity, disposition, inline suppression or exception is added. Dated304,
305,315 and319 receipts above remain historical evidence rather than current
inventory claims. Final-source scanner and hosted checks remain required; this
retirement does not add audit acceptance or establish a passing scan.

**Coordinate refresh (2026-11-02).** Commit `b8c94de9c` refreshes five detect-secrets `line_number` coordinates in three paths: `.github/workflows/reusable-backend-tests.yml` (398 to 437 and 408 to 447), `charts/university-ecosystem/values.yaml` (619 to 613 and 620 to 614) and `tests/test_middleware_setup_contract_closure.py` (106 to 107). It also sets `generated_at` to `2026-11-02T19:44:09Z`. The 242 path/type/digest identities and their verified flags are unchanged, checked record by record against the parent commit. This is a coordinate refresh, not an identity change; it adds no baseline identity or disposition.

## SPIFFE backend reference retirement (2026-11-02)

The owner approved the exact single-record retirement at 17:59:51 UTC, replying
to the 17:02:30 UTC question about removing the unused staging backend Secret
reference with the SPIFFE transition. This approval does not authorize additional
records, runtime execution, deployment, bypasses or changed scanner scope.

Together with removal of `university-internal-http-backend-server` from
`charts/university-ecosystem/values-staging.yaml`, retire its one exact Secret
Keyword disposition, whose exact identity bytes remain in the rejection test.
The current policy contains **351** identities. All remaining records retain
their exact contents and relative order, owners, categories and expiry dates.
Both `tls.key` approvals remain: each chart values file still contains the key
reference for the gateway client and file-processor server gRPC consumers.
The original three-record approval above is historical, not an active grant
for the removed backend field. Reintroduction requires fresh owner approval.

Baseline **242**, Gitleaks **27**, audit **449/512** with **63** open, all **78**
required context/app pairs, hooks and coverage floors remain unchanged. This
retirement must not be integrated independently of the source-field removal.
Static source/data checks are not runtime validation or hosted-check acceptance.


### 2026-11-02: Node action coverage component (source proposal; acceptance pending)

Add the node-actions coverage component for repository-authored runtime source under .github/actions/dependency-review-capture. Initially the production inventory is exactly capture.cjs and index.cjs; both are explicitly Tier 0 and owned by @egorribun. The test harness is test infrastructure, not a runtime source exclusion. Additional .js/.cjs/.mjs runtime files become inventory requirements rather than silently disappearing.

Every file and aggregate must satisfy 100% lines, statements, branches and functions. Missing files, skipped counters, malformed reports, unsupported metrics or inconsistent LCOV/Istanbul counters block. No rounded display value substitutes for exact integer equality. The entire measured source is held at 100%, which also covers changed executable units; existing patch policy and source binding are retained.

Use Node24 native V8 collection for capture.cjs and index.cjs with enforced line/branch/function thresholds, plus existing frontend-lock AST conversion for real statement counters. ast-v8-to-istanbul 1.0.7 and Babel parser 8.0.8 convert the same collected V8 evidence; @bcoe/v8-coverage 1.0.2 merges processes. Existing locked Istanbul tools emit LCOV and JSON. No new package or invented integrity pin, ignore directive, floor reduction or new mandatory context is introduced.

## Pinned Dependency Review upstream object identities (2026-11-02)

The owner `egorribun` approved, in chat on 2026-11-02 (about 22:30 UTC), exactly
ten new `public_integrity_digest` identities of detector type
`Hex High Entropy String`. Each is a public immutable Git object id of the pinned
upstream `actions/dependency-review-action` at commit
`a1d282b36b6f3519aa1f3fc636f609c47dddb294` (v5.0.0, abbreviated `a1d282b3`).
They are appended after the final policy record with `approval_status: approved`,
`reviewed_on: 2026-11-02` and `expires_on: 2027-01-10` (69 days, within the
90-day cap). The evidence of each names the exact file and line and the object
kind, and records that the owner approved exactly these ten identities on
2026-11-02; not credential material.

| Path:line | Object kind | Object id |
| --- | --- | --- |
| `.github/actions/dependency-review-capture/capture.cjs:11` | commit | `a1d282b3…` (upstream commit) |
| `.github/actions/dependency-review-capture/capture.cjs:13` | blob | `cdfebd4e…` (`LICENSE`) |
| `.github/actions/dependency-review-capture/capture.cjs:14` | blob | `5f6cf73d…` (`action.yml`) |
| `.github/actions/dependency-review-capture/capture.cjs:15` | blob | `2da57a50…` (`dist/index.js`) |
| `.github/actions/dependency-review-capture/capture.cjs:16` | blob | `87e80840…` (`dist/index.js.map`) |
| `.github/actions/dependency-review-capture/capture.cjs:17` | blob | `8f8164bf…` (`dist/licenses.txt`) |
| `.github/actions/dependency-review-capture/capture.cjs:18` | blob | `cb1fb136…` (`dist/sourcemap-register.js`) |
| `.github/actions/dependency-review-capture/capture.cjs:19` | blob | `e5e5ca95…` (`package.json`) |
| `.github/actions/node-actions-coverage/action.yml:21` | commit | `a1d282b3…` (checkout ref) |
| `.github/workflows/dependency-review.yml:25` | commit | `a1d282b3…` (`DEPENDENCY_REVIEW_ACTION_REF`) |

No other identity is added. The 351-record prefix is unchanged, the disposition
total becomes **361**, and the cap remains 512. Baseline **242** and Gitleaks
**27** are unchanged. The verifier gains no frozen identity set and no constant
change for these paths; the validator accepts them through the generic
`public_integrity_digest` rule. The 2026-11-02 Helm chart records keep their
existing evidence and line references.

This is a finite disposition scope, not scanner success, audit acceptance, full
CI, merge, deployment or a required-check result.

## Single producer, ordinary same-run trust
The composite helper .github/actions/node-actions-coverage/action.yml runs identical tests and canonical provenance in two existing jobs:
1. Dependency Review / Review Dependencies: existing PR event scope remains unchanged. The artifact is diagnostic for that workflow; original vulnerability/license evaluation and always-run exact-row guard remain.
2. CI / Coverage & Quality Policy Gate: producer runs before the existing same-run selector. It emits an ordinary attempt-suffixed artifact, selected/downloaded/verified using existing same-run provenance. No new job, cross-workflow selector, receipt schema, event expansion or permission is required.

The actual tested runtime is the GitHub runner Node executable used by the local action. Record its process.version from the source snapshot as node-actions-node; do not misattribute setup-node's PATH executable or conflict with frontend's separate node version.

The central manifest registers node-actions additively. Reuse existing LCOV/Istanbul parser and merge checks with component identity preserved; do not label these files as frontend or unsupported workflow source. Canonical quality evidence retains reports, producer receipt and source snapshot.

## Trust and failure behavior
Tests snapshot source/control bytes before runtime imports. Existing provenance binds checkout commit and workflow/run/attempt, and existing normalizer HEAD/control checks now include .github/actions. Explicit per-file inventory prevents a missing entrypoint from yielding aggregate 100%. Same-run artifact selection rejects cross-run evidence; partial diagnostic uploads cannot satisfy successful producer/provenance requirements.

The capture adapter executes one immutable official bundle and preserves original nonzero exits. A successful coverage report does not turn a failed dependency review green. Snapshot captures are not independent same-UID isolation or proof against a compromised runner.


Validation remains pending: the capture suite, exact four-metric gates, central coverage/provenance/selector tests, actionlint, Zizmor, hooks and final-source hosted evidence must pass before acceptance. All 78 required context/app pairs and resource limits remain unchanged. Source integration is not evidence of a runtime pass.

## (2026-11-03) howett.net/plist license identification

**Status: approved by the owner (egorribun) on 2026-11-03** for exactly the scope below. The license identification is evidence-based.

Dependency Review on PR #1343 (run 41536117012, tested SHA `92d9cfed4`) fails the upstream license check for `services/caddy/go.mod » howett.net/plist@1.0.1`, reported as `LicenseRef-bad-bsd-2-clause-views-bsd-3-clause`. The same license failure appears in each checked run from `2eb51a77e` (2026-11-01) through `92d9cfed4`, so the license step had not passed for this graph in those runs.

Evidence: the upstream `LICENSE` at `https://proxy.golang.org/howett.net/plist/@v/v1.0.1.zip` (entry `howett.net/plist@v1.0.1/LICENSE`) contains two parts. The first is a two-clause BSD license with the FreeBSD-style disclaimer ("The views and conclusions contained in the software ... of the FreeBSD Project"), which corresponds to SPDX `BSD-2-Clause-Views`. The second, under "Parts of this package were made available under the license covering the Go language", is the Go license, which corresponds to SPDX `BSD-3-Clause`. Both are permissive. The marker is therefore an unmapped composite of permissive licenses, not a copyleft or incompatible license. `BSD-2-Clause-Views` is not in `allow-licenses`, and this change does not add it there.

Scope: `.github/dependency-review-config.yml` gains exactly one name-only `allow-dependencies-licenses` entry, `pkg:golang/howett.net/plist`. Because the pinned action ignores PURL versions, `scripts/quality/verify_dependency_review_scope.py` binds the exception to one exact row: `services/caddy/go.mod`, `howett.net/plist`, `1.0.1`, license `BSD-2-Clause-Views AND BSD-3-Clause` (the identity reported since the 2026-11-04 rebind below), and the name-only PURL is listed in `PURL_ADDITIONS`. Any other version, manifest, license or a versioned PURL fails closed. The verifier also binds the two other caddy rows the same way: `otlptracegrpc` 1.46.0 (`Apache-2.0 AND BSD-3-Clause`, which the action already accepts) and `klauspost/compress` 1.20.1. `services/caddy/go.mod` is now a verified manifest, and a manifest absent at the protected base requires every pin it declares to appear as a changed row.

Label rebind (2026-11-04): Dependency Review run 41828936659 (tested SHA `e2a322e34`) reports the same package, version, manifest and license text for `services/caddy/go.mod » howett.net/plist@1.0.1` as `BSD-2-Clause-Views AND BSD-3-Clause`, where the run above reported `LicenseRef-bad-bsd-2-clause-views-bsd-3-clause`. This is a 1:1 rebind of the reported identity only. The verifier's `PLIST_LICENSE` now carries the new label, and the exception scope is unchanged: same manifest, package, version, single PURL entry, and no other row or allow-list change. The 2026-11-03 owner approval covers this scope; the label change itself is not a new license decision.

No global allow-list entry, GHSA entry or go.mod/go.sum change is introduced by this note.

## Exact Caddy go-jose advisory extension (2026-11-03)

The owner approved adding GHSA-4w3g-jfj2-cw2q and GHSA-vvm8-gf78-28g4
beside GHSA-mgcc-cww5-fp2q. Each record remains restricted to
`github.com/go-jose/go-jose/v3` version `3.0.5` in `services/caddy/go.mod`,
owned by `egorribun`, and inactive on or after 2027-01-10. No expiry is extended.
The scoped verifier rejects other manifests, versions and packages; the global
Dependency Review action configuration is not sufficient authorization by itself.

The upstream advisories report no patched v3 release. This is explicit temporary
risk acceptance, not a finding of non-reachability or a clean scan. Final-source
hosted evidence remains mandatory.

- <https://github.com/advisories/GHSA-4w3g-jfj2-cw2q>
- <https://github.com/advisories/GHSA-vvm8-gf78-28g4>

The Caddy module also selects the official x/crypto pseudo-version identified as
fixed by [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932), directly in its
requirement rather than with a replacement. Upstream split the unmaintained
OpenPGP packages into a separate vulnerable module; this is not a repair to
OpenPGP. The Caddy graph must not reintroduce that separate module. Module
verification, readonly build and final-source vulnerability scanning remain
required before acceptance.

## Addendum 2026-11-04: AUD-245 path-scoped KSV misconfiguration exceptions

Owner decision (2026-11-04): every KSV misconfiguration exception in `.trivyignore.yaml` is scoped to the exact manifests it applies to, with a reason and an expiry of 2027-01-10. Rules that no longer fire are removed. The plain `.trivyignore` carries no KSV rule. Changes are tighten-only: no identity was added and no path was widened.

Trivy ignore entries match file paths only; Trivy 0.75.0 has no resource-level field for misconfiguration entries. Paths are exact file paths, with no globs.

Evidence: `aquasec/trivy:0.75.0` (the CI version) ran `trivy config --config security/trivy-university-config.yaml --skip-dirs charts/revocation-store,charts/university-ecosystem,charts/redis-compat` on the repository with no ignore file, to map where each rule fires. The local-only `mutants/` and `frontend/node_modules/` trees are excluded.

| Rule | Gate severity | Before | After (exact paths in `.trivyignore.yaml`) | Expiry |
| --- | --- | --- | --- | --- |
| KSV-0001 | MEDIUM | global (YAML and plain) | scoped to 19 Kyverno negative-test fixtures; plain entry removed | 2027-01-10 |
| KSV-0104 | MEDIUM | global (YAML) | scoped to 19 Kyverno negative-test fixtures | 2027-01-10 |
| KSV-0014 | HIGH | global (YAML and plain) | scoped to 19 Kyverno negative-test fixtures; plain entry removed | 2027-01-10 |
| KSV-0118 | HIGH | global (YAML and plain) | scoped to 18 Kyverno negative-test fixtures; plain entry removed | 2027-01-10 |
| KSV-0009 | HIGH | global (YAML and plain) | scoped to `k8s/spire/spire-agent.yaml` and two Kyverno fixtures (`disallow-host-access/host-access.yaml`, `ephemeral-container-subresource/resources.yaml`); plain entry removed | 2027-01-10 |
| KSV-0010 | HIGH | global (YAML and plain) | scoped to `k8s/spire/spire-agent.yaml` and `disallow-host-access/host-access.yaml`; plain entry removed | 2027-01-10 |
| KSV-0012 | MEDIUM | scoped to `k8s/spire/spire-agent.yaml` | unchanged | 2027-01-10 |
| KSV-0023 | MEDIUM | scoped to `k8s/spire/spire-agent.yaml` | unchanged | 2027-01-10 |
| KSV-0047 | HIGH | scoped to `k8s/spire/spire-rbac.yaml` | unchanged | 2027-01-10 |
| KSV-0008 | HIGH | scoped to `disallow-host-access/host-access.yaml` | unchanged path; expiry extended by owner instruction (2026-11-04) | 2027-01-10 |
| KSV-0024 | HIGH | scoped to `disallow-host-access/host-access.yaml` | unchanged path; expiry extended by owner instruction (2026-11-04) | 2027-01-10 |

Reasons: the SPIRE rules (KSV-0009, KSV-0010, KSV-0012, KSV-0023, KSV-0047) cover the documented SPIRE node-agent and RBAC architecture. The Kyverno rules (KSV-0001, KSV-0014, KSV-0104, KSV-0118) cover negative-test fixtures that intentionally violate a policy so the policy is shown to fire. KSV-0017 was removed earlier because no manifest triggers it.

Expiry: the owner decision of 2026-11-04 sets expiry 2027-01-10 for every path-scoped KSV entry. KSV-0008 and KSV-0024 (host-access fixture) were moved from 2026-11-22 to 2027-01-10 on the owner's direct instruction. `scripts/quality/validate_trivy_kyverno_fixture.py` now pins `EXPECTED_IGNORE_EXPIRY = 2027-01-10` and raises `MAX_IGNORE_DAYS` from 30 to 90 so the live-window check accepts that date. This is an expiry extension for those two fixture entries; it is recorded here as the owner decision.

Policy digest: `scripts/quality/validate_trivy_kyverno_fixture.py` pins `EXPECTED_IGNORE_POLICY_SHA256 = 6f245662816c8e99877d2d8b36567b6bfcffaeb479b4b3310ef5cb519499bf02` (previously `38cc6ca3...`). The 1:1 detect-secrets digest-identity rebind (same path, type and category, total count unchanged) is applied in `scripts/verify_secrets_baseline.py`, `quality/security-false-positive-dispositions.json` and the live NEW constant of `tests/test_verify_secrets_baseline.py`. The historical `4eef1ee1...` snapshot constant is unchanged. At this decision, the disposition record retained its existing `expires_on` of 2026-11-22.

Proof (local, Trivy 0.75.0 in Docker, container names `ue-r7-w3-*`):
- Repository with the new policy, CRITICAL,HIGH, CI-equivalent scope: 0 unignored findings outside the local-only `frontend/node_modules` tree (the same single DS-0002 finding that the previous policy also reports there).
- Probe (copies outside the scoped paths, same rules, with the new policy): `k8s/spire-elsewhere/spire-agent-probe.yaml` reports KSV-0009 and KSV-0010; `k8s/kyverno/tests/probe-outside/flagd-probe.yaml` reports KSV-0014 and KSV-0118. Positive controls at the scoped paths (`k8s/spire/spire-agent.yaml`, `restrict-image-registries/flagd-pod.yaml`) report nothing.

## Addendum 2026-11-04 UTC: two Trivy validator checksum dispositions

The owner separately confirmed renewing exactly two detect-secrets dispositions
in `quality/security-false-positive-dispositions.json`: the public fixture
checksum and the complete Trivy ignore-policy checksum in
`scripts/quality/validate_trivy_kyverno_fixture.py`. Both retain their exact
path, `Hex High Entropy String` detector type, digest identity,
`public_integrity_digest` category, evidence and owner. Their earlier expiry was
2026-11-22; after the source re-review on 2026-11-04 UTC, their `reviewed_on` is
2026-11-04 and their new `expires_on` is 2027-01-10. The disposition verifier
accepts the expiry date itself and fails closed on the following day.

The re-review checked that the fixture and complete policy bytes match the
validator's respective pinned SHA-256 constants and that each constant matches
its existing detect-secrets identity. This decision is separate from the KSV
misconfiguration exceptions above; those and their fixture preflight keep their
own expiry semantics. The disposition inventory remains at 361 identities, the
baseline remains at 242 identities and all 78 required context/app pairs remain
unchanged. No new finding, baseline entry, category change, wildcard, scanner
exclusion or bypass is approved. This policy decision does not establish a
passing scan or hosted check for any source SHA.

## Addendum 2026-11-04 UTC: Semgrep rules source pin

The owner separately approved exactly one `public_integrity_digest` disposition
for the `Hex High Entropy String` detected at the Semgrep rules checkout ref in
`.github/workflows/ci.yml`. The ref identifies a public commit in the upstream
`semgrep/semgrep-rules` repository, and its detect-secrets identity is derived
from the exact pinned ref. The record is owned by `egorribun`, reviewed on
2026-11-04 UTC and expires on 2027-01-10. This adds one identity to the
361-record inventory; it does not approve any other finding, rule exclusion,
baseline entry, category change or scanner bypass.

## Addendum 2026-11-04 UTC: SPIRE chart archive pin

In a separate decision, the owner approved exactly one
`public_integrity_digest` disposition for the `Hex High Entropy String` at the
SPIRE chart archive checksum in `scripts/kind/aud373_internal_mtls_proof.sh`.
The official SPIRE 0.30.4 release archive bytes fetched on 2026-11-04 UTC
matched that local SHA-256 pin; the proof verifies downloaded bytes against it
before use. The upstream release is mutable and this does not claim a signed
upstream checksum. The detect-secrets identity derives from the exact pin. The
record is owned by `egorribun`, reviewed on 2026-11-04 UTC and expires on
2027-01-10. This adds one identity after the Semgrep decision, for a total of
363. The 242-identity baseline, 27 Gitleaks fingerprints and 78 required
context/app pairs remain unchanged. These decisions do not establish passing
scans, tests or hosted checks for any source SHA.

## Addendum 2026-11-05 UTC - Gitleaks lockfile basename scope

Recorded 2026-11-05 UTC. Owner `egorribun` explicitly approved tightening
the three existing Gitleaks path expressions to `(^|/)uv[.]lock$`, `(^|/)package-lock[.]json$`
and `(^|/)go[.]sum$`. These repository-specific expressions match only those final path components
at any directory depth. They no longer match lookalike full paths such as
`app/goXsum.py`. The scanner continues to extend its existing defaults. Those
defaults can suppress other paths, including `app/notgo.sum`, and directory
scans also prune directories whose names match an allowlist. This decision
does not claim to eliminate those separate skips.

This decision adds no scanner exclusion, fingerprint, baseline entry,
disposition, reclassification or bypass. It preserves the 27 historical
Gitleaks fingerprints, the 242 baseline identities, the existing finite
disposition inventory, all 78 required context/app pairs, blocking CodeQL and
the hooks. Any newly exposed finding remains blocking under the existing
policy. Each published source SHA still requires its own scans, tests and
required hosted checks. This approval establishes no passing result.

## Addendum 2026-11-05 UTC: Temporal loopback internal frontend

The owner approved using Temporal's loopback `internal-frontend` for the
single-container system-client scanner. Bind `internal-frontend`, `history`,
`matching` and `worker` to `127.0.0.1`; use port `7236` for
`internal-frontend`, membership port `6936`, and `broadcastAddress: 127.0.0.1`.
The service set is `frontend,history,matching,worker,internal-frontend`.
Expose only the authenticated public `frontend` on port `7233`. This decision
does not require inter-node certificates. It approves this configuration and
network boundary; source integration, bootstrap behavior, tests and hosted
validation remain separate evidence.

## Addendum 2026-11-05 UTC: SQLMap retains both scan modes

The owner requires both SQLMap modes. The blocking anonymous scan covers the
entire OpenAPI surface, uses the flags from the
[reviewed `c3693dbed` workflow](https://github.com/egorribun/university_ecosystem/blob/c3693dbedda63ec89c18fa51ede7e90fb25e2aaf/.github/workflows/sqlmap.yml),
and fails on any injection. It must prove completion with completion markers,
a target count equal to the OpenAPI operation count, and no incomplete or
timeout warnings. Keep the seeded `/api/v1/news` scan as a separate evidence
run. Retain reports for 90 days, and keep the workflow comment about raw-file
retention aligned with the actual artifacts. This decision sets acceptance
criteria; implementation and source-bound scan or hosted-check results are not
implied.

## Addendum 2026-11-05 UTC: Semgrep uses the same pinned local and CI gate

The local Semgrep pre-commit hook must use the same pinned rules checkout and
the same exact-disposition gate as the blocking CI job. Keep the hook mandatory
locally and use one policy for both paths; do not add inline Semgrep comments.
This decision does not approve any finding-specific Semgrep disposition. In
particular, the separately approved detect-secrets identity for the public
Semgrep rules-checkout pin is a source-integrity digest only; it is not an
approval of entries in `quality/semgrep-dispositions.json`. Any proposed
Semgrep finding dispositions must be shown to the owner before commit. The
decision does not establish that the local hook or CI job passes on the current
working tree.

## Owner-approved Node SSR CSP WebAssembly capability exception (2026-11-05)

On 2026-11-05, the owner approved adding the single quoted
`'wasm-unsafe-eval'` keyword to the `script-src` directive in the Node SSR
response policy. A bounded Chromium capability probe against the current
policy and a counterfactual differing only by that token found that the
baseline blocked minimal WebAssembly compilation and the one-token policy
allowed it. JavaScript `eval` remained blocked in both cases. Native Trusted
Types controls also remained enforced in both cases: default-policy creation
and raw-string `innerHTML` assignment were blocked. This authorization is
limited to that exact token in that directive. It does not authorize
`'unsafe-eval'`, a default Trusted Types policy, or any other CSP change.

The Node SSR policy is implemented in the canonical
[CSP response source](../../frontend/scripts/server-csp.mjs) and covered by its
[production CSP contract test](../../frontend/scripts/server-readiness.test.mjs)
and [browser CSP negative test](../../frontend/tests/e2e-live/production/ssr-csp-browser-negative.spec.ts).
At the time of this initial capability probe, the separate compiled
application-route evidence was incomplete: the app policy callback failed
before requesting the sanitizer WASM asset, and the route did not reach
`networkidle`.

Subsequent local verification on 2026-11-05 supersedes that route observation
only within its recorded scope. Chromium exercised the compiled SSR with
synthetic backend/auth responses, native CSP-negative checks, safe HTML/GFM,
and hydration. The expected cold WASM attempt was caught; the UI rendered inert
text and then retried rich rendering after WASM returned HTTP 200. The
`semanticReady` check passed. A diagnostic `networkidle` wait timed out on the
single mocked CSRF fetch, which returned HTTP 200. This local result does not
establish full-stack behavior, hosted validation, or acceptance of the app
finding. The authorized policy change remains limited to the single quoted
`'wasm-unsafe-eval'` token above; no default Trusted Types policy, raw-string
sink, or other CSP relaxation is authorized. The [WASM sanitizer contract
tests](../../frontend/src/utils/__tests__/wasmSanitizer.test.ts) and
[Trusted Types tests](../../frontend/src/utils/__tests__/trustedTypes.test.ts)
remain the source-level references alongside the CSP tests linked above.

## Addendum 2026-11-05 UTC - exact TruffleHog CI license exception

Owner `egorribun` explicitly approved retaining the CI-only TruffleHog Action
at the immutable revision used in `.github/workflows/trufflehog.yml`, with an
exclusive expiry of 2027-01-10. The approved revision and license source are
[the pinned LICENSE](https://github.com/trufflesecurity/trufflehog/blob/31ce31ee1abbcc7dc8eee5764c17121c3044c8b2/LICENSE).
The retrieved Git blob `d2bc34f9900abd088bfd0d914641ecf434aa5a52` contains the
GNU Affero General Public License, version 3. The recorded license remains
`AGPL-3.0`; CI approval does not remove the license's obligations.

The pinned Dependency Review action reports this exact added row as ecosystem
`actions`, name `trufflesecurity/trufflehog`, the approved revision, PURL
`pkg:githubactions/trufflesecurity/trufflehog@` followed by that revision,
source `https://github.com/trufflesecurity/trufflehog`, and raw `license=null`.
Without the exclusion, separate license evaluation can enrich that null; the
exclusion skips this evaluation without changing the raw comparison output.
The guard accepts only this observed raw row, without
rewriting or substituting its license. It rejects a different source, manifest,
version, PURL, license representation or duplicate row.

The single unversioned `githubactions` PURL replaces the incorrect `github`
entry. Because upstream PURL exclusions ignore version and manifest, preflight
independently requires the approved workflow revision, and the always-run row
guard enforces the exact identity. A matching future workflow and comparison
revision cannot inherit this approval. Expiry blocks on and after 2027-01-10,
even when the comparison contains no added TruffleHog row. The action remains
CI-only and is not distributed with the product.

No global license allowance, vulnerability exception, scanner disposition,
baseline identity, fingerprint, required context, threshold or hook is added
or weakened. The pinned upstream action and output capture remain unchanged;
upstream failures are not masked. This record does not establish passing
tests, scans or hosted checks for any source revision.

## Owner-approved Helm rendered-target Semgrep model (2026-11-05 UTC)

On 2026-11-05 UTC, the owner approved the exact rendered-target model and 11-file implementation package in the owner-reviewed Helm proposal. The package identity is manifest SHA-256 dc4d0ad607fa2679567bd3c84f718e522594c9ceacc77e5cc8038a7b6366d036; its reviewed patch SHA-256 is cb608f73a994d8e3b648af6f5ecd1cf85d2ba52059c489275ae80071ae7755b0. This records approval of the target model; it does not activate the scan-target change before the required final source-bound scan and gate review.

The approved model replaces the 40 raw YAML scan inputs under charts/redis-compat/templates/, charts/revocation-store/templates/, and charts/university-ecosystem/templates/ with the exact eight rendered views in the approved profile matrix. The offline render evidence contains 260 Kubernetes objects across those eight views. Each of the 36 resource-bearing template sources must be represented by at least one approved profile; four validation or deployment-contract templates remain guard-only and are not counted as resource objects. The isolated Gateway API view is diagnostic source-analysis input only and does not authorize feature deployment or replace the full-chart refusal contract.

The implementation candidate package passed its scoped 41-test suite (22 gate regressions, 11 runner integration tests, and 8 overlay-helper tests). The test harness simulated the Helm callback, Docker, and Semgrep; this result is not a full selected-rules scan. The render and provenance evidence does not cover every conditional template branch. It establishes no runtime, deployment, admission-controller, cluster, or CNI behavior.

Preserve every non-Helm Semgrep input and the exact existing .semgrepignore, full selected-rules configuration, scanner and rules pins, severity and error behavior, SARIF handling, disposition gate, pre-commit hook, CodeQL gate, and all 78 required CI context/app pairs. This approval adds no finding disposition, false-positive identity, baseline entry, ignore pattern, exclusion, suppression, hook change, required-check change, or threshold change. Findings at rendered paths do not inherit source-template path/line identities; unmatched findings remain blocking.

Before activation, build a fresh source census and render provenance from the frozen current source snapshot, scan the complete preserved non-Helm inputs plus the eight rendered views with the full selected rules, retain raw JSON and SARIF, and require no scan errors, fixpoint timeouts, unapproved skipped targets, or drift. Review every finding under the existing exact-disposition policy. The separate gateway diagnostic profile remains non-deployment evidence.

## Owner-approved Semgrep finding #11 rationale refresh (2026-11-06)

On 2026-11-06, the owner approved a rationale refresh and six source/test companions for exact Semgrep finding #11, `python.lang.security.audit.regex-dos.regex_dos` at `app/core/logging.py:50`. Its rule, path, line/span identity, owner, approval date and expiry are unchanged; expiry remains 2027-01-10. The rationale is limited to catastrophic regex backtracking in the bounded email/phone/UUID patterns and monotonic local email scanning. The OTel bridge adds no regex and reuses the central redactors with a fixed number of passes. Inputs have no enforced maximum length, so no bounded processing cost is claimed for arbitrarily long logs. The approved 15-row postimage preserves the other 14 rows. Scoped evidence records 207 tests across five logging/OTel modules and 22 focused ReDoS tests; the v4 result is only a preview exact-disposition pass over a supplied report, not full SAST or hosted validation. No new identity, rule-wide exclusion, inline suppression, bypass or expiry extension is approved; final-source SAST and required checks remain necessary.

Public references: [Semgrep ledger, row #11](../../quality/semgrep-dispositions.json), [app/core/logging.py:50](../../app/core/logging.py#L50), [app/core/observability.py](../../app/core/observability.py), [app/core/otel_logging.py](../../app/core/otel_logging.py), [app/worker.py](../../app/worker.py), [ReDoS tests](../../tests/test_logging_redos_aud380.py), [PII redaction tests](../../tests/test_logging_pii_redaction_contract.py), and [OTel bridge tests](../../tests/test_otel_logging_bridge.py).

## Owner-approved Helm registry LF pin amendment (2026-11-06)

On 2026-11-06, the owner approved the exact three-file LF pin amendment for the Helm profile registry, renderer helper and regression test. With `.gitattributes` setting `*.json text eol=lf`, the helper/test digest literals must match checkout-normalized registry bytes. The amendment changes only line endings and matching pin literals; parsed JSON, profiles, source coverage, rendered targets, rules, gates and dispositions remain unchanged. This source-integrity update does not activate rendered-target substitution or authorize scanner-policy changes. The two detect-secrets identities associated with the pin literals remain NOT_APPROVED and are not added to either policy file. The bounded candidate result is not the final whole-main unmatched count; final-source and current-index checks remain required.

Public references: [Helm profile registry](../../scripts/quality/helm_semgrep_profile_registry.json), [rendered-target helper](../../scripts/quality/helm_rendered_target_overlay.py), and [helper regression tests](../../tests/test_helm_rendered_target_overlay.py).
## Owner-approved GitHub workflow helper protection (2026-11-06)

At 2026-11-06 02:26:15 UTC, the owner approved the exact three-file expansion
of review and immutable-base protection for `.github/scripts/**`. The approved
change adds the directory to [CODEOWNERS](../../.github/CODEOWNERS), covers
nested helper paths in the [security-policy integrity workflow](../../.github/workflows/security-policy-integrity.yml),
and includes the directory in both protected path lists in the
[reusable security audit workflow](../../.github/workflows/reusable-security-audit.yml).
All four existing explicit legacy helper patterns remain.

The focused candidate-overlay contract passed for eight new nested helpers and
four existing explicit helper paths; ordinary-source and neighboring-directory
negative controls remained unprotected, the non-owner helper-only change was
rejected, and both reusable path-list guards detected changes under the
directory. An independent review also passed the exact scope. This approval is
limited to owner-review and immutable-base path classification. It does not
change the 78 required CI context/app pairs, hooks, scanners, thresholds,
permissions, baselines, or finding dispositions. The detect-secrets disposition
policy remains at 363 records; no new false-positive disposition or baseline
identity is approved. The candidate evidence does not establish live
branch-protection/CODEOWNERS enforcement, repository-suite results, or hosted
check results. DAST target scope remains outside this approval.

## Owner-approved six exact Semgrep source rebindings (2026-11-06 UTC)

On 2026-11-06 UTC, the owner approved source/context and companion rebindings for existing Semgrep disposition rows #3, #7, #8, #9, #10, and #15. The 15-row ledger count is unchanged. Each affected row keeps its exact finding identity, rule, primary path and span, rationale, owner, approval date and expiry; the other nine rows remain semantically identical. This is a bounded metadata refresh: it adds no finding exception, rule-wide exclusion, suppression, expiry extension, scanner change or required-check change.

The current-index reconciliation matched all 15 existing row identities and surfaced one additional regex finding in the OSV validator. The source correction and targeted one-path Semgrep check are recorded separately. These scoped results do not establish a full current-source SAST pass, hosted validation or release readiness. Final source-bound SAST and required checks remain necessary.

[Semgrep dispositions](../../quality/semgrep-dispositions.json), [audit index](../audits/INDEX.md), and [Semgrep gate](../../scripts/quality/run_semgrep_gate.py).

## Owner-approved exact 21 detect-secrets identities (2026-11-06 UTC)

On 2026-11-06 UTC, the owner approved exactly 21 additional exact path/type/finding-digest dispositions: 16 `public_integrity_digest`, four `external_kubernetes_secret_reference`, and one `ci_test_contract_sentinel`. The four Secret Keyword records identify Kubernetes external Secret object names or key references, not credential material. All 21 records retain their reviewed source evidence and expire on 2027-01-10. The previously owner-approved 106 exact records are materialized without reopening their approval. Together with the existing 363 active records, the disposition policy contains 490 exact records after integration.

The final local follow-up used detect-secrets 1.5.0, 27 plugins, 13 filters, `-n`, and one worker over eight selected logical inputs (four changed source paths plus four candidate overlays); source maps remained stable with zero drift. It reconciled the same 21 identities (16/4/1), with 11 unmatched observations in the selected delta and 10 unchanged prior identities retained by exact source-hash confirmation. This is a conservative local preview, not normal 14-filter hook parity or a full-tree clearance scan. The candidate fail-closed guard’s 20/20 bounded tests are not a substitute for the normal hook, final-source scan or hosted checks.

The baseline remains 242 identities, Gitleaks remains 27 historical fingerprints, the 15 Semgrep rows remain exact, and all 78 required CI context/app pairs, thresholds and hooks are unchanged. No baseline entry, category change, wildcard, exclusion, pragma, bypass or expiry extension is approved. These policy decisions do not establish a passing scan, test suite, hosted check or release readiness.

[Disposition policy](../../quality/security-false-positive-dispositions.json), [validator](../../scripts/verify_secrets_baseline.py), and [baseline contract tests](../../tests/test_verify_secrets_baseline.py).


## Owner-approved Semgrep rows #7 and #15 companion rebind (2026-11-06)

On 2026-11-06, the owner approved a six-companion source-integrity refresh for existing Semgrep disposition rows #7 and #15. The 15-row ledger count is unchanged. Each row retains its finding identity, rule, primary path and span, rationale, owner, approval date and expiry; only the exact companion hashes are refreshed. The six companions are `scripts/live_stand.py` and five SafeHtml build/source metadata files under `frontend/`. No new Semgrep exception, scanner bypass, suppression, rule-wide exclusion, or expiry extension is added.

The refresh changes which source digests are present at those ledger lines. Six exact detect-secrets observations previously associated with the superseded companion values are no longer current: the former row #7 observation is replaced by one current digest, and five former row #15 observations are replaced by values already represented by other exact records in the active disposition inventory. Those six existing records remain unchanged; none is removed, reclassified, extended, or treated as matching a changed value.

The retained full Semgrep report was generated on the 13:54 UTC predecessor source/index snapshot and recorded 15 findings with zero scan errors or timeouts. A read-only reconciliation maps all 15 existing rows to the refreshed candidate against the root20 source/index snapshot; that reconciliation reuses the retained report and is not a new full SAST run on the latest source. Latest-source full SAST remains required, and neither result establishes hosted-check clearance. The separate detect-secrets preview scanned only the proposed Semgrep ledger with 14 filters; it is not normal-hook parity or a full-tree scan.

## Owner-approved four exact detect-secrets identities (2026-11-06)

On 2026-11-06, the owner approved exactly four additional path/type/finding-digest dispositions: one `public_integrity_digest` for the updated Semgrep row #7 companion value and three `ci_test_contract_sentinel` findings in test fixtures. The three test findings are a fixed mocked password-hash equality value and replaceable shell-template markers; they are test-only values, not runtime credentials. All four new records expire on 2027-01-10. The prior 490 policy records, including their existing expiry values, remain byte-for-byte unchanged. Together with the four additions, the disposition policy contains 494 exact records.

A normal 14-filter hook reconciliation confirmed the three test sentinels at their exact source locations; that run exited nonzero because those findings were intentionally surfaced for owner review, and it is not a gate pass. A separate direct 14-filter CLI preview of the proposed ledger found 93 identities, 92 already matching active records and one new unmatched row #7 digest. That single-file preview is not full-tree or normal-hook evidence. The final-source scan and required checks remain necessary after integration.

The detect-secrets baseline remains 242 identities, Gitleaks remains at 27 immutable historical fingerprints, all 78 required CI context/app pairs and existing thresholds/hooks remain unchanged, and the Semgrep ledger remains at 15 rows. No baseline entry, category change, wildcard, exclusion, pragma, bypass, or expiry extension is approved.

[Semgrep dispositions](../../quality/semgrep-dispositions.json), [detect-secrets disposition policy](../../quality/security-false-positive-dispositions.json), [validator](../../scripts/verify_secrets_baseline.py), and [baseline contract tests](../../tests/test_verify_secrets_baseline.py).

## Owner-approved Undici 8.12.4 update, row #15 rebind and one exact disposition (2026-11-06 UTC)

On 2026-11-06 UTC, the owner approved a one-time seven-day maturity exception for the exact `undici` lockfile update from 8.12.2 to 8.12.4, alongside one Semgrep row #15 companion refresh and one exact detect-secrets disposition. The accepted scope changes only version, resolved URL and integrity in `frontend/package-lock.json` at `packages.node_modules/undici`; `frontend/package.json`, other lock records, and the `seroval` 1.6.12 lock entry and override remain unchanged. The Undici lock entry is development-only; this approval makes no claim of production runtime exposure. The published 8.12.4 tarball matched npm registry integrity and SHA-1 metadata.

Semgrep row #15 retains its finding identity, rule, primary path and span, rationale, owner, approval date and expiry; only its `frontend/package-lock.json` companion pin changes. The exact row-bound source and package postimages are recorded in the private owner packet.

The normal 14-filter candidate-ledger preview found one new `Hex High Entropy String` identity at `quality/semgrep-dispositions.json:485`; its value is the new public SHA-256 source-companion pin. The disposition is categorized `public_integrity_digest`, expires 2027-01-10, and is public source-integrity metadata, not credential material. The original 242-entry baseline had no matching identity; no baseline entry is added. The 495-record policy postimage preserves all 494 previously approved record objects and expiry values unchanged, then adds this one exact identity.

The scan was a direct one-file preview with detect-secrets 1.5.0, 27 plugins and 14 filters; it is not normal pre-commit hook parity or full-tree clearance. The retained result is 93 identities, 92 matching the active 494 policy records and one matching this pending record, with zero matches in the frozen original baseline. A separate bounded loopback SRI probe showed 8.12.2 accepted a mismatched tab-prefixed digest while 8.12.4 rejected it; it is diagnostic, not install, maturity, full-suite or hosted-check evidence. Final-source scans, install/audit/test results and required checks remain necessary for the integrated source.

This decision leaves the seven-day npm release-age rule, `.npmrc`, Renovate policy, the 242-entry baseline, Gitleaks inventory, all other policy records and their expiry values, Semgrep rule behavior, hooks, thresholds and required contexts unchanged. It authorizes no other dependency update, new identity, baseline addition, broad exclusion, bypass, expiry extension, merge or deployment. See [ADR-050](ADR-050-security-release-cooldown-exceptions.md) for the exact cooldown boundary and [the disposition policy](../../quality/security-false-positive-dispositions.json).

<a id="proposed-aud-378-decision-verify-the-frontend-ci-application-artifact"></a>

## Owner-approved AUD-378 decision: verify the frontend CI application artifact

**Status: explicitly owner-approved on 2026-11-06 UTC; hosted attestation and final-source validation remain pending.**

The CI application artifact for this decision is the immutable `frontend-dist`
Actions archive produced by the existing `Frontend Tests / Production Build`
job in `.github/workflows/reusable-frontend-tests.yml`. Its subject is the
SHA-256 digest of the raw uploaded archive, not a locally re-created ZIP, a
digest of the extracted directory, or a release container image. The upload
action's artifact ID and digest outputs are surfaced through the existing
`frontend-tests` reusable-workflow call.

For `push` events, a single isolated job in `.github/workflows/ci.yml` attaches
SLSA v1 build provenance to that exact digest. The job is the signer, so its
certificate is checked against the top-level `ci.yml` `workflow_ref` identity.
It does not check out the repository or execute repository scripts. The
read-only provenance check downloads the raw archive by the artifact ID,
cross-checks the Actions artifact and workflow-run API records, hashes the
archive bytes, then performs real `gh attestation verify` verification and
exactly checks the verified subject, source repository ID, source commit/ref,
event, workflow identity, run ID, run attempt, and GitHub-hosted runner claim.
The helper fails closed unless the runner-installed GitHub CLI is at least
2.102.0, bounds the version check and attestation-verification subprocesses,
and reports the verified CLI version.
The existing pinned `slsa-verifier` self-attestation check remains in place.

This adds an application-artifact provenance gate through the existing
`SLSA Provenance Dry-Run` result consumed by `CI Success`. It does not add,
rename, remove, or weaken a required CI context or app pair, and it does not
change quality thresholds. The only job granted `id-token: write` and
`attestations: write` is the isolated attester. The artifact build job remains
read-only. The verifier receives only `actions: read` and `attestations: read`.

Application-artifact attestations are limited to repository `push` events.
For `pull_request`, including fork pull requests, no job requests or receives
attestation-write capability and the application-artifact verifier records
that the scope does not apply; the existing frontend tests and pinned-tool
self-attestation check still run. GitHub documents that fork pull-request
`GITHUB_TOKEN` write permissions are downgraded to read-only unless an
administrator opts into write tokens. Requiring signed provenance for every
fork pull request would therefore need a separate, owner-approved architecture
and event policy; it is not inferred by this decision.

The dated `b85516e` run and its artifact are
historical metadata only. That run failed frontend checks and predates this
decision. A passing hosted run from the approved postimage must establish the
real certificate fields and archive digest before this gate can be reported as
operational. Synthetic parser fixtures are tests only and are not attestations
or trusted-root evidence.


## Owner-approved four Semgrep companion rebindings and two exact detect-secrets identities (2026-11-06 UTC)

On 2026-11-06 UTC, the owner approved exactly four companion-hash updates for existing Semgrep rows #7, #8, #9, and #10. The 15-row ledger count remains unchanged. Row #7 binds `scripts/live_stand.py`; rows #8, #9, and #10 share `tests/test_mfa_deploy_workflow_contract.py`. All Semgrep finding identities, rules, primary paths and spans, rationales, owners, approval dates, and expiries remain unchanged. The already approved row #15 lockfile companion remains unchanged.

The owner also approved exactly two new `public_integrity_digest` detect-secrets identities at `quality/semgrep-dispositions.json:189` and `:229`, bound respectively to those row #7 and rows #8–#10 companion pins. Both records expire on 2027-01-10. The previous 495 approved records and their expiry values remain unchanged; the integrated policy contains 497 exact records. The 242-identity baseline remains unchanged, and neither identity matched the frozen baseline. No other identity, category, baseline entry, wildcard, exclusion, pragma, bypass, reclassification, or expiry extension is approved.

A direct detect-secrets 1.5.0 preview used 27 plugins, 14 filters, verification enabled, no exclusions, and five scoped input files. It recorded 100 identities: 98 matched the existing approved 495-record policy, none matched the frozen baseline, and the two approved identities were the only new matches. This bounded CLI preview is not normal-hook parity or full-tree clearance. Current-source full scans, the ordinary hook, and required checks remain necessary. The guard and test additions enforce these exact records and do not broaden matching behavior.

This update changes neither ADR-050's one-time Undici maturity decision nor the global seven-day release-age rule. Gitleaks remains at 27 historical fingerprints, and the existing required checks and thresholds remain unchanged. See [the Semgrep ledger](../../quality/semgrep-dispositions.json), [the detect-secrets disposition policy](../../quality/security-false-positive-dispositions.json), and [the validator contract](../../tests/test_verify_secrets_baseline.py).


## Owner-approved AUD-427/428 current-source binding (2026-11-07 UTC)

The owner explicitly approved the exact current-source binding for
`tests/test_aud427_428_contract_quality.py` (SHA-256 prefix `590bbac160e2`)
and guard patch `3a3de5a1ab6c`. The contract now checks the reviewed sourced
`scripts/ci/backend-run-integration-tests.ps1` helper instead of the previous
inline workflow body. The guard retains the immutable historical source pin
and adds the exact current-source byte pin, positive context checks, and
call-site, helper-location, and appended-byte negative controls.

This decision changes no finding identity, category, approval status, expiry,
baseline entry, scanner configuration, exclusion, or bypass. The active
disposition inventory remains 497, the baseline remains 242, and Gitleaks
remains at 27 historical fingerprints. Private focused validation passed six
cases; independent review passed. A detect-secrets 1.5.0 direct guard preview
found three existing approved identities and no new identities. These scoped
results do not establish ordinary-hook, full-source, or hosted-check success.
All existing required checks and quality thresholds remain in force.


## One-time owner-approved AUD-420 private recovery replacement (2026-11-07 UTC)

The owner explicitly authorized exactly one standalone private full-history
bundle of the existing `egorribun` head `8a4367b` and one new value-free archive
inventory CSV. This is a one-time exception to the master plan and audit index
prohibition on routine rescue-bundle creation; it grants no general permission
to copy, distribute, restore, or extract credential-shaped history.

The operation completed in an owner-private external directory. Every existing
path component and the target was checked for reparse points before writing.
The protected DACL grants access only to the verified owner, SYSTEM, and
Administrators. The Git bundle is 184,867,508 bytes (SHA-256 prefix
`0c9976ebd3a1`), has no prerequisite commits, passes `git bundle verify`, and
advertises only the approved existing head/ref. The new CSV is 12,461 bytes
(SHA-256 prefix `167dc54faccd7`); its 120 path/mode/blob-OID/size rows cover
112 archived audits and eight plans, totaling 3,981,581 listed blob bytes.
All OID/type/size entries were checked against retained Git metadata.

The historical bundle and CSV remain absent; their historical checksums and
disposition/transfer fields were not reproduced. The new checksums identify
new artifacts only. Exact private locators, full hashes, ACL and verification
receipts are retained privately by the owner. No archive content was printed,
extracted, or published, and no source, index, ref, or worktree was changed by
the recovery operation. This decision does not change scanner dispositions,
required checks, coverage floors, or mutation-stage policy.


### 2026-11-07: restore the previously approved zlib integrity suffix

Merge fbddf32 omitted the eight exact zlib APK integrity dispositions published in 2cfa54cc. Reintegration preserves all 497 current records in order and appends those same eight records, for 505 total and 309 public_integrity_digest records. The paths, detector types, finding digests, owner egorribun, reviewed date 2026-11-06 and expiry 2027-01-10 remain unchanged. This restores the existing finite approval, not new identities or an expiry extension. The baseline remains 242 and Gitleaks remains 27. Signed Alpine archives preserve zlib 1.3.2-r1 after moving indexes stop listing it; SHA-256 and ordinary APK signature verification remain mandatory, with no allow-untrusted or mutable fallback. Source-line evidence is updated only to the exact restored locations. Every new source SHA still requires its own checks.

## Owner-approved AUD-373 Kind source binding (2026-11-07 UTC)

The owner approved the exact current-source test guard for
`scripts/kind/aud373_internal_mtls_proof.sh` in commit `f03b62ba7`. The
SHA-256 binding moved from `99db5a3d...88a96f` to `5c255778...b84ecb6` for
the script with a bounded arithmetic retry loop and explicit error handling
for probe capture. The guard matches the full digest, retained with the
private decision receipt.

The decision applies to that script revision only. Scanner identities,
categories, expiry dates and gates retain their existing values. Later Kind
revisions and the Seed, Temporal and zlib 1.4 proposals require separate
decisions. The hosted A/B/C/D Kind proof still requires passing evidence from
the reviewed source.

## Owner-approved AUD-373 diagnostics source bindings (2026-11-07 UTC)

The owner approved two exact current-source bindings for published
commit `31da75db`. The SHA-256 of
`scripts/kind/aud373_internal_mtls_proof.sh` moved from
`5c255778...b84ecb6` to `84878536...78d5226`. The SHA-256 of
`tests/test_internal_mtls_kind_contract.py` moved from
`06d18a29...f8ebae` to `071d3336...fd2c12`. The private decision
receipt retains the full digests and the corresponding guard.

The revisions add bounded, opt-in no-SVID diagnostics and keep the exact
client-side certificate-required criterion. The associated hosted proof
passed A, C and D. B received EOF without a correlated server event and
remains open. This decision covers only the two bindings. Scanner
inventories, expiries, required checks and the separate Temporal and
ADR-052 decisions retain their existing scope.

## Owner-approved AUD-373 rollout source bindings (2026-11-07 UTC)

The owner approved the two exact source bindings in published commit
`1f532f35`. The SHA-256 for
`scripts/kind/aud373_internal_mtls_proof.sh` moved from
`84878536...78d5226` to `a2721732...3973ddf1`. The SHA-256 for
`tests/test_internal_mtls_kind_contract.py` moved from
`071d3336...fd2c12` to `4bef0e32...939d2a7e`. The private decision
receipt retains the full digests.

This revision waits for the backend deployment to finish its second rollout
before running the probes. It retains the exact TLS certificate-required
criterion for B. The decision covers these two bindings and leaves
Semgrep dispositions, scanner inventories, required checks and ADR-052
under their existing decision scopes.


### 2026-11-07: AUD-428 row13 MapLibre and RLS receipt companion rebind

Status: OWNER APPROVED 2026-11-07; exact source and policy activation is pending normal integration.

This owner-approved change binds Semgrep row 13 to the exact MapLibre workflow
contract postimage, including the current RLS PostgreSQL receipt contract. The
receipt contract names the 14 existing cohort tests and 41 total tests; this
change does not include the separate AUD-360 fifteenth test. The Semgrep ledger
changes only the row13 companion SHA-256 field for
`tests/test_quality_workflow_contract.py`; row14 and its companions remain
byte-exact. The separate N7/HIBP work is not included.

The companion source SHA-256 is `f3193c43...f18b41` and the candidate Semgrep
ledger SHA-256 is `47657088...5a29`. A pinned detect-secrets 1.5.0 preview
of the five frozen row 13 and RLS candidate inputs exited 0. It found one
unmatched row 13 `public_integrity_digest` identity, 99 active-policy matches
and zero baseline matches. The sanitized receipt SHA-256 is
`7fecbd75...8d513`. The private packet retains the full digests. The approved
identity is the finite public SHA-256 companion-digest fingerprint
bound to `quality/semgrep-dispositions.json:381`; the record expires
2027-01-10.

The approved policy appends this one record after the exact prior 505 records.
All previous record bytes and expiry values remain unchanged, including the
eight zlib APK integrity records at indexes 497–504; the row13 record is at
index 505. The policy inventory is 506, the detect-secrets baseline remains
242, Gitleaks remains 27, and the Semgrep ledger remains at 15 rows. These
inventory counts do not establish current whole-source scan results or passing
required checks. Every final source SHA still requires its own validation.

## Owner-approved AUD-373 server-correlated evidence (2026-11-07 UTC)

The owner approved published commit `47da3ae6` as disclosed, including the
alternate server-correlated case B in the Kind proof. The current-source
SHA-256 bindings for the proof script, its contract test and
`app/core/logging.py` move respectively from `a2721732...3973ddf1`,
`4bef0e32...939d2a7e` and `a51276b7...6fc4baa` to
`f6d26624...7c5fc872`, `1b0092f7...891f495c` and
`2a0890c9...908d1a77`. The private decision receipt and published source
retain the full bindings.

The original client TLS alert still satisfies case B. The approved alternate
path requires a valid client TLS error capture at READ_ALERT with EOF and
exactly one correlated server missing-certificate event. It also verifies
the source-bound workload, identity, endpoint and evidence window before
accepting the event. The original client-observed certificate-required
alert remains an open audit evidence item. Required checks still need to
pass on the final source SHA.

The hosted Kind proof on `9410f03f` passed A, B, C and D. For B, the
client recorded EOF during READ_ALERT and the verifier found one matching
server missing-certificate event. The run proves the approved alternate
case for that source. The client alert remains outstanding.
[Hosted Kind job](https://github.com/egorribun/university_ecosystem/actions/runs/42378979206/job/128422376885).

## Owner-approved AUD-373 Kind chart image bindings (2026-11-07 UTC)

The owner approved the two exact source bindings in the Kind Helm repair.
The proof script SHA-256 moves from `f6d26624...7c5fc872` to
`849665fe...e0943`, and the proof contract test SHA-256 moves from
`1b0092f7...891f495c` to `9263fe04...b11e54`. The private decision
receipt retains the full source and patch digests.

The hosted Kind job on `47da3ae6` stopped before the mTLS probes because
the Redis metrics password-file init image differed from the backend image.
The generated values now use the same backend manifest digest and the chart's
required `Always` pull policy. The contract test passes the digest explicitly
to the values generator and checks the helper image binding. The proof
criteria and scanner inventories retain their existing scope. A hosted Kind
run on the final source is still required.

## Owner-approved AUD-373 line-preserving Kind bindings (2026-11-07 UTC)

The owner approved the two exact v3 source bindings for the same Kind Helm
repair. The proof script SHA-256 moves from `849665fe...e0943` to
`dab34a65...d3af9`, and the contract test SHA-256 moves from
`9263fe04...b11e54` to `ed3f3335...d1aad`. The private decision receipt
retains the full source and patch digests.

The previously approved layout moved protected source coordinates. The
flow mapping and explicit test fixture now preserve all protected line and
context bindings. The shared backend/init image digest, pull policy and
mTLS proof criteria are unchanged from the approved repair. The full
source still needs its own scanner and hosted Kind results.
