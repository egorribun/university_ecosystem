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
