from __future__ import annotations

import importlib
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "quality" / "quality-contract.json"
CONTRACT_GENERATED_AT = "2026-10-31T00:00:00Z"


@pytest.fixture
def normalizer(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts" / "quality"))
    return importlib.import_module("normalize_coverage_reports")


def _load_mutated_contract(
    normalizer: ModuleType,
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> object:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    mutate(contract)
    path = tmp_path / "quality-contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    return normalizer._load_contract(
        path, normalizer._parse_generated_at(CONTRACT_GENERATED_AT)
    )


def test_checked_in_contract_loads_before_legacy_expiry(
    normalizer: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(normalizer, "_utc_today", lambda: date(2026, 10, 31))

    normalizer._load_contract(
        CONTRACT_PATH, normalizer._parse_generated_at(CONTRACT_GENERATED_AT)
    )


def test_stale_generated_at_cannot_keep_expired_legacy_exemption(
    normalizer: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real UTC day is past the 2026-11-13 expiry; the caller-supplied
    # generated-at is deliberately older and must not extend the exemption.
    monkeypatch.setattr(normalizer, "_utc_today", lambda: date(2026, 11, 14))
    stale = normalizer._parse_generated_at("2026-10-31T00:00:00Z")

    with pytest.raises(
        normalizer._InputError,
        match="migration exemption is no longer valid",
    ):
        normalizer._load_contract(CONTRACT_PATH, stale)


def test_legacy_baseline_must_name_exactly_131_paths(
    normalizer: ModuleType,
    tmp_path: Path,
) -> None:
    def drop_one_record(contract: dict[str, Any]) -> None:
        contract["tier0"]["legacy_migration_baselines"]["files"].pop()

    with pytest.raises(
        normalizer._InputError,
        match="must contain exactly 131 approved paths",
    ):
        _load_mutated_contract(normalizer, tmp_path, drop_one_record)


def test_legacy_baseline_digest_pins_every_approved_record(
    normalizer: ModuleType,
    tmp_path: Path,
) -> None:
    def change_one_record(contract: dict[str, Any]) -> None:
        record = contract["tier0"]["legacy_migration_baselines"]["files"][0]
        record["metrics"]["lines"]["covered"] -= 1

    with pytest.raises(
        normalizer._InputError,
        match="does not match the approved immutable baseline digest",
    ):
        _load_mutated_contract(normalizer, tmp_path, change_one_record)


def test_tier0_exempts_only_unchanged_baseline_residuals(
    normalizer: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _measured(covered: int, total: int) -> Any:
        return normalizer._measured_metric("native", covered, total)

    monkeypatch.setattr(
        normalizer,
        "COVERAGE_SCOPE_ROOTS",
        {**normalizer.COVERAGE_SCOPE_ROOTS, "python": ("app", "alembic/versions")},
    )
    monkeypatch.setattr(
        normalizer,
        "_load_tier0_rules",
        lambda: (["alembic/versions/**"], None),
    )
    exempt = "alembic/versions/0001_exempt.py"
    changed = "alembic/versions/0002_changed.py"
    added = "alembic/versions/0003_added.py"
    metrics = normalizer.METRICS
    report = normalizer._ParsedReport(
        component="python",
        report_format="coverage-py-json",
        path=Path("coverage.json"),
        metrics={},
        file_metrics={
            # Unchanged baseline residual: one missed line, still exempt.
            exempt: {
                "lines": _measured(8, 9),
                "statements": _measured(8, 9),
                "branches": _measured(2, 2),
                "functions": _measured(1, 1),
            },
            # Changed migration: the same single miss is no longer exempt.
            changed: {
                "lines": _measured(9, 10),
                "statements": _measured(10, 10),
                "branches": _measured(2, 2),
                "functions": _measured(1, 1),
            },
            added: {metric: _measured(4, 4) for metric in metrics},
        },
        sha256="0" * 64,
    )
    legacy = {
        exempt: {
            "path": exempt,
            "metrics": {
                "lines": _measured(8, 9),
                "statements": _measured(8, 9),
                "branches": _measured(2, 2),
                "functions": _measured(1, 1),
            },
        }
    }
    floors = {
        component: dict.fromkeys(metrics, 100) for component in normalizer.COMPONENTS
    }
    statuses = {
        component: dict.fromkeys(metrics, frozenset({"native", "derived"}))
        for component in normalizer.COMPONENTS
    }

    result = normalizer._aggregate_tier0(
        defaultdict(list, {"python": [report]}),
        floors,
        statuses,
        {"python": frozenset({exempt, changed, added})},
        legacy,
        (),
    )

    errors = result["errors"]
    assert result["status"] == "failed"
    assert f"{changed} (python).lines is below 100%" in errors
    assert (
        "tier0.coverage.lines misses must equal the current legacy-migration "
        "residual (1, got 2)"
    ) in errors
    assert not [error for error in errors if exempt in error or added in error]
