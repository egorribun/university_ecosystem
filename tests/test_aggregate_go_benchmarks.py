from pathlib import Path

import pytest

from scripts.quality.aggregate_go_benchmarks import aggregate_go_benchmarks, main


def test_aggregates_repeated_runs_by_median_and_preserves_metrics() -> None:
    output = """\
goos: linux
goarch: amd64
pkg: example/pkg
BenchmarkLookup-4 100 10.0 ns/op 1 B/op 2 allocs/op
BenchmarkLookup-4 110 40.0 ns/op 3 B/op 4 allocs/op
BenchmarkLookup-4 120 11.0 ns/op 2 B/op 2 allocs/op
BenchmarkLookup-4 130 12.0 ns/op 2 B/op 3 allocs/op
BenchmarkLookup-4 140 9.0 ns/op 2 B/op 2 allocs/op
PASS
ok   example/pkg 5.000s
"""

    aggregated = aggregate_go_benchmarks(output)

    assert aggregated.splitlines() == [
        "goos: linux",
        "goarch: amd64",
        "pkg: example/pkg",
        "BenchmarkLookup-4 120 11 ns/op 2 B/op 2 allocs/op",
        "PASS",
        "ok   example/pkg 5.000s",
    ]


def test_aggregates_each_package_independently() -> None:
    output = """\
pkg: first/pkg
BenchmarkLookup-8 10 2 ns/op
BenchmarkLookup-8 10 4 ns/op
pkg: second/pkg
BenchmarkLookup-8 10 20 ns/op
BenchmarkLookup-8 10 22 ns/op
"""

    aggregated = aggregate_go_benchmarks(output)

    assert aggregated.splitlines() == [
        "pkg: first/pkg",
        "BenchmarkLookup-8 10 3 ns/op",
        "pkg: second/pkg",
        "BenchmarkLookup-8 10 21 ns/op",
    ]


def test_reordered_metrics_are_aggregated_by_unit_not_position() -> None:
    output = (
        "pkg: example/pkg\n"
        "BenchmarkLookup-4 10 10 ns/op 100 B/op\n"
        "BenchmarkLookup-4 20 300 B/op 30 ns/op\n"
    )

    assert aggregate_go_benchmarks(output) == (
        "pkg: example/pkg\nBenchmarkLookup-4 15 20 ns/op 200 B/op\n"
    )


@pytest.mark.parametrize(
    "metrics",
    ["30 ns/op", "30 ns/op 300 allocs/op", "30 ns/op 300 B/op 2 allocs/op"],
)
def test_repeated_benchmark_rejects_changed_metric_set(metrics: str) -> None:
    output = (
        "BenchmarkLookup-4 10 10 ns/op 100 B/op\n"
        f"BenchmarkLookup-4 20 {metrics}\n"
    )

    with pytest.raises(ValueError, match="Inconsistent Go benchmark metric units"):
        aggregate_go_benchmarks(output)


def test_duplicate_metric_units_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate Go benchmark metric unit"):
        aggregate_go_benchmarks("BenchmarkLookup-4 10 10 ns/op 20 ns/op\n")


def test_distinct_benchmarks_may_report_different_metric_sets() -> None:
    output = (
        "BenchmarkLookup-4 10 10 ns/op\n"
        "BenchmarkLookup-8 20 20 ns/op 100 B/op\n"
        "BenchmarkOther-4 30 30 ns/op 2 allocs/op\n"
    )

    assert aggregate_go_benchmarks(output) == output


def test_invalid_metric_schema_does_not_overwrite_output(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    output = tmp_path / "output.txt"
    source.write_text(
        "BenchmarkLookup-4 10 10 ns/op\n"
        "BenchmarkLookup-4 20 30 ns/op 100 B/op\n",
        encoding="utf-8",
    )
    output.write_text("previous verified report\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Inconsistent Go benchmark metric units"):
        main([str(source), "--output", str(output)])

    assert output.read_text(encoding="utf-8") == "previous verified report\n"
