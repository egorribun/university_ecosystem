"""Execute the real CI receipt validator against the expanded tenant cohort."""

import ast
import runpy
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/ci/backend-run-integration-tests.ps1"
TENANT_CLASS = "tests.integration.test_aud277_360_450_tenant_rls_postgres"
PREVIOUS_TENANT_CASES = (
    "test_no_permissive_true_policy_remains_on_core_tables",
    "test_tenant_session_sees_only_its_rows_and_never_null_rows",
    "test_guc_bypass_cannot_expose_other_tenants_or_null_rows",
    "test_dedicated_bypass_role_member_sees_every_row",
    "test_ordinary_writes_are_stamped_with_the_session_tenant",
    "test_news_service_producer_is_stamped_and_rls_scoped",
    "test_writes_cannot_target_another_tenant_or_escape_the_session",
    "test_messages_need_both_participation_and_the_session_tenant",
    "test_every_tenant_table_forces_rls_and_stamps_unowned_inserts",
    "test_notification_producer_rows_are_owned_by_the_session_tenant",
    "test_worker_bypass_producer_must_write_its_tenant_explicitly",
    "test_bypass_scheduler_persists_owned_reminders_and_outbox_events",
    "test_transaction_local_bypass_guc_is_cleared_by_rollback_on_same_backend",
    "test_permissive_true_causality_depends_on_restrictive_tenant_policy",
)
MFA_CASES = (
    "test_mfa_reset_real_producer_uses_target_owner_under_bypass[True-]",
    "test_mfa_reset_real_producer_uses_target_owner_under_bypass[True-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb]",
    "test_mfa_reset_real_producer_uses_target_owner_under_bypass[False-]",
    "test_mfa_reset_real_producer_uses_target_owner_under_bypass[False-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb]",
)


ADMIN_CASES = (
    "test_create_admin_real_producer_scopes_create_and_reset[empty]",
    "test_create_admin_real_producer_scopes_create_and_reset[foreign]",
    "test_create_admin_real_producer_rejects_foreign_email[foreign]",
    "test_create_admin_real_producer_rejects_foreign_email[null]",
    "test_create_admin_real_producer_requires_active_tenant[missing]",
    "test_create_admin_real_producer_requires_active_tenant[inactive]",
    "test_create_admin_real_producer_rejects_unconfigured_tenant",
)


WEEKLY_CASES = (
    "test_weekly_cleanup_preserves_rls_hidden_subscriptions[normal-empty]",
    "test_weekly_cleanup_preserves_rls_hidden_subscriptions[normal-a]",
    "test_weekly_cleanup_preserves_rls_hidden_subscriptions[normal-b]",
    "test_weekly_cleanup_preserves_rls_hidden_subscriptions[python-bypass-empty]",
    "test_weekly_cleanup_preserves_rls_hidden_subscriptions[python-bypass-a]",
    "test_weekly_cleanup_preserves_rls_hidden_subscriptions[python-bypass-b]",
    "test_weekly_cleanup_schema_drift_rejects_before_stale_delete[missing-fk]",
    "test_weekly_cleanup_schema_drift_rejects_before_stale_delete[shadow-child]",
    "test_weekly_cleanup_schema_drift_rejects_before_stale_delete[shadow-parent]",
)


SCHEDULE_CASES = (
    "test_schedule_service_parent_ownership[create-a]",
    "test_schedule_service_parent_ownership[create-b]",
    "test_schedule_service_parent_ownership[create-null]",
    "test_schedule_service_parent_ownership[create-missing]",
    "test_schedule_service_parent_ownership[move-a]",
    "test_schedule_service_parent_ownership[move-b]",
    "test_schedule_service_parent_ownership[move-null]",
    "test_schedule_service_parent_ownership[move-missing]",
    "test_schedule_service_parent_ownership[unchanged-a]",
    "test_schedule_service_parent_ownership[unchanged-b]",
    "test_schedule_service_parent_ownership[unchanged-null]",
)


def validator():
    runner = RUNNER.read_text()
    marker = "$receiptValidator = @'\n"
    assert runner.count(marker) == 1
    source = runner.split(marker, 1)[1].split("\n'@", 1)[0]
    assignment = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "expected"
            for target in node.targets
        )
    )
    return source, ast.literal_eval(assignment.value)


def receipt():
    source, expected = validator()
    root = ElementTree.Element("testsuite")
    for classname, names in expected.items():
        # The required target cohort is independent of the validator's contents.
        if classname == TENANT_CLASS:
            names = (
                *PREVIOUS_TENANT_CASES,
                *MFA_CASES,
                *ADMIN_CASES,
                *WEEKLY_CASES,
                *SCHEDULE_CASES,
            )
        for name in names:
            ElementTree.SubElement(root, "testcase", classname=classname, name=name)
    return source, root


def execute(source, root, tmp_path, monkeypatch):
    path = tmp_path / "receipt.xml"
    ElementTree.ElementTree(root).write(path)
    monkeypatch.setattr(sys, "argv", ["validator", str(path)])
    script = tmp_path / "validator.py"
    script.write_text(source)
    runpy.run_path(str(script), run_name="__main__")


def test_tenant_cohort_preserves_all_previous_names_and_adds_exact_mfa_cases():
    _, expected = validator()
    assert expected[TENANT_CLASS] == (
        *PREVIOUS_TENANT_CASES,
        *MFA_CASES,
        *ADMIN_CASES,
        *WEEKLY_CASES,
        *SCHEDULE_CASES,
    )
    assert sum(map(len, expected.values())) == 72


def test_complete_expanded_postgres_receipt_passes(tmp_path, monkeypatch, capsys):
    source, root = receipt()
    execute(source, root, tmp_path, monkeypatch)
    assert capsys.readouterr().out == "INTEGRATION_POSTGRES_COHORT_VERIFIED_PASS 72\n"


@pytest.mark.parametrize(
    "name", (*MFA_CASES, *ADMIN_CASES, *WEEKLY_CASES, *SCHEDULE_CASES)
)
@pytest.mark.parametrize(
    "mutation",
    ["missing", "skipped", "failure", "error", "duplicate", "wrong-name", "extra-case"],
)
def test_mfa_receipt_rejects_incomplete_or_unsuccessful_case(
    name, mutation, tmp_path, monkeypatch, capsys
):
    source, root = receipt()
    target = next(
        case
        for case in root
        if case.get("classname") == TENANT_CLASS and case.get("name") == name
    )
    if mutation == "missing":
        root.remove(target)
    elif mutation in {"skipped", "failure", "error"}:
        ElementTree.SubElement(target, mutation)
    elif mutation == "duplicate":
        ElementTree.SubElement(root, "testcase", classname=TENANT_CLASS, name=name)
    elif mutation == "wrong-name":
        target.set("name", "unreviewed")
    else:
        ElementTree.SubElement(
            root, "testcase", classname=TENANT_CLASS, name="unreviewed"
        )
    with pytest.raises(
        SystemExit, match="PostgreSQL cohort receipt incomplete or unsuccessful"
    ):
        execute(source, root, tmp_path, monkeypatch)
    assert "VERIFIED_PASS" not in capsys.readouterr().out


def test_same_length_duplicate_cannot_replace_missing_mfa_case(tmp_path, monkeypatch):
    source, root = receipt()
    cases = [case for case in root if case.get("classname") == TENANT_CLASS]
    cases[-1].set("name", cases[-2].get("name"))
    assert len(cases) == 45
    with pytest.raises(SystemExit, match=TENANT_CLASS):
        execute(source, root, tmp_path, monkeypatch)
