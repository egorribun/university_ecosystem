"""Tests for schedule router (app/routers/schedule.py).

Validates _build_filename helper and the download_schedule_ics endpoint
for correct Content-Type, Content-Disposition, locale handling, and 404 paths.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers.schedule import _build_filename

# ---------------------------------------------------------------------------
# _build_filename unit tests
# ---------------------------------------------------------------------------


class TestBuildFilename:
    """Tests for the _build_filename helper."""

    def test_normal_group_name(self):
        """Normal group name produces a sanitized filename."""
        group = MagicMock()
        group.id = uuid.uuid4()
        group.name = "Computer Science 101"
        result = _build_filename(group)
        assert result == "schedule-computer-science-101.ics"

    def test_special_characters(self):
        """Special characters are replaced with hyphens."""
        group = MagicMock()
        group.id = uuid.uuid4()
        group.name = "CS/IT & ML (2024)"
        result = _build_filename(group)
        assert result.startswith("schedule-")
        assert result.endswith(".ics")
        # Only A-Za-z0-9 and hyphens should remain
        name_part = result[len("schedule-") : -len(".ics")]
        assert all(c.isalnum() or c == "-" for c in name_part)

    def test_empty_name_uses_group_id(self):
        """Empty name falls back to group-{id}."""
        group = MagicMock()
        group.id = uuid.uuid4()
        group.name = ""
        result = _build_filename(group)
        assert f"group-{group.id}" in result
        assert result.endswith(".ics")

    def test_none_name_uses_group_id(self):
        """None name falls back to group-{id}."""
        group = MagicMock()
        group.id = uuid.uuid4()
        group.name = None
        result = _build_filename(group)
        assert f"group-{group.id}" in result
        assert result.endswith(".ics")

    def test_unicode_name(self):
        """Unicode characters in group name are handled."""
        group = MagicMock()
        group.id = uuid.uuid4()
        group.name = "Группа Математика 201"
        result = _build_filename(group)
        assert result.startswith("schedule-")
        assert result.endswith(".ics")
        # Unicode letters are not in [A-Za-z0-9], so they get replaced
        # The result should still be a valid filename

    def test_only_special_chars_uses_group_id(self):
        """Group name with only special characters falls back to group-{id}."""
        group = MagicMock()
        group.id = uuid.uuid4()
        group.name = "!@#$%^&*()"
        result = _build_filename(group)
        # After regex replacement, all chars become hyphens, stripped → empty
        assert f"group-{group.id}" in result

    @pytest.mark.parametrize(
        ("name", "expected_contains"),
        [
            ("Group A", "group-a"),
            ("CS-301", "cs-301"),
            ("ML_and_AI", "ml-and-ai"),
        ],
        ids=["simple", "with_hyphen", "with_underscore"],
    )
    def test_various_names(self, name: str, expected_contains: str):
        """Various group names produce expected filename patterns."""
        group = MagicMock()
        group.id = uuid.uuid4()
        group.name = name
        result = _build_filename(group)
        assert expected_contains in result


# ---------------------------------------------------------------------------
# download_schedule_ics endpoint tests
# ---------------------------------------------------------------------------


def _build_schedule_app() -> FastAPI:
    """Build a test app with the schedule router."""
    from app.routers.schedule import router

    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


class TestDownloadScheduleIcs:
    """Tests for the download_schedule_ics endpoint."""

    @pytest.mark.asyncio
    async def test_returns_ics_with_correct_headers(self):
        """Successful request returns ICS content with correct Content-Type."""
        group_id = uuid.uuid4()
        mock_group = MagicMock()
        mock_group.id = group_id
        mock_group.name = "Test Group"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_group)

        mock_service = MagicMock()
        mock_service.get_schedule = AsyncMock(return_value=[])

        ics_content = "BEGIN:VCALENDAR\nEND:VCALENDAR"

        app = _build_schedule_app()

        from app.api.deps import get_read_schedule_service
        from app.core.database import get_read_db

        app.dependency_overrides[get_read_db] = lambda: mock_db
        app.dependency_overrides[get_read_schedule_service] = lambda: mock_service

        with patch(
            "app.routers.schedule.generate_schedule_ics",
            return_value=ics_content,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(f"/schedule/ics?group={group_id}")

        assert response.status_code == 200
        assert "text/calendar" in response.headers.get("content-type", "")
        assert "charset=utf-8" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_group_not_found_returns_404(self):
        """Missing group returns 404."""
        group_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        mock_service = MagicMock()

        app = _build_schedule_app()

        from app.api.deps import get_read_schedule_service
        from app.core.database import get_read_db

        app.dependency_overrides[get_read_db] = lambda: mock_db
        app.dependency_overrides[get_read_schedule_service] = lambda: mock_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/schedule/ics?group={group_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_locale_header_set(self):
        """Content-Language header is set when locale is resolved."""
        group_id = uuid.uuid4()
        mock_group = MagicMock()
        mock_group.id = group_id
        mock_group.name = "Locale Group"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_group)

        mock_service = MagicMock()
        mock_service.get_schedule = AsyncMock(return_value=[])

        app = _build_schedule_app()

        from app.api.deps import get_read_schedule_service
        from app.core.database import get_read_db

        app.dependency_overrides[get_read_db] = lambda: mock_db
        app.dependency_overrides[get_read_schedule_service] = lambda: mock_service

        with (
            patch(
                "app.routers.schedule.generate_schedule_ics",
                return_value="BEGIN:VCALENDAR\nEND:VCALENDAR",
            ),
            patch(
                "app.routers.schedule.resolve_locale",
                return_value="uk",
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(
                    f"/schedule/ics?group={group_id}",
                    headers={"Accept-Language": "uk"},
                )

        assert response.status_code == 200
        assert response.headers.get("content-language") == "uk"

    @pytest.mark.asyncio
    async def test_content_disposition_has_sanitized_filename(self):
        """Content-Disposition header contains a sanitized .ics filename."""
        group_id = uuid.uuid4()
        mock_group = MagicMock()
        mock_group.id = group_id
        mock_group.name = "My Group / 2024"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_group)

        mock_service = MagicMock()
        mock_service.get_schedule = AsyncMock(return_value=[])

        app = _build_schedule_app()

        from app.api.deps import get_read_schedule_service
        from app.core.database import get_read_db

        app.dependency_overrides[get_read_db] = lambda: mock_db
        app.dependency_overrides[get_read_schedule_service] = lambda: mock_service

        with patch(
            "app.routers.schedule.generate_schedule_ics",
            return_value="BEGIN:VCALENDAR\nEND:VCALENDAR",
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(f"/schedule/ics?group={group_id}")

        assert response.status_code == 200
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".ics" in disposition
        # Filename should not contain path separators
        assert (
            "/" not in disposition.split("filename=")[1]
            if "filename=" in disposition
            else True
        )

    @pytest.mark.asyncio
    async def test_cache_control_no_cache(self):
        """Response includes Cache-Control: no-cache."""
        group_id = uuid.uuid4()
        mock_group = MagicMock()
        mock_group.id = group_id
        mock_group.name = "Cache Test"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_group)

        mock_service = MagicMock()
        mock_service.get_schedule = AsyncMock(return_value=[])

        app = _build_schedule_app()

        from app.api.deps import get_read_schedule_service
        from app.core.database import get_read_db

        app.dependency_overrides[get_read_db] = lambda: mock_db
        app.dependency_overrides[get_read_schedule_service] = lambda: mock_service

        with patch(
            "app.routers.schedule.generate_schedule_ics",
            return_value="BEGIN:VCALENDAR\nEND:VCALENDAR",
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(f"/schedule/ics?group={group_id}")

        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-cache"

    @pytest.mark.asyncio
    async def test_locale_header_omitted_when_locale_is_unresolved(self):
        from app.routers.schedule import download_schedule_ics

        group_id = uuid.uuid4()
        group = MagicMock()
        group.id = group_id
        group.name = "No Locale"
        db = AsyncMock()
        db.get.return_value = group
        service = MagicMock()
        service.get_schedule = AsyncMock(return_value=[])
        request = MagicMock()

        with (
            patch("app.routers.schedule.resolve_locale", return_value=None),
            patch(
                "app.routers.schedule.generate_schedule_ics",
                return_value="BEGIN:VCALENDAR\nEND:VCALENDAR",
            ),
        ):
            response = await download_schedule_ics(request, service, group_id, db)

        assert response.status_code == 200
        assert "content-language" not in response.headers
