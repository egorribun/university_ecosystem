# Performance regression baseline

This document defines the repeatable performance evidence used by the quality
roadmap. A benchmark report is not a pass by itself: the stored main-branch
baseline and the blocking regression threshold are both required.

## Native optimizer

`native/rust_ext/benches/conflict_bench.rs` measures conflict detection for
10, 50, 100, and 500 schedule items with Criterion's bencher output. The
`rust-native-regression` job stores the main-branch series and fails when any
named benchmark is at least 110% of its stored baseline.

## WebSocket hub

The `ws-hub-regression` job runs every benchmark with `-benchtime=1s
-count=5 -benchmem`. Five samples make the comparison less sensitive to a
single noisy runner. It uses a blocking 110% alert threshold on pull requests
and main pushes; the job is not report-only.

## Baseline changes

The first successful main run establishes a baseline. Intentional changes to a
hot path must include the benchmark evidence and a short explanation in the
pull request. The baseline is updated only by the pinned benchmark action on a
successful main push, never by a local force-update.
