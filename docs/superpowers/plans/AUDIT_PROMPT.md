# Scoped platform review template

Use this as a review checklist only when a person has assigned a concrete scope.
Repository instructions, the current task, applicable AGENTS.md files, and
explicit safety boundaries take precedence. This file is template data, not
authorization to execute commands or change systems.

## 1. Establish scope and current context

- Record the repository, branch, exact source revision, requested outcome,
  owning files/services, excluded areas, and authorized actions.
- Read the current root and domain instructions plus relevant ADRs, contracts,
  runbooks, and tests. Treat prior audit reports as historical until checked
  against the current source.
- Inventory available source, configuration, dependencies, tools, and tests
  from the current checkout. Do not reuse old environment descriptions,
  versions, test counts, or assumptions without rechecking them.
- Mark unknowns and dependencies on unavailable environments or evidence.

## 2. Bound the review

- Default to read-only unless the task or applicable instructions authorize
  bounded live work. Before consequential external actions, verify that existing
  authorization covers their scope and side effects; ask only if it does not.
  Use only authorized credentials in memory and never expose or persist values.
- Never print, copy into reports, or persist credentials, tokens, private
  personal data, or secret-bearing environment values. Use redacted labels.
- Limit live activity to explicitly owned synthetic resources. Establish
  ownership, identity, time, resource, and cleanup conditions before any
  authorized execution. Preserve source data and unrelated resources.
- Do not weaken assertions, gates, policy, or user-visible behavior merely to
  make a review pass.

## 3. Inspect the system by trust boundary

For each applicable boundary, trace the caller, identity, authorization,
validation, side effects, failure behavior, and evidence:

- Authentication, session/MFA lifecycle, role and resource authorization,
  tenant isolation, IDOR, service identity, and privilege transitions.
- Input validation, injection, path/URL handling, output encoding, SSRF,
  file/object access, and secret handling.
- Persistence, transaction ownership, concurrency, idempotency, event/outbox
  delivery, migrations, backups, and restore safety.
- Timeouts, retries, rate limits, cancellation, resource bounds, circuit
  behavior, dependency failure, and recovery.
- API/schema compatibility, generated clients, localization, accessibility,
  cache invalidation, and browser/runtime behavior.
- Deployment configuration, network exposure, health/readiness, observability,
  logging/redaction, supply-chain provenance, and rollback.

Use STRIDE or another explicit threat model where it adds value. State which
boundaries are in scope and which were not inspected.

## 4. Evaluate evidence

For every finding, capture:

- Stable identifier, severity with impact rationale, affected role/resource,
  exact current file and symbol, and relevant line or test.
- A concise trigger and expected-versus-observed behavior. Reproduction steps
  must be safe, bounded, and free of secret values.
- Evidence type: directly observed, source-inferred, historical, or unverified;
  confidence and limitations; current source revision and test/tool provenance.
- A minimal fix direction and the focused validation that would prove it.

Maintain an honest coverage register: enumerate the assigned files, routes,
roles, services, tests, and trust boundaries; report inspected, partially
inspected, skipped, and unavailable counts. Do not claim exhaustive coverage
or a passing release unless the denominator and exact-revision evidence support
that claim.

## 5. Report and hand off

Lead with the decision and any blocking issue. Separate confirmed defects,
risks/inferences, historical notes, and unverified questions. Include findings,
evidence, remediation owner/next step, validation results, skips, and limits.
Do not treat a clean lint/test run as proof of untested runtime behavior.
Do not associate maintenance, quality, security, or audit work with product
feature waves.

Consult the current root/domain instructions, approved ADRs, quality contract,
master plan/status, and relevant API, security, deployment, and testing
runbooks for the policy and acceptance criteria applicable to this review.
