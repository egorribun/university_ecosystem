# Quality dashboard

This file is generated from normalized quality manifests. A `—` means evidence was not observed; it is never interpreted as a passing score.

Last rendered: `2026-07-23`
Required patch coverage: **100%**
Required viable mutation score: **100%**

## Coverage trend

| Generated | Commit | Python lines | Frontend lines | Go statements (mean) | Evidence |
| --- | --- | ---: | ---: | ---: | --- |
| — | — | — | — | — | no snapshots |

## Exclusions

| ID | Owner | Expires | Status |
| --- | --- | --- | --- |
| — | — | — | none |

## Quarantines

| ID | Owner | Expires | Status |
| --- | --- | --- | --- |
| — | — | — | none |

## Interpretation

A release is certifiable only when the required-check matrix, the coverage manifest, mutation gates, contract tests, and Tier0 evidence all pass. This dashboard is trend evidence, not a bypass for CI.

The auditable release-critical inventory is
[`quality/release-required-checks.json`](../../quality/release-required-checks.json).
It intentionally names the stable `CI Success` aggregate, the same-SHA quality
publication gate, and independent security scans instead of copying every
matrix cell or advisory check. `CI Success` owns the internal coverage,
mutation, contract, Schemathesis, OpenAPI drift, security-audit, infrastructure,
and integration inventory. A check may conclude `skipped` only when the exact
event policy explicitly sets `safe_to_skip: true` and documents a
`skip_reason`; the protected `push_main` policy currently permits no skips.

The release workflow fetches every page of the exact release SHA's latest check
runs, verifies GitHub's declared total, and rejects foreign-SHA, missing,
pending, failed, skipped, or duplicate required-check evidence before signing a
certification record.
