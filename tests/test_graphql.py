import datetime as dt
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models import Event, News, Schedule
from app.models.schedule import Group


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
    group = Group(name="CS-101")
    db_session.add(group)
    await db_session.flush()
    group_id = group.id
    schedule_entry = Schedule(
        group_id=group_id,
        weekday="monday",
        start_time=now,
        end_time=now + dt.timedelta(hours=1, minutes=30),
        subject="Mathematics",
        lesson_type="lecture",
    )
    db_session.add(schedule_entry)
    await db_session.commit()

    query = f"""
    query {{
      schedule(groupId: "{group_id}") {{
        subject
        lessonType: type
        dayOfWeek
      }}
    }}
    """
    with patch(
        "app.auth.rbac.PermissionChecker.check_permission",
        new_callable=AsyncMock,
        return_value=True,
    ):
        response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["schedule"]) == 1
    assert data["schedule"][0]["subject"] == "Mathematics"
    assert data["schedule"][0]["dayOfWeek"] == "monday"


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
async def test_graphql_me_authenticated(
    root_client: AsyncClient, user_factory, db_session
):
    user = await user_factory()
    from tests.fixtures.auth.auth_fixtures import create_access_token

    token, _ = await create_access_token(sub=str(user.id), db=db_session)

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


@pytest.mark.asyncio
async def test_graphql_context_non_bearer_auth(root_client: AsyncClient):
    # Test with Basic auth which is ignored by get_context
    query = "{ me { email } }"
    response = await root_client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["me"] is None


@pytest.mark.asyncio
async def test_graphql_context_user_not_found(
    root_client: AsyncClient, monkeypatch, db_session
):
    # Test with valid token but non-existent user ID.
    # Build JWT directly (no ActiveSession row) to avoid FK constraint on
    # active_sessions.user_id — the GraphQL context will fail to find the
    # session and return anonymous context, which is what we test.
    from app.auth.security import _mint_pure_jwt

    token = _mint_pure_jwt(
        subject=str(uuid.uuid4()),
        expires_minutes=30,
        extra_claims={"jti": str(uuid.uuid4())},
    )

    query = "{ me { email } }"
    response = await root_client.post(
        "/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["me"] is None


@pytest.mark.asyncio
async def test_graphql_context_db_error(
    root_client: AsyncClient, monkeypatch, db_session
):
    # Test with database error during user fetching.
    # Build JWT directly (no ActiveSession row) to avoid FK constraint.
    from app.auth.security import _mint_pure_jwt

    token = _mint_pure_jwt(
        subject=str(uuid.uuid4()),
        expires_minutes=30,
        extra_claims={"jti": str(uuid.uuid4())},
    )

    # Mock select to raise error

    async def mock_execute(*args, **kwargs):
        raise Exception("Database explosion")

    # We need to monkeypatch the session executed inside get_context
    # This is tricky because it's an 'async with' session.
    # But get_context logs the error and continues.

    query = "{ me { email } }"
    # We'll use a malformed token that causes decode_token to pass but then fail later?
    # Actually, the easiest is to mock decode_token to return a payload,
    # but then have the session.execute fail.

    with patch("app.core.database.async_session") as mock_session_cm:
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB Fail")
        mock_session_cm.return_value.__aenter__.return_value = mock_session

        response = await root_client.post(
            "/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        # Should still return None for 'me' due to exception handling in get_context
        assert response.json()["data"]["me"] is None


@pytest.mark.asyncio
async def test_graphql_news_query_keyset_cursor(
    root_client: AsyncClient, db_session, user_factory
):
    from app.utils.pagination import encode_datetime_cursor

    user = await user_factory()
    now = dt.datetime.now(dt.UTC)
    news1 = News(
        title="News 1",
        content="Content 1",
        author_id=user.id,
        created_at=now - dt.timedelta(minutes=10),
    )
    news2 = News(
        title="News 2",
        content="Content 2",
        author_id=user.id,
        created_at=now - dt.timedelta(minutes=5),
    )
    news3 = News(title="News 3", content="Content 3", author_id=user.id, created_at=now)
    db_session.add_all([news1, news2, news3])
    await db_session.commit()

    # Query first page (limit = 2)
    query = """
    query {
      news(limit: 2) {
        items {
          title
        }
        pageInfo {
          hasNextPage
          hasPreviousPage
          cursor
        }
      }
    }
    """
    response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    res_data = response.json()["data"]["news"]
    assert len(res_data["items"]) == 2
    assert res_data["pageInfo"]["hasNextPage"] is True
    assert res_data["pageInfo"]["hasPreviousPage"] is False
    cursor = res_data["pageInfo"]["cursor"]
    assert cursor is not None

    # Query second page with cursor
    query_page2 = f"""
    query {{
      news(limit: 2, after: "{cursor}") {{
        items {{
          title
        }}
        pageInfo {{
          hasNextPage
          hasPreviousPage
        }}
      }}
    }}
    """
    response2 = await root_client.post("/graphql", json={"query": query_page2})
    assert response2.status_code == 200
    res_data2 = response2.json()["data"]["news"]
    assert len(res_data2["items"]) == 1
    assert res_data2["pageInfo"]["hasPreviousPage"] is True

    # Query with invalid base64 cursor
    query_invalid_cursor = """
    query {
      news(limit: 2, after: "not-base64-invalid!!!") {
        items {
          title
        }
      }
    }
    """
    response_invalid = await root_client.post(
        "/graphql", json={"query": query_invalid_cursor}
    )
    assert response_invalid.status_code == 200
    assert len(response_invalid.json()["data"]["news"]["items"]) == 2

    # Query with valid base64 but invalid UUID tie-breaker
    invalid_uuid_cursor = encode_datetime_cursor(now, "invalid-uuid-tiebreaker")
    query_invalid_uuid = f"""
    query {{
      news(limit: 2, after: "{invalid_uuid_cursor}") {{
        items {{
          title
        }}
      }}
    }}
    """
    response_invalid_uuid = await root_client.post(
        "/graphql", json={"query": query_invalid_uuid}
    )
    assert response_invalid_uuid.status_code == 200
    assert len(response_invalid_uuid.json()["data"]["news"]["items"]) == 2


@pytest.mark.asyncio
async def test_graphql_news_by_id_negatives(root_client: AsyncClient):
    # Case 1: Invalid UUID format
    query1 = """
    query {
      newsById(id: "invalid-uuid-format") {
        title
      }
    }
    """
    response1 = await root_client.post("/graphql", json={"query": query1})
    assert response1.status_code == 200
    assert response1.json()["data"]["newsById"] is None

    # Case 2: Non-existent UUID
    random_uuid = str(uuid.uuid4())
    query2 = f"""
    query {{
      newsById(id: "{random_uuid}") {{
        title
      }}
    }}
    """
    response2 = await root_client.post("/graphql", json={"query": query2})
    assert response2.status_code == 200
    assert response2.json()["data"]["newsById"] is None


@pytest.mark.asyncio
async def test_graphql_events_query_keyset_cursor(
    root_client: AsyncClient, db_session, user_factory
):
    from app.utils.pagination import encode_datetime_cursor

    user = await user_factory()
    now = dt.datetime.now(dt.UTC)
    event1 = Event(
        title="E1",
        starts_at=now - dt.timedelta(minutes=10),
        ends_at=now + dt.timedelta(hours=1),
        created_by=user.id,
    )
    event2 = Event(
        title="E2",
        starts_at=now - dt.timedelta(minutes=5),
        ends_at=now + dt.timedelta(hours=1),
        created_by=user.id,
    )
    event3 = Event(
        title="E3",
        starts_at=now,
        ends_at=now + dt.timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add_all([event1, event2, event3])
    await db_session.commit()

    # Query first page
    query = """
    query {
      events(limit: 2, activeOnly: false) {
        items {
          title
        }
        pageInfo {
          hasNextPage
          hasPreviousPage
          cursor
        }
      }
    }
    """
    response = await root_client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    res_data = response.json()["data"]["events"]
    assert len(res_data["items"]) == 2
    assert res_data["pageInfo"]["hasNextPage"] is True
    cursor = res_data["pageInfo"]["cursor"]

    # Query next page
    query_page2 = f"""
    query {{
      events(limit: 2, activeOnly: false, after: "{cursor}") {{
        items {{
          title
        }}
        pageInfo {{
          hasPreviousPage
        }}
      }}
    }}
    """
    response2 = await root_client.post("/graphql", json={"query": query_page2})
    assert response2.status_code == 200
    res_data2 = response2.json()["data"]["events"]
    assert len(res_data2["items"]) == 1
    assert res_data2["pageInfo"]["hasPreviousPage"] is True

    # Query with invalid cursor
    query_invalid = """
    query {
      events(limit: 2, activeOnly: false, after: "invalid-cursor-format!!!") {
        items {
          title
        }
      }
    }
    """
    response_invalid = await root_client.post("/graphql", json={"query": query_invalid})
    assert response_invalid.status_code == 200
    assert len(response_invalid.json()["data"]["events"]["items"]) == 2

    # Query with valid base64 but invalid UUID tie-breaker
    invalid_uuid_cursor = encode_datetime_cursor(now, "invalid-uuid-tiebreaker")
    query_invalid_uuid = f"""
    query {{
      events(limit: 2, activeOnly: false, after: "{invalid_uuid_cursor}") {{
        items {{
          title
        }}
      }}
    }}
    """
    response_invalid_uuid = await root_client.post(
        "/graphql", json={"query": query_invalid_uuid}
    )
    assert response_invalid_uuid.status_code == 200
    assert len(response_invalid_uuid.json()["data"]["events"]["items"]) == 2


@pytest.mark.asyncio
async def test_graphql_schedule_negatives_and_errors(root_client: AsyncClient):
    # Case 1: Invalid group UUID format
    query1 = """
    query {
      schedule(groupId: "invalid-group-uuid-format") {
        subject
      }
    }
    """
    response1 = await root_client.post("/graphql", json={"query": query1})
    assert response1.status_code == 200
    assert response1.json()["data"]["schedule"] == []

    # Case 2: Permission denied (check_permission returns False)
    group_id = str(uuid.uuid4())
    query2 = f"""
    query {{
      schedule(groupId: "{group_id}") {{
        subject
      }}
    }}
    """
    with patch(
        "app.auth.rbac.PermissionChecker.check_permission",
        new_callable=AsyncMock,
        return_value=False,
    ):
        response2 = await root_client.post("/graphql", json={"query": query2})
    assert response2.status_code == 200
    assert response2.json()["data"]["schedule"] == []

    # Case 3: SpiceDB exception raised (fail-closed, logs error and returns [])
    with patch(
        "app.auth.rbac.PermissionChecker.check_permission",
        new_callable=AsyncMock,
        side_effect=Exception("SpiceDB Connection Refused"),
    ):
        response3 = await root_client.post("/graphql", json={"query": query2})
    assert response3.status_code == 200
    assert response3.json()["data"]["schedule"] == []

    # Case 4: PermissionChecker is None
    from app.graphql.context import GraphQLContext

    original_init = GraphQLContext.__init__

    def mock_init(self, *args, **kwargs):
        kwargs["checker"] = None
        original_init(self, *args, **kwargs)

    with patch.object(GraphQLContext, "__init__", mock_init):
        response4 = await root_client.post("/graphql", json={"query": query2})
    assert response4.status_code == 200
    assert response4.json()["data"]["schedule"] == []
