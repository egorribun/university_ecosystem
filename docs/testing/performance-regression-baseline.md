# Performance regression comparison

The required performance jobs compare paired evidence from exact immutable base
and candidate revisions. They do not use a mutable, stored main-branch baseline.

## Native optimizer

`native/rust_ext/benches/conflict_bench.rs` measures conflict detection for
10, 50, 100, and 500 schedule items with Criterion's bencher output. The
`rust-native-regression` job compares 12 paired base/candidate observations.
For non-zero baselines, the comparison fails a named benchmark only when both
its paired median ratio and one-sided 95% bootstrap lower bound exceed 1.10.
Allocation metrics with an all-zero base pass only if the candidate stays zero;
a non-zero candidate fails, and a mixed zero/non-zero base is invalid.

## WebSocket hub

The `ws-hub-regression` job captures each Go benchmark in an isolated
base/candidate pair with
`go test -bench=^<name>$ -run=^$ -benchmem -count=1 -benchtime=1s`.
The helper captures 12 pairs. The same blocking comparison rule applies to
non-zero baselines: both the paired median ratio and one-sided 95% bootstrap
lower bound must exceed 1.10. Allocation metrics use the zero-baseline rule
above.

## Review evidence

For pull requests, the workflow binds the benchmark pair to the immutable PR
base and tested candidate; for a main push, it compares the pre-push and new
commit. The run-bound artifact records source, toolchain, and capture-helper
provenance plus the paired comparison. Include the evidence and a short
explanation for an intentional hot-path change. This lane does not update a
mutable benchmark baseline from local results.
