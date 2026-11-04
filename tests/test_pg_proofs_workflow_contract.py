"""Contract for the hosted PostgreSQL proofs AUD-426 and AUD-447.

The proofs must run in the PostgreSQL-backed integration job after migrations,
must use a non-superuser NOBYPASSRLS login for AUD-447, and must fail on any
skipped or unexecuted test.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
LOSSLESS_CLASS = "tests.test_aud447_lossless_storage_postgres"
LOSSLESS_CASE = "test_aud447_postgres_insert_and_replay_store_no_token_bytes"
MFA_CLASS = "tests.security.test_mfa_race"
QUARANTINE_CLASS = "tests.integration.test_aud447_quarantine_cas_postgres"
EXPECTED_CASES = (
    (MFA_CLASS, "test_mfa_challenge_race_condition"),
    (MFA_CLASS, "test_mfa_step_up_challenge_verification_race"),
    (
        QUARANTINE_CLASS,
        "test_quarantine_never_overwrites_bytes_repaired_after_they_were_read",
    ),
    (
        QUARANTINE_CLASS,
        "test_quarantine_replaces_observed_bytes_and_scrubs_link_in_error_field",
    ),
    (QUARANTINE_CLASS, "test_failed_replay_stores_scrubbed_error_text"),
    (LOSSLESS_CLASS, LOSSLESS_CASE),
)


def _job() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job: dict[str, Any] = document["jobs"]["integration-tests"]
    return job


def _names() -> list[str]:
    return [str(step.get("name", "")) for step in _job()["steps"]]


def test_proofs_run_after_migrations_and_before_integration_suite() -> None:
    names = _names()
    migrate = names.index("Run Alembic migrations")
    login = names.index("Create disposable non-superuser PostgreSQL login for AUD-447")
    proofs = names.index("Run PostgreSQL proofs (AUD-426, AUD-447) without skips")
    suite = names.index("Run integration tests")

    assert migrate < login < proofs < suite


def test_aud447_login_is_non_superuser_and_nobypassrls() -> None:
    step = _job()["steps"][
        _names().index("Create disposable non-superuser PostgreSQL login for AUD-447")
    ]
    run = str(step["run"])

    assert "runtime_role_statements" in run
    assert "GRANT CREATE ON DATABASE test" in run
    assert "AUD447_DLQ_DISPOSABLE=1" in run
    assert "AUD447_DLQ_DISPOSABLE_PG_URL=" in run
    assert "ue_aud447_probe" in run


def test_proof_step_selects_exact_files_and_rejects_skips() -> None:
    step = _job()["steps"][
        _names().index("Run PostgreSQL proofs (AUD-426, AUD-447) without skips")
    ]
    run = str(step["run"])

    assert "tests/security/test_mfa_race.py" in run
    assert "tests/integration/test_aud447_quarantine_cas_postgres.py" in run
    assert "tests/test_aud447_lossless_storage_postgres.py" in run
    assert "-rs" in run
    assert "unexecuted" in run and "sys.exit(1)" in run
    assert "continue-on-error" not in step


def _verify_report(
    tmp_path: Path,
    cases: list[tuple[str, str, str | None]],
    monkeypatch: pytest.MonkeyPatch,
    *,
    report_counts: bool = True,
) -> int:
    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(
        root,
        "testsuite",
        tests=str(len(cases)),
        skipped=str(
            sum(status == "skipped" for _, _, status in cases) if report_counts else 0
        ),
        failures=str(
            sum(status == "failure" for _, _, status in cases) if report_counts else 0
        ),
        errors=str(
            sum(status == "error" for _, _, status in cases) if report_counts else 0
        ),
    )
    for classname, name, status in cases:
        case = ElementTree.SubElement(suite, "testcase", classname=classname, name=name)
        if status:
            ElementTree.SubElement(case, status)
    ElementTree.ElementTree(root).write(tmp_path / "pg-proofs.xml", encoding="utf-8")

    step = _job()["steps"][
        _names().index("Run PostgreSQL proofs (AUD-426, AUD-447) without skips")
    ]
    _, opening, remainder = str(step["run"]).partition(
        'uv run --frozen --no-sync python -c "\n'
    )
    script, closing, _ = remainder.partition('\n"')
    assert opening and closing
    script_path = tmp_path / "verify_pg_report.py"
    script_path.write_text(script, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as error:
        return int(error.code)
    return 0


@pytest.mark.parametrize(
    "missing", [(MFA_CLASS,), (QUARANTINE_CLASS,), (MFA_CLASS, QUARANTINE_CLASS)]
)
def test_proof_report_rejects_missing_existing_suites(
    tmp_path: Path, missing: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [
        (classname, name, None)
        for classname, name in EXPECTED_CASES
        if classname not in missing
    ]

    assert _verify_report(tmp_path, cases, monkeypatch) != 0


@pytest.mark.parametrize("missing_case", EXPECTED_CASES)
def test_proof_report_rejects_any_missing_case(
    tmp_path: Path, missing_case: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [
        (classname, name, None)
        for classname, name in EXPECTED_CASES
        if (classname, name) != missing_case
    ]

    assert _verify_report(tmp_path, cases, monkeypatch) != 0


@pytest.mark.parametrize("extra", [EXPECTED_CASES[1], ("tests.extra", "test_extra")])
def test_proof_report_rejects_duplicate_or_unexpected_case(
    tmp_path: Path, extra: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [
        (classname, name, None) for classname, name in (*EXPECTED_CASES[1:], extra)
    ]

    assert _verify_report(tmp_path, cases, monkeypatch) != 0


def test_proof_report_accepts_complete_passed_cohort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [(classname, name, None) for classname, name in EXPECTED_CASES]

    assert _verify_report(tmp_path, cases, monkeypatch) == 0


@pytest.mark.parametrize("status", ["skipped", "failure", "error"])
@pytest.mark.parametrize("report_counts", [True, False])
def test_proof_report_rejects_unexecuted_or_failed_cases(
    tmp_path: Path, status: str, report_counts: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [
        (classname, name, status if index == 0 else None)
        for index, (classname, name) in enumerate(EXPECTED_CASES)
    ]

    assert (
        _verify_report(tmp_path, cases, monkeypatch, report_counts=report_counts) != 0
    )
