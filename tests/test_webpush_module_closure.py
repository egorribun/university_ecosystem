"""Boundary contracts for Web Push DNS, payloads, and result coalescing."""

from __future__ import annotations

import asyncio
import socket
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import webpush


def test_private_ip_literal_is_rejected_before_transport() -> None:
    with pytest.raises(ValueError, match="globally routable"):
        webpush._reject_non_global_endpoint_host("https://10.0.0.1/push")


@pytest.mark.asyncio
async def test_public_endpoint_dns_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = AsyncMock(side_effect=socket.gaierror("resolver unavailable"))
    fake_loop = SimpleNamespace(getaddrinfo=resolver)
    monkeypatch.setattr(
        asyncio,
        "get_running_loop",
        lambda: cast(asyncio.AbstractEventLoop, fake_loop),
    )

    with pytest.raises(ValueError, match="DNS resolution failed"):
        await webpush._validate_public_endpoint_dns("https://push.example.test/send")

    resolver.assert_awaited_once_with(
        "push.example.test",
        443,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )


@pytest.mark.asyncio
async def test_public_endpoint_dns_accepts_a_global_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = AsyncMock(
        return_value=[
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("1.1.1.1", 443),
            )
        ]
    )
    fake_loop = SimpleNamespace(getaddrinfo=resolver)
    monkeypatch.setattr(
        asyncio,
        "get_running_loop",
        lambda: cast(asyncio.AbstractEventLoop, fake_loop),
    )

    await webpush._validate_public_endpoint_dns("https://push.example.test/send")

    resolver.assert_awaited_once_with(
        "push.example.test",
        443,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )


def test_result_coalescing_keeps_first_equal_or_higher_priority_result() -> None:
    subscription_id = uuid4()
    first = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint="https://push.example.test/first",
        user_id=None,
        status="sent",
    )
    lower_priority = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint="https://push.example.test/retry",
        user_id=None,
        status="error",
    )

    coalesced = webpush.coalesce_push_results([first, lower_priority])

    assert coalesced == [first]
    assert coalesced[0] is first
