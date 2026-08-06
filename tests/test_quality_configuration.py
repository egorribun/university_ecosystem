import json
import re
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_VITEST_EXCLUSIONS = (
    '"**/routes/**/*"',
    '"**/api/events.ts"',
    '"**/api/stories.ts"',
    '"**/api/news.ts"',
    '"**/config/navigation.ts"',
    '"**/stores/index.ts"',
    '"**/features/index.ts"',
)

EXPECTED_VITEST_INCLUDE = ("src/**/*.{ts,tsx}",)

EXPECTED_VITEST_EXCLUSIONS = (
    "src/tests/**/*",
    "src/**/__tests__/**/*",
    "src/**/*.test.{ts,tsx}",
    "src/**/*.stories.{ts,tsx}",
    "src/setupTests.ts",
    "src/routeTree.gen.ts",
    "src/api/generated/**/*",
    "**/*.d.ts",
    "src/workers/**/*",
    "src/server.ts",
    "src/main.tsx",
    "src/sw.ts",
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


def test_governance_quality_configuration_matches_contract() -> None:
    contract = _read_contract()
    ownership = json.loads(_read_text("quality/ownership-mapping.json"))
    assert set(ownership["teams"].values()) == {"@egorribun"}

    codeowners = _read_text(".github/CODEOWNERS")
    assert "@security-team" not in codeowners
    assert "@devops-team" not in codeowners

    codecov = yaml.safe_load(_read_text("codecov.yml"))
    expected_flags = {
        "python": "app/",
        "frontend": "frontend/src/",
        "go-gateway": "services/gateway/",
        "go-ws-hub": "services/ws-hub/",
        "go-file-processor": "services/file-processor/",
        "rust-native": "native/rust_ext/",
        "rust-pyo3-sanitizer": "crates/pyo3-sanitizer/",
        "rust-wasm-sanitizer": "frontend/wasm-sanitizer/",
        "rust-crypto": "frontend/rust-crypto/",
    }
    assert set(codecov["flags"]) == set(expected_flags)
    for flag, path in expected_flags.items():
        assert codecov["flags"][flag]["paths"] == [path]
        coverage = contract["components"][flag]["coverage"]
        floor = next(value for value in coverage.values() if value)
        assert codecov["coverage"]["status"]["project"][flag]["target"] == f"{floor}%"
    assert codecov["comment"]["layout"] == "condensed_header, diff, flags, files"

    checkov = yaml.safe_load(_read_text(".github/workflows/checkov.yml"))
    checkov_with = checkov["jobs"]["checkov"]["steps"][1]["with"]
    assert checkov_with.get("soft_fail") is not True
    assert checkov["jobs"]["checkov"]["timeout-minutes"] == 20

    mutation_exclusions = json.loads(_read_text("quality/mutation-exclusions.json"))
    assert mutation_exclusions == {"version": 1, "exclusions": []}


def test_mutmut_uses_the_unit_population_instead_of_a_single_probe_file() -> None:
    mutation_config = _read_pyproject()["tool"]["mutmut"]

    assert mutation_config["pytest_add_cli_args_test_selection"] == [
        "-m",
        "not integration and not chaos and not performance and not slow",
        "tests/",
    ]
    assert "tests/test_tenant_rls.py" not in mutation_config["pytest_add_cli_args"]
    required_contract_inputs = {
        ".github",
        "quality",
        "scripts",
        "codecov.yml",
        "renovate.json",
        "uv.lock",
        ".pre-commit-config.yaml",
        "Makefile",
        "docs/DEPENDENCY_COOLDOWN_EMERGENCY.md",
        "k8s/kyverno",
        "crates/pyo3-sanitizer/src/lib.rs",
        "frontend/scripts/merge-vitest-coverage.mjs",
    }
    assert required_contract_inputs.issubset(mutation_config["also_copy"])


def test_test_duration_updater_aggregates_junit_cases_and_preserves_schema() -> None:
    from scripts.quality.update_test_durations import build_duration_payload

    with TemporaryDirectory() as temporary_directory:
        report_path = Path(temporary_directory) / "pytest-report.xml"
        report_path.write_text(
            """<?xml version='1.0' encoding='utf-8'?>
            <testsuites>
              <testsuite name='unit'>
                <testcase file='tests/test_alpha.py' time='0.25' />
                <testcase file='tests/test_alpha.py' time='0.75' />
                <testcase classname='tests.test_beta' name='test_value' time='2.0' />
                <testcase file='tests/test_skipped.py' time='0' />
              </testsuite>
            </testsuites>""",
            encoding="utf-8",
        )
        existing = {
            "version": 1,
            "default_duration_seconds": 1.0,
            "durations": {"tests/test_stale.py": 9.0},
        }

        payload = build_duration_payload(report_path, existing=existing)

    assert payload["version"] == 1
    assert payload["durations"] == {
        "tests/test_alpha.py": 1.0,
        "tests/test_beta.py": 2.0,
        "tests/test_skipped.py": 0.0,
        "tests/test_stale.py": 9.0,
    }
    assert payload["default_duration_seconds"] == 1.0


def test_test_duration_updater_rejects_negative_or_non_numeric_times() -> None:
    from scripts.quality.update_test_durations import build_duration_payload

    root = ElementTree.Element("testsuite")
    ElementTree.SubElement(root, "testcase", file="tests/test_bad.py", time="-1")
    ElementTree.SubElement(root, "testcase", file="tests/test_worse.py", time="nan")

    with TemporaryDirectory() as temporary_directory:
        report_path = Path(temporary_directory) / "pytest-report.xml"
        ElementTree.ElementTree(root).write(report_path, encoding="utf-8")

        try:
            build_duration_payload(report_path, existing={})
        except ValueError as error:
            assert "time" in str(error)
        else:
            raise AssertionError("invalid JUnit timing data must be rejected")


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


def test_mypy_excludes_are_valid_regular_expressions() -> None:
    excludes = _read_pyproject()["tool"]["mypy"]["exclude"]

    assert isinstance(excludes, list)
    for pattern in excludes:
        assert isinstance(pattern, str)
        re.compile(pattern)


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
    assert _extract_string_array(coverage, "include") == EXPECTED_VITEST_INCLUDE
    assert _extract_string_array(coverage, "exclude") == EXPECTED_VITEST_EXCLUSIONS

    thresholds = _extract_object_body(coverage, "thresholds")
    for metric in ("statements", "branches", "functions", "lines"):
        value = contract["components"]["frontend"]["coverage"][metric]
        match = re.search(rf"\b{metric}\s*:\s*(\d+)\b", thresholds)
        assert match is not None, f"missing {metric} coverage threshold"
        assert int(match.group(1)) == value

    exclusions = _extract_string_array(coverage, "exclude")
    for forbidden_exclusion in FORBIDDEN_VITEST_EXCLUSIONS:
        assert forbidden_exclusion.removeprefix('"').removesuffix('"') not in exclusions


def test_vitest_does_not_discover_stryker_sandbox_tests() -> None:
    config = _read_text("frontend/vitest.config.ts")

    assert '"stryker-tmp/**"' in config
    assert '".stryker-tmp/**"' in config


def test_stryker_does_not_copy_generated_caches_or_sandboxes() -> None:
    config = _read_text("frontend/stryker.config.mjs")

    assert (
        'const strykerTempRoot = path.join(os.tmpdir(), "university-ecosystem-stryker")'
        in config
    )
    assert "tempDirName: strykerTempRoot" in config
    assert 'cleanTempDir: "always"' in config
    for fragment in (
        '"**/.codex_*/**"',
        '"**/target/**"',
        '"/reports/**"',
    ):
        assert fragment in config


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
    test_ci = package["scripts"]["test:ci"]
    assert test_ci.startswith("npm run test:wasm && vitest run ")
    assert "--configLoader runner" in test_ci
    assert "--coverage" in test_ci
    assert package["scripts"]["test:watch"] == "vitest --configLoader runner"

    vitest_packages = package["devDependencies"]
    vitest_specs = {
        vitest_packages[name]
        for name in ("vitest", "@vitest/browser", "@vitest/coverage-v8")
    }
    assert len(vitest_specs) == 1
