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
_TARGET_PATH = _REPOSITORY_ROOT / "tests" / "test_live_stand.py"
_TARGET_NAMES = (
    "test_live_playwright_page_errors_accept_only_fixed_domains",
    "test_live_playwright_http_status_accepts_only_fixed_domains",
    "test_live_playwright_page_errors_accept_admin_hydration_domains",
    "test_live_playwright_email_otp_and_mfa_http_statuses_are_closed",
    "test_live_playwright_auth_http_parser_accepts_closed_status_mismatches",
    "test_live_playwright_story_setup_parser_accepts_closed_stages",
    "test_live_playwright_a11y_contrast_accepts_bounded_closed_records",
    "test_live_playwright_http_status_accepts_auth_status_checks",
    "test_live_playwright_http_status_rejects_malformed_records",
    "test_live_playwright_page_errors_reject_malformed_records",
    "test_live_playwright_push_observation_accepts_closed_records",
    "test_live_playwright_retry_diagnostics_accept_bounded_integer_decisions",
    "test_live_playwright_counts_reject_malformed_summary_records",
)
_NEAR_MISS_NAME = (
    "test_live_playwright_http_status_auth_session_cap_requires_exact_forbidden_status"
)
_TARGET_NAME = _TARGET_NAMES[0]


def _node(path: Path = _TARGET_PATH, name: str = _TARGET_NAME) -> Any:
    return SimpleNamespace(
        path=path,
        originalname=name,
        config=SimpleNamespace(rootpath=_REPOSITORY_ROOT),
    )


def test_cleanup_profile_matches_only_exact_parser_functions() -> None:
    matches = database_fixtures._is_pure_parser_profile_case

    for name in _TARGET_NAMES:
        assert matches(_node(name=name))
        assert not matches(
            _node(path=_TARGET_PATH.with_name("test_live_stand_copy.py"), name=name)
        )
    assert not matches(_node(name=_NEAR_MISS_NAME))
    assert not matches(
        SimpleNamespace(
            path=None,
            originalname=_TARGET_NAME,
            config=SimpleNamespace(rootpath=_REPOSITORY_ROOT),
        )
    )


@pytest.mark.parametrize(
    ("node_name", "expected_clear_calls"),
    [*((name, 0) for name in _TARGET_NAMES), (_NEAR_MISS_NAME, 1)],
)
@pytest.mark.asyncio
async def test_database_cleanup_skips_only_allowlisted_parser_after_body_error(
    monkeypatch: pytest.MonkeyPatch,
    node_name: str,
    expected_clear_calls: int,
) -> None:
    clear_calls: list[bool] = []

    async def record_clear(*, is_postgresql: bool) -> None:
        clear_calls.append(is_postgresql)

    monkeypatch.setattr(database_fixtures, "_clear_mapped_database_rows", record_clear)
    request = SimpleNamespace(node=_node(name=node_name))
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
    ("node_name", "expected_gc_calls"),
    [*((name, 0) for name in _TARGET_NAMES), (_NEAR_MISS_NAME, 1)],
)
@pytest.mark.asyncio
async def test_async_task_cleanup_runs_after_body_error_and_limits_gc_to_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    node_name: str,
    expected_gc_calls: int,
) -> None:
    gc_calls: list[None] = []
    monkeypatch.setattr(gc, "collect", lambda: gc_calls.append(None))
    request = SimpleNamespace(node=_node(name=node_name))
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
