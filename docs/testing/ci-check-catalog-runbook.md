# CI check catalog runbook

`quality/ci-check-catalog.json` is the repository's machine-readable inventory
of GitHub Actions workflows and jobs.  It is a governance artifact: validating
it is local and read-only, and it does not dispatch workflows, change branch
protection, or retry a GitHub run.

## Validate the catalog

From the repository root run:

```bash
python scripts/quality/validate_ci_check_catalog.py
```

The validator is fail-closed.  It compares the catalog with every
`.github/workflows/*.yml` and `.yaml` file and rejects stale or incomplete
workflow/job inventories, changed trigger guards, missing timeouts, invalid
paths, absent runbook/retry/artifact metadata, and unsupported required-event
claims.

## Metadata contract

Each workflow records its source path, display name, owner, and exact trigger
guards.  Each job records the source check-name template, expected timeout and
duration budget, job guard, and a profile.  Profiles provide the effective
required/advisory/nightly/manual/internal classification, required event
aliases, owner, runbook, artifact contract, and retry policy.  A job may
override any profile field when its artifact or retry behavior differs.

`expected_duration_seconds` is currently an explicit upper-budget placeholder
(`expected_timeout_minutes * 60`) until the CI timing ledger has enough history
to replace it with measured p50/p95 data.  The distinction is intentional and
must remain visible in reviews.

Retry metadata uses `review-required` for source jobs whose current YAML has
retry-like behavior that has not yet been proven to be transient-only.  Do not
silently relabel such a job as `none` or `transient-only`; first-failure
artifacts and a classifier must be added and tested before changing the entry.

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
complete 55-workflow/182-source-job inventory.  A context must not be duplicated
between source jobs, provider checks, or expansions.

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
still requires the detached same-run DAG/artifact-selector workflow described
in the continuation plan.  A missing or malformed report fails the existing
finalizer after the authoritative result table has been evaluated, preserving
the required fail-closed behavior without adding a fan-out job.

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
