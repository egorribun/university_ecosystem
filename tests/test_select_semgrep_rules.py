"""Unit tests for the deterministic Semgrep security rule selection (AUD-380)."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.quality import select_semgrep_rules as selector


def _rule(rule_id: str, **metadata: Any) -> dict[str, Any]:
    return {
        "id": rule_id,
        "message": "m",
        "languages": ["python"],
        "metadata": metadata,
    }


def _write_rules(root: Path, relative: str, rules: list[Any]) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"rules": rules}, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def _tree(tmp_path: Path) -> Path:
    """Build a rules root with one rule per selection branch."""

    root = tmp_path / "rules"
    for directory in selector.DEFAULT_DIRECTORIES:
        (root / directory).mkdir(parents=True)
    _write_rules(
        root,
        "python/a.yaml",
        [
            _rule("py.vuln", category="security", subcategory=["vuln"]),
            _rule("py.guard", category="security", subcategory=["guardrail"]),
            _rule("py.audit", category="security", subcategory=["audit"]),
            _rule("py.unset", category="security"),
            _rule("py.style", category="best-practice"),
        ],
    )
    _write_rules(
        root, "go/b.yaml", [_rule("go.str", category="security", subcategory="vuln")]
    )
    _write_rules(
        root, "generic/secrets/c.yaml", [_rule("secret.any", category="security")]
    )
    return root


# Rule file discovery -----------------------------------------------------------


def test_rule_files_skip_tests_and_non_yaml_and_are_sorted(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "python" / "z.test.yaml").write_text("rules: []\n", encoding="utf-8")
    (root / "python" / "notes.txt").write_text("x", encoding="utf-8")
    (root / "python" / "sub").mkdir()
    (root / "python" / "sub" / "d.yml").write_text(
        json.dumps({"rules": []}), encoding="utf-8"
    )
    files = selector._rule_files(root, selector.DEFAULT_DIRECTORIES)
    names = [path.relative_to(root).as_posix() for path in files]
    assert "python/z.test.yaml" not in names
    assert "python/notes.txt" not in names
    assert "python/sub/d.yml" in names
    assert names == sorted(names)


def test_rule_files_fail_when_a_directory_is_missing(tmp_path: Path) -> None:
    with pytest.raises(selector.SelectionError, match="rule directory is missing"):
        selector._rule_files(tmp_path, ("absent",))


# Rule parsing ------------------------------------------------------------------


def test_rules_in_rejects_unparseable_yaml(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("rules: [\n", encoding="utf-8")
    with pytest.raises(selector.SelectionError, match="cannot parse rule file"):
        selector._rules_in(path)


def test_rules_in_rejects_binary_content(tmp_path: Path) -> None:
    path = tmp_path / "binary.yaml"
    path.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(selector.SelectionError, match="cannot parse rule file"):
        selector._rules_in(path)


def test_rules_in_rejects_an_unreadable_path(tmp_path: Path) -> None:
    with pytest.raises(selector.SelectionError, match="cannot parse rule file"):
        selector._rules_in(tmp_path)


@pytest.mark.parametrize("content", ["- just\n- a list\n", "rules: 3\n"])
def test_rules_in_skips_or_rejects_non_rule_documents(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "doc.yaml"
    path.write_text(content, encoding="utf-8")
    if content.startswith("- "):
        assert selector._rules_in(path) == []
    else:
        with pytest.raises(selector.SelectionError, match="rules is not a list"):
            selector._rules_in(path)


def test_rules_in_skips_yaml_without_a_rules_key(tmp_path: Path) -> None:
    path = tmp_path / "other.yaml"
    path.write_text("other: 1\n", encoding="utf-8")
    assert selector._rules_in(path) == []


@pytest.mark.parametrize("rules", ["[1]", "[{message: no id}]", "[{id: 3}]"])
def test_rules_in_rejects_malformed_rules(tmp_path: Path, rules: str) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(f"rules: {rules}\n", encoding="utf-8")
    with pytest.raises(selector.SelectionError, match="malformed rule"):
        selector._rules_in(path)


# Selection predicate -----------------------------------------------------------


def _kept(rule: dict[str, Any]) -> bool:
    return selector._is_kept(rule, Path("python/x.yaml"))


def test_secret_directory_is_not_a_selected_directory() -> None:
    assert "generic/secrets" not in selector.DEFAULT_DIRECTORIES
    assert _kept({"id": "s", "metadata": {"category": "correctness"}}) is False


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"category": "security", "subcategory": ["vuln"]}, True),
        ({"category": "security", "subcategory": ["guardrail"]}, True),
        ({"category": "security"}, True),
        ({"category": "security", "subcategory": "vuln"}, True),
        ({"category": "security", "subcategory": ["audit"]}, False),
        ({"category": "security", "subcategory": "audit"}, False),
        ({"category": "security", "subcategory": ["audit", "vuln"]}, True),
        ({"category": "best-practice"}, False),
        ({}, False),
    ],
)
def test_category_and_subcategory_selection(
    metadata: dict[str, Any], expected: bool
) -> None:
    assert _kept({"id": "r", "metadata": metadata}) is expected


def test_rule_without_metadata_is_not_security() -> None:
    assert _kept({"id": "r"}) is False


def test_non_mapping_metadata_fails_closed() -> None:
    with pytest.raises(selector.SelectionError, match="metadata is not a mapping"):
        _kept({"id": "r", "metadata": ["x"]})


def test_malformed_subcategory_fails_closed() -> None:
    with pytest.raises(selector.SelectionError, match="subcategory is malformed"):
        _kept({"id": "r", "metadata": {"category": "security", "subcategory": 3}})


# Whole selection ---------------------------------------------------------------


def test_select_rules_keeps_the_expected_security_subset(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    rules, kept, dropped = selector.select_rules(root, selector.DEFAULT_DIRECTORIES)
    ids = [rule["id"] for rule in rules]
    assert ids == sorted(ids)
    assert ids == [
        "go.b.go.str",
        "python.a.py.guard",
        "python.a.py.unset",
        "python.a.py.vuln",
    ]
    assert (kept, dropped) == (4, 2)


def test_select_rules_defaults_to_the_reviewed_directories(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert selector.select_rules(root)[1] == 4


def test_select_rules_refuses_an_empty_selection(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    for directory in selector.DEFAULT_DIRECTORIES:
        (root / directory).mkdir(parents=True)
    _write_rules(root, "python/a.yaml", [_rule("py.style", category="best-practice")])
    with pytest.raises(selector.SelectionError, match="selection is empty"):
        selector.select_rules(root)


def test_same_short_id_in_different_files_is_qualified_apart(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    for directory in selector.DEFAULT_DIRECTORIES:
        (root / directory).mkdir(parents=True)
    _write_rules(root, "python/a.yaml", [_rule("dup", category="security")])
    _write_rules(root, "go/b.yaml", [_rule("dup", category="security")])
    ids = [rule["id"] for rule in selector.select_rules(root)[0]]
    assert ids == ["go.b.dup", "python.a.dup"]


def test_duplicate_id_in_one_file_is_refused_even_when_one_copy_is_dropped(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rules"
    for directory in selector.DEFAULT_DIRECTORIES:
        (root / directory).mkdir(parents=True)
    _write_rules(
        root,
        "python/a.yaml",
        [_rule("dup", category="best-practice"), _rule("dup", category="security")],
    )
    with pytest.raises(
        selector.SelectionError, match="duplicate rule id within a file"
    ):
        selector.select_rules(root)


def test_qualified_id_uses_the_dotted_rule_path() -> None:
    root = Path("/rules")
    path = root / "python" / "django" / "security" / "x.yaml"
    assert selector.qualified_id(path, root, "x") == "python.django.security.x.x"


# Rendering and entry point -----------------------------------------------------


def test_render_config_is_deterministic_and_valid_json(tmp_path: Path) -> None:
    rules = [{"id": "a", "when": "2020-01-01"}]
    first = selector.render_config(rules)
    assert first == selector.render_config(rules)
    assert json.loads(first)["rules"][0]["id"] == "a"
    assert first.endswith("\n")


def test_main_writes_the_selected_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path)
    output = tmp_path / "out" / "security-rules.json"
    assert selector.main(["--rules-root", str(root), "--output", str(output)]) == 0
    assert "kept 4 rule(s), dropped 2" in capsys.readouterr().out
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert next(rule["id"] for rule in loaded["rules"]) == "go.b.go.str"


def test_main_returns_one_and_annotates_a_selection_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "security-rules.json"
    status = selector.main(
        ["--rules-root", str(tmp_path / "missing"), "--output", str(output)]
    )
    assert status == 1
    assert "::error::Semgrep rule selection" in capsys.readouterr().out
    assert not output.exists()


def test_script_entry_point_runs_the_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path)
    output = tmp_path / "security-rules.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["select_semgrep_rules.py", "--rules-root", str(root), "--output", str(output)],
    )
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(selector.__file__), run_name="__main__")
    assert exit_info.value.code == 0
    assert output.exists()
