import json
import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath
from shutil import which
from tempfile import TemporaryDirectory
from urllib.parse import unquote
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
    "src/test/**/*",
)

MARKDOWN_LINK_RE = re.compile(
    r"!?\[[^\]]*\]\((?:<(?P<angled>[^>]+)>|(?P<plain>[^\s)]+))"
)
MARKDOWN_REFERENCE_LINK_RE = re.compile(
    r"^\s*\[[^\]]+\]:\s*(?:<(?P<angled>[^>]+)>|(?P<plain>\S+))",
    re.MULTILINE,
)


def _tracked_files(*pathspecs: str) -> list[str]:
    git_executable = which("git")
    assert git_executable is not None, "Git is required for repository contracts"
    return subprocess.run(  # noqa: S603 -- resolved Git executable, fixed operation
        [git_executable, "ls-files", "--", *pathspecs],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def test_repository_skill_catalogs_are_exact_mirrors_without_stale_archive() -> None:
    primary_root = ROOT / ".agents" / "skills"
    opencode_root = ROOT / ".opencode" / "skills"
    archive_root = ROOT / ".agents" / "skills_archive"

    def catalog(root: Path) -> dict[PurePosixPath, bytes]:
        prefix = f"{root.relative_to(ROOT).as_posix()}/"
        return {
            PurePosixPath(relative_name.removeprefix(prefix)): (
                ROOT / relative_name
            ).read_bytes()
            for relative_name in _tracked_files(root.relative_to(ROOT).as_posix())
        }

    primary = catalog(primary_root)
    opencode = catalog(opencode_root)

    assert primary, "the canonical repository skill catalog must not be empty"
    assert primary.keys() == opencode.keys()
    assert primary == opencode
    assert not any(path.is_file() for path in archive_root.rglob("*"))


def test_agent_instruction_surface_has_one_canonical_source() -> None:
    canonical = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude_adapter = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "NEVER include `Co-Authored-By`" in canonical
    assert (
        "`AGENTS.md` is the single canonical repository instruction file"
        in claude_adapter
    )
    assert len(claude_adapter.encode("utf-8")) < 4_096
    assert "docs/audits/AUDIT_WAVE" not in claude_adapter


def test_canonical_markdown_internal_links_resolve() -> None:
    tracked = _tracked_files("*.md")
    excluded_prefixes = (
        ".agents/",
        ".opencode/",
        "docs/audits/archive/",
    )
    missing: list[str] = []

    for relative_name in tracked:
        if relative_name.startswith(excluded_prefixes):
            continue
        document = ROOT / relative_name
        if not document.is_file():
            continue
        text = document.read_text(encoding="utf-8")
        for link_pattern in (MARKDOWN_LINK_RE, MARKDOWN_REFERENCE_LINK_RE):
            for match in link_pattern.finditer(text):
                target = match.group("angled") or match.group("plain") or ""
                if not target or target.startswith(
                    (
                        "#",
                        "http://",
                        "https://",
                        "mailto:",
                        "tel:",
                        "data:",
                        "file://",
                    )
                ):
                    continue
                path_text = unquote(target.split("#", maxsplit=1)[0])
                path_text = re.sub(r":\d+(?:-\d+)?$", "", path_text)
                if not path_text:
                    continue
                candidate = (
                    ROOT / path_text.lstrip("/")
                    if path_text.startswith("/")
                    else document.parent / path_text
                )
                if not candidate.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    missing.append(f"{relative_name}:{line} -> {target}")

    assert not missing, "broken internal Markdown links:\n" + "\n".join(missing)


def _read_contract() -> dict[str, object]:
    return json.loads(
        (ROOT / "quality" / "quality-contract.json").read_text(encoding="utf-8")
    )


def _read_pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _dockerignore_patterns(relative_path: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in _read_text(relative_path).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_xdist_sqlite_database_artifacts_are_ignored() -> None:
    gitignore_patterns = set(_read_text(".gitignore").splitlines())

    assert {
        "test_gw*.db",
        "test_gw*.db-wal",
        "test_gw*.db-shm",
    }.issubset(gitignore_patterns)


def test_root_pytest_report_artifact_is_ignored() -> None:
    assert "pytest-report.xml" in set(_read_text(".gitignore").splitlines())


def test_backend_test_files_use_domain_oriented_names() -> None:
    forbidden = re.compile(
        r"(?:wave\d+|session\d+|booster|topup|coverage_(?:boost|closure))",
        re.I,
    )
    violations = sorted(
        path.name
        for path in (ROOT / "tests").glob("test_*.py")
        if forbidden.search(path.name)
    )

    assert violations == []


def test_python_coverage_excludes_only_non_runtime_typing_contours() -> None:
    coverage_report = _read_pyproject()["tool"]["coverage"]["report"]

    assert coverage_report["exclude_lines"] == [
        "pragma: no cover",
        "if TYPE_CHECKING:",
    ]


def test_runtime_source_has_no_executable_coverage_pragmas() -> None:
    usages: list[tuple[str, str]] = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "pragma: no cover" in line:
                usages.append((path.relative_to(ROOT).as_posix(), line.strip()))

    assert usages == [
        (
            "app/core/event_decorators.py",
            "]: ...  # pragma: no cover - typing-only overload",
        ),
        (
            "app/core/event_decorators.py",
            "]: ...  # pragma: no cover - typing-only overload",
        ),
    ]


def test_governance_quality_configuration_matches_contract() -> None:
    contract = _read_contract()
    ownership = json.loads(_read_text("quality/ownership-mapping.json"))
    assert set(ownership["teams"].values()) == {"@egorribun"}

    codeowners = _read_text(".github/CODEOWNERS")
    assert "@security-team" not in codeowners
    assert "@devops-team" not in codeowners
    for protected_path in (
        "scripts/quality/compare_paired_benchmarks.py",
        "scripts/quality/capture_isolated_benchmarks.py",
        "containers/quality/Dockerfile.performance-rust",
    ):
        assert f"{protected_path} @egorribun" in codeowners

    codecov = yaml.safe_load(_read_text("codecov.yml"))
    expected_flags = {
        "python": ["app/"],
        "frontend": ["frontend/src/"],
        "go-gateway": ["services/gateway/"],
        "go-ws-hub": ["services/ws-hub/"],
        "go-file-processor": ["services/file-processor/"],
        "go-shared": [
            "services/cmd/uni-cli/",
            "services/pkg/spiffe/",
            "services/pkg/spicedb/",
        ],
        "rust-native": ["native/rust_ext/"],
        "rust-pyo3-sanitizer": ["crates/pyo3-sanitizer/"],
        "rust-wasm-sanitizer": ["frontend/wasm-sanitizer/"],
        "rust-crypto": ["frontend/rust-crypto/"],
    }
    assert set(codecov["flags"]) == set(expected_flags)
    assert codecov["coverage"]["status"]["project"]["default"] == {
        "target": "100%",
        "threshold": "0%",
    }
    assert codecov["coverage"]["status"]["patch"]["default"] == {
        "target": "100%",
        "threshold": "0%",
    }
    for flag, paths in expected_flags.items():
        assert codecov["flags"][flag]["paths"] == paths
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


def test_uv_version_is_pinned_for_reproducible_ci_bootstrap() -> None:
    uv_config = _read_pyproject()["tool"]["uv"]

    assert uv_config["required-version"] == "==0.11.28"


def test_backend_dockerfile_uses_the_required_uv_version() -> None:
    dockerfile = (ROOT / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "ghcr.io/astral-sh/uv:0.11.28@sha256:" in dockerfile


def test_test_dockerfile_uses_the_required_uv_version() -> None:
    dockerfile = (ROOT / "Dockerfile.test").read_text(encoding="utf-8")

    assert "ghcr.io/astral-sh/uv:0.11.28@sha256:" in dockerfile


def test_test_image_installs_atheris_toolchain() -> None:
    dockerfile = (ROOT / "Dockerfile.test").read_text(encoding="utf-8")

    package_install = re.search(
        r"apt-get install -y --no-install-recommends \\\n(?P<packages>.*?)\n    &&",
        dockerfile,
        re.DOTALL,
    )

    assert package_install is not None
    package_names = package_install.group("packages").split()
    assert "clang" in package_names
    assert "libclang-rt-14-dev" in package_names


def test_test_image_copies_rust_benches_declared_in_workspace_manifests() -> None:
    dockerfile = (ROOT / "Dockerfile.test").read_text(encoding="utf-8")

    assert re.search(
        r"^COPY native/rust_ext/benches native/rust_ext/benches$",
        dockerfile,
        re.MULTILINE,
    )
    assert re.search(
        r"^COPY crates/pyo3-sanitizer/benches crates/pyo3-sanitizer/benches$",
        dockerfile,
        re.MULTILINE,
    )


def test_test_docker_context_excludes_recursive_rust_build_artifacts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "**/target/" in dockerignore
    assert ".pre-commit-trivy-cache/" in dockerignore


def test_docker_context_excludes_local_quality_virtualenv() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert ".quality-venv/" in dockerignore.splitlines()


def test_test_image_context_preserves_required_and_safe_inputs() -> None:
    test_dockerignore = ROOT / "Dockerfile.test.dockerignore"

    assert test_dockerignore.is_file()

    root_patterns = _dockerignore_patterns(".dockerignore")
    test_patterns = _dockerignore_patterns("Dockerfile.test.dockerignore")
    required_docker_config = (
        "!backend.Dockerfile",
        "!Dockerfile.test",
        "!Dockerfile.test.dockerignore",
        "!.gitignore",
    )
    required_safety_exclusions = (
        ".secrets/",
        "**/.secrets/",
        ".codex-uv-cache/",
        ".agents/",
        ".opencode/",
        ".superpowers/",
        ".quality-pytest-tmp*/",
        ".worktrees/",
        ".pytest_tmp*/",
        ".uv-cache*/",
        ".docker-quality-closure/",
    )
    assert "tests/" in root_patterns
    assert "tests/" not in test_patterns
    assert ".github" in root_patterns
    assert ".github" not in test_patterns
    for safety_exclusion in required_safety_exclusions:
        assert safety_exclusion in root_patterns
        assert safety_exclusion in test_patterns

    expected_test_patterns = tuple(
        pattern for pattern in root_patterns if pattern not in {"tests/", ".github"}
    )
    dockerfile_rule_index = expected_test_patterns.index("Dockerfile*")
    expected_test_patterns = (
        expected_test_patterns[: dockerfile_rule_index + 1]
        + required_docker_config
        + expected_test_patterns[dockerfile_rule_index + 1 :]
    )
    assert test_patterns == expected_test_patterns
    test_dockerfile_rule_index = test_patterns.index("Dockerfile*")
    assert (
        test_patterns[
            test_dockerfile_rule_index + 1 : test_dockerfile_rule_index
            + 1
            + len(required_docker_config)
        ]
        == required_docker_config
    )
    assert 'CMD ["pytest", "tests/",' in _read_text("Dockerfile.test")


def test_mutmut_uses_the_unit_population_instead_of_a_single_probe_file() -> None:
    mutation_config = _read_pyproject()["tool"]["mutmut"]

    assert mutation_config["source_paths"] == ["app/"]
    assert "paths_to_mutate" not in mutation_config
    assert mutation_config["timeout_multiplier"] == 15.0
    assert mutation_config["timeout_constant"] == 1.0
    assert mutation_config["pytest_add_cli_args_test_selection"] == [
        "-m",
        "not integration and not chaos and not performance and not slow",
        "tests/",
    ]
    assert "tests/test_tenant_rls.py" not in mutation_config["pytest_add_cli_args"]
    required_contract_inputs = {
        ".github",
        ".gitignore",
        ".dockerignore",
        "quality",
        "scripts",
        "Dockerfile.test",
        "Dockerfile.test.dockerignore",
        "backend.Dockerfile",
        "codecov.yml",
        "renovate.json",
        "uv.lock",
        ".pre-commit-config.yaml",
        "Makefile",
        "docs",
        "containers/quality",
        "k8s/kyverno",
        "k8s/flagd",
        "crates/pyo3-sanitizer/src",
        "frontend/scripts",
        "frontend/package.json",
        "frontend/stryker.config.mjs",
        "frontend/vitest.config.ts",
        "sonar-project.properties",
    }
    assert required_contract_inputs.issubset(mutation_config["also_copy"])


def test_mutmut_bounds_each_hanging_test_without_weakening_mutation_scope() -> None:
    """A hung mutant must become a killed result, not exhaust the shard watchdog."""

    pyproject = _read_pyproject()
    mutation_config = pyproject["tool"]["mutmut"]
    dev_dependencies = pyproject["dependency-groups"]["dev"]

    assert "pytest-timeout>=2.4.0" in dev_dependencies
    assert "--timeout=120" in mutation_config["pytest_add_cli_args"]
    assert "--timeout-method=signal" in mutation_config["pytest_add_cli_args"]


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
    assert re.search(r"\bexperimentalAstAwareRemapping\s*:\s*true\b", coverage)
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

    testing_guide = _read_text("TESTING.md")
    assert "--cov-fail-under=0" not in testing_guide
    assert "inherits the fail-closed threshold" in testing_guide

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
