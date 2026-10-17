"""Web-push delivery, cleanup, and failure-mode runtime contracts."""

from __future__ import annotations

import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from pywebpush import WebPushException
from sqlalchemy.engine import make_url

from app.services import webpush


def test_sync_url_preserves_already_synchronous_driver() -> None:
    with (
        patch.object(webpush, "_sync_url_cache", None),
        patch.object(webpush.settings, "database_url", "postgresql://db/app"),
    ):
        assert webpush._get_sync_url() == make_url("postgresql://db/app")


def test_sync_sessionmaker_fast_path_and_double_check() -> None:
    existing = MagicMock()
    with patch.object(webpush, "_Session", existing):
        assert webpush._ensure_sync_sessionmaker() is existing

    lock = MagicMock()

    def initialize_elsewhere() -> None:
        webpush._Session = existing

    lock.__enter__.side_effect = initialize_elsewhere
    with (
        patch.object(webpush, "_Session", None),
        patch.object(webpush, "_sync_init_lock", lock),
        patch.object(webpush, "_initialize_sync_resources") as initialize,
    ):
        assert webpush._ensure_sync_sessionmaker() is existing
    initialize.assert_not_called()


@pytest.mark.asyncio
async def test_async_sessionmaker_fast_path() -> None:
    existing = MagicMock()
    with (
        patch.object(webpush, "_Session", existing),
        patch.object(webpush.asyncio, "to_thread") as to_thread,
    ):
        assert await webpush._ensure_async_sessionmaker() is existing
    to_thread.assert_not_called()


def test_async_sessionmaker_initializes_across_concurrent_event_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if hasattr(webpush, "_async_init_lock"):
        monkeypatch.setattr(webpush, "_async_init_lock", asyncio.Lock())
    monkeypatch.setattr(webpush, "_sync_engine", None)
    monkeypatch.setattr(webpush, "_Session", None)
    monkeypatch.setattr(webpush, "_sync_init_lock", threading.Lock())
    monkeypatch.setattr(webpush, "_get_sync_url", lambda: make_url("sqlite://"))

    engines: list[MagicMock] = []

    def fake_create_engine(*args: object, **kwargs: object) -> MagicMock:
        engine = MagicMock()
        engines.append(engine)
        return engine

    monkeypatch.setattr(webpush, "create_engine", fake_create_engine)
    initialize_resources = webpush._initialize_sync_resources
    initialization_started = threading.Event()
    allow_initialization = threading.Event()

    def delayed_initialize_resources() -> None:
        initialization_started.set()
        if not allow_initialization.wait(timeout=5):
            raise TimeoutError("test did not release sync initialization")
        initialize_resources()

    monkeypatch.setattr(
        webpush, "_initialize_sync_resources", delayed_initialize_resources
    )
    loop_a_started = threading.Event()
    repeat_loop_a = threading.Event()
    repeat_started = threading.Event()
    loop_b_contending = threading.Event()

    async def initialize_from_loop_a() -> list[object]:
        first = asyncio.create_task(webpush._ensure_async_sessionmaker())
        if not await asyncio.to_thread(initialization_started.wait, 5):
            raise AssertionError("loop A did not reach sync initialization")

        loop_a_started.set()
        if not await asyncio.to_thread(repeat_loop_a.wait, 5):
            raise AssertionError("loop A did not receive the repeat signal")

        repeated = asyncio.create_task(webpush._ensure_async_sessionmaker())
        await asyncio.sleep(0)
        repeat_started.set()
        await asyncio.to_thread(allow_initialization.wait, 5)
        return await asyncio.gather(first, repeated, return_exceptions=True)

    async def initialize_from_loop_b() -> object:
        pending = asyncio.create_task(webpush._ensure_async_sessionmaker())
        await asyncio.sleep(0)
        loop_b_contending.set()
        try:
            return await asyncio.wait_for(pending, timeout=2)
        except (RuntimeError, TimeoutError) as exc:
            return exc

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            loop_a = executor.submit(asyncio.run, initialize_from_loop_a())
            assert initialization_started.wait(timeout=5)
            assert loop_a_started.wait(timeout=5)
            loop_b = executor.submit(asyncio.run, initialize_from_loop_b())
            assert loop_b_contending.wait(timeout=5)
            repeat_loop_a.set()
            assert repeat_started.wait(timeout=5)
            allow_initialization.set()

            loop_a_results = loop_a.result(timeout=5)
            loop_b_result = loop_b.result(timeout=5)

        all_results = [*loop_a_results, loop_b_result]
        assert all(not isinstance(result, BaseException) for result in all_results), [
            type(result).__name__ for result in all_results
        ]
        sessionmaker = loop_a_results[0]
        assert sessionmaker is loop_a_results[1] is loop_b_result
        assert len(engines) == 1

        session = sessionmaker()
        session.close()
        assert not session.in_transaction()

        webpush.cleanup()
        assert webpush._Session is None
        assert webpush._sync_engine is None
        engines[0].dispose.assert_called_once()

        reinitialized = asyncio.run(webpush._ensure_async_sessionmaker())
        assert reinitialized is not sessionmaker
        assert len(engines) == 2
        webpush.cleanup()
        assert webpush._Session is None
        assert webpush._sync_engine is None
        for engine in engines:
            engine.dispose.assert_called_once()
    finally:
        allow_initialization.set()
        webpush.cleanup()


def test_normalize_actions_without_urls_in_both_input_shapes() -> None:
    action = {"action": "open", "title": "Open"}
    top_level, _ = webpush._normalize_payload({"actions": [action]})
    nested, _ = webpush._normalize_payload({"options": {"actions": [action]}})

    assert top_level["options"]["actions"] == [action]
    assert nested["options"]["actions"] == [action]
    assert "actionUrls" not in top_level["data"]
    assert "actionUrls" not in nested["data"]


def test_empty_webpush_error_message_is_not_misclassified_as_gone() -> None:
    class EmptyMessageWebPushError(WebPushException):
        def __str__(self) -> str:
            return ""

    subscription = MagicMock(
        id=uuid.uuid4(),
        endpoint="https://push.example.com/subscription",
        p256dh="key",
        auth="auth",
        user_id=None,
        user=None,
    )
    settings = MagicMock(
        VAPID_PRIVATE_KEY="private-key",  # pragma: allowlist secret
        WEBPUSH_SUBJECT="mailto:admin@example.com",
    )
    with (
        patch.object(webpush, "settings", settings),
        patch.object(webpush, "validate_public_https_url"),
        patch.object(
            webpush, "validate_and_resolve", return_value=[("93.184.216.34", 443)]
        ),
        patch.object(
            webpush,
            "webpush",
            side_effect=EmptyMessageWebPushError(""),
        ),
    ):
        result = webpush.send_web_push(subscription, {"title": "Hello"})

    assert result.status == "error"
    assert result.error is None
