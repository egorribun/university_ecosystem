from datetime import UTC, datetime, timedelta

import pytest

import app.models as models


async def _robust_invalidate(cache, *patterns):
    """Helper to invalidate cache keys handling both Wrapper and Client objects.

    Also clears L1 memory cache for multi-layer caches to ensure
    proper cache invalidation during tests.
    """
    from app.core import cache as core_cache

    # Clear L1 memory caches for relevant patterns
    for pattern in patterns:
        if pattern.startswith("schedule:"):
            core_cache.schedule_cache.l1.invalidate_prefix("schedule:")
        if pattern.startswith("news:"):
            core_cache.news_cache.l1.invalidate_prefix("news:")

    if hasattr(cache, "invalidate"):
        # Wrapper object (e.g. _TestingRedisCache)
        await cache.invalidate(*patterns)
    else:
        # Raw client (e.g. FakeRedis)
        for pattern in patterns:
            keys = await cache.keys(pattern)
            if keys:
                await cache.delete(*keys)


@pytest.mark.asyncio
async def test_schedule_cache_supports_etag(async_client, db_session, fake_cache):
    group = models.Group(name="Test Group", course=1, faculty="IT")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    start = datetime.now(UTC).replace(microsecond=0)
    lesson = models.Schedule(
        group_id=group.id,
        subject="Math",
        teacher="Alice",
        room="101",
        weekday="monday",
        start_time=start,
        end_time=start + timedelta(hours=1),
        parity="both",
        lesson_type="Лекция",
    )
    db_session.add(lesson)
    await db_session.commit()

    response = await async_client.get(f"/schedule/{group.id}")
    assert response.status_code == 200
    first_etag = response.headers.get("ETag")
    assert first_etag
    assert len(response.json()) == 1

    cached_response = await async_client.get(
        f"/schedule/{group.id}", headers={"If-None-Match": first_etag}
    )
    assert cached_response.status_code == 304
    assert cached_response.headers.get("ETag") == first_etag

    second_lesson = models.Schedule(
        group_id=group.id,
        subject="Physics",
        teacher="Bob",
        room="202",
        weekday="monday",
        start_time=start + timedelta(days=1),
        end_time=start + timedelta(days=1, hours=1),
        parity="both",
        lesson_type="Семинар",
    )
    db_session.add(second_lesson)
    await db_session.commit()

    await _robust_invalidate(fake_cache, f"schedule:group:{group.id}")

    refreshed = await async_client.get(
        f"/schedule/{group.id}", headers={"If-None-Match": first_etag}
    )
    assert refreshed.status_code == 200
    assert refreshed.headers.get("ETag") != first_etag
    assert len(refreshed.json()) == 2


@pytest.mark.asyncio
async def test_news_list_and_detail_cache(async_client, db_session, fake_cache):
    news = models.News(title="First", content="Initial")
    db_session.add(news)
    await db_session.commit()
    await db_session.refresh(news)

    list_response = await async_client.get("/news")
    assert list_response.status_code == 200
    list_etag = list_response.headers.get("ETag")
    assert list_etag
    assert len(list_response.json()["items"]) == 1

    cached_list = await async_client.get("/news", headers={"If-None-Match": list_etag})
    assert cached_list.status_code == 304
    assert cached_list.headers.get("ETag") == list_etag

    auth_headers = {"Authorization": "Bearer cache-news"}

    detail_response = await async_client.get(f"/news/{news.id}", headers=auth_headers)
    assert detail_response.status_code == 200
    detail_etag = detail_response.headers.get("ETag")
    assert detail_etag

    cached_detail = await async_client.get(
        f"/news/{news.id}",
        headers={"If-None-Match": detail_etag, **auth_headers},
    )
    assert cached_detail.status_code == 304
    assert cached_detail.headers.get("ETag") == detail_etag

    updated_title = "Updated"
    news.title = updated_title
    await db_session.commit()
    await db_session.refresh(news)

    await _robust_invalidate(fake_cache, "news:list*", "ue:news:item:*")

    list_after_update = await async_client.get(
        "/news", headers={"If-None-Match": list_etag}
    )
    assert list_after_update.status_code == 200
    assert list_after_update.headers.get("ETag") != list_etag

    detail_after_update = await async_client.get(
        f"/news/{news.id}",
        headers={"If-None-Match": detail_etag, **auth_headers},
    )
    assert detail_after_update.status_code == 200
    assert detail_after_update.headers.get("ETag") != detail_etag
    assert detail_after_update.json()["title"] == updated_title

    another_news = models.News(title="Second", content="More")
    db_session.add(another_news)
    await db_session.commit()

    await _robust_invalidate(fake_cache, "news:list*")

    list_with_two = await async_client.get("/news")
    assert list_with_two.status_code == 200
    assert len(list_with_two.json()["items"]) == 2
