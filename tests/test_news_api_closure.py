"""Focused closure tests for the news API coverage hotspot."""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Response

import app.api.news as news_api
from app.models.enums import UserRole

NEWS_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df79")


def _request(*, cache: object | None = None, locale: str = "en") -> SimpleNamespace:
    return SimpleNamespace(
        query_params={},
        headers={"Accept-Language": locale},
        app=SimpleNamespace(state=SimpleNamespace(cache=cache)),
    )


def _admin() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.UUID(int=1),
        role=UserRole.ADMIN,
        email="admin@example.com",
        profile=SimpleNamespace(full_name="Admin User"),
    )


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.UUID(int=2),
        role=UserRole.STUDENT,
        email="student@example.com",
        profile=None,
    )


def _news_record() -> SimpleNamespace:
    return SimpleNamespace(id=NEWS_ID, title="Title", content="Body")


def _cache(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(enabled=enabled, invalidate=AsyncMock())


async def test_cache_helpers_normalize_fallbacks_and_increment() -> None:
    assert news_api._normalized_cache_locale(None) == news_api.DEFAULT_LOCALE
    assert news_api._normalized_cache_locale("xx") == news_api.DEFAULT_LOCALE

    await news_api._increment_news_list_version(None)
    cache = object()
    manager = MagicMock()
    manager.increment = AsyncMock()
    manager.get_version = AsyncMock(return_value="v2")
    with patch.object(news_api, "news_cache_version", manager):
        await news_api._increment_news_list_version(cache)
        assert await news_api._get_news_list_version(cache) == "v2"
    manager.increment.assert_awaited_once_with(cache)
    manager.get_version.assert_awaited_once_with(cache)


async def test_create_news_requires_admin_and_dispatches_notification() -> None:
    handler = inspect.unwrap(news_api.create_news)
    service = AsyncMock()
    notifications = AsyncMock()
    record = _news_record()
    service.create_news.return_value = record
    service.serialize_news = MagicMock(return_value={"id": NEWS_ID})
    request = _request(cache=object())
    background = BackgroundTasks()

    with patch.object(
        news_api, "_increment_news_list_version", new_callable=AsyncMock
    ) as increment:
        result = await handler(
            data=MagicMock(),
            request=request,
            background=background,
            service=service,
            user=_admin(),
            notifications=notifications,
        )

    assert result == {"id": NEWS_ID}
    service.create_news.assert_awaited_once()
    service.serialize_news.assert_called_once_with(record, "en")
    notifications.dispatch_news_created.assert_awaited_once_with(
        NEWS_ID, "en", background
    )
    increment.assert_awaited_once_with(request.app.state.cache)

    with patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock):
        result = await handler(
            data=MagicMock(),
            request=None,
            background=background,
            service=service,
            user=_admin(),
            notifications=notifications,
        )
    assert result == {"id": NEWS_ID}


async def test_news_list_for_anonymous_and_authenticated_users() -> None:
    handler = inspect.unwrap(news_api.news_list)
    service = AsyncMock()
    service.list_news.return_value = {"items": [], "next_cursor": None}
    request = _request()

    anonymous = await handler(
        request=request,
        response=Response(),
        limit=10,
        cursor="cursor-1",
        if_none_match=None,
        service=service,
        user=None,
    )
    authenticated = await handler(
        request=request,
        response=Response(),
        limit=5,
        cursor=None,
        if_none_match=None,
        service=service,
        user=_user(),
    )

    assert anonymous == authenticated == {"items": [], "next_cursor": None}
    assert service.list_news.await_args_list[0].kwargs == {
        "limit": 10,
        "cursor": "cursor-1",
        "current_user_id": None,
        "search": None,
        "locale": "en",
    }
    assert service.list_news.await_args_list[1].kwargs["current_user_id"] == uuid.UUID(
        int=2
    )


async def test_get_news_handles_anonymous_authenticated_and_missing_rows() -> None:
    handler = inspect.unwrap(news_api.get_news)
    service = MagicMock()
    service.serialize_news.return_value = {"id": NEWS_ID}
    db = AsyncMock()
    row = _news_record()
    db_result = MagicMock()
    db.execute.return_value = db_result
    db_result.first.return_value = (row, 4, 2, True)

    result = await handler(
        id=NEWS_ID,
        request=_request(),
        response=Response(),
        if_none_match=None,
        user=None,
        db=db,
        service=service,
    )
    assert result == {"id": NEWS_ID}
    assert row.likes_count == 4
    assert row.comments_count == 2
    assert row.is_liked is True

    db_result.first.return_value = (row, None, None, False)
    result = await handler(
        id=NEWS_ID,
        request=_request(),
        response=Response(),
        if_none_match=None,
        user=_user(),
        db=db,
        service=service,
    )
    assert result == {"id": NEWS_ID}
    assert row.likes_count == 0
    assert row.comments_count == 0
    assert row.is_liked is False

    db_result.first.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await handler(
            id=NEWS_ID,
            request=_request(),
            response=Response(),
            if_none_match=None,
            user=None,
            db=db,
            service=service,
        )
    assert exc_info.value.status_code == 404


async def test_update_news_success_and_missing_paths_invalidate_cache() -> None:
    handler = inspect.unwrap(news_api.update_news)
    service = AsyncMock()
    updated = _news_record()
    service.update_news.return_value = updated
    service.serialize_news = MagicMock(return_value={"id": NEWS_ID})
    cache = _cache()
    data = MagicMock()

    with (
        patch.object(news_api, "get_cache", return_value=cache),
        patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock),
    ):
        result = await handler(
            id=NEWS_ID,
            request=_request(cache=object()),
            data=data,
            service=service,
            user=_admin(),
        )
    assert result == {"id": NEWS_ID}
    service.update_news.assert_awaited_once_with(NEWS_ID, data)
    cache.invalidate.assert_awaited_once()

    service.update_news.side_effect = ValueError("not found")
    with pytest.raises(HTTPException) as exc_info:
        await handler(
            id=NEWS_ID,
            request=_request(cache=None),
            data=None,
            service=service,
            user=_admin(),
        )
    assert exc_info.value.status_code == 404

    service.update_news.side_effect = None
    service.update_news.return_value = updated
    disabled_cache = _cache(enabled=False)
    with (
        patch.object(news_api, "get_cache", return_value=disabled_cache),
        patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock),
    ):
        assert await handler(
            id=NEWS_ID,
            request=None,
            data=None,
            service=service,
            user=_admin(),
        ) == {"id": NEWS_ID}
    disabled_cache.invalidate.assert_not_awaited()


async def test_delete_news_success_and_missing_paths_invalidate_cache() -> None:
    handler = inspect.unwrap(news_api.delete_news)
    service = AsyncMock()
    cache = _cache()

    with (
        patch.object(news_api, "get_cache", return_value=cache),
        patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock),
    ):
        service.delete_news.return_value = True
        assert await handler(
            id=NEWS_ID,
            request=_request(cache=object()),
            service=service,
            user=_admin(),
        ) == {"ok": True}
    cache.invalidate.assert_awaited_once()

    disabled_cache = _cache(enabled=False)
    service.delete_news.return_value = True
    with (
        patch.object(news_api, "get_cache", return_value=disabled_cache),
        patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock),
    ):
        assert await handler(
            id=NEWS_ID,
            request=None,
            service=service,
            user=_admin(),
        ) == {"ok": True}
    disabled_cache.invalidate.assert_not_awaited()

    service.delete_news.return_value = False
    with pytest.raises(HTTPException) as exc_info:
        await handler(
            id=NEWS_ID,
            request=_request(cache=None),
            service=service,
            user=_admin(),
        )
    assert exc_info.value.status_code == 404


async def test_like_news_success_and_missing_paths() -> None:
    handler = inspect.unwrap(news_api.like_news)
    service = AsyncMock()
    user = _user()
    service.get_news_item.return_value = _news_record()
    service.toggle_like.return_value = True

    assert await handler(
        id=NEWS_ID,
        request=_request(),
        service=service,
        user=user,
    ) == {"is_liked": True}
    service.toggle_like.assert_awaited_once_with(NEWS_ID, user.id)

    service.get_news_item.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await handler(
            id=NEWS_ID,
            request=_request(),
            service=service,
            user=user,
        )
    assert exc_info.value.status_code == 404


async def test_comment_news_validates_news_content_and_profile_fallback() -> None:
    handler = inspect.unwrap(news_api.comment_on_news)
    service = AsyncMock()
    notifications = AsyncMock()
    user = _user()
    comment = SimpleNamespace(
        id=uuid.UUID(int=3),
        content="A comment",
        user_id=user.id,
        created_at="now",
    )
    service.get_news_item.return_value = _news_record()
    service.create_comment.return_value = comment

    result = await handler(
        id=NEWS_ID,
        request=_request(),
        background=BackgroundTasks(),
        content=" A comment ",
        service=service,
        user=user,
        notifications=notifications,
    )
    assert result["user_name"] == str(user.email)
    notifications.dispatch_comment_created.assert_awaited_once()

    with pytest.raises(HTTPException) as exc_info:
        await handler(
            id=NEWS_ID,
            request=_request(),
            background=BackgroundTasks(),
            content="   ",
            service=service,
            user=user,
            notifications=notifications,
        )
    assert exc_info.value.status_code == 400

    service.get_news_item.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await handler(
            id=NEWS_ID,
            request=_request(),
            background=BackgroundTasks(),
            content="comment",
            service=service,
            user=user,
            notifications=notifications,
        )
    assert exc_info.value.status_code == 404


async def test_news_interactions_not_found() -> None:
    handler = inspect.unwrap(news_api.get_news_interact)
    service = AsyncMock()
    service.get_news_item.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await handler(
            id=NEWS_ID,
            request=_request(),
            limit=10,
            offset=2,
            service=service,
            user=None,
        )
    assert exc_info.value.status_code == 404


async def test_news_interactions_success() -> None:
    handler = inspect.unwrap(news_api.get_news_interact)
    service = AsyncMock()
    service.get_news_item.return_value = _news_record()
    service.get_interactions.return_value = {
        "likes_count": 2,
        "is_liked": True,
        "comments": [],
        "comments_count": 0,
    }
    user = _user()

    result = await handler(
        id=NEWS_ID,
        request=_request(),
        limit=10,
        offset=2,
        service=service,
        user=user,
    )

    assert result.likes_count == 2
    service.get_interactions.assert_awaited_once_with(
        NEWS_ID, user.id, limit=10, offset=2
    )


async def test_update_comment_success_and_error_paths() -> None:
    handler = inspect.unwrap(news_api.update_comment)
    service = AsyncMock()
    comment = SimpleNamespace(
        id=uuid.UUID(int=3),
        content="updated",
        user_id=uuid.UUID(int=2),
        created_at="now",
    )
    service.update_comment.return_value = comment
    user = _user()
    data = SimpleNamespace(content="updated")

    result = await handler(
        comment_id=uuid.UUID(int=3),
        request=_request(),
        data=data,
        service=service,
        user=user,
    )
    assert result["user_name"] == str(user.email)

    for error, status_code in ((LookupError(), 404), (PermissionError(), 403)):
        service.update_comment.side_effect = error
        with pytest.raises(HTTPException) as exc_info:
            await handler(
                comment_id=uuid.UUID(int=3),
                request=_request(),
                data=data,
                service=service,
                user=user,
            )
        assert exc_info.value.status_code == status_code
    service.update_comment.side_effect = None


async def test_delete_comment_success_and_error_paths() -> None:
    handler = inspect.unwrap(news_api.delete_comment)
    service = AsyncMock()
    comment_id = uuid.UUID(int=3)

    for user, expected_admin in ((_user(), False), (_admin(), True)):
        assert await handler(
            comment_id=comment_id,
            request=_request(),
            service=service,
            user=user,
        ) == {"ok": True}
        assert (
            service.delete_comment.await_args_list[-1].kwargs["is_admin"]
            is expected_admin
        )

    for error, status_code in ((LookupError(), 404), (PermissionError(), 403)):
        service.delete_comment.side_effect = error
        with pytest.raises(HTTPException) as exc_info:
            await handler(
                comment_id=comment_id,
                request=_request(),
                service=service,
                user=_user(),
            )
        assert exc_info.value.status_code == status_code
    service.delete_comment.side_effect = None


async def test_upload_news_image_scans_and_saves() -> None:
    handler = inspect.unwrap(news_api.upload_news_image)
    upload = SimpleNamespace(size=12)

    with (
        patch.object(news_api, "scan_for_malware", new_callable=AsyncMock) as scan,
        patch.object(
            news_api, "save_upload", new_callable=AsyncMock, return_value="/image.jpg"
        ) as save,
    ):
        result = await handler(file=upload, request=_request(), user=_admin())

    assert result == {"url": "/image.jpg"}
    scan.assert_awaited_once_with(upload, locale="en", size_bytes=12)
    save.assert_awaited_once_with(upload, "news_images", "news", locale="en")


async def test_semantic_search_returns_not_modified_for_matching_etag() -> None:
    handler = inspect.unwrap(news_api.semantic_search)
    cache = _cache()
    vector = AsyncMock()
    service = AsyncMock()
    response = Response()

    with (
        patch.object(news_api, "get_cache", return_value=cache),
        patch.object(
            news_api,
            "_get_news_list_version",
            new_callable=AsyncMock,
            return_value="v1",
        ),
        patch.object(news_api, "etag_matches", return_value=True),
    ):
        etag = news_api.format_etag("semantic:v1:query:5:0.7")
        result = await handler(
            request=_request(),
            response=response,
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=etag,
            db=AsyncMock(),
            vector_service=vector,
            service=service,
            _user=_user(),
        )

    assert isinstance(result, Response)
    assert result.status_code == 304
    vector.get_embedding.assert_not_awaited()


async def test_semantic_search_returns_serialized_matches() -> None:
    handler = inspect.unwrap(news_api.semantic_search)
    cache = _cache()
    vector = AsyncMock()
    vector.get_embedding.return_value = [0.1, 0.2]
    record = _news_record()
    vector.search_similar.return_value = [record]
    service = MagicMock()
    service.serialize_news.return_value = {"id": NEWS_ID}
    response = Response()

    with (
        patch.object(news_api, "get_cache", return_value=cache),
        patch.object(
            news_api,
            "_get_news_list_version",
            new_callable=AsyncMock,
            return_value="v1",
        ),
    ):
        result = await handler(
            request=_request(),
            response=response,
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=None,
            db=AsyncMock(),
            vector_service=vector,
            service=service,
            _user=_user(),
        )

    assert result == [{"id": NEWS_ID}]
    vector.get_embedding.assert_awaited_once_with("query")
    vector.search_similar.assert_awaited_once()
    assert response.headers["ETag"]
