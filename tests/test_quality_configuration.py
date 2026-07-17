import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_VITEST_EXCLUSIONS = (
    '"src/workers/**/*"',
    '"**/routes/**/*"',
    '"**/pages/**/*"',
    '"src/App.tsx"',
    '"src/AppProviders.tsx"',
    '"**/api/events.ts"',
    '"**/api/stories.ts"',
    '"**/api/news.ts"',
    '"**/config/navigation.ts"',
    '"**/stores/index.ts"',
    '"**/features/index.ts"',
)

EXPECTED_VITEST_EXCLUSIONS = (
    "src/tests/**/*",
    "src/**/__tests__/**/*",
    "src/**/*.test.{ts,tsx}",
    "src/**/*.stories.{ts,tsx}",
    "src/setupTests.ts",
    "src/routeTree.gen.ts",
    "src/api/generated/**/*",
    "**/*.d.ts",
    "src/test/**/*",
)


def _read_contract() -> dict[str, object]:
    return json.loads(
        (ROOT / "quality" / "quality-contract.json").read_text(encoding="utf-8")
    )


def _read_pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _extract_object_body(source: str, property_name: str) -> str:
    match = re.search(rf"\b{re.escape(property_name)}\s*:\s*\{{", source)
    assert match is not None, f"missing {property_name} object"

    start = match.end()
    depth = 1
    for index, character in enumerate(source[start:], start=start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]

    raise AssertionError(f"unterminated {property_name} object")


def _extract_string_array(source: str, property_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"\b{re.escape(property_name)}\s*:\s*\[(?P<items>.*?)\]",
        source,
        re.DOTALL,
    )
    assert match is not None, f"missing {property_name} array"
    return tuple(re.findall(r'"([^"]+)"', match.group("items")))


def _make_target_body(source: str, target_name: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(target_name)}:\s*\n(?P<body>(?:\t.*(?:\n|$))*)",
        source,
    )
    assert match is not None, f"missing {target_name} target"
    return match.group("body")


def _sonar_property(source: str, property_name: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(property_name)}=(?P<value>.+)$",
        source,
    )
    assert match is not None, f"missing {property_name}"
    return match.group("value")


def test_python_coverage_policy_and_output_paths_match_quality_contract() -> None:
    contract = _read_contract()
    coverage = _read_pyproject()["tool"]["coverage"]

    assert coverage["run"]["branch"] is True
    assert coverage["report"]["fail_under"] == contract["coverage_minimums"]["lines"]
    assert coverage["xml"]["output"] == "coverage.xml"
    assert coverage["json"]["output"] == "artifacts/coverage/python/coverage.json"


def test_frontend_coverage_policy_and_source_universe_match_quality_contract() -> None:
    contract = _read_contract()
    coverage = _extract_object_body(_read_text("frontend/vitest.config.ts"), "coverage")

    assert _extract_string_array(coverage, "reporter") == (
        "text",
        "json",
        "lcov",
        "html",
    )
    reports_directory = re.search(
        r'\breportsDirectory\s*:\s*"(?P<value>[^"]+)"', coverage
    )
    assert reports_directory is not None, "missing reportsDirectory"
    assert reports_directory.group("value") == "coverage"
    assert _extract_string_array(coverage, "include") == ("src/**/*",)
    assert _extract_string_array(coverage, "exclude") == EXPECTED_VITEST_EXCLUSIONS

    thresholds = _extract_object_body(coverage, "thresholds")
    for metric in ("statements", "branches", "functions", "lines"):
        value = contract["coverage_minimums"][metric]
        match = re.search(rf"\b{metric}\s*:\s*(\d+)\b", thresholds)
        assert match is not None, f"missing {metric} coverage threshold"
        assert int(match.group(1)) == value

    exclusions = _extract_string_array(coverage, "exclude")
    for forbidden_exclusion in FORBIDDEN_VITEST_EXCLUSIONS:
        assert forbidden_exclusion.removeprefix('"').removesuffix('"') not in exclusions


def test_coverage_commands_and_sonar_paths_match_quality_contract() -> None:
    makefile = _read_text("Makefile")
    required_fragments = (
        "mkdir -p artifacts/coverage/python",
        "--cov-report=xml:coverage.xml",
        "--cov-report=json:artifacts/coverage/python/coverage.json",
    )
    for target_name in ("backend-test", "coverage"):
        target = _make_target_body(makefile, target_name)
        for fragment in required_fragments:
            assert fragment in target
        assert "--cov-fail-under=" not in target

    sonar = _read_text("sonar-project.properties")
    assert _sonar_property(sonar, "sonar.python.coverage.reportPaths") == "coverage.xml"
    assert (
        _sonar_property(sonar, "sonar.javascript.lcov.reportPaths")
        == "frontend/coverage/lcov.info"
    )

    package = json.loads(_read_text("frontend/package.json"))
    assert package["scripts"]["test:ci"].startswith("vitest run --coverage")
