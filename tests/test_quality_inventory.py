from __future__ import annotations

from pathlib import Path

from scripts.quality.check_orphans_and_anti_patterns import (
    check_anti_patterns,
    check_python_duplicates_and_imports,
)
from scripts.quality.generate_test_inventory import (
    classify_file,
    is_generated,
    is_tier0,
    resolve_owner,
)


def test_resolve_owner() -> None:
    teams = {
        "app/api/users": "@backend-team",
        "app/": "@backend-team",
        "frontend/src/": "@frontend-team",
    }
    assert resolve_owner("app/api/users/router.py", teams) == "@backend-team"
    assert resolve_owner("app/core/config.py", teams) == "@backend-team"
    assert (
        resolve_owner("frontend/src/components/Button.tsx", teams) == "@frontend-team"
    )
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
