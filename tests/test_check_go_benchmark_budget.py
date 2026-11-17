from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality.check_go_benchmark_budget import (
    BenchmarkEvidenceError,
    evaluate_exclusive_maximum_metric,
    evaluate_minimum_metric,
    main,
)


def _gateway_samples(values: tuple[int, ...]) -> str:
    return "\n".join(
        f"BenchmarkHashRingLookup-8 500000 1000 ns/op {value} lookups/s"
        for value in values
    )


def test_accepts_the_median_at_the_absolute_lookup_budget() -> None:
    decision = evaluate_minimum_metric(
        _gateway_samples((240_000, 250_000, 260_000, 270_000, 230_000)),
        benchmark="BenchmarkHashRingLookup",
        metric="lookups/s",
        minimum=250_000,
        expected_samples=5,
    )

    assert decision.median == 250_000
    assert decision.minimum == 250_000
    assert decision.samples == (240_000, 250_000, 260_000, 270_000, 230_000)


def test_rejects_a_median_below_the_absolute_lookup_budget() -> None:
    with pytest.raises(BenchmarkEvidenceError, match="below required minimum"):
        evaluate_minimum_metric(
            _gateway_samples((249_999, 240_000, 250_000, 260_000, 230_000)),
            benchmark="BenchmarkHashRingLookup",
            metric="lookups/s",
            minimum=250_000,
            expected_samples=5,
        )


def test_accepts_less_than_4000_ns_per_op() -> None:
    decision = evaluate_exclusive_maximum_metric(
        _gateway_samples((260_000, 250_000, 240_000, 230_000, 270_000)).replace(
            "1000 ns/op", "3999 ns/op"
        ),
        benchmark="BenchmarkHashRingLookup",
        metric="ns/op",
        exclusive_maximum=4_000,
        expected_samples=5,
    )

    assert decision.median == 3_999
    assert decision.exclusive_maximum == 4_000


@pytest.mark.parametrize("slow_median", [4_000, 4_001])
def test_rejects_4000_or_more_ns_per_op(slow_median: int) -> None:
    output = "\n".join(
        f"BenchmarkHashRingLookup-8 500000 {value} ns/op 250000 lookups/s"
        for value in (slow_median,) * 5
    )

    with pytest.raises(BenchmarkEvidenceError, match="does not satisfy exclusive"):
        evaluate_exclusive_maximum_metric(
            output,
            benchmark="BenchmarkHashRingLookup",
            metric="ns/op",
            exclusive_maximum=4_000,
            expected_samples=5,
        )


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (_gateway_samples((300_000,) * 4), "expected exactly 5 samples"),
        ("BenchmarkOther-8 1 1 ns/op 300000 lookups/s", "no samples"),
        (
            "BenchmarkHashRingLookup-8 1 1 ns/op NaN lookups/s",
            "finite positive",
        ),
    ],
)
def test_rejects_incomplete_or_invalid_benchmark_evidence(
    output: str, message: str
) -> None:
    with pytest.raises(BenchmarkEvidenceError, match=message):
        evaluate_minimum_metric(
            output,
            benchmark="BenchmarkHashRingLookup",
            metric="lookups/s",
            minimum=250_000,
            expected_samples=5,
        )


@pytest.mark.parametrize(
    "truncated_target",
    [
        "BenchmarkHashRingLookup-8",
        "BenchmarkHashRingLookup-8 500000",
        "BenchmarkHashRingLookup-8 500000 1000",
    ],
)
def test_rejects_an_extra_truncated_target_record(truncated_target: str) -> None:
    output = f"{_gateway_samples((300_000,) * 5)}\n{truncated_target}"

    with pytest.raises(BenchmarkEvidenceError, match="malformed benchmark record"):
        evaluate_exclusive_maximum_metric(
            output,
            benchmark="BenchmarkHashRingLookup",
            metric="ns/op",
            exclusive_maximum=4_000,
            expected_samples=5,
        )


@pytest.mark.parametrize(
    "metrics",
    [
        "1000 ns/op 9000 ns/op",
        "9000 ns/op 1000 ns/op",
        "1000 ns/op 1000 ns/op",
        "1000 ns/op 0 B/op 1 B/op",
    ],
)
def test_maximum_rejects_duplicate_metric_units(metrics: str) -> None:
    output = f"BenchmarkHashRingLookup-8 500000 {metrics}"

    with pytest.raises(BenchmarkEvidenceError, match="duplicate metric unit"):
        evaluate_exclusive_maximum_metric(
            output,
            benchmark="BenchmarkHashRingLookup",
            metric="ns/op",
            exclusive_maximum=4_000,
            expected_samples=1,
        )


@pytest.mark.parametrize(
    "metrics",
    ["300000 lookups/s 1 lookups/s", "1 lookups/s 300000 lookups/s"],
)
def test_minimum_rejects_duplicate_metric_units(metrics: str) -> None:
    output = f"BenchmarkHashRingLookup-8 500000 {metrics}"

    with pytest.raises(BenchmarkEvidenceError, match="duplicate metric unit"):
        evaluate_minimum_metric(
            output,
            benchmark="BenchmarkHashRingLookup",
            metric="lookups/s",
            minimum=250_000,
            expected_samples=1,
        )


def test_distinct_metrics_remain_valid_in_any_order() -> None:
    decision = evaluate_exclusive_maximum_metric(
        "BenchmarkHashRingLookup-8 500000 0 B/op 300000 lookups/s 1000 ns/op",
        benchmark="BenchmarkHashRingLookup",
        metric="ns/op",
        exclusive_maximum=4_000,
        expected_samples=1,
    )

    assert decision.median == 1000


def test_cli_rejects_duplicate_units_without_success_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "benchmark.txt"
    source.write_text(
        "BenchmarkHashRingLookup-8 500000 1000 ns/op 9000 ns/op\n",
        encoding="utf-8",
    )

    result = main(
        [
            str(source),
            "--benchmark",
            "BenchmarkHashRingLookup",
            "--metric",
            "ns/op",
            "--exclusive-maximum",
            "4000",
            "--expected-samples",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "duplicate metric unit" in captured.err
