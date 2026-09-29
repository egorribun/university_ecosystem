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
- [S3 storage migration runbook](runbooks/s3-seaweedfs-cutover.md)
- [Dependency cooldown emergency procedure](DEPENDENCY_COOLDOWN_EMERGENCY.md)
- [Legacy MinIO volume migration to SeaweedFS](runbooks/s3-seaweedfs-cutover.md)
- [Manual MFA verification checklist](manual-mfa-checklist.md)

## Quality evidence

- [Active MVP closure status](superpowers/plans/STATUS.md) — the single current
  operational status; earlier handoff and continuation plans live under
  `superpowers/plans/archive/` as history.
- [Quality dashboard](testing/dashboard.md)
- [CI check catalog runbook](testing/ci-check-catalog-runbook.md)
- [i18n gate](testing/i18n-gate.md)
- [Flaky-test audit runbook](testing/flaky-test-audit-runbook.md)
- [Performance regression baseline](testing/performance-regression-baseline.md)
- [Canonical audit index](audits/INDEX.md)
- [Machine-enforced quality contract](../quality/quality-contract.json)

Historical audit reports remain under `audits/archive/`. They are retained as
an explicit audit trail and are not current implementation guidance.
