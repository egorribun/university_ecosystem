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
- [Dependency cooldown emergency procedure](DEPENDENCY_COOLDOWN_EMERGENCY.md)
- [Manual MFA verification checklist](manual-mfa-checklist.md)

## Quality evidence

- [MVP master plan (Russian)](superpowers/plans/MVP_MASTER_PLAN.md) — the single
  current roadmap, product acceptance for `v1.0.0`, retained work checkpoints
  and the certification backlog for `v1.1`.
- [ADR-047: risk-based quality policy](adr/ADR-047-risk-based-quality-policy.md)
  — Tier 0 keeps 100% coverage; mutation testing is a nightly signal, not a
  release gate after Q1. Current coverage floors remain enforced until Q3.
- [Active MVP closure status](superpowers/plans/STATUS.md) — the single current
  operational status. Historical handoffs are not continuation instructions.
- [Quality dashboard](testing/dashboard.md)
- [CI check catalog runbook](testing/ci-check-catalog-runbook.md)
- [i18n gate](testing/i18n-gate.md)
- [Flaky-test audit runbook](testing/flaky-test-audit-runbook.md)
- [Performance regression baseline](testing/performance-regression-baseline.md)
- [Canonical audit index and retention policy](audits/INDEX.md)
- [Project audit prompt (Russian)](superpowers/plans/AUDIT_PROMPT.md) — review template.
- [Machine-enforced quality contract](../quality/quality-contract.json)

Legacy audit and plan archives have been reconciled against the master plan,
ADRs, tests, and workflow contracts, then removed from the working tree without
rewriting Git history. The audit index records the private rescue bundle,
verification evidence, and recovery procedure; archive contents are not current
implementation guidance.
