# Quality dashboard

This file is generated from normalized quality manifests. A `—` means evidence was not observed; it is never interpreted as a passing score.

No certified quality snapshot is currently published (`quality-history/` has
no normalized manifest). The empty trend row is therefore intentional and
must not be read as a pass.

Historical CI-capacity observations are diagnostic context only, not current
release evidence. The [MVP master plan](../superpowers/plans/MVP_MASTER_PLAN.md)
defines future O1–O8 comparable-run evidence; historical measurements are not
a fresh baseline.

Last rendered: `2026-10-10`
Configured current patch-coverage floor: **100%**
Tier 0 keeps 100% coverage. Current component floors remain blocking until
ADR-047 Q3.
The planned Q3 coverage ratchet and 90% non-Tier 0 patch floor are not implemented.
Configured viable-mutation score value: **100%**
ADR-047 Q1 keeps full mutmut/Stryker runs on nightly/manual lanes and removes
mutation jobs from the MVP release gate. The Q2 nightly regression check and
dashboard publication are planned, not implemented.

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

A release certification record requires the exact required-check matrix, same-SHA
quality publication, current coverage floors and manifest, contract tests,
and required Tier 0 evidence pass. Mutation jobs do not block the MVP release
under ADR-047 Q1; their full runs remain nightly/manual evidence. Q2 mutation
regression publication and Q3 coverage changes are future stages. This dashboard
is trend evidence, not a bypass for CI.

The auditable release-critical inventory is
[`quality/release-required-checks.json`](../../quality/release-required-checks.json).
It lists the stable `CI Success` aggregate, the same-SHA `Trusted Codecov Upload`,
and independent required security checks without duplicating every matrix entry.
The aggregate's prerequisites are defined in `.github/workflows/ci.yml` and
cataloged in `quality/ci-check-catalog.json`; mutation jobs are not among them
after ADR-047 Q1. A check may conclude `skipped` only when the exact event policy
explicitly sets `safe_to_skip: true` and documents a `skip_reason`; the protected
`push_main` policy currently permits no skips.

The release workflow fetches every page of the exact release SHA's latest check
runs, verifies GitHub's declared total, and rejects foreign-SHA, missing, pending,
failed, skipped, or duplicate required-check evidence before signing a
certification record.
