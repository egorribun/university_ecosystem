# CI check catalog runbook

`quality/ci-check-catalog.json` is the repository's machine-readable inventory
of GitHub Actions workflows and jobs.  It is a governance artifact: validating
it is local and read-only, and it does not dispatch workflows, change branch
protection, or retry a GitHub run.

## Validate the catalog

From the repository root run the locked-toolchain command:

```bash
uv run python scripts/quality/validate_ci_check_catalog.py
```

The validator is fail-closed.  It compares the catalog with every
`.github/workflows/*.yml` and `.yaml` file and rejects stale or incomplete
workflow/job inventories, changed trigger guards or job `needs` dependencies,
missing timeouts, invalid paths, absent runbook/retry/artifact metadata, and
unsupported required-event claims.

## Mutation evidence is nightly/manual, not a release gate

ADR-047 Q1 moved full mutmut and Stryker execution out of pull-request and
main-push CI. `ci.yml` still validates the quality policy and mutation registry,
but it does not run mutation shards or publish a
`frontend-mutation-progress-*` artifact. Full backend and frontend mutation
evidence is produced by `nightly-full-gate.yml` and
`manual-mutation-evidence.yml`. Their canonical reports and shard evidence
belong to those non-blocking evidence lanes; the 100% full-run assertion is not
a required release check. A retry-cache hit or preflight-only validation is
not a fresh shard run.

## MIG-PASS-01 CI image preflight

The existing required `DB Migration Gate (Postgres)` context also verifies the
password preflight after its migration round-trip. CI builds `backend.Dockerfile`
from the checked-out source, records Docker's full image config SHA-256 ID, and
runs `python -m app.cli migrate-passwords assert-none` inside that image by ID.
The job uses only its pinned, disposable PostgreSQL service. That service uses
passwordless trust authentication inside the isolated CI runner; the helper
refuses a non-local endpoint, a password-bearing URL, or a database other than
the disposable migration database. It creates a dedicated non-superuser,
`NOBYPASSRLS` reader with `SELECT` on `users`, checks the clean result, inserts a
random synthetic active row with a non-verifiable bcrypt prefix sentinel and
requires the expected nonzero result, verifies the row is unchanged, removes it,
then requires a clean result again. The sentinel is only used to exercise the
CLI's prefix predicate and is never passed to authentication code.

This catalog entry proves the CI image and CLI wiring plus fail-closed behavior
against disposable PostgreSQL. It does not use protected credentials or a
deployed database and therefore does not satisfy the separate secret-backed
deployment evidence still required by MIG-PASS-01.

## Metadata contract

Each workflow records its source path, display name, owner, and exact trigger
guards.  Each job records the source check-name template, expected timeout and
duration budget, job guard, exact `needs` list, and a profile. Jobs with no
`needs` declare `[]`; a scalar source `needs` becomes a one-item list. The
validator compares each list, including order, to its source workflow.
Source dependencies must name existing jobs in the same workflow, without
duplicates or self-dependencies. Static references in Actions expressions,
including `needs.job-id` and `needs['job-id']`, must name a dependency of that
job. The aggregate `needs.*` form is allowed; dynamic bracket indexing is
unsupported and fails closed because no fixed edge can be audited. Literal
text outside Actions expressions is not treated as a dependency reference.
Whitespace (including newlines), grouping such as `(needs).job-id`, and
case-varied context spelling do not hide a static reference. Bare `needs`,
dynamic access, and comment-like syntax between access tokens are unsupported
and fail closed.
The validator inspects nested job fields (including action inputs), respects
quoted expression text such as `'}}'`, and rejects an unterminated `${{ ... }}`.
Profiles provide the effective required/advisory/nightly/manual/internal
classification, required event aliases, owner, runbook, artifact contract,
and retry policy. A job may
override any profile field when its artifact or retry behavior differs.

The reusable security workflow starts with the required `Security policy
integrity` job. On pull requests it compares every scanner configuration,
ignore list, suppression ledger, and release-quality policy against the
immutable base commit; all dependency, container, SBOM, secrets, and Semgrep
consumers declare that job in `needs` before reading the checkout. Owner-authored
policy changes remain visible for review, while external policy changes fail
closed. Non-pull-request invocations pass this prerequisite without a base
comparison because no untrusted merge ref is involved.

`expected_duration_seconds` is currently an explicit upper-budget placeholder
(`expected_timeout_minutes * 60`) until the CI timing ledger has enough history
to replace it with measured p50/p95 data.  The distinction is intentional and
must remain visible in reviews.  This is an open observability task, not a
claim that CI speed is already fully optimized: the accountable owner is
`@egorribun`, the source artifact is the run/attempt-bound `ci-health-report`
JSON emitted by `ci-success` and rendered by
`scripts/quality/render_ci_health_report.py`, and acceptance requires three
comparable terminal runs on the same workflow topology with non-empty
queue/setup/test/upload p50/p95, observed peak concurrency, retry/timeout
classification and a recorded reason for every skip.  Only then may
`expected_duration_seconds` be replaced with measured values through a
reviewed catalog change.

Retry metadata uses `review-required` for source jobs whose current YAML has
retry-like behavior that has not yet been proven to be transient-only.  Do not
silently relabel such a job as `none` or `transient-only`; first-failure
artifacts and a classifier must be added and tested before changing the entry.

The required `Trivy Image Scan` deliberately has no automatic retry.  The
pinned `aquasecurity/trivy-action` exposes only a process outcome, not a typed
failure reason, so a retry could hide a vulnerability finding or a deterministic
configuration/image error.  Its CRITICAL/HIGH scan remains blocking; the SARIF
upload is an evidence sink and may run after a failed scan.  For a suspected
transient runner or registry failure, rerun the same workflow manually and
retain the first run's logs and SARIF.  Do not add an automatic retry until a
captured stdout/stderr classifier, bounded attempts, first-attempt artifacts,
and focused positive/negative tests prove transient-only behavior.

### Cache trust boundary

Treat cache entries as an optimization, never as source or quality evidence.
Untrusted pull-request jobs must not create executable or generated-state cache
entries that a privileged release job can restore.  A release cache needs its
own trusted producer/scope and keys bound to the source lockfiles, runner OS,
and relevant toolchain; any cache hit must still be validated by the normal
build and release checks.

The current YAML configures some of this boundary: `ci.yml` labels its
pre-commit cache prefixes CI-only and states they must not be consumed by
privileged `workflow_dispatch`/`workflow_run` jobs; the canonical image builder
is main-only and `reusable-build-and-sign.yml` uses a per-image BuildKit cache
scope.  PR frontend npm caches use `frontend/package-lock.json`, while the
release tool's npm cache uses the repository-root `package-lock.json`.
`test_precommit_cache_cannot_cross_into_privileged_workflows` protects the two
pre-commit namespaces, and `test_reusable_node_cache_never_restores_stale_node_modules`
checks that the reusable npm cache contains only lock-bound package downloads.
This is not a complete cache-trust certification: no focused contract proves
that every privileged consumer and cache backend cannot restore PR-writable
state.  Keep that proof as an O3 acceptance item; different lockfile paths or
cache names alone do not establish the trust boundary.

### Fail-closed aggregation and upload errors

A CI timing aggregate or release certificate must bind its required evidence
to one intended repository, workflow, run ID, and source SHA, with an explicit
attempt policy.  Missing identity, an unapproved attempt mix, source mismatch,
duplicate logical results, or missing required evidence must make the aggregate
unavailable or failed; they must never be silently combined into a green
result.  If a workflow deliberately reuses earlier-attempt artifacts after a
failed-job rerun, its selector policy and each producer-attempt identity must
be explicit, and the aggregate must prove that the selected cohort is complete
and compatible.  Strict timing analysis must reject jobs from mixed attempts.

An artifact upload HTTP 403 is a transport/access failure.  It does not mean
that a mutant was killed or that a certificate was produced: tests may have run,
but the required evidence is absent.  Required upload failure must therefore
block the evidence aggregate/certificate. The critical-path analyzer rejects
mixed attempts in diagnostic input. The `ci.yml` health-report step invokes it
only with `--diagnostic-lower-bound`; strict DAG analysis needs separately
supplied attempt-bound DAG and provenance inputs and is not release evidence.
Mutation shard aggregation lives in the nightly/manual workflows, not in
`ci.yml`. No focused contract test currently demonstrates that an upload HTTP
403 cannot produce a killed-mutation certificate. Keep that end-to-end
guarantee unclaimed unless an integrated path and negative test are added.

### Provider checks and expanded contexts

`external_checks` records provider-managed required contexts that do not map
one-to-one to a repository workflow/job name (`CodeQL`, `Checkov`, `spectral`,
and `zizmor`).  The provider integration ID is the identity of the GitHub
Advanced Security integration, not a ruleset ID.  `externally_owned: true`, an
explicit provider owner, classification, source reference, and runbook are
required so ownership is never inferred from a stale check run.

`expansions` records protected contexts emitted by reusable-workflow callers or
matrix jobs.  Each expansion binds an existing caller workflow/job to an
existing reusable workflow/job set (or a matrix strategy) and declares the
finite, exact context names.  These entries supplement, but never replace, the
complete source workflow/job inventory in `quality/ci-check-catalog.json`.
A context must not be duplicated between source jobs, provider checks, or
expansions. Use the validation command above to compare the catalog with the
current workflow files.

### Refresh live ruleset evidence

The catalog intentionally does not store a volatile branch-ruleset ID,
snapshot, or current check conclusion.  Refresh live evidence immediately
before a release review and retain the command output in the SHA-bound audit
artifact:

```bash
repo='egorribun/university_ecosystem'
ruleset_ids=$(gh api "repos/${repo}/rulesets" --paginate \
  --jq '.[] | select(.target == "branch" and .enforcement == "active") | .id')
test -n "$ruleset_ids"
for ruleset_id in $ruleset_ids; do
  gh api "repos/${repo}/rulesets/${ruleset_id}" \
    --jq '{id, name, target, enforcement, conditions, required_status_checks:
      [.rules[] | select(.type == "required_status_checks") |
      .parameters.required_status_checks[] | {context, integration_id}]}'
done
```

Confirm that the active ruleset targeting `refs/heads/main` contains every
required source and expanded/provider context from the catalog, with the
expected integration ID.  Treat a missing, duplicate, renamed, or unexpected
context as a release-blocking catalog/ruleset drift finding.  Do not copy the
returned ruleset ID or a transient status conclusion into
`quality/ci-check-catalog.json`; update the catalog only when the source
workflow, provider integration, or protected-context contract intentionally
changes, and rerun its focused tests and validator.

### Current-run health artifact

The required `ci-success` finalizer publishes one run-bound pair named
`ci-health-${{ github.run_id }}-${{ github.run_attempt }}`.  The pair contains
`artifacts/quality/ci-health-report.json` (the full analyzer ledger) and
`artifacts/quality/ci-health-report.md` (a compact step-summary projection).
The CLI renderer requires and validates the analyzer's `report_sha256` digest,
then validates the schema, outcome counts and queue/setup/test/artifact p50/p95
values before writing Markdown.  A library caller may render an in-memory
report without a digest for focused tests, but no persisted CI artifact may
cross the CLI boundary unsigned.  Job names
are HTML-escaped and bounded; pending or unknown outcomes are called out and
never presented as a green release signal.

Every job row also carries machine-readable `retry_reason`,
`timeout_reason`, and (for skipped jobs) `skip_reason` values.  These fields
describe only evidence exposed by the Jobs API: a workflow rerun does not
prove that an individual failure was retried or transient, and an
`if:`-condition is reported as `condition_not_exposed_by_jobs_api` unless the
validated DAG proves an upstream failure blocked the job.  The `artifact`
timing bucket covers observed upload, download, cache, and other artifact
steps; it is not presented as an upload-only duration when the API cannot
distinguish those operations.

The summary includes `resource_usage` with explicit CPU and peak-RSS
measurements.  The current Jobs API does not expose runner resource telemetry,
so the producer records `status: unsupported` and null measurements with a
reason.  The renderer rejects a non-null value in that state; a future
runner-side producer may use `status: measured` only when both values are
actually captured.

The report is intentionally diagnostic-only: it observes the completed run
through the GitHub Jobs API and therefore is a lower bound, not proof of the
dependency DAG, archive bytes, or release provenance.  Strict timing evidence
must come from a trusted same-run workflow that obtains the DAG sidecar through
the server-issued artifact selector, binds its repository/workflow/run/attempt/
source identity to trusted workflow context, downloads and verifies the archive
bytes against the selected digest, then passes both the DAG and detached
provenance record to strict analysis.  The selector's REST metadata checks and
digest format do not themselves verify downloaded bytes.  The analyzer must
reject a missing or malformed DAG, identity mismatch, incomplete job timing,
foreign/future artifact, or mixed run attempts; a diagnostic lower-bound report
cannot substitute for that strict evidence.

The analyzer and selector libraries have focused identity, digest, DAG, and
mixed-attempt rejection tests.  The current `ci-success` path still publishes
the Jobs-API lower bound, and no repository workflow invokes strict analysis
end-to-end or verifies the selected archive bytes before analysis.  Strict
reports are therefore not release evidence today.  A missing or malformed
health report fails the existing finalizer after the authoritative result
table has been evaluated, preserving the required fail-closed behavior without
adding a fan-out job.

### Full-backend mutation Helm dependency reuse

After ADR-047 Q1, PR/main CI no longer runs full mutmut. The nightly
`nightly-full-gate.yml` and manually dispatched `manual-mutation-evidence.yml`
full-backend callers both use `reusable-helm-dependencies.yml` to resolve the
locked Redis and NATS Helm archives once. The producer publishes regular files
in a source-, run-, and attempt-bound artifact and returns its exact name to
the reusable mutation workflow. Consumers select and validate that artifact
before running `helm_dependency_build.py --skip-refresh`. The helper checks
that both archives exist and are non-empty; the artifact manifest checks their
SHA-256 inventory and source/run identity. A missing, symlinked, or modified
archive must fail closed. The producer is the only step allowed to perform the
narrow transport retry against the registry.

The nightly caller uses this boundary for its backend stats and execution
shards; the manual full-backend caller uses the same producer/consumer path.
Each consumer validates the server-issued artifact identity before restoring
the archives, and the nightly retry selector does not accept a future attempt
or foreign commit/workflow artifact. The restore helper also rejects
destination traversal and symlinked or junction-backed destination components
before copying into a consumer checkout.

## Updating safely

When adding, removing, or renaming a workflow/job:

1. Update the catalog in the same change, including its profile and exact
   timeout/check-name guard.
2. Add or update a runbook when the operational response is not covered here.
3. Run the focused tests and the validator.
4. Review required/advisory classification against
   `quality/release-required-checks.json` and live branch protection; this
   catalog intentionally does not mutate either source.

Never use this catalog to justify a broad retry, an unbounded timeout, a
missing artifact, or a required-check bypass.  Record an explicit owner and
follow the repository's normal security and release review gates.
