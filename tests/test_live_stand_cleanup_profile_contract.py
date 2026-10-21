from __future__ import annotations

import asyncio
import gc
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests import conftest as project_conftest
from tests.fixtures.database import database as database_fixtures

_REPOSITORY_ROOT = Path(project_conftest.PROJECT_ROOT)
_TARGET_CASES = (
    (
        "tests/test_live_stand.py",
        "test_live_playwright_page_errors_accept_only_fixed_domains",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_http_status_accepts_only_fixed_domains",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_page_errors_accept_admin_hydration_domains",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_email_otp_and_mfa_http_statuses_are_closed",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_auth_http_parser_accepts_closed_status_mismatches",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_story_setup_parser_accepts_closed_stages",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_a11y_contrast_accepts_bounded_closed_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_http_status_accepts_auth_status_checks",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_http_status_rejects_malformed_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_page_errors_reject_malformed_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_push_observation_accepts_closed_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_retry_diagnostics_accept_bounded_integer_decisions",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_counts_reject_malformed_summary_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_auth_status_rows_accept_lf_and_crlf",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_profile_save_diagnostics_reject_malformed_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_retry_diagnostics_reject_malformed_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_page_errors_reject_cross_scenario_domains",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_footer_parser_rejects_malformed_rows",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_counts_accept_all_bounded_summary_categories",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_rate_limit_metadata_rejects_malformed_or_unterminated_rows",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_a11y_contrast_rejects_malformed_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_story_setup_parser_accepts_closed_exception_kinds",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_page_errors_accept_auth_roles_domain",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_a11y_paint_parser_rejects_malformed_rows",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_a11y_phase_parser_rejects_malformed_rows",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_auth_ui_parser_accepts_exact_failure_records",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_auth_registration_parser_rejects_inconsistent_phases",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_rate_limit_metadata_accepts_bounded_logout_headers",
    ),
    (
        "tests/test_live_stand.py",
        "test_live_playwright_counts_accept_numeric_durations",
    ),
    (
        "tests/test_cwv_contract_vectors.py",
        "test_route_group_allowlist_is_complete_and_normalizes_url_delimiters",
    ),
    (
        "tests/test_cwv_contract_vectors.py",
        "test_origin_parser_rejects_credentials_paths_and_non_https_exactly",
    ),
    (
        "tests/test_logging_pii_redaction_contract.py",
        "test_field_names_normalize_across_naming_styles",
    ),
    (
        "tests/test_backup_paired_snapshot_restore.py",
        "test_storage_public_base_url_rejects_unsafe_root_relative_paths",
    ),
    (
        "tests/test_backup_paired_snapshot_restore.py",
        "test_storage_public_base_url_rejects_invalid_unparsed_values",
    ),
    (
        "tests/test_backup_paired_snapshot_restore.py",
        "test_application_storage_key_rejects_keys_outside_app_contract",
    ),
    (
        "tests/test_owned_nats_correlation.py",
        "test_http_message_must_match_intent_and_have_a_canonical_id",
    ),
    (
        "tests/test_owned_nats_correlation.py",
        "test_single_event_requires_exact_type_and_aggregate",
    ),
    (
        "tests/test_owned_nats_correlation.py",
        "test_each_payload_field_is_independently_bound_to_the_message",
    ),
    (
        "tests/test_owned_nats_correlation.py",
        "test_missing_payload_fields_are_not_replaced_by_defaults",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_request_uses_only_explicit_pins",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_request_refuses_unsupported_pins",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_decode_matches_exact_private_metadata",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_decode_refuses_nonexit_outcomes",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_decode_refuses_process_or_payload_ambiguity",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_decode_refuses_missing_or_different_pin",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_boundaries_refuse_unusable_deadline",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_boundaries_refuse_postcheck_expiry",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_boundaries_share_original_deadline",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_private_fields_are_not_represented",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_request_uses_exact_in_place_pins_and_private_environment",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_decode_matches_independent_resource_projection",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_boundaries_refuse_unadmitted_owner",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_prepare_refuses_unreviewed_layout",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_decode_refuses_process_evidence",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_decode_refuses_ambiguous_or_different_json",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_boundaries_keep_the_shared_deadline",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_prepare_snapshots_inputs_before_clock_callback",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_decode_retains_fingerprint_across_clock_callback",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_boundaries_refuse_missing_exact_class_fields",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_decode_refuses_malformed_process_field_types",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_decode_refuses_deeply_nested_private_json",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_decode_enforces_exact_json_container_depth",
    ),
)
_NEAR_MISS_CASES = (
    (
        "tests/test_live_stand.py",
        "test_live_playwright_http_status_auth_session_cap_requires_exact_forbidden_status",
    ),
    (
        "tests/test_live_stand.py",
        "test_route_group_allowlist_is_complete_and_normalizes_url_delimiters",
    ),
    (
        "tests/test_cwv_contract_vectors.py",
        "test_route_group_allowlist_is_complete_and_normalizes_url_delimiters_near_miss",
    ),
    (
        "tests/test_owned_nats_correlation.py",
        "test_exact_query_must_return_one_event_without_latest_row_fallback",
    ),
    (
        "tests/test_owned_nats_outage.py",
        "test_each_payload_field_is_independently_bound_to_the_message",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_compose_observation_collects_exact_request_under_shared_deadline",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_observation_collects_exact_request_once",
    ),
    (
        "tests/test_live_nats_transport.py",
        "test_daemon_decode_matches_exact_private_metadata_near_miss",
    ),
    (
        "tests/test_live_stand.py",
        "test_daemon_decode_matches_exact_private_metadata",
    ),
)
_POLICY_TEST_NAMES = (
    "test_source_delta_rejects_added_marker_in_quoted_path",
    "test_source_delta_parses_forced_text_binary_hunk_with_unicode_separators",
    "test_source_delta_rejects_a_moved_legacy_marker",
    "test_source_delta_allows_unchanged_and_removed_legacy_markers",
    "test_source_delta_fails_closed_when_git_is_unavailable",
    "test_source_delta_fails_closed_on_malformed_git_diff",
    "test_source_delta_rejects_invalid_or_unavailable_base",
    "test_source_delta_does_not_surface_git_error_output",
    "test_source_delta_diagnostic_reports_count_without_untrusted_paths",
    "test_security_workflow_passes_source_base_for_supported_events",
    "test_matching_findings_allow_stale_removals",
    "test_new_finding_in_existing_file_is_rejected",
    "test_line_number_drift_does_not_create_a_new_finding",
    "test_trusted_base_rejects_new_baseline_suppression",
    "test_trusted_base_stale_addition_preserves_removal_semantics",
    "test_empty_current_results_are_valid_and_mark_baseline_stale",
    "test_path_separators_are_compared_canonically",
    "test_malformed_artifacts_fail_closed",
    "test_missing_artifact_fails_closed",
    "test_baseline_requires_explicit_false_positive_triage",
    "test_baseline_rejects_a_committed_secret_decision",
    "test_invalid_json_fails_closed",
    "test_malformed_trusted_base_fails_closed",
    "test_cli_usage_error_is_fail_closed",
    "test_empty_trusted_base_path_fails_closed",
    "test_base_baseline_alias_is_supported",
    "test_reviewed_false_positive_disposition_matches_exact_identity",
    "test_exact_new_identity_allowlists_remain_finite_and_path_scoped",
    "test_source_contract_identifier_category_is_finite_and_evidence_bound",
    "test_c6_source_contract_records_require_explicit_approval",
    "test_c6_source_contract_records_reject_mutated_identity_or_category",
    "test_v4_independent_contract_fingerprints_match_exact_identities",
    "test_external_kubernetes_secret_references_match_exact_identities",
    "test_trivy_university_secret_reference_is_exact_and_requires_approval",
    "test_new_exact_disposition_categories_reject_mutated_identities",
    "test_mfa_helm_secret_reference_is_exact_and_requires_approval",
    "test_external_secret_reference_requires_semantic_evidence_markers",
    "test_external_secret_reference_still_requires_unexpired_review",
    "test_independent_contract_fingerprint_category_remains_exact",
    "test_non_hex_dispositions_are_scoped_to_reviewed_path_and_type",
    "test_non_hex_dispositions_reject_wrong_source_or_type",
    "test_internal_demo_account_requires_both_owner_evidence_markers",
    "test_internal_demo_account_category_does_not_approve_pending_record",
    "test_reviewed_disposition_does_not_match_other_path_or_digest",
    "test_reviewed_disposition_rejects_unapproved_finding_type",
    "test_reviewed_disposition_requires_approved_owner_and_finite_dates",
    "test_reviewed_disposition_rejects_non_exact_paths",
    "test_reviewed_disposition_rejects_duplicate_identities",
    "test_reviewed_disposition_rejects_unknown_fields_and_bad_digest",
    "test_reviewed_disposition_rejects_malformed_digest_bytes",
    "test_reviewed_disposition_does_not_cover_an_unrelated_finding",
    "test_trusted_disposition_loader_uses_base_tree_not_worktree",
    "test_trusted_disposition_loader_ignores_candidate_only_artifact",
    "test_trusted_disposition_loader_rejects_duplicate_json_keys",
    "test_main_uses_trusted_exact_dispositions",
    "test_owner_authored_candidate_disposition_is_explicit_opt_in",
    "test_candidate_disposition_tamper_expiry_fails_closed",
    "test_push_can_use_accepted_head_policy_while_source_diff_uses_before_sha",
    "test_trusted_disposition_does_not_allow_new_baseline_suppression",
    "test_trusted_disposition_does_not_allow_added_inline_pragma",
    "test_disposition_file_is_protected_by_existing_owner_policy_gates",
    "test_public_compose_sentinel_matches_only_approved_identity",
    "test_public_compose_sentinel_refuses_scope_mutation",
    "test_public_compose_sentinel_expires_after_approved_date",
    "test_public_compose_sentinel_requires_each_semantic_marker",
    "test_public_compose_sentinel_identity_matches_fixed_source_literal",
    "test_approved_go_image_disposition_binds_exact_source_checksum",
)
_TARGET_NAME = _TARGET_CASES[0][1]


def _node(
    relative_path: str | None = "tests/test_live_stand.py",
    name: str = _TARGET_NAME,
) -> Any:
    node_path = _REPOSITORY_ROOT / relative_path if relative_path is not None else None
    return SimpleNamespace(
        path=node_path,
        originalname=name,
        config=SimpleNamespace(rootpath=_REPOSITORY_ROOT),
    )


def test_cleanup_profile_matches_only_exact_parser_functions() -> None:
    matches = database_fixtures._is_pure_parser_profile_case

    for relative_path, name in _TARGET_CASES:
        assert matches(_node(relative_path=relative_path, name=name))
        assert not matches(_node(relative_path=f"{relative_path}.copy", name=name))
    for relative_path, name in _NEAR_MISS_CASES:
        assert not matches(_node(relative_path=relative_path, name=name))
    assert not matches(_node(relative_path=None, name=_TARGET_NAME))
    for name in _POLICY_TEST_NAMES:
        assert not matches(
            _node(relative_path="tests/test_verify_secrets_baseline.py", name=name)
        )


@pytest.mark.parametrize(
    ("relative_path", "node_name", "expected_clear_calls"),
    [
        *((path, name, 0) for path, name in _TARGET_CASES),
        *((path, name, 1) for path, name in _NEAR_MISS_CASES),
        (None, _TARGET_NAME, 1),
    ],
)
@pytest.mark.asyncio
async def test_database_cleanup_skips_only_allowlisted_parser_after_body_error(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str | None,
    node_name: str,
    expected_clear_calls: int,
) -> None:
    clear_calls: list[bool] = []

    async def record_clear(*, is_postgresql: bool) -> None:
        clear_calls.append(is_postgresql)

    monkeypatch.setattr(database_fixtures, "_clear_mapped_database_rows", record_clear)
    request = SimpleNamespace(node=_node(relative_path=relative_path, name=node_name))
    fixture = database_fixtures.clean_database.__wrapped__(
        prepare_database=None, request=request
    )
    await fixture.__anext__()

    with pytest.raises(RuntimeError, match="synthetic test body failure"):
        try:
            raise RuntimeError("synthetic test body failure")
        finally:
            with pytest.raises(StopAsyncIteration):
                await fixture.__anext__()

    assert len(clear_calls) == expected_clear_calls


@pytest.mark.parametrize(
    ("relative_path", "node_name", "expected_gc_calls"),
    [
        *((path, name, 0) for path, name in _TARGET_CASES),
        *((path, name, 1) for path, name in _NEAR_MISS_CASES),
        (None, _TARGET_NAME, 1),
        ("tests/test_verify_secrets_baseline.py", _POLICY_TEST_NAMES[0], 1),
    ],
)
@pytest.mark.asyncio
async def test_async_task_cleanup_runs_after_body_error_and_limits_gc_to_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str | None,
    node_name: str,
    expected_gc_calls: int,
) -> None:
    gc_calls: list[None] = []
    monkeypatch.setattr(gc, "collect", lambda: gc_calls.append(None))
    request = SimpleNamespace(node=_node(relative_path=relative_path, name=node_name))
    fixture = project_conftest.cleanup_asyncio_tasks.__wrapped__(request)
    await fixture.__anext__()

    owned_task = asyncio.create_task(asyncio.sleep(3600))
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="synthetic test body failure"):
        try:
            raise RuntimeError("synthetic test body failure")
        finally:
            with pytest.raises(StopAsyncIteration):
                await fixture.__anext__()

    assert owned_task.cancelled()
    assert len(gc_calls) == expected_gc_calls


@pytest.mark.asyncio
async def test_policy_database_cleanup_is_exact_after_body_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_calls: list[bool] = []

    async def record_clear(*, is_postgresql: bool) -> None:
        clear_calls.append(is_postgresql)

    monkeypatch.setattr(database_fixtures, "_clear_mapped_database_rows", record_clear)
    cases = [
        ("tests/test_verify_secrets_baseline.py", "test_unlisted_policy_case", 1),
        ("tests/test_verify_secrets_baseline.py.copy", _POLICY_TEST_NAMES[0], 1),
        (None, _POLICY_TEST_NAMES[0], 1),
        *(
            ("tests/test_verify_secrets_baseline.py", name, 0)
            for name in _POLICY_TEST_NAMES
        ),
    ]
    for relative_path, node_name, expected_clear_calls in cases:
        clear_calls.clear()
        request = SimpleNamespace(
            node=_node(relative_path=relative_path, name=node_name)
        )
        fixture = database_fixtures.clean_database.__wrapped__(
            prepare_database=None, request=request
        )
        await fixture.__anext__()

        with pytest.raises(RuntimeError, match="synthetic test body failure"):
            try:
                raise RuntimeError("synthetic test body failure")
            finally:
                with pytest.raises(StopAsyncIteration):
                    await fixture.__anext__()

        assert len(clear_calls) == expected_clear_calls, (relative_path, node_name)
