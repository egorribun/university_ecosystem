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


@pytest.mark.asyncio
async def test_group_http_provider_resolves_production_service_per_request(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.config import settings
    from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
    from app.repositories.schedule_repository import GroupRepository
    from app.services.group_service import GroupService
    from tests.integration.test_group_list_tenant_http_postgres import (
        _Evidence,
        _GroupHTTPProvider,
    )

    # Only the PostgreSQL probe results are simulated. Resolve the actual HTTP
    # provider, production session generator, service and repository through
    # Dishka's compiled factory, which graph construction alone does not call.
    monkeypatch.setattr(settings, "mvp_tenant_id", None)
    sessions = []

    def session_factory():
        session = AsyncSession()
        role = ("reader", "reader", False, False, False, False, False, False, False)
        boundary = (
            True,
            True,
            True,
            False,
            True,
            False,
            False,
            False,
            False,
            False,
            42,
            "",
        )
        session.execute = AsyncMock(
            side_effect=[Mock(one=Mock(return_value=row)) for row in (role, boundary)]
        )
        session.close = AsyncMock(wraps=session.close)
        sessions.append(session)
        return session

    evidence = _Evidence()
    container = make_async_container(
        _GroupHTTPProvider(session_factory, "reader", evidence)
    )
    tenant_token = tenant_id_ctx.set("")
    bypass_token = bypass_rls_ctx.set(False)
    services = []
    try:
        for _ in range(2):
            async with container() as request:
                service = await request.get(GroupService)
                services.append(service)
                assert type(service) is GroupService
                assert type(service.repo) is GroupRepository
                assert service.db is service.repo.db is sessions[-1]
                assert await request.get(GroupService) is service
                sessions[-1].close.assert_not_awaited()
            sessions[-1].close.assert_awaited_once()
            assert sessions[-1].execute.await_count == 2
        assert services[0] is not services[1]
        assert sessions[0] is not sessions[1]
        assert evidence.opened == 2
        assert evidence.sessions == sessions
    finally:
        await container.close()
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
