$integrationShardArgs = @()
$integrationShardId = [int]$env:INTEGRATION_SHARD_ID
$integrationNumShards = [int]$env:INTEGRATION_NUM_SHARDS
if ($integrationShardId -ge 0 -or $integrationNumShards -ne 1) {
  if ($integrationShardId -lt 0 -or $integrationShardId -ge $integrationNumShards -or $integrationNumShards -lt 1) {
    throw "Invalid integration shard configuration: id=$integrationShardId total=$integrationNumShards"
  }
  $integrationShardArgs = @(
    "--shard-id=$integrationShardId",
    "--num-shards=$integrationNumShards"
  )
}

# pytest-timeout 2.4.0 supports this only as a caller option,
# not a marker keyword. Keep receipt watchdogs active in debuggers.
$pytestArgs = @(
  "--timeout-disable-debugger-detection",
  $env:INTEGRATION_TEST_PATTERN,
  "tests/test_events_localization.py",
  "tests/test_user_analytics_window_contracts.py",
  "tests/test_migrations_runtime.py",
  "tests/test_query_plans.py",
  "tests/test_backend_p2_correctness_regressions.py::test_chat_list_cursor_uses_the_same_ordering_key_as_the_page",
  "tests/test_backend_p2_correctness_regressions.py::test_chat_and_message_pages_follow_complete_ordering_keys",
  "tests/test_news_repository_db.py::test_comment_service_commits_create_and_edit_across_sessions",
  "tests/test_news_repository_db.py::test_comment_delete_commits_across_sessions_and_preserves_creation_outbox",
  "-v",
  "--tb=short",
  "-x"
)
$pytestArgs += $integrationShardArgs
$pytestArgs += @(
  "--ignore=tests/performance",
  "--ignore=tests/test_schemathesis_api.py"
)
# The canonical PR integration suite is unsharded. Capture
# these existing PostgreSQL proofs without rerunning them.
$requireBaselineReceipt = $integrationNumShards -eq 1 -and $env:INTEGRATION_TEST_PATTERN -eq "tests/integration/"
if ($requireBaselineReceipt) {
  $receiptName = "baseline-equivalence-" + [guid]::NewGuid().ToString("N") + ".xml"
  $baselineReceipt = Join-Path $env:RUNNER_TEMP $receiptName
  $pytestArgs += "--junitxml=$baselineReceipt"
}
uv run python scripts/quality/run_owned_redis_contracts.py @pytestArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($requireBaselineReceipt) {
  $receiptValidator = @'
import sys
from xml.etree import ElementTree

expected = {'tests.integration.test_mvp_baseline_schema_equivalence': ('test_proof_owned_fixture_never_uses_default_database',
                                                            'test_absent_pre_squash_commit_fails_with_a_clear_message',
                                                            'test_pre_squash_chain_and_baseline_stamp_their_own_heads',
                                                            'test_statement_level_schema_differs_only_by_the_audited_additions',
                                                            'test_catalog_facts_outside_the_additions_are_identical',
                                                            'test_no_permissive_using_true_policy_exists_on_any_rls_table',
                                                            'test_baseline_database_matches_the_current_models',
                                                            'test_baseline_refuses_downgrade_and_keeps_its_revision',
                                                            'test_baseline_refuses_nonempty_schema_before_ddl',
                                                            'test_baseline_refuses_populated_pgx_namespace'),
 'tests.integration.test_aud277_360_450_tenant_rls_postgres': ('test_no_permissive_true_policy_remains_on_core_tables',
                                                               'test_tenant_session_sees_only_its_rows_and_never_null_rows',
                                                               'test_guc_bypass_cannot_expose_other_tenants_or_null_rows',
                                                               'test_dedicated_bypass_role_member_sees_every_row',
                                                               'test_ordinary_writes_are_stamped_with_the_session_tenant',
                                                               'test_news_service_producer_is_stamped_and_rls_scoped',
                                                               'test_writes_cannot_target_another_tenant_or_escape_the_session',
                                                               'test_messages_need_both_participation_and_the_session_tenant',
                                                               'test_every_tenant_table_forces_rls_and_stamps_unowned_inserts',
                                                               'test_notification_producer_rows_are_owned_by_the_session_tenant',
                                                               'test_worker_bypass_producer_must_write_its_tenant_explicitly',
                                                               'test_bypass_scheduler_persists_owned_reminders_and_outbox_events',
                                                               'test_transaction_local_bypass_guc_is_cleared_by_rollback_on_same_backend',
                                                               'test_permissive_true_causality_depends_on_restrictive_tenant_policy',
                                                               'test_mfa_reset_real_producer_uses_target_owner_under_bypass[True-]',
                                                               'test_mfa_reset_real_producer_uses_target_owner_under_bypass[True-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb]',
                                                               'test_mfa_reset_real_producer_uses_target_owner_under_bypass[False-]',
                                                               'test_mfa_reset_real_producer_uses_target_owner_under_bypass[False-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb]',
                                                               'test_create_admin_real_producer_scopes_create_and_reset[empty]',
                                                               'test_create_admin_real_producer_scopes_create_and_reset[foreign]',
                                                               'test_create_admin_real_producer_rejects_foreign_email[foreign]',
                                                               'test_create_admin_real_producer_rejects_foreign_email[null]',
                                                               'test_create_admin_real_producer_requires_active_tenant[missing]',
                                                               'test_create_admin_real_producer_requires_active_tenant[inactive]',
                                                               'test_create_admin_real_producer_rejects_unconfigured_tenant',
                                                               'test_weekly_cleanup_preserves_rls_hidden_subscriptions[normal-empty]',
                                                               'test_weekly_cleanup_preserves_rls_hidden_subscriptions[normal-a]',
                                                               'test_weekly_cleanup_preserves_rls_hidden_subscriptions[normal-b]',
                                                               'test_weekly_cleanup_preserves_rls_hidden_subscriptions[python-bypass-empty]',
                                                               'test_weekly_cleanup_preserves_rls_hidden_subscriptions[python-bypass-a]',
                                                               'test_weekly_cleanup_preserves_rls_hidden_subscriptions[python-bypass-b]',
                                                               'test_weekly_cleanup_schema_drift_rejects_before_stale_delete[missing-fk]',
                                                               'test_weekly_cleanup_schema_drift_rejects_before_stale_delete[shadow-child]',
                                                               'test_weekly_cleanup_schema_drift_rejects_before_stale_delete[shadow-parent]',
                                                               'test_schedule_service_parent_ownership[create-a]',
                                                               'test_schedule_service_parent_ownership[create-b]',
                                                               'test_schedule_service_parent_ownership[create-null]',
                                                               'test_schedule_service_parent_ownership[create-missing]',
                                                               'test_schedule_service_parent_ownership[move-a]',
                                                               'test_schedule_service_parent_ownership[move-b]',
                                                               'test_schedule_service_parent_ownership[move-null]',
                                                               'test_schedule_service_parent_ownership[move-missing]',
                                                               'test_schedule_service_parent_ownership[unchanged-a]',
                                                               'test_schedule_service_parent_ownership[unchanged-b]',
                                                               'test_schedule_service_parent_ownership[unchanged-null]'),
 'tests.integration.test_aud262_receipt_schema_postgres': ('test_receipt_upgrade_creates_exact_catalog_and_forces_owner_rls',
                                                           'test_receipt_rls_hides_other_owners_and_rejects_forged_writes[empty]',
                                                           'test_receipt_rls_hides_other_owners_and_rejects_forged_writes[peer]',
                                                           'test_receipt_rls_hides_other_owners_and_rejects_forged_writes[outsider]',
                                                           'test_receipt_rls_revokes_owner_access_after_membership_removal',
                                                           'test_receipt_rls_inherits_parent_chat_tenant_visibility',
                                                           'test_receipt_unique_scope_allows_other_chat_and_sender',
                                                           'test_expired_receipt_has_no_global_visibility_or_implicit_deletion',
                                                           'test_receipt_foreign_key_lifecycle_preserves_message_deletion_marker[messages]',
                                                           'test_receipt_foreign_key_lifecycle_preserves_message_deletion_marker[users]',
                                                           'test_receipt_foreign_key_lifecycle_preserves_message_deletion_marker[chats]',
                                                           'test_receipt_baseline_downgrade_refuses_without_losing_committed_history',
                                                           'test_receipt_owned_fixture_never_uses_default_database',
                                                           'test_notification_pair_claims_commit_conflict_and_rollback_on_owned_postgres',
                                                           'test_notification_pair_ledger_is_unique_without_attempt_constraint'),
 'tests.integration.test_group_list_tenant_http_postgres': ('test_mixed_scope_group_http_a_then_b',
                                                            'test_mixed_scope_group_http_a_then_unscoped[anonymous]',
                                                            'test_mixed_scope_group_http_a_then_unscoped[unsigned-hint]',
                                                            'test_mixed_scope_group_http_a_then_unscoped[bad-signature]',
                                                            'test_mixed_scope_group_http_unscoped_then_a',
                                                            'test_group_http_ignores_legacy_foreign_cache',
                                                            'test_group_http_observes_committed_change[rename]',
                                                            'test_group_http_observes_committed_change[delete]',
                                                            'test_mvp_group_http_anonymous_uses_configured_tenant',
                                                            'test_mvp_group_http_foreign_identity_rejected_before_session'),
 'tests.integration.test_dlq_retry_postgres': ('test_retry_completed_job_waits_for_worker_and_preserves_state',
                                               'test_aud447_dedup_waits_for_worker_refreshes_and_leaves_commit_to_caller')}
root = ElementTree.parse(sys.argv[1]).getroot()
for classname, names in expected.items():
    cases = [
        case for case in root.iter("testcase")
        if case.get("classname") == classname
    ]
    observed = [case.get("name") for case in cases]
    if (
        len(cases) != len(names)
        or set(observed) != set(names)
        or any(
            case.find(status) is not None
            for case in cases
            for status in ("skipped", "failure", "error")
        )
    ):
        raise SystemExit(f"PostgreSQL cohort receipt incomplete or unsuccessful: {classname}")
print(f"INTEGRATION_POSTGRES_COHORT_VERIFIED_PASS {sum(map(len, expected.values()))}")
'@
  uv run --frozen --no-sync python -c $receiptValidator $baselineReceipt
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
