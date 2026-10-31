from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def normalizer(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts" / "quality"))
    return importlib.import_module("normalize_coverage_reports")


def _measured(covered: int, total: int) -> dict[str, object]:
    return {"status": "native", "covered": covered, "total": total}


def _passing_components(normalizer: ModuleType) -> dict[str, object]:
    return {
        component: {
            "status": "passed",
            "metrics": {metric: _measured(1, 1) for metric in normalizer.METRICS},
        }
        for component in normalizer.COVERAGE_COMPONENTS
    }


def _report(
    normalizer: ModuleType,
    component: str,
    file_metrics: dict[str, dict[str, dict[str, object]]],
) -> object:
    return normalizer._ParsedReport(
        component=component,
        report_format="test",
        path=Path(f"{component}.json"),
        metrics={},
        file_metrics=file_metrics,
        sha256="0" * 64,
    )


def test_gap_sections_list_only_unexempt_uncovered_files_for_failing_metrics(
    normalizer: ModuleType,
) -> None:
    components = _passing_components(normalizer)
    components["python"] = {
        "status": "failed",
        "metrics": {
            "lines": _measured(19, 20),
            "statements": _measured(10, 10),
            "branches": _measured(4, 6),
            # Unsupported component counters are not failing metrics, so their
            # per-file derived counters must not be listed as failure causes.
            "functions": {"status": "unsupported", "reason_code": "no_counter"},
        },
    }
    python_report = _report(
        normalizer,
        "python",
        {
            "alembic/versions/exempt.py": {
                metric: _measured(8, 10) for metric in normalizer.METRICS
            },
            "app/clean.py": {metric: _measured(5, 5) for metric in normalizer.METRICS},
            "app/uncovered.py": {
                "lines": _measured(5, 5),
                "statements": _measured(5, 5),
                "branches": _measured(2, 3),
                "functions": _measured(0, 1),
            },
        },
    )
    tier0 = {
        "coverage": {
            "lines": _measured(17, 19),
            "statements": _measured(10, 10),
            "branches": _measured(4, 5),
            "functions": _measured(2, 2),
        },
        "files": [
            {
                "path": "alembic/versions/exempt.py",
                "component": "python",
                "metrics": {metric: _measured(8, 10) for metric in normalizer.METRICS},
            },
            {
                "path": "alembic/versions/changed.py",
                "component": "python",
                "metrics": {
                    "lines": _measured(9, 10),
                    "statements": _measured(10, 10),
                    "branches": _measured(2, 2),
                    "functions": _measured(1, 1),
                },
            },
        ],
    }

    sections = normalizer._coverage_gap_sections(
        components=components,
        reports_by_component={"python": [python_report]},
        tier0=tier0,
        legacy_records={"alembic/versions/exempt.py": {"path": "x"}},
    )

    assert sections == [
        (
            "python",
            [
                {
                    "path": "app/uncovered.py",
                    "metrics": {
                        "branches": {
                            "status": "native",
                            "covered": 2,
                            "total": 3,
                            "missing": 1,
                        }
                    },
                }
            ],
        ),
        (
            "tier0",
            [
                {
                    "path": "alembic/versions/changed.py",
                    "metrics": {
                        "lines": {
                            "status": "native",
                            "covered": 9,
                            "total": 10,
                            "missing": 1,
                        }
                    },
                }
            ],
        ),
    ]


def test_gap_diagnostics_are_silent_when_every_gap_is_exempt(
    normalizer: ModuleType,
) -> None:
    components = _passing_components(normalizer)
    components["python"] = {
        "status": "failed",
        "metrics": {metric: _measured(8, 10) for metric in normalizer.METRICS},
    }
    python_report = _report(
        normalizer,
        "python",
        {
            "alembic/versions/exempt.py": {
                metric: _measured(8, 10) for metric in normalizer.METRICS
            }
        },
    )
    tier0 = {
        "coverage": {metric: _measured(8, 10) for metric in normalizer.METRICS},
        "files": [
            {
                "path": "alembic/versions/exempt.py",
                "component": "python",
                "metrics": {metric: _measured(8, 10) for metric in normalizer.METRICS},
            }
        ],
    }

    sections = normalizer._coverage_gap_sections(
        components=components,
        reports_by_component={"python": [python_report]},
        tier0=tier0,
        legacy_records={"alembic/versions/exempt.py": {"path": "x"}},
    )

    assert sections == []
    assert normalizer._coverage_gap_diagnostic_lines(sections) == []


def test_gap_lines_stay_under_limit_and_count_every_omitted_file(
    normalizer: ModuleType,
) -> None:
    prefix = "services/ws-hub/" + "very-long-directory-name/" * 20
    files = [
        {
            "path": f"{prefix}file_{index:02d}.go",
            "metrics": {
                "lines": {
                    "status": "derived",
                    "covered": 0,
                    "total": 1,
                    "missing": 1,
                },
                "statements": {
                    "status": "native",
                    "covered": 0,
                    "total": 1,
                    "missing": 1,
                },
            },
        }
        for index in range(40)
    ]

    (line,) = normalizer._coverage_gap_diagnostic_lines([("go-ws-hub", files)])

    assert line.startswith(normalizer.COVERAGE_GAP_DIAGNOSTIC_PREFIX)
    assert len(line) + 1 <= normalizer.COVERAGE_GAP_LINE_LIMIT_BYTES
    payload = json.loads(line.removeprefix(normalizer.COVERAGE_GAP_DIAGNOSTIC_PREFIX))
    assert payload["classification"] == normalizer.COVERAGE_GAP_CLASSIFICATION
    (component,) = payload["components"]
    kept = [entry["path"] for entry in component["files"]]
    assert 0 < len(kept) < normalizer.COVERAGE_GAP_FILES_PER_COMPONENT
    assert kept == [entry["path"] for entry in files[: len(kept)]]
    assert len(kept) + component["omitted_files"] == len(files)
