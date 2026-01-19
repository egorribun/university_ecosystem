import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_static_file_served_with_cache_control(root_client):
    avatars_dir = settings.static_dir_path / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    file_path = avatars_dir / "demo.txt"
    file_path.write_text("demo", encoding="utf-8")

    response = await root_client.get("/static/avatars/demo.txt")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/plain")
    cache_control = response.headers.get("cache-control", "")
    assert "max-age=" in cache_control.lower()
    assert "public" in cache_control.lower()
    assert "immutable" not in cache_control.lower()

    file_path.unlink(missing_ok=True)
    # Leave directories in place for other tests.
