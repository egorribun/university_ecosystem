from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

try:
    from scripts.quality import check_orphans_and_anti_patterns as checker
    from scripts.quality import generate_test_inventory as inventory
    from scripts.quality.check_orphans_and_anti_patterns import (
        check_anti_patterns,
        check_go_duplicates,
        check_python_duplicates_and_imports,
        find_python_repository_references,
        find_typescript_repository_references,
        matches_source,
    )
    from scripts.quality.generate_test_inventory import (
        classify_file,
        is_generated,
        is_tier0,
        resolve_owner,
        scan_repository,
        should_prune_directory,
    )
except ImportError:
    # QUALITY-1207 @egorribun: Skip test when scripts module is not importable under mutmut isolation
    pytest.skip(
        "scripts module not available (e.g. under mutmut isolation)",
        allow_module_level=True,
    )


def _write_repository_contract(tmp_path: Path, monkeypatch, content: str) -> Path:
    repository = tmp_path / "repository"
    test_path = repository / "tests" / "test_contract.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    return test_path


def test_resolve_owner() -> None:
    teams = {
        "app/api/users": "@egorribun",
        "app/": "@egorribun",
        "frontend/src/": "@egorribun",
    }
    assert resolve_owner("app/api/users/router.py", teams) == "@egorribun"
    assert resolve_owner("app/core/config.py", teams) == "@egorribun"
    assert resolve_owner("frontend/src/components/Button.tsx", teams) == "@egorribun"
    assert resolve_owner("random_file.txt", teams) is None


def test_is_tier0() -> None:
    tier0_rules = ["**/auth/**", "**/security/**"]
    assert is_tier0("app/api/auth/router.py", tier0_rules) is True
    assert is_tier0("frontend/src/security/AuthContext.tsx", tier0_rules) is True
    assert is_tier0("app/core/config.py", tier0_rules) is False


def test_is_generated() -> None:
    generated_patterns = ["**/routeTree.gen.ts", "**/*.pb.go"]
    assert is_generated("frontend/src/routeTree.gen.ts", generated_patterns) is True
    assert is_generated("services/gateway/pb/auth.pb.go", generated_patterns) is True
    assert is_generated("app/core/config.py", generated_patterns) is False


def test_classify_file() -> None:
    generated_patterns = ["**/routeTree.gen.ts"]

    # Generated
    assert (
        classify_file("frontend/src/routeTree.gen.ts", generated_patterns)
        == "generated"
    )

    # Test
    assert classify_file("tests/core/test_auth.py", generated_patterns) == "test"
    assert (
        classify_file("frontend/src/components/Button.test.tsx", generated_patterns)
        == "test"
    )
    assert classify_file("services/gateway/auth_test.go", generated_patterns) == "test"

    # Source
    assert classify_file("app/core/config.py", generated_patterns) == "source"
    assert (
        classify_file("frontend/src/components/Button.tsx", generated_patterns)
        == "source"
    )
    assert classify_file("services/gateway/main.go", generated_patterns) == "source"
    # Authored capability code lives beside generated protobuf transport files
    # under gen/go; generated patterns are checked first, so only the authored
    # contract is treated as source and can own its focused Go tests.
    assert (
        classify_file("gen/go/file_processor/v1/capability.go", generated_patterns)
        == "source"
    )
    assert (
        classify_file("gen/go/file_processor/v1/file.pb.go", ["**/*.pb.go"])
        == "generated"
    )

    # Utility
    assert classify_file("scripts/setup.sh", generated_patterns) == "utility"


def test_rust_fuzz_tsan_contract_is_backed_by_repository_references() -> None:
    contract = Path(__file__).with_name("test_rust_fuzz_tsan_contract.py")

    references = find_python_repository_references(contract)

    assert {
        ".github/workflows/rust-fuzz.yml",
        "scripts/run_tsan_tests.sh",
        "tests/tsan_suppressions.txt",
    }.issubset(references)


def test_api_dependency_contract_is_backed_by_repository_references() -> None:
    contract = Path(__file__).with_name("test_api_dependency_injection_contract.py")

    references = find_python_repository_references(contract)

    assert "app/api" in references
    assert matches_source(
        "tests/test_api_dependency_injection_contract.py",
        set(),
        [],
        repository_references=references,
        reference_paths={"app/api/auth/login.py"},
    )


def test_typescript_contract_is_backed_by_repository_references() -> None:
    contract_path = (
        "frontend/src/__tests__/events-history-scroll-restoration.contract.test.ts"
    )
    contract = Path(contract_path)
    scenario = "frontend/tests/e2e/events-history-scroll-restoration.spec.ts"
    references = find_typescript_repository_references(contract)

    assert references == {scenario}
    assert matches_source(
        contract_path,
        set(),
        [],
        repository_references=references,
        reference_paths={scenario},
    )


def test_typescript_repository_references_reject_dynamic_and_outside_paths(
    tmp_path: Path, monkeypatch
) -> None:
    repository = tmp_path / "repository"
    contract = repository / "frontend" / "src" / "contract.test.ts"
    contract.parent.mkdir(parents=True)
    (repository / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.ts"
    outside.write_text("export {}", encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    contract.write_text(
        'readFileSync(resolve(process.cwd(), target), "utf8")',
        encoding="utf-8",
    )
    assert find_typescript_repository_references(contract) == set()

    contract.write_text(
        'readFileSync(resolve(process.cwd(), "../../outside.ts"), "utf8")',
        encoding="utf-8",
    )
    assert find_typescript_repository_references(contract) == set()


def test_inventory_ignores_root_output_backups_but_keeps_authored_artifact_modules(
    tmp_path: Path, monkeypatch
) -> None:
    for relative_path in (
        "artifacts/wip/frontend/src/example.test.ts",
        "app/artifacts/model.py",
        "tests/test_authored.py",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(inventory, "REPOSITORY_ROOT", tmp_path)
    records = scan_repository(
        {"teams": {}, "tier0_rules": [], "generated_patterns": []}
    )
    assert {record["path"] for record in records} == {
        "app/artifacts/model.py",
        "tests/test_authored.py",
    }


def test_inventory_prunes_dependency_and_hidden_directories(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "visible.py").write_text("pass", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "hidden.ts").write_text(
        "export {}", encoding="utf-8"
    )
    (tmp_path / "mutants" / "tests").mkdir(parents=True)
    (tmp_path / "mutants" / "tests" / "test_generated_copy.py").write_text(
        "pass", encoding="utf-8"
    )
    (tmp_path / ".codex" / "cache").mkdir(parents=True)
    (tmp_path / ".codex" / "cache" / "hidden.py").write_text("pass", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci", encoding="utf-8"
    )
    (tmp_path / ".husky").mkdir()
    (tmp_path / ".husky" / "pre-commit").write_text(
        "npm --prefix frontend run lint-staged", encoding="utf-8"
    )

    monkeypatch.setattr(inventory, "REPOSITORY_ROOT", tmp_path)
    records = scan_repository(
        {
            "teams": {},
            "tier0_rules": [],
            "generated_patterns": [],
        }
    )
    paths = {str(record["path"]) for record in records}

    assert paths == {
        ".github/workflows/ci.yml",
        ".husky/pre-commit",
        "app/visible.py",
    }
    assert should_prune_directory("node_modules") is True
    assert should_prune_directory("mutants") is True
    assert should_prune_directory(".codex") is True
    assert should_prune_directory("stryker-tmp") is True
    assert should_prune_directory(".github") is False
    assert should_prune_directory(".husky") is False


def test_inventory_indexes_authored_hooks_but_prunes_agent_state(
    tmp_path: Path, monkeypatch
) -> None:
    files = {
        ".agents/hooks/common.py": "def helper(): pass\n",
        ".agents/hooks/post_tool_linter.py": "def lint(): pass\n",
        ".agents/hooks/.gate_state.json": "{}\n",
        ".agents/hooks/.gate_state.json.lock": "\n",
        ".agents/skills/notauthored.py": "pass\n",
        ".agents/subagents/notauthored.py": "pass\n",
        ".agents/hooks.json": "{}\n",
        ".agents/subagents.json": "{}\n",
    }
    for relative_path, contents in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    cached_hook = tmp_path / ".agents" / "hooks" / "__pycache__" / "cached.py"
    cached_hook.parent.mkdir(parents=True)
    cached_hook.write_text("pass\n", encoding="utf-8")

    monkeypatch.setattr(inventory, "REPOSITORY_ROOT", tmp_path)
    records = scan_repository(
        {"teams": {}, "tier0_rules": [], "generated_patterns": []}
    )

    assert {
        (str(record["path"]), str(record["classification"])) for record in records
    } == {
        (".agents/hooks/common.py", "utility"),
        (".agents/hooks/post_tool_linter.py", "utility"),
    }


def test_check_anti_patterns(tmp_path: Path) -> None:
    # 1. Focused test marker error
    test_file_focused = tmp_path / "test_focused.ts"
    test_file_focused.write_text(
        "describe.on" + "ly('some test', () => {})", encoding="utf-8"
    )
    errors: list[str] = []
    check_anti_patterns(test_file_focused, errors, [], [])
    assert any("focused test marker" in err for err in errors)

    # 2. Sleep without pragma error
    test_file_sleep = tmp_path / "test_sleep.py"
    test_file_sleep.write_text("import time\ntime.sleep(5)", encoding="utf-8")
    errors = []
    check_anti_patterns(test_file_sleep, errors, [], [])
    assert any("sleep" in err for err in errors)

    # 3. Sleep with pragma allowed
    errors = []
    check_anti_patterns(test_file_sleep, errors, ["**/test_sleep.py"], [])
    assert len(errors) == 0

    # 4. Sleep with inline pragma allowed
    test_file_sleep_pragma = tmp_path / "test_sleep_pragma.py"
    test_file_sleep_pragma.write_text(
        "time.sleep(5)  # pragma: allowlist", encoding="utf-8"
    )
    errors = []
    check_anti_patterns(test_file_sleep_pragma, errors, [], [])
    assert len(errors) == 0

    # 5. Dynamic skip error (no issue/owner)
    test_file_skip = tmp_path / "test_skip.py"
    test_file_skip.write_text("pytest.sk" + "ip('reason')", encoding="utf-8")
    errors = []
    check_anti_patterns(test_file_skip, errors, [], [])
    assert any("dynamic skip" in err for err in errors)

    # 6. Dynamic skip with issue and owner allowed
    test_file_skip_valid = tmp_path / "test_skip_valid.py"
    test_file_skip_valid.write_text(
        "# QUALITY-123 @someuser\npytest.sk" + "ip('reason')", encoding="utf-8"
    )
    errors = []
    check_anti_patterns(test_file_skip_valid, errors, [], [])
    assert len(errors) == 0


def test_python_duplicate_scopes(tmp_path: Path) -> None:
    test_file = tmp_path / "test_duplicates.py"
    test_file.write_text(
        """
class TestA:
    def test_foo(self):
        pass

class TestB:
    def test_foo(self):
        pass
""",
        encoding="utf-8",
    )
    errors: list[str] = []
    check_python_duplicates_and_imports(test_file, errors)
    # Distinct classes, so no duplicates should be reported
    assert len(errors) == 0

    test_file_dup = tmp_path / "test_duplicates_real.py"
    test_file_dup.write_text(
        """
class TestA:
    def test_foo(self):
        pass
    def test_foo(self):
        pass
""",
        encoding="utf-8",
    )
    errors = []
    check_python_duplicates_and_imports(test_file_dup, errors)
    assert len(errors) == 1
    assert "duplicate test function 'test_foo'" in errors[0]


def test_python_duplicate_checker_scopes_nested_functions_independently(
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "test_nested_duplicates.py"
    test_file.write_text(
        """
def test_parent_one():
    @pytest.mark.parametrize("value", [1])
    def test_helper():
        pass

def test_parent_two():
    @pytest.mark.parametrize("value", [2])
    def test_helper():
        pass

async def test_async_parent_one():
    @pytest.mark.parametrize("value", [1])
    def test_async_helper():
        pass

async def test_async_parent_two():
    @pytest.mark.parametrize("value", [2])
    def test_async_helper():
        pass
""",
        encoding="utf-8",
    )
    errors: list[str] = []

    check_python_duplicates_and_imports(test_file, errors)

    assert errors == []


def test_python_duplicate_checker_detects_async_and_mixed_same_scope_duplicates(
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "test_async_duplicates.py"
    test_file.write_text(
        """
class TestOuter:
    class TestAsync:
        @pytest.mark.asyncio
        async def test_duplicate(self):
            pass

        @pytest.mark.asyncio
        async def test_duplicate(self):
            pass

def test_parent():
    @pytest.mark.parametrize("value", [1])
    def test_nested(self):
        pass

    @pytest.mark.asyncio
    async def test_nested(self):
        pass
""",
        encoding="utf-8",
    )
    errors: list[str] = []

    check_python_duplicates_and_imports(test_file, errors)

    assert len(errors) == 2
    assert all("duplicate test function" in error for error in errors)


def test_go_duplicate_checker_ignores_comments_and_literals(tmp_path: Path) -> None:
    test_file = tmp_path / "duplicates_test.go"
    test_file.write_text(
        r"""package sample
// func TestLineComment(t *testing.T) {}
/* func TestBlockComment(t *testing.T) {} */
var interpreted = "escaped quote: \" // func TestInterpreted(t *testing.T) {}"
var raw = `raw string:
func TestRaw(t *testing.T) {}
// still literal
/* still a raw string */`
var slash = '/'
var quote = '\''
var backslash = '\\'

func TestLineComment(t *testing.T) {}
func TestBlockComment(t *testing.T) {}
func TestInterpreted(t *testing.T) {}
func TestRaw(t *testing.T) {}
""",
        encoding="utf-8",
    )
    errors: list[str] = []

    check_go_duplicates(test_file, errors)

    assert errors == []


def test_go_duplicate_checker_still_rejects_real_duplicate_declarations(
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "duplicates_test.go"
    test_file.write_text(
        "package sample\n"
        "func /* declaration comment */ TestDuplicate(t *testing.T) {}\n"
        "func TestDuplicate(t *testing.T) {}\n",
        encoding="utf-8",
    )
    errors: list[str] = []

    check_go_duplicates(test_file, errors)

    assert len(errors) == 1
    assert "duplicate test function name 'TestDuplicate'" in errors[0]


def test_matches_source_normalizes_frontend_closure_test_suffix() -> None:
    test_path = "frontend/src/api/interceptors/__tests__/rateLimit.closure.test.ts"
    source_paths = {"frontend/src/api/interceptors/rateLimit.ts"}

    assert matches_source(test_path, source_paths, []) is True


def test_matches_source_accepts_production_variant_suites() -> None:
    cases = (
        (
            "frontend/src/api/__tests__/client.csrf.production.test.ts",
            "frontend/src/api/client.ts",
        ),
        (
            "frontend/src/components/motion/__tests__/PageFadeIn.production.test.tsx",
            "frontend/src/components/motion/PageFadeIn.tsx",
        ),
        (
            "frontend/src/components/profile/__tests__/NowPlayingCard.production.test.tsx",
            "frontend/src/components/profile/NowPlayingCard.tsx",
        ),
    )
    for test_path, source_path in cases:
        assert matches_source(test_path, {source_path}, []) is True


def test_matches_source_accepts_tests_for_utility_scripts() -> None:
    assert matches_source(
        "tests/test_aggregate_go_benchmarks.py",
        set(),
        [],
        {"scripts", "scripts.quality", "scripts.quality.aggregate_go_benchmarks"},
        reference_paths={"scripts/quality/aggregate_go_benchmarks.py"},
    )


def test_matches_source_accepts_authored_test_support_module() -> None:
    assert (
        matches_source(
            "tests/test_duration_sharding_contract.py",
            set(),
            [],
            {"tests", "tests.conftest"},
            reference_paths={"tests/conftest.py"},
        )
        is True
    )

    # Importing another test module is not an ownership relationship.
    assert (
        matches_source(
            "tests/test_duration_sharding_contract.py",
            set(),
            [],
            {"tests", "tests.test_other"},
            reference_paths={"tests/conftest.py"},
        )
        is False
    )


def test_matches_source_accepts_named_workflow_contract_tests() -> None:
    workflow_paths = {".github/workflows/dast.yml"}

    assert (
        matches_source(
            "tests/test_dast_workflow_contract.py",
            set(),
            [],
            workflow_paths=workflow_paths,
        )
        is True
    )
    assert (
        matches_source("tests/test_dast.py", set(), [], workflow_paths=workflow_paths)
        is False
    )


def test_matches_source_normalizes_hyphenated_workflow_contract_names() -> None:
    assert (
        matches_source(
            "tests/test_quality_promotion_check_workflow_contract.py",
            set(),
            [],
            workflow_paths={".github/workflows/quality-promotion-check.yml"},
        )
        is True
    )


def test_python_contract_paths_match_inventory_utilities(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        """
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "alembic" / "versions"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
HOOK = Path(".husky/pre-commit")
""",
    )

    references = find_python_repository_references(contract_test)

    assert references == {
        ".github/workflows/deploy.yml",
        ".husky/pre-commit",
        "alembic/versions",
    }
    assert matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=references,
        reference_paths={
            ".github/workflows/deploy.yml",
            ".husky/pre-commit",
            "alembic/versions/202608250001_expand_email_otp_mfa.py",
        },
    )


def test_python_contract_visits_keyword_only_defaults_with_missing_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        """
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def helper(*, required, target=ROOT / "quality" / "quality-contract.json"):
    return required, target
""",
    )

    assert find_python_repository_references(contract_test) == {
        "quality/quality-contract.json"
    }


def test_python_contract_path_match_requires_a_real_inventory_target(
    tmp_path: Path,
) -> None:
    contract_test = tmp_path / "test_contract.py"
    contract_test.write_text(
        'from pathlib import Path\nROOT = Path(__file__).parents[1]\nMISSING = ROOT / "missing"\n',
        encoding="utf-8",
    )

    assert not matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=find_python_repository_references(contract_test),
        reference_paths={"quality/quality-contract.json"},
    )


def test_python_contract_path_does_not_fall_back_to_existing_parent(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\nTARGET = ROOT / "quality" / "missing.json"\n',
    )

    assert not matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=find_python_repository_references(contract_test),
        reference_paths={"quality/quality-contract.json"},
    )


def test_python_contract_rejects_root_name_with_non_repository_assignment(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nROOT = Path("/tmp/not-repo")\nTARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert not matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=find_python_repository_references(contract_test),
        reference_paths={"quality/quality-contract.json"},
    )


def test_python_contract_rejects_non_root_file_expression(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nTARGET = Path(__file__).name / "quality" / "quality-contract.json"\n',
    )

    assert not matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=find_python_repository_references(contract_test),
        reference_paths={"quality/quality-contract.json"},
    )


def test_python_contract_keeps_dynamic_repository_directory_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\nTARGET = ROOT / "alembic" / "versions" / migration_name\n',
    )

    assert matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=find_python_repository_references(contract_test),
        reference_paths={"alembic/versions/202608250001_expand.py"},
    )


def test_python_contract_rejects_canonical_root_rebound_later(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\nROOT = Path("/tmp/not-repo")\nTARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_rejects_dotted_import_rebinding_canonical_root(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "import ROOT.submodule\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_rejects_wildcard_import_after_canonical_root(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "from arbitrary_module import *\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


@pytest.mark.parametrize(
    "class_binding",
    [
        "ROOT = fallback",
        "del ROOT",
        "import arbitrary_module as ROOT",
        "def ROOT():\n        pass",
        "class ROOT:\n        pass",
        "for ROOT in values:\n        pass",
        "with manager() as ROOT:\n        pass",
        "try:\n        raise RuntimeError\n    except RuntimeError as ROOT:\n        pass",
        "match subject:\n        case ROOT:\n            pass",
        "value = (ROOT := fallback)",
        "def subject(value=(ROOT := fallback)):\n        pass",
    ],
)
def test_python_contract_rejects_class_code_global_root_bindings(
    tmp_path: Path, monkeypatch, class_binding: str
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "class Container:\n"
        "    global ROOT\n"
        f"    {class_binding}\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )
    compile(contract_test.read_text(encoding="utf-8"), str(contract_test), "exec")

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_keeps_class_global_out_of_nested_function_scope(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "class Container:\n"
        "    global ROOT\n"
        "    def method():\n"
        "        ROOT = fallback\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == {
        "quality/quality-contract.json"
    }


def test_python_contract_rejects_nested_class_own_global_binding(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "class Outer:\n"
        "    class Inner:\n"
        "        global ROOT\n"
        "        ROOT = fallback\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_annotation_only_does_not_rebind_root(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "ROOT: Path\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == {
        "quality/quality-contract.json"
    }


def test_python_contract_annotation_with_value_rebinds_root(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "ROOT: Path = fallback\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


@pytest.mark.parametrize(
    "namespace_mutation",
    [
        "exec(source)",
        "eval(source)",
        'globals()["ROOT"] = fallback',
        'del globals()["ROOT"]',
        'globals().update({"ROOT": fallback})',
        'globals().__ior__({"ROOT": fallback})',
        'globals().__init__({"ROOT": fallback})',
        'dict.__setitem__(globals(), "ROOT", fallback)',
        'locals().setdefault("ROOT", fallback)',
        'vars().__setitem__("ROOT", fallback)',
        'module.__dict__["ROOT"] = fallback',
        'module.__dict__.update({"ROOT": fallback})',
    ],
)
def test_python_contract_rejects_direct_module_namespace_mutation(
    tmp_path: Path, monkeypatch, namespace_mutation: str
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        f"{namespace_mutation}\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_rejects_globals_mutation_in_executed_class_body(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "class Container:\n"
        '    globals()["ROOT"] = fallback\n'
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_does_not_descend_into_unexecuted_function_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "def mutate_later():\n"
        '    globals()["ROOT"] = fallback\n'
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == {
        "quality/quality-contract.json"
    }


@pytest.mark.parametrize(
    "module_binding",
    [
        "del ROOT",
        "try:\n    raise RuntimeError\nexcept RuntimeError as ROOT:\n    pass",
        "match subject:\n    case ROOT:\n        pass",
        "match subject:\n    case [*ROOT]:\n        pass",
        'match subject:\n    case {"key": _, **ROOT}:\n        pass',
    ],
)
def test_python_contract_rejects_string_backed_module_root_rebindings(
    tmp_path: Path, monkeypatch, module_binding: str
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        f"{module_binding}\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


@pytest.mark.parametrize(
    "module_evaluated_binding",
    [
        "def subject(value=(ROOT := fallback)):\n    pass",
        "async def subject(value=(ROOT := fallback)):\n    pass",
        "@(ROOT := decorator)\ndef subject():\n    pass",
        "subject = lambda value=(ROOT := fallback): value",
        "subject = [item for item in values if (ROOT := item)]",
        "class Subject((ROOT := Base)):\n    pass",
        "class Subject(metaclass=(ROOT := Meta)):\n    pass",
    ],
)
def test_python_contract_rejects_bindings_in_module_evaluated_child_expressions(
    tmp_path: Path, monkeypatch, module_evaluated_binding: str
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        f"{module_evaluated_binding}\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


@pytest.mark.parametrize(
    "child_scope_binding",
    [
        "def subject():\n    ROOT = fallback",
        "class Subject:\n    ROOT = fallback",
        "subject = lambda: (ROOT := fallback)",
        "items = [ROOT for ROOT in values]",
    ],
)
def test_python_contract_keeps_bindings_confined_to_child_scope(
    tmp_path: Path, monkeypatch, child_scope_binding: str
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        f"{child_scope_binding}\n"
        'TARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == {
        "quality/quality-contract.json"
    }


def test_python_contract_rejects_nested_fake_root_binding(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nROOT = Path("/tmp/not-repo")\ndef fake():\n    ROOT = Path(__file__).resolve().parents[1]\n    return ROOT / "quality" / "quality-contract.json"\nTARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_rejects_root_reference_before_binding(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nTARGET = ROOT / "quality" / "quality-contract.json"\nROOT = Path(__file__).resolve().parents[1]\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_rejects_wrong_repository_parent_index(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nROOT = Path(__file__).resolve().parents[0]\nTARGET = ROOT / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_python_contract_rejects_static_segments_after_dynamic_segment(
    tmp_path: Path, monkeypatch
) -> None:
    contract_test = _write_repository_contract(
        tmp_path,
        monkeypatch,
        'from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\nTARGET = ROOT / dynamic / "quality" / "quality-contract.json"\n',
    )

    assert find_python_repository_references(contract_test) == set()


def test_static_skip_condition_is_not_a_dynamic_skip(tmp_path: Path) -> None:
    test_file = tmp_path / "test_platform.py"
    test_file.write_text(
        '@pytest.mark.skipif(not SYMLINKS_SUPPORTED, reason="requires symlinks")\n'
        "def test_symlink_contract(): ...\n",
        encoding="utf-8",
    )
    errors: list[str] = []

    check_anti_patterns(test_file, errors, [], [])

    assert errors == []


@pytest.mark.parametrize(
    ("contract_name", "support_path"),
    [
        ("test_conftest_jsonb_compiler.py", "tests/conftest.py"),
        (
            "test_service_fixture_annotations.py",
            "tests/fixtures/services/service_fixtures.py",
        ),
    ],
)
def test_fixture_contract_declares_its_actual_repository_support_target(
    contract_name: str, support_path: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    contract_path = root / "tests" / contract_name
    references = find_python_repository_references(contract_path)

    assert (root / support_path).is_file()
    assert classify_file(support_path, []) != "test"
    assert support_path in references
    assert matches_source(
        f"tests/{contract_name}",
        set(),
        [],
        repository_references=references,
        reference_paths={support_path},
    )


@pytest.fixture
def generated_quality_inventory(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    for relative_path, content in {
        "app/sample.py": "VALUE = 1\n",
        "tests/test_sample.py": "def test_sample():\n    assert True\n",
        "frontend/src/routeTree.gen.ts": "export {}\n",
        "README.md": "Inventory fixture\n",
    }.items():
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(inventory, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(
            {
                "teams": {"app/": "@owner", "tests/": "@owner"},
                "generated_patterns": ["**/routeTree.gen.ts"],
            }
        ),
        encoding="utf-8",
    )
    inventory_path = tmp_path / "inventory.json"
    assert (
        inventory.main(
            ["--mapping", str(mapping_path), "--output", str(inventory_path)]
        )
        == 0
    )
    return repository, inventory_path, mapping_path


def test_checker_accepts_generated_inventory(
    generated_quality_inventory, capsys
) -> None:
    _, inventory_path, mapping_path = generated_quality_inventory
    manifest = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert {record["classification"] for record in manifest["files"]} == {
        "source",
        "test",
        "generated",
        "utility",
    }
    assert (
        checker.main(
            ["--inventory", str(inventory_path), "--mapping", str(mapping_path)]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "Quality inventory validation passed" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    ("manifest", "error"),
    [
        (None, "manifest must be an object"),
        ([], "manifest must be an object"),
        ({}, "files must be a non-empty list"),
        (
            {"command": "generate_test_inventory.py", "returncode": 0},
            "files must be a non-empty list",
        ),
        ({"files": []}, "files must be a non-empty list"),
        ({"files": None}, "files must be a non-empty list"),
        ({"files": {}}, "files must be a non-empty list"),
        ({"files": "app/sample.py"}, "files must be a non-empty list"),
        ({"files": [None]}, "files[0] must be an object"),
        ({"files": ["app/sample.py"]}, "files[0] must be an object"),
        ({"files": [[]]}, "files[0] must be an object"),
        ({"files": [{}]}, "files[0].path"),
    ],
)
def test_checker_rejects_invalid_inventory_structure(
    generated_quality_inventory, capsys, manifest: object, error: str
) -> None:
    _, inventory_path, mapping_path = generated_quality_inventory
    inventory_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert (
        checker.main(
            ["--inventory", str(inventory_path), "--mapping", str(mapping_path)]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "ERROR: invalid inventory manifest:" in captured.err
    assert error in captured.err
    assert "validation passed" not in captured.out


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", None),
        ("path", []),
        ("path", 1),
        ("path", ""),
        ("path", "."),
        ("path", "/outside.py"),
        ("path", "../outside.py"),
        ("path", "app/../../outside.py"),
        ("path", "app\\sample.py"),
        ("classification", None),
        ("classification", []),
        ("classification", 1),
        ("classification", ""),
        ("classification", "soruce"),
        ("owner", []),
        ("owner", 1),
        ("owner", ""),
        ("owner", " "),
    ],
)
def test_checker_rejects_invalid_generated_record_fields(
    generated_quality_inventory, capsys, field: str, value: object
) -> None:
    _, inventory_path, mapping_path = generated_quality_inventory
    manifest = json.loads(inventory_path.read_text(encoding="utf-8"))
    record_index = next(
        index
        for index, record in enumerate(manifest["files"])
        if record["path"] == "app/sample.py"
    )
    manifest["files"][record_index][field] = value
    inventory_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert (
        checker.main(
            ["--inventory", str(inventory_path), "--mapping", str(mapping_path)]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert (
        f"ERROR: invalid inventory manifest: files[{record_index}].{field}"
        in captured.err
    )
    assert "validation passed" not in captured.out


@pytest.mark.parametrize("field", ["path", "classification", "owner"])
def test_checker_rejects_missing_generated_record_fields(
    generated_quality_inventory, capsys, field: str
) -> None:
    _, inventory_path, mapping_path = generated_quality_inventory
    manifest = json.loads(inventory_path.read_text(encoding="utf-8"))
    del manifest["files"][0][field]
    inventory_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert (
        checker.main(
            ["--inventory", str(inventory_path), "--mapping", str(mapping_path)]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert f"ERROR: invalid inventory manifest: files[0].{field}" in captured.err
    assert "validation passed" not in captured.out


@pytest.mark.parametrize("classification", ["source", "test"])
def test_checker_keeps_null_owner_as_quality_violation(
    generated_quality_inventory, capsys, classification: str
) -> None:
    _, inventory_path, mapping_path = generated_quality_inventory
    manifest = json.loads(inventory_path.read_text(encoding="utf-8"))
    record = next(
        record
        for record in manifest["files"]
        if record["classification"] == classification
    )
    record["owner"] = None
    inventory_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert (
        checker.main(
            ["--inventory", str(inventory_path), "--mapping", str(mapping_path)]
        )
        == 1
    )
    assert f"unowned {classification} file path" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "error", "allowlist"),
    [
        ("import time\ntime.sleep(1)\n", "Python test sleep", "allowed_sleeps"),
        (
            "import pytest\npytest.skip('unavailable')\n",
            "Python dynamic skip",
            "allowed_dynamic_skips",
        ),
        (
            "def test_sample():\n    assert True\n",
            "orphaned test file",
            "allowed_orphans",
        ),
    ],
)
def test_checker_preserves_violations_and_explicit_allowlists(
    generated_quality_inventory, capsys, content: str, error: str, allowlist: str
) -> None:
    repository, inventory_path, mapping_path = generated_quality_inventory
    test_path = repository / "tests/test_sample.py"
    test_path.write_text(content, encoding="utf-8")
    if allowlist == "allowed_orphans":
        (repository / "app/sample.py").unlink()
        assert (
            inventory.main(
                ["--mapping", str(mapping_path), "--output", str(inventory_path)]
            )
            == 0
        )
    arguments = ["--inventory", str(inventory_path), "--mapping", str(mapping_path)]
    assert checker.main(arguments) == 1
    assert error in capsys.readouterr().err

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping[allowlist] = ["tests/test_sample.py"]
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    assert checker.main(arguments) == 0
    assert capsys.readouterr().err == ""


def test_mjs_is_test_but_spec_classification_remains_out_of_this_tranche() -> None:
    assert (
        inventory.classify_file("tools/npm-cli-shim/test/npm-cli.test.mjs", [])
        == "test"
    )
    assert (
        inventory.classify_file("frontend/tests/e2e/example.spec.ts", []) == "utility"
    )
    assert (
        inventory.resolve_owner(
            "tools/npm-cli-shim/test/npm-cli.test.mjs",
            {"tools/npm-cli-shim/test/": "@egorribun"},
        )
        == "@egorribun"
    )


def test_javascript_reference_scanner_accepts_literal_repository_files_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "tests" / "contract.test.mjs"
    test_file.parent.mkdir(parents=True)
    (repository / "app").mkdir()
    (repository / "frontend" / "src").mkdir(parents=True)
    (repository / "frontend" / "tests" / "e2e").mkdir()
    (repository / "outside.js").write_text("outside\n", encoding="utf-8")
    (repository / "app" / "source.js").write_text("export {}\n", encoding="utf-8")
    (repository / "frontend" / "src" / "view.tsx").write_text(
        "export {}\n", encoding="utf-8"
    )
    (repository / "frontend" / "src" / "real.js").write_text(
        "export {}\n", encoding="utf-8"
    )
    (repository / "frontend" / "src" / "regex-spoof.js").write_text(
        "export {}\n", encoding="utf-8"
    )
    (repository / "frontend" / "tests" / "regex-after-control.js").write_text(
        "export {}\n", encoding="utf-8"
    )
    (repository / "frontend" / "tests" / "e2e" / "live.spec.ts").write_text(
        "test()\n", encoding="utf-8"
    )
    test_file.write_text(
        'import { value } from "../../app/source.js";\n'
        'const live = await readFile(new URL("./e2e/live.spec.ts", import.meta.url), "utf8");\n'
        'const view = await readFile(new URL("../src/view.tsx", import.meta.url), "utf8");\n'
        'const dynamic = await readFile(new URL(target, import.meta.url), "utf8");\n'
        'const outside = await readFile(new URL("../../../../outside.js", import.meta.url), "utf8");\n'
        "const documentation = \"import '../src/real.js'\";\n"
        r"const pattern = /import '\.\.\/src\/regex-spoof\.js'/;" + "\n"
        'if (false) /import "regex-after-control.js"/.test("");\n'
        '// import "../../app/comment-only.js";\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    references = checker.find_javascript_repository_references(test_file)
    assert references == {
        "app/source.js",
        "frontend/src/view.tsx",
        "frontend/tests/e2e/live.spec.ts",
    }
    assert not checker.matches_source(
        "frontend/scripts/unrelated.test.mjs",
        set(),
        [],
        repository_references=references,
        reference_paths={"frontend/tests/regex-after-control.js"},
    )


def test_javascript_read_helper_tracks_import_meta_and_static_root_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "tests" / "e2e-live" / "contract.test.mjs"
    test_file.parent.mkdir(parents=True)
    for relative in (
        "frontend/tests/e2e-live/fixtures.ts",
        "frontend/src/pages/Schedule.tsx",
        "app/services/auth_service.py",
    ):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("source\n", encoding="utf-8")
    test_file.write_text(
        'const rootUrl = new URL("../../../", import.meta.url);\n'
        'const read = (path) => readFile(new URL(path, import.meta.url), "utf8");\n'
        'const readFromRoot = (path) => readFile(new URL(path, rootUrl), "utf8");\n'
        'const fixtures = await read("./fixtures.ts");\n'
        'const page = await read("../../src/pages/Schedule.tsx");\n'
        'const service = await readFromRoot("app/services/auth_service.py");\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.find_javascript_repository_references(test_file) == {
        "frontend/tests/e2e-live/fixtures.ts",
        "frontend/src/pages/Schedule.tsx",
        "app/services/auth_service.py",
    }


def test_release_contract_tracks_literal_files_under_statically_derived_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "scripts" / "tests" / "release-config.test.mjs"
    test_file.parent.mkdir(parents=True)
    for relative in (
        ".releaserc.json",
        "package.json",
        "package-lock.json",
        ".github/workflows/release.yml",
    ):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    test_file.write_text(
        'const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..",);\n'
        'function readJson(relativePath) { return JSON.parse(readFileSync(path.join(repositoryRoot, relativePath), "utf8")); }\n'
        'const releaseConfig = readJson(".releaserc.json");\n'
        'const packageDocument = readJson("package.json");\n'
        'const lockDocument = readJson("package-lock.json");\n'
        'const workflow = readFileSync(path.join(repositoryRoot, ".github", "workflows", "release.yml"), "utf8");\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.find_javascript_repository_references(test_file) == {
        ".releaserc.json",
        "package.json",
        "package-lock.json",
        ".github/workflows/release.yml",
    }


def test_shallow_authored_source_scan_does_not_match_nested_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "scripts" / "ui-barrel-boundary.test.mjs"
    test_file.parent.mkdir(parents=True)
    source = repository / "frontend" / "src" / "components" / "Button.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export const Button = 1\n", encoding="utf-8")
    e2e_test = repository / "frontend" / "tests" / "e2e" / "button.spec.ts"
    e2e_test.parent.mkdir(parents=True)
    e2e_test.write_text("test()\n", encoding="utf-8")
    test_file.write_text(
        'const frontendRoot = path.resolve(import.meta.dirname, "..");\n'
        'const scanRoots = ["src", "tests"];\n'
        'const authoredExtensions = new Set([".ts", ".tsx"]);\n'
        "const ignoredDirectories = new Set([]);\n"
        "function collectAuthoredFiles(root) { return fs.readdirSync(root).flatMap((entry) => [entry]); }\n"
        "for (const root of scanRoots) {\n"
        "  const absoluteRoot = path.join(frontendRoot, root);\n"
        '  for (const filePath of collectAuthoredFiles(absoluteRoot)) { const source = fs.readFileSync(filePath, "utf8"); }\n'
        "}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    references = checker.find_javascript_repository_references(test_file)
    assert references == set()
    assert not checker._references_inventory_target(
        references, {"frontend/src/components/Button.tsx"}
    )
    assert not checker.matches_source(
        "frontend/scripts/ui-barrel-boundary.test.mjs",
        {"frontend/src/components/Button.tsx"},
        [],
        repository_references=references,
        reference_paths={"frontend/src/components/Button.tsx"},
    )


def test_actual_recursive_authored_source_scan_matches_exact_nested_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "scripts" / "ui-barrel-boundary.test.mjs"
    test_file.parent.mkdir(parents=True)
    source = repository / "frontend" / "src" / "components" / "Button.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export const Button = 1\n", encoding="utf-8")
    test_file.write_text(
        'const frontendRoot = path.resolve(import.meta.dirname, "..");\n'
        'const scanRoots = ["src"];\n'
        'const authoredExtensions = new Set([".ts", ".tsx"]);\n'
        'const ignoredDirectories = new Set(["vendor"]);\n'
        "function collectAuthoredFiles(root) {\n"
        "  const files = [];\n"
        "  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {\n"
        "    if (entry.isDirectory()) {\n"
        "      if (!ignoredDirectories.has(entry.name)) {\n"
        "        files.push(...collectAuthoredFiles(path.join(root, entry.name)));\n"
        "      }\n"
        "      continue;\n"
        "    }\n"
        "    if (authoredExtensions.has(path.extname(entry.name))) {\n"
        "      files.push(path.join(root, entry.name));\n"
        "    }\n"
        "  }\n"
        "  return files;\n"
        "}\n"
        "for (const root of scanRoots) {\n"
        "  const absoluteRoot = path.join(frontendRoot, root);\n"
        '  for (const filePath of collectAuthoredFiles(absoluteRoot)) { const source = fs.readFileSync(filePath, "utf8"); }\n'
        "}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    references = checker.find_javascript_repository_references(test_file)
    assert references == {"frontend/src/components/Button.tsx"}
    assert checker.matches_source(
        "frontend/scripts/ui-barrel-boundary.test.mjs",
        {"frontend/src/components/Button.tsx"},
        [],
        repository_references=references,
        reference_paths={"frontend/src/components/Button.tsx"},
    )


def test_recursive_authored_source_scan_rejects_external_file_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "scripts" / "ui-barrel-boundary.test.mjs"
    test_file.parent.mkdir(parents=True)
    source = repository / "frontend" / "src" / "components" / "Button.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export const Button = 1\n", encoding="utf-8")
    internal_link = source.parent / "ButtonAlias.tsx"
    os.symlink(source, internal_link)

    external_target = tmp_path / "external" / "PrivateComponent.tsx"
    external_target.parent.mkdir()
    external_target.write_text("export const PrivateComponent = 1\n", encoding="utf-8")
    external_link = source.parent / "ExternalComponent.tsx"
    os.symlink(external_target, external_link)

    test_file.write_text(
        'const frontendRoot = path.resolve(import.meta.dirname, "..");\n'
        'const scanRoots = ["src"];\n'
        'const authoredExtensions = new Set([".ts", ".tsx"]);\n'
        "const ignoredDirectories = new Set([]);\n"
        "function collectAuthoredFiles(root) {\n"
        "  const files = [];\n"
        "  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {\n"
        "    if (entry.isDirectory()) {\n"
        "      if (!ignoredDirectories.has(entry.name)) {\n"
        "        files.push(...collectAuthoredFiles(path.join(root, entry.name)));\n"
        "      }\n"
        "      continue;\n"
        "    }\n"
        "    if (authoredExtensions.has(path.extname(entry.name))) {\n"
        "      files.push(path.join(root, entry.name));\n"
        "    }\n"
        "  }\n"
        "  return files;\n"
        "}\n"
        "for (const root of scanRoots) {\n"
        "  const absoluteRoot = path.join(frontendRoot, root);\n"
        '  for (const filePath of collectAuthoredFiles(absoluteRoot)) { const source = fs.readFileSync(filePath, "utf8"); }\n'
        "}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr(inventory, "REPOSITORY_ROOT", repository)

    references = checker.find_javascript_repository_references(test_file)
    assert references == {
        "frontend/src/components/Button.tsx",
        "frontend/src/components/ButtonAlias.tsx",
    }

    records = inventory.scan_repository({"teams": {"frontend/": "@frontend"}})
    external_record = next(
        item
        for item in records
        if item["path"] == "frontend/src/components/ExternalComponent.tsx"
    )
    assert external_record["classification"] == "source"
    assert not checker.matches_source(
        "frontend/scripts/unrelated.test.mjs",
        set(),
        [],
        repository_references=references,
        reference_paths={external_record["path"]},
    )


def test_direct_javascript_url_uses_its_statically_resolved_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "tests" / "e2e" / "direct-url.test.mjs"
    test_file.parent.mkdir(parents=True)
    target = repository / "app" / "services" / "auth_service.py"
    target.parent.mkdir(parents=True)
    target.write_text("source\n", encoding="utf-8")
    decoy = (
        repository
        / "frontend"
        / "tests"
        / "e2e"
        / "app"
        / "services"
        / "auth_service.py"
    )
    decoy.parent.mkdir(parents=True)
    decoy.write_text("unrelated decoy\n", encoding="utf-8")
    test_file.write_text(
        'const rootUrl = new URL("../../../", import.meta.url);\n'
        'const service = await readFile(new URL("app/services/auth_service.py", rootUrl), "utf8");\n'
        'const filesystemRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../");\n'
        'const decoyRead = await readFile(new URL("frontend/tests/e2e/app/services/auth_service.py", filesystemRoot), "utf8");\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    references = checker.find_javascript_repository_references(test_file)
    assert references == {"app/services/auth_service.py"}
    assert not checker.matches_source(
        "frontend/scripts/unrelated.test.mjs",
        set(),
        [],
        repository_references=references,
        reference_paths={"frontend/tests/e2e/app/services/auth_service.py"},
    )


def test_static_file_url_and_path_join_dependencies_are_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = (
        repository / "frontend" / "scripts" / "validate-css-token-closure.test.mjs"
    )
    test_file.parent.mkdir(parents=True)
    (repository / "frontend" / "src").mkdir(parents=True)
    (repository / "frontend" / "src" / "app.tsx").write_text(
        "export {}\n", encoding="utf-8"
    )
    (test_file.parent / "validate-css-token-closure.mjs").write_text(
        "export {}\n", encoding="utf-8"
    )
    test_file.write_text(
        "const __dirname = path.dirname(fileURLToPath(import.meta.url));\n"
        'const validatorPath = path.join(__dirname, "validate-css-token-closure.mjs");\n'
        'function runValidator(root) { return spawnSync(process.execPath, [validatorPath, "--root", root]); }\n'
        'test("source graph is closed", () => runValidator(path.join(__dirname, "../src")));\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.find_javascript_repository_references(test_file) == {
        "frontend/scripts/validate-css-token-closure.mjs",
        "frontend/src",
    }


def test_contract_test_requires_exact_playwright_spec_and_cleanup_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = (
        repository
        / "frontend"
        / "scripts"
        / "messenger-reconnect-live-contract.test.mjs"
    )
    target = (
        repository
        / "frontend"
        / "tests"
        / "e2e-live"
        / "messenger-reconnect.live.spec.ts"
    )
    cleanup_helper = (
        repository
        / "frontend"
        / "tests"
        / "e2e-live"
        / "messenger-reconnect-cleanup.mjs"
    )
    target.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("test()\n", encoding="utf-8")
    cleanup_helper.write_text(
        "export async function cleanupMessengerReconnect() {}\n", encoding="utf-8"
    )
    test_file.write_text(
        'import "../tests/e2e-live/messenger-reconnect-cleanup.mjs";\n'
        "const spec = await readFile(\n"
        '  new URL("../tests/e2e-live/messenger-reconnect.live.spec.ts", import.meta.url),\n'
        '  "utf8"\n'
        ")\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    references = checker.find_javascript_repository_references(test_file)
    exact_spec = "frontend/tests/e2e-live/messenger-reconnect.live.spec.ts"
    exact_cleanup_helper = "frontend/tests/e2e-live/messenger-reconnect-cleanup.mjs"

    assert references == {exact_spec, exact_cleanup_helper}
    assert checker.matches_source(
        test_file.relative_to(repository).as_posix(),
        set(),
        [],
        repository_references=references,
        reference_paths={exact_spec, exact_cleanup_helper},
        contract_test_paths={exact_spec, exact_cleanup_helper},
    )
    assert not checker.matches_source(
        "frontend/scripts/unrelated.test.mjs",
        set(),
        [],
        repository_references=references,
        reference_paths={exact_spec, exact_cleanup_helper},
        contract_test_paths={exact_spec, exact_cleanup_helper},
    )
    assert not checker.matches_source(
        test_file.relative_to(repository).as_posix(),
        set(),
        [],
        repository_references=references,
        reference_paths=set(),
        contract_test_paths={"frontend/tests/e2e-live/other.live.spec.ts"},
    )


def test_checker_requires_owned_mjs_tests_and_keeps_orphan_and_skip_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = tmp_path / "repo"
    shim = repository / "tools" / "npm-cli-shim"
    test_file = shim / "test" / "npm-cli.test.mjs"
    source_file = shim / "bin" / "npm-cli.js"
    source_file.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    source_file.write_text("export const shim = true;\n", encoding="utf-8")
    test_file.write_text(
        'import assert from "node:assert/strict";\n'
        'import test from "node:test";\n'
        'import "../bin/npm-cli.js";\n'
        'test("shim exists", () => assert.ok(true));\n',
        encoding="utf-8",
    )
    mapping = {
        "teams": {"tools/npm-cli-shim/test/": "@egorribun"},
        "tier0_rules": [],
        "generated_patterns": [],
        "allowed_sleeps": [],
        "allowed_dynamic_skips": [],
        "allowed_orphans": [],
    }
    mapping_file = tmp_path / "ownership-mapping.json"
    mapping_file.write_text(json.dumps(mapping), encoding="utf-8")
    inventory_file = tmp_path / "inventory.json"
    monkeypatch.setattr(inventory, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    def write_inventory() -> list[dict[str, object]]:
        records = inventory.scan_repository(mapping)
        inventory_file.write_text(
            json.dumps({"version": 1, "files": records}), encoding="utf-8"
        )
        return records

    records = write_inventory()
    record = next(
        item
        for item in records
        if item["path"] == "tools/npm-cli-shim/test/npm-cli.test.mjs"
    )
    assert record["classification"] == "test"
    assert record["owner"] == "@egorribun"
    assert (
        checker.main(
            ["--inventory", str(inventory_file), "--mapping", str(mapping_file)]
        )
        == 0
    )
    assert capsys.readouterr().err == ""

    test_file.write_text(
        'import test from "node:test"; test("orphan", () => {});\n', encoding="utf-8"
    )
    write_inventory()
    assert (
        checker.main(
            ["--inventory", str(inventory_file), "--mapping", str(mapping_file)]
        )
        == 1
    )
    assert (
        "tools/npm-cli-shim/test/npm-cli.test.mjs: orphaned test file"
        in capsys.readouterr().err
    )

    test_file.write_text(
        'import "../bin/npm-cli.js";\n'
        'import test from "node:test"; test.'
        'skip("skipped", () => {});\n',
        encoding="utf-8",
    )
    write_inventory()
    assert (
        checker.main(
            ["--inventory", str(inventory_file), "--mapping", str(mapping_file)]
        )
        == 1
    )
    assert "JS/TS dynamic skip (test.skip) found" in capsys.readouterr().err


def _write_javascript_fixture(
    tmp_path: Path, source: str, targets: tuple[str, ...] = ()
) -> tuple[Path, Path]:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "tests" / "e2e" / "scanner.test.mjs"
    test_file.parent.mkdir(parents=True)
    for relative in targets:
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("source\n", encoding="utf-8")
    test_file.write_text(source, encoding="utf-8")
    return repository, test_file


def test_javascript_masker_only_exposes_real_code_and_fails_closed_on_malformed_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, test_file = _write_javascript_fixture(
        tmp_path,
        'import "./real.js";\n'
        "const message = \"import './string.js'\";\n"
        "const escaped = 'quote\\' and import \"./escaped.js\"';\n"
        'const template = `import "./template.js"`;\n'
        r'const pattern = /import "\.\/regex.js"/giu;' + "\n"
        'if (false) /import "regex-after-control.js"/.test("");\n'
        "call() / 2;\n"
        ') /import "regex-after-unmatched-close.js"/;\n'
        '// import "./line-comment.js"',
        (
            "frontend/tests/e2e/real.js",
            "frontend/tests/e2e/string.js",
            "frontend/tests/e2e/escaped.js",
            "frontend/tests/e2e/template.js",
            "frontend/tests/e2e/regex.js",
            "frontend/tests/e2e/regex-at-start.js",
            "frontend/tests/e2e/regex-after-control.js",
            "frontend/tests/e2e/regex-after-unmatched-close.js",
            "frontend/tests/e2e/line-comment.js",
        ),
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    assert checker.find_javascript_repository_references(test_file) == {
        "frontend/tests/e2e/real.js"
    }

    test_file.write_text('/import "regex-at-start.js"/;\n', encoding="utf-8")
    assert checker.find_javascript_repository_references(test_file) == set()

    malformed_files = (
        'const broken = "unterminated\nimport "./after-string.js";\n',
        'const broken = \'unterminated\nimport "./after-string.js";\n',
        'const broken = "',
        'const pattern = /import "after-regex.js"\nimport "./after-regex-too.js";\n',
        "const pattern = /",
        '/* import "./after-comment.js";\n',
        'import "./nul.js";\0',
    )
    for source in malformed_files:
        test_file.write_text(source, encoding="utf-8")
        assert checker.find_javascript_repository_references(test_file) == set()
    assert (
        checker.find_javascript_repository_references(repository / "missing.mjs")
        == set()
    )


def test_javascript_module_paths_resolve_files_and_reject_unsupported_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, test_file = _write_javascript_fixture(
        tmp_path,
        'import "./real.js";\n'
        'import "./without-extension";\n'
        'import "./with-index";\n'
        'require("./required.js");\n'
        'import("./dynamic.js");\n'
        'module.import("./member-import.js");\n'
        'module.require("./member-require.js");\n'
        'module . import("./spaced-member-import.js");\n'
        'module\n.\nrequire("./newline-member-require.js");\n'
        "const ignored = import(target);\n"
        'import ""; import "/rooted.js"; import "\\\\rooted.js";\n'
        'import "../../../../../outside.js"; import "./missing.js";\n'
        'import "./real.js?raw"; import "./real.js#fragment";\n'
        'import "https://example.invalid/module.js";\n'
        "const docs = \"import './string-only.js'\";\n",
        (
            "frontend/tests/e2e/real.js",
            "frontend/tests/e2e/without-extension.ts",
            "frontend/tests/e2e/with-index/index.js",
            "frontend/tests/e2e/required.js",
            "frontend/tests/e2e/dynamic.js",
            "frontend/tests/e2e/member-import.js",
            "frontend/tests/e2e/member-require.js",
            "frontend/tests/e2e/spaced-member-import.js",
            "frontend/tests/e2e/newline-member-require.js",
            "frontend/tests/e2e/string-only.js",
        ),
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.find_javascript_repository_references(test_file) == {
        "frontend/tests/e2e/real.js",
        "frontend/tests/e2e/without-extension.ts",
        "frontend/tests/e2e/with-index/index.js",
        "frontend/tests/e2e/required.js",
        "frontend/tests/e2e/dynamic.js",
    }

    outside_target = tmp_path / "outside.js"
    outside_target.write_text("outside\n", encoding="utf-8")
    external_link = repository / "frontend" / "tests" / "e2e" / "external.js"
    os.symlink(outside_target, external_link)
    # Extension expansion must resolve the symlink target before accepting it.
    test_file.write_text('import "./external";\n', encoding="utf-8")
    assert checker.find_javascript_repository_references(test_file) == set()


def test_javascript_url_readers_require_static_contained_bases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, test_file = _write_javascript_fixture(
        tmp_path,
        'const rootUrl = new URL("../../../", import.meta.url);\n'
        'const fileUrl = new URL("./base.js", import.meta.url);\n'
        "const templateBase = new URL(`../../../`, import.meta.url);\n"
        'const invalidBase = new URL("/rooted/", import.meta.url);\n'
        'const unknownUrl = new URL("../../../", computedBase);\n'
        'const outsideUrl = new URL("../../../../", import.meta.url);\n'
        'const outsideFrontendRoot = path.resolve(import.meta.dirname, "../../../../");\n'
        "const dynamicFrontendRoot = path.resolve(import.meta.dirname, `../../../`);\n"
        'const read = (path) => readFile(new URL(path, rootUrl), "utf8");\n'
        'const readUnknown = (path) => readFile(new URL(path, computedBase), "utf8");\n'
        'const valid = await read("app/service.py");\n'
        'const outsideRead = await read("../../../../outside.js");\n'
        'const invalidHelperRead = await readUnknown("./base.js");\n'
        'const decoy = await readFile(new URL("app/service.py", filesystemRoot), "utf8");\n'
        'const fileBaseRead = await readFile(new URL("base.js", fileUrl), "utf8");\n'
        'const dynamicBaseRead = await readFile(new URL("base.js", unknownUrl), "utf8");\n'
        'const outsideBaseRead = await readFile(new URL("secret.js", outsideUrl), "utf8");\n'
        "const templateRead = await read(`app/service.py`);\n",
        (
            "app/service.py",
            "frontend/tests/e2e/base.js",
            "frontend/tests/e2e/secret.js",
            "frontend/tests/e2e/app/service.py",
        ),
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.find_javascript_repository_references(test_file) == {
        "app/service.py",
        "frontend/tests/e2e/base.js",
    }


def test_recursive_javascript_scan_fails_closed_for_unproven_collectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "scripts" / "recursive.test.mjs"
    test_file.parent.mkdir(parents=True)
    source = repository / "frontend" / "src" / "nested" / "Button.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export const Button = 1\n", encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    valid_collector = (
        "function collectAuthoredFiles(root) {\n"
        "  const files = [];\n"
        "  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {\n"
        "    if (entry.isDirectory()) {\n"
        "      if (!ignoredDirectories.has(entry.name)) {\n"
        "        files.push(...collectAuthoredFiles(path.join(root, entry.name)));\n"
        "      }\n"
        "      continue;\n"
        "    }\n"
        "    if (authoredExtensions.has(path.extname(entry.name))) {\n"
        "      files.push(path.join(root, entry.name));\n"
        "    }\n"
        "  }\n"
        "  return files;\n"
        "}\n"
    )
    scan = (
        'const frontendRoot = path.resolve(import.meta.dirname, "..");\n'
        'const scanRoots = ["src"];\n'
        'const authoredExtensions = new Set([".ts", ".tsx"]);\n'
        "const ignoredDirectories = new Set([]);\n"
        "{collector}"
        "for (const root of scanRoots) {\n"
        "  const absoluteRoot = path.join(frontendRoot, root);\n"
        "  for (const filePath of collectAuthoredFiles(absoluteRoot)) {\n"
        '    fs.readFileSync(filePath, "utf8");\n'
        "  }\n"
        "}\n"
    )
    variants = (
        scan.replace("{collector}", ""),
        scan.replace(
            "{collector}", valid_collector.replace("return files;", "return [];")
        ),
        scan.replace(
            "{collector}",
            valid_collector.replace("const files = [];", "const files = new Set();"),
        ),
        scan.replace(
            "{collector}",
            valid_collector.replace("withFileTypes: true", "withFileTypes: false"),
        ),
        scan.replace(
            "{collector}",
            valid_collector.replace("entry.isDirectory()", "entry.isFile()"),
        ),
        scan.replace(
            "{collector}",
            valid_collector.replace("return files;", "return otherFiles;"),
        ),
        scan.replace("{collector}", valid_collector).replace(
            'const authoredExtensions = new Set([".ts", ".tsx"]);\n', ""
        ),
        scan.replace("{collector}", valid_collector).replace(
            'const authoredExtensions = new Set([".ts", ".tsx"]);',
            "const authoredExtensions = new Set([]);",
        ),
        scan.replace("{collector}", valid_collector).replace(
            "const ignoredDirectories = new Set([]);\n", ""
        ),
        scan.replace("{collector}", valid_collector).replace(
            'fs.readFileSync(filePath, "utf8")', "readFile(filePath)"
        ),
        scan.replace(
            'const scanRoots = ["src"];', 'const scanRoots = ["../../../../outside"];'
        ),
        scan.replace(
            'const scanRoots = ["src"];', 'const scanRoots = ["src/nested/Button.tsx"];'
        ),
        scan.replace(
            'const scanRoots = ["src"];',
            'const scanRoots = ["file:src", "src/nested/Button.tsx"];',
        ),
        scan.replace(
            'const frontendRoot = path.resolve(import.meta.dirname, "..");',
            'const frontendRoot = path.resolve(import.meta.dirname, "../../../../");',
        ),
    )
    for index, source_text in enumerate(variants):
        test_file.write_text(source_text, encoding="utf-8")
        assert checker.find_javascript_repository_references(test_file) == set(), (
            f"variant {index}: {source_text}"
        )


def test_recursive_javascript_scan_requires_actual_roots_loops_and_read_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "scripts" / "recursive.test.mjs"
    test_file.parent.mkdir(parents=True)
    source = repository / "frontend" / "src" / "nested" / "Button.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export const Button = 1\n", encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    collector = (
        "function collectAuthoredFiles(root) {\n"
        "  const files = [];\n"
        "  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {\n"
        "    if (entry.isDirectory()) {\n"
        "      if (!ignoredDirectories.has(entry.name)) {\n"
        "        files.push(...collectAuthoredFiles(path.join(root, entry.name)));\n"
        "      }\n"
        "      continue;\n"
        "    }\n"
        "    if (authoredExtensions.has(path.extname(entry.name))) {\n"
        "      files.push(path.join(root, entry.name));\n"
        "    }\n"
        "  }\n"
        "  return files;\n"
        "}\n"
    )
    root_loop = (
        "for (const root of scanRoots) {\n"
        "  const absoluteRoot = path.join(frontendRoot, root);\n"
        "  for (const filePath of collectAuthoredFiles(absoluteRoot)) {\n"
        '    fs.readFileSync(filePath, "utf8");\n'
        "  }\n"
        "}\n"
    )
    header = (
        'const frontendRoot = path.resolve(import.meta.dirname, "..");\n'
        'const scanRoots = ["src"];\n'
        'const authoredExtensions = new Set([".ts", ".tsx"]);\n'
        "const ignoredDirectories = new Set([]);\n"
    )
    malformed = (
        header + collector + "const unrelated = true;\n",
        header + "function collectAuthoredFiles(root) {\n",
        header + collector + "for (const root of scanRoots) {\n",
        header
        + collector
        + "for (const root of scanRoots) {\n  const ignored = true;\n}\n",
        header
        + collector
        + root_loop.replace(
            "const absoluteRoot = path.join(frontendRoot, root);",
            "const absoluteRoot = root;",
        ),
        header
        + collector
        + root_loop.replace(
            "for (const filePath of collectAuthoredFiles(absoluteRoot)) {",
            "for (const filePath of files) {",
        ),
        header
        + collector
        + root_loop.replace(
            'fs.readFileSync(filePath, "utf8");', "readFile(filePath);"
        ),
        header.replace(
            'const frontendRoot = path.resolve(import.meta.dirname, "..");',
            "const frontendRoot = path.resolve(import.meta.dirname, `..`);",
        )
        + collector
        + root_loop,
        header.replace('const scanRoots = ["src"];', "const scanRoots = [dynamicRoot];")
        + collector
        + root_loop,
    )
    for source_text in malformed:
        test_file.write_text(source_text, encoding="utf-8")
        assert checker.find_javascript_repository_references(test_file) == set()

    real_scandir = checker.os.scandir

    def deny_scan(path: object):
        if Path(path) == repository / "frontend" / "src" / "nested":
            raise PermissionError("fixture scan is not accessible")
        return real_scandir(path)

    monkeypatch.setattr(checker.os, "scandir", deny_scan)
    test_file.write_text(header + collector + root_loop, encoding="utf-8")
    assert checker.find_javascript_repository_references(test_file) == set()


def test_javascript_static_root_reads_and_path_join_reject_unresolved_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, test_file = _write_javascript_fixture(
        tmp_path,
        'const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..",);\n'
        'function readJson(relativePath) { return JSON.parse(readFileSync(path.join(repositoryRoot, relativePath), "utf8")); }\n'
        'function notAReader(relativePath) { return readFileSync(path.join(otherRoot, relativePath), "utf8"); }\n'
        'const good = readJson("package.json");\n'
        "const templated = readJson(`package-lock.json`);\n"
        "const templatedJoin = path.join(repositoryRoot, `package-lock.json`);\n"
        'const direct = readFileSync(path.join(repositoryRoot, ".releaserc.json"), "utf8");\n'
        'const outsideHelper = readJson("../../../../outside.json");\n'
        'const outside = readFileSync(path.join(repositoryRoot, "../../../../outside.json"), "utf8");\n'
        "const noStaticRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), dynamicRoot);\n"
        'const outsideRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../../../",);\n',
        ("package.json", ".releaserc.json", "package-lock.json"),
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.find_javascript_repository_references(test_file) == {
        "package.json",
        ".releaserc.json",
    }


def test_recursive_reference_matcher_rejects_escaped_root_and_non_directory_targets(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend" / "scripts" / "recursive.test.mjs"
    test_file.parent.mkdir(parents=True)
    source = repository / "frontend" / "src" / "nested" / "Button.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export const Button = 1\n", encoding="utf-8")
    collector = (
        'const authoredExtensions = new Set([".ts", ".tsx"]);\n'
        "const ignoredDirectories = new Set([]);\n"
        "function collectAuthoredFiles(root) {\n"
        "  const files = [];\n"
        "  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {\n"
        "    if (entry.isDirectory()) {\n"
        "      if (!ignoredDirectories.has(entry.name)) {\n"
        "        files.push(...collectAuthoredFiles(path.join(root, entry.name)));\n"
        "      }\n"
        "      continue;\n"
        "    }\n"
        "    if (authoredExtensions.has(path.extname(entry.name))) {\n"
        "      files.push(path.join(root, entry.name));\n"
        "    }\n"
        "  }\n"
        "  return files;\n"
        "}\n"
    )
    loop = (
        "for (const root of scanRoots) {\n"
        "  const absoluteRoot = path.join(frontendRoot, root);\n"
        "  for (const filePath of collectAuthoredFiles(absoluteRoot)) {\n"
        '    fs.readFileSync(filePath, "utf8");\n'
        "  }\n"
        "}\n"
    )

    escaped = (
        'const frontendRoot = path.resolve(import.meta.dirname, "../../../../../../../../");\n'
        'const scanRoots = ["src"];\n' + collector + loop
    )
    masked, literals = checker._mask_javascript_non_code(escaped)
    escaped_root = (
        test_file.parent
        / checker._javascript_string_value(
            checker._JS_IMPORT_META_DIRNAME_ROOT.search(masked).group("path"), literals
        )
    ).resolve()
    assert repository.resolve() not in escaped_root.parents
    assert (
        checker._recursive_scan_references(
            masked, test_file, repository.resolve(), literals
        )
        == set()
    )

    invalid_targets = (
        'const frontendRoot = path.resolve(import.meta.dirname, "..");\n'
        'const scanRoots = ["file:src", "src/nested/Button.tsx"];\n' + collector + loop
    )
    masked, literals = checker._mask_javascript_non_code(invalid_targets)
    assert (
        checker._recursive_scan_references(
            masked, test_file, repository.resolve(), literals
        )
        == set()
    )


def test_static_base_extractors_reject_paths_outside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, test_file = _write_javascript_fixture(
        tmp_path,
        'const outsideFrontend = path.resolve(import.meta.dirname, "../../../../../../../../");\n'
        'const outsideRepository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../../../../../",);\n',
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert checker.find_javascript_repository_references(test_file) == set()


def test_mjs_source_stem_match_is_exact_and_nearby() -> None:
    test_path = "frontend/scripts/validator.test.mjs"
    assert checker.matches_source(test_path, {"frontend/scripts/validator.mjs"}, [])
    assert checker.matches_source(test_path, {"frontend/validator.js"}, [])
    assert not checker.matches_source(
        test_path, {"frontend/scripts/validator-extra.js"}, []
    )


@pytest.mark.parametrize(
    ("source", "expected_message"),
    [
        (
            '@pytest.mark.skip(reason="unavailable")\ndef test_case(): ...\n',
            "Python dynamic skip",
        ),
        (
            '@pytest.mark.xfail(reason="known failure")\ndef test_case(): ...\n',
            "Python dynamic skip",
        ),
        (
            'pytest.skip(\n    "unavailable",\n)\n',
            "Python dynamic skip",
        ),
        (
            'func TestCase(t *testing.T) { t.Skipf("unavailable: %s", reason) }\n',
            "Go dynamic skip",
        ),
        (
            'describe\n  .skip("unavailable", () => {})\n',
            "JS/TS dynamic skip (describe.skip)",
        ),
    ],
)
def test_aud508_dynamic_skip_syntax_is_detected(
    tmp_path: Path, source: str, expected_message: str
) -> None:
    suffix = (
        ".py"
        if expected_message.startswith("Python")
        else ".go"
        if expected_message.startswith("Go")
        else ".ts"
    )
    test_file = tmp_path / f"test_dynamic_skip{suffix}"
    test_file.write_text(source, encoding="utf-8")

    errors: list[str] = []
    check_anti_patterns(test_file, errors, [], [])

    assert any(expected_message in error for error in errors)


def test_aud508_skip_exemptions_require_real_comment_evidence(tmp_path: Path) -> None:
    cases = {
        "commented.py": ('# pytest.skip("example")\n', False),
        "string.py": ('message = "pytest.skip(\\"reason\\")"\n', False),
        "static_skipif.py": (
            '@pytest.mark.skipif(not PLATFORM_SUPPORTED, reason="platform")\ndef test_case(): ...\n',
            False,
        ),
        "commented_skip.py": ('# QUALITY-123 @owner\npytest.skip("reason")\n', False),
        "reason_text_is_not_comment.py": (
            'pytest.skip("QUALITY-123 @owner")\n',
            True,
        ),
        "quarantine_text_is_not_allowance.py": (
            'pytest.skip("quarantined pending review")\n',
            True,
        ),
    }
    for name, (source, should_error) in cases.items():
        test_file = tmp_path / name
        test_file.write_text(source, encoding="utf-8")
        errors: list[str] = []

        check_anti_patterns(test_file, errors, [], [])

        assert any("dynamic skip" in error for error in errors) is should_error, name


def test_aud509_source_matching_requires_exact_module_relationships(
    tmp_path: Path, monkeypatch
) -> None:
    assert not matches_source("tests/test_auth.py", {"app/subauth.py"}, [])
    assert not matches_source("tests/test_auth.py", {"app/authentication.py"}, [])
    assert matches_source("tests/test_auth_service.py", {"app/auth.py"}, [])

    repository = tmp_path / "repository"
    gateway = repository / "services" / "gateway"
    gateway.mkdir(parents=True)
    (gateway / "go.mod").write_text("module example.com/gateway\n", encoding="utf-8")
    (gateway / "unrelated.go").write_text("package unrelated\n", encoding="utf-8")
    (gateway / "auth.go").write_text("package gateway\n", encoding="utf-8")
    (gateway / "auth_test.go").write_text("package gateway\n", encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert not matches_source(
        "services/gateway/auth_test.go", {"services/gateway/unrelated.go"}, []
    )
    assert matches_source(
        "services/gateway/auth_test.go", {"services/gateway/auth.go"}, []
    )

    assert not matches_source(
        "frontend/src/components/__tests__/Button.test.tsx",
        {"frontend/src/other/Button.tsx"},
        [],
    )
    assert not matches_source(
        "frontend/src/components/__tests__/Button.test.tsx", set(), []
    )


def test_aud509_go_test_matches_its_same_package_without_a_sibling_name(
    tmp_path: Path, monkeypatch
) -> None:
    repository = tmp_path / "repository"
    package = repository / "services" / "gateway" / "middleware"
    package.mkdir(parents=True)
    (repository / "go.mod").write_text("module example.com/repo\n", encoding="utf-8")
    (package / "auth.go").write_text("package middleware\n", encoding="utf-8")
    (package / "auth_and_jwks_setup_test.go").write_text(
        "package middleware\n", encoding="utf-8"
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert matches_source(
        "services/gateway/middleware/auth_and_jwks_setup_test.go",
        {"services/gateway/middleware/auth.go"},
        [],
        reference_paths={"services/gateway/middleware/auth.go"},
    )
    assert not matches_source(
        "services/gateway/middleware/auth_and_jwks_setup_test.go",
        {"services/gateway/handlers.go"},
        [],
        reference_paths={"services/gateway/handlers.go"},
    )


def test_aud509_go_external_test_requires_exact_package_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    repository = tmp_path / "repository"
    package = repository / "services" / "pkg" / "spiffe"
    package.mkdir(parents=True)
    (package / "spiffe.go").write_text("package spiffe\n", encoding="utf-8")
    test_file = package / "spiffe_dynamic_rotation_stress_test.go"
    test_file.write_text(
        'package spiffe_test\nimport "github.com/spiffe/go-spiffe/v2/workloadapi"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert matches_source(
        "services/pkg/spiffe/spiffe_dynamic_rotation_stress_test.go",
        {"services/pkg/spiffe/spiffe.go"},
        [],
        reference_paths={
            "services/pkg/spiffe/spiffe.go",
        },
    )

    test_file.write_text(
        'package unrelated_test\nimport "github.com/spiffe/go-spiffe/v2/workloadapi"\n',
        encoding="utf-8",
    )
    assert not matches_source(
        "services/pkg/spiffe/spiffe_dynamic_rotation_stress_test.go",
        {"services/pkg/spiffe/spiffe.go"},
        [],
        reference_paths={"services/pkg/spiffe/spiffe.go"},
    )


def test_aud509_imports_match_only_the_exact_inventoried_module() -> None:
    assert not matches_source(
        "tests/test_auth.py",
        {"app/unrelated.py"},
        [],
        imported_modules={"app"},
        reference_paths={"app/unrelated.py"},
    )
    assert matches_source(
        "tests/test_auth.py",
        {"app/auth.py"},
        [],
        imported_modules={"app", "app.auth"},
        reference_paths={"app/auth.py"},
    )


def test_aud509_typescript_import_must_resolve_to_an_inventoried_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "frontend/src/components/__tests__/unrelated.test.tsx"
    test_file.parent.mkdir(parents=True)
    test_file.write_text('import helper from "../../helpers";\n', encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    sources = {"frontend/src/components/Button.tsx"}

    assert not matches_source(
        "frontend/src/components/__tests__/unrelated.test.tsx",
        sources,
        [],
        reference_paths=sources,
    )

    test_file.write_text('import Button from "../Button";\n', encoding="utf-8")
    assert matches_source(
        "frontend/src/components/__tests__/unrelated.test.tsx",
        sources,
        [],
        reference_paths=sources,
    )


def test_aud509_relative_python_import_resolves_inside_its_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    test_file = repository / "tests/unit/test_case.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("from .helpers import helper\n", encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    imported_modules = checker.check_python_duplicates_and_imports(test_file, [])

    assert matches_source(
        "tests/unit/test_case.py",
        set(),
        [],
        imported_modules=imported_modules,
        reference_paths={"tests/unit/helpers.py"},
    )
    assert not matches_source(
        "tests/unit/test_case.py",
        set(),
        [],
        imported_modules=imported_modules,
        reference_paths={"helpers.py"},
    )


def test_aud509_python_name_match_prefers_exact_and_rejects_ambiguity() -> None:
    assert matches_source(
        "tests/test_report_api.py",
        {"app/report.py", "app/report_api.py"},
        [],
    )
    assert not matches_source(
        "tests/test_report_api.py",
        {"app/report.py", "services/report.py"},
        [],
    )


@pytest.mark.parametrize(
    ("filename", "source"),
    [
        (
            "fake_skip.go",
            '// t.Skipf("comment only")\nmessage := "t.Skipf(\\"string only\\")"\n',
        ),
        (
            "fake_skip.mjs",
            '// describe.skip("comment only")\nconst text = "describe.skip(\\"string only\\")";\n',
        ),
    ],
)
def test_aud508_non_python_skip_scanner_ignores_comments_and_strings(
    tmp_path: Path, filename: str, source: str
) -> None:
    test_file = tmp_path / filename
    test_file.write_text(source, encoding="utf-8")
    errors: list[str] = []

    check_anti_patterns(test_file, errors, [], [])

    assert not any("dynamic skip" in error for error in errors)


@pytest.mark.parametrize(
    ("filename", "source"),
    [
        ("tracked_skip.go", 't.Skipf("reason") // QUALITY-123 @owner\n'),
        ("tracked_skip.mjs", 'describe.skip("reason") // QUALITY-123 @owner\n'),
    ],
)
def test_aud508_non_python_skip_accepts_tracking_comments(
    tmp_path: Path, filename: str, source: str
) -> None:
    test_file = tmp_path / filename
    test_file.write_text(source, encoding="utf-8")
    errors: list[str] = []

    check_anti_patterns(test_file, errors, [], [])

    assert not any("dynamic skip" in error for error in errors)


@pytest.mark.parametrize(
    "markup",
    [
        "<main>content</main>",
        "<><section>content</section></>",
        "<Widget.Part><span /></Widget.Part>",
        '<main title={">"}>content</main>',
        "<Widget<string> />",
        "<Widget<Array<string>>><span /></Widget>",
        "<Widget-1>content</Widget-1>",
        "<Élement>content</Élement>",
        "<Élement>content</Élement>",
        '<main title="line one\nline two" />',
        '<main>{value ? <span /> : "</main>"}</main>',
    ],
)
def test_typescript_import_after_jsx_keeps_exact_source_relationship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, markup: str
) -> None:
    repository = tmp_path / "repo"
    relative = "frontend/src/components/__tests__/jsx.test.tsx"
    test_file = repository / relative
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        f'const view = {markup};\nimport Button from "../Button";\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert matches_source(relative, {"frontend/src/components/Button.tsx"}, [])
    assert not matches_source(relative, {"frontend/src/components/Other.tsx"}, [])


@pytest.mark.parametrize(
    "source",
    [
        'const view = <main>import Button from "../Button"</main>;\n',
        "const view = <main title='import Button from \"../Button\"' />;\n",
        'const value = left </main>\nimport Button from "../Button";\n',
        'const view = <main>import Button from "../Button";\n',
        'const view = <main>import Button from "../Button"</other>;\n',
        'const view = <Widget<string>>import Button from "../Button"</Widget>;\n',
        'const view = <Widget-1>import Button from "../Button"</Widget-1>;\n',
        'const view = <Élement>import Button from "../Button"</Élement>;\n',
        'const view = <Élement>import Button from "../Button"</Élement>;\n',
        'const view = <Widget!>import Button from "../Button"</Widget!>;\n',
        'const view = <main title="line one\nline two">'
        'import Button from "../Button"</main>;\n',
        (
            "const view = "
            + "<main>" * 66
            + 'import Button from "../Button"'
            + "</main>" * 66
            + ";\n"
        ),
    ],
)
def test_typescript_non_code_jsx_and_regex_do_not_claim_source_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    repository = tmp_path / "repo"
    relative = "frontend/src/components/__tests__/unrelated.test.tsx"
    test_file = repository / relative
    test_file.parent.mkdir(parents=True)
    test_file.write_text(source, encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert not matches_source(relative, {"frontend/src/components/Button.tsx"}, [])


def test_typescript_dotted_module_stem_resolves_exact_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    relative = "frontend/src/test/__tests__/mockIsolation.test.ts"
    test_file = repository / relative
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        'import config from "../../../vitest.config";\n', encoding="utf-8"
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)

    assert matches_source(
        relative, set(), [], reference_paths={"frontend/vitest.config.ts"}
    )
    assert not matches_source(
        relative, set(), [], reference_paths={"frontend/other.config.ts"}
    )


_LOCAL_TYPESCRIPT_GLOB_CONTRACT = """import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"
import { glob } from "glob"
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const SRC_ROOT = path.resolve(__dirname, "..")
const MATCHER = /removed/
async function scan() {
  const files = await glob("**/*.{ts,tsx,css}", {
    cwd: SRC_ROOT,
    ignore: [
      "tests/**",
      "**/__tests__/**",
      "**/*.test.{ts,tsx}",
      "**/*.spec.{ts,tsx}",
      "**/*.stories.{ts,tsx}",
    ],
  })
  expect(files.length).toBeGreaterThan(0)
  const violations = files.filter((relFile) =>
    MATCHER.test(readFileSync(path.join(SRC_ROOT, relFile), "utf-8"))
  )
  return violations
}
"""


def _write_typescript_glob_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> tuple[Path, Path]:
    repository = tmp_path / "repo"
    contract = repository / "frontend/src/tests/glob.test.ts"
    contract.parent.mkdir(parents=True)
    (repository / "frontend/package.json").write_text("{}", encoding="utf-8")
    for relative in (
        "frontend/src/components/Button.tsx",
        "frontend/src/utils/nested/helper.ts",
        "frontend/src/theme.css",
        "frontend/src/tests/fixture.ts",
        "frontend/src/components/__tests__/fixture.tsx",
        "frontend/src/components/Button.test.tsx",
        "frontend/src/components/Button.spec.tsx",
        "frontend/src/components/Button.stories.tsx",
        "frontend/src/components/data.json",
        "frontend/src/.hidden.ts",
        "frontend/src/.private/hidden.ts",
    ):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    contract.write_text(source, encoding="utf-8")
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", repository)
    return repository, contract


def test_typescript_glob_scan_links_only_files_it_recursively_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, contract = _write_typescript_glob_fixture(
        tmp_path, monkeypatch, _LOCAL_TYPESCRIPT_GLOB_CONTRACT
    )

    references = find_typescript_repository_references(contract)

    assert references == {
        "frontend/src/components/Button.tsx",
        "frontend/src/utils/nested/helper.ts",
        "frontend/src/theme.css",
    }
    assert matches_source(
        "frontend/src/tests/glob.test.ts",
        set(),
        [],
        repository_references=references,
        reference_paths={"frontend/src/utils/nested/helper.ts"},
    )
    assert not matches_source(
        "frontend/src/tests/glob.test.ts",
        set(),
        [],
        repository_references=references,
        reference_paths={"frontend/src/components/Unscanned.tsx"},
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("fileURLToPath(import.meta.url)", "fileURLToPath(otherUrl)"),
        (
            'path.resolve(__dirname, "..")',
            'path.resolve(__dirname, "../../../..")',
        ),
        ("cwd: SRC_ROOT", "cwd: otherRoot"),
        ("path.join(SRC_ROOT, relFile)", "path.join(otherRoot, relFile)"),
        ("files.filter", '["components/Button.tsx"].filter'),
        (
            'readFileSync(path.join(SRC_ROOT, relFile), "utf-8")',
            "String(path.join(SRC_ROOT, relFile))",
        ),
        ("async function scan()", "async function scan(SRC_ROOT: string)"),
        ('"tests/**",', '"tests/**", "**/*",'),
        ('"**/*.{ts,tsx,css}"', '"*.{ts,tsx,css}"'),
        (
            'path.resolve(__dirname, "..")',
            'path.resolve(__dirname, "..") + "/elsewhere"',
        ),
        (
            'path.resolve(__dirname, "..")',
            'path.resolve(__dirname, "..")\n + "/elsewhere"',
        ),
        ("  })\n  expect", "  }).then(() => [])\n  expect"),
        ("  })\n  expect", "  })\n .then(() => [])\n  expect"),
        (
            "async function scan()",
            r"async function scan(SRC_\u0052OOT: string)",
        ),
        (
            'const SRC_ROOT = path.resolve(__dirname, "..")',
            'const SRC_ROOT = path.resolve(__dirname, "..") as string',
        ),
    ],
)
def test_typescript_glob_scan_rejects_unproven_traversal_or_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: str, new: str
) -> None:
    _, contract = _write_typescript_glob_fixture(
        tmp_path, monkeypatch, _LOCAL_TYPESCRIPT_GLOB_CONTRACT.replace(old, new)
    )

    assert find_typescript_repository_references(contract) == set()


def test_typescript_glob_scan_does_not_follow_external_file_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, contract = _write_typescript_glob_fixture(
        tmp_path, monkeypatch, _LOCAL_TYPESCRIPT_GLOB_CONTRACT
    )
    outside = tmp_path / "outside.ts"
    outside.write_text("external\n", encoding="utf-8")
    os.symlink(outside, repository / "frontend/src/components/external.ts")

    assert find_typescript_repository_references(contract) == {
        "frontend/src/components/Button.tsx",
        "frontend/src/utils/nested/helper.ts",
        "frontend/src/theme.css",
    }


def test_python_contract_accepts_verified_test_root_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "TEST_ROOT = Path(__file__).resolve().parents[1]\n"
        'VALIDATOR_PATH = TEST_ROOT / "scripts" / "quality"'
        ' / "validate_trivy_kyverno_fixture.py"\n',
    )

    assert find_python_repository_references(contract) == {
        "scripts/quality/validate_trivy_kyverno_fixture.py"
    }


@pytest.mark.parametrize(
    ("rebind", "expected"),
    [
        ('TEST_ROOT = Path("elsewhere")\n', {"elsewhere"}),
        ("import elsewhere as TEST_ROOT\n", set()),
    ],
)
def test_python_contract_rejects_rebound_test_root_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rebind: str,
    expected: set[str],
) -> None:
    contract = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        f"TEST_ROOT = Path(__file__).resolve().parents[1]\n{rebind}"
        'TARGET = TEST_ROOT / "scripts" / "quality"'
        ' / "validate_trivy_kyverno_fixture.py"\n',
    )

    references = find_python_repository_references(contract)
    assert references == expected
    assert not matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=references,
        reference_paths={"scripts/quality/validate_trivy_kyverno_fixture.py"},
    )


@pytest.mark.parametrize("root_name", ["TEST_ROOT", "ROOT"])
@pytest.mark.parametrize(
    "body",
    [
        "def helper({root_name}):\n    return {root_name} / {target}\n",
        "async def helper({root_name}):\n    return {root_name} / {target}\n",
        "def helper():\n    {root_name} = fallback\n"
        "    return {root_name} / {target}\n",
        "def helper():\n    return {root_name} / {target}\n"
        "    {root_name} = fallback\n",
        "def helper():\n    {root_name}: Path\n    return {root_name} / {target}\n",
        "def helper[{root_name}]():\n    return {root_name} / {target}\n",
        "class Subject[{root_name}]:\n    target = {root_name} / {target}\n",
        "type Subject[{root_name}] = list[{root_name} / {target}]\n",
        "subject = lambda {root_name}: {root_name} / {target}\n",
        "class Subject:\n    {root_name} = fallback\n"
        "    target = {root_name} / {target}\n",
        "targets = [{root_name} / {target} for {root_name} in roots]\n",
        "targets = ({root_name} / {target} for {root_name} in roots)\n",
        "targets = [{root_name} / {target} for value in roots "
        "for {root_name} in value]\n",
    ],
)
def test_python_contract_does_not_borrow_shadowed_root_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_name: str,
    body: str,
) -> None:
    contract = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        f"{root_name} = Path(__file__).resolve().parents[1]\n"
        + body.format(
            root_name=root_name,
            target='"scripts" / "quality" / "validate_trivy_kyverno_fixture.py"',
        )
        + f'MODULE_TARGET = {root_name} / "app" / "unrelated.py"\n',
    )

    references = find_python_repository_references(contract)

    assert references == {"app/unrelated.py"}
    assert not matches_source(
        "tests/test_contract.py",
        set(),
        [],
        repository_references=references,
        reference_paths={"scripts/quality/validate_trivy_kyverno_fixture.py"},
    )


@pytest.mark.parametrize(
    "body",
    [
        "def helper():\n    return TEST_ROOT / {target}\n",
        "def helper[Value]():\n    return TEST_ROOT / {target}\n",
        "subject = lambda: TEST_ROOT / {target}\n",
        "class Subject:\n    TEST_ROOT = fallback\n"
        "    def helper(self):\n        return TEST_ROOT / {target}\n",
        "targets = [TEST_ROOT / {target} for item in items]\n",
        "targets = [item for TEST_ROOT in [TEST_ROOT / {target}] for item in items]\n",
        "def helper(TEST_ROOT=TEST_ROOT / {target}):\n    return TEST_ROOT\n",
    ],
)
def test_python_contract_keeps_unshadowed_root_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    contract = _write_repository_contract(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        "TEST_ROOT = Path(__file__).resolve().parents[1]\n"
        + body.format(
            target='"scripts" / "quality" / "validate_trivy_kyverno_fixture.py"'
        ),
    )

    assert find_python_repository_references(contract) == {
        "scripts/quality/validate_trivy_kyverno_fixture.py"
    }


def test_typescript_glob_scan_accepts_closed_semicolon_initializers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (
        _LOCAL_TYPESCRIPT_GLOB_CONTRACT.replace(")\nconst", ");\nconst")
        .replace("  })\n  expect", "  });\n  expect")
        .replace(
            "expect(files.length).toBeGreaterThan(0)\n",
            "expect(files.length).toBeGreaterThan(0);\n",
        )
    )
    _, contract = _write_typescript_glob_fixture(tmp_path, monkeypatch, source)

    assert find_typescript_repository_references(contract) == {
        "frontend/src/components/Button.tsx",
        "frontend/src/utils/nested/helper.ts",
        "frontend/src/theme.css",
    }


def test_typescript_glob_scan_requires_module_scope_root_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _LOCAL_TYPESCRIPT_GLOB_CONTRACT.replace(
        "const __filename", "function unrelated() {\nconst __filename"
    ).replace("async function scan()", "}\nasync function scan()")
    _, contract = _write_typescript_glob_fixture(tmp_path, monkeypatch, source)

    assert find_typescript_repository_references(contract) == set()
