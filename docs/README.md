# University Ecosystem documentation

This directory holds the durable documentation for University Ecosystem: operations, architecture, API
and quality. Temporary execution notes and handoffs are not part of this index.

## Current audit status — 2026-11-22

The formal total is **511/512 (99.8%) accepted or resolved, 1 open**: **1S / 0P / 0U / 0N**.
- AUD-381 is resolved for the
  [exact-main ephemeral Compose DAST criterion](audits/AUDIT-2026-11-06-full-reassessment.md#scoped-aud-381-acceptance--2026-11-22).
- The [remaining finding](audits/AUDIT-2026-10-30-reconciliation.md#current-1-finding-reconciliation--2026-11-22)
  is AUD-154.
- Full scan coverage, general CI and release acceptance are not implied.
- Every dated checkpoint, from 476/512 to 510/512, is listed in the [audit index](audits/INDEX.md).

**Secret-scanning inventory.**
- The current baseline contains 242 identities, after the
  [62 deleted-source identities were retired](adr/ADR-047-risk-based-quality-policy.md#deleted-source-baseline-retirement-2026-11-02).
- The detect-secrets disposition working tree contains 524 approved records.
- The Gitleaks approval covers 27 historical fingerprints, and Semgrep has 15 disposition rows.
- How the records grew:
  - At the N5 integration snapshot on 2026-11-06, the working tree held 495 records. They were 363 previously active records, 106 previously owner-approved identities now materialized, 21 previously approved exact identities, and five newly approved exact identities.
  - The later owner-approved additions are recorded in [ADR-047](adr/ADR-047-risk-based-quality-policy.md) and in the [audit index](audits/INDEX.md). The most recent were twelve AUD-189 backup/restore test identities on 2026-11-16.
  - Every addition expires 2027-01-10.
- The inventory is not evidence of a passing scan or required checks; each source SHA requires its own validation.
- All 78 required context/app pairs, blocking CodeQL, hooks and quality floors remain in force.

## Start here

- [Project overview and local startup](../README.md)
- [Configuration reference](../CONFIGURATION.md)
- [Contributing guide](CONTRIBUTING.md)
- [API documentation](api/README.md) and [API examples](API_EXAMPLES.md)
- [Test and quality guide](../TESTING.md)
- [MVP requirements (Russian)](superpowers/plans/University_Ecosystem_MVP.md)

## Architecture and contracts

- [Architecture decision records](adr/README.md)
- [API versioning policy](api_versioning.md)
- [Redis key contract](../contracts/redis-keys.md)
- [Localization guidelines](LOCALIZATION.md)

## Operations

- Deployment guide: [Russian](DEPLOY.md) and [English](DEPLOY.en.md)
- [Helm chart](../charts/university-ecosystem/README.md) and [Kubernetes notes](../k8s/README.md)
- Runbooks:
  - [database backup and restore](runbooks/database-backup-restore.md)
  - [Temporal network access](runbooks/temporal-network-access.md)
  - [S3 storage migration](runbooks/s3-seaweedfs-cutover.md)
  - [rejected-upload quarantine](runbooks/upload-quarantine.md)
  - [event image retention under tenant RLS](runbooks/event-image-retention.md)
- [Observability configuration and reference examples](observability/README.md)
- [Dependency cooldown emergency procedure](DEPENDENCY_COOLDOWN_EMERGENCY.md)
- [Manual MFA verification checklist](manual-mfa-checklist.md)

## MVP and quality

- [MVP master plan (Russian)](superpowers/plans/MVP_MASTER_PLAN.md): the single release plan, with
  stages 3–6, acceptance criteria, owner decisions and the `v1.1` backlog.
- [Current status (Russian)](superpowers/plans/STATUS.md): the single operational snapshot.
- [MVP traceability matrix (ТЗ §2–13)](testing/mvp-traceability-matrix.md)
- [ADR-047: risk-based quality policy](adr/ADR-047-risk-based-quality-policy.md)
  - Tier 0 and every migration require 100% coverage for every applicable metric.
  - Full mutation testing runs only in nightly or manual lanes, outside the MVP release gate.
  - Other coverage floors remain until Q3.
- Key MVP decisions:
  - [ADR-049 MapLibre lazy-chunk budget](adr/ADR-049-maplibre-lazy-chunk-budget.md)
  - [ADR-051 migration baseline squash](adr/ADR-051-mvp-migration-baseline-squash.md)
  - [ADR-052 backend SPIFFE transport](adr/ADR-052-backend-spiffe-transport.md)
  - [ADR-053 single-organization authentication](adr/ADR-053-operator-scoped-mvp-authentication.md)
  - [ADR-054 Docker Compose deployment target](adr/ADR-054-mvp-docker-compose-deployment-target.md)
  - [ADR-055 retention under tenant RLS](adr/ADR-055-retention-cleanup-under-tenant-rls.md)
- Testing guides:
  - [quality dashboard](testing/dashboard.md)
  - [CI check catalog runbook](testing/ci-check-catalog-runbook.md)
  - [i18n gate](testing/i18n-gate.md)
  - [flaky-test audit runbook](testing/flaky-test-audit-runbook.md)
  - [performance regression baseline](testing/performance-regression-baseline.md)
  - [React Compiler facade integration](testing/react-compiler-facade-integration.md)
- Audit material:
  - [audit index and retention policy](audits/INDEX.md)
  - [full platform audit, October 2026](audits/AUDIT-2026-10.md)
  - [scoped review template](superpowers/plans/AUDIT_PROMPT.md)
- [Machine-enforced quality contract](../quality/quality-contract.json)

Legacy audit and plan archives were reconciled and removed from the working tree, without rewriting Git
history. The audit index records the private rescue bundle and its recovery procedure.

## Documentation ownership

| Subject | Canonical source |
| --- | --- |
| Product requirements | [MVP requirements](superpowers/plans/University_Ecosystem_MVP.md) |
| Priorities, acceptance and v1.1 backlog | [MVP master plan](superpowers/plans/MVP_MASTER_PLAN.md) |
| Current checkpoint and next actions | [STATUS](superpowers/plans/STATUS.md) |
| Architecture and policy decisions | [ADRs](adr/README.md) |
| Enforced quality and check inventory | [Quality contract](../quality/quality-contract.json), [testing guide](../TESTING.md) and [CI catalog](../quality/ci-check-catalog.json) |
| Operator procedures | Deployment ([RU](DEPLOY.md), [EN](DEPLOY.en.md)) and [runbooks](runbooks/) |
| Finding traceability and historical retention | [Audit index](audits/INDEX.md) |
| Current open findings | [Current 1-finding complement, 2026-11-22](audits/AUDIT-2026-10-30-reconciliation.md#current-1-finding-reconciliation--2026-11-22) |

Update the canonical source before you adjust summaries or translations. Keep commands, versions and
configuration descriptions aligned with the executable configuration. Change a generated document
through its generator, and verify the output. Record runtime results with their source revision and
scope; a historical pass does not certify a later checkout. The vendored skill catalog under
`.agents/skills/` keeps the upstream guidance; the current task and repository instructions decide how
it applies here.
