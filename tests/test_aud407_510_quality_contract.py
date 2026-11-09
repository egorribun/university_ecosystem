from __future__ import annotations

import importlib
import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.quality import validate_quality_contract as validator

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)
METRICS = ("lines", "statements", "branches", "functions")
TRACKED_FRONTEND_TIER0 = "frontend/src/components/auth/AuthBackdrop.tsx"
TRACKED_PYTHON_TIER0 = "app/auth/constants.py"
VALID_POLICY = {
    "frontend": {
        "include": ["src/**/*.{ts,tsx}"],
        "exclude": ["src/**/*.test.{ts,tsx}"],
    }
}


def _mutation_registry(created: date, expires: date) -> dict[str, object]:
    return {
        "version": 1,
        "exclusions": [
            {
                "id": "equivalent-example",
                "path": "app/example.py",
                "reason": "The mutant has equivalent behavior",
                "owner": "quality-owner",
                "issue": "QUALITY-1",
                "created_on": created.isoformat(),
                "expires_on": expires.isoformat(),
                "evidence": "tests/test_example.py",
            }
        ],
    }


def test_aud407_rejects_future_creation_even_with_a_short_expiry() -> None:
    registry = _mutation_registry(TODAY + timedelta(days=1), TODAY + timedelta(days=2))

    errors = validator._validate_mutation_registry(registry, today=TODAY)

    assert (
        "mutation_exclusions[0].created_on must not be after validation day" in errors
    )


@pytest.mark.parametrize(
    ("created", "expires", "expected_error"),
    [
        (TODAY, TODAY + timedelta(days=30), None),
        (TODAY, TODAY + timedelta(days=31), "at most 30 days after created_on"),
        (TODAY, date(2099, 1, 1), "at most 30 days after created_on"),
        (TODAY - timedelta(days=30), TODAY, "after validation day"),
    ],
)
def test_aud407_mutation_expiry_is_bounded_and_future(
    created: date, expires: date, expected_error: str | None
) -> None:
    errors = validator._validate_mutation_registry(
        _mutation_registry(created, expires), today=TODAY
    )

    if expected_error is None:
        assert errors == []
    else:
        assert any(expected_error in error for error in errors)


@pytest.fixture
def tier0_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, object], dict[str, object]]:
    quality = tmp_path / "quality"
    quality.mkdir()
    (quality / "coverage-source-policy.json").write_text(
        json.dumps(VALID_POLICY), encoding="utf-8"
    )
    rule = "frontend/src/**"
    (quality / "ownership-mapping.json").write_text(
        json.dumps({"tier0_rules": [rule]}), encoding="utf-8"
    )
    path = "frontend/src/auth.ts"
    source = tmp_path / path
    source.parent.mkdir(parents=True)
    source.write_text("export const auth = true;\n", encoding="utf-8")
    monkeypatch.setattr(
        validator,
        "_tracked_source_paths",
        lambda _root, roots: (path, "frontend/src/auth.test.ts")
        if "frontend/src" in roots
        else (),
    )
    contract = json.loads(
        (ROOT / "quality/quality-contract.json").read_text(encoding="utf-8")
    )
    measured = {"status": "native", "covered": 1, "total": 1, "percent": 100.0}
    metrics = {metric: dict(measured) for metric in METRICS}
    manifest = {
        "coverage_scope": contract["coverage_scope"],
        "source_roots": contract["source_roots"],
        "tier0": {
            "status": "ready",
            "errors": [],
            "rules": [rule],
            "files": [{"path": path, "component": "frontend", "metrics": metrics}],
            "metric_summary": {
                metric: {"applicable_files": 1, "not_applicable_files": 0}
                for metric in METRICS
            },
            "coverage": {metric: dict(measured) for metric in METRICS},
        },
    }
    return tmp_path, contract, manifest


def _tier0_errors(case: tuple[Path, dict[str, object], dict[str, object]]) -> list[str]:
    root, contract, manifest = case
    return validator._validate_tier0_manifest(
        manifest, contract, root, legacy_records={}
    )


def test_aud510_valid_policy_includes_production_and_excludes_tests(
    tier0_case: tuple[Path, dict[str, object], dict[str, object]],
) -> None:
    assert _tier0_errors(tier0_case) == []


def test_aud510_repository_policy_matches_coverage_producer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")

    assert validator._load_frontend_source_policy(ROOT) == (
        producer._load_frontend_coverage_policy()
    )


@pytest.mark.parametrize(
    "path",
    ["frontend/src/components/auth/AUTH.TSX", "frontend/src/SETUPTESTS.ts"],
)
def test_aud510_producer_and_validator_apply_current_policy_identically(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")
    policy = validator._load_frontend_source_policy(ROOT)
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_INCLUDE", policy[0])
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_EXCLUDE", policy[1])

    assert validator._is_production_source(path, "frontend", policy) == (
        producer._tracked_source_is_coverable("frontend", path)
    )


def test_aud510_current_policy_matches_for_tracked_frontend_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")
    policy = validator._load_frontend_source_policy(ROOT)
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_INCLUDE", policy[0])
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_EXCLUDE", policy[1])
    tracked = validator._tracked_source_paths(ROOT, ["frontend/src"])
    assert TRACKED_FRONTEND_TIER0 in tracked

    differences = [
        path
        for path in tracked
        if validator._is_production_source(path, "frontend", policy)
        != producer._tracked_source_is_coverable("frontend", path)
    ]
    assert differences == []


def test_aud510_valid_policy_controls_eligible_files(
    tier0_case: tuple[Path, dict[str, object], dict[str, object]],
) -> None:
    root, _, _ = tier0_case
    policy = {"frontend": {"include": ["src/**/*.ts"], "exclude": ["src/auth.ts"]}}
    (root / "quality/coverage-source-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    errors = _tier0_errors(tier0_case)

    assert "tier0.files contains unexpected source frontend/src/auth.ts" in errors


@pytest.mark.parametrize(
    "policy_bytes",
    [
        None,
        b'{"frontend":',
        b"\xff",
        b'{"frontend":{"include":["src/**/*.{ts,tsx}"],'
        b'"include":["src/**/*.{ts,tsx}"],"exclude":["src/**/*.test.{ts,tsx}"]}}',
        b'{"frontend":{"include":["src/**/*.{ts,tsx}"],'
        b'"exclude":["src/**/*.test.{ts,tsx}"]},"extra":{}}',
        b'{"frontend":{"include":[],"exclude":["src/**/*.test.{ts,tsx}"]}}',
        b'{"frontend":{"include":["../src/**/*.ts"],"exclude":["src/tests/**"]}}',
        b'{"frontend":{"include":["src/**/*.{ts,}"],"exclude":["src/tests/**"]}}',
    ],
    ids=[
        "missing",
        "malformed",
        "invalid-utf8",
        "duplicate-key",
        "extra-key",
        "empty",
        "unsafe-glob",
        "empty-brace-alternative",
    ],
)
def test_aud510_invalid_policy_fails_tier0_validation(
    tier0_case: tuple[Path, dict[str, object], dict[str, object]],
    policy_bytes: bytes | None,
) -> None:
    root, _, _ = tier0_case
    policy_path = root / "quality/coverage-source-policy.json"
    if policy_bytes is None:
        policy_path.unlink()
    else:
        policy_path.write_bytes(policy_bytes)

    errors = _tier0_errors(tier0_case)

    assert any("coverage source policy" in error for error in errors), errors


def test_aud510_deep_brace_policy_is_reported_as_invalid(
    tier0_case: tuple[Path, dict[str, object], dict[str, object]],
) -> None:
    root, _, _ = tier0_case
    policy = {
        "frontend": {"include": ["src/" + "{x}" * 1200], "exclude": ["src/test/**"]}
    }
    (root / "quality/coverage-source-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    errors = _tier0_errors(tier0_case)

    assert any("coverage source policy" in error for error in errors), errors


def test_aud510_malformed_glob_cannot_hide_real_tracked_tier0_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    policy_path = quality / "coverage-source-policy.json"
    policy_path.write_text(json.dumps(VALID_POLICY), encoding="utf-8")
    original_loader = validator._load_frontend_source_policy
    monkeypatch.setattr(
        validator,
        "_load_frontend_source_policy",
        lambda _root: original_loader(tmp_path),
    )

    contract = json.loads(
        (ROOT / "quality/quality-contract.json").read_text(encoding="utf-8")
    )
    scope = {
        "python": [TRACKED_PYTHON_TIER0],
        "frontend": [TRACKED_FRONTEND_TIER0],
    }
    contract["coverage_scope"] = scope
    rules_errors: list[str] = []
    rules = validator._load_canonical_tier0_rules(ROOT, rules_errors)
    assert rules_errors == []
    assert validator._tracked_source_paths(
        ROOT, [TRACKED_PYTHON_TIER0, TRACKED_FRONTEND_TIER0]
    ) == tuple(sorted((TRACKED_PYTHON_TIER0, TRACKED_FRONTEND_TIER0)))
    assert validator._expected_tier0_inventory(
        ROOT, contract["source_roots"], rules, scope
    ) == {
        ("python", TRACKED_PYTHON_TIER0),
        ("frontend", TRACKED_FRONTEND_TIER0),
    }

    measured = {"status": "native", "covered": 1, "total": 1, "percent": 100.0}
    metrics = {metric: dict(measured) for metric in METRICS}
    metrics["functions"] = {
        **measured,
        "status": "derived",
        "derivation": "AST function entries covered when the first executable body line is reported as executed",
    }
    manifest = {
        "coverage_scope": scope,
        "source_roots": contract["source_roots"],
        "tier0": {
            "status": "ready",
            "errors": [],
            "rules": rules,
            "files": [
                {
                    "path": TRACKED_PYTHON_TIER0,
                    "component": "python",
                    "metrics": metrics,
                }
            ],
            "metric_summary": {
                metric: {"applicable_files": 1, "not_applicable_files": 0}
                for metric in METRICS
            },
            "coverage": {metric: dict(value) for metric, value in metrics.items()},
        },
    }

    valid_errors = validator._validate_tier0_manifest(
        manifest, contract, ROOT, legacy_records={}
    )
    assert valid_errors == [
        f"Tier0 source inventory is missing evidence for {TRACKED_FRONTEND_TIER0}"
    ]

    malformed = {
        "frontend": {"include": ["src/**/*.{ts,tsx"], "exclude": ["src/**/*.test.ts"]}
    }
    policy_path.write_text(json.dumps(malformed), encoding="utf-8")
    errors = validator._validate_tier0_manifest(
        manifest, contract, ROOT, legacy_records={}
    )

    assert any("coverage source policy" in error for error in errors), errors


@pytest.mark.parametrize("consumer", ["validator", "producer"])
@pytest.mark.parametrize(
    "pattern",
    [
        "src/**/*.{ts,tsx",
        "src/**/*.{ts,tsx}}",
        "src/**/*.{ts,,tsx}",
        "src/**/*.{}",
        "src/**/*.{ts}",
        "src/**/*.{a..z}",
        "src/**/*.{a..z,ts}",
        "src/**/*.[ts",
        "src/**/*.ts]",
        "src/**/[]*.ts",
        "src/**/[!]*.ts",
        "src/**/[!a].ts",
        "src/**/[^a].ts",
        "src/**/[a/b].ts",
        "src/**/[abc]-*.ts",
        "src/**/[a-z]*.{ts,tsx}",
        "src/**/[[]segment[]].ts",
        "src/**/[{},].ts",
        "!src/**/*.ts",
        "src/**/@(a|b).ts",
        "src/(a|b).ts",
        "src/foo(bar).ts",
        "src/foo).ts",
        "src/foo|bar.ts",
        "src/?.ts",
        "src/**/file?.ts",
        "src/**/[z-a]*.ts",
        "src/**/[!z-a]*.ts",
        "src/**/[z-ac]*.ts",
        "src/" + "{a,b}" * 13 + ".ts",
        "src/" + "a" * 4096,
    ],
    ids=[
        "open-brace",
        "extra-close-brace",
        "empty-alternative",
        "empty-braces",
        "singleton-brace",
        "range-brace",
        "mixed-brace-range",
        "open-class",
        "extra-close-class",
        "empty-class",
        "literal-bang-class",
        "bang-class",
        "caret-class",
        "slash-in-class",
        "unsupported-class",
        "range-class",
        "literal-bracket-class",
        "punctuation-class",
        "negated-glob",
        "extglob",
        "regex-alternation",
        "regex-group",
        "unmatched-parenthesis",
        "standalone-pipe",
        "single-character-glob",
        "embedded-question-mark",
        "reversed-range",
        "reversed-negated-range",
        "partially-reversed-range",
        "too-many-expansions",
        "pattern-too-long",
    ],
)
def test_aud510_invalid_glob_is_rejected_by_each_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, consumer: str, pattern: str
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    policy = {"frontend": {"include": [pattern], "exclude": ["src/tests/**"]}}
    (quality / "coverage-source-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    if consumer == "validator":
        with pytest.raises(ValueError, match="coverage source policy"):
            validator._load_frontend_source_policy(tmp_path)
    else:
        monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
        producer = importlib.import_module("normalize_coverage_reports")
        monkeypatch.setattr(producer, "REPOSITORY_ROOT", tmp_path)
        with pytest.raises(producer._InputError, match="coverage source policy"):
            producer._load_frontend_coverage_policy()


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("src/**/*.{ts,tsx}", ("frontend/src/**/*.ts", "frontend/src/**/*.tsx")),
        ("src/**/file*.ts", ("frontend/src/**/file*.ts",)),
        (
            "src/**/file.{ts,{tsx,js}}",
            (
                "frontend/src/**/file.ts",
                "frontend/src/**/file.tsx",
                "frontend/src/**/file.js",
            ),
        ),
    ],
)
def test_aud510_supported_globs_match_both_consumers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pattern: str,
    expected: tuple[str, ...],
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    policy = {"frontend": {"include": [pattern], "exclude": ["src/tests/**"]}}
    (quality / "coverage-source-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")
    monkeypatch.setattr(producer, "REPOSITORY_ROOT", tmp_path)

    producer_policy = producer._load_frontend_coverage_policy()
    assert producer_policy == validator._load_frontend_source_policy(tmp_path)
    assert producer_policy[0][: len(expected)] == expected


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("frontend/src/auth/secure.ts", "frontend/src/*.ts", False),
        ("frontend/src/secure.ts", "frontend/src/*.ts", True),
        ("frontend/src/auth/secure.ts", "frontend/src/**/*.ts", True),
        ("frontend/src/secure.ts", "frontend/src/**/*.ts", True),
        ("frontend/src/.hidden.ts", "frontend/src/**/*.ts", False),
        ("frontend/src/.private/secure.ts", "frontend/src/**/*.ts", False),
        ("frontend/src/.hidden.ts", "frontend/src/**/.*.ts", True),
        ("frontend/src/a.ts", "frontend/src/a*/**", False),
        ("frontend/src/apple/file.ts", "frontend/src/a*/**", True),
    ],
)
def test_aud510_glob_matching_respects_path_segments_and_dotfiles(
    monkeypatch: pytest.MonkeyPatch, path: str, pattern: str, expected: bool
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")

    assert validator._source_policy_glob_matches(path, pattern) is expected
    assert producer._glob_matches_path(path, pattern) is expected


@pytest.mark.parametrize(
    ("path", "pattern", "equal_on_windows"),
    [
        ("frontend/src/Straße/file.ts", "frontend/src/strasse/*.ts", False),
        ("frontend/src/K/file.ts", "frontend/src/k/*.ts", False),
        ("frontend/src/ä/file.ts", "frontend/src/Ä/*.ts", True),
        ("frontend/src/σ/file.ts", "frontend/src/Σ/*.ts", True),
        ("frontend/src/𐐨/file.ts", "frontend/src/𐐀/*.ts", False),
    ],
)
def test_aud510_windows_nocase_matches_ecmascript_without_full_unicode_folding(
    monkeypatch: pytest.MonkeyPatch, path: str, pattern: str, equal_on_windows: bool
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")
    expected = equal_on_windows if os.name == "nt" else False

    assert validator._source_policy_glob_matches(path, pattern) is expected
    assert producer._glob_matches_path(path, pattern) is expected


def test_aud510_top_level_exclusion_cannot_hide_tracked_nested_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    policy = {"frontend": {"include": ["src/**/*.{ts,tsx}"], "exclude": ["src/*.tsx"]}}
    (quality / "coverage-source-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    assert validator._tracked_source_paths(ROOT, [TRACKED_FRONTEND_TIER0]) == (
        TRACKED_FRONTEND_TIER0,
    )
    loaded = validator._load_frontend_source_policy(tmp_path)
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_INCLUDE", loaded[0])
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_EXCLUDE", loaded[1])

    assert validator._is_production_source(TRACKED_FRONTEND_TIER0, "frontend", loaded)
    assert producer._tracked_source_is_coverable("frontend", TRACKED_FRONTEND_TIER0)


@pytest.mark.parametrize("consumer", ["validator", "producer"])
def test_aud510_total_glob_expansions_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, consumer: str
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    patterns = [f"src/{index}/" + "{a,b}" * 8 + ".ts" for index in range(17)]
    policy = {"frontend": {"include": patterns, "exclude": ["src/tests/**"]}}
    (quality / "coverage-source-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    if consumer == "validator":
        with pytest.raises(ValueError, match="coverage source policy"):
            validator._load_frontend_source_policy(tmp_path)
    else:
        monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
        producer = importlib.import_module("normalize_coverage_reports")
        monkeypatch.setattr(producer, "REPOSITORY_ROOT", tmp_path)
        with pytest.raises(producer._InputError, match="coverage source policy"):
            producer._load_frontend_coverage_policy()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("frontend/src/{a,b}.ts", True),
        ("frontend/src/{A,B}.ts", False),
        ("frontend/SRC/{a,b}.ts", False),
        ("frontend/src/a.ts", True),
    ],
)
def test_aud510_brace_glob_preserves_picomatch_exact_path_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, expected: bool
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    policy = {"frontend": {"include": ["src/{a,b}.ts"], "exclude": ["src/tests/**"]}}
    (quality / "coverage-source-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    loaded = validator._load_frontend_source_policy(tmp_path)
    monkeypatch.syspath_prepend(str(ROOT / "scripts/quality"))
    producer = importlib.import_module("normalize_coverage_reports")
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_INCLUDE", loaded[0])
    monkeypatch.setattr(producer, "FRONTEND_COVERAGE_EXCLUDE", loaded[1])

    assert validator._is_production_source(path, "frontend", loaded) is expected
    assert producer._tracked_source_is_coverable("frontend", path) is expected
