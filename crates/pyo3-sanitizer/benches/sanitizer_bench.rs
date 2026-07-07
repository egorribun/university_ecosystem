//! Criterion benchmarks for `pyo3_sanitizer`.
//!
//! Run with:  `cargo bench -p pyo3-sanitizer`
//! HTML reports land in `target/criterion/`.
//!
//! WHY these inputs:
//!  - "empty"       → baseline / zero-work branch
//!  - "plain_text"  → no-parse-tree fast path
//!  - "simple_html" → realistic short user content
//!  - "xss_attempt" → worst-case attribute/tag scrubbing
//!  - "large"       → throughput ceiling with 100 repeated paragraphs

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use pyo3_sanitizer::{sanitize_html_basic, sanitize_rich_text, strip_html};

/// Build the benchmark inputs once so allocation cost is outside the hot loop.
fn build_inputs() -> Vec<(&'static str, String)> {
    vec![
        ("empty", String::new()),
        ("plain_text", "Hello, world! No markup here.".to_owned()),
        (
            "simple_html",
            "<p>Hello <b>world</b></p><ul><li>item</li></ul>".to_owned(),
        ),
        (
            "xss_attempt",
            "<script>alert('xss')</script><p>safe <a href='javascript:void(0)'>click</a></p>"
                .to_owned(),
        ),
        // ~2.7 KiB: 100 × "<p>Hello world</p>"
        ("large", "<p>Hello world</p>".repeat(100)),
    ]
}

fn bench_sanitize_rich_text(c: &mut Criterion) {
    let inputs = build_inputs();
    let mut group = c.benchmark_group("sanitize_rich_text");

    for (name, input) in &inputs {
        group.bench_with_input(BenchmarkId::from_parameter(name), input, |b, i| {
            b.iter(|| sanitize_rich_text(i));
        });
    }
    group.finish();
}

fn bench_sanitize_html_basic(c: &mut Criterion) {
    let inputs = build_inputs();
    let mut group = c.benchmark_group("sanitize_html_basic");

    for (name, input) in &inputs {
        group.bench_with_input(BenchmarkId::from_parameter(name), input, |b, i| {
            b.iter(|| sanitize_html_basic(i));
        });
    }
    group.finish();
}

fn bench_strip_html(c: &mut Criterion) {
    let inputs = build_inputs();
    let mut group = c.benchmark_group("strip_html");

    for (name, input) in &inputs {
        group.bench_with_input(BenchmarkId::from_parameter(name), input, |b, i| {
            b.iter(|| strip_html(i));
        });
    }
    group.finish();
}

criterion_group!(
    benches,
    bench_sanitize_rich_text,
    bench_sanitize_html_basic,
    bench_strip_html
);
criterion_main!(benches);
