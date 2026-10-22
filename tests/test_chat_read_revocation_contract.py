"""Membership-derived chat reads must observe revocations on the primary DB."""

from __future__ import annotations

from typing import Annotated, get_args, get_origin, get_type_hints

import pytest
from dishka import FromComponent

from app.api import chat as chat_api
from app.core.di.read_replica import READ_COMPONENT
from app.services.chat.query_service import ChatQueryService


@pytest.mark.parametrize(
    "endpoint",
    [
        pytest.param(chat_api.get_chats, id="chat-list"),
        pytest.param(chat_api.get_chat, id="chat-details"),
        pytest.param(chat_api.get_messages, id="message-history"),
        pytest.param(chat_api.get_reactors, id="message-reactors"),
    ],
)
def test_membership_derived_read_uses_primary_query_service(endpoint: object) -> None:
    """Replica lag must not preserve access after a participant is removed.

    These handlers derive authorization and returned data from chat membership.
    The read component is backed by a potentially lagging replica, so a recent
    membership revocation could otherwise still authorize a response.
    """
    implementation = getattr(endpoint, "__dishka_orig_func__", endpoint)
    annotation = get_type_hints(implementation, include_extras=True)["query_service"]

    assert get_origin(annotation) is Annotated
    assert get_args(annotation)[0] is ChatQueryService
    assert FromComponent(READ_COMPONENT) not in get_args(annotation)[1:]
