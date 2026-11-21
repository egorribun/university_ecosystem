"""Story create and update reject covers that are not story cover uploads."""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api import stories as stories_api
from app.schemas import schemas
from app.services.story_service import StoryCoverNotUploaded
from tests.conftest import call_injected


def _admin() -> MagicMock:
    user = MagicMock()
    user.id = uuid.UUID(int=1)
    user.locale = "en"
    return user


def _request() -> MagicMock:
    request = MagicMock()
    request.headers.get.return_value = "en"
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "method", "arguments"),
    [
        (
            "create_story",
            "create_story",
            {"data": schemas.StoryCreate(title="T", short_text="S")},
        ),
        (
            "update_story",
            "update_story",
            {"story_id": uuid.UUID(int=2), "data": schemas.StoryUpdate()},
        ),
    ],
)
async def test_cover_that_is_not_an_upload_is_a_localized_422(
    endpoint: str, method: str, arguments: dict
) -> None:
    service = AsyncMock()
    getattr(service, method).side_effect = StoryCoverNotUploaded(
        "story_cover_not_uploaded"
    )
    handler = inspect.unwrap(getattr(stories_api, endpoint))

    with pytest.raises(HTTPException) as caught:
        await call_injected(
            handler,
            request=_request(),
            user=_admin(),
            provides={"StoryService": service},
            **arguments,
        )

    assert caught.value.status_code == 422
    assert "cover upload" in str(caught.value.detail)
