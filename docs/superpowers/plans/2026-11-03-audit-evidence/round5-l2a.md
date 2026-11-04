# Lane L2a evidence (HEAD 811747bc9, branch egorribun)

Container: ue-r5-l2a-pg (pgvector/pgvector:pg17), database ue_test_r5_l2a, non-superuser role ue_r5_dlq. Removed with `docker rm -fv` at the end. No university_* volume touched.

## AUD-392 (HIBP default and production requirement)

- status: code-fixed+locally-proven (fixture drift did not reproduce at HEAD; one behavioural test added). Hosted: needs backend-tests green on the exact SHA.
- HEAD state: the production default already exists in `app/core/config/mixins/mfa_settings.py` (`_enable_hibp_screening_in_deployed_environments`, staging/production resolve to enabled, explicit false rejected). Validator and HIBP client: `app/auth/security.py` (`validate_password_hibp`, `_validate_password_policy`). Consumers: `app/services/user/compliance_service.py` (register, admin create), `app/services/auth_service.py` (reset, change).
- Fixture drift check at HEAD: 32 password/HIBP-referencing test files, 653 passed, 1 skipped, 0 drift failures. The one failure in that run, `tests/test_alembic_settings_isolation.py::test_probe_discards_parent_database_and_env_file_redirections`, is a Windows-only env-probe mismatch outside this lane (not touched).
- Frontend: `frontend/src/pages/__tests__/Register.test.tsx`, `ResetPassword.test.tsx`, `ResetPassword.token-error.test.tsx` (125 passed); `frontend/src/utils/passwordStrength.test.ts` (6 passed).
- New test: `tests/test_aud392_production_hibp_enforcement.py::test_aud392_production_registration_rejects_breached_password` (production Settings with the flag unset drives the real `UserComplianceService.register_user`; real `validate_password_hibp` against a mocked HTTP transport returns a breached record; asserts `password_policy_compromised`, one lookup, no hashing or insert). Before the default existed the flag was False and registration would not look up HIBP, so the test fails without the default.
- Commands: `uv run pytest tests/test_aud392_production_hibp_enforcement.py -q` -> 1 passed. Full set above -> 653 passed. ruff check and format --check clean.
- Hosted job that must be green: backend-tests (ci.yml ~717) on the exact SHA.

## AUD-426 (MFA race, asyncio.Lock shim)

- status: code-fixed+locally-proven; needs-hosted-CI for the PostgreSQL run.
- Lock shim: already removed at b72ca7226 (HEAD `tests/security/test_mfa_race.py` has no asyncio.Lock; the only "Lock" text is in the docstring).
- Change: the two tests previously drove requests through httpx ASGI transport. They now use a uvicorn server on 127.0.0.1 (port 0, lifespan off) inside the test loop, with an httpx client primed through the real CSRF handshake (`_configure_csrf_client`). The login-challenge test copies the factory's pre-auth cookie and user agent to the socket client so the fingerprint binding matches.
- Files: `tests/security/test_mfa_race.py`.
- Test names: `tests/security/test_mfa_race.py::test_mfa_challenge_race_condition`, `::test_mfa_step_up_challenge_verification_race`.
- Command on owned PG: `DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:55432/ue_test_r5_l2a UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET=1 uv run pytest tests/security/test_mfa_race.py -q` -> 2 passed, three consecutive runs (2 passed each). Earlier runs: 2 failed before the fingerprint copy (all 400s), then fixed.
- Limit: no mutation run (removing the row locks would touch `app/auth/mfa/challenge.py`, not owned). Discrimination relies on the PG row locks in `consume_challenge` (User row `with_for_update`, then challenge `for_update=True`).
- Hosted job that must be green: no current CI job selects this file with a PostgreSQL DATABASE_URL. A PG-service job must add it (e.g. the PG-backed jobs at ci.yml ~1172 alembic-migrations or ~1975 db-migration-gate). CI edits are outside this lane.

## AUD-447 (reset-link tokens in dead_letter_jobs)

- status: code-fixed+locally-proven for the two residuals below; ID stays open. needs-owner for the deployed-row scrub; lossless-storage design not coded.
- Residual 1, retained-error dedup: a duplicate failure returned early without scrubbing `existing.error_message`, so a link stored by an earlier row survived. Fixed in `DeadLetterQueue.add_failed_job` duplicate branch (`_scrub_error_text` on the retained error).
- Residual 2, escaped markers: `_PLAINTEXT_TOKEN_LINK` only matched plain `#token=`, `?token=`, `&token=`. It now also matches percent-encoded (`%23token%3D`, `%3Ftoken%3D`, `%26token%3D`), HTML-entity (`&amp;`, `&#38;`, `&#x26;`, `&#61;`, `&#x3d;`) forms, and mixed case.
- Stale overwrite: the quarantine compare-and-set (`WHERE payload = <observed bytes>`) already exists; the PostgreSQL interleaving tests pass on a real PG (below). Replay rows are held under `FOR UPDATE SKIP LOCKED` for the whole transaction, so no separate unlocked overwrite was found. Not separately coded.
- Forged markers: auth payloads are accepted only through Fernet envelope authentication (`_read_auth_email_link`); a forged plaintext link with `encrypted_link` fails closed and is quarantined. Covered by existing tests (not changed).
- Files changed: `app/workers/dead_letter_queue.py`; `tests/test_dead_letter_queue.py` (one line: `existing_job.error_message = None` on the duplicate mock); `tests/test_dead_letter_queue_worker.py` (`MagicMock(status=status, error_message=None)`). Both mock fixes were needed because the new scrub reads `error_message`; no assertion was weakened.
- New tests: `tests/test_aud447_residual_error_scrub.py`:
  - `test_aud447_duplicate_failure_scrubs_error_text_retained_by_the_earlier_row` (failed before the fix)
  - `test_aud447_duplicate_failure_keeps_ordinary_retained_error_text`
  - `test_aud447_every_encoding_of_a_token_link_is_scrubbed[10 ids]` (8 failed before the fix, 2 passed as controls)
  - `test_aud447_ordinary_text_mentioning_tokens_is_kept[4 cases]`
- Commands and results:
  - `uv run pytest tests/test_aud447_residual_error_scrub.py tests/test_aud447_quarantine_persistence.py tests/test_aud447_retained_storage_persistence.py tests/test_aud447_dlq_admin_error_privacy.py tests/test_dead_letter_queue.py tests/test_dead_letter_queue_closure.py tests/test_dead_letter_queue_worker.py tests/test_workers_dlq.py tests/test_self_healing_dlq.py tests/test_dlq_outbox_failures.py tests/test_api_dlq.py tests/test_api_dlq_closure.py tests/test_dlq_api_closure.py tests/test_notification_dead_letter_api.py tests/test_event_dlq_closure.py tests/test_outbox_dlq_contracts.py` -> 139 passed (final run, after the two mock fixture fixes; the first run before them had 3 failures from `MagicMock` error_message).
  - PostgreSQL: `AUD447_DLQ_DISPOSABLE=1 AUD447_DLQ_DISPOSABLE_PG_URL=postgresql+asyncpg://ue_r5_dlq:...@127.0.0.1:55432/ue_test_r5_l2a uv run pytest tests/integration/test_aud447_quarantine_cas_postgres.py` -> 3 passed (non-superuser, NOBYPASSRLS role). `tests/integration/test_dlq_retry_postgres.py` passed in the same run (4 passed total with the MFA race file).
  - ruff check and ruff format --check on changed Python: clean. mypy on `app/workers/dead_letter_queue.py`: no issues.
- Hosted job that must be green: backend-tests for the SQLite-backed tests; the CAS PG test needs a PG job that sets AUD447_DLQ_DISPOSABLE=1 and a non-superuser URL (no current CI job sets these).
- Deployed-row scrub: NOT coded. Nothing is deployed, the scrub migration was squashed (plan), and ADR-051 forbids a new migration outside the single baseline. Needs the owner.
- Lossless-storage design: analysis only, not coded.

## Other observations (outside this lane)

- `tests/test_user_compliance_closure.py` (4 export tests) fails on SQLite with "table notifications has no column named tenant_id". The uncommitted `app/models/notifications.py` change (another lane) adds `tenant_id`, and the SQLite test schema does not match. Not caused by L2a edits.
- Windows-only: pytest-timeout needs SIGALRM; run with `-o timeout=0` for local runs.
- Tests mypy: `mypy` on tests reports pre-existing untyped-def errors; the gate is `mypy app/`.

## Files changed by L2a

- app/workers/dead_letter_queue.py
- tests/security/test_mfa_race.py
- tests/test_dead_letter_queue.py
- tests/test_dead_letter_queue_worker.py
- tests/test_aud392_production_hibp_enforcement.py (new)
- tests/test_aud447_residual_error_scrub.py (new)
