# University Ecosystem documentation

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
- [S3 storage migration runbook](runbooks/s3-seaweedfs-cutover.md)
- [Observability configuration and reference examples](observability/README.md)
- [Dependency cooldown emergency procedure](DEPENDENCY_COOLDOWN_EMERGENCY.md)
- [Manual MFA verification checklist](manual-mfa-checklist.md)

## Quality evidence

- [MVP master plan (Russian)](superpowers/plans/MVP_MASTER_PLAN.md) — the single
  current roadmap, product acceptance for `v1.0.0`, retained work checkpoints
  and the certification backlog for `v1.1`.
- [ADR-047: risk-based quality policy](adr/ADR-047-risk-based-quality-policy.md)
  — Tier 0 keeps 100% coverage, with the owner-approved finite no-decrease
  baseline for exactly 131 unchanged migrations through 2026-11-13. Mutation
  testing is a nightly signal after Q1; other coverage floors remain until Q3.
- [Active MVP closure status](superpowers/plans/STATUS.md) — the single current
  operational status. Historical handoffs are not continuation instructions.
- [Quality dashboard](testing/dashboard.md)
- [CI check catalog runbook](testing/ci-check-catalog-runbook.md)
- [i18n gate](testing/i18n-gate.md)
- [Flaky-test audit runbook](testing/flaky-test-audit-runbook.md)
- [Performance regression baseline](testing/performance-regression-baseline.md)
- [Canonical audit index and retention policy](audits/INDEX.md)
- [Full platform audit, October 2026](audits/AUDIT-2026-10.md) — current
  open-finding register; [dependency closure checkpoint (2026-10-15)](audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15)
  records frozen dependency selection and source-bound local evidence. The
  [2026-10-16 owner update](audits/AUDIT-2026-10.md#owner-approved-two-identity-follow-up-2026-10-16)
  records the current owner-approved scope of 252 exact dispositions after the
  2026-10-16 approvals of 18, 7, and 2 identities, preserving the prior 250.
  The 319-identity baseline and 78 required contexts remain unchanged. The
  [post-pragma-removal update](audits/AUDIT-2026-10.md#post-pragma-removal-scan-and-seven-identity-owner-update-2026-10-16)
  distinguishes the historical 243-policy unfiltered scan from the private
  conditional 250-overlay result. The separate two-identity approval brings the
  owner-approved scope to 252; the policy records do not establish passing tests,
  final-source validation, or hosted-check results. Git and PR #1306 determine published source
  and hosted status. See the [two-identity update](audits/AUDIT-2026-10.md#owner-approved-two-identity-follow-up-2026-10-16).
- [Scoped platform review template](superpowers/plans/AUDIT_PROMPT.md).
- [Machine-enforced quality contract](../quality/quality-contract.json)

Legacy audit and plan archives have been reconciled against the master plan,
ADRs, tests, and workflow contracts, then removed from the working tree without
rewriting Git history. The audit index records the private rescue bundle,
verification evidence, and recovery procedure; archive contents are not current
implementation guidance.

## Documentation ownership

| Subject | Canonical source |
| --- | --- |
| Product requirements | [MVP requirements](superpowers/plans/University_Ecosystem_MVP.md) |
| Priorities, acceptance and v1.1 backlog | [MVP master plan](superpowers/plans/MVP_MASTER_PLAN.md) |
| Current checkpoint and next actions | [STATUS](superpowers/plans/STATUS.md) |
| Architecture and policy decisions | [ADRs](adr/README.md) |
| Enforced quality and check inventory | [Quality contract](../quality/quality-contract.json), [testing guide](../TESTING.md) and [CI catalog](../quality/ci-check-catalog.json) |
| Operator procedures | [Deployment](DEPLOY.en.md) and [runbooks](runbooks/) |
| Finding traceability and historical retention | [Audit index](audits/INDEX.md) |
| Current open findings | [Platform audit, October 2026](audits/AUDIT-2026-10.md) |

Update the canonical source before adjusting summaries or translations. Keep
commands, versions and configuration descriptions aligned with executable
configuration. Change a generated document through its generator and verify
the output. Record runtime results with their source revision and scope; a
historical pass does not certify a later checkout. Retain useful procedures
and decisions while removing superseded handoffs and duplicate snapshots.
The vendored skill catalog under `.agents/skills/` retains upstream guidance;
current task and repository instructions determine how it applies here.
