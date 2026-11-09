"""Focused closure tests for the news API coverage hotspot."""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from fastapi.exceptions import RequestValidationError

import app.api.news as news_api
from app.models.enums import UserRole
from app.services.vector_service import (
    SEMANTIC_SEARCH_UNAVAILABLE_DETAIL,
    SemanticSearchUnavailableError,
)
from tests.conftest import call_injected

NEWS_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df79")
NEWS_IMAGE_URL = "/static/news_images/news_0123456789abcdef0123456789abcdef.jpg"


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

    cache = object()
    manager = MagicMock()
    manager.increment = AsyncMock()
    manager.get_version = AsyncMock(return_value="v2")
    with patch.object(news_api, "news_cache_version", manager):
        await news_api._increment_news_list_version(None)
        manager.increment.assert_awaited_once_with(None)
        manager.increment.reset_mock()
        await news_api._increment_news_list_version()
        manager.increment.assert_awaited_once_with(None)
        manager.increment.reset_mock()
        await news_api._increment_news_list_version(cache)
        assert await news_api._get_news_list_version(cache) == "v2"
    manager.increment.assert_awaited_once_with(cache)
    manager.get_version.assert_awaited_once_with(cache)


async def test_create_news_requires_admin_and_serializes_record() -> None:
    handler = inspect.unwrap(news_api.create_news)
    service = AsyncMock()
    record = _news_record()
    service.create_news.return_value = record
    service.serialize_news = MagicMock(return_value={"id": NEWS_ID})
    request = _request(cache=object())
    data = MagicMock()
    with patch.object(
        news_api, "_increment_news_list_version", new_callable=AsyncMock
    ) as increment:
        result = await call_injected(
            handler,
            data=data,
            request=request,
            user=_admin(),
            provides={"NewsService": service},
        )

    assert result == {"id": NEWS_ID}
    service.create_news.assert_awaited_once_with(
        data, locale="en", owner_user_id=uuid.UUID(int=1)
    )
    service.serialize_news.assert_called_once_with(record, "en")
    increment.assert_awaited_once_with()

    with patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock):
        result = await call_injected(
            handler,
            data=MagicMock(),
            request=None,
            user=_admin(),
            provides={"NewsService": service},
        )
    assert result == {"id": NEWS_ID}


async def test_news_list_for_anonymous_and_authenticated_users() -> None:
    handler = inspect.unwrap(news_api.news_list)
    service = AsyncMock()
    service.list_news.return_value = {"items": [], "next_cursor": None}
    request = _request()

    anonymous = await call_injected(
        handler,
        request=request,
        response=Response(),
        limit=10,
        cursor="cursor-1",
        if_none_match=None,
        user=None,
        provides={"NewsService": service},
    )
    authenticated = await call_injected(
        handler,
        request=request,
        response=Response(),
        limit=5,
        cursor=None,
        if_none_match=None,
        user=_user(),
        provides={"NewsService": service},
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

    result = await call_injected(
        handler,
        id=NEWS_ID,
        request=_request(),
        response=Response(),
        if_none_match=None,
        user=None,
        provides={"AsyncDatabaseSession": db, "NewsService": service},
    )
    assert result == {"id": NEWS_ID}
    assert row.likes_count == 4
    assert row.comments_count == 2
    assert row.is_liked is True

    db_result.first.return_value = (row, None, None, False)
    result = await call_injected(
        handler,
        id=NEWS_ID,
        request=_request(),
        response=Response(),
        if_none_match=None,
        user=_user(),
        provides={"AsyncDatabaseSession": db, "NewsService": service},
    )
    assert result == {"id": NEWS_ID}
    assert row.likes_count == 0
    assert row.comments_count == 0
    assert row.is_liked is False

    db_result.first.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            response=Response(),
            if_none_match=None,
            user=None,
            provides={"AsyncDatabaseSession": db, "NewsService": service},
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
        result = await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(cache=object()),
            data=data,
            user=_admin(),
            provides={"NewsService": service},
        )
    assert result == {"id": NEWS_ID}
    service.update_news.assert_awaited_once_with(
        NEWS_ID, data, owner_user_id=uuid.UUID(int=1)
    )
    cache.invalidate.assert_awaited_once()

    service.update_news.side_effect = ValueError("not found")
    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(cache=None),
            data=None,
            user=_admin(),
            provides={"NewsService": service},
        )
    assert exc_info.value.status_code == 404

    service.update_news.side_effect = None
    service.update_news.return_value = updated
    disabled_cache = _cache(enabled=False)
    with (
        patch.object(news_api, "get_cache", return_value=disabled_cache),
        patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock),
    ):
        assert await call_injected(
            handler,
            id=NEWS_ID,
            request=None,
            data=None,
            user=_admin(),
            provides={"NewsService": service},
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
        assert await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(cache=object()),
            user=_admin(),
            provides={"NewsService": service},
        ) == {"ok": True}
    cache.invalidate.assert_awaited_once()

    disabled_cache = _cache(enabled=False)
    service.delete_news.return_value = True
    with (
        patch.object(news_api, "get_cache", return_value=disabled_cache),
        patch.object(news_api, "_increment_news_list_version", new_callable=AsyncMock),
    ):
        assert await call_injected(
            handler,
            id=NEWS_ID,
            request=None,
            user=_admin(),
            provides={"NewsService": service},
        ) == {"ok": True}
    disabled_cache.invalidate.assert_not_awaited()

    service.delete_news.return_value = False
    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(cache=None),
            user=_admin(),
            provides={"NewsService": service},
        )
    assert exc_info.value.status_code == 404


async def test_like_news_success_and_missing_paths() -> None:
    handler = inspect.unwrap(news_api.like_news)
    service = AsyncMock()
    user = _user()
    service.get_news_item.return_value = _news_record()
    service.toggle_like.return_value = True

    assert await call_injected(
        handler,
        id=NEWS_ID,
        request=_request(),
        user=user,
        provides={"NewsService": service},
    ) == {"is_liked": True}
    service.toggle_like.assert_awaited_once_with(NEWS_ID, user.id)

    service.get_news_item.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            user=user,
            provides={"NewsService": service},
        )
    assert exc_info.value.status_code == 404


async def test_comment_news_validates_news_content_and_profile_fallback() -> None:
    handler = inspect.unwrap(news_api.comment_on_news)
    service = AsyncMock()
    user = _user()
    comment = SimpleNamespace(
        id=uuid.UUID(int=3),
        content="A comment",
        user_id=user.id,
        created_at="now",
    )
    service.get_news_item.return_value = _news_record()
    service.create_comment.return_value = comment

    result = await call_injected(
        handler,
        id=NEWS_ID,
        request=_request(),
        content=" A comment ",
        user=user,
        provides={"NewsService": service},
    )
    assert result["user_name"] == str(user.email)
    service.create_comment.assert_awaited_once_with(
        NEWS_ID, user.id, "A comment", locale="en"
    )

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            content="   ",
            user=user,
            provides={"NewsService": service},
        )
    assert exc_info.value.status_code == 400

    service.get_news_item.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            content="comment",
            user=user,
            provides={"NewsService": service},
        )
    assert exc_info.value.status_code == 404


async def test_comment_news_sanitizes_content_like_patch_update() -> None:
    handler = inspect.unwrap(news_api.comment_on_news)
    service = AsyncMock()
    service.get_news_item.return_value = _news_record()
    service.create_comment.return_value = SimpleNamespace(
        id=uuid.UUID(int=3),
        content="safe",
        user_id=uuid.UUID(int=2),
        created_at="now",
    )
    user = _user()
    raw_content = '<strong onclick="run()">safe</strong><script>unsafe()</script>'

    await call_injected(
        handler,
        id=NEWS_ID,
        request=_request(),
        content=raw_content,
        user=user,
        provides={"NewsService": service},
    )

    persisted_content = service.create_comment.await_args.args[2]
    expected_content = news_api.schemas.NewsCommentUpdate(content=raw_content).content
    assert persisted_content == expected_content
    assert "<strong>safe</strong>" in persisted_content
    assert "onclick" not in persisted_content.casefold()
    assert "<script" not in persisted_content.casefold()


async def test_comment_news_rejects_overlong_content_before_write() -> None:
    handler = inspect.unwrap(news_api.comment_on_news)
    service = AsyncMock()
    service.get_news_item.return_value = _news_record()
    user = _user()

    with pytest.raises(RequestValidationError) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            content="x" * 1001,
            user=user,
            provides={"NewsService": service},
        )

    errors = exc_info.value.errors()
    assert errors
    assert errors[0]["loc"] == ("body", "content")
    assert "input" not in errors[0]
    service.create_comment.assert_not_awaited()


async def test_comment_news_rejects_content_sanitized_to_empty() -> None:
    handler = inspect.unwrap(news_api.comment_on_news)
    service = AsyncMock()
    service.get_news_item.return_value = _news_record()
    user = _user()

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            content="<script></script>",
            user=user,
            provides={"NewsService": service},
        )

    assert exc_info.value.status_code == 400
    service.create_comment.assert_not_awaited()


async def test_comment_news_missing_news_precedes_overlong_validation() -> None:
    handler = inspect.unwrap(news_api.comment_on_news)
    service = AsyncMock()
    service.get_news_item.return_value = None
    user = _user()

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            content="x" * 1001,
            user=user,
            provides={"NewsService": service},
        )

    assert exc_info.value.status_code == 404
    service.create_comment.assert_not_awaited()


async def test_news_interactions_not_found() -> None:
    handler = inspect.unwrap(news_api.get_news_interact)
    service = AsyncMock()
    service.get_news_item.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            handler,
            id=NEWS_ID,
            request=_request(),
            limit=10,
            offset=2,
            user=None,
            provides={"NewsService": service},
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

    result = await call_injected(
        handler,
        id=NEWS_ID,
        request=_request(),
        limit=10,
        offset=2,
        user=user,
        provides={"NewsService": service},
    )

    assert result.likes_count == 2
    service.get_interactions.assert_awaited_once_with(
        NEWS_ID, user.id, limit=10, offset=2
    )


async def test_news_interactions_forwards_later_comment_pages() -> None:
    """A later comment page must reach the service with its offset (AUD-030)."""
    handler = inspect.unwrap(news_api.get_news_interact)
    service = AsyncMock()
    service.get_news_item.return_value = _news_record()
    service.get_interactions.return_value = {
        "likes_count": 0,
        "is_liked": False,
        "comments": [],
        "comments_count": 45,
    }

    result = await call_injected(
        handler,
        id=NEWS_ID,
        request=_request(),
        limit=20,
        offset=40,
        user=None,
        provides={"NewsService": service},
    )

    assert result.comments_count == 45
    service.get_interactions.assert_awaited_once_with(
        NEWS_ID, None, limit=20, offset=40
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

    result = await call_injected(
        handler,
        comment_id=uuid.UUID(int=3),
        request=_request(),
        data=data,
        user=user,
        provides={"NewsService": service},
    )
    assert result["user_name"] == str(user.email)

    for error, status_code in ((LookupError(), 404), (PermissionError(), 403)):
        service.update_comment.side_effect = error
        with pytest.raises(HTTPException) as exc_info:
            await call_injected(
                handler,
                comment_id=uuid.UUID(int=3),
                request=_request(),
                data=data,
                user=user,
                provides={"NewsService": service},
            )
        assert exc_info.value.status_code == status_code
    service.update_comment.side_effect = None


async def test_delete_comment_success_and_error_paths() -> None:
    handler = inspect.unwrap(news_api.delete_comment)
    service = AsyncMock()
    comment_id = uuid.UUID(int=3)

    for user, expected_admin in ((_user(), False), (_admin(), False)):
        assert await call_injected(
            handler,
            comment_id=comment_id,
            request=_request(),
            user=user,
            checker=SimpleNamespace(check_admin=AsyncMock(return_value=False)),
            provides={"NewsService": service},
        ) == {"ok": True}
        assert (
            service.delete_comment.await_args_list[-1].kwargs["is_admin"]
            is expected_admin
        )

    for error, status_code in ((LookupError(), 404), (PermissionError(), 403)):
        service.delete_comment.side_effect = error
        with pytest.raises(HTTPException) as exc_info:
            await call_injected(
                handler,
                comment_id=comment_id,
                request=_request(),
                user=_user(),
                checker=SimpleNamespace(check_admin=AsyncMock(return_value=False)),
                provides={"NewsService": service},
            )
        assert exc_info.value.status_code == status_code
    service.delete_comment.side_effect = None


async def test_delete_comment_preserves_service_denial_after_admin_check() -> None:
    service = AsyncMock()
    service.delete_comment.side_effect = PermissionError("Comment cannot be removed")
    checker = SimpleNamespace(check_admin=AsyncMock(return_value=True))
    comment_id = uuid.UUID(int=3)
    user = _admin()

    with pytest.raises(HTTPException) as denied:
        await call_injected(
            inspect.unwrap(news_api.delete_comment),
            comment_id=comment_id,
            request=_request(),
            user=user,
            checker=checker,
            provides={"NewsService": service},
        )

    assert denied.value.status_code == 403
    assert [
        call.kwargs["is_admin"] for call in service.delete_comment.await_args_list
    ] == [
        False,
        True,
    ]


async def test_upload_news_image_scans_and_saves() -> None:
    handler = inspect.unwrap(news_api.upload_news_image)
    upload = SimpleNamespace(size=12)
    user = _admin()
    service = AsyncMock()

    with (
        patch.object(news_api, "scan_for_malware", new_callable=AsyncMock) as scan,
        patch.object(
            news_api,
            "save_upload",
            new_callable=AsyncMock,
            return_value=NEWS_IMAGE_URL,
        ) as save,
    ):
        result = await call_injected(
            handler,
            file=upload,
            request=_request(),
            user=user,
            provides={"NewsService": service},
        )

    assert result == {"url": NEWS_IMAGE_URL}
    scan.assert_awaited_once_with(upload, locale="en", size_bytes=12)
    save.assert_awaited_once_with(upload, "news_images", "news", locale="en")
    service.register_uploaded_image.assert_awaited_once_with(
        NEWS_IMAGE_URL, owner_user_id=user.id
    )


async def test_semantic_search_returns_not_modified_for_matching_etag() -> None:
    handler = inspect.unwrap(news_api.semantic_search)
    cache = _cache()
    vector = AsyncMock()
    vector.get_embedding.return_value = [0.1, 0.2]
    vector.search_similar.return_value = []
    service = AsyncMock()
    request = _request()

    with (
        patch.object(news_api, "get_cache", return_value=cache),
        patch.object(
            news_api,
            "_get_news_list_version",
            new_callable=AsyncMock,
            return_value="v1",
        ),
    ):
        first_response = Response()
        await call_injected(
            handler,
            request=request,
            response=first_response,
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=None,
            _user=_user(),
            provides={
                "AsyncDatabaseSession": AsyncMock(),
                "VectorService": vector,
                "NewsService": service,
            },
        )
        etag = first_response.headers["ETag"]

        result = await call_injected(
            handler,
            request=request,
            response=Response(),
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=etag,
            _user=_user(),
            provides={
                "AsyncDatabaseSession": AsyncMock(),
                "VectorService": vector,
                "NewsService": service,
            },
        )

    assert isinstance(result, Response)
    assert result.status_code == 304
    assert result.headers["ETag"] == etag
    assert vector.get_embedding.await_count == 2
    vector.get_embedding.assert_awaited_with("query")


async def test_semantic_search_etag_is_locale_specific_and_reuses_same_locale() -> None:
    handler = inspect.unwrap(news_api.semantic_search)
    cache = _cache()
    vector = AsyncMock()
    vector.get_embedding.return_value = [0.1, 0.2]
    vector.search_similar.return_value = [_news_record()]
    service = MagicMock()
    service.serialize_news.side_effect = lambda _item, locale: {"locale": locale}
    ru_response = Response()
    en_response = Response()
    repeated_en_response = Response()

    with (
        patch.object(news_api, "get_cache", return_value=cache),
        patch.object(
            news_api,
            "_get_news_list_version",
            new_callable=AsyncMock,
            return_value="v1",
        ),
    ):
        ru_result = await call_injected(
            handler,
            request=_request(locale="ru-RU"),
            response=ru_response,
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=None,
            _user=_user(),
            provides={
                "AsyncDatabaseSession": AsyncMock(),
                "VectorService": vector,
                "NewsService": service,
            },
        )
        en_result = await call_injected(
            handler,
            request=_request(locale="en-US"),
            response=en_response,
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=ru_response.headers["ETag"],
            _user=_user(),
            provides={
                "AsyncDatabaseSession": AsyncMock(),
                "VectorService": vector,
                "NewsService": service,
            },
        )
        repeated_en_result = await call_injected(
            handler,
            request=_request(locale="en-US"),
            response=repeated_en_response,
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=en_response.headers["ETag"],
            _user=_user(),
            provides={
                "AsyncDatabaseSession": AsyncMock(),
                "VectorService": vector,
                "NewsService": service,
            },
        )

    assert ru_result == [{"locale": "ru"}]
    assert en_result == [{"locale": "en"}]
    assert en_response.headers["Content-Language"] == "en"
    assert ru_response.headers["Content-Language"] == "ru"
    assert "Accept-Language" in en_response.headers["Vary"]
    assert en_response.headers["ETag"] != ru_response.headers["ETag"]
    assert isinstance(repeated_en_result, Response)
    assert repeated_en_result.status_code == 304
    assert repeated_en_result.headers["ETag"] == en_response.headers["ETag"]
    assert repeated_en_result.headers["Content-Language"] == "en"
    assert "Accept-Language" in repeated_en_result.headers["Vary"]


async def test_semantic_search_unavailability_precedes_matching_etag() -> None:
    handler = inspect.unwrap(news_api.semantic_search)
    cache = _cache()
    vector = AsyncMock()
    vector.get_embedding.side_effect = SemanticSearchUnavailableError(
        "provider credentials and error details must remain private"
    )
    service = AsyncMock()
    response = Response()
    get_version = AsyncMock(return_value="v1")
    etag_matches = MagicMock(return_value=True)

    with (
        patch.object(news_api, "get_cache", return_value=cache),
        patch.object(news_api, "_get_news_list_version", get_version),
        patch.object(news_api, "etag_matches", etag_matches),
    ):
        with pytest.raises(HTTPException) as exc:
            await call_injected(
                handler,
                request=_request(),
                response=response,
                query="query",
                limit=5,
                min_score=0.7,
                if_none_match='"match"',
                _user=_user(),
                provides={
                    "AsyncDatabaseSession": AsyncMock(),
                    "VectorService": vector,
                    "NewsService": service,
                },
            )

    assert exc.value.status_code == 503
    assert exc.value.detail == SEMANTIC_SEARCH_UNAVAILABLE_DETAIL
    vector.get_embedding.assert_awaited_once_with("query")
    get_version.assert_not_awaited()
    etag_matches.assert_not_called()


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
        result = await call_injected(
            handler,
            request=_request(),
            response=response,
            query="query",
            limit=5,
            min_score=0.7,
            if_none_match=None,
            _user=_user(),
            provides={
                "AsyncDatabaseSession": AsyncMock(),
                "VectorService": vector,
                "NewsService": service,
            },
        )

    assert result == [{"id": NEWS_ID}]
    vector.get_embedding.assert_awaited_once_with("query")
    vector.search_similar.assert_awaited_once()
    assert response.headers["ETag"]


@pytest.mark.asyncio
async def test_create_news_maps_media_ownership_conflict_to_forbidden_without_mutation():
    from app.schemas import schemas
    from app.services.news_service import NewsImageOwnershipError

    handler = inspect.unwrap(news_api.create_news)
    service = AsyncMock()
    service.create_news.side_effect = NewsImageOwnershipError("news_image_not_owned")
    service.serialize_news = MagicMock()
    request = _request(cache=object(), locale="ru")

    with (
        patch.object(
            news_api, "_increment_news_list_version", new_callable=AsyncMock
        ) as increment,
        pytest.raises(HTTPException) as exc,
    ):
        await call_injected(
            handler,
            data=schemas.NewsCreate(
                title="Owned image", content="Body", image_url=NEWS_IMAGE_URL
            ),
            request=request,
            user=_admin(),
            provides={"NewsService": service},
        )

    assert exc.value.status_code == 403
    service.create_news.assert_awaited_once()
    increment.assert_not_awaited()
    service.serialize_news.assert_not_called()


@pytest.mark.asyncio
async def test_upload_news_image_maps_registration_conflict_after_scan_and_save():
    from app.services.news_service import NewsImageOwnershipError

    handler = inspect.unwrap(news_api.upload_news_image)
    upload = SimpleNamespace(size=12)
    service = AsyncMock()
    service.register_uploaded_image.side_effect = NewsImageOwnershipError(
        "news_image_not_owned"
    )
    order: list[str] = []

    async def scan(_file, *, locale, size_bytes):
        order.append(f"scan:{locale}:{size_bytes}")

    async def save(_file, folder, prefix, *, locale):
        order.append(f"save:{folder}:{prefix}:{locale}")
        return NEWS_IMAGE_URL

    with (
        patch.object(news_api, "scan_for_malware", side_effect=scan),
        patch.object(news_api, "save_upload", side_effect=save),
        pytest.raises(HTTPException) as exc,
    ):
        await call_injected(
            handler,
            file=upload,
            request=_request(locale="en"),
            user=_admin(),
            provides={"NewsService": service},
        )

    assert exc.value.status_code == 403
    assert order == ["scan:en:12", "save:news_images:news:en"]
    service.register_uploaded_image.assert_awaited_once_with(
        NEWS_IMAGE_URL, owner_user_id=_admin().id
    )
