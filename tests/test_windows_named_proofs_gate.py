from __future__ import annotations

import ast
import copy
import runpy
import shlex
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from defusedxml.common import DefusedXmlException

from scripts.quality import windows_named_proofs_gate as gate

ROOT = Path(__file__).resolve().parents[1]

# Independent pin of the named Windows proofs. This literal is the review
# anchor: it must not be derived from gate.REQUIRED, otherwise shrinking the
# gate's set would shrink every fixture built from it.
PINNED_PROOFS = frozenset(
    {
        (
            "tests.test_start_docker_live_owner_key_paths",
            "test_common_git_metadata_rejects_reparse_directory_when_supported",
        ),
        (
            "tests.test_start_docker_live_owner_key_paths",
            "test_worktree_owner_rejects_reparse_common_key_when_supported",
        ),
        (
            "tests.test_start_docker_live_stand_state_root",
            "test_live_stand_uses_system32_acl_tools_when_git_usr_bin_precedes_path",
        ),
        (
            "tests.test_symlink_privilege_probe_contract",
            "test_file_symlink_probe_reports_unprivileged_creation_as_unsupported",
        ),
        (
            "tests.test_symlink_privilege_probe_contract",
            "test_directory_symlink_probe_reports_unprivileged_creation_as_unsupported",
        ),
        (
            "tests.test_symlink_privilege_probe_contract",
            "test_probe_flags_match_the_native_symlink_capability",
        ),
        (
            "tests.test_symlink_privilege_probe_contract",
            "test_every_when_supported_symlink_test_is_probe_gated",
        ),
        (
            "tests.test_symlink_privilege_probe_contract",
            "test_census_detects_an_ungated_when_supported_symlink_test",
        ),
        (
            "tests.test_live_stand_subprocess_timeouts",
            "test_every_live_stand_subprocess_call_declares_a_timeout",
        ),
        (
            "tests.test_live_stand_subprocess_timeouts",
            "test_generic_live_stand_command_timeout_becomes_a_stand_error",
        ),
        (
            "tests.test_live_stand_subprocess_timeouts",
            "test_git_probe_timeout_becomes_a_stand_error",
        ),
        (
            "tests.test_live_stand_subprocess_timeouts",
            "test_playwright_timeout_becomes_a_stand_error",
        ),
        (
            "tests.test_live_stand_subprocess_timeouts",
            "test_native_lifecycle_lock_contends_and_recovers_after_release[worktree]",
        ),
        (
            "tests.test_live_stand_subprocess_timeouts",
            "test_native_lifecycle_lock_contends_and_recovers_after_release[in-place]",
        ),
        (
            "tests.test_live_stand_subprocess_timeouts",
            "test_windows_lifecycle_lock_wait_is_bounded",
        ),
        (
            "tests.test_windows_live_native_subprocess",
            "test_subprocess_timeout_terminates_native_child",
        ),
        (
            "tests.test_windows_live_native_subprocess",
            "test_subprocess_success_completes_native_child",
        ),
    }
)


def _ci_selected_modules() -> set[str]:
    """Modules the Windows CI producer step actually runs, read from ci.yml."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text("utf-8"))
    steps = workflow["jobs"]["windows-live-proofs"]["steps"]
    producer = next(
        step for step in steps if step.get("name") == "Run Windows-only proofs"
    )
    argv = shlex.split(producer["run"].replace("\\\n", " "), comments=True)
    return {
        Path(arg).with_suffix("").as_posix().replace("/", ".")
        for arg in argv
        if arg.startswith("tests/") and arg.endswith(".py")
    }


def _defined_test_functions(module: str) -> set[str]:
    path = ROOT / (module.replace(".", "/") + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assert_pinned(required: frozenset[tuple[str, str]]) -> None:
    missing = sorted(PINNED_PROOFS - required)
    unexpected = sorted(required - PINNED_PROOFS)
    assert not missing, f"named Windows proof missing from gate REQUIRED: {missing}"
    assert not unexpected, f"unpinned Windows proof in gate REQUIRED: {unexpected}"


def document() -> ET.Element:
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        tests=str(len(PINNED_PROOFS)),
        skipped="0",
        failures="0",
        errors="0",
    )
    for classname, name in sorted(PINNED_PROOFS):
        ET.SubElement(suite, "testcase", classname=classname, name=name)
    return root


def test_gate_required_set_matches_the_pinned_ci_proofs() -> None:
    _assert_pinned(gate.REQUIRED)


@pytest.mark.parametrize("dropped", sorted(PINNED_PROOFS))
def test_required_set_missing_one_name_fails_the_pin(
    monkeypatch: pytest.MonkeyPatch, dropped: tuple[str, str]
) -> None:
    monkeypatch.setattr(gate, "REQUIRED", PINNED_PROOFS - {dropped})
    with pytest.raises(AssertionError, match="missing from gate REQUIRED"):
        _assert_pinned(gate.REQUIRED)


def test_pinned_proofs_are_selected_by_the_ci_producer_step() -> None:
    selected = _ci_selected_modules()
    assert {classname for classname, _ in PINNED_PROOFS} <= selected


@pytest.mark.parametrize("pinned", sorted(PINNED_PROOFS))
def test_pinned_proof_names_a_real_test_function(pinned: tuple[str, str]) -> None:
    classname, name = pinned
    assert name.split("[", 1)[0] in _defined_test_functions(classname)


def save(tmp_path: Path, root: ET.Element) -> Path:
    path = tmp_path / "windows-proofs.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_extra_passing_case_is_allowed(tmp_path: Path) -> None:
    root = document()
    suite = root[0]
    ET.SubElement(suite, "testcase", classname="other", name="extra")
    suite.set("tests", str(len(suite.findall("testcase"))))
    assert gate.validate(save(tmp_path, root)) == len(PINNED_PROOFS) + 1


def test_single_testsuite_root_is_allowed(tmp_path: Path) -> None:
    assert gate.validate(save(tmp_path, document()[0])) == len(PINNED_PROOFS)


@pytest.mark.parametrize("missing", sorted(PINNED_PROOFS))
def test_each_required_case_is_individually_required(
    tmp_path: Path, missing: tuple[str, str]
) -> None:
    root = document()
    suite = root[0]
    item = next(
        case for case in suite if (case.get("classname"), case.get("name")) == missing
    )
    suite.remove(item)
    suite.set("tests", str(len(suite.findall("testcase"))))
    with pytest.raises(ValueError, match="named Windows proof is missing"):
        gate.validate(save(tmp_path, root))


@pytest.mark.parametrize("outcome", ["skipped", "failure", "error"])
def test_testcase_nonpass_cannot_hide_behind_zero_counters(
    tmp_path: Path, outcome: str
) -> None:
    root = document()
    ET.SubElement(root[0][0], outcome)
    with pytest.raises(ValueError, match="did not pass"):
        gate.validate(save(tmp_path, root))


@pytest.mark.parametrize("field", ["skipped", "failures", "errors"])
def test_nonzero_aggregate_is_rejected(tmp_path: Path, field: str) -> None:
    root = document()
    root[0].set(field, "1")
    with pytest.raises(ValueError, match="non-passing"):
        gate.validate(save(tmp_path, root))


@pytest.mark.parametrize("value", ["", "-1", "nan", "1.0", " 0", "１２"])
def test_invalid_aggregate_is_rejected(tmp_path: Path, value: str) -> None:
    root = document()
    root[0].set("tests", value)
    with pytest.raises(ValueError, match="invalid JUnit count"):
        gate.validate(save(tmp_path, root))


def test_missing_count_is_rejected(tmp_path: Path) -> None:
    root = document()
    del root[0].attrib["skipped"]
    with pytest.raises(ValueError, match="invalid JUnit count"):
        gate.validate(save(tmp_path, root))


def test_forged_count_is_rejected(tmp_path: Path) -> None:
    root = document()
    root[0].set("tests", "100")
    with pytest.raises(ValueError, match="count mismatch"):
        gate.validate(save(tmp_path, root))


def test_duplicate_case_is_rejected_even_with_matching_counter(tmp_path: Path) -> None:
    root = document()
    root[0].append(copy.deepcopy(root[0][0]))
    root[0].set("tests", str(len(root[0])))
    with pytest.raises(ValueError, match="duplicate testcase"):
        gate.validate(save(tmp_path, root))


def test_empty_identity_is_rejected(tmp_path: Path) -> None:
    root = document()
    root[0][0].set("classname", "")
    with pytest.raises(ValueError, match="missing or duplicate"):
        gate.validate(save(tmp_path, root))


def test_non_suite_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid JUnit root"):
        gate.validate(save(tmp_path, ET.Element("unknown")))


def test_invalid_suite_child_is_rejected(tmp_path: Path) -> None:
    root = document()
    ET.SubElement(root[0], "testsuite")
    with pytest.raises(ValueError, match="invalid JUnit suite child"):
        gate.validate(save(tmp_path, root))


def test_missing_file_and_malformed_xml_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(OSError):
        gate.validate(tmp_path / "missing.xml")
    invalid = tmp_path / "bad.xml"
    invalid.write_text("<testsuites>", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        gate.validate(invalid)
    monkeypatch.setattr(sys, "argv", ["windows_named_proofs_gate.py", str(invalid)])
    assert gate.main() == 1


def test_xml_entity_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = tmp_path / "entity.xml"
    invalid.write_text(
        '<!DOCTYPE a [<!ENTITY x "bad">]><testsuites>&x;</testsuites>',
        encoding="utf-8",
    )
    with pytest.raises(DefusedXmlException):
        gate.validate(invalid)
    monkeypatch.setattr(sys, "argv", ["windows_named_proofs_gate.py", str(invalid)])
    assert gate.main() == 1


def test_cli_requires_one_path_and_accepts_a_valid_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["windows_named_proofs_gate.py"])
    assert gate.main() == 1
    report = save(tmp_path, document())
    monkeypatch.setattr(sys, "argv", ["windows_named_proofs_gate.py", str(report)])
    assert gate.main() == 0


def test_script_entrypoint_accepts_valid_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = save(tmp_path, document())
    monkeypatch.setattr(sys, "argv", [str(gate.__file__), str(report)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(gate.__file__), run_name="__main__")
    assert result.value.code == 0
