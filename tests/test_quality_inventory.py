from __future__ import annotations

from pathlib import Path

import pytest

try:
    from scripts.quality import check_orphans_and_anti_patterns as checker
    from scripts.quality import generate_test_inventory as inventory
    from scripts.quality.check_orphans_and_anti_patterns import (
        check_anti_patterns,
        check_python_duplicates_and_imports,
        find_python_repository_references,
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

    # Utility
    assert classify_file("scripts/setup.sh", generated_patterns) == "utility"


def test_inventory_prunes_dependency_and_hidden_directories(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "visible.py").write_text("pass", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "hidden.ts").write_text(
        "export {}", encoding="utf-8"
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
    assert should_prune_directory(".codex") is True
    assert should_prune_directory("stryker-tmp") is True
    assert should_prune_directory(".github") is False
    assert should_prune_directory(".husky") is False


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
    assert (
        matches_source(
            "tests/test_aggregate_go_benchmarks.py",
            set(),
            [],
            {"scripts"},
        )
        is True
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
