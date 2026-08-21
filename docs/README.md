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

## Architecture and contracts

- [Architecture decision records](adr/README.md)
- [API versioning policy](api_versioning.md)
- [Redis key contract](../contracts/redis-keys.md)
- [API changelog](CHANGELOG.md)
- [Localization guidelines](LOCALIZATION.md)

## Operations

- [Deployment guide (Russian)](DEPLOY.md)
- [Deployment guide (English)](DEPLOY.en.md)
- [Kubernetes notes](../k8s/README.md)
- [Dependency cooldown emergency procedure](DEPENDENCY_COOLDOWN_EMERGENCY.md)
- [Manual MFA verification checklist](manual-mfa-checklist.md)

## Quality evidence

- [Quality dashboard](testing/dashboard.md)
- [Flaky-test audit runbook](testing/flaky-test-audit-runbook.md)
- [Performance regression baseline](testing/performance-regression-baseline.md)
- [Canonical audit index](audits/INDEX.md)
- [Machine-enforced quality contract](../quality/quality-contract.json)

## Agent tooling

- [MCP recipes and server catalog](mcp/MCP_RECIPES.md)
- [Browser E2E MCP workflow](mcp/BROWSER_E2E_MCP.md)
- [Database and cache MCP workflow](mcp/DB_CACHE_MCP.md)
- [Memory and Context7 MCP workflow](mcp/MEMORY_CONTEXT7_MCP.md)

Historical audit reports remain under `audits/archive/`. They are retained as
an explicit audit trail and are not current implementation guidance.
