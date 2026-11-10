from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.news import _comment_author_name
from app.core.database import async_session
from app.models.news import News, NewsComment
from app.repositories.unit_of_work import uow_from_session
from app.services.news_service import NewsService
from app.services.vector_service import VectorService
from tests.conftest import install_dishka_override


@pytest.fixture
async def comment_context(app, db_session, user_factory):
    user = await user_factory()
    article = News(title="Comment validation", content="Synthetic article")
    db_session.add(article)
    await db_session.flush()
    comment = NewsComment(news_id=article.id, user_id=user.id, content="Original")
    db_session.add(comment)
    await db_session.commit()
    service = NewsService(uow_from_session(db_session), cast(VectorService, None))
    install_dishka_override(app, NewsService=service)
    app.dependency_overrides[get_current_user] = lambda: user
    return user, article.id, comment.id


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize(
    "full_name", [None, "", "   ", "Named Student", " Named Student "]
)
async def test_comment_mutation_returns_non_null_display_name(
    async_client, db_session, comment_context, operation, full_name
):
    user, article_id, comment_id = comment_context
    user.profile.full_name = full_name
    await db_session.commit()
    expected_name = full_name if full_name and full_name.strip() else "User"
    assert _comment_author_name(user) == expected_name
    if operation == "create":
        response = await async_client.post(
            f"/news/{article_id}/comment", json={"content": "Saved comment"}
        )
    else:
        response = await async_client.patch(
            f"/news/comments/{comment_id}", json={"content": "Saved comment"}
        )
    assert response.status_code == 200
    assert response.json()["user_name"] == ((full_name or "").strip() or "User")
    async with async_session() as observer:
        comments = list(
            await observer.scalars(
                select(NewsComment).where(NewsComment.news_id == article_id)
            )
        )
        assert len(comments) == (2 if operation == "create" else 1)
        assert sum(row.content == "Saved comment" for row in comments) == 1


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_comment_mutation_preserves_missing_profile_email_fallback(
    async_client, db_session, comment_context, operation
):
    user, article_id, comment_id = comment_context
    user.profile = None
    await db_session.commit()
    if operation == "create":
        response = await async_client.post(
            f"/news/{article_id}/comment", json={"content": "Saved comment"}
        )
    else:
        response = await async_client.patch(
            f"/news/comments/{comment_id}", json={"content": "Saved comment"}
        )
    assert response.status_code == 200
    assert response.json()["user_name"] == user.email


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("content", ["   ", "<script></script>", "<!-- erased -->"])
async def test_comment_mutation_rejects_empty_sanitized_content_without_write(
    async_client, comment_context, operation, content
):
    _, article_id, comment_id = comment_context
    headers = {"Accept-Language": "en"}
    if operation == "create":
        response = await async_client.post(
            f"/news/{article_id}/comment", json={"content": content}, headers=headers
        )
    else:
        response = await async_client.patch(
            f"/news/comments/{comment_id}", json={"content": content}, headers=headers
        )
    expected_status = 422 if operation == "update" and content == "   " else 400
    assert response.status_code == expected_status
    if expected_status == 400:
        assert response.json()["detail"] == "A required field is empty"
    else:
        error = response.json()["detail"][0]
        assert error["loc"] == ["body", "content"]
        assert error["type"] == "string_too_short"
    async with async_session() as observer:
        comments = list(
            await observer.scalars(
                select(NewsComment).where(NewsComment.news_id == article_id)
            )
        )
        assert len(comments) == 1
        assert comments[0].content == "Original"


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_comment_mutation_preserves_allowed_html_and_strips_unsafe_attributes(
    async_client, comment_context, operation
):
    _, article_id, comment_id = comment_context
    payload = {"content": '<strong onclick="synthetic()">Safe</strong>'}
    if operation == "create":
        response = await async_client.post(f"/news/{article_id}/comment", json=payload)
    else:
        response = await async_client.patch(
            f"/news/comments/{comment_id}", json=payload
        )
    assert response.status_code == 200
    assert response.json()["content"] == "<strong>Safe</strong>"
    async with async_session() as observer:
        persisted = await observer.get(NewsComment, UUID(response.json()["id"]))
        assert persisted is not None
        assert persisted.content == "<strong>Safe</strong>"


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("length", [1000, 1001])
async def test_comment_mutation_keeps_length_limit(
    async_client, comment_context, operation, length
):
    _, article_id, comment_id = comment_context
    payload = {"content": "x" * length}
    if operation == "create":
        response = await async_client.post(f"/news/{article_id}/comment", json=payload)
    else:
        response = await async_client.patch(
            f"/news/comments/{comment_id}", json=payload
        )
    assert response.status_code == (200 if length == 1000 else 422)
