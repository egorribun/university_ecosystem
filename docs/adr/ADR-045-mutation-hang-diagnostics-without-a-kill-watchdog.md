# ADR-045: Mutation Hang Diagnostics Without a Kill Watchdog

## Status

Accepted

## Date

2026-09-29

## Context

Organizational task O9 asked for protection against silent stalls in long CI
stages, chiefly the 64 frontend mutation shards. Two mechanisms existed:

- **Progress diagnostic.** The Stryker runner can produce a bounded,
  schema-checked progress record (`frontend/scripts/stryker-progress-*.mjs`).
  The current nightly and manual mutation shard workflows upload `mutation.json`
  and `SHARD_EVIDENCE.json`; they do not upload the progress record. The
  diagnostic is informational and does not change a mutation result.
- **`scripts/quality/heartbeat_watchdog.py`.** A generic wrapper that SIGTERMs
  and then SIGKILLs a command whose output, heartbeat file and CPU time have not
  advanced for a configured window. It was tested (650 lines of tests) but
  called by no workflow, so it protected nothing.

Hangs are already bounded without a killer. A shard has `timeout-minutes: 270`
and an in-process deadline (ADR-039 records the measured envelope: a
16-minute per-test dry run followed by more than two hours of mutation is
normal), and the mutmut groups derive their budgets from the 15x per-PID
watchdog that mutmut itself applies. Mutation results stay fail-closed:
timeouts are never inflated and a timed-out mutant is not relabelled.

## Decision

1. The in-process progress diagnostic plus the existing job ceilings are the
   accepted O9 mechanism. The diagnostic records shard progress without
   changing any verdict; publishing it as a workflow artifact remains
   unimplemented.
2. `scripts/quality/heartbeat_watchdog.py` and `tests/test_heartbeat_watchdog.py`
   are deleted. Wiring a kill switch into mutation jobs would turn a
   diagnostic into a new source of failures: a shard that is slow but healthy
   (the dry run alone is silent for many minutes) would be terminated and
   reported as an infrastructure failure.
3. A future stall killer must first show, from recorded progress records, a
   stall class that the job ceiling does not already bound, and must arrive
   with its own ADR and catalog entry.

## Consequences

- One fewer unused script and 1,000+ lines of tests to maintain.
- A hung shard is still stopped by GitHub at the job ceiling. Current mutation
  shard artifacts contain mutation results and shard evidence, not the progress
  diagnostic, so its last phase and completed-mutant count are not retained as
  a workflow artifact.
- The no-killer decision is accepted; CI artifact availability for the progress
  diagnostic has not been implemented.
