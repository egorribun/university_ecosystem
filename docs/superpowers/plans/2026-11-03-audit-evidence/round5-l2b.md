# Lane L2b evidence (HEAD 811747bc9, branch egorribun)

Environment: Windows host, Docker Desktop (Linux engine). Owned-PG fixtures run on the Windows host through
`C:\Temp\claude\...\scratchpad\l2b_win_shim.py` (scratch only, not committed): it sets
`owned._DOCKER_SOCKET` to the Docker named pipe and disables pytest-timeout (no SIGALRM on Windows).
Command: `PYTHONPATH=<scratch> .venv/Scripts/python.exe -m pytest -p l2b_win_shim -p no:timeout -p no:cacheprovider --no-cov <files>`.
Disposable PG: container `ue-r5-l2b-pg` (pgvector/pgvector:pg17, 127.0.0.1:56431), removed with `-v` at the end.
Databases on it: `test_l2b_ci` (baseline via `alembic upgrade head`), `test_l2b_fresh` (fresh upgrade + check),
`audit_ws_borrowed` (AUD-363 reader role). Credentials were generated at runtime into scratch files, not reported.

| ID | status | files | exact tests | command + result | hosted job that must be green |
|---|---|---|---|---|---|
| AUD-360 | code-fixed (CLI owner) + locally-proven; producer inventory below | app/cli/db.py; tests/test_aud360_producer_tenant_stamping.py (new); tests/integration/test_aud277_360_450_tenant_rls_postgres.py | test_operator_created_admin_is_owned_by_the_configured_tenant, test_operator_created_admin_without_configured_tenant_stays_unset; owned: test_every_tenant_table_forces_rls_and_stamps_unowned_inserts, test_notification_producer_rows_are_owned_by_the_session_tenant, test_worker_bypass_producer_must_write_its_tenant_explicitly | unit: 2 passed; owned PG file: 10 passed (7 pre-existing + 3 new) | owned PostgreSQL integration job |
| AUD-450 | already-done in code; proven | none (GUC write already absent: grep finds no `app.bypass_rls` writes outside tests) | test_no_permissive_true_policy_remains_on_core_tables, test_guc_bypass_cannot_expose_other_tenants_or_null_rows, test_dedicated_bypass_role_member_sees_every_row (+ 7 in owned file) | owned PG file 10 passed | owned PostgreSQL integration job |
| AUD-454 | code already ordered; ordering test + borrowed-session PG proof | tests/test_aud454_websocket_membership_race.py | test_roster_read_precedes_every_room_semaphore_acquisition (new); existing 3 + PG 6 | unit file 5 passed; tests/integration/test_aud363_454_borrowed_session_postgres.py 6 passed on owned-style PG (AUD363 disposable DB) | owned PostgreSQL integration job; ws-hub live delivery and in-flight frame cancellation remain separate evidence |
| AUD-272 | U; PG claim run recorded; attempted_at constraint still in baseline | none | tests/test_notification_delivery_once_claims.py (10) and tests/integration/test_aud262_receipt_schema_postgres.py (14) | PG run: 24 passed | owner acceptance that the ledger supersedes uq_notification_delivery_once (baseline) |

## Commands and results (final tree)
- `pytest tests/integration/test_aud363_454_borrowed_session_postgres.py tests/integration/test_aud262_receipt_schema_postgres.py tests/test_notification_delivery_once_claims.py tests/integration/test_aud277_360_450_tenant_rls_postgres.py tests/integration/test_rls_matrix.py tests/integration/test_rls_messages.py tests/integration/test_rls_identity_isolation.py` (AUD363 and RLS env set, DATABASE_URL to test_l2b_ci): **56 passed**.
- SQLite set `pytest tests/ -k "notification or compliance or tenant" --ignore=tests/test_spiffe_worker.py`: **976 passed, 47 skipped, 2 failed**. The 2 failures are PG tests that cannot run on Windows (psycopg async on ProactorEventLoop): tests/test_mvp_tenant_auth_postgres.py::test_owned_registration_login_token_and_rls_isolation and tests/test_seed_tenant_postgres.py::test_owned_seed_group_as_nonprivileged_role_is_scoped_and_repeatable. Linux runner (`ue-r5-l2b-runner`, scratch image on pinned python:3.14.8-slim-bookworm and uv 0.12.23): 14 passed, the same 2 failed with "Owned PostgreSQL readiness deadline exceeded": the owned fixture's randomly published port is refused from the runner's host network on this Docker Desktop. Unverified here; hosted owned-PG job must confirm.
- tests/test_spiffe_worker.py: collection error on Windows, excluded from the set; not investigated (not in lane scope).
- Fresh DB: `alembic upgrade head` exit 0 (202611020000 applied); `alembic check`: "No new upgrade operations detected." (exit 0).
- Ruff check and format --check on touched files: pass.
- Not run: mypy on touched Python, full tests/ unit suite, frontend, Go.
- tests/integration/test_aud197_198_notification_outbox_postgres.py: 22 errors here (asyncpg/asyncio timeouts on Windows Proactor; in Linux runner ConnectionRefused, probably a service not running). Not verified.

## Producer inventory for AUD-360 (tenant-scoped tables with ue_rls_assign_tenant trigger: chats, events, groups, messages, news, notifications, schedule, stories, users)
Runtime ORM maps tenant_id only for users (app/core/db/retained_table_metadata.py treats others as migration-owned; a runtime mapping elsewhere is rejected at line 274). Writers that rely on the baseline stamping trigger under a session tenant:
- app/repositories/user_repository.py:536 (User aggregate, registration) - ORM, stamped via users.tenant_id
- app/repositories/chat_repository.py:627,645 (Chat) - trigger
- app/services/chat/command_service.py:505,833 (Message) - trigger (owned by chat lane, not edited)
- app/services/notifications/delivery.py:571 (insert Notification, multi-row core insert) - trigger; tenant from worker context (outbox metadata)
- app/repositories/news_repository.py, event_repository.py, schedule/story repositories: no tenant-table constructor found in grep; not exhaustively traced.
Gap closed: app/cli/db.py create-admin ran with no tenant (unowned, invisible under RLS); now stamped with settings.mvp_tenant_id.
Recorded residual: writes under the bypass role with no session tenant (no GUC, trigger cannot stamp) stay NULL and are hidden from tenants; owned test asserts this so producers must write tenant_id explicitly.

## Changed files (this lane)
- app/cli/db.py (+ settings import, tenant_id=settings.mvp_tenant_id)
- tests/test_aud360_producer_tenant_stamping.py (new)
- tests/test_aud454_websocket_membership_race.py (+1 test)
- tests/integration/test_aud277_360_450_tenant_rls_postgres.py (+3 tests, notifications grant added to fixture)
- Reverted, net zero: app/models/notifications.py, app/services/notifications/delivery.py, tests/fixtures/database/database.py
- Not changed: app/core/tenant.py, app/core/middleware/tenant.py, app/core/db/listeners.py, app/api/ws/connection_manager.py, infrastructure/postgres-roles/bootstrap-app-roles.sql, alembic baseline.

## Blocked / needs owner
- AUD-272: baseline still has `uq_notification_delivery_once UNIQUE (notification_id, channel, subscription_id, attempted_at)` on notification_deliveries. Removing it is a baseline schema change: stopped, not done (ADR-051).
- AUD-360: bypass-role writes without tenant_id remain unowned (see residual); requires producer audit beyond this lane for the remaining repositories.
- Owned-PG fixture tests on Windows: needs hosted job.
