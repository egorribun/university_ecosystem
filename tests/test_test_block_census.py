"""Negative and positive controls for scripts/quality/test_block_census.py (AUD-428).

Every control writes its fixture tree to tmp_path, so the census never reads the
real repository from these tests.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CENSUS_PATH = REPOSITORY_ROOT / "scripts" / "quality" / "test_block_census.py"


def _load_census() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_block_census_under_test", CENSUS_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


census = _load_census()


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _python_checks(text: str) -> list[tuple[str, bool]]:
    return [
        (block.name, block.has_result_check)
        for block in census.python_blocks("t.py", text)
    ]


def _go_checks(text: str) -> list[tuple[str, bool]]:
    return [
        (block.name, block.has_result_check)
        for block in census.go_blocks("t_test.go", text)
    ]


def _run(
    tmp_path: Path,
    *,
    python: dict[str, str] | None = None,
    go: dict[str, str] | None = None,
    allowlist: object | None = None,
) -> tuple[int, dict]:
    for relative, text in (python or {}).items():
        _write(tmp_path, relative, text)
    for relative, text in (go or {}).items():
        _write(tmp_path, relative, text)
    allow_path = tmp_path / "quality" / "allowlist.json"
    if allowlist is not None:
        _write(
            tmp_path,
            "quality/allowlist.json",
            allowlist if isinstance(allowlist, str) else json.dumps(allowlist),
        )
    output = tmp_path / "out" / "census.json"
    code = census.main(
        [
            "--root",
            str(tmp_path),
            "--allowlist",
            str(allow_path),
            "--output",
            str(output),
        ]
    )
    return code, json.loads(output.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Python negative controls
# ---------------------------------------------------------------------------


def test_python_test_without_any_check_is_resultless() -> None:
    assert _python_checks(
        "def test_nothing():\n    value = 1 + 1\n    print(value)\n"
    ) == [("test_nothing", False)]


@pytest.mark.parametrize(
    "statement", ["assert True", "assert 1", "assert 'text'", "assert None"]
)
def test_python_constant_assert_is_not_a_result_check(statement: str) -> None:
    assert _python_checks(f"def test_constant():\n    {statement}\n") == [
        ("test_constant", False)
    ]


def test_python_tuple_assert_is_not_a_result_check() -> None:
    assert _python_checks("def test_tuple():\n    assert (True, 'always true')\n") == [
        ("test_tuple", False)
    ]


def test_python_comment_and_string_do_not_count() -> None:
    source = (
        "def test_commented():\n"
        "    # assert value == 2\n"
        "    text = 'assert value == 2 and pytest.raises(ValueError)'\n"
        "    doc = '''assert mock.assert_called_once()'''\n"
        "    print(text, doc)\n"
    )
    assert _python_checks(source) == [("test_commented", False)]


def test_python_non_test_function_is_not_a_block() -> None:
    assert _python_checks("def helper():\n    value = 1\n") == []


# ---------------------------------------------------------------------------
# Python positive controls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "assert value == 2",
        "with pytest.raises(ValueError):\n        raise ValueError()",
        "with pytest.warns(UserWarning):\n        warn()",
        "pytest.fail('reached')",
        "mock.assert_called_once()",
        "self.assertEqual(value, 2)",
        "assert_result(value)",
        "_assert_result(value)",
        "expect_result(value)",
        "verify_result(value)",
        "require_result(value)",
        "check_result(value)",
        "validate_result(value)",
    ],
)
def test_python_real_result_checks_are_detected(body: str) -> None:
    source = f"from helpers import *\n\ndef test_checked(self=None):\n    value = 2\n    {body}\n"
    assert _python_checks(source) == [("test_checked", True)]


def test_python_check_inside_nested_helper_counts() -> None:
    source = (
        "def test_nested():\n    def inner():\n        assert 1 + 1 == 2\n    inner()\n"
    )
    assert _python_checks(source) == [("test_nested", True)]


def test_python_method_and_async_test_are_blocks() -> None:
    source = (
        "import unittest\n"
        "class Suite(unittest.TestCase):\n"
        "    def test_method(self):\n"
        "        self.assertTrue(True)\n"
        "    async def test_async(self):\n"
        "        pass\n"
    )
    assert _python_checks(source) == [
        ("Suite.test_method", True),
        ("Suite.test_async", False),
    ]


def test_python_duplicate_names_are_suffixed_in_line_order() -> None:
    source = (
        "def test_same():\n    pass\n\ndef test_same():\n    assert True is not None\n"
    )
    names = [block.name for block in census.python_blocks("t.py", source)]
    assert names == ["test_same", "test_same#2"]


def test_python_helper_named_variable_is_not_a_call() -> None:
    # A variable whose name starts with a helper prefix is not a call and never counts.
    assert _python_checks(
        "def test_name():\n    checkpoint = 1\n    print(checkpoint)\n"
    ) == [("test_name", False)]
    assert _python_checks(
        "def test_variable():\n    check = 1\n    print(check)\n"
    ) == [("test_variable", False)]


# ---------------------------------------------------------------------------
# Go negative controls
# ---------------------------------------------------------------------------

GO_HEADER = 'package sample\n\nimport "testing"\n\n'


def test_go_test_with_only_log_is_resultless() -> None:
    source = GO_HEADER + 'func TestLogOnly(t *testing.T) {\n\tt.Log("observed")\n}\n'
    assert _go_checks(source) == [("TestLogOnly", False)]


def test_go_test_with_no_body_checks_is_resultless() -> None:
    source = (
        GO_HEADER + "func TestEmpty(t *testing.T) {\n\tvalue := 1\n\t_ = value\n}\n"
    )
    assert _go_checks(source) == [("TestEmpty", False)]


def test_go_comments_and_strings_do_not_count() -> None:
    source = (
        GO_HEADER
        + "func TestDecoys(t *testing.T) {\n"
        + '\t// t.Fatal("never") and require.NoError(t, err)\n'
        + '\ts := "t.Fatal(\\"no\\") assert.Equal(t, 1, 2)"\n'
        + '\traw := `t.Errorf("no") require.True(t, false)`\n'
        + '\t/* t.Error("no") */\n'
        + "\t_, _ = s, raw\n"
        + "}\n"
    )
    assert _go_checks(source) == [("TestDecoys", False)]


def test_go_subtest_without_check_is_flagged_by_its_own_name() -> None:
    source = (
        GO_HEADER
        + "func TestParent(t *testing.T) {\n"
        + '\tt.Run("checked", func(t *testing.T) {\n'
        + "\t\trequire.NoError(t, nil)\n"
        + "\t})\n"
        + '\tt.Run("unchecked", func(t *testing.T) {\n'
        + '\t\tt.Log("no result")\n'
        + "\t})\n"
        + "}\n"
    )
    assert _go_checks(source) == [
        ("TestParent", True),
        ("TestParent/checked", True),
        ("TestParent/unchecked", False),
    ]


def test_go_nested_subtest_names_and_repeats_are_deterministic() -> None:
    source = (
        GO_HEADER
        + "func TestNested(t *testing.T) {\n"
        + '\tt.Run("outer", func(t *testing.T) {\n'
        + '\t\tt.Run("inner", func(t *testing.T) {\n'
        + '\t\t\tt.Fatal("stop")\n'
        + "\t\t})\n"
        + "\t})\n"
        + '\tt.Run("outer", func(t *testing.T) {\n'
        + '\t\tt.Log("no result")\n'
        + "\t})\n"
        + "}\n"
    )
    assert _go_checks(source) == [
        ("TestNested", True),
        ("TestNested/outer", True),
        ("TestNested/outer/inner", True),
        ("TestNested/outer#2", False),
    ]


def test_go_strip_keeps_offsets_and_newlines() -> None:
    text = 'a // x\nb "y\\"z" /* c\nd */ e `r\nq` f'
    stripped = census.strip_go(text)
    assert len(stripped) == len(text)
    assert stripped.count("\n") == text.count("\n")
    assert "x" not in stripped and "y" not in stripped and "c" not in stripped
    assert "a" in stripped and "e" in stripped and "f" in stripped


# ---------------------------------------------------------------------------
# Go positive controls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "require.NoError(t, err)",
        "assert.Equal(t, 1, value)",
        't.Errorf("bad %d", value)',
        't.Error("bad")',
        't.Fatal("bad")',
        't.Fatalf("bad %d", value)',
        "t.Fail()",
        "t.FailNow()",
        "assertWidget(t, value)",
        "expectWidget(t, value)",
        "checkWidget(t, value)",
        "verifyWidget(t, value)",
        "requireWidget(t, value)",
    ],
)
def test_go_real_result_checks_are_detected(statement: str) -> None:
    source = (
        GO_HEADER
        + f"func TestChecked(t *testing.T) {{\n\tvalue := 1\n\terr := error(nil)\n\t{statement}\n\t_ = err\n}}\n"
    )
    assert _go_checks(source) == [("TestChecked", True)]


def test_go_check_helper_must_take_t() -> None:
    source = GO_HEADER + "func TestNoT(t *testing.T) {\n\tassertWidget(1)\n}\n"
    assert _go_checks(source) == [("TestNoT", False)]


def test_go_fixture_file_outside_scan_roots_is_ignored(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        go={
            "other/sample_test.go": GO_HEADER + "func TestElsewhere(t *testing.T) {}\n"
        },
    )
    assert code == 0
    assert report["totals"]["blocks"] == 0


# ---------------------------------------------------------------------------
# Whole-census behaviour: allowlist, stale and unknown entries, determinism
# ---------------------------------------------------------------------------


def test_census_passes_for_positive_controls_only(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        python={
            "tests/test_good.py": "def test_good():\n    assert 1 == 1\n",
        },
        go={
            "services/svc/good_test.go": GO_HEADER
            + "func TestGood(t *testing.T) {\n\trequire.True(t, true)\n}\n",
        },
    )
    assert code == 0
    assert report["resultless"] == []
    assert report["totals"] == {
        "files": 2,
        "blocks": 2,
        "with_result_check": 2,
        "resultless": 0,
    }


def test_unlisted_resultless_blocks_fail_and_are_sorted(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        python={
            "tests/test_b.py": "def test_b():\n    assert True\n",
            "tests/test_a.py": "def test_a():\n    pass\n",
        },
        go={
            "services/svc/x_test.go": GO_HEADER
            + "func TestX(t *testing.T) {\n\tt.Log(1)\n}\n",
        },
    )
    assert code == 1
    assert report["resultless"] == [
        "services/svc/x_test.go::TestX",
        "tests/test_a.py::test_a",
        "tests/test_b.py::test_b",
    ]
    assert report["unlisted"] == report["resultless"]
    assert report["languages"]["python"]["resultless"] == 2
    assert report["languages"]["go"]["resultless"] == 1


def test_reviewed_allowlist_entry_passes(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        python={"tests/test_b.py": "def test_b():\n    pass\n"},
        allowlist={
            "schema_version": 1,
            "entries": [
                {
                    "path": "tests/test_b.py",
                    "name": "test_b",
                    "reason": "control: allowlisted resultless block",
                }
            ],
        },
    )
    assert code == 0
    assert report["allowlisted"] == ["tests/test_b.py::test_b"]
    assert report["unlisted"] == []
    assert report["stale_allowlist"] == []


def test_stale_allowlist_entry_fails(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        python={"tests/test_ok.py": "def test_ok():\n    assert 2 == 2\n"},
        allowlist={
            "schema_version": 1,
            "entries": [
                {
                    "path": "tests/test_ok.py",
                    "name": "test_ok",
                    "reason": "no longer resultless",
                }
            ],
        },
    )
    assert code == 1
    assert report["stale_allowlist"] == ["tests/test_ok.py::test_ok"]


def test_unknown_allowlist_entry_fails(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        python={"tests/test_ok.py": "def test_ok():\n    assert 2 == 2\n"},
        allowlist={
            "schema_version": 1,
            "entries": [
                {
                    "path": "tests/missing.py",
                    "name": "test_gone",
                    "reason": "file was removed",
                }
            ],
        },
    )
    assert code == 1
    assert report["stale_allowlist"] == ["tests/missing.py::test_gone"]


@pytest.mark.parametrize(
    "allowlist",
    [
        "{not json",
        {"schema_version": 1},
        {"schema_version": 1, "entries": ["tests/test_b.py::test_b"]},
        {
            "schema_version": 1,
            "entries": [{"path": "tests/test_b.py", "name": "test_b"}],
        },
        {
            "schema_version": 1,
            "entries": [
                {"path": "tests/test_b.py", "name": "test_b", "reason": "a"},
                {"path": "tests/test_b.py", "name": "test_b", "reason": "b"},
            ],
        },
    ],
)
def test_malformed_allowlist_is_rejected(tmp_path: Path, allowlist: object) -> None:
    _write(tmp_path, "tests/test_b.py", "def test_b():\n    pass\n")
    allow_path = tmp_path / "quality" / "allowlist.json"
    _write(
        tmp_path,
        "quality/allowlist.json",
        allowlist if isinstance(allowlist, str) else json.dumps(allowlist),
    )
    assert census.main(["--root", str(tmp_path), "--allowlist", str(allow_path)]) == 1


def test_unparsable_python_file_fails_closed(tmp_path: Path) -> None:
    code, report = _run(tmp_path, python={"tests/test_broken.py": "def test_x(:\n"})
    assert code == 1
    assert len(report["errors"]) == 1
    assert report["errors"][0].startswith("tests/test_broken.py:")


def test_output_is_deterministic(tmp_path: Path) -> None:
    python = {
        "tests/test_z.py": "def test_z():\n    pass\n",
        "tests/sub/test_a.py": "def test_a():\n    assert True\n",
    }
    go = {"gen/x/y_test.go": GO_HEADER + "func TestY(t *testing.T) {}\n"}
    _, first = _run(tmp_path / "one", python=python, go=go)
    _, second = _run(tmp_path / "two", python=python, go=go)
    assert first == second
    text_one = (tmp_path / "one" / "out" / "census.json").read_bytes()
    text_two = (tmp_path / "two" / "out" / "census.json").read_bytes()
    assert text_one == text_two
    assert b"timestamp" not in text_one


# ---------------------------------------------------------------------------
# Same-file helper resolution (Python and Go)
# ---------------------------------------------------------------------------


def test_python_same_file_helper_with_a_check_passes() -> None:
    source = (
        "def reject_value(value):\n"
        "    assert value != 0\n"
        "\n"
        "def test_uses_helper():\n"
        "    reject_value(5)\n"
    )
    assert _python_checks(source) == [("test_uses_helper", True)]


def test_python_same_named_helper_without_check_still_flags() -> None:
    # Two definitions share the helper's name; one of them checks nothing, so the call
    # does not prove a result and the block stays resultless.
    source = (
        "def probe(value):\n"
        "    assert value != 0\n"
        "\n"
        "class Other:\n"
        "    def probe(self, value):\n"
        "        return value\n"
        "\n"
        "def test_calls_probe():\n"
        "    probe(5)\n"
    )
    assert _python_checks(source) == [("test_calls_probe", False)]


def test_python_helper_without_any_check_flags() -> None:
    source = (
        "def probe(value):\n    return value\n\ndef test_calls_probe():\n    probe(5)\n"
    )
    assert _python_checks(source) == [("test_calls_probe", False)]


def test_python_transitive_helper_passes() -> None:
    source = (
        "def inner_step(value):\n"
        "    assert value == 1\n"
        "\n"
        "def outer_step(value):\n"
        "    inner_step(value)\n"
        "\n"
        "def test_transitive():\n"
        "    outer_step(1)\n"
    )
    assert _python_checks(source) == [("test_transitive", True)]


def test_python_cycle_terminates_and_flags_without_a_check() -> None:
    source = (
        "def ping(value):\n"
        "    pong(value)\n"
        "\n"
        "def pong(value):\n"
        "    ping(value)\n"
        "\n"
        "def test_cycle():\n"
        "    ping(1)\n"
    )
    assert _python_checks(source) == [("test_cycle", False)]


def test_python_cycle_with_a_check_passes() -> None:
    source = (
        "def ping(value):\n"
        "    pong(value)\n"
        "    assert value == 1\n"
        "\n"
        "def pong(value):\n"
        "    ping(value)\n"
        "\n"
        "def test_cycle_checked():\n"
        "    ping(1)\n"
    )
    assert _python_checks(source) == [("test_cycle_checked", True)]


def test_python_method_helper_through_self_passes() -> None:
    source = (
        "class Suite:\n"
        "    def reject(self, value):\n"
        "        assert value is not None\n"
        "\n"
        "    def test_method(self):\n"
        "        self.reject(1)\n"
    )
    assert _python_checks(source) == [("Suite.test_method", True)]


def test_python_fixture_with_a_check_passes_when_requested() -> None:
    source = (
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def widget():\n"
        "    value = 1\n"
        "    assert value == 1\n"
        "    return value\n"
        "\n"
        "def test_uses_fixture(widget):\n"
        "    print(widget)\n"
    )
    assert _python_checks(source) == [("test_uses_fixture", True)]


def test_python_fixture_without_a_check_still_flags() -> None:
    source = (
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def plain():\n"
        "    return 1\n"
        "\n"
        "def test_uses_plain(plain):\n"
        "    print(plain)\n"
    )
    assert _python_checks(source) == [("test_uses_plain", False)]


def test_python_parameter_matching_a_plain_checking_function_is_not_a_fixture() -> None:
    # A parameter only resolves to a fixture; an ordinary function of the same name
    # that happens to check is not an injected dependency and does not count.
    source = (
        "def helper_arg():\n"
        "    assert True is not None\n"
        "\n"
        "def test_param(helper_arg):\n"
        "    print(helper_arg)\n"
    )
    assert _python_checks(source) == [("test_param", False)]


GO_HELPER_HEADER = 'package sample\n\nimport (\n\t"testing"\n\n\t"github.com/stretchr/testify/require"\n)\n\n'


def test_go_same_file_helper_with_a_check_passes() -> None:
    source = (
        GO_HELPER_HEADER
        + "func rejectRun(t *testing.T, value int) {\n\trequire.NotZero(t, value)\n}\n\n"
        + "func TestUsesHelper(t *testing.T) {\n\trejectRun(t, 5)\n}\n"
    )
    assert _go_checks(source) == [("TestUsesHelper", True)]


def test_go_same_file_helper_without_check_still_flags() -> None:
    source = (
        GO_HELPER_HEADER
        + 'func probeRun(t *testing.T) {\n\tt.Log("observed")\n}\n\n'
        + "func TestCallsProbe(t *testing.T) {\n\tprobeRun(t)\n}\n"
    )
    assert dict(_go_checks(source))["TestCallsProbe"] is False


def test_go_transitive_helper_passes() -> None:
    source = (
        GO_HELPER_HEADER
        + "func innerRun(t *testing.T) {\n\trequire.True(t, true)\n}\n\n"
        + "func outerRun(t *testing.T) {\n\tinnerRun(t)\n}\n\n"
        + "func TestTransitive(t *testing.T) {\n\touterRun(t)\n}\n"
    )
    assert dict(_go_checks(source))["TestTransitive"] is True


def test_go_cycle_terminates_and_flags_without_a_check() -> None:
    source = (
        GO_HELPER_HEADER
        + "func pingRun(t *testing.T) {\n\tpongRun(t)\n}\n\n"
        + "func pongRun(t *testing.T) {\n\tpingRun(t)\n}\n\n"
        + "func TestCycle(t *testing.T) {\n\tpingRun(t)\n}\n"
    )
    assert dict(_go_checks(source))["TestCycle"] is False


def test_go_helper_check_inside_a_subtest_resolves() -> None:
    source = (
        GO_HELPER_HEADER
        + "func rejectRun(t *testing.T) {\n\trequire.True(t, true)\n}\n\n"
        + "func TestSubtestHelper(t *testing.T) {\n"
        + '\tt.Run("uses helper", func(t *testing.T) {\n'
        + "\t\trejectRun(t)\n"
        + "\t})\n"
        + "}\n"
    )
    checks = dict(_go_checks(source))
    assert checks["TestSubtestHelper/uses helper"] is True


def test_python_external_validate_response_counts_as_a_check() -> None:
    source = (
        "def test_schema_case(case):\n"
        "    response = case.call()\n"
        "    case.validate_response(response, checks=[])\n"
    )
    assert _python_checks(source) == [("test_schema_case", True)]


def test_python_similar_external_method_name_does_not_count() -> None:
    source = (
        "def test_schema_case(case):\n"
        "    response = case.call()\n"
        "    case.validate_other(response, checks=[])\n"
        "    case.validate_response_later(response)\n"
    )
    assert _python_checks(source) == [("test_schema_case", False)]


def test_python_fixture_named_like_a_test_is_not_a_block() -> None:
    source = (
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "async def test_user(db_session):\n"
        "    return db_session\n"
    )
    assert _python_checks(source) == []


def test_repository_has_no_unreviewed_resultless_test_block(tmp_path: Path) -> None:
    """AUD-428: a new test without a result check fails here, not in a later audit."""
    report = tmp_path / "census.json"

    assert census.main(["--output", str(report)]) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["schema_version"] == 1


@pytest.mark.parametrize("name", census.HELPER_PREFIXES)
@pytest.mark.parametrize("checked", [False, True])
def test_python_known_prefixed_helper_requires_body_check(
    name: str, checked: bool
) -> None:
    body = "assert value == 5" if checked else "return value"
    source = f"def {name}_ready(value):\n    {body}\n\ndef test_calls():\n    {name}_ready(5)\n"
    assert _python_checks(source) == [("test_calls", checked)]


@pytest.mark.parametrize("name", ["assert", "require", "expect", "check", "verify"])
@pytest.mark.parametrize("checked", [False, True])
def test_go_known_prefixed_helper_requires_body_check(name: str, checked: bool) -> None:
    body = 'if value != 5 { t.Fatal("bad") }' if checked else 't.Log("nothing")'
    source = (
        GO_HEADER
        + f"func {name}Ready(t *testing.T, value int) {{ {body} }}\nfunc TestCalls(t *testing.T) {{ {name}Ready(t, 5) }}\n"
    )
    assert _go_checks(source) == [("TestCalls", checked)]


@pytest.mark.parametrize("checked", [False, True])
def test_python_known_prefixed_method_requires_body_check(checked: bool) -> None:
    body = "assert value == 5" if checked else "return value"
    source = f"class Suite:\n    def assert_ready(self, value):\n        {body}\n    def test_calls(self):\n        self.assert_ready(5)\n"
    assert _python_checks(source) == [("Suite.test_calls", checked)]


def test_python_explicit_assertion_failure_is_a_check() -> None:
    source = 'def test_value(value):\n    if value != 5:\n        raise AssertionError("unexpected result")\n'
    assert _python_checks(source) == [("test_value", True)]


@pytest.mark.parametrize("checked", [False, True])
def test_python_prefixed_helper_cycle_requires_real_check(checked: bool) -> None:
    check = "\n    assert value == 5" if checked else ""
    source = f"def assert_first(value):\n    assert_second(value){check}\ndef assert_second(value):\n    assert_first(value)\ndef test_calls():\n    assert_first(5)\n"
    assert _python_checks(source) == [("test_calls", checked)]


@pytest.mark.parametrize("checked", [False, True])
def test_go_prefixed_helper_cycle_requires_real_check(checked: bool) -> None:
    check = '; if value != 5 { t.Fatal("bad") }' if checked else ""
    source = (
        GO_HEADER
        + f"func checkFirst(t *testing.T, value int) {{{check.lstrip(';')} ; if value > 0 {{ checkSecond(t, value - 1) }} }}\nfunc checkSecond(t *testing.T, value int) {{ if value > 0 {{ checkFirst(t, value - 1) }} }}\nfunc TestCalls(t *testing.T) {{ checkFirst(t, 5) }}\n"
    )
    assert _go_checks(source) == [("TestCalls", checked)]


@pytest.mark.parametrize("api", ["raises(ValueError)", "warns(UserWarning)"])
@pytest.mark.parametrize(
    "body",
    [
        "{call}",
        "pending = {call}",
        "pending = {call}\n    pending = other\n    with pending:\n        pass",
        "if enabled:\n        pending = {call}\n    with pending:\n        pass",
        "pending = {call}\n    if enabled:\n        pending = other\n    with pending:\n        pass",
        "with pending:\n        pass\n    pending = {call}",
    ],
)
def test_python_unused_pytest_context_is_not_a_check(api: str, body: str) -> None:
    source = (
        "import pytest\ndef test_context():\n    "
        + body.format(call="pytest." + api)
        + "\n"
    )
    assert _python_checks(source) == [("test_context", False)]


@pytest.mark.parametrize(
    "imports,call",
    [
        ("import pytest", "pytest.raises(ValueError)"),
        ("import pytest as pt", "pt.raises(ValueError)"),
        ("from pytest import raises as require_error", "require_error(ValueError)"),
        ("from pytest import warns as assert_warning", "assert_warning(UserWarning)"),
    ],
)
@pytest.mark.parametrize("entered", [False, True])
def test_python_context_alias_preserves_consumption(
    imports: str, call: str, entered: bool
) -> None:
    body = f"pending = {call}"
    if entered:
        body += "\n    with pending:\n        operation()"
    assert _python_checks(f"{imports}\ndef test_context():\n    {body}\n") == [
        ("test_context", entered)
    ]


@pytest.mark.parametrize(
    "body",
    [
        "with pytest.raises(ValueError):\n        operation()",
        "with pytest.warns(UserWarning):\n        operation()",
        "with pytest.warns():\n        operation()",
        "pytest.raises(ValueError, operation)",
        "pytest.warns(UserWarning, operation)",
        'pytest.fail("unexpected outcome")',
        "pending = pytest.raises(ValueError)\n    with pending:\n        operation()",
    ],
)
def test_python_consumed_expectation_remains_a_check(body: str) -> None:
    assert _python_checks(f"import pytest\ndef test_context():\n    {body}\n") == [
        ("test_context", True)
    ]


@pytest.mark.parametrize(
    "body",
    [
        "pytest.raises()",
        "pytest.raises(ValueError, None)",
        "pytest.warns(UserWarning, None)",
        "with pytest.raises():\n        operation()",
    ],
)
def test_python_malformed_expectation_is_not_a_check(body: str) -> None:
    assert _python_checks(f"import pytest\ndef test_context():\n    {body}\n") == [
        ("test_context", False)
    ]


@pytest.mark.parametrize(
    "body",
    [
        "pending = pytest.raises(ValueError)\n    other = pytest.raises((pending := TypeError))\n    with pending:\n        operation()",
        "pending = pytest.raises(ValueError) if enabled else other\n    with pending:\n        operation()",
        "pending = pytest.raises(ValueError)\n    operation()\n    with pending:\n        operation()",
        "pending = pytest.raises(ValueError)\n    def helper():\n        with pending:\n            operation()",
    ],
)
def test_python_stored_context_outside_proven_binding_scope_is_not_claimed(
    body: str,
) -> None:
    assert _python_checks(f"import pytest\ndef test_context():\n    {body}\n") == [
        ("test_context", False)
    ]


def test_python_unresolved_starred_context_arguments_are_not_claimed() -> None:
    source = "import pytest\ndef test_context(args):\n    with pytest.raises(*args):\n        operation()\n"
    assert _python_checks(source) == [("test_context", False)]


@pytest.mark.parametrize(
    "body",
    [
        "_ = require.Equal",
        "other := func(_ int, _ any) func(*testing.T, int, int) { return func(*testing.T, int, int) {} }; other(0, require.Equal)(t, 2, 2)",
        "_ = assert.AnError",
        "_ = require.Equal /* no invocation */",
        "_ = require.Equal // no invocation\n",
        "_ = (require.Equal)",
        "_ = ((require.Equal))",
        "other := func(_ any) func(*testing.T, int, int) { return func(*testing.T, int, int) {} }; other(require.Equal)(t, 2, 2)",
        "other := func(_ any) func(*testing.T, int, int) { return func(*testing.T, int, int) {} }; other((require.Equal))(t, 2, 2)",
    ],
)
def test_go_assertion_member_reference_is_not_a_check(body: str) -> None:
    source = GO_HEADER + f"func TestReference(t *testing.T) {{ {body} }}\n"
    assert _go_checks(source) == [("TestReference", False)]


@pytest.mark.parametrize(
    "call",
    [
        "require.Equal(t, 2, got)",
        "require.Equal(\n t, 2, got,\n)",
        "require.Equal /* invoke */ (t, 2, got)",
        "require.\n Equal(t, 2, got)",
        "(require.Equal)(t, 2, got)",
        "((require.Equal))(t, 2, got)",
        "( require.Equal /* invoke */ )(t, 2, got)",
        'if (assert.Equal)(t, 2, got) { t.Log("checked") }',
        'if\n(assert.Equal)(t, 2, got) { t.Log("checked") }',
    ],
)
def test_go_assertion_call_syntax_remains_a_check(call: str) -> None:
    source = GO_HEADER + f"func TestCalled(t *testing.T) {{ got := 1 + 1; {call} }}\n"
    assert _go_checks(source) == [("TestCalled", True)]


def test_go_reference_only_file_fails_real_census_cli(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        go={
            "services/sample/result_test.go": GO_HEADER
            + "func TestReference(t *testing.T) { _ = require.Equal /* not invoked */ }\n"
        },
    )
    assert code == 1
    assert report["unlisted"] == ["services/sample/result_test.go::TestReference"]
    assert report["errors"] == []


@pytest.mark.parametrize(
    "body",
    [
        "got := 1 + 1\n(require.Equal)(t, 2, got)",
        't.Log("ready")\n(require.Equal)(t, 2, 1 + 1)',
        "got := 1 + 1 /* new statement\n */ (require.Equal)(t, 2, got)",
        "got := 1 + 1 // new statement\n((require.Equal))(t, 2, got)",
    ],
)
def test_go_parenthesized_assertion_after_automatic_semicolon_is_a_check(
    body: str,
) -> None:
    assert _go_checks(GO_HEADER + f"func TestCalled(t *testing.T) {{ {body} }}\n") == [
        ("TestCalled", True)
    ]


@pytest.mark.parametrize(
    "argument", ["require.Equal", "(require.Equal)", "((require.Equal))"]
)
def test_go_literal_function_discarding_assertion_reference_is_not_a_check(
    argument: str,
) -> None:
    body = f"func(_ any) func(*testing.T, int, int) {{ return func(*testing.T, int, int) {{}} }}({argument})(t, 2, 2)"
    assert _go_checks(
        GO_HEADER + f"func TestReference(t *testing.T) {{ {body} }}\n"
    ) == [("TestReference", False)]


@pytest.mark.parametrize(
    "argument", ["require.Equal", "(require.Equal)", "((require.Equal))"]
)
def test_go_multiline_literal_callee_does_not_create_a_semicolon_boundary(
    argument: str,
) -> None:
    body = f"func(_ any) func(*testing.T, int, int) {{\n return func(*testing.T, int, int) {{}}\n}}({argument})(t, 2, 2)"
    assert _go_checks(
        GO_HEADER + f"func TestReference(t *testing.T) {{ {body} }}\n"
    ) == [("TestReference", False)]


@pytest.mark.parametrize(
    "body",
    [
        "_ = require.Equal\n(func() {})()",
        "_ = (require.Equal)\n(func() {})()",
        "_ = ((require.Equal))\n(func() {})()",
        "_ = require.Equal // reference only\n(func() {})()",
        "_ = require.Equal /* reference only\n */ (func() {})()",
        "_ = (require.Equal) /* reference only\n */ (func() {})()",
        "_ = require.Equal; (func() {})()",
        "_ = (require.Equal); (func() {})()",
    ],
)
def test_go_reference_then_unrelated_iife_is_not_an_assertion_call(body: str) -> None:
    assert _go_checks(
        GO_HEADER + f"func TestReference(t *testing.T) {{ {body} }}\n"
    ) == [("TestReference", False)]
