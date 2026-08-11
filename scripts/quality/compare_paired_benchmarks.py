"""Compare complete same-run benchmark pairs with a deterministic confidence gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import tempfile
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median

EXPECTED_PAIRS = 12
THRESHOLD_RATIO = 1.10
BOOTSTRAP_ITERATIONS = 10_000
CONFIDENCE = 0.95

_ALLOCATION_METRICS = frozenset({"B/op", "allocs/op"})
_GO_METRICS = frozenset({"ns/op", *_ALLOCATION_METRICS})
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_GO_BENCHMARK_RE = re.compile(r"^Benchmark\S+$")
_GO_PACKAGE_RE = re.compile(r"^pkg:\s+(?P<package>\S+)$")
_PROCESS_SUFFIX_RE = re.compile(r"-\d+$")
_INTEGER_RE = re.compile(r"^\d+$")
_GO_NUMBER_RE = re.compile(r"^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_BENCHER_NUMBER_RE = re.compile(
    r"^(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)
_BENCHER_RECORD_RE = re.compile(
    r"^\s*test\s+(?P<benchmark>\S+)\s+\.\.\.\s+bench:\s+"
    r"(?P<value>(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s+ns/iter(?:\s+.*)?$"
)

MetricKey = tuple[str, str]
PairedValues = tuple[tuple[float, ...], tuple[float, ...]]
BenchmarkParser = Callable[[str], dict[str, dict[str, float]]]


class EvidenceIntegrityError(ValueError):
    """Raised when raw benchmark evidence cannot support a safe decision."""


@dataclass(frozen=True)
class BenchmarkSample:
    """One finite lower-is-better measurement from a raw benchmark file."""

    benchmark: str
    metric: str
    value: float


@dataclass(frozen=True)
class MetricComparison:
    """The complete, auditable decision for one benchmark metric."""

    benchmark: str
    metric: str
    base_values: tuple[float, ...]
    candidate_values: tuple[float, ...]
    ratios: tuple[float | None, ...]
    median_ratio: float | None
    one_sided_95_lower_bound: float | None
    comparison_mode: str
    decision: str

    def to_dict(self) -> dict[str, object]:
        return {
            "benchmark": self.benchmark,
            "metric": self.metric,
            "base_values": list(self.base_values),
            "candidate_values": list(self.candidate_values),
            "ratios": list(self.ratios),
            "median_ratio": self.median_ratio,
            "one_sided_95_lower_bound": self.one_sided_95_lower_bound,
            "comparison_mode": self.comparison_mode,
            "decision": self.decision,
        }


@dataclass(frozen=True)
class ComparisonResult:
    """A versioned report suitable for an immutable CI artifact."""

    format_name: str
    base_revision: str
    candidate_revision: str
    expected_pairs: int
    toolchain: Mapping[str, object]
    decision: str
    metrics: tuple[MetricComparison, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": 1,
            "format": self.format_name,
            "base_revision": self.base_revision,
            "candidate_revision": self.candidate_revision,
            "expected_pairs": self.expected_pairs,
            "threshold_ratio": THRESHOLD_RATIO,
            "toolchain": dict(self.toolchain),
            "decision": self.decision,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }
        if self.error is not None:
            result["error"] = self.error
        return result


def _parse_measurement(
    token: str,
    *,
    line: str,
    number_pattern: re.Pattern[str],
    allow_commas: bool = False,
) -> float:
    if number_pattern.fullmatch(token) is None:
        raise EvidenceIntegrityError(f"Malformed benchmark measurement in {line!r}")

    value = float(token.replace(",", "") if allow_commas else token)
    if not math.isfinite(value) or value < 0:
        raise EvidenceIntegrityError(f"Non-finite or negative measurement in {line!r}")
    return value


def parse_go_benchmark_output(text: str) -> dict[str, dict[str, float]]:
    """Parse canonical ``go test -bench -benchmem`` output without guessing."""

    records: dict[str, dict[str, float]] = {}
    current_package: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("pkg:"):
            package_match = _GO_PACKAGE_RE.fullmatch(line)
            if package_match is None:
                raise EvidenceIntegrityError(f"Malformed Go package identity: {line!r}")
            current_package = package_match.group("package")
            continue
        if not line.startswith("Benchmark"):
            continue
        if current_package is None:
            raise EvidenceIntegrityError(
                f"Go benchmark record has no package identity: {line!r}"
            )

        fields = line.split()
        if len(fields) < 4 or (len(fields) - 2) % 2:
            raise EvidenceIntegrityError(f"Malformed Go benchmark record: {line!r}")

        benchmark_token = fields[0]
        if _GO_BENCHMARK_RE.fullmatch(benchmark_token) is None:
            raise EvidenceIntegrityError(f"Malformed Go benchmark name: {line!r}")
        benchmark = f"{current_package}::{_PROCESS_SUFFIX_RE.sub('', benchmark_token)}"
        if benchmark in records:
            raise EvidenceIntegrityError(
                f"Duplicate Go benchmark record for {benchmark!r} in one file"
            )

        if _INTEGER_RE.fullmatch(fields[1]) is None or int(fields[1]) <= 0:
            raise EvidenceIntegrityError(f"Malformed Go benchmark iterations: {line!r}")

        metrics: dict[str, float] = {}
        for index in range(2, len(fields), 2):
            value = _parse_measurement(
                fields[index], line=line, number_pattern=_GO_NUMBER_RE
            )
            metric = fields[index + 1]
            if metric not in _GO_METRICS:
                raise EvidenceIntegrityError(
                    f"Unsupported Go benchmark metric {metric!r} in {line!r}"
                )
            if metric in metrics:
                raise EvidenceIntegrityError(
                    f"Duplicate Go benchmark metric {metric!r} in {line!r}"
                )
            metrics[metric] = value

        if set(metrics) != _GO_METRICS:
            raise EvidenceIntegrityError(
                f"Incomplete Go benchmark metric set in {line!r}; expected "
                "ns/op, B/op, and allocs/op"
            )
        records[benchmark] = metrics
    return records


def parse_bencher_output(text: str) -> dict[str, dict[str, float]]:
    """Parse Criterion's canonical bencher output as the common ``ns/op`` unit."""

    records: dict[str, dict[str, float]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = _BENCHER_RECORD_RE.fullmatch(line)
        if match is None:
            if line.startswith("test ") and "bench:" in line:
                raise EvidenceIntegrityError(
                    f"Malformed bencher benchmark record: {line!r}"
                )
            continue

        benchmark = match.group("benchmark")
        if benchmark in records:
            raise EvidenceIntegrityError(
                f"Duplicate bencher benchmark record for {benchmark!r} in one file"
            )
        records[benchmark] = {
            "ns/op": _parse_measurement(
                match.group("value"),
                line=line,
                number_pattern=_BENCHER_NUMBER_RE,
                allow_commas=True,
            )
        }
    return records


def _pair_paths(directory: Path, expected_pairs: int) -> tuple[Path, ...]:
    if expected_pairs != EXPECTED_PAIRS:
        raise EvidenceIntegrityError(
            f"Expected pair count must be exactly {EXPECTED_PAIRS}, got {expected_pairs}"
        )
    if not directory.is_dir():
        raise EvidenceIntegrityError(f"Evidence directory does not exist: {directory}")

    expected_names = {f"pair-{index:02d}.txt" for index in range(1, expected_pairs + 1)}
    unexpected = sorted(
        entry.name for entry in directory.iterdir() if entry.name not in expected_names
    )
    if unexpected:
        raise EvidenceIntegrityError(
            f"Unexpected pair evidence entry(s) in {directory}: {', '.join(unexpected)}"
        )

    paths = tuple(
        directory / f"pair-{index:02d}.txt" for index in range(1, expected_pairs + 1)
    )
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise EvidenceIntegrityError(
            f"Missing pair evidence file(s) in {directory}: {', '.join(missing)}"
        )
    return paths


def _as_samples(
    records: dict[str, dict[str, float]],
) -> dict[MetricKey, BenchmarkSample]:
    if not records:
        raise EvidenceIntegrityError(
            "Benchmark evidence file contains no supported records"
        )

    samples: dict[MetricKey, BenchmarkSample] = {}
    for benchmark, metrics in records.items():
        if not benchmark or not metrics:
            raise EvidenceIntegrityError(
                "Benchmark evidence contains an empty identity or metric set"
            )
        for metric, value in metrics.items():
            if not math.isfinite(value) or value < 0:
                raise EvidenceIntegrityError(
                    f"Non-finite or negative value for {benchmark!r} / {metric!r}"
                )
            key = (benchmark, metric)
            if key in samples:
                raise EvidenceIntegrityError(
                    f"Duplicate benchmark metric {benchmark!r} / {metric!r}"
                )
            samples[key] = BenchmarkSample(benchmark, metric, value)
    return samples


def load_paired_samples(
    base_dir: Path,
    candidate_dir: Path,
    expected_pairs: int,
    parser: BenchmarkParser,
) -> dict[MetricKey, PairedValues]:
    """Load exactly twelve canonical pairs and require one stable metric universe."""

    base_paths = _pair_paths(base_dir, expected_pairs)
    candidate_paths = _pair_paths(candidate_dir, expected_pairs)
    collected: dict[MetricKey, tuple[list[float], list[float]]] = {}
    expected_keys: set[MetricKey] | None = None

    for index, (base_path, candidate_path) in enumerate(
        zip(base_paths, candidate_paths, strict=True), start=1
    ):
        try:
            base_records = parser(base_path.read_text(encoding="utf-8"))
            candidate_records = parser(candidate_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise EvidenceIntegrityError(
                f"Unable to read pair {index:02d} evidence: {exc}"
            ) from exc

        base_samples = _as_samples(base_records)
        candidate_samples = _as_samples(candidate_records)
        base_keys = set(base_samples)
        candidate_keys = set(candidate_samples)
        if base_keys != candidate_keys:
            raise EvidenceIntegrityError(
                f"Base/candidate benchmark metrics differ in pair {index:02d}"
            )
        if expected_keys is None:
            expected_keys = base_keys
            for key in sorted(expected_keys):
                collected[key] = ([], [])
        elif base_keys != expected_keys:
            raise EvidenceIntegrityError(
                f"Benchmark metric set differs from pair 01 in pair {index:02d}"
            )

        for key in sorted(base_keys):
            base_values, candidate_values = collected[key]
            base_values.append(base_samples[key].value)
            candidate_values.append(candidate_samples[key].value)

    if expected_keys is None:
        raise EvidenceIntegrityError("No paired benchmark evidence was loaded")
    return {
        key: (tuple(base_values), tuple(candidate_values))
        for key, (base_values, candidate_values) in sorted(collected.items())
    }


def _validate_pair_values(
    base_values: Sequence[float], candidate_values: Sequence[float]
) -> None:
    if not base_values or len(base_values) != len(candidate_values):
        raise EvidenceIntegrityError(
            "Base and candidate measurements must be non-empty pairs"
        )
    for value in (*base_values, *candidate_values):
        if not math.isfinite(value) or value < 0:
            raise EvidenceIntegrityError(
                "Benchmark measurements must be finite and non-negative"
            )


def _ratios(
    base_values: Sequence[float], candidate_values: Sequence[float]
) -> tuple[float, ...]:
    _validate_pair_values(base_values, candidate_values)
    if any(value <= 0 for value in base_values):
        raise EvidenceIntegrityError(
            "Relative benchmark comparisons require positive base values"
        )
    ratios = tuple(
        candidate / base
        for base, candidate in zip(base_values, candidate_values, strict=True)
    )
    if any(not math.isfinite(value) for value in ratios):
        raise EvidenceIntegrityError("Benchmark ratios must be finite")
    return ratios


def paired_median_ratio(
    base_values: Sequence[float], candidate_values: Sequence[float]
) -> float:
    """Return the paired median candidate/base ratio for finite positive bases."""

    return float(median(_ratios(base_values, candidate_values)))


def bootstrap_lower_bound(
    ratios: Sequence[float],
    confidence: float = CONFIDENCE,
    iterations: int = BOOTSTRAP_ITERATIONS,
    *,
    benchmark: str = "",
    metric: str = "",
) -> float:
    """Return a deterministic one-sided bootstrap lower bound for paired ratios."""

    if not ratios:
        raise EvidenceIntegrityError("Cannot bootstrap an empty ratio distribution")
    if not 0 < confidence < 1 or iterations <= 0:
        raise EvidenceIntegrityError(
            "Bootstrap confidence and iteration count are invalid"
        )
    if any(not math.isfinite(value) or value < 0 for value in ratios):
        raise EvidenceIntegrityError("Bootstrap ratios must be finite and non-negative")

    identity = json.dumps(
        {"benchmark": benchmark, "metric": metric, "ratios": list(ratios)},
        sort_keys=True,
        separators=(",", ":"),
    )
    seed = int.from_bytes(hashlib.sha256(identity.encode("utf-8")).digest())
    generator = random.Random(seed)  # noqa: S311 - deterministic statistical bootstrap.
    sample_size = len(ratios)
    bootstrap_medians = [
        float(
            median(
                tuple(
                    ratios[generator.randrange(sample_size)] for _ in range(sample_size)
                )
            )
        )
        for _ in range(iterations)
    ]
    bootstrap_medians.sort()
    index = math.floor((1 - confidence) * iterations)
    return bootstrap_medians[index]


def _comparison_for_metric(
    benchmark: str,
    metric: str,
    base_values: tuple[float, ...],
    candidate_values: tuple[float, ...],
) -> MetricComparison:
    _validate_pair_values(base_values, candidate_values)

    if metric in _ALLOCATION_METRICS and any(value == 0 for value in base_values):
        if not all(value == 0 for value in base_values):
            raise EvidenceIntegrityError(
                f"Allocation baseline for {benchmark!r} / {metric!r} mixes zero and non-zero values"
            )
        if all(value == 0 for value in candidate_values):
            return MetricComparison(
                benchmark=benchmark,
                metric=metric,
                base_values=base_values,
                candidate_values=candidate_values,
                ratios=(None,) * len(base_values),
                median_ratio=None,
                one_sided_95_lower_bound=None,
                comparison_mode="zero_stable",
                decision="pass",
            )
        return MetricComparison(
            benchmark=benchmark,
            metric=metric,
            base_values=base_values,
            candidate_values=candidate_values,
            ratios=(None,) * len(base_values),
            median_ratio=None,
            one_sided_95_lower_bound=None,
            comparison_mode="zero_baseline_regression",
            decision="regression",
        )

    ratios = _ratios(base_values, candidate_values)
    median_ratio = paired_median_ratio(base_values, candidate_values)
    lower_bound = bootstrap_lower_bound(
        ratios,
        benchmark=benchmark,
        metric=metric,
    )
    decision = (
        "regression"
        if median_ratio > THRESHOLD_RATIO and lower_bound > THRESHOLD_RATIO
        else "pass"
    )
    return MetricComparison(
        benchmark=benchmark,
        metric=metric,
        base_values=base_values,
        candidate_values=candidate_values,
        ratios=ratios,
        median_ratio=median_ratio,
        one_sided_95_lower_bound=lower_bound,
        comparison_mode="paired_ratio",
        decision=decision,
    )


def compare_paired_samples(
    samples: Mapping[MetricKey, PairedValues],
    *,
    format_name: str,
    base_revision: str,
    candidate_revision: str,
    toolchain: Mapping[str, object],
    expected_pairs: int = EXPECTED_PAIRS,
) -> ComparisonResult:
    """Compare all validated metrics and fail the aggregate on any regression."""

    if expected_pairs != EXPECTED_PAIRS:
        raise EvidenceIntegrityError(
            f"Expected pair count must be exactly {EXPECTED_PAIRS}, got {expected_pairs}"
        )
    if not samples:
        raise EvidenceIntegrityError(
            "No benchmark metrics are available for comparison"
        )

    metrics: list[MetricComparison] = []
    for (benchmark, metric), (base_values, candidate_values) in sorted(samples.items()):
        if (
            len(base_values) != expected_pairs
            or len(candidate_values) != expected_pairs
        ):
            raise EvidenceIntegrityError(
                f"Benchmark {benchmark!r} / {metric!r} does not contain {expected_pairs} pairs"
            )
        metrics.append(
            _comparison_for_metric(benchmark, metric, base_values, candidate_values)
        )

    decision = (
        "regression"
        if any(metric.decision == "regression" for metric in metrics)
        else "pass"
    )
    return ComparisonResult(
        format_name=format_name,
        base_revision=base_revision,
        candidate_revision=candidate_revision,
        expected_pairs=expected_pairs,
        toolchain=toolchain,
        decision=decision,
        metrics=tuple(metrics),
    )


def _validate_revision(value: str, flag_name: str) -> str:
    if _SHA_RE.fullmatch(value) is None or value == "0" * 40:
        raise EvidenceIntegrityError(
            f"{flag_name} must be a non-zero 40-hex commit SHA"
        )
    return value


def _load_toolchain(path: Path) -> dict[str, object]:
    def reject_nonstandard_constant(value: str) -> None:
        raise EvidenceIntegrityError(
            f"Toolchain JSON contains non-finite value {value!r}"
        )

    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=reject_nonstandard_constant
        )
    except OSError as exc:
        raise EvidenceIntegrityError(f"Unable to read toolchain JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceIntegrityError(f"Malformed toolchain JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise EvidenceIntegrityError("Toolchain JSON must be an object")
    return parsed


def _write_result(path: Path, result: ComparisonResult) -> None:
    payload = (
        json.dumps(
            result.to_dict(),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(payload)
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _invalid_result(
    *,
    format_name: str,
    base_revision: str,
    candidate_revision: str,
    expected_pairs: int,
    toolchain: Mapping[str, object],
    error: str,
) -> ComparisonResult:
    return ComparisonResult(
        format_name=format_name,
        base_revision=base_revision,
        candidate_revision=candidate_revision,
        expected_pairs=expected_pairs,
        toolchain=toolchain,
        decision="invalid_evidence",
        metrics=(),
        error=error,
    )


def _write_invalid_result(
    arguments: argparse.Namespace,
    toolchain: Mapping[str, object],
    error: str,
) -> None:
    try:
        _write_result(
            arguments.output,
            _invalid_result(
                format_name=arguments.format,
                base_revision=arguments.base_revision,
                candidate_revision=arguments.candidate_revision,
                expected_pairs=arguments.expected_pairs,
                toolchain=toolchain,
                error=error,
            ),
        )
    except OSError as write_error:
        print(
            f"error: unable to write invalid-evidence report: {write_error}",
            file=sys.stderr,
        )


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("go", "bencher"), required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--expected-pairs", type=int, default=EXPECTED_PAIRS)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--toolchain-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the fail-closed comparison and map its decision to CI exit codes."""

    try:
        arguments = _parse_arguments(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    toolchain: Mapping[str, object] = {}
    try:
        base_revision = _validate_revision(arguments.base_revision, "--base-revision")
        candidate_revision = _validate_revision(
            arguments.candidate_revision, "--candidate-revision"
        )
        if base_revision.lower() == candidate_revision.lower():
            raise EvidenceIntegrityError(
                "--base-revision and --candidate-revision must differ"
            )
        toolchain = _load_toolchain(arguments.toolchain_json)
        parser = (
            parse_go_benchmark_output
            if arguments.format == "go"
            else parse_bencher_output
        )
        samples = load_paired_samples(
            arguments.base_dir,
            arguments.candidate_dir,
            arguments.expected_pairs,
            parser,
        )
        result = compare_paired_samples(
            samples,
            format_name=arguments.format,
            base_revision=base_revision,
            candidate_revision=candidate_revision,
            toolchain=toolchain,
            expected_pairs=arguments.expected_pairs,
        )
        _write_result(arguments.output, result)
        return 1 if result.decision == "regression" else 0
    except EvidenceIntegrityError as exc:
        _write_invalid_result(arguments, toolchain, str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (
        Exception
    ) as exc:  # RZ-22-01-JUSTIFIED: fail closed on unexpected CLI failures.
        _write_invalid_result(arguments, toolchain, str(exc))
        if arguments.verbose:
            traceback.print_exc()
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
