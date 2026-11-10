"""Execute the existing integration receipt validator; no database or Docker."""

from __future__ import annotations

from xml.etree import ElementTree

import pytest
from dishka import make_async_container

from tests.fixtures import owned_baseline_postgres as owned
from tests.test_aud360_postgres_cohort_receipt import execute, receipt, validator

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard

GROUP_CLASS = "tests.integration.test_group_list_tenant_http_postgres"
GROUP_CASES = (
    "test_mixed_scope_group_http_a_then_b",
    "test_mixed_scope_group_http_a_then_unscoped[anonymous]",
    "test_mixed_scope_group_http_a_then_unscoped[unsigned-hint]",
    "test_mixed_scope_group_http_a_then_unscoped[bad-signature]",
    "test_mixed_scope_group_http_unscoped_then_a",
    "test_group_http_ignores_legacy_foreign_cache",
    "test_group_http_observes_committed_change[rename]",
    "test_group_http_observes_committed_change[delete]",
    "test_mvp_group_http_anonymous_uses_configured_tenant",
    "test_mvp_group_http_foreign_identity_rejected_before_session",
)


def _receipt():
    source, root = receipt()
    # Independent literal inventory: deriving these names from the validator
    # would allow an omitted requirement to disappear from the positive proof.
    for case in list(root):
        if case.get("classname") == GROUP_CLASS:
            root.remove(case)
    for name in GROUP_CASES:
        ElementTree.SubElement(root, "testcase", classname=GROUP_CLASS, name=name)
    return source, root


def test_group_receipt_adds_ten_cases_without_changing_legacy_cohorts():
    _, expected = validator()
    assert expected[GROUP_CLASS] == GROUP_CASES
    assert (
        sum(
            len(names)
            for classname, names in expected.items()
            if classname != GROUP_CLASS
        )
        == 72
    )
    assert sum(map(len, expected.values())) == 82


def test_complete_group_postgres_receipt_passes(tmp_path, monkeypatch, capsys):
    source, root = _receipt()
    execute(source, root, tmp_path, monkeypatch)
    assert capsys.readouterr().out == "INTEGRATION_POSTGRES_COHORT_VERIFIED_PASS 82\n"


@pytest.mark.parametrize("name", GROUP_CASES)
@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "skipped",
        "failure",
        "error",
        "duplicate",
        "wrong-name",
        "wrong-class",
        "extra-case",
    ],
)
def test_group_receipt_rejects_incomplete_or_unsuccessful_case(
    name, mutation, tmp_path, monkeypatch, capsys
):
    source, root = _receipt()
    target = next(
        case
        for case in root
        if case.get("classname") == GROUP_CLASS and case.get("name") == name
    )
    if mutation == "missing":
        root.remove(target)
    elif mutation in {"skipped", "failure", "error"}:
        ElementTree.SubElement(target, mutation)
    elif mutation == "duplicate":
        ElementTree.SubElement(root, "testcase", classname=GROUP_CLASS, name=name)
    elif mutation == "wrong-name":
        target.set("name", "unreviewed")
    elif mutation == "wrong-class":
        target.set("classname", "tests.integration.unreviewed")
    else:
        ElementTree.SubElement(
            root, "testcase", classname=GROUP_CLASS, name="unreviewed"
        )
    with pytest.raises(
        SystemExit, match="PostgreSQL cohort receipt incomplete or unsuccessful"
    ):
        execute(source, root, tmp_path, monkeypatch)
    assert "VERIFIED_PASS" not in capsys.readouterr().out


def test_group_receipt_same_length_duplicate_cannot_replace_missing_case(
    tmp_path, monkeypatch
):
    source, root = _receipt()
    cases = [case for case in root if case.get("classname") == GROUP_CLASS]
    cases[-1].set("name", cases[-2].get("name"))
    assert len(cases) == 10
    with pytest.raises(SystemExit, match=GROUP_CLASS):
        execute(source, root, tmp_path, monkeypatch)


def test_group_receipt_rejects_absent_cohort(tmp_path, monkeypatch):
    source, root = _receipt()
    for case in list(root):
        if case.get("classname") == GROUP_CLASS:
            root.remove(case)
    with pytest.raises(SystemExit, match=GROUP_CLASS):
        execute(source, root, tmp_path, monkeypatch)


def test_group_receipt_rejects_empty_or_malformed_xml(tmp_path, monkeypatch, capsys):
    import runpy
    import sys

    source, _ = validator()
    script = tmp_path / "validator.py"
    script.write_text(source)
    path = tmp_path / "receipt.xml"
    monkeypatch.setattr(sys, "argv", ["validator", str(path)])
    for payload in ("", "<testsuite>", "not xml"):
        path.write_text(payload)
        with pytest.raises(ElementTree.ParseError):
            runpy.run_path(str(script), run_name="__main__")
    assert "VERIFIED_PASS" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_group_http_provider_graph_constructs_without_opening_a_database():
    from tests.integration.test_group_list_tenant_http_postgres import (
        _Evidence,
        _GroupHTTPProvider,
    )

    def unavailable_factory():
        pytest.fail("Constructing the HTTP provider graph must not open a session")

    evidence = _Evidence()
    container = make_async_container(
        _GroupHTTPProvider(unavailable_factory, "unopened", evidence)
    )
    try:
        assert evidence.opened == 0
    finally:
        await container.close()
