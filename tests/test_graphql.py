import datetime as dt

import pytest
from httpx import AsyncClient

from app.models import Event, News, Schedule


@pytest.mark.asyncio
async def test_graphql_news_query(root_client: AsyncClient, db_session, user_factory):
    # Setup: Create a user and some news
    user = await user_factory()
    news1 = News(title="News 1", content="Content 1", author_id=user.id)
    news2 = News(title="News 2", content="Content 2", author_id=user.id)
    db_session.add_all([news1, news2])
    await db_session.commit()

    query = """
    query {
      news(limit: 10) {
        items {
          title
          content
          author {
            fullName
          }
        }
        pageInfo {
          totalCount
        }
      }
    }
    """
    response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["news"]["pageInfo"]["totalCount"] == 2
    assert len(data["news"]["items"]) == 2
    # News are ordered by created_at desc.
    # Since they are created in the same transaction,
    # the order might depend on ID or internal timing if timestamps are identical.
    # But usually, the latest created is first.


@pytest.mark.asyncio
async def test_graphql_news_by_id(root_client: AsyncClient, db_session, user_factory):
    user = await user_factory()
    news = News(title="Specific News", content="Content", author_id=user.id)
    db_session.add(news)
    await db_session.commit()
    await db_session.refresh(news)

    query = f"""
    query {{
      newsById(id: "{news.id}") {{
        title
        content
      }}
    }}
    """
    response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["newsById"]["title"] == "Specific News"


@pytest.mark.asyncio
async def test_graphql_events_query(root_client: AsyncClient, db_session, user_factory):
    user = await user_factory()
    now = dt.datetime.now(dt.UTC)
    event1 = Event(
        title="Event 1",
        starts_at=now + dt.timedelta(days=1),
        ends_at=now + dt.timedelta(days=1, hours=2),
        created_by=user.id,
        is_active=True,
    )
    event2 = Event(
        title="Event 2",
        starts_at=now + dt.timedelta(days=2),
        ends_at=now + dt.timedelta(days=2, hours=2),
        created_by=user.id,
        is_active=False,
    )
    db_session.add_all([event1, event2])
    await db_session.commit()

    # Query active events
    query = """
    query {
      events(activeOnly: true) {
        items {
          title
          organizer {
            fullName
          }
        }
        pageInfo {
          totalCount
        }
      }
    }
    """
    response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["events"]["pageInfo"]["totalCount"] == 1
    assert data["events"]["items"][0]["title"] == "Event 1"


@pytest.mark.asyncio
async def test_graphql_schedule_query(root_client: AsyncClient, db_session):
    now = dt.datetime.now(dt.UTC)
    schedule_entry = Schedule(
        group_id=101,
        weekday="Monday",
        start_time=now,
        end_time=now + dt.timedelta(hours=1, minutes=30),
        subject="Mathematics",
        lesson_type="Lecture",
    )
    db_session.add(schedule_entry)
    await db_session.commit()

    query = """
    query {
      schedule(groupId: 101) {
        subject
        lessonType: type
        dayOfWeek
      }
    }
    """
    response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["schedule"]) == 1
    assert data["schedule"][0]["subject"] == "Mathematics"
    assert data["schedule"][0]["dayOfWeek"] == "Monday"


@pytest.mark.asyncio
async def test_graphql_me_unauthenticated(root_client: AsyncClient):
    query = """
    query {
      me {
        email
      }
    }
    """
    response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["me"] is None


@pytest.mark.asyncio
async def test_graphql_me_authenticated(root_client: AsyncClient, user_factory):
    user = await user_factory()
    from app.auth.security import create_access_token

    token = await create_access_token(sub=str(user.id))

    query = """
    query {
      me {
        email
        fullName
      }
    }
    """
    response = await root_client.post(
        "/graphql", json={"query": query}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["me"]["email"] == user.email


@pytest.mark.asyncio
async def test_graphql_context_error_handling(root_client: AsyncClient):
    # Test with invalid token to cover exception block in get_context
    query = "{ me { email } }"
    response = await root_client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["me"] is None
