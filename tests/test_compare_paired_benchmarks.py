import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from scripts.quality.compare_paired_benchmarks import (
    EvidenceIntegrityError,
    load_paired_samples,
    main,
    parse_bencher_output,
    parse_go_benchmark_output,
)

BASE_REVISION = "a" * 40
CANDIDATE_REVISION = "b" * 40
GO_PACKAGE = "github.com/university-ecosystem/ws-hub/pkg/hub"


def _go_record(
    value: float,
    *,
    benchmark: str = "BenchmarkLookup-8",
    allocation_value: float | None = None,
    package: str = GO_PACKAGE,
) -> str:
    allocation_value = value if allocation_value is None else allocation_value
    return (
        f"pkg: {package}\n{benchmark} 100 {value} ns/op {allocation_value} B/op "
        f"{allocation_value} allocs/op\n"
    )


def _bencher_record(value: float, *, benchmark: str = "native_conflicts/100") -> str:
    return f"test {benchmark} ... bench: {value} ns/iter (+/- 4)\n"


def _write_pairs(
    base_dir: Path,
    candidate_dir: Path,
    base_record: Callable[[int], str],
    candidate_record: Callable[[int], str],
) -> None:
    base_dir.mkdir()
    candidate_dir.mkdir()
    for index in range(1, 13):
        (base_dir / f"pair-{index:02d}.txt").write_text(
            base_record(index), encoding="utf-8"
        )
        (candidate_dir / f"pair-{index:02d}.txt").write_text(
            candidate_record(index), encoding="utf-8"
        )


def _run_cli(
    tmp_path: Path,
    *,
    output: Path,
    format_name: str = "go",
    expected_pairs: int = 12,
    base_revision: str = BASE_REVISION,
    candidate_revision: str = CANDIDATE_REVISION,
) -> int:
    toolchain = tmp_path / "toolchain.json"
    toolchain.write_text(json.dumps({"go": "go version go1.26.5"}), encoding="utf-8")
    return main(
        [
            "--format",
            format_name,
            "--base-dir",
            str(tmp_path / "base"),
            "--candidate-dir",
            str(tmp_path / "candidate"),
            "--expected-pairs",
            str(expected_pairs),
            "--base-revision",
            base_revision,
            "--candidate-revision",
            candidate_revision,
            "--toolchain-json",
            str(toolchain),
            "--output",
            str(output),
        ]
    )


def test_go_pair_loader_normalizes_processor_suffix_and_preserves_all_metrics(
    tmp_path: Path,
) -> None:
    """Catches a parser that treats a Go processor suffix as benchmark identity."""

    base_dir = tmp_path / "base"
    candidate_dir = tmp_path / "candidate"
    _write_pairs(
        base_dir,
        candidate_dir,
        lambda _: _go_record(12.5, allocation_value=0.0),
        lambda _: _go_record(13.0, allocation_value=0.0),
    )

    loaded = load_paired_samples(base_dir, candidate_dir, 12, parse_go_benchmark_output)

    assert loaded[(f"{GO_PACKAGE}::BenchmarkLookup", "ns/op")] == (
        (12.5,) * 12,
        (13.0,) * 12,
    )
    assert loaded[(f"{GO_PACKAGE}::BenchmarkLookup", "B/op")] == (
        (0.0,) * 12,
        (0.0,) * 12,
    )
    assert loaded[(f"{GO_PACKAGE}::BenchmarkLookup", "allocs/op")] == (
        (0.0,) * 12,
        (0.0,) * 12,
    )


def test_pair_loader_rejects_an_extra_directory_with_twelve_valid_pairs(
    tmp_path: Path,
) -> None:
    """The evidence directory is canonical only when no extra entries exist."""

    base_dir = tmp_path / "base"
    candidate_dir = tmp_path / "candidate"
    _write_pairs(
        base_dir,
        candidate_dir,
        lambda _: _go_record(10.0),
        lambda _: _go_record(11.0),
    )
    (base_dir / "unexpected-directory").mkdir()

    with pytest.raises(EvidenceIntegrityError, match="Unexpected pair evidence"):
        load_paired_samples(base_dir, candidate_dir, 12, parse_go_benchmark_output)


def test_go_parser_namespaces_identical_benchmark_names_by_package() -> None:
    """Catches an ambiguous full-module capture when packages reuse a benchmark name."""

    other_package = "github.com/university-ecosystem/ws-hub/pkg/other"

    parsed = parse_go_benchmark_output(
        _go_record(10.0) + _go_record(11.0, package=other_package)
    )

    assert set(parsed) == {
        f"{GO_PACKAGE}::BenchmarkLookup",
        f"{other_package}::BenchmarkLookup",
    }


def test_go_parser_rejects_a_benchmark_record_without_package_identity() -> None:
    """Catches a parser that cannot distinguish identical names across packages."""

    with pytest.raises(EvidenceIntegrityError, match="package identity"):
        parse_go_benchmark_output("BenchmarkLookup-8 100 12 ns/op 4 B/op 1 allocs/op\n")


def test_bencher_pair_loader_normalizes_ns_per_iteration_to_ns_per_operation(
    tmp_path: Path,
) -> None:
    """Catches a Criterion parser that drops or mislabels ns/iter measurements."""

    base_dir = tmp_path / "base"
    candidate_dir = tmp_path / "candidate"
    _write_pairs(
        base_dir,
        candidate_dir,
        lambda _: _bencher_record(120.0),
        lambda _: _bencher_record(121.0),
    )

    loaded = load_paired_samples(base_dir, candidate_dir, 12, parse_bencher_output)

    assert loaded[("native_conflicts/100", "ns/op")] == (
        (120.0,) * 12,
        (121.0,) * 12,
    )
    assert parse_bencher_output(_bencher_record(120.0)) == {
        "native_conflicts/100": {"ns/op": 120.0}
    }


def test_go_pair_loader_rejects_missing_required_benchmem_metrics(
    tmp_path: Path,
) -> None:
    """Catches a gate that silently drops allocation metrics from ``-benchmem``."""

    base_dir = tmp_path / "base"
    candidate_dir = tmp_path / "candidate"
    _write_pairs(
        base_dir,
        candidate_dir,
        lambda _: f"pkg: {GO_PACKAGE}\nBenchmarkLookup-8 100 12.5 ns/op\n",
        lambda _: f"pkg: {GO_PACKAGE}\nBenchmarkLookup-8 100 13.0 ns/op\n",
    )

    with pytest.raises(
        EvidenceIntegrityError, match="Incomplete Go benchmark metric set"
    ):
        load_paired_samples(base_dir, candidate_dir, 12, parse_go_benchmark_output)


@pytest.mark.parametrize(
    ("base_record", "candidate_record", "mutation"),
    [
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda base_dir, _candidate_dir: (base_dir / "pair-12.txt").unlink(),
        ),
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda base_dir, _candidate_dir: (base_dir / "unexpected.txt").write_text(
                "unexpected", encoding="utf-8"
            ),
        ),
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda base_dir, _candidate_dir: (base_dir / "pair-01.txt").write_text(
                _go_record(10.0) + _go_record(11.0), encoding="utf-8"
            ),
        ),
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda base_dir, _candidate_dir: (base_dir / "pair-01.txt").write_text(
                "BenchmarkLookup-8 100 not-a-number ns/op 4 B/op 1 allocs/op\n",
                encoding="utf-8",
            ),
        ),
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda base_dir, _candidate_dir: (base_dir / "pair-01.txt").write_text(
                "BenchmarkLookup-8 100 nan ns/op 4 B/op 1 allocs/op\n",
                encoding="utf-8",
            ),
        ),
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda base_dir, _candidate_dir: (base_dir / "pair-01.txt").write_text(
                "BenchmarkLookup-8 100 inf ns/op 4 B/op 1 allocs/op\n",
                encoding="utf-8",
            ),
        ),
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda _base_dir, candidate_dir: (candidate_dir / "pair-01.txt").write_text(
                "BenchmarkLookup-8 100 11 ns/op 11 B/op\n", encoding="utf-8"
            ),
        ),
        (
            lambda _: _go_record(10.0),
            lambda _: _go_record(11.0),
            lambda _base_dir, candidate_dir: (candidate_dir / "pair-01.txt").write_text(
                _go_record(11.0, benchmark="BenchmarkOther-8"), encoding="utf-8"
            ),
        ),
    ],
)
def test_pair_loader_rejects_incomplete_or_ambiguous_evidence(
    tmp_path: Path,
    base_record: Callable[[int], str],
    candidate_record: Callable[[int], str],
    mutation: Callable[[Path, Path], None],
) -> None:
    """Catches any path that turns malformed paired evidence into a comparison."""

    base_dir = tmp_path / "base"
    candidate_dir = tmp_path / "candidate"
    _write_pairs(base_dir, candidate_dir, base_record, candidate_record)
    mutation(base_dir, candidate_dir)

    with pytest.raises(EvidenceIntegrityError):
        load_paired_samples(base_dir, candidate_dir, 12, parse_go_benchmark_output)


@pytest.mark.parametrize(
    ("ratios", "expected_exit"),
    [
        ([1.10] * 12, 0),
        ([1.00] * 5 + [1.11] * 7, 0),
        ([1.12] * 12, 1),
    ],
)
def test_cli_applies_the_strict_regression_boundary(
    tmp_path: Path,
    ratios: Sequence[float],
    expected_exit: int,
) -> None:
    """Catches a gate that fails at 1.10 or without a proven lower bound."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0),
        lambda index: _go_record(100.0 * ratios[index - 1]),
    )
    output = tmp_path / "comparison.json"

    exit_code = _run_cli(tmp_path, output=output)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == expected_exit
    assert report["decision"] == ("regression" if expected_exit == 1 else "pass")
    assert report["threshold_ratio"] == 1.1


def test_cli_writes_byte_identical_report_with_metadata_and_raw_values(
    tmp_path: Path,
) -> None:
    """Catches non-deterministic bootstrap output or omitted audit evidence."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0),
        lambda _: _go_record(105.0),
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    assert _run_cli(tmp_path, output=first) == 0
    assert _run_cli(tmp_path, output=second) == 0
    assert first.read_bytes() == second.read_bytes()

    report = json.loads(first.read_text(encoding="utf-8"))
    ns_metric = next(
        metric for metric in report["metrics"] if metric["metric"] == "ns/op"
    )
    assert report["base_revision"] == BASE_REVISION
    assert report["candidate_revision"] == CANDIDATE_REVISION
    assert report["toolchain"] == {"go": "go version go1.26.5"}
    assert ns_metric["base_values"] == [100.0] * 12
    assert ns_metric["candidate_values"] == [105.0] * 12
    assert ns_metric["ratios"] == [1.05] * 12


def test_cli_marks_stable_zero_allocation_metrics_as_an_explicit_pass(
    tmp_path: Path,
) -> None:
    """Catches a gate that mistakes a no-allocation benchmark for invalid data."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0, allocation_value=0.0),
        lambda _: _go_record(105.0, allocation_value=0.0),
    )
    output = tmp_path / "comparison.json"

    assert _run_cli(tmp_path, output=output) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    allocation_metrics = [
        metric
        for metric in report["metrics"]
        if metric["metric"] in {"B/op", "allocs/op"}
    ]
    assert len(allocation_metrics) == 2
    for metric in allocation_metrics:
        assert metric["base_values"] == [0.0] * 12
        assert metric["candidate_values"] == [0.0] * 12
        assert metric["ratios"] == [None] * 12
        assert metric["median_ratio"] is None
        assert metric["one_sided_95_lower_bound"] is None
        assert metric["comparison_mode"] == "zero_stable"
        assert metric["decision"] == "pass"


def test_cli_marks_new_allocations_against_a_zero_baseline_as_a_regression(
    tmp_path: Path,
) -> None:
    """Catches a gate that hides allocations newly introduced by the candidate."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0, allocation_value=0.0),
        lambda _: _go_record(100.0, allocation_value=1.0),
    )
    output = tmp_path / "comparison.json"

    assert _run_cli(tmp_path, output=output) == 1

    report_bytes = output.read_bytes()
    report = json.loads(report_bytes.decode("utf-8"))
    allocation_metric = next(
        metric for metric in report["metrics"] if metric["metric"] == "B/op"
    )
    assert allocation_metric["base_values"] == [0.0] * 12
    assert allocation_metric["candidate_values"] == [1.0] * 12
    assert allocation_metric["ratios"] == [None] * 12
    assert allocation_metric["median_ratio"] is None
    assert allocation_metric["one_sided_95_lower_bound"] is None
    assert allocation_metric["comparison_mode"] == "zero_baseline_regression"
    assert allocation_metric["decision"] == "regression"
    assert b"Infinity" not in report_bytes
    assert b"NaN" not in report_bytes


def test_cli_rejects_a_mixed_zero_and_nonzero_allocation_baseline(
    tmp_path: Path,
) -> None:
    """Catches a relative comparison that treats an intermittent zero baseline as valid."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda index: _go_record(100.0, allocation_value=0.0 if index % 2 else 1.0),
        lambda _: _go_record(100.0, allocation_value=0.0),
    )
    output = tmp_path / "comparison.json"

    assert _run_cli(tmp_path, output=output) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["decision"] == "invalid_evidence"


def test_cli_rejects_a_zero_ns_per_operation_baseline(tmp_path: Path) -> None:
    """Catches a time comparison that divides by an unusable zero baseline."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(0.0, allocation_value=0.0),
        lambda _: _go_record(100.0, allocation_value=0.0),
    )
    output = tmp_path / "comparison.json"

    assert _run_cli(tmp_path, output=output) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["decision"] == "invalid_evidence"


@pytest.mark.parametrize("revision", ["0" * 40, "g" * 40])
def test_cli_rejects_non_immutable_base_revision_with_an_invalid_evidence_report(
    tmp_path: Path,
    revision: str,
) -> None:
    """Catches an acceptance path for the all-zero or malformed base SHA."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0),
        lambda _: _go_record(101.0),
    )
    output = tmp_path / "comparison.json"

    assert _run_cli(tmp_path, output=output, base_revision=revision) == 2

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["base_revision"] == revision
    assert report["decision"] == "invalid_evidence"
    assert report["metrics"] == []


def test_cli_rejects_identical_valid_revisions_with_an_invalid_evidence_report(
    tmp_path: Path,
) -> None:
    """A syntactically valid self-comparison cannot supply regression evidence."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0),
        lambda _: _go_record(101.0),
    )
    output = tmp_path / "comparison.json"

    assert (
        _run_cli(
            tmp_path,
            output=output,
            base_revision=BASE_REVISION,
            candidate_revision=BASE_REVISION,
        )
        == 2
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["base_revision"] == BASE_REVISION
    assert report["candidate_revision"] == BASE_REVISION
    assert report["decision"] == "invalid_evidence"
    assert report["metrics"] == []
    assert "must differ" in report["error"]


def test_cli_fails_the_whole_report_when_one_benchmark_regresses(
    tmp_path: Path,
) -> None:
    """Catches aggregate success when one measured benchmark is proven slower."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0) + _go_record(100.0, benchmark="BenchmarkSlow-8"),
        lambda _: _go_record(100.0) + _go_record(112.0, benchmark="BenchmarkSlow-8"),
    )
    output = tmp_path / "comparison.json"

    assert _run_cli(tmp_path, output=output) == 1

    report = json.loads(output.read_text(encoding="utf-8"))
    decisions = {
        (metric["benchmark"], metric["decision"]) for metric in report["metrics"]
    }
    assert report["decision"] == "regression"
    assert (f"{GO_PACKAGE}::BenchmarkLookup", "pass") in decisions
    assert (f"{GO_PACKAGE}::BenchmarkSlow", "regression") in decisions


def test_cli_writes_invalid_evidence_report_and_rejects_non_twelve_pair_count(
    tmp_path: Path,
) -> None:
    """Catches invalid input being reported as success or a weakened sample count."""

    _write_pairs(
        tmp_path / "base",
        tmp_path / "candidate",
        lambda _: _go_record(100.0),
        lambda _: _go_record(101.0),
    )
    (tmp_path / "base" / "pair-12.txt").unlink()
    invalid_output = tmp_path / "invalid.json"

    assert _run_cli(tmp_path, output=invalid_output) == 2
    invalid_report = json.loads(invalid_output.read_text(encoding="utf-8"))
    assert invalid_report["decision"] == "invalid_evidence"
    assert invalid_report["metrics"] == []

    count_output = tmp_path / "count.json"
    assert _run_cli(tmp_path, output=count_output, expected_pairs=11) == 2
