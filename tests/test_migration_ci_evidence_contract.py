"""Fail-closed dispatch and receipts for retained migration CI evidence."""

from __future__ import annotations

import json
import runpy
import shlex
import sys
from pathlib import Path

import pytest
import yaml

from tests.helpers.synthetic_credentials import make_test_marker


def _repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".github/workflows/ci.yml").is_file():
            return parent
    raise RuntimeError("could not locate the repository CI workflow")


REPOSITORY_ROOT = _repository_root()
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"
_RENDERER_LIFECYCLE_RECEIPT_HELPER = (
    REPOSITORY_ROOT / ".github/scripts/ci/verify_alembic_renderer_lifecycle_receipt.py"
)
_OWNED_RENDERER_POSTGRES_RECEIPT_HELPER = (
    REPOSITORY_ROOT / ".github/scripts/ci/verify_owned_renderer_postgres_receipt.py"
)


def _assert_receipt_helper_is_invoked(run: str, helper: Path) -> None:
    relative_helper = helper.relative_to(REPOSITORY_ROOT).as_posix()
    invocation = (
        "uv run --frozen --no-sync python -I "
        f'{relative_helper} "$probe_root/junit.xml" || receipt_status=$?'
    )
    assert run.count(invocation) == 1


def _migration_job():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["alembic-migrations"]


def test_tenant_context_diagnostic_is_separate_bounded_and_fail_closed() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["alembic-migrations"]
    steps = job["steps"]
    tenant = next(step for step in steps if step.get("id") == "tenant-context-evidence")
    migration = next(step for step in steps if step.get("id") == "migration-squawk")
    assert steps.index(migration) < steps.index(tenant)
    assert job["timeout-minutes"] == 15
    assert tenant["timeout-minutes"] == 3
    guard = tenant["if"]
    assert "!cancelled()" in guard
    assert "steps.migration-squawk.outcome == 'success'" in guard
    assert "steps.migration-squawk.outcome == 'failure'" in guard
    assert "always()" not in guard
    assert tenant["env"] == {
        "SECRET_KEY": "${{ env.SECRET_KEY }}",
        "ENVIRONMENT": "testing",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "RUN_INTEGRATION_TESTS": "1",
    }
    run = tenant["run"]
    assert "set -euo pipefail" in run
    assert 'probe_root="$(mktemp -d)"' in run
    assert "trap 'rm -rf -- \"$probe_root\"' EXIT" in run
    assert "uv run pytest -v --tb=short --show-capture=no --no-cov --maxfail=0" in run
    selector = (
        "tests/integration/test_aud197_198_notification_outbox_postgres.py::"
        "test_content_outbox_restores_tenant_scope"
    )
    assert run.count(selector) == 1
    assert selector not in migration["run"]
    additional_selectors = (
        "tests/integration/test_aud197_198_notification_outbox_postgres.py::"
        "test_legacy_null_tenant_content_ignores_worker_ambient_scope",
        "tests/test_outbox_tenant_context.py",
        "tests/integration/test_aud197_198_notification_outbox_postgres.py::"
        "test_unscoped_missing_content_retains_retry_and_dlq_evidence",
        "tests/test_event_handlers_behavior_closure.py::"
        "test_created_notification_handler_skips_deleted_source_record",
        "tests/test_event_handlers_behavior_closure.py::"
        "test_comment_notification_fails_closed_when_news_or_author_disappears",
        "tests/test_event_handlers_behavior_closure.py::"
        "test_comment_notification_skips_deleted_comment_before_loading_sources",
        "tests/test_event_handlers_behavior_closure.py::"
        "test_created_notification_handler_retries_unscoped_missing_source",
        "tests/test_event_handlers_behavior_closure.py::"
        "test_comment_notification_retries_unscoped_missing_protected_parent",
        "tests/integration/test_aud197_198_notification_outbox_postgres.py::"
        "test_grade_committed_assignment_delivery_replay_sends_once",
        "tests/integration/test_aud197_198_notification_outbox_postgres.py::"
        "test_grade_rollback_then_fresh_retry_sends_only_after_commit",
    )
    for additional in additional_selectors:
        assert run.count(additional) == 1
        assert additional not in migration["run"]
    assert '--basetemp="$probe_root/basetemp"' in run
    assert '> "$test_log" 2>&1 || pytest_status=$?' in run
    assert 'head -c 131072 "$test_log"' in run
    assert 'if [ "$bytes" -gt 131072 ]; then' in run
    assert '[ "$pytest_status" -ne 0 ] || pytest_status=1' in run
    assert 'exit "$pytest_status"' in run
    assert "OWNED_TENANT_CONTEXT_TESTS_BEGIN" in run
    assert "OWNED_TENANT_CONTEXT_TESTS_END" in run
    assert "--capture=no" not in run
    assert "continue-on-error" not in tenant


_RENDERER_LIFECYCLE_NAMES = (
    "test_live_renderer_records_transaction_events_and_removes_listeners_on_success",
    "test_live_renderer_records_rollback_and_removes_listeners_on_failure",
    "test_scratch_requires_template0_and_empty_catalog_before_upgrade",
    "test_scratch_create_failure_never_drops_or_changes_execution_state",
    "test_scratch_nonempty_or_unverifiable_catalog_blocks_upgrade",
    "test_scratch_cleanup_requires_confirmed_created_database_identity",
    "test_renderer_failure_diagnostics_are_opaque",
    "test_renderer_api_rejects_dbname_query_override_before_scratch_work",
    "test_renderer_cli_rejects_dbname_query_override_before_scratch_work",
    "test_renderer_rejects_invalid_url_and_engine_setup_opaquely",
    "test_renderer_connection_failure_disposes_opaquely",
    "test_renderer_rejects_malformed_server_identity",
    "test_renderer_rejects_malformed_catalog_values",
    "test_renderer_cleanup_preserves_failure_and_disposes",
    "test_renderer_restores_unset_environment_after_owned_scratch",
)
_RENDERER_LIFECYCLE_SELECTORS = tuple(
    "tests/test_alembic_live_sql_render.py::" + name
    for name in _RENDERER_LIFECYCLE_NAMES
)


def _renderer_lifecycle_step(job):
    matches = [
        step for step in job["steps"] if step.get("id") == "renderer-lifecycle-evidence"
    ]
    assert len(matches) == 1, "one bounded renderer lifecycle step is required"
    return matches[0]


def _assert_renderer_lifecycle_contract(job):
    step = _renderer_lifecycle_step(job)
    steps = job["steps"]
    original = next(s for s in steps if s.get("id") == "migration-squawk")
    assert steps[-1] is step
    assert steps[-2]["name"] == "Check Alembic schema drift (MOD-14-03)"
    assert job["timeout-minutes"] == 15
    assert step["name"] == "Verify Alembic renderer lifecycle contracts"
    assert step["timeout-minutes"] == 3
    assert step["shell"] == "bash"
    assert "continue-on-error" not in job
    assert "continue-on-error" not in original
    assert "continue-on-error" not in step
    assert "permissions" not in step
    assert " ".join(step["if"].split()) == (
        "${{ !cancelled() && "
        "(steps.migration-squawk.outcome == 'success' || "
        "steps.migration-squawk.outcome == 'failure') }}"
    )
    assert step["env"] == {
        "SECRET_KEY": "${{ env.SECRET_KEY }}",
        "ENVIRONMENT": "testing",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "RUN_INTEGRATION_TESTS": "",
    }
    run = step["run"]
    assert run.splitlines()[0] == "set -euo pipefail"
    assert 'probe_root="$(mktemp -d)"' in run
    assert "trap 'rm -rf -- \"$probe_root\"' EXIT" in run
    commands = [
        line.strip()
        for line in run.replace("\\\n", "").splitlines()
        if line.lstrip().startswith("timeout ")
    ]
    assert len(commands) == 1
    assert shlex.split(commands[0]) == [
        "timeout",
        "--signal=TERM",
        "--kill-after=5s",
        "150s",
        "uv",
        "run",
        "--frozen",
        "--no-sync",
        "pytest",
        "-n",
        "0",
        "-vv",
        "--tb=short",
        "--show-capture=no",
        "--no-cov",
        "--maxfail=0",
        *_RENDERER_LIFECYCLE_SELECTORS,
        "--basetemp=$probe_root/basetemp",
        "--junitxml=$probe_root/junit.xml",
        ">",
        "$test_log",
        "2>&1",
        "||",
        "pytest_status=$?",
    ]
    for selector in _RENDERER_LIFECYCLE_SELECTORS:
        assert run.count(selector) == 1
    assert 'bytes="$(wc -c < "$test_log")"' in run
    assert 'head -c 131072 "$test_log"' in run
    assert "ALEMBIC_RENDERER_LIFECYCLE_TESTS_BEGIN" in run
    assert "ALEMBIC_RENDERER_LIFECYCLE_TESTS_END" in run
    _assert_receipt_helper_is_invoked(run, _RENDERER_LIFECYCLE_RECEIPT_HELPER)
    assert (
        'if [ "$bytes" -gt 131072 ]; then\n'
        '  echo "::error::Alembic renderer lifecycle output exceeded 131072 bytes"\n'
        "  receipt_status=1\nfi\n"
        'if [ "$pytest_status" -ne 0 ]; then\n'
        '  exit "$pytest_status"\nfi\nexit "$receipt_status"'
    ) == run[run.index('if [ "$bytes" -gt 131072 ]; then') :].rstrip()
    assert "|| true" not in run
    assert "set +e" not in run


def test_renderer_lifecycle_diagnostic_is_last_bounded_and_fail_preserving() -> None:
    job = _migration_job()
    _assert_renderer_lifecycle_contract(job)


@pytest.mark.parametrize(
    "defect",
    [
        "missing-selector",
        "reordered-selectors",
        "success-only",
        "advisory",
        "not-last",
        "postgres-environment",
        "integration-opt-in",
        "maxfail",
        "discard-exit",
    ],
)
def test_renderer_lifecycle_contract_rejects_dispatch_bypasses(defect) -> None:
    job = _migration_job()
    _assert_renderer_lifecycle_contract(job)
    step = _renderer_lifecycle_step(job)
    if defect == "missing-selector":
        step["run"] = step["run"].replace(_RENDERER_LIFECYCLE_SELECTORS[-1], "")
    elif defect == "reordered-selectors":
        first, second = _RENDERER_LIFECYCLE_SELECTORS[:2]
        run = step["run"].replace(first, "RENDERER_SELECTOR_PLACEHOLDER")
        run = run.replace(second, first)
        step["run"] = run.replace("RENDERER_SELECTOR_PLACEHOLDER", second)
    elif defect == "success-only":
        step["if"] = "${{ success() }}"
    elif defect == "advisory":
        step["continue-on-error"] = True
    elif defect == "not-last":
        job["steps"][-2], job["steps"][-1] = job["steps"][-1], job["steps"][-2]
    elif defect == "postgres-environment":
        step["env"]["DATABASE_URL"] = "postgresql://unexpected"
    elif defect == "integration-opt-in":
        step["env"]["RUN_INTEGRATION_TESTS"] = "1"
    elif defect == "maxfail":
        step["run"] = step["run"].replace("--maxfail=0", "--maxfail=1")
    else:
        assert defect == "discard-exit"
        step["run"] = step["run"].replace('exit "$pytest_status"', "exit 0")
    with pytest.raises(AssertionError):
        _assert_renderer_lifecycle_contract(job)


@pytest.mark.parametrize(
    "defect", ["count", "duplicate", "skipped", "malformed", "oversized"]
)
def test_renderer_lifecycle_receipt_rejects_incomplete_results(
    tmp_path, monkeypatch, capsys, defect
) -> None:
    report = tmp_path / "junit.xml"
    cases = [
        f'<testcase classname="owned.renderer" name="case-{index}"/>'
        for index in range(41)
    ]
    start = '<testsuites><testsuite tests="41" failures="0" errors="0" skipped="0">'
    end = "</testsuite></testsuites>"
    valid = start + "".join(cases) + end
    report.write_text(valid, encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [str(_RENDERER_LIFECYCLE_RECEIPT_HELPER), str(report)],
    )
    runpy.run_path(str(_RENDERER_LIFECYCLE_RECEIPT_HELPER), run_name="__main__")
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out.endswith("ALEMBIC_RENDERER_LIFECYCLE_VERIFIED_PASS 41\n")
    counts = json.loads(output.out.splitlines()[0].split(" ", 1)[1])
    assert counts == {"tests": 41, "failures": 0, "errors": 0, "skipped": 0}

    private = make_test_marker(length=32)
    if defect == "count":
        value = valid.replace('tests="41"', 'tests="40"')
    elif defect == "duplicate":
        value = start + "".join([cases[0], *cases[:-1]]) + end
    elif defect == "skipped":
        value = valid.replace('skipped="0"', 'skipped="1"').replace(
            cases[0], '<testcase name="omitted"><skipped/></testcase>'
        )
    elif defect == "malformed":
        value = "<" + private
    else:
        assert defect == "oversized"
        value = private + "x" * 1_048_577
    report.write_text(value, encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        runpy.run_path(str(_RENDERER_LIFECYCLE_RECEIPT_HELPER), run_name="__main__")
    assert failure.value.code == 1
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out.endswith("ALEMBIC_RENDERER_LIFECYCLE_RECEIPT_REJECTED\n")
    assert "VERIFIED_PASS" not in output.out
    assert private not in output.out
    assert str(tmp_path) not in output.out
    assert len(output.out.encode()) < 1024


@pytest.mark.parametrize("defect", ["failure", "error", "skipped", "wrong-identity"])
def test_owned_renderer_postgres_receipt_rejects_failed_or_misattributed_results(
    tmp_path, monkeypatch, capsys, defect
) -> None:
    job = yaml.safe_load(WORKFLOW.read_text())["jobs"]["db-migration-gate"]
    matches = [
        step for step in job["steps"] if step.get("id") == "renderer-postgres-evidence"
    ]
    assert len(matches) == 1
    run = matches[0]["run"]
    _assert_receipt_helper_is_invoked(run, _OWNED_RENDERER_POSTGRES_RECEIPT_HELPER)
    report = tmp_path / "junit.xml"
    names = [
        "test_owned_renderer_catalog_rejects_user_objects[" + kind + "]"
        for kind in ("relation", "routine", "type", "schema", "extension")
    ]
    names.extend(
        [
            "test_owned_live_renderer_root_lifecycle_cleans_up",
            "test_owned_live_renderer_create_collision_preserves_existing_database",
        ]
    )
    cases = [
        f'<testcase classname="tests.test_alembic_live_sql_render" name="{name}"/>'
        for name in names
    ]
    start = '<testsuites><testsuite tests="7" failures="0" errors="0" skipped="0">'
    end = "</testsuite></testsuites>"
    valid = start + "".join(cases) + end
    report.write_text(valid, encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [str(_OWNED_RENDERER_POSTGRES_RECEIPT_HELPER), str(report)],
    )
    runpy.run_path(str(_OWNED_RENDERER_POSTGRES_RECEIPT_HELPER), run_name="__main__")
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out.endswith("OWNED_RENDERER_POSTGRES_VERIFIED_PASS 7\n")
    counts = json.loads(output.out.splitlines()[0].split(" ", 1)[1])
    assert counts == {"tests": 7, "failures": 0, "errors": 0, "skipped": 0}

    private = make_test_marker(length=32, required_classes=frozenset({"lower"}))
    if defect == "wrong-identity":
        mutations = [
            valid.replace(
                'classname="tests.test_alembic_live_sql_render"',
                f'classname="{private}"',
                1,
            )
        ]
    else:
        # Neither a falsely clean aggregate nor missing child tags may hide failure.
        failed_case = cases[0].replace(
            "/>", f"><{defect}>{private}</{defect}></testcase>"
        )
        counters = {"failure": "failures", "error": "errors", "skipped": "skipped"}
        counter = counters[defect]
        mutations = [
            valid.replace(cases[0], failed_case, 1),
            valid.replace(f'{counter}="0"', f'{counter}="1"', 1),
        ]
    for value in mutations:
        report.write_text(value, encoding="utf-8")
        with pytest.raises(SystemExit) as failure:
            runpy.run_path(
                str(_OWNED_RENDERER_POSTGRES_RECEIPT_HELPER), run_name="__main__"
            )
        assert failure.value.code == 1
        output = capsys.readouterr()
        opaque = private not in output.out + output.err
        assert opaque, "receipt diagnostics must not publish private report context"
        assert output.err == ""
        assert output.out.endswith("OWNED_RENDERER_POSTGRES_RECEIPT_REJECTED\n")
        assert "VERIFIED_PASS" not in output.out
        assert str(tmp_path) not in output.out
        assert len(output.out.encode()) < 1024
