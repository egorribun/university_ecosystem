# ADR-038: Go Mutation Diagnostic Boundary

## Status

Accepted

## Date

2026-09-10

## Context

The Go quality contract requires native statement coverage and derived line
coverage for each in-scope Go component, together with race, static-analysis
and security-behavior evidence. Go's standard coverprofile does not provide
native branch or function coverage, so those metrics are explicitly
unsupported in `quality/quality-contract.json`. Go mutation testing is not a
contract-owned metric today.

The former required Go job executed a long `go-mutesting` tail after the
coverage and race work. When that tail reached the job deadline, the job was
cancelled before its report and provenance were uploaded. This made a valid
coverage/race result appear unavailable and did not produce an honest mutation
score.

## Decision

Go mutation testing remains a bounded, advisory diagnostic. It is not added to
the quality contract, the required pull-request matrix, or the coverage policy
aggregate. The contract-owned Go producer always runs and uploads its coverage
and provenance independently of the diagnostic job.

The diagnostic is exposed only by the dedicated scheduled/manual workflow. It
does not use job-level `continue-on-error`: a tool, runtime, timeout, or
evidence-finalization error makes the diagnostic job fail visibly. Because the
workflow is not a required PR check, this visibility does not weaken or block
the contract-owned PR gate.

Each changed, non-generated Go source file is an exact diagnostic target. The
diagnostic writes an expected-target manifest before starting workers and
materializes one outcome for every expected target. A target that could not
start or finish is recorded as `unreported`, with no fabricated report or
score. A `complete` summary is accepted only when the outcome count equals the
expected-target count, every outcome is successful, and every report exists.
All summaries and per-target reports carry the commit, base, workflow/run,
configuration, source and report hashes needed to audit the result. Artifacts
are uploaded with `if: always()` after fail-closed finalization.

The per-target timeout remains bounded at 1,800 seconds and the diagnostic
job retains an explicit outer deadline. Increasing that deadline alone is not
considered a fix; future changes must preserve complete-target accounting and
be justified by measured duration/cost evidence.

## Consequences

### Positive

- A diagnostic timeout cannot delete or mask the contract-owned Go coverage,
  race or security evidence.
- Tool failures are visible as failures of the advisory diagnostic rather than
  being converted into a green job by `continue-on-error`.
- Partial runs remain useful for forensics while being impossible to mistake
  for a complete mutation result.
- The repository does not claim unsupported Go branch/function coverage or a
  mutation score that the quality contract does not define.

### Negative

- Go mutation is not a release-blocking 100% metric; promoting it would need a
  separate contract, tool semantics, inventory, equivalent-mutant policy and
  full-score implementation.
- A large diagnostic target set can still exceed its bounded envelope; that
  condition is an explicit failed/incomplete diagnostic and requires measured
  sharding or scheduling work, not a silent retry or exclusion.

## Verification

- `tests/test_go_mutation_governance_contract.py` checks the standalone
  schedule/manual boundary, independence from the required Go coverage job,
  provenance fields, expected-target ledger and unconditional artifact upload.
- `tests/test_workflow_fail_closed_contracts.py` checks that diagnostic
  command errors are not converted into successful workflow paths.
- `quality/quality-contract.json` remains the authority for Go coverage metric
  status and contains no Go mutation requirement.
- Every future current-SHA diagnostic must retain the complete artifact and
  provenance inventory; it must not be used as a substitute for required
  current-SHA coverage/race/static/security evidence.

## Related decisions

- [ADR-015: Go Services Testing Strategy](ADR-015-go-services-testing-strategy.md)
- [ADR-022: Go Services Integration Testing with Testcontainers](ADR-022-go-services-integration-testing-with-testcontainers.md)
- [ADR-034: Helm as the Canonical Application Deployment Artifact](ADR-034-helm-canonical-application-deployment.md)
