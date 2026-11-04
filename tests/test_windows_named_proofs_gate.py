from __future__ import annotations

import copy
import runpy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from defusedxml.common import DefusedXmlException

from scripts.quality import windows_named_proofs_gate as gate


def document() -> ET.Element:
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        tests=str(len(gate.REQUIRED)),
        skipped="0",
        failures="0",
        errors="0",
    )
    for classname, name in sorted(gate.REQUIRED):
        ET.SubElement(suite, "testcase", classname=classname, name=name)
    return root


def save(tmp_path: Path, root: ET.Element) -> Path:
    path = tmp_path / "windows-proofs.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_extra_passing_case_is_allowed(tmp_path: Path) -> None:
    root = document()
    suite = root[0]
    ET.SubElement(suite, "testcase", classname="other", name="extra")
    suite.set("tests", str(len(suite.findall("testcase"))))
    assert gate.validate(save(tmp_path, root)) == len(gate.REQUIRED) + 1


def test_single_testsuite_root_is_allowed(tmp_path: Path) -> None:
    assert gate.validate(save(tmp_path, document()[0])) == len(gate.REQUIRED)


@pytest.mark.parametrize("missing", sorted(gate.REQUIRED))
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
