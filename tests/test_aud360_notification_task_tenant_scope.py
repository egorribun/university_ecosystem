"""AUD-360: NATS notification tasks must restore an authorized tenant scope."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import settings
from app.core.tenant import (
    bypass_rls_ctx,
    get_bypass_rls,
    get_current_tenant,
    tenant_id_ctx,
)
from app.models import Event, News, NewsComment, User
from app.tasks import notifications

_NEWS_ID = uuid.UUID("00000000-0000-4000-8000-000000000011")
_EVENT_ID = uuid.UUID("00000000-0000-4000-8000-000000000012")
_COMMENT_ID = uuid.UUID("00000000-0000-4000-8000-000000000013")
_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000014")
_TENANT_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_TENANT_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


class _Session:
    def __init__(self, tenant_id: uuid.UUID) -> None:
        self.expected_tenant_id = str(tenant_id)
        self.commits = 0
        self.reads: list[tuple[type[object], uuid.UUID]] = []

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, model: type[object], identity: uuid.UUID) -> object:
        assert get_current_tenant() == self.expected_tenant_id
        assert get_bypass_rls() is False
        self.reads.append((model, identity))
        return SimpleNamespace(id=identity)

    async def commit(self) -> None:
        assert get_current_tenant() == self.expected_tenant_id
        assert get_bypass_rls() is False
        self.commits += 1


async def _invoke_task(
    task_name: str, *, tenant_id: uuid.UUID | str | None = None
) -> None:
    tenant_kwargs = {} if tenant_id is None else {"tenant_id": tenant_id}
    if task_name == "news":
        await notifications.enqueue_news_notification_task(
            _NEWS_ID, locale="en", **tenant_kwargs
        )
    elif task_name == "event":
        await notifications.enqueue_event_notification_task(
            _EVENT_ID, locale="en", **tenant_kwargs
        )
    else:
        await notifications.enqueue_comment_notification_task(
            _NEWS_ID, _COMMENT_ID, _USER_ID, locale="en", **tenant_kwargs
        )


def _patch_task(session, monkeypatch: pytest.MonkeyPatch, task_name: str) -> None:
    monkeypatch.setattr(notifications, "async_session", lambda: session)

    async def notify(*_args: object, **_kwargs: object) -> int:
        assert get_current_tenant() == session.expected_tenant_id
        assert get_bypass_rls() is False
        return 1

    callback_name = {
        "news": "_notify_about_news",
        "event": "_notify_about_event",
        "comment": "_notify_about_comment",
    }[task_name]
    monkeypatch.setattr(notifications, callback_name, notify)


@pytest.mark.asyncio
@pytest.mark.parametrize("task_name", ["news", "event", "comment"])
async def test_notification_task_uses_configured_mvp_tenant_and_restores_context(
    task_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _Session(_TENANT_A)
    _patch_task(session, monkeypatch, task_name)
    monkeypatch.setattr(settings, "mvp_tenant_id", _TENANT_A)
    ambient_tenant = tenant_id_ctx.set(str(_TENANT_B))
    ambient_bypass = bypass_rls_ctx.set(True)
    try:
        await _invoke_task(task_name)

        expected_reads = {
            "news": [(News, _NEWS_ID)],
            "event": [(Event, _EVENT_ID)],
            "comment": [
                (News, _NEWS_ID),
                (NewsComment, _COMMENT_ID),
                (User, _USER_ID),
            ],
        }[task_name]
        assert session.reads == expected_reads
        assert session.commits == 1
        assert get_current_tenant() == str(_TENANT_B)
        assert get_bypass_rls() is True
    finally:
        bypass_rls_ctx.reset(ambient_bypass)
        tenant_id_ctx.reset(ambient_tenant)


@pytest.mark.asyncio
@pytest.mark.parametrize("task_name", ["news", "event", "comment"])
async def test_notification_task_accepts_explicit_tenant_without_mvp_config(
    task_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _Session(_TENANT_B)
    _patch_task(session, monkeypatch, task_name)
    monkeypatch.setattr(settings, "mvp_tenant_id", None)

    await _invoke_task(task_name, tenant_id=str(_TENANT_B))

    assert session.commits == 1


@pytest.mark.asyncio
async def test_notification_task_rejects_unscoped_work_before_opening_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mvp_tenant_id", None)
    monkeypatch.setattr(
        notifications,
        "async_session",
        lambda: pytest.fail("unscoped task opened a database session"),
    )

    with pytest.raises(RuntimeError, match="tenant"):
        await _invoke_task("news")


@pytest.mark.asyncio
async def test_notification_task_cannot_override_the_configured_mvp_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mvp_tenant_id", _TENANT_A)
    monkeypatch.setattr(
        notifications,
        "async_session",
        lambda: pytest.fail("mismatched task opened a database session"),
    )

    with pytest.raises(ValueError, match="configured MVP tenant"):
        await _invoke_task("news", tenant_id=_TENANT_B)


@pytest.mark.asyncio
async def test_notification_task_restores_context_after_callback_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session(_TENANT_A)
    _patch_task(session, monkeypatch, "news")
    monkeypatch.setattr(settings, "mvp_tenant_id", _TENANT_A)

    async def fail_notification(*_args: object, **_kwargs: object) -> int:
        assert get_current_tenant() == str(_TENANT_A)
        assert get_bypass_rls() is False
        raise OSError("simulated notification failure")

    monkeypatch.setattr(notifications, "_notify_about_news", fail_notification)
    ambient_tenant = tenant_id_ctx.set(str(_TENANT_B))
    ambient_bypass = bypass_rls_ctx.set(True)
    try:
        with pytest.raises(OSError, match="simulated notification failure"):
            await _invoke_task("news")

        assert get_current_tenant() == str(_TENANT_B)
        assert get_bypass_rls() is True
    finally:
        bypass_rls_ctx.reset(ambient_bypass)
        tenant_id_ctx.reset(ambient_tenant)


@pytest.mark.asyncio
async def test_notification_task_rejects_malformed_tenant_before_opening_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mvp_tenant_id", None)
    monkeypatch.setattr(
        notifications,
        "async_session",
        lambda: pytest.fail("invalidly scoped task opened a database session"),
    )

    with pytest.raises(ValueError, match="tenant identity"):
        await _invoke_task("event", tenant_id="not-a-uuid")


@pytest.mark.asyncio
@pytest.mark.parametrize("task_name", ["news", "event", "comment"])
@pytest.mark.parametrize("tenant_id", [7, [], {"tenant_id": str(_TENANT_A)}])
async def test_notification_task_rejects_non_string_tenant_without_side_effects(
    task_name: str, tenant_id: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mvp_tenant_id", _TENANT_A)
    monkeypatch.setattr(
        notifications,
        "async_session",
        lambda: pytest.fail("invalid tenant opened a database session"),
    )
    ambient_tenant = tenant_id_ctx.set(str(_TENANT_B))
    ambient_bypass = bypass_rls_ctx.set(True)
    try:
        with pytest.raises(
            ValueError, match=r"^Invalid notification task tenant identity$"
        ):
            await _invoke_task(task_name, tenant_id=tenant_id)

        assert get_current_tenant() == str(_TENANT_B)
        assert get_bypass_rls() is True
    finally:
        bypass_rls_ctx.reset(ambient_bypass)
        tenant_id_ctx.reset(ambient_tenant)
