# ADR-039: Frontend Mutation Shard Cost Model

## Status

Accepted

## Date

2026-09-21

## Context

`frontend/scripts/run-stryker.mjs` partitions the Stryker mutation universe
into a fixed 64 logical shards. A first attempt has no historical timing
model, so the planner falls back to a checked-in table,
`firstAttemptSourceCostWeights`, that assigns each source a "relative
placement cost". A source whose weight exceeds one is treated as *expensive*
and routed into a cost-aware lane; everything else is packed by locality and
mutant count.

That table has been maintained reactively: when a shard reached its deadline,
the sources it carried were given a "timeout guard weight" annotated with the
offending run. Runs 33863748227, 33994803565, 34003977528, 34634679511,
34743194178, 35023906328, 35160102569 and 35327250942 each contributed
entries or tuning constants this way. Despite that, shard 26/64 reached its
in-process deadline in three consecutive runs (35470088045 at 9,900,000 ms,
35517610350 at 13,500,000 ms).

Run 35517610350 is the first run that makes the table measurable. Sixty-three
of its sixty-four shards completed and uploaded `mutation.json`, which records
`static` and `testsCompleted` for every mutant, and the preflight artifact
records the exact plan those shards executed. Replaying the planner offline
against that artifact reproduces the shipped plan byte for byte, so the model
and the outcome can be compared directly.

Correlating each shard's measured wall time against candidate predictors:

| predictor | Pearson r |
|:---|---:|
| planner `estimatedCost` (the checked-in weights) | **-0.03** |
| mutant count | 0.42 |
| measured `testsCompleted` | **0.82** |

The weight table does not predict cost. It is uncorrelated noise, which is why
adding entries to it has not stopped the same shard from timing out. The
symptom is visible directly in the plan: shard 26 ran 225 minutes for 1,418
mutants while shard 62 ran 39 minutes for 1,086, and shard 1 ran 111 minutes
for 127.

Five candidate repairs were replanned offline against that same universe and
scored against the measured cost of the resulting lanes:

| change | worst lane |
|:---|:---|
| as shipped | 1,418 mutants / 61,554 measured cost |
| `firstAttemptRegularMutantsPerShard` 1,024 → 256 | unchanged (inert; `Math.max(1_024, …)` clamps it) |
| shard-26 sources → `firstAttemptStaticHotspotFiles` | 1,447 mutants (worse) |
| `firstAttemptUnitSplitFactor` 16 → 24/32/48 | 4,069 mutants (much worse) |
| shard-26 sources → `firstAttemptDedicatedFiles` (3/5/8/12) | 3,078-17,224 mutants (much worse) |
| weight table replaced with measured tests-per-mutant | 3,978 mutants / 81,766 cost (worse) |

The first-attempt packer is a lane-reservation and locality heuristic, not a
cost balancer; it reads a weight only as a binary "expensive" flag. Feeding it
better numbers does not make it balance, and spending lanes on isolation makes
the remaining lanes denser. The 64-lane budget is saturated.

Supplying the same measured costs through the planner's *other* input does
work. `planMutationShards` already accepts a `historicalCosts` map and, when
present, balances on cost instead of count. Planning run 35517610350's
universe with per-source costs derived from its own reports lowers the
measured cost imbalance from **48.9x to 8.4x** and the largest lane from 1,418
to 1,259 mutants.

That path is implemented — `buildHistoricalCostArtifact`,
`historicalCostModelCosts` and the `STRYKER_HISTORICAL_COSTS_ARTIFACT`
contract all exist in `run-stryker.mjs` — but no workflow produces or consumes
the artifact, and `validatedHistoricalCosts` requires a cost for every viable
source. A complete 64-shard run is therefore a precondition for enabling it,
and no complete run exists: shard 26 has never finished.

## Decision

The reactive weight table is closed to new entries. A shard that reaches its
deadline is not to be answered by adding a `timeout guard weight`, because
that mechanism has been measured and does not work.

Until the historical cost model is wired in, the frontend shard envelope is
sized from measurement rather than from re-planning. The shard job cap is 270
minutes and the in-process Stryker deadline is 15,300,000 ms (255 minutes),
keeping the in-process deadline strictly below the job cap so the runner
reports its own overrun and the evidence upload still runs (the property
ADR-era run 35327250942 established). The 64-shard critical path is bounded by
throughput, not by any single shard — 1,842 measured shard-minutes at
`max-parallel: 6` is roughly 307 minutes — so a higher per-job ceiling costs
no additional wall clock.

This envelope is explicitly a means, not an end: its purpose is to let one
complete 64-shard run exist so the cost model can be bootstrapped.

## Consequences

A frontend mutation shard may now occupy a runner for up to 270 minutes. The
measured aggregate is unchanged, so the wall-clock cost of the matrix is
unchanged.

The weight table remains in the source because removing it would reshuffle
every lane, and a reshuffle cannot be validated offline against wall time. It
is frozen, not deleted; its entries retain their provenance comments as
history.

Wiring the historical cost model remains open work. It requires a producer
step that publishes `HISTORICAL_COSTS.json` from a completed run, a consumer
that restores it on a later run, and a decision about how a cost artifact ages
against a moving source inventory. Until then the envelope above is the only
thing standing between shard 26 and a red gate, and this ADR is the record of
why no planner change accompanies it.

## References

- `frontend/scripts/run-stryker.mjs` — `planMutationShards`,
  `validatedHistoricalCosts`, `assignFirstAttemptMutationUnits`,
  `firstAttemptSourceCostWeights`
- `.github/workflows/ci.yml` — `stryker-shards`
- `.github/workflows/nightly-full-gate.yml`,
  `.github/workflows/manual-mutation-evidence.yml`
- `quality/ci-check-catalog.json` — expected timeout and duration
- Run 35517610350 — the preflight artifact and 63 shard reports this ADR
  measures
