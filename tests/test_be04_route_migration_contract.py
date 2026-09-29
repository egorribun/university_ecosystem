"""Bounded BE-04 route migration contracts.

The Stories write slice is intentionally small: it exercises the existing
request-scoped ``StoryService`` provider without changing read-replica
semantics or the public response contract.
"""

from __future__ import annotations

import inspect
from typing import Annotated, get_args, get_origin

import pytest

from app.api import stories as stories_api
from app.api.deps import auth as auth_deps
from app.services.story_service import StoryService


@pytest.mark.parametrize(
    "endpoint",
    [stories_api.create_story, stories_api.update_story, stories_api.delete_story],
)
def test_story_write_routes_use_dishka_service_and_auth(endpoint: object) -> None:
    implementation = getattr(endpoint, "__dishka_orig_func__", endpoint)
    signature = inspect.signature(implementation)

    service = signature.parameters["service"]
    assert get_origin(service.annotation) is Annotated
    assert get_args(service.annotation)[0] is StoryService
    assert service.default is inspect.Parameter.empty
    assert hasattr(endpoint, "__dishka_orig_func__")

    user = signature.parameters["user"]
    assert user.default.dependency is auth_deps.get_current_user_from_dishka


@pytest.mark.parametrize(
    "endpoint",
    [stories_api.create_story, stories_api.update_story, stories_api.delete_story],
)
def test_story_write_routes_have_no_legacy_database_dependency(
    endpoint: object,
) -> None:
    implementation = getattr(endpoint, "__dishka_orig_func__", endpoint)
    signature = inspect.signature(implementation)

    assert "db" not in signature.parameters
    assert all(
        "get_story_service" not in repr(parameter.default)
        for parameter in signature.parameters.values()
    )
