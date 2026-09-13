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
