"""Contract for the hosted PostgreSQL proofs AUD-426 and AUD-447.

The proofs must run in the PostgreSQL-backed integration job after migrations,
must use a non-superuser NOBYPASSRLS login for AUD-447, and must fail on any
skipped or unexecuted test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"


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
    assert "-rs" in run
    assert "unexecuted" in run and "sys.exit(1)" in run
    assert "continue-on-error" not in step
