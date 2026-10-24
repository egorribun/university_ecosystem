"""Contract for allocating the hermetic NATS transport suite outside the backend preflight."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
import yaml

from scripts import owned_nats_process as process
from scripts.owned_nats_outage import Deadline

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BACKEND_WORKFLOW = ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
TRANSPORT_TEST = ROOT / "tests" / "test_live_nats_transport.py"
TRANSPORT_SELECTOR = "tests/test_live_nats_transport.py"
FULL_BACKEND_REUSABLE_CONTRACT_SELECTOR = "tests/test_full_backend_reusable_contract.py"
HEALTH_ENDPOINT_SELECTORS = (
    "tests/test_health_endpoint.py::test_healthcheck_tiered_cache_reports_shared_layer_failure",
    "tests/test_health_endpoint.py::test_healthcheck_storage_probe_recovers_errors_and_caps_success_cache",
)
NATS_CHECKPOINT_SELECTORS = (
    "tests/test_owned_nats_outage_coordinator.py::test_invalid_broker_probe_has_distinct_finite_checkpoint",
    "tests/test_owned_nats_outage_cli.py::test_main_renders_broker_receipt_checkpoint_without_private_evidence",
)
CONSUMER_RUNNER = 'consumer_root="$cohort_root/consumer"'
POLICY_RUNNER = 'policy_root="$cohort_root/security-disposition"'


def _step(steps: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(step for step in steps if step.get("name") == name)


def test_transport_suite_moves_to_contract_job_and_stays_in_full_backend_universe() -> (
    None
):
    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    reusable = yaml.safe_load(BACKEND_WORKFLOW.read_text(encoding="utf-8"))

    frozen_rc = _step(
        reusable["jobs"]["unit-tests"]["steps"],
        "Verify frozen-RC contracts and complete validator coverage",
    )
    assert TRANSPORT_SELECTOR not in frozen_rc["run"].split()

    contract_run = _step(
        ci["jobs"]["contract-tests"]["steps"], "Run contract tests (consumer-side)"
    )["run"]
    policy_verification = _step(
        ci["jobs"]["contract-tests"]["steps"],
        "Verify exact security disposition contracts",
    )
    assert policy_verification["if"] == "${{ !cancelled() }}"
    policy_verification_run = policy_verification["run"]
    assert contract_run.split().count(TRANSPORT_SELECTOR) == 1
    assert contract_run.split().count(FULL_BACKEND_REUSABLE_CONTRACT_SELECTOR) == 1
    assert all(
        contract_run.split().count(selector) == 1
        for selector in HEALTH_ENDPOINT_SELECTORS
    )
    assert all(
        contract_run.split().count(selector) == 1
        for selector in NATS_CHECKPOINT_SELECTORS
    )
    assert ' -k "not integration"' in contract_run
    assert ci["jobs"]["contract-tests"]["timeout-minutes"] == 10
    assert contract_run.count('wait "$consumer_pid"') == 1
    assert contract_run.count('wait "$policy_pid"') == 1
    assert "consumer_status != 0 || policy_status != 0" in contract_run
    assert (
        "uv run --frozen --no-sync pytest tests/test_verify_secrets_baseline.py -v"
        in contract_run
    )
    assert contract_run.count("tests/test_verify_secrets_baseline.py") == 1
    assert (
        "exec uv run --frozen --no-sync pytest tests/test_verify_secrets_baseline.py"
        in contract_run
    )
    assert '--basetemp="$1"' in contract_run
    assert '--junitxml="$2"' in contract_run
    assert contract_run.count("setsid env") == 2
    assert CONSUMER_RUNNER in contract_run
    assert POLICY_RUNNER in contract_run
    assert (
        'cohort_root="$RUNNER_TEMP/contract-tests-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"'
        in contract_run
    )
    assert 'mkdir -p "$consumer_root/tmp" "$policy_root/tmp"' in contract_run
    assert "trap cleanup_contract_processes EXIT" in contract_run
    assert "trap 'exit 130' INT" in contract_run
    assert "trap 'exit 143' TERM" in contract_run
    assert "trap 'exit 129' HUP" in contract_run
    assert (
        'terminate_contract_process_groups "$consumer_pid" "$policy_pid"'
        in contract_run
    )
    assert 'kill -0 -- "-$process_pid"' in contract_run
    assert 'kill -TERM -- "-$process_pid"' in contract_run
    assert 'kill -KILL -- "-$process_pid"' in contract_run
    assert 'wait "$process_pid"' in contract_run
    assert "grace_tick < 20" in contract_run
    assert "sleep 0.1" in contract_run
    assert 'TMPDIR="$consumer_root/tmp"' in contract_run
    assert 'TMPDIR="$policy_root/tmp"' in contract_run
    assert '"$consumer_root/basetemp"' in contract_run
    assert '"$consumer_root/junit.xml"' in contract_run
    assert '"$policy_root/basetemp"' in contract_run
    assert '"$policy_root/junit.xml"' in contract_run
    assert 'tee "$3"' in contract_run
    assert '"$consumer_root/pytest.log"' in contract_run
    assert '"$policy_root/pytest.log"' in contract_run
    assert '"$policy_root/status"' in contract_run
    assert (
        '[[ ! -f "$policy_root/status" || ! -f "$policy_root/pytest.log" ]]'
        in policy_verification_run
    )
    assert 'cat "$policy_root/pytest.log"' in policy_verification_run
    assert 'policy_status="$(cat "$policy_root/status")"' in policy_verification_run
    assert 'if [[ "$policy_status" != "0" ]]' in policy_verification_run
    first_runner = contract_run.index("setsid env")
    consumer_runner = contract_run[
        first_runner : contract_run.index("consumer_pid=$!", first_runner)
    ]
    second_runner = contract_run.index("setsid env", first_runner + 1)
    policy_runner = contract_run[
        second_runner : contract_run.index("policy_pid=$!", second_runner)
    ]
    distinct_runner_paths = (consumer_runner, policy_runner)
    assert len(distinct_runner_paths) == 2
    for left, right in (
        ("consumer_root/tmp", "policy_root/tmp"),
        ("consumer_root/basetemp", "policy_root/basetemp"),
        ("consumer_root/junit.xml", "policy_root/junit.xml"),
        ("consumer_root/pytest.log", "policy_root/pytest.log"),
    ):
        assert left in distinct_runner_paths[0]
        assert right in distinct_runner_paths[1]
        assert left != right
    assert "integration" not in TRANSPORT_TEST.read_text(encoding="utf-8").lower()

    backend_call = ci["jobs"]["backend-tests"]["with"]
    assert backend_call["test-pattern"] == "tests/"
    assert backend_call["num-shards"] == 4
    assert backend_call["coverage-threshold"] == 0

    unit_steps = reusable["jobs"]["unit-tests"]["steps"]
    pytest_step = _step(unit_steps, "Run pytest")
    assert pytest_step["env"]["PYTEST_SHARD_MANIFEST"] == (
        "artifacts/coverage/python/pytest-shard-${{ inputs.shard-id }}.json"
    )
    assert "--cov=app" in pytest_step["run"]
    assert "--cov=alembic/versions" in pytest_step["run"]
    assert "--junitxml=pytest-report.xml" in pytest_step["run"]
    assert "--ignore=tests/test_schemathesis_api.py" in pytest_step["run"]
    assert "--ignore=tests/test_live_nats_transport.py" not in pytest_step["run"]

    provenance = _step(unit_steps, "Write backend shard coverage provenance")["run"]
    assert "pytest-node-manifest" in provenance
    assert "pytest-shard-$SHARD_ID.json" in provenance
    raw_upload = _step(unit_steps, "Upload raw coverage data for aggregation")["with"][
        "path"
    ]
    assert "pytest-shard-${{ inputs.shard-id }}.json" in raw_upload
    junit_upload = _step(unit_steps, "Upload pytest report")["with"]["path"]
    assert junit_upload == "pytest-report.xml"

    aggregate_steps = ci["jobs"]["coverage-policy-gate"]["steps"]
    names = [step.get("name") for step in aggregate_steps]
    assert names.index("Verify backend test-universe manifests") < names.index(
        "Combine Python shard coverage"
    )


# Ordered argv population from 1a3954e99f06bf7b1660ad2df609a84b022daefa.
# Preserve all 136 original selectors, including intentional file/node overlaps.
# Twenty-six explicit selections follow that unchanged prefix: existing audit
# regressions, Gitleaks diagnostics, WebSocket/migration safety, logging/email,
# inventory and repaired orchestrator verification. Do not shrink this scope.
_CONSUMER_SELECTORS = (
    "tests/contracts/",
    "tests/test_live_stand_cleanup_profile_contract.py",
    "tests/test_live_nats_transport.py",
    "tests/test_owned_nats_outage_cli.py",
    "tests/test_owned_nats_outage_cli.py::test_main_renders_broker_receipt_checkpoint_without_private_evidence",
    "tests/test_owned_nats_outage_coordinator.py::test_public_result_and_logs_contain_only_closed_labels",
    "tests/test_owned_nats_outage_coordinator.py::test_runtime_checkpoint_distinguishes_callback_and_inventory_rejection",
    "tests/test_owned_nats_outage_coordinator.py::test_invalid_broker_probe_has_distinct_finite_checkpoint",
    "tests/test_owned_nats_outage_coordinator.py::test_broker_receipt_cannot_hide_final_owner_or_inventory_drift",
    "tests/test_owned_nats_outage_coordinator.py::test_coordinator_requires_exact_raw_broker_receipt",
    "tests/test_owned_nats_outage_coordinator.py::test_valid_path_binds_exact_event_and_restores_before_drain",
    "tests/test_owned_nats_docker_context_pins.py",
    "tests/test_owned_nats_runtime_adapter.py",
    "tests/test_owned_nats_transport_port.py",
    "tests/test_spotify_fallback.py",
    "tests/test_api_dlq.py",
    "tests/test_event_create_api_fix.py",
    "tests/test_event_time_constraints.py::test_internal_partial_time_update_uses_the_stored_time_pair",
    "tests/test_audit_timetravel.py",
    "tests/test_audit_service_closure.py",
    "tests/test_audit_service.py",
    "tests/test_admin_audit_closure.py",
    "tests/test_docker_startup_contracts.py::test_migrations_disable_inherited_backend_runtime_healthcheck",
    "tests/test_docker_startup_contracts.py::test_ci_caddy_smokes_use_the_pinned_project_runtime",
    "tests/test_security_hardening_workflow_contract.py::test_security_audit_checkouts_disable_credentials_and_detect_secrets_is_locked",
    "tests/test_quality_configuration.py::test_virtualenv_security_floor_is_dev_only_and_locked",
    "tests/test_dependency_audit_contract.py::test_storybook_security_floor_and_aligned_lock",
    "tests/test_cli_infra_closure.py",
    "tests/test_check_mypy_budget.py",
    "tests/test_periodic_task_metrics.py",
    "tests/test_security_hardening_workflow_contract.py::test_npm_failure_metadata_is_diagnostic_only_and_keeps_audit_blocking",
    "tests/test_gitleaks_hygiene_contract.py::test_gitleaks_workflow_pins_complete_graph_scanner_and_redacted_artifact",
    "tests/test_units.py::test_api_version_constants",
    "tests/test_task_registry_closure.py",
    "tests/test_database_pool_lifecycle.py",
    "tests/test_database_metrics.py",
    "tests/test_database_closure.py::test_pool_metrics_snapshot_and_peak_property",
    "tests/test_database_runtime_paths.py::test_pool_health_metrics_properties",
    "tests/test_database_runtime_paths.py::test_pool_health_monitoring_callbacks",
    "tests/test_mutation_regressions.py::test_database_invalidation_keeps_structured_log_message",
    "tests/test_mutation_regressions.py::test_database_invalidation_without_exception_uses_none_type_marker",
    "tests/test_news_api_closure.py::test_comment_news_sanitizes_content_like_patch_update",
    "tests/test_news_api_closure.py::test_comment_news_rejects_overlong_content_before_write",
    "tests/test_news_api_closure.py::test_comment_news_rejects_content_sanitized_to_empty",
    "tests/test_cache_settings_closure.py::test_cache_warmup_properties_preserve_uuid_ids_and_skip_invalid_tokens",
    "tests/test_cache_settings_closure.py::test_cache_warmup_uuid_ids_load_from_environment",
    "tests/test_cache_settings_closure.py::test_cache_warmup_properties_coerce_and_deduplicate_values",
    "tests/test_cache_settings_closure.py::test_cache_warmup_properties_handle_empty_and_iterable_inputs",
    "tests/test_cache_warmup.py::test_warm_schedule_fans_out_per_group",
    "tests/test_cache_warmup.py::test_warm_stats_fans_out_per_user_period",
    "tests/test_exception_handlers_and_request_ids.py::test_asgi_json_problem_emits_problem_json",
    "tests/test_exception_handlers.py::TestAsgiJsonProblem::test_with_custom_headers",
    "tests/test_exception_handlers_branch_coverage_test.py::test_asgi_json_problem_detail_text",
    "tests/test_live_stand.py::test_live_caddy_probe_deadline_covers_final_container_recheck",
    "tests/test_workflow_fail_closed_contracts.py::test_literal_continue_on_error_cases_are_exhaustively_classified",
    "tests/test_start_docker_live_stand_core_readiness.py::test_live_readiness_loop_uses_core_and_preserves_full_inventories",
    "tests/test_notifications_cleanup_closure.py",
    "tests/test_chat_repository_coverage.py::test_find_existing_dm_returns_chat_for_pair",
    "tests/test_chat_repository_coverage.py::test_find_existing_dm_none_when_no_shared_chat",
    "tests/test_chat_repository_coverage.py::test_find_existing_dm_ignores_two_member_group",
    "tests/test_news_repository_db.py::test_anonymous_interactions_never_use_email_as_comment_name",
    "tests/test_notifications_news_events_db.py::test_comment_notification_uses_real_profile_name_without_email",
    "tests/test_localization_core_closure.py::test_missing_resource_not_found_keys_return_localized_404_details",
    "tests/test_chat_reaction_emoji_validation.py::test_reaction_input_accepts_qualified_unicode_emoji_sequences",
    "tests/test_chat_reaction_emoji_validation.py::test_reaction_input_rejects_text_multiple_or_invalid_sequences",
    "tests/test_chat_reaction_emoji_validation.py::test_reaction_creation_is_strict_but_legacy_lookup_and_delete_remain",
    "tests/test_health_api_closure.py::test_healthz_tiered_cache_reports_unavailable_shared_layer",
    "tests/test_health_api_closure.py::test_storage_probe_uses_short_outcome_ttls_and_recovers",
    "tests/test_schedule_reminders_closure.py::test_build_schedule_reminder_formats_resolved_occurrence_in_campus_timezone",
    "tests/test_notifications_news_events_closure.py::test_event_notification_times_use_campus_timezone",
    "tests/test_ws_connection_manager_closure.py::test_send_to_user_uses_real_websocket_json_boundary",
    "tests/test_aud350_frozen_migration_fixture.py",
    "tests/test_quality_inventory.py::test_typescript_import_after_jsx_keeps_exact_source_relationship",
    "tests/test_quality_inventory.py::test_typescript_non_code_jsx_and_regex_do_not_claim_source_ownership",
    "tests/test_quality_inventory.py::test_typescript_dotted_module_stem_resolves_exact_config_file",
    "tests/test_quality_inventory.py::test_typescript_glob_scan_links_only_files_it_recursively_reads",
    "tests/test_quality_inventory.py::test_typescript_glob_scan_rejects_unproven_traversal_or_reads",
    "tests/test_quality_inventory.py::test_typescript_glob_scan_does_not_follow_external_file_symlinks",
    "tests/test_quality_inventory.py::test_python_contract_accepts_verified_test_root_alias",
    "tests/test_quality_inventory.py::test_python_contract_rejects_rebound_test_root_alias",
    "tests/test_quality_inventory.py::test_go_duplicate_checker_ignores_comments_and_literals",
    "tests/test_quality_inventory.py::test_go_duplicate_checker_still_rejects_real_duplicate_declarations",
    "tests/test_quality_inventory.py::test_python_duplicate_scopes",
    "tests/test_quality_inventory.py::test_python_duplicate_checker_scopes_nested_functions_independently",
    "tests/test_quality_inventory.py::test_python_duplicate_checker_detects_async_and_mixed_same_scope_duplicates",
    "tests/test_graphql.py::test_backend_graphql_paths_return_not_found",
    "tests/test_cdc_safety.py::test_cdc_opt_in_fails_before_lifespan_resources",
    "tests/test_cdc_safety.py::test_cdc_opt_in_fails_before_background_tasks_or_polling_selection",
    "tests/test_cdc_safety.py::test_standalone_cdc_fails_before_connecting_or_provisioning",
    "tests/test_configuration_reference.py",
    "tests/test_benchmark_capture_activation_workflow.py",
    "tests/test_management_scripts.py::test_mfa_reset_parser_preserves_uuid_and_notification_choice",
    "tests/test_management_scripts.py::test_mfa_reset_parser_rejects_non_uuid_ids",
    "tests/test_management_scripts.py::test_mfa_reset_parser_keeps_email_and_mutual_exclusion",
    "tests/test_management_scripts.py::test_load_user_by_id",
    "tests/test_security_hardening_workflow_contract.py::test_ci_scanner_bootstraps_are_version_pinned_and_checksum_verified",
    "tests/test_full_backend_reusable_contract.py",
    "tests/test_kyverno_registry_source_binding.py",
    "tests/test_kyverno_registry_owner_review_b.py",
    "tests/test_live_acceptance_workflow.py::test_live_stand_nats_outage_dispatches_once_and_redacts_failures",
    "tests/test_ci_check_catalog.py",
    "tests/test_dependency_resolution_policy.py",
    "tests/test_cache_settings_closure.py",
    "tests/test_check_no_python2_except.py",
    "tests/test_health_endpoint.py::test_healthcheck_tiered_cache_reports_shared_layer_failure",
    "tests/test_health_endpoint.py::test_healthcheck_storage_probe_recovers_errors_and_caps_success_cache",
    "tests/test_geolocation.py::test_geolocation_service_init_success",
    "tests/test_aud469_partition_scheduler_resilience.py",
    "tests/test_chat_query_projection_regressions.py::test_message_history_projects_page_senders_in_one_public_profile_query",
    "tests/test_chat_query_projection_regressions.py::test_message_sender_profiles_empty_batch_skips_database",
    "tests/test_chat_query_service.py::TestGetMessages::test_not_participant",
    "tests/test_chat_query_service.py::TestGetMessages::test_empty_messages",
    "tests/test_chat_query_service.py::test_message_sender_output_filters_legacy_producer_fields",
    "tests/test_aud252_compose_file_secrets.py::test_production_profile_renders_only_file_backed_secret_sources",
    "tests/test_aud252_compose_file_secrets.py::test_production_render_fails_when_required_secret_path_or_key_id_is_missing",
    "tests/test_quality_workflow_contract.py::test_aud257_postgres_regression_has_explicit_pg_routing",
    "tests/test_quality_workflow_contract.py::test_frozen_rc_preflight_uses_bounded_parallel_merged_coverage",
    "tests/test_image_proxy_closure.py::test_process_image_avif_real_codec_round_trip",
    "tests/test_images_v2.py::test_pillow_thumbnail_real_codec_preserves_transparency",
    "tests/test_live_stand.py::test_live_caddy_real_reader_failure_diagnostics_and_final_pin_precedence",
    "tests/test_live_stand.py::test_live_bounded_reader_accepts_exact_combined_cap_and_preserves_exit_status",
    "tests/test_live_stand.py::test_live_bounded_read_failure_reason_is_finite",
    "tests/test_live_stand.py::test_live_reset_registration_parser_accepts_only_six_unique_pairs",
    "tests/test_live_stand.py::test_live_reset_registration_parser_rejects_untrusted_framing",
    "tests/test_live_stand.py::test_live_reset_registration_runner_uses_failure_stdout_only",
    "tests/test_live_stand.py::test_live_caddy_probe_excludes_oversized_gap_between_project_windows",
    "tests/test_live_stand.py::test_live_caddy_probe_coalesces_only_overlapping_or_touching_windows",
    "tests/test_live_stand.py::test_live_caddy_probe_disjoint_reads_share_bytes_and_capture_time",
    "tests/test_live_stand.py::test_live_caddy_probe_disjoint_captures_keep_cross_window_validation",
    "tests/test_live_stand.py::test_live_caddy_disjoint_real_reads_enforce_aggregate_cap",
    "tests/test_live_stand.py::test_live_caddy_disjoint_reads_preserve_record_boundaries",
    "tests/test_live_stand.py::test_live_caddy_disjoint_capture_deadline_prevents_second_read",
    "tests/test_live_stand.py::test_live_caddy_disjoint_second_read_failure_preserves_cleanup",
    "tests/test_live_stand.py::test_live_caddy_capture_deadline_cannot_be_rebased_during_reader_admission",
    "tests/test_live_stand.py::test_live_caddy_probe_reads_one_union_window_from_reverified_pinned_container",
    "tests/test_live_stand.py::test_live_caddy_probe_brackets_one_union_read_within_the_shared_deadline",
    "tests/test_health_api_closure.py::test_healthz_brief_cache_hit_filters_full_payload",
    "tests/test_logging_pii_redaction_contract.py",
    "tests/test_cwv_rum_security.py",
    "tests/test_gitleaks_hygiene_contract.py",
    "tests/test_websocket_closure.py",
    "tests/test_migration_148642dd1207_safety.py",
    "tests/test_logging_object_redaction_contract.py",
    "tests/test_logging_contract_closure.py",
    "tests/test_logging_core.py",
    "tests/test_logging_test_isolation.py",
    "tests/test_email_utils.py",
    "tests/test_email_utils_full.py",
    "tests/test_utils_email.py",
    "tests/test_quality_inventory.py::test_aud508_dynamic_skip_syntax_is_detected",
    "tests/test_quality_inventory.py::test_aud508_skip_exemptions_require_real_comment_evidence",
    "tests/test_quality_inventory.py::test_aud509_source_matching_requires_exact_module_relationships",
    "tests/test_quality_inventory.py::test_aud509_go_test_matches_its_same_package_without_a_sibling_name",
    "tests/test_quality_inventory.py::test_aud509_go_external_test_requires_exact_package_ownership",
    "tests/test_quality_inventory.py::test_aud509_imports_match_only_the_exact_inventoried_module",
    "tests/test_quality_inventory.py::test_aud509_typescript_import_must_resolve_to_an_inventoried_module",
    "tests/test_quality_inventory.py::test_aud509_relative_python_import_resolves_inside_its_package",
    "tests/test_quality_inventory.py::test_aud509_python_name_match_prefers_exact_and_rejects_ambiguity",
    "tests/test_quality_inventory.py::test_aud508_non_python_skip_scanner_ignores_comments_and_strings",
    "tests/test_quality_inventory.py::test_aud508_non_python_skip_accepts_tracking_comments",
    "tests/test_quality_inventory.py",
    "tests/test_migration_148642dd1207_orchestrator.py::test_upgrade_with_unavailable_inspector_exposes_later_unconditional_lookup",
)
_DISPATCH_PROBE = """\
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
cohort = (
    "security-disposition"
    if "tests/test_verify_secrets_baseline.py" in args
    else "consumer"
)
record = {
    "args": args,
    "temp": [os.environ.get(key) for key in ("TMPDIR", "TMP", "TEMP")],
    "pgid": os.getpgid(0),
    "pact_tracking": os.environ.get("PACT_DO_NOT_TRACK"),
}
destination = Path(os.environ["CONTRACT_DISPATCH_RECORDS"])
(destination / f"{cohort}.json").write_text(json.dumps(record), encoding="utf-8")
junit = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--junitxml="))
Path(junit).write_text('<testsuite tests="1"/>', encoding="utf-8")
print(f"{cohort}-output", flush=True)
variable = "CONSUMER_TEST_STATUS" if cohort == "consumer" else "POLICY_TEST_STATUS"
raise SystemExit(int(os.environ[variable]))
"""


def _run_contract_dispatch(
    tmp_path: Path,
    script: str,
    *,
    consumer_status: int = 0,
    policy_status: int = 0,
) -> tuple[process.PrivateProcessResult, Path, dict[str, dict[str, object]]]:
    """Run the real orchestration; replace only the expensive pytest boundary."""
    bash = shutil.which("bash")
    if os.name != "posix" or bash is None or shutil.which("setsid") is None:
        pytest.fail("Contract dispatch requires Linux/POSIX, Bash, and setsid")
    binaries = tmp_path / "bin"
    records = tmp_path / "dispatch"
    binaries.mkdir()
    records.mkdir()
    uv = binaries / "uv"
    uv.write_text(f"#!{sys.executable}\n{_DISPATCH_PROBE}", encoding="utf-8")
    uv.chmod(0o700)
    environment = {
        "PATH": f"{binaries}{os.pathsep}{os.environ.get('PATH', '')}",
        "RUNNER_TEMP": str(tmp_path / "runner"),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "CONTRACT_DISPATCH_RECORDS": str(records),
        "CONSUMER_TEST_STATUS": str(consumer_status),
        "POLICY_TEST_STATUS": str(policy_status),
    }
    result = process.run_private_process(
        process.PrivateProcessRequest(
            argv=(str(Path(bash).resolve()), "--noprofile", "--norc", "-c", script),
            cwd=str(tmp_path),
            env=environment,
            stdout_limit=32 * 1024,
            stderr_limit=16 * 1024,
            input_limit=0,
        ),
        deadline=Deadline.after(20, clock=time.monotonic),
    )
    assert result.outcome is process.ProcessOutcome.EXITED, result
    assert result.local_cleanup is process.LocalCleanup.CONFIRMED, result
    dispatched = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in records.glob("*.json")
    }
    return result, tmp_path / "runner" / "contract-tests-123-1", dispatched


def _assert_contract_dispatch(
    root: Path, dispatched: dict[str, dict[str, object]]
) -> None:
    assert set(dispatched) == {"consumer", "security-disposition"}
    consumer_args = dispatched["consumer"]["args"]
    assert isinstance(consumer_args, list)
    assert consumer_args[:4] == ["run", "--frozen", "--no-sync", "pytest"]
    selectors = [arg for arg in consumer_args[4:] if arg.startswith("tests/")]
    assert tuple(selectors) == _CONSUMER_SELECTORS, (
        "consumer selector population changed"
    )
    consumer_options = [
        arg for arg in consumer_args[4:] if not arg.startswith("tests/")
    ]
    assert consumer_options == [
        "-v",
        "--tb=short",
        "--durations=20",
        "-n",
        "2",
        "--dist",
        "loadfile",
        "-p",
        "no:cacheprovider",
        "-k",
        "not integration",
        f"--basetemp={root / 'consumer' / 'basetemp'}",
        f"--junitxml={root / 'consumer' / 'junit.xml'}",
    ], "consumer dispatch options changed"
    assert dispatched["security-disposition"]["args"] == [
        "run",
        "--frozen",
        "--no-sync",
        "pytest",
        "tests/test_verify_secrets_baseline.py",
        "-v",
        "--tb=short",
        "--durations=20",
        "-p",
        "no:cacheprovider",
        f"--basetemp={root / 'security-disposition' / 'basetemp'}",
        f"--junitxml={root / 'security-disposition' / 'junit.xml'}",
    ]
    for cohort in ("consumer", "security-disposition"):
        assert dispatched[cohort]["temp"] == [str(root / cohort / "tmp")] * 3
        assert (root / cohort / "junit.xml").read_text() == '<testsuite tests="1"/>'
        assert (root / cohort / "pytest.log").read_text() == f"{cohort}-output\n"
    assert dispatched["consumer"]["pact_tracking"] == "true"
    assert dispatched["consumer"]["pgid"] != dispatched["security-disposition"]["pgid"]


@pytest.mark.parametrize("consumer_status,policy_status", [(0, 0), (9, 0), (0, 7)])
def test_contract_runner_bounds_workers_preserves_population_and_propagates_failures(
    tmp_path: Path, consumer_status: int, policy_status: int
) -> None:
    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    job = ci["jobs"]["contract-tests"]
    assert job["timeout-minutes"] == 10
    script = _step(job["steps"], "Run contract tests (consumer-side)")["run"]
    result, root, dispatched = _run_contract_dispatch(
        tmp_path,
        script,
        consumer_status=consumer_status,
        policy_status=policy_status,
    )
    _assert_contract_dispatch(root, dispatched)
    assert result.returncode == int(bool(consumer_status or policy_status)), (
        result.stdout + result.stderr
    )
    assert (root / "security-disposition" / "status").read_text() == (
        f"{policy_status}\n"
    )


@pytest.mark.parametrize(
    "old,new,reason",
    [
        ("-n 2 --dist loadfile", "", "consumer dispatch options changed"),
        ("-n 2 --dist loadfile", "-n 0", "consumer dispatch options changed"),
        (
            "-n 2 --dist loadfile",
            "-n auto --dist loadfile",
            "consumer dispatch options changed",
        ),
        (
            "-n 2 --dist loadfile",
            "-n 3 --dist loadfile",
            "consumer dispatch options changed",
        ),
        (
            "-n 2 --dist loadfile",
            "-n 2 --dist load",
            "consumer dispatch options changed",
        ),
        (
            "tests/test_live_nats_transport.py ",
            "",
            "consumer selector population changed",
        ),
        (
            '-k "not integration"',
            '-k "not integration and not live"',
            "consumer dispatch options changed",
        ),
    ],
    ids=["serial", "zero", "auto", "excess", "split-file", "lost-suite", "filter"],
)
def test_contract_dispatch_rejects_budget_and_population_mutations(
    tmp_path: Path, old: str, new: str, reason: str
) -> None:
    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    script = _step(
        ci["jobs"]["contract-tests"]["steps"], "Run contract tests (consumer-side)"
    )["run"]
    assert script.count(old) == 1
    result, root, dispatched = _run_contract_dispatch(
        tmp_path, script.replace(old, new, 1)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with pytest.raises(AssertionError, match=reason):
        _assert_contract_dispatch(root, dispatched)


def test_contract_dispatch_missing_bash_fails_before_allocating_or_spawning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    real_which = shutil.which
    monkeypatch.setattr(
        shutil,
        "which",
        lambda command: None if command == "bash" else real_which(command),
    )
    spawn_attempts: list[bool] = []

    def forbid_spawn(*_args: object, **_kwargs: object) -> None:
        spawn_attempts.append(True)
        raise AssertionError("missing Bash reached process startup")

    monkeypatch.setattr(process, "run_private_process", forbid_spawn)
    with pytest.raises((pytest.fail.Exception, pytest.skip.Exception)) as failure:
        _run_contract_dispatch(tmp_path, "exit 0")
    assert isinstance(failure.value, pytest.fail.Exception)
    assert "requires Linux/POSIX, Bash, and setsid" in str(failure.value)
    assert spawn_attempts == []
    assert list(tmp_path.iterdir()) == []
