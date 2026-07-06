from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps.services import (
    get_analytics_service,
    get_auth_service,
    get_chat_command_service,
    get_chat_creation_service,
    get_chat_query_service,
    get_chat_service,
    get_event_service,
    get_geolocation_service,
    get_login_service,
    get_news_service,
    get_read_chat_query_service,
    get_read_chat_service,
    get_read_event_service,
    get_read_news_service,
    get_read_schedule_service,
    get_read_story_service,
    get_redis_session_service,
    get_schedule_service,
    get_session_service,
    get_story_service,
)


@pytest.mark.asyncio
async def test_all_api_deps_services():
    """Verify that all dependency builder functions return the correct service types."""
    mock_session = MagicMock()
    mock_uow = MagicMock()

    # We patch uow_from_session to return mock_uow
    with patch("app.repositories.unit_of_work.uow_from_session", return_value=mock_uow):
        # 1. Chat creation
        with patch("app.deps.cache.get_cache"):
            chat_creation = get_chat_creation_service(mock_session)
            assert chat_creation is not None

        # 2. Chat queries
        chat_query = get_chat_query_service(mock_session)
        assert chat_query is not None

        read_chat_query = get_read_chat_query_service(mock_session)
        assert read_chat_query is not None

        # 3. Chat legacy aliases
        with patch(
            "app.api.deps.services.get_chat_message_dispatcher"
        ) as mock_dispatcher:
            get_chat_service(mock_session)
            mock_dispatcher.assert_called_with(mock_session)

            get_chat_command_service(mock_session)
            mock_dispatcher.assert_called_with(mock_session)

        get_read_chat_service(mock_session)  # calls get_read_chat_query_service

        # 4. Events
        event_serv = get_event_service(mock_session, MagicMock())
        assert event_serv is not None

        read_event_serv = get_read_event_service(mock_session, MagicMock())
        assert read_event_serv is not None

        # 5. News
        news_serv = get_news_service(mock_session, MagicMock())
        assert news_serv is not None

        read_news_serv = get_read_news_service(mock_session, MagicMock())
        assert read_news_serv is not None

        # 6. Story
        story_serv = get_story_service(mock_session)
        assert story_serv is not None

        read_story_serv = get_read_story_service(mock_session)
        assert read_story_serv is not None

        # 7. Schedule
        schedule_serv = get_schedule_service(mock_session)
        assert schedule_serv is not None

        read_schedule_serv = get_read_schedule_service(mock_session)
        assert read_schedule_serv is not None

        # 8. Auth
        auth_serv = get_auth_service(mock_session)
        assert auth_serv is not None

        # 9. Session
        session_serv = get_session_service(mock_session)
        assert session_serv is not None

        # 10. Geolocation
        mock_geo_instance = MagicMock()
        with patch(
            "app.services.geolocation.get_geolocation_service_instance",
            new_callable=AsyncMock,
        ) as mock_geo_getter:
            mock_geo_getter.return_value = mock_geo_instance
            geo_serv = await get_geolocation_service()
            assert geo_serv is mock_geo_instance

        # 11. Redis session
        redis_session_serv = await get_redis_session_service()
        assert redis_session_serv is not None

        # 12. Login service
        login_serv = await get_login_service(
            db=mock_session,
            session_service=session_serv,
            audit=MagicMock(),
            redis_session_service=redis_session_serv,
            geolocation_service=geo_serv,
        )
        assert login_serv is not None

        # 13. Analytics
        mock_analytics_instance = MagicMock()
        with patch(
            "app.services.analytics.get_analytics_service",
            return_value=mock_analytics_instance,
        ):
            analytics_serv = get_analytics_service()
            assert analytics_serv is mock_analytics_instance
