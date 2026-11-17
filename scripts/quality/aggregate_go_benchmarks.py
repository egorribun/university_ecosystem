"""Aggregate repeated ``go test -bench`` samples for benchmark-action.

The Go tool emits one line per ``-count`` sample, but benchmark-action treats
each line with the same name as a separate result.  Keeping only the median
sample makes the regression comparison deterministic without changing its
threshold or the benchmark workload.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

_PROCESS_SUFFIX_RE = re.compile(r"-(?P<procs>\d+)$")


@dataclass(frozen=True)
class _Sample:
    benchmark_name: str
    process_suffix: str
    iterations: int
    metrics: tuple[tuple[float, str], ...]


@dataclass
class _Section:
    package_line: str | None
    other_lines: list[str] = field(default_factory=list)
    samples: OrderedDict[tuple[str, str], list[_Sample]] = field(
        default_factory=OrderedDict
    )


def _parse_sample(line: str) -> _Sample | None:
    fields = line.split()
    if not fields or not fields[0].startswith("Benchmark"):
        return None
    if len(fields) < 4 or (len(fields) - 2) % 2:
        raise ValueError(f"Malformed Go benchmark line: {line!r}")

    benchmark_token = fields[0]
    process_match = _PROCESS_SUFFIX_RE.search(benchmark_token)
    if process_match is None:
        benchmark_name = benchmark_token
        process_suffix = ""
    else:
        benchmark_name = benchmark_token[: process_match.start()]
        process_suffix = f"-{process_match.group('procs')}"

    metrics: list[tuple[float, str]] = []
    seen_units: set[str] = set()
    for index in range(2, len(fields), 2):
        try:
            value = float(fields[index])
        except ValueError as exc:
            raise ValueError(f"Malformed Go benchmark metric: {line!r}") from exc
        unit = fields[index + 1]
        if unit in seen_units:
            raise ValueError(f"Duplicate Go benchmark metric unit: {unit!r}")
        seen_units.add(unit)
        metrics.append((value, unit))

    return _Sample(
        benchmark_name=benchmark_name,
        process_suffix=process_suffix,
        iterations=int(fields[1]),
        metrics=tuple(metrics),
    )


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".15g")


def _render_section(section: _Section) -> list[str]:
    lines: list[str] = []
    if section.package_line is not None:
        lines.append(section.package_line)

    for samples in section.samples.values():
        first = samples[0]
        by_unit = [
            {unit: value for value, unit in sample.metrics} for sample in samples
        ]
        metric_values = [
            (median(metrics[unit] for metrics in by_unit), unit)
            for _, unit in first.metrics
        ]
        iterations = int(median(sample.iterations for sample in samples))
        fields = [
            f"{first.benchmark_name}{first.process_suffix}",
            str(iterations),
        ]
        for value, unit in metric_values:
            fields.extend((_format_number(value), unit))
        lines.append(" ".join(fields))

    lines.extend(section.other_lines)
    return lines


def aggregate_go_benchmarks(output: str) -> str:
    """Return per-unit medians for each package/name with a stable metric set."""

    preamble: list[str] = []
    sections: list[_Section] = []
    current: _Section | None = None

    for line in output.splitlines():
        if line.startswith("pkg:"):
            current = _Section(package_line=line)
            sections.append(current)
            continue

        sample = _parse_sample(line)
        if sample is not None:
            if current is None:
                current = _Section(package_line=None)
                sections.append(current)
            key = (sample.benchmark_name, sample.process_suffix)
            samples = current.samples.setdefault(key, [])
            if samples and {unit for _, unit in sample.metrics} != {
                unit for _, unit in samples[0].metrics
            }:
                raise ValueError(
                    f"Inconsistent Go benchmark metric units: {sample.benchmark_name}"
                )
            samples.append(sample)
            continue

        if current is None:
            preamble.append(line)
        else:
            current.other_lines.append(line)

    lines = preamble
    for section in sections:
        lines.extend(_render_section(section))
    return "\n".join(lines) + ("\n" if lines else "")


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=str,
        nargs="?",
        default="-",
        help="Raw Go benchmark output path, or '-' for stdin",
    )
    parser.add_argument("-o", "--output", type=Path, help="Aggregated output path")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    raw_output = (
        sys.stdin.read()
        if arguments.input == "-"
        else Path(arguments.input).read_text(encoding="utf-8")
    )
    aggregated = aggregate_go_benchmarks(raw_output)
    if arguments.output is None:
        print(aggregated, end="")
    else:
        arguments.output.write_text(aggregated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
