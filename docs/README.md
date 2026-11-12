# University Ecosystem documentation

## Current reconciliation — 2026-11-12

The current formal total is **502/512 (98.0%) accepted or resolved, 10 open**:
**4S / 6P / 0U / 0N**. This update accepts AUD-313, AUD-321, AUD-322, AUD-346,
AUD-347, AUD-375, AUD-378 and AUD-483, each for its own stated criterion.
[Decision scopes and evidence limits](audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-12)
bind them to hosted runs on main `eb853a37cca3a614a32c8ee598f7cf6f3d10e0ec` and
`81ee9ce6c64bd36fa9b0f48a6093bedf48611f7f`. Two findings were reviewed and stay open:
the AUD-432 live hydration spec fails on main, and the eight AUD-484 Trivy alerts
are still open on the `egorribun` branch ref under two retired SARIF categories. The
[current 10-finding complement](audits/AUDIT-2026-10-30-reconciliation.md#current-10-finding-reconciliation--2026-11-12)
lists what each open finding needs. No overall CI, release or deployment
acceptance is implied; this documentation commit needs its own checks.

## Dated exact-source review note — 2026-11-11 (superseded)

At this dated review the formal total remained **494/512 (96.5%) accepted or resolved, 18 open**
(9S / 9P / 0U / 0N). [Source-bound CI and candidate review](audits/AUDIT-2026-11-06-full-reassessment.md#exact-source-ci-review--2026-11-11-preparation-only)
records source 307cfb7a4ea2ca53543fc7a191282e26e9390668, tested merge
3ca365f071438a5dba2c9b3e9d65dea06f3ba71c and Matrix run 43018326180:
77 required successes plus Checkov neutral, not 78 successes. No audit closure
was added; the held 497/512 proposal was never published. AUD-154 has verified
current named-case desktop/mobile proof, but its original criterion remains
unfulfilled and it stays open. Historical checkpoints
below retain their source dates. A later documentation commit needs its own checks.

## Dated reconciliation — 2026-11-09 (494/18; superseded)

At this dated checkpoint the formal total was **494/512 (96.5%) accepted or resolved, 18 open**:
**9S / 9P / 0U / 0N**. Sixteen scope additions since the **478/34** checkpoint were AUD-164, AUD-178, AUD-208, AUD-226,
AUD-272, AUD-334, AUD-360, AUD-373, AUD-416, AUD-420, AUD-428, AUD-429, AUD-454, AUD-478, AUD-480 and AUD-501.
Only AUD-164, AUD-178, AUD-454 and AUD-501 were added by that update, each for its
own stated criterion. The prior **490/22**, **486/26**, **485/27**, **484/28**, **478/34** and
**476/36** checkpoints remain dated history.

[Decision scopes and evidence limits](audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-09).
The reviewed supplemental evidence is bound to its individual source pins,
including earlier 20d4/13693/ea381 evidence snapshots. The supplemental v4
packet was captured at index tree 8ba3ea986595; the first 484 documentation
draft was prepared after staged-tree capture 6dd3cc904fff. That draft tree is
historical, not a current-index or coverage assertion; the working index has
since advanced, and no checks are claimed for the later index or these doc
updates. At draft capture, local HEAD was 9c566fa906a6 and the observed
remote-tracking ref was 067b922f10cb; local and remote were not synchronized. A later 2026-11-07 UTC observation recorded normal merge commit fbddf32f04f0 and tree 74c0c0c38f94, pushed at 04:43:56 UTC with local and remote refs matching then; applicable hooks, full SAST, and pre-push typecheck passed. A final-source guard run on that tree reported 1,180 PASS and 5 FAIL across 1,185 nodes, with no errors, skips, or warnings; the five failures remain tied to the known whole-file guard-pin approval issue. The later terminal snapshot on the same source recorded 98 successful, 23 failed, and 25 skipped checks. Full CI GREEN, all required checks passing, and release readiness are not established.
Current inventory is **511 dispositions / 242 baseline identities / 27 Gitleaks
fingerprints / 15 Semgrep rows**, not a passing scan. All 78 required context/app
pairs, blocking CodeQL, hooks and quality floors remain in force.

---

This directory contains the durable operating, architecture, API, and quality
documentation for University Ecosystem. Temporary execution notes and completed
handoffs are intentionally not part of the canonical index.

## Start here

- [Project overview and local startup](../README.md)
- [Configuration reference](../CONFIGURATION.md)
- [Contributing guide](CONTRIBUTING.md)
- [API documentation](api/README.md)
- [API examples](API_EXAMPLES.md)
- [Test and quality guide](../TESTING.md)
- [MVP requirements (Russian)](superpowers/plans/University_Ecosystem_MVP.md)

## Architecture and contracts

- [Architecture decision records](adr/README.md)
- [API versioning policy](api_versioning.md)
- [Redis key contract](../contracts/redis-keys.md)
- [Localization guidelines](LOCALIZATION.md)

## Operations

- [Deployment guide (Russian)](DEPLOY.md)
- [Deployment guide (English)](DEPLOY.en.md)
- [Helm chart](../charts/university-ecosystem/README.md)
- [Kubernetes notes](../k8s/README.md)
- [Database backup and restore runbook](runbooks/database-backup-restore.md)
- [Temporal network access runbook](runbooks/temporal-network-access.md)
- [S3 storage migration runbook](runbooks/s3-seaweedfs-cutover.md)
- [Rejected-upload quarantine and capacity](runbooks/upload-quarantine.md)
- [Observability configuration and reference examples](observability/README.md)
- [Dependency cooldown emergency procedure](DEPENDENCY_COOLDOWN_EMERGENCY.md)
- [Manual MFA verification checklist](manual-mfa-checklist.md)

## Quality evidence

- [MVP master plan (Russian)](superpowers/plans/MVP_MASTER_PLAN.md) — the single
  current roadmap, product acceptance for `v1.0.0`, retained work checkpoints
  and the certification backlog for `v1.1`.
- [ADR-047: risk-based quality policy](adr/ADR-047-risk-based-quality-policy.md)
  — Tier 0 requires 100% for every applicable coverage metric; all migrations
  require 100% line, statement, branch and function coverage. The 131-file
  migration exception was retired on 2026-11-02. Full mutation testing runs in
  nightly/manual lanes outside the MVP release gate; other coverage floors
  remain until Q3.
- [ADR-051: MVP migration baseline squash](adr/ADR-051-mvp-migration-baseline-squash.md)
  — the 143 historical Alembic revisions are replaced by one irreversible
  baseline, accepted 2026-11-02; pre-squash databases must be recreated.
- [ADR-052: Backend SPIFFE identity at the HTTP transport boundary](adr/ADR-052-backend-spiffe-transport.md)
  — accepted by the owner on 2026-11-09. The transport exists in source; the Helm
  chart defaults it off and requires it in production. AUD-373 was accepted at
  490/512 on the hosted kind proof; Compose keeps plaintext gateway-to-backend
  traffic as an owner-accepted risk recorded in ADR-054.
- [ADR-053: Operator-scoped single-organization MVP authentication](adr/ADR-053-operator-scoped-mvp-authentication.md)
- [ADR-054: Docker Compose is the MVP deployment target](adr/ADR-054-mvp-docker-compose-deployment-target.md)
  — scope accepted 2026-11-02 and implemented in source; full source-bound
  hosted acceptance remains pending.
- [Active MVP closure status](superpowers/plans/STATUS.md) — the single current
  operational status. Historical handoffs are not continuation instructions.
- [Quality dashboard](testing/dashboard.md)
- [CI check catalog runbook](testing/ci-check-catalog-runbook.md)
- [i18n gate](testing/i18n-gate.md)
- [Flaky-test audit runbook](testing/flaky-test-audit-runbook.md)
- [Performance regression baseline](testing/performance-regression-baseline.md)
- [Canonical audit index and retention policy](audits/INDEX.md)
- [Current full audit reassessment, 2026-11-12 UTC](audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-12) — 502 / 512 accepted or resolved (98.0%), 10 open; 49 scoped acceptances plus the AUD-384 false-positive retraction. No overall CI GREEN or release acceptance is implied.
- [Dated 494 / 512 audit checkpoint](audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-09) — 18 open (9S / 9P / 0U / 0N), retained as history.
- [Dated 490 / 512 audit checkpoint](audits/AUDIT-2026-11-06-full-reassessment.md#dated-490-22-scoped-supplement--2026-11-09) — 22 open (13S / 9P / 0U / 0N), retained as history.
- [Dated 486 / 512 audit checkpoint](audits/AUDIT-2026-11-06-full-reassessment.md#dated-486-26-scoped-supplement--2026-11-09) — 26 open (14S / 12P / 0U / 0N), retained as history.
- [Dated 485 / 512 audit checkpoint](audits/AUDIT-2026-11-06-full-reassessment.md#current-scoped-supplement--2026-11-07) — 27 open (15S / 12P / 0U / 0N), retained as history.
- [Dated 484 / 512 audit checkpoint](audits/AUDIT-2026-11-06-full-reassessment.md#dated-484-28-scoped-supplement--2026-11-07) — 28 open (16S / 12P / 0U / 0N), retained as history.
- [Dated prior public checkpoint](audits/AUDIT-2026-11-06-full-reassessment.md#previous-public-checkpoint--2026-11-07) — 478 / 512, 34 open (20S / 13P / 0U / 1N); superseded and retained as history.
- [Dated previous cohort checkpoint](audits/AUDIT-2026-11-06-full-reassessment.md#previous-cohort-checkpoint--2026-11-06-2359-utc) — 476 / 512, 36 open (19S / 15P / 1U / 1N), retained as history.
- [Dated cumulative scoped audit review, 2026-11-06](audits/AUDIT-2026-11-06-review.md) — AUD-426 PostgreSQL, AUD-231 compiled SSR CSP/nonce, and AUD-449 log-redaction acceptances for Caddy and the Python application server with separate evidence limits; overall CI and release readiness are not accepted.
- [Full platform audit, October 2026](audits/AUDIT-2026-10.md) — current
  open-finding register; [dependency closure checkpoint (2026-10-15)](audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15)
  records frozen dependency selection and source-bound local evidence. The
  [2026-10-16 owner update](audits/AUDIT-2026-10.md#owner-approved-two-identity-follow-up-2026-10-16)
  records the intermediate owner-approved scope of 252 after the 18-, 7-, and
  2-identity approvals, preserving the prior 250 records. The later nine-identity
  Go source-contract approval extended the historical scope to 261; see the
  [nine-identity audit update](audits/AUDIT-2026-10.md#owner-approved-nine-go-source-contract-identifiers-2026-10-16).
  The current baseline contains 242 identities after the
  [62 deleted-source identities were retired](adr/ADR-047-risk-based-quality-policy.md#deleted-source-baseline-retirement-2026-11-02)
  from the preceding 304-identity checkpoint;
  78 required contexts remain unchanged. The
  [post-pragma-removal update](audits/AUDIT-2026-10.md#post-pragma-removal-scan-and-seven-identity-owner-update-2026-10-16)
  distinguishes the historical 243-policy unfiltered scan from the private
  conditional 250-overlay result. The policy approvals do not establish passing
  tests, final-source validation, or hosted-check results. Git and PR #1343 determine published source
  and hosted status. At HEAD `1cc8fb2db`, the detect-secrets disposition file
  contained 362 records. At the 2026-11-05 checkpoint, the working tree
  contained 363 after adding the owner-approved Semgrep rules-checkout pin; that
  interim staged update was unpublished and still required source-bound
  validation. At the N5 integration snapshot on 2026-11-06, the working tree
  contained 495 approved disposition records: 363 previously active records,
  106 previously owner-approved identities now materialized, 21 previously
  approved exact identities, and five newly approved exact identities (two
  `public_integrity_digest` and three `ci_test_contract_sentinel`). The prior
  494-record set remained unchanged, including expiry values; the additional
  `public_integrity_digest` identity expires 2027-01-10. The inventory is not evidence of a passing scan or required checks; each source SHA requires its own validation.
  This historical inventory did not establish passing tests, final-source validation, or hosted-check results.
  The separate finite Gitleaks approval covers 27 historical fingerprints.
  The subsequent N6 decisions approve four Semgrep companion-hash refreshes
  for rows #7–#10 and exactly two `public_integrity_digest` identities. At the N6 integration snapshot, the working tree contained 505 approved disposition records;
  expiry values remain unchanged, and the two additions expire 2027-01-10. The
  baseline remains at 242 identities and Gitleaks at 27 historical fingerprints.
  After the owner-approved AUD-428 row13 integration and WASM CLI integrity update, the working tree contained 509 approved records; the row13 public-integrity identity follows the unchanged 505-record prefix, the three WASM CLI checksum identities follow it, and all four expire 2027-01-10. After the owner-approved Go image integrity update on 2026-11-11, the working tree contained 510 approved records; the additional Go Alpine image checksum identity in `tests/test_docker_startup_contracts.py` expires 2027-01-10. Authorized helper and row13 one-to-one rebinds retain that 510 count and existing scope and expiry. With the exact owner-approved ZAP image identity appended, the working tree contains 511 approved records; all 510 latest published pre-ZAP records remain unchanged, and the ZAP record expires 2027-01-10.
  See [current status](superpowers/plans/STATUS.md) and the [Gitleaks decision](adr/ADR-047-risk-based-quality-policy.md#one-exact-historical-public-test-password-hash-fingerprint-2026-11-01).
  See the [two-identity update](audits/AUDIT-2026-10.md#owner-approved-two-identity-follow-up-2026-10-16)
  and the [nine-identity update](audits/AUDIT-2026-10.md#owner-approved-nine-go-source-contract-identifiers-2026-10-16).
- [Scoped platform review template](superpowers/plans/AUDIT_PROMPT.md).
- [Machine-enforced quality contract](../quality/quality-contract.json)

Legacy audit and plan archives have been reconciled against the master plan,
ADRs, tests, and workflow contracts, then removed from the working tree without
rewriting Git history. The audit index records the private rescue bundle,
verification evidence, and recovery procedure; archive contents are not current
implementation guidance.

## Documentation ownership

| Subject                                       | Canonical source                                                                                                                        |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Product requirements                          | [MVP requirements](superpowers/plans/University_Ecosystem_MVP.md)                                                                       |
| Priorities, acceptance and v1.1 backlog       | [MVP master plan](superpowers/plans/MVP_MASTER_PLAN.md)                                                                                 |
| Current checkpoint and next actions           | [STATUS](superpowers/plans/STATUS.md)                                                                                                   |
| Architecture and policy decisions             | [ADRs](adr/README.md)                                                                                                                   |
| Enforced quality and check inventory          | [Quality contract](../quality/quality-contract.json), [testing guide](../TESTING.md) and [CI catalog](../quality/ci-check-catalog.json) |
| Operator procedures                           | [Deployment](DEPLOY.en.md) and [runbooks](runbooks/)                                                                                    |
| Finding traceability and historical retention | [Audit index](audits/INDEX.md)                                                                                                          |
| Current open findings                         | [Current 10-finding complement, 2026-11-12 UTC](audits/AUDIT-2026-10-30-reconciliation.md#current-10-finding-reconciliation--2026-11-12)                 |

Update the canonical source before adjusting summaries or translations. Keep
commands, versions and configuration descriptions aligned with executable
configuration. Change a generated document through its generator and verify
the output. Record runtime results with their source revision and scope; a
historical pass does not certify a later checkout. Retain useful procedures
and decisions while removing superseded handoffs and duplicate snapshots.
The vendored skill catalog under `.agents/skills/` retains upstream guidance;
current task and repository instructions determine how it applies here.

At the earlier zlib restoration checkpoint, eight previously approved APK integrity identities followed the 497-record prefix at indexes 497–504. The AUD-428 row13 public-integrity identity then followed at index 505; three WASM CLI checksum identities followed at indexes 506–508, bringing that checkpoint inventory to 509. The approved Go Alpine image identity followed at index 509, bringing the inventory to 510. Subsequent authorized helper and row13 one-to-one rebinds retain the count, existing scope and expiry. The exact ZAP image identity now follows at index 510 and preserves all 510 latest published records unchanged, bringing the current total to 511. All five WASM, Go and ZAP additions expire 2027-01-10.
