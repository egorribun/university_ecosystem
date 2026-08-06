from scripts.quality.aggregate_go_benchmarks import aggregate_go_benchmarks


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
