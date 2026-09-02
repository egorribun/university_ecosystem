"""Fail closed when repeated Go benchmark evidence misses an absolute budget."""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median

_PROCESS_SUFFIX_RE = re.compile(r"-\d+$")


class BenchmarkEvidenceError(ValueError):
    """Raised when benchmark evidence is incomplete, invalid, or below budget."""


@dataclass(frozen=True)
class BenchmarkBudgetDecision:
    """Auditable result of evaluating one benchmark metric."""

    benchmark: str
    metric: str
    samples: tuple[float, ...]
    median: float
    minimum: float | None = None
    exclusive_maximum: float | None = None


def _metric_sample(line: str, benchmark: str, metric: str) -> float | None:
    fields = line.split()
    if not fields or not fields[0].startswith("Benchmark"):
        return None
    if _PROCESS_SUFFIX_RE.sub("", fields[0]) != benchmark:
        return None
    if len(fields) < 4 or (len(fields) - 2) % 2:
        raise BenchmarkEvidenceError(f"malformed benchmark record: {line!r}")

    for index in range(2, len(fields), 2):
        if fields[index + 1] != metric:
            continue
        try:
            value = float(fields[index])
        except ValueError as exc:
            raise BenchmarkEvidenceError(
                f"benchmark metric must be numeric: {line!r}"
            ) from exc
        if not math.isfinite(value) or value <= 0:
            raise BenchmarkEvidenceError(
                f"benchmark metric must be finite positive: {line!r}"
            )
        return value

    raise BenchmarkEvidenceError(f"benchmark record has no {metric!r} metric: {line!r}")


def _validated_samples(
    output: str,
    *,
    benchmark: str,
    metric: str,
    expected_samples: int,
) -> tuple[float, ...]:
    if not benchmark or not metric:
        raise BenchmarkEvidenceError("benchmark and metric must be non-empty")
    if expected_samples <= 0:
        raise BenchmarkEvidenceError("expected_samples must be positive")

    samples = tuple(
        value
        for line in output.splitlines()
        if (value := _metric_sample(line, benchmark, metric)) is not None
    )
    if not samples:
        raise BenchmarkEvidenceError(
            f"no samples found for benchmark {benchmark!r} and metric {metric!r}"
        )
    if len(samples) != expected_samples:
        raise BenchmarkEvidenceError(
            f"expected exactly {expected_samples} samples for {benchmark!r}, "
            f"found {len(samples)}"
        )
    return samples


def evaluate_minimum_metric(
    output: str,
    *,
    benchmark: str,
    metric: str,
    minimum: float,
    expected_samples: int,
) -> BenchmarkBudgetDecision:
    """Validate complete evidence and require its median to meet ``minimum``."""

    if not math.isfinite(minimum) or minimum <= 0:
        raise BenchmarkEvidenceError("minimum must be finite positive")
    samples = _validated_samples(
        output,
        benchmark=benchmark,
        metric=metric,
        expected_samples=expected_samples,
    )

    observed_median = float(median(samples))
    if observed_median < minimum:
        raise BenchmarkEvidenceError(
            f"{benchmark} median {observed_median:g} {metric} is below required "
            f"minimum {minimum:g} {metric}"
        )
    return BenchmarkBudgetDecision(
        benchmark=benchmark,
        metric=metric,
        samples=samples,
        median=observed_median,
        minimum=minimum,
    )


def evaluate_exclusive_maximum_metric(
    output: str,
    *,
    benchmark: str,
    metric: str,
    exclusive_maximum: float,
    expected_samples: int,
) -> BenchmarkBudgetDecision:
    """Require the evidence median to be strictly below ``exclusive_maximum``."""

    if not math.isfinite(exclusive_maximum) or exclusive_maximum <= 0:
        raise BenchmarkEvidenceError("exclusive_maximum must be finite positive")
    samples = _validated_samples(
        output,
        benchmark=benchmark,
        metric=metric,
        expected_samples=expected_samples,
    )

    observed_median = float(median(samples))
    if observed_median >= exclusive_maximum:
        raise BenchmarkEvidenceError(
            f"{benchmark} median {observed_median:g} {metric} does not satisfy "
            f"exclusive maximum {exclusive_maximum:g} {metric}"
        )
    return BenchmarkBudgetDecision(
        benchmark=benchmark,
        metric=metric,
        samples=samples,
        median=observed_median,
        exclusive_maximum=exclusive_maximum,
    )


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Raw `go test -bench` output")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--metric", required=True)
    bound = parser.add_mutually_exclusive_group(required=True)
    bound.add_argument("--minimum", type=float)
    bound.add_argument("--exclusive-maximum", type=float)
    parser.add_argument("--expected-samples", required=True, type=int)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    try:
        output = arguments.input.read_text(encoding="utf-8")
        if arguments.minimum is not None:
            decision = evaluate_minimum_metric(
                output,
                benchmark=arguments.benchmark,
                metric=arguments.metric,
                minimum=arguments.minimum,
                expected_samples=arguments.expected_samples,
            )
            comparison = f">= {arguments.minimum:g}"
        else:
            decision = evaluate_exclusive_maximum_metric(
                output,
                benchmark=arguments.benchmark,
                metric=arguments.metric,
                exclusive_maximum=arguments.exclusive_maximum,
                expected_samples=arguments.expected_samples,
            )
            comparison = f"< {arguments.exclusive_maximum:g}"
    except (BenchmarkEvidenceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"{decision.benchmark}: median {decision.median:g} {decision.metric} "
        f"{comparison} {decision.metric} "
        f"({len(decision.samples)} samples)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
