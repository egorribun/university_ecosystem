# Same-run performance regression gates

**Status:** approved by the repository owner on 2026-08-11. Phase 1 supplies
the protected comparator, container-capture helper, image definition, and
tests; Phase 2 may activate the required workflows only after Phase 1 is in
`main`, so the detached base worktree can supply every trusted tool.

## Problem and decision

The two blocking raw benchmark jobs (`WS-Hub Go Benchmark Regression Gate` and
`Rust Native Optimizer Regression Gate`) currently compare a PR result with a
historical result stored on `gh-pages`. That comparison is not a valid source
regression signal on generic GitHub-hosted hardware: the failed WS-Hub run at
`232e243c6` compared an AMD EPYC 7763 baseline with an Intel Xeon 8370C run,
although the WS-Hub source, Go module inputs, and aggregation script were
identical. Local repeated measurements of identical source also crossed ten
percent on noisy samples.

The repository is public and personal. It has no configured self-hosted runner
or GitHub-hosted larger runner, so requiring a custom runner would permanently
break the existing required contexts. Public PR code must not be routed to a
self-hosted runner.

**Decision:** replace historical cross-run blocking comparisons with a paired,
same-run base-SHA versus head-SHA source regression gate. Keep the existing
`110%` threshold and fail-closed behavior; make historical dashboards
non-blocking evidence only.

## Alternatives considered

1. **Same-run paired comparison (selected).** Both revisions execute in the
   same GitHub-hosted VM with an identical toolchain and an alternating run
   order. This removes the CPU-class change that caused the false positive and
   adds a statistical confidence requirement for noisy samples.
2. **Dedicated GitHub-hosted larger runner.** This would retain a historical
   baseline model, but cannot be configured on this personal repository without
   an organization/plan migration and external provisioning.
3. **Self-hosted runner.** Rejected for this public PR surface: an untrusted
   fork can execute workflow code, making a self-hosted runner unsafe without
   independent isolation and approval controls.

## Architecture

### Revision selection and isolation

Each blocking job remains GitHub-hosted Linux and resolves an immutable base
revision before any benchmark command:

- pull request: `github.event.pull_request.base.sha`;
- push to `main`: `github.event.before`, rejecting the all-zero initial-push
  SHA; and
- manual evidence: a required `base_sha` workflow-dispatch input.

For a pull request, the candidate is `github.sha`, GitHub's immutable synthetic
merge commit, rather than a potentially stale raw head SHA. The workflow
requires the base to be a strict ancestor of the candidate in every mode; this
prevents comparing an unrelated or behind branch with the current base.

The workflow fetches each exact object and creates a detached temporary Git
worktree for the base revision. The normal checkout is the candidate merge/head
revision.
Neither workflow uses `pull_request_target`, a self-hosted label, a repository
variable that selects a runner, nor mutable branch names as the comparison
input.

The comparison decision runs the comparator from the immutable base worktree,
not from candidate/PR source. If that trusted base revision does not yet contain
the comparator, the job fails closed with no candidate fallback. The initial
rollout consequently needs an intentional bootstrap merge before a later
evidence PR can be green under the new trusted-comparator policy.

### Container execution boundary

The Phase-2 workflow delegates capture to the base-worktree helper
`scripts/quality/capture_isolated_benchmarks.py`. Base and candidate benchmark
commands run in separate disposable Docker containers. Each container receives
only its own source worktree mounted read-only at `/src` and a private
per-side cache volume at `/cache`; it receives neither the artifact directory,
the comparator, a Docker socket, nor `GITHUB_*`, `RUNNER_*`, or token
environment variables.

Measurements run with no network, a read-only root filesystem, Docker's
default seccomp profile (never `seccomp=unconfined`), dropped Linux
capabilities, no-new-privileges, a non-root uid, PID/CPU/memory/swap limits,
and bounded tmpfs mounts. A short networked dependency-prefetch run is allowed
only before measurement, with the same source and resource boundary. Raw
stdout is captured by the trusted host helper into a fresh directory beneath
`RUNNER_TEMP`; the helper keeps one non-networked holder container alive for
each private cache volume so Docker daemons that scope tmpfs mounts to a
container cannot discard prefetched dependencies between runs. Short-lived
prefetch, warm-up, and measurement containers attach only to that
side-specific cache. The helper disables GitHub workflow-command parsing while
it captures output, enforces a streaming size limit, and kills an overflowing
capture.

The Go image is digest-pinned. The Rust image is built from a Dockerfile copied
only from the protected base worktree using an empty build context; it never
copies candidate files. This prevents a pull-request checkout from replacing
the measurement harness or host evidence. It is not a cryptographic attestation
of benchmark semantics: a reviewed source change can still emit syntactically
valid but misleading benchmark output. CODEOWNERS, branch protection, and
review remain the control for that residual source-level risk.

### Paired sampling

The workflows collect **twelve pairs** of measurements for each benchmark
suite. Odd-numbered pairs run base then head; even-numbered pairs run head then
base. Each command uses a fixed toolchain, disables test-result caching, warms
the build before recording samples, and writes one raw output file per
revision/pair. This alternation reduces thermal and temporary-host-load drift.

- WS-Hub uses `go test -bench=. -run=^$ -benchmem -count=1 -benchtime=1s ./...`.
- Native Rust uses the existing `conflict_bench` Criterion/bencher command with
  one recorded invocation per side/pair and the same feature flags as today.

Any setup failure, invalid base SHA, command failure, missing output, or an
incomplete pair fails the required job. There is no silent fallback to a
historical `gh-pages` result.

### Comparator

A new pure-Python quality utility parses the existing Go and bencher output
formats into per-benchmark paired samples. It compares lower-is-better metrics:
`ns/op`, `B/op`, and `allocs/op` where present.

The required WS-Hub command always uses `-benchmem`; therefore every accepted
Go record must contain all three of those metrics. Criterion bencher output has
only `ns/iter` (normalized to `ns/op`). Missing expected Go allocation metrics
are invalid evidence rather than a silent latency-only comparison.

For every metric, it requires twelve complete finite pairs and computes the
candidate/base ratio for each pair. It fails only when both conditions hold:

1. the paired median ratio is strictly greater than `1.10`; and
2. a deterministic, one-sided 95% bootstrap lower confidence bound for that
   paired median is strictly greater than `1.10`.

Malformed values, benchmark-name mismatches, duplicates within one sample,
insufficient samples, or an inability to calculate a confidence bound are
integrity failures rather than passes. The JSON result records raw values,
ratios, median, lower bound, threshold, decision, revisions, and toolchain.

`B/op` and `allocs/op` may legitimately be zero. An all-zero base/candidate
allocation metric is recorded as an explicit stable pass; a positive candidate
allocation against an all-zero base is a regression, and mixed zero/nonzero
allocation baselines fail integrity because they have no single finite ratio
distribution. Zero is never accepted for a `ns/op` base measurement.

This retains a real ten-percent blocking threshold while avoiding a claim of
regression from a single noisy or hardware-incomparable sample.

### Evidence, history, and permissions

The required PR jobs publish raw base/head files and the comparison JSON as
artifacts. Historical `benchmark-action` charts may remain useful, but their
alerts cannot decide PR acceptance: their `fail-on-alert` setting is advisory.
Only the paired comparator controls the existing required context names.

History publication is isolated to a main-only publisher job with
`contents: write`. PR and manual-evidence jobs receive `contents: read` and do
not publish or comment. Manual evidence uses distinct job names, takes a
required base SHA, and is never eligible to satisfy a PR ruleset context.

## Files and responsibilities

| File | Change |
| --- | --- |
| `scripts/quality/compare_paired_benchmarks.py` | Pure parser, pairing, deterministic bootstrap, JSON report, and fail-closed CLI. |
| `tests/test_compare_paired_benchmarks.py` | Parser, valid pass/fail, confidence boundary, malformed/missing/mismatched evidence, and deterministic-output tests. |
| `scripts/quality/capture_isolated_benchmarks.py` | Base-trusted isolated Docker capture, bounded host-only raw evidence, and toolchain provenance. |
| `containers/quality/Dockerfile.performance-rust` | Digest-pinned non-root Rust/Python benchmark image built from the base worktree only. |
| `tests/test_capture_isolated_benchmarks.py` | Container boundary, output-cap, manifest-selection, and Dockerfile provenance tests. |
| `.github/workflows/benchmark.yml` | Immutable base retrieval, alternating pair capture, required comparator step, artifact upload, and main-only advisory history publisher. |
| `.github/workflows/manual-performance-evidence.yml` | Required `base_sha`, the same read-only paired evidence path, and distinct manual contexts. |
| `tests/test_quality_workflow_contract.py` | Enforce source-only base/head selection, twelve pairs, alternation, 110% threshold, fail-closed evidence, artifact retention, job permissions, and absence of self-hosted/`pull_request_target` execution. |
| `docs/testing/roadmap-100-percent-quality-closure-plan.md` | Replace the obsolete historical-baseline claim with the current paired-gate policy and live evidence after remote validation. |

## Acceptance criteria

1. Both required context names remain unchanged and block on a statistically
   proven ratio greater than 110%.
2. A workflow-only PR compares identical source revisions in one hosted VM and
   cannot fail solely because a previous run used different hardware.
3. Invalid, missing, or incomplete evidence fails closed.
4. Public PR jobs run only on GitHub-hosted runners with read-only content
   permissions; only a main-only history publisher can write.
5. Unit and workflow-contract tests cover every invariant, and actionlint plus
   YAML parsing pass.
6. Once Phase 1 is on `main`, comparator/workflow changes are code-owned and
   the active ruleset requires code-owner review. Because Phase 1's base lacks
   those new ownership rules, its exceptional bootstrap requires documented
   explicit owner/manual review plus the recorded one-time bypass reason; it
   cannot be presented as enforced CODEOWNERS approval.
7. Phase 1 lands in `main` before the Phase-2 workflow activation; a fresh
   hosted PR run then validates the new gate before roadmap evidence is
   updated; historical dashboard data is not presented as certification.

## Non-goals

This design does not claim that a generic VM can provide a universal absolute
performance baseline or cryptographically attest benchmark semantics, does not
lower the ten-percent threshold, does not hide historical charts, and does not
provision infrastructure or expose a self-hosted runner to public PRs.
